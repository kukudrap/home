"""Integrity of the committed snapshot: every number of the report can be traced to a stored, real search."""
import json
import re
import unittest
from pathlib import Path

from dopamine_king.radar import analyze as A
from dopamine_king.radar import collect as rc
from dopamine_king.verticals import load_vertical

ROOT = Path(__file__).resolve().parent.parent
RADAR = ROOT / "radar"
SNAPSHOT = RADAR / "snapshots" / "2026-10-23"
DRAFTS = RADAR / "drafts" / "2026-10-23"
PLAN = rc.load_plan(RADAR / "plan.json")
RECORDS = rc.load_records(SNAPSHOT, PLAN)
BY_ID = {r["id"]: r for r in RECORDS}
EM, EN = chr(0x2014), chr(0x2013)


def folded(text):
    return rc._fold(text)


class PlanTests(unittest.TestCase):
    def test_the_plan_has_the_groups_it_names_and_unique_ids(self):
        groups = set(PLAN["groups"])
        self.assertTrue({q["group"] for q in PLAN["queries"]} <= groups)
        self.assertEqual(len({q["id"] for q in PLAN["queries"]}), len(PLAN["queries"]))
        self.assertEqual(PLAN["brand"]["own_domains"], ["mitolight.cz"])

    def test_every_persona_of_the_plan_is_a_persona_of_the_vertical(self):
        personas = {p["id"] for p in load_vertical("pbm").personas()}
        self.assertTrue({q["persona"] for q in PLAN["queries"] if q.get("persona")} <= personas)
        self.assertTrue(personas <= {q["persona"] for q in PLAN["queries"] if q.get("persona")})        # every persona is searched

    def test_the_plan_covers_the_brand_the_category_the_personas_the_rivals_and_the_study_leads(self):
        by_group = {g: [q for q in PLAN["queries"] if q["group"] == g] for g in PLAN["groups"]}
        self.assertGreaterEqual(len(by_group["brand"]), 5)
        self.assertGreaterEqual(len(by_group["category"]), 10)
        self.assertGreaterEqual(len(by_group["persona"]), 12)
        self.assertGreaterEqual(len(by_group["competitor"]), 5)
        self.assertGreaterEqual(len(by_group["brandsite"]), 10)
        self.assertTrue(all(q.get("domains") for q in by_group["brandsite"] + by_group["own"]))


class RecordTests(unittest.TestCase):
    def test_every_planned_search_is_stored_and_nothing_else_is(self):
        manifest = json.loads((SNAPSHOT / "snapshot.json").read_text("utf-8"))
        self.assertEqual(manifest["missing"], [])
        self.assertEqual({r["id"] for r in RECORDS}, {q["id"] for q in PLAN["queries"]})
        self.assertEqual((manifest["records"], manifest["planned"]), (len(RECORDS), len(PLAN["queries"])))

    def test_each_record_is_a_search_that_ran_as_planned(self):
        planned = {q["id"]: q for q in PLAN["queries"]}
        for rec in RECORDS:
            plan = planned[rec["id"]]
            self.assertEqual(rec["query"], plan["q"], rec["id"])
            self.assertEqual(folded(rec["query_sent"]), folded(rec["query"]), rec["id"])
            self.assertEqual(rec["allowed_domains"], sorted(d.lower() for d in plan.get("domains", [])), rec["id"])
            self.assertEqual((rec["group"], rec.get("persona", "")), (plan["group"], plan.get("persona", "")), rec["id"])
            self.assertEqual(rec["tool"], rc.TOOL_NAME, rec["id"])
            self.assertGreaterEqual(rec["web_searches"], 1, rec["id"])
            self.assertRegex(rec["retrieved_at"], r"^2026-10-2\dT\d\d:\d\d:\d\dZ$", rec["id"])
            self.assertTrue(rec["model"].startswith("claude-"), rec["id"])

    def test_links_are_ranked_real_addresses(self):
        for rec in RECORDS:
            self.assertGreaterEqual(len(rec["links"]), 5, rec["id"])
            self.assertEqual([l["rank"] for l in rec["links"]], list(range(1, len(rec["links"]) + 1)), rec["id"])
            for link in rec["links"]:
                self.assertRegex(link["url"], r"^https?://[^\s/]+\.[^\s/]+", (rec["id"], link["url"]))
                self.assertIsInstance(link["title"], str)

    def test_the_summary_is_kept_apart_as_text(self):
        for rec in RECORDS:
            self.assertIsInstance(rec["summary"], str, rec["id"])
            self.assertTrue(rec["summary"].strip(), rec["id"])

    def test_site_searches_return_pages_of_the_named_site(self):
        for rec in RECORDS:
            if rec["group"] == "own":
                if rec["allowed_domains"] == ["mitolight.cz"]:
                    self.assertTrue(all(A.host_matches(A.host_of(l["url"]), ["mitolight.cz"]) for l in rec["links"]), rec["id"])


class DirectCheckTests(unittest.TestCase):
    def test_a_search_made_directly_with_the_tool_agrees_with_the_stored_one(self):
        direct = A.load_direct(SNAPSHOT)
        self.assertGreaterEqual(len(direct), 5)
        for row in A.validation(RECORDS, direct):
            self.assertGreaterEqual(row["shared"] / row["direct_links"], 0.8, row)

    def test_a_direct_record_names_its_method_and_date(self):
        for d in A.load_direct(SNAPSHOT):
            self.assertIn("direct WebSearch tool call", d["method"])
            self.assertEqual(d["retrieved_on"], "2026-10-23")
            self.assertTrue(d["links"])


class NoLongDashTests(unittest.TestCase):
    def test_no_file_of_the_radar_has_a_long_dash(self):
        files = [p for p in RADAR.rglob("*") if p.is_file()]
        self.assertGreater(len(files), 100)
        for path in files:
            text = path.read_text("utf-8")
            self.assertNotIn(EM, text, path)
            self.assertNotIn(EN, text, path)


class DraftTests(unittest.TestCase):
    def test_the_index_matches_the_saved_packs_and_nothing_is_blocked(self):
        index = json.loads((DRAFTS / "index.json").read_text("utf-8"))
        self.assertEqual(len(index), 9)
        for row in index:
            pack = json.loads((DRAFTS / row["id"] / "pack.json").read_text("utf-8"))
            self.assertEqual(pack["items"][0]["verdict"], row["verdict"], row["id"])
            self.assertNotEqual(row["verdict"], "blocked", row["id"])
            self.assertEqual(row["errors"], 0, row["id"])
            self.assertEqual(row["writer"], "claude-code", row["id"])


class LedgerTests(unittest.TestCase):
    def test_a_study_verified_by_the_snapshot_names_searches_that_exist(self):
        vertical = load_vertical("pbm")
        own = {s["id"] for s in json.loads((vertical.path / "ledger.json").read_text("utf-8"))["studies"]}
        marker = "web search on 2026-10-23"
        checked = [s for s in vertical.ledger().studies if s.id in own and s.verified and marker in s.verification_note]
        self.assertEqual(len(checked), 14)
        for study in checked:
            ids = re.findall(r"\bstudy2?-[a-z0-9-]+", study.verification_note)
            self.assertTrue(ids, study.id)
            for qid in ids:
                self.assertIn(qid, BY_ID, (study.id, qid))
            self.assertTrue(study.venue and study.year, study.id)
            self.assertTrue(study.url or study.doi, study.id)

    def test_the_two_leads_that_stay_open_say_why(self):
        vertical = load_vertical("pbm")
        own = {s["id"] for s in json.loads((vertical.path / "ledger.json").read_text("utf-8"))["studies"]}
        open_ = [s for s in vertical.ledger().studies if s.id in own and not s.verified]
        self.assertEqual(len(open_), 2)
        for study in open_:
            self.assertTrue(study.verification_note.startswith("Not verified"), study.id)


if __name__ == "__main__":
    unittest.main()
