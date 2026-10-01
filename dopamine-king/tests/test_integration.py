"""Cross-module checks: packs, CLI and API working together on offline data."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from dopamine_king import cli
from dopamine_king.generate import formats as registry
from dopamine_king.generate.packs import DEFAULT_FORMATS, build_pack
from dopamine_king.generate.providers import slot_violations
from dopamine_king.generate.types import Brief, Skeleton, Slot
from dopamine_king.server import handle_api

EN = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", cohort="sport", keyword="running shoes for beginners",
           facts=["Our Aero 2 weighs 210 g."], cta="Try the Aero 2 for 30 days")
CS = Brief(brand="Hrnek a Hvězda", topic="domácí káva", audience="začátečníci", lang="cs", cohort="cz-local", keyword="domácí káva",
           facts=["Pražíme každý týden v malých dávkách."], cta="Objednejte první balení",
           topic_forms={"gen": "domácí kávy", "acc": "domácí kávu", "loc": "domácí kávě"})


class FillerWriter:
    """Fills every slot with text that satisfies its constraints (pipeline test double)."""

    name = "filler"

    def fill(self, skeleton: Skeleton, brief: Brief) -> dict[str, str]:
        return {s.id: self._fit(s, brief) for s in skeleton.slots}

    @staticmethod
    def _fit(slot: Slot, brief: Brief) -> str:
        if slot.default and not slot_violations(slot, slot.default):
            return slot.default
        words = (brief.facts[0] if brief.facts else brief.topic).split()
        text = " ".join(slot.must_include + words * 4)
        if slot.max_words:
            text = " ".join(text.split()[: slot.max_words])
        while slot.min_chars and len(text) < slot.min_chars:
            text += " " + " ".join(words)
        if slot.max_chars:
            text = text[: slot.max_chars].rstrip()
        return text


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class PackTests(unittest.TestCase):
    def test_every_registered_format_builds_offline_in_both_languages(self):
        ids = list(registry.all_formats())
        self.assertGreaterEqual(len(ids), 25)
        for brief in (EN, CS):
            pack = build_pack(brief, ids, improve_rounds=0)
            self.assertEqual(pack.errors, [])
            self.assertEqual(len(pack.items), len(ids))
            for item in pack.items:
                self.assertTrue(item.hook, item.format)
                self.assertIn(item.verdict, ("ok", "review", "blocked"))
                self.assertNotIn(chr(0x2014), item.body, item.format)
                self.assertNotIn("CITATION_UNKNOWN", [i["code"] for i in item.issues], item.format)
            json.dumps(pack.to_dict())

    def test_default_formats_all_exist(self):
        known = set(registry.all_formats())
        self.assertTrue(set(DEFAULT_FORMATS) <= known, set(DEFAULT_FORMATS) - known)

    def test_filled_drafts_have_no_open_slots(self):
        pack = build_pack(EN, list(DEFAULT_FORMATS), writer=FillerWriter(), improve_rounds=0)
        for item in pack.items:
            self.assertEqual(item.slots_open, [], item.format)
        self.assertEqual(pack.summary["open_slots"], 0)

    def test_scores_for_article_formats(self):
        pack = build_pack(EN, ["seo_article", "geo_answer_page"], writer=FillerWriter(), improve_rounds=0)
        by_format = {i.format: i for i in pack.items}
        self.assertIsNotNone(by_format["seo_article"].scores["seo"])
        self.assertIsNotNone(by_format["seo_article"].scores["geo"])
        self.assertIsNotNone(by_format["geo_answer_page"].scores["geo"])

    def test_offline_article_is_not_publishable_without_experience(self):
        brief = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="running shoes")
        pack = build_pack(brief, ["seo_article"], improve_rounds=0)
        item = pack.items[0]
        self.assertEqual(item.verdict, "blocked")
        self.assertTrue(any(i["severity"] == "error" for i in item.issues))

    def test_save_writes_report_and_side_files(self):
        pack = build_pack(EN, ["hook_set", "short_video_script", "seo_article"], improve_rounds=0)
        with tempfile.TemporaryDirectory() as tmp:
            written = pack.save(tmp)
            names = {p.name for p in written}
            self.assertIn("pack.json", names)
            self.assertIn("report.md", names)
            self.assertTrue(any(n.endswith(".md") and n[:2].isdigit() for n in names))
            self.assertEqual(json.loads((Path(tmp) / "pack.json").read_text("utf-8"))["brief"]["brand"], "Zorvia")

    def test_unknown_format_is_reported_not_raised(self):
        pack = build_pack(EN, ["linkedin_post", "no_such_format"], improve_rounds=0)
        self.assertEqual(len(pack.items), 1)
        self.assertEqual(len(pack.errors), 1)


class CliTests(unittest.TestCase):
    def test_demo_runs_end_to_end(self):
        code, out, err = run_cli("demo")
        self.assertEqual(code, 0, err)
        for needle in ("1. Corpus", "2. Pattern mining", "3. Score", "4. Lab", "5. Evidence", "6. Forge", "7. Guru", "Done in"):
            self.assertIn(needle, out)
        self.assertNotIn("not available", out)

    def test_score_and_compare_json(self):
        code, out, _ = run_cli("score", "7 mistakes every beginner runner makes", "--json")
        self.assertEqual(code, 0)
        self.assertGreater(json.loads(out)["total"], 40)
        code, out, _ = run_cli("compare", "Why most dashboards lie to you", "Our update", "--json")
        self.assertEqual(json.loads(out)["winner"], "a")

    def test_formats_and_forge_offline(self):
        code, out, _ = run_cli("formats", "--family", "social")
        self.assertEqual(code, 0)
        self.assertIn("linkedin_post", out)
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run_cli("forge", "--brand", "Zorvia", "--topic", "running shoes", "--audience", "beginner runners",
                                     "--formats", "hook_set,linkedin_post", "--writer", "offline", "--quiet", "--out", tmp)
            self.assertEqual(code, 0, err)
            self.assertTrue((Path(tmp) / "pack.json").exists())
            self.assertIn("2 formats", err)

    def test_forge_requires_brand_fields(self):
        with self.assertRaises(SystemExit):
            run_cli("forge", "--brand", "Zorvia")

    def test_guru_plan_markdown(self):
        code, out, _ = run_cli("guru", "plan", "--brand", "Zorvia", "--topic", "running shoes", "--audience", "beginner runners", "--cohort", "sport")
        self.assertEqual(code, 0)
        self.assertIn("Content plan", out)

    def test_lab_commands(self):
        self.assertIn("8158", run_cli("lab", "size", "--baseline", "0.05", "--mde", "0.2")[1])
        self.assertIn("significant: True", run_cli("lab", "ab", "--a", "100/1000", "--b", "130/1000")[1])


class ApiIntegrationTests(unittest.TestCase):
    def test_formats_and_forge_endpoints(self):
        status, formats = handle_api("GET", "/api/formats", None)
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(formats), 25)
        self.assertTrue(all({"id", "name_en", "name_cs", "family", "platform", "limits"} <= set(f) for f in formats))
        status, pack = handle_api("POST", "/api/forge", {"brief": EN.to_dict(), "formats": ["hook_set", "linkedin_post"], "writer": "offline"})
        self.assertEqual(status, 200)
        self.assertEqual(len(pack["items"]), 2)
        self.assertEqual(pack["writer"], "offline")
        self.assertIn("summary", pack)


if __name__ == "__main__":
    unittest.main()
