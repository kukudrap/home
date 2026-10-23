"""The radar collector: reading the real tool stream, refusing searches that did not run as asked, resumable collection."""
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dopamine_king.radar import collect as rc

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "radar" / "claude_stream_websearch.jsonl"
STREAM = FIXTURE.read_text("utf-8")
QUERY = "terapie červeným světlem panel"
EM, EN = chr(0x2014), chr(0x2013)
NOW = lambda: datetime(2026, 10, 23, 12, 30, 5, tzinfo=timezone.utc)


class Runner:
    """A stand-in for subprocess.run that records every call and answers from a script."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, cmd, **kwargs):
        self.calls.append({"cmd": cmd, **kwargs})
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, tuple):
            code, out, err = item
            return SimpleNamespace(returncode=code, stdout=out, stderr=err)
        return SimpleNamespace(returncode=0, stdout=item, stderr="")


def stream(query=QUERY, *, domains=None, title="Titulek", url="https://example.cz/a", summary="Souhrn.", searches=1, error=False, call=True):
    """A minimal stream in the shape of the real one."""
    events = []
    if call:
        inp = {"query": query, "mode": "standard"}
        if domains is not None:
            inp["allowed_domains"] = domains
        events.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "WebSearch", "input": inp}]}})
        events.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "text"}]},
                       "tool_use_result": {"query": query, "results": [{"tool_use_id": "s1", "content": [{"title": title, "url": url}]}, summary]}})
    events.append({"type": "result", "subtype": "error" if error else "success", "is_error": error, "result": "Credit balance is too low" if error else "DONE",
                   "modelUsage": {"claude-haiku-5-5": {"webSearchRequests": searches}}})
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


class ParseTests(unittest.TestCase):
    def test_the_real_stream_gives_the_links_and_the_summary_exactly(self):
        parsed = rc.parse_events(STREAM)
        self.assertEqual(len(parsed["calls"]), 1)
        call = parsed["calls"][0]
        self.assertEqual(call["input"]["query"], QUERY)
        self.assertEqual(len(call["links"]), 9)
        self.assertEqual(call["links"][0]["url"], "https://dwn.alza.cz/manual/160634")
        self.assertEqual(call["links"][3]["title"], "Červené světlo, jak funguje terapie lampou?")
        self.assertTrue(call["summary"].startswith("The search returned mostly Czech-language sources"))
        self.assertEqual((parsed["web_searches"], parsed["model"]), (1, "claude-haiku-5-5"))

    def test_lines_that_are_not_events_are_ignored(self):
        parsed = rc.parse_events("Warning: no stdin\n\n[1, 2]\n{broken\n" + STREAM)
        self.assertEqual(len(parsed["calls"]), 1)

    def test_a_stream_without_a_search_has_no_calls(self):
        self.assertEqual(rc.parse_events(stream(call=False))["calls"], [])
        self.assertEqual(rc.parse_events("")["final"], {})


class SearchTests(unittest.TestCase):
    def run_search(self, out, query=QUERY, domains=(), **kwargs):
        runner = Runner(out)
        record = rc.search(query, domains, runner=runner, now=NOW, **kwargs)
        return record, runner

    def test_a_real_stream_becomes_a_record(self):
        record, runner = self.run_search(STREAM)
        self.assertEqual((record["query"], record["query_sent"], record["allowed_domains"], record["mode"]), (QUERY, QUERY, [], "standard"))
        self.assertEqual((record["retrieved_at"], record["tool"], record["model"], record["web_searches"]), ("2026-10-23T12:30:05Z", rc.TOOL_NAME, "claude-haiku-5-5", 1))
        self.assertEqual([l["rank"] for l in record["links"]], list(range(1, 10)))
        self.assertEqual(record["links"][1]["url"], "https://www.drmax.cz/cbd-star-red-light-panel-300-w-terapie-cervenym-svetlem")
        self.assertIn("Mito Light and Lighthacker panels are compared", record["summary"])
        self.assertTrue(runner.calls[0]["capture_output"] and runner.calls[0]["text"])

    def test_the_command_has_only_the_search_tool_and_no_session(self):
        cmd = rc.command(rc.build_prompt(QUERY, ["mitolight.cz"]), model="haiku", executable="claude")
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertEqual(cmd[cmd.index("--tools") + 1], "WebSearch")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "WebSearch")
        for flag in ("--no-session-persistence", "--strict-mcp-config", "--disable-slash-commands", "--verbose"):
            self.assertIn(flag, cmd)
        self.assertNotIn("--bare", cmd)                                 # bare mode would ignore the subscription login
        self.assertIn(json.dumps(QUERY, ensure_ascii=False), cmd[2])
        self.assertIn('["mitolight.cz"]', cmd[2])

    def test_the_api_key_is_not_passed_on_and_the_run_has_an_empty_directory(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test", "KEEP_ME": "1"}):
            _, runner = self.run_search(STREAM)
        call = runner.calls[0]
        self.assertNotIn("ANTHROPIC_API_KEY", call["env"])
        self.assertEqual(call["env"]["KEEP_ME"], "1")
        self.assertNotIn(os.getcwd(), call["cwd"])
        self.assertIs(call["stdin"], subprocess.DEVNULL)

    def test_long_dashes_in_titles_and_summaries_are_replaced(self):
        record, _ = self.run_search(stream(title=f"Název {EN} druhá část {EM} konec", summary=f"Věta {EM} druhá."))
        self.assertNotIn(EN, record["links"][0]["title"])
        self.assertNotIn(EM, record["summary"])
        self.assertIn("Název - druhá část - konec", record["links"][0]["title"])

    def test_a_search_that_changed_the_query_is_refused(self):
        with self.assertRaises(rc.SearchError) as ctx:
            self.run_search(stream(query="jiný dotaz"))
        self.assertIn("another query", str(ctx.exception))

    def test_a_pair_of_quotation_marks_around_the_query_is_accepted(self):
        record, _ = self.run_search(stream(query=f'"{QUERY}"'))
        self.assertEqual(record["query_sent"], f'"{QUERY}"')

    def test_a_changed_domain_filter_is_refused_and_a_kept_one_is_stored(self):
        with self.assertRaises(rc.SearchError) as ctx:
            self.run_search(stream(domains=["other.cz"]), domains=["mitolight.cz"])
        self.assertIn("domain filter", str(ctx.exception))
        record, _ = self.run_search(stream(domains=["MitoLight.cz"]), domains=["mitolight.cz"])
        self.assertEqual(record["allowed_domains"], ["mitolight.cz"])

    def test_no_tool_call_no_result_and_no_search_request_are_refused(self):
        for out, needle in ((stream(call=False), "did not call"), (stream(searches=0), "no web search"), ("", "without a result")):
            with self.assertRaises(rc.SearchError) as ctx:
                self.run_search(out)
            self.assertIn(needle, str(ctx.exception))

    def test_an_error_result_a_failed_exit_a_missing_command_and_a_timeout_are_reported(self):
        cases = ((stream(error=True), "Credit balance"), ((1, "", "Not logged in. Run /login"), "Not logged in"),
                 (FileNotFoundError("claude"), "log in"), (subprocess.TimeoutExpired("claude", 5), "No answer"))
        for item, needle in cases:
            with self.assertRaises(rc.SearchError) as ctx:
                rc.search(QUERY, runner=Runner(item), now=NOW)
            self.assertIn(needle, str(ctx.exception))


PLAN = {"name": "test", "queries": [
    {"id": "a-01", "group": "brand", "q": "first", "purpose": "Co lidé hledají"},
    {"id": "b-01", "group": "category", "q": "second", "domains": ["example.cz"], "persona": "fitness"},
]}


def fake_search(calls, fail=()):
    def search(query, domains=(), **kwargs):
        calls.append((query, list(domains)))
        if query in fail:
            raise rc.SearchError("boom")
        return {"query": query, "query_sent": query, "allowed_domains": list(domains), "mode": "standard", "retrieved_at": "2026-10-23T10:00:00Z",
                "tool": rc.TOOL_NAME, "model": "claude-haiku-5-5", "web_searches": 1,
                "links": [{"rank": 1, "title": "T", "url": "https://example.cz/"}], "summary": "S"}
    return search


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.out = Path(self.dir.name) / "snap"

    def test_every_planned_search_is_stored_with_its_plan_fields_and_a_manifest(self):
        calls = []
        summary = rc.collect(PLAN, self.out, search_fn=fake_search(calls), jobs=2, log=lambda line: None)
        self.assertEqual((summary["requested"], summary["stored"], summary["errors"]), (2, 2, {}))
        rec = json.loads((self.out / "raw" / "b-01.json").read_text("utf-8"))
        self.assertEqual((rec["id"], rec["group"], rec["persona"], rec["allowed_domains"]), ("b-01", "category", "fitness", ["example.cz"]))
        self.assertEqual(json.loads((self.out / "raw" / "a-01.json").read_text("utf-8"))["purpose"], "Co lidé hledají")
        manifest = json.loads((self.out / "snapshot.json").read_text("utf-8"))
        self.assertEqual((manifest["records"], manifest["planned"], manifest["missing"]), (2, 2, []))
        self.assertEqual(manifest["first_retrieved_at"], "2026-10-23T10:00:00Z")

    def test_a_second_run_only_does_what_is_missing_and_force_redoes_it(self):
        calls = []
        rc.collect(PLAN, self.out, search_fn=fake_search(calls), log=lambda line: None)
        rc.collect(PLAN, self.out, search_fn=fake_search(calls), log=lambda line: None)
        self.assertEqual(len(calls), 2)
        rc.collect(PLAN, self.out, search_fn=fake_search(calls), force=True, only={"a-01"}, log=lambda line: None)
        self.assertEqual(len(calls), 3)

    def test_a_failed_search_is_retried_once_reported_and_not_stored(self):
        calls = []
        summary = rc.collect(PLAN, self.out, search_fn=fake_search(calls, fail={"second"}), log=lambda line: None)
        self.assertEqual(calls.count(("second", ["example.cz"])), 2)
        self.assertEqual((summary["stored"], list(summary["errors"])), (1, ["b-01"]))
        self.assertFalse((self.out / "raw" / "b-01.json").exists())
        manifest = json.loads((self.out / "snapshot.json").read_text("utf-8"))
        self.assertEqual(manifest["missing"], ["b-01"])

    def test_records_load_in_plan_order(self):
        rc.collect(PLAN, self.out, search_fn=fake_search([]), log=lambda line: None)
        self.assertEqual([r["id"] for r in rc.load_records(self.out, PLAN)], ["a-01", "b-01"])

    def test_the_plan_is_checked(self):
        path = Path(self.dir.name) / "plan.json"
        for queries, needle in (([{"id": "x", "group": "g", "q": "a"}, {"id": "x", "group": "g", "q": "b"}], "duplicate"),
                                ([{"id": "Bad Id", "group": "g", "q": "a"}], "bad query id")):
            path.write_text(json.dumps({"queries": queries}), "utf-8")
            with self.assertRaises(ValueError) as ctx:
                rc.load_plan(path)
            self.assertIn(needle, str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
