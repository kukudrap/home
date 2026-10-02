"""The Claude Code writer: slots written through the local `claude -p` command (the logged-in Claude subscription)."""
import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from dopamine_king import cli
from dopamine_king.generate.providers import (
    SYSTEM_PROMPT, ClaudeCodeWriter, WriterError, select_writer, slots_schema,
)
from dopamine_king.generate.types import Brief, Skeleton, Slot

EM, EN = chr(0x2014), chr(0x2013)


def skeleton():
    return Skeleton(
        format="linkedin_post", lang="en", template="{{hook}}\n\n{{body}}\n\n{{cta}}",
        slots=[
            Slot("hook", "Write the hook", max_chars=40, kind="title", default="7 mistakes new runners make"),
            Slot("body", "Write the body", max_words=20, must_include=["shoes"]),
            Slot("cta", "Write the CTA", default="Try it today."),
        ],
    )


BRIEF = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", facts=["Our shoes weigh 210 g."])


def reply(payload=None, *, result=None, is_error=False, usage=None):
    data = {"type": "result", "subtype": "error" if is_error else "success", "is_error": is_error,
            "usage": usage if usage is not None else {"input_tokens": 120, "output_tokens": 60, "cache_read_input_tokens": 5}}
    if payload is not None:
        data["structured_output"] = payload
        data["result"] = json.dumps(payload)
    if result is not None:
        data["result"] = result
    return json.dumps(data)


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


GOOD = {"hook": "Shoes that fit", "body": "Pick shoes by foot shape and pace.", "cta": "Read the guide."}


class CommandTests(unittest.TestCase):
    def test_the_command_is_print_mode_with_json_schema_no_tools_and_no_session(self):
        writer = ClaudeCodeWriter(tier="balanced", runner=Runner())
        cmd = writer.command(["hook", "body"])
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertEqual(cmd[cmd.index("--output-format") + 1], "json")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "")
        self.assertIn("--no-session-persistence", cmd)
        self.assertEqual(cmd[cmd.index("--system-prompt") + 1], SYSTEM_PROMPT)
        self.assertEqual(json.loads(cmd[cmd.index("--json-schema") + 1]), slots_schema(["hook", "body"]))
        self.assertNotIn("--bare", cmd)                               # bare mode would ignore the subscription login
        self.assertEqual(cmd[cmd.index("--effort") + 1], "low")       # slot writing needs little thinking

    def test_tiers_map_to_model_aliases_and_an_explicit_model_wins(self):
        for tier, alias in (("premium", "opus"), ("balanced", "sonnet"), ("economy", "haiku"), ("fast", "haiku")):
            cmd = ClaudeCodeWriter(tier=tier, runner=Runner()).command(["a"])
            self.assertEqual(cmd[cmd.index("--model") + 1], alias, tier)
        cmd = ClaudeCodeWriter("claude-opus-5-5", runner=Runner()).command(["a"])
        self.assertEqual(cmd[cmd.index("--model") + 1], "claude-opus-5-5")
        with mock.patch.dict(os.environ, {"KING_CLAUDE_MODEL": "haiku", "KING_EFFORT": "medium", "KING_CLAUDE_BIN": "/opt/claude"}):
            writer = ClaudeCodeWriter(runner=Runner())
            cmd = writer.command(["a"])
        self.assertEqual((cmd[0], cmd[cmd.index("--model") + 1], cmd[cmd.index("--effort") + 1]), ("/opt/claude", "haiku", "medium"))

    def test_the_api_key_is_not_passed_on_unless_asked_for(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test", "KEEP_ME": "1"}):
            runner = Runner(reply(GOOD), reply(GOOD))
            ClaudeCodeWriter(runner=runner).fill(skeleton(), BRIEF)
            ClaudeCodeWriter(runner=Runner(reply(GOOD)), use_api_key=True)
            kept = Runner(reply(GOOD))
            ClaudeCodeWriter(runner=kept, use_api_key=True).fill(skeleton(), BRIEF)
        self.assertNotIn("ANTHROPIC_API_KEY", runner.calls[0]["env"])
        self.assertEqual(runner.calls[0]["env"]["KEEP_ME"], "1")
        self.assertEqual(kept.calls[0]["env"]["ANTHROPIC_API_KEY"], "sk-test")

    def test_the_prompt_goes_in_on_stdin_and_runs_in_an_empty_directory(self):
        runner = Runner(reply(GOOD))
        ClaudeCodeWriter(runner=runner).fill(skeleton(), BRIEF)
        call = runner.calls[0]
        self.assertIn("Our shoes weigh 210 g.", call["input"])
        self.assertIn("{{hook}}", call["input"])
        self.assertTrue(call["capture_output"] and call["text"])
        self.assertTrue(call["cwd"])
        self.assertNotIn(os.getcwd(), call["cwd"])


class FillTests(unittest.TestCase):
    def test_structured_output_fills_the_slots_and_usage_is_counted(self):
        writer = ClaudeCodeWriter(runner=Runner(reply(GOOD)))
        fills = writer.fill(skeleton(), BRIEF)
        self.assertEqual(fills, GOOD)
        self.assertEqual((writer.usage.calls, writer.usage.input_tokens, writer.usage.output_tokens, writer.usage.cache_read_input_tokens),
                         (1, 120, 60, 5))
        self.assertEqual(writer.name, "claude-code")

    def test_long_dashes_are_normalised_and_unknown_keys_dropped(self):
        payload = {**GOOD, "body": f"Pick shoes {EM} by foot shape.", "extra": "ignored"}
        fills = ClaudeCodeWriter(runner=Runner(reply(payload))).fill(skeleton(), BRIEF)
        self.assertNotIn(EM, fills["body"])
        self.assertNotIn("extra", fills)

    def test_missing_slots_keep_their_defaults(self):
        fills = ClaudeCodeWriter(runner=Runner(reply({"hook": "Shoes that fit", "body": "Pick shoes by foot shape."}))).fill(skeleton(), BRIEF)
        self.assertEqual(fills["cta"], "Try it today.")

    def test_the_text_result_is_the_fallback_and_code_fences_are_stripped(self):
        fenced = "```json\n" + json.dumps(GOOD) + "\n```"
        fills = ClaudeCodeWriter(runner=Runner(reply(result=fenced))).fill(skeleton(), BRIEF)
        self.assertEqual(fills, GOOD)

    def test_a_slot_that_breaks_its_limit_is_repaired_in_a_second_call(self):
        bad = {**GOOD, "hook": "x" * 80}
        runner = Runner(reply(bad), reply({"hook": "Shoes that fit"}))
        writer = ClaudeCodeWriter(runner=runner)
        fills = writer.fill(skeleton(), BRIEF)
        self.assertEqual(fills["hook"], "Shoes that fit")
        self.assertEqual(len(runner.calls), 2)
        self.assertIn("problems to fix", runner.calls[1]["input"])
        self.assertEqual(json.loads(runner.calls[1]["cmd"][runner.calls[1]["cmd"].index("--json-schema") + 1])["required"], ["hook"])
        self.assertEqual(writer.usage.calls, 2)

    def test_revise_rewrites_only_the_slots_with_remarks(self):
        runner = Runner(reply({"body": "Choose shoes by foot shape and pace."}))
        writer = ClaudeCodeWriter(runner=runner)
        fills = writer.revise(skeleton(), BRIEF, dict(GOOD), {"body": ["too generic"]})
        self.assertEqual(fills["body"], "Choose shoes by foot shape and pace.")
        self.assertEqual(fills["hook"], GOOD["hook"])
        self.assertEqual(len(runner.calls), 1)
        self.assertEqual(writer.revise(skeleton(), BRIEF, dict(GOOD), {}), GOOD)


class ErrorTests(unittest.TestCase):
    def fail(self, item, needle):
        with self.assertRaises(WriterError) as ctx:
            ClaudeCodeWriter(runner=Runner(item)).fill(skeleton(), BRIEF)
        self.assertIn(needle, str(ctx.exception))

    def test_a_missing_command_says_how_to_install_and_log_in(self):
        self.fail(FileNotFoundError("claude"), "log in")

    def test_a_timeout_a_failed_exit_and_an_error_result_are_reported(self):
        self.fail(subprocess.TimeoutExpired("claude", 5), "did not answer")
        self.fail((1, "", "Not logged in. Run /login"), "Not logged in")
        self.fail(reply(is_error=True, result="Credit balance is too low"), "Credit balance")

    def test_output_that_is_not_json_is_reported(self):
        self.fail("not json at all", "Unexpected output")
        self.fail("[1, 2]", "not a JSON object")
        self.fail(reply(result="plain prose"), "valid JSON")
        self.fail(reply(result="[1]"), "JSON object")


class RealProcessTests(unittest.TestCase):
    """The same writer against a small stand-in executable, so the subprocess plumbing really runs."""

    def make_executable(self, body: str) -> str:
        directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        path = Path(directory) / "fake-claude"
        path.write_text("#!/bin/sh\n" + body, "utf-8")
        path.chmod(path.stat().st_mode | stat.S_IEXEC)
        return str(path)

    def test_a_stand_in_command_answers_over_stdin_and_stdout(self):
        answer = reply(GOOD).replace("'", "")
        exe = self.make_executable(f"cat > /dev/null\nprintf '%s' '{answer}'\n")
        fills = ClaudeCodeWriter(executable=exe).fill(skeleton(), BRIEF)
        self.assertEqual(fills, GOOD)

    def test_the_stand_in_sees_the_arguments_and_no_api_key(self):
        exe = self.make_executable(
            'cat > /dev/null\n'
            'case "$*" in *"--output-format json"*) ;; *) echo "missing flag" >&2; exit 3;; esac\n'
            '[ -z "$ANTHROPIC_API_KEY" ] || { echo "key leaked" >&2; exit 4; }\n'
            f"printf '%s' '{reply(GOOD)}'\n")
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test"}):
            self.assertEqual(ClaudeCodeWriter(executable=exe).fill(skeleton(), BRIEF), GOOD)

    def test_a_failing_stand_in_command_raises(self):
        exe = self.make_executable('cat > /dev/null\necho "boom" >&2\nexit 7\n')
        with self.assertRaises(WriterError) as ctx:
            ClaudeCodeWriter(executable=exe).fill(skeleton(), BRIEF)
        self.assertIn("exit 7", str(ctx.exception))
        self.assertIn("boom", str(ctx.exception))


class SelectionTests(unittest.TestCase):
    def test_select_writer_knows_the_claude_code_writer(self):
        writer = select_writer("claude-code", tier="premium")
        self.assertIsInstance(writer, ClaudeCodeWriter)
        self.assertEqual(writer.model, "opus")

    def test_auto_never_picks_it_silently(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(select_writer("auto").name, "offline")

    def test_the_forge_command_offers_it(self):
        with self.assertRaises(SystemExit):
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()) as out:
                cli.main(["forge", "--help"])
        self.assertIn("claude-code", out.getvalue())


if __name__ == "__main__":
    unittest.main()
