"""The photobiomodulation vertical: data files, claim map, samples, bundle and command line."""
import contextlib
import io
import json
import re
import unittest
from pathlib import Path

from dopamine_king import cli
from dopamine_king.generate import claims
from dopamine_king.generate.guard import TrustShield
from dopamine_king.generate.packs import build_pack
from dopamine_king.guru import build_plan
from dopamine_king.guru.planner import PILLARS
from dopamine_king.ingest.registry import validate_brands
from dopamine_king.models import COHORT_LABELS
from dopamine_king.research.models import DESIGNS
from dopamine_king.synth import generate_corpus
from dopamine_king.verticals import LABEL_RANK, VerticalError, list_verticals, load_vertical
from dopamine_king.webdata import build_bundle

DIR = Path(__file__).resolve().parent.parent / "src" / "dopamine_king" / "data" / "verticals" / "pbm"
V = load_vertical("pbm")
PROFILE_CODES = set(claims.RULES) - {"THERAPY_WORD"}


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class LoaderTests(unittest.TestCase):
    def test_the_vertical_is_listed_and_unknown_ones_are_refused(self):
        self.assertIn("pbm", list_verticals())
        with self.assertRaises(VerticalError) as ctx:
            load_vertical("nope")
        self.assertIn("pbm", str(ctx.exception))

    def test_cohorts_are_registered_with_the_same_labels(self):
        self.assertTrue(V.cohorts)
        for cohort, labels in V.cohorts.items():
            self.assertEqual(COHORT_LABELS.get(cohort), labels, cohort)

    def test_no_data_file_contains_a_long_dash(self):
        for path in DIR.glob("*.json"):
            text = path.read_text("utf-8")
            self.assertNotIn(chr(0x2014), text, path.name)
            self.assertNotIn(chr(0x2013), text, path.name)

    def test_public_meta_describes_the_edition(self):
        meta = V.public_meta()
        for key in ("id", "name_en", "name_cs", "tagline_en", "tagline_cs", "edition_en", "edition_cs", "claims_profile",
                    "regulatory_note_en", "regulatory_note_cs", "glossary"):
            self.assertTrue(meta.get(key), key)
        self.assertEqual(meta["claims_profile"], "wellness")
        self.assertGreaterEqual(len(meta["glossary"]), 6)
        self.assertTrue(all(g["def_en"] and g["def_cs"] for g in meta["glossary"]))


class BrandRegistryTests(unittest.TestCase):
    def test_registry_validates(self):
        brands = V.brands()
        self.assertGreaterEqual(len(brands), 20)
        self.assertEqual(validate_brands(brands), [])
        self.assertEqual(len({b.id for b in brands}), len(brands))
        self.assertTrue(all(b.cohort in V.cohorts for b in brands))
        self.assertTrue(all((b.homepage or "").startswith("https://") for b in brands))
        self.assertTrue(all(not b.verified and not b.synthetic for b in brands))

    def test_the_brand_itself_is_in_the_czech_cohort(self):
        mito = next(b for b in V.brands() if b.id == V.default_brand)
        self.assertEqual((mito.cohort, mito.country), ("pbm-cz-sk", "CZ"))
        self.assertIn("mitolight.cz", mito.homepage)


class LedgerAndClaimMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = V.ledger()
        cls.map = {row["id"]: row for row in V.claim_map(cls.ledger)}
        cls.topics = {t["id"]: t for t in V.claims()["topics"]}

    def test_ledger_is_structurally_valid(self):
        self.assertEqual(self.ledger.validate(), [])
        for study in self.ledger.studies:
            self.assertIn(study.design, DESIGNS, study.id)

    def test_every_study_says_how_far_it_was_checked(self):
        own = json.loads((DIR / "ledger.json").read_text("utf-8"))["studies"]
        self.assertGreaterEqual(len(own), 30)
        for study in own:
            note = study["verification_note"].strip()
            self.assertTrue(note, study["id"])
            if study["verified"]:
                self.assertIn("confirmed", note.lower(), study["id"])
                self.assertIn("web search", note.lower(), study["id"])
            else:
                self.assertFalse(note.startswith("Confirmed"), study["id"])

    def test_leads_recalled_from_memory_carry_no_findings(self):
        """A research lead states design and topic only, as context: nothing unchecked can support a claim."""
        leads = [s for s in V.ledger().studies if "recalled from the author's knowledge" in s.verification_note]
        self.assertGreaterEqual(len(leads), 8)
        for study in leads:
            self.assertFalse(study.verified)
            self.assertIn("verify", study.verification_note.lower())
        for study, link in all_pairs(self.ledger):
            if study in leads:
                self.assertEqual(link.direction, "context", (study.id, link.tactic_id))

    def test_every_topic_is_in_the_map_with_a_valid_label(self):
        self.assertEqual(set(self.map), set(self.topics))
        for row in self.map.values():
            self.assertIn(row["label"], LABEL_RANK, row["id"])
            self.assertTrue(row["summary_en"] and row["summary_cs"], row["id"])
            self.assertTrue(row["safe_en"] and row["safe_cs"], row["id"])

    def test_a_label_never_exceeds_its_cap_unless_contested(self):
        for row in self.map.values():
            cap = self.topics[row["id"]]["label_cap"]
            if row["label"] != "contested":
                self.assertLessEqual(LABEL_RANK[row["label"]], LABEL_RANK[cap], row["id"])

    def test_only_verified_studies_are_counted(self):
        for row in self.map.values():
            counted = {s.id for s, _ in self.ledger.evidence_for(row["id"]) if s.verified}
            self.assertEqual(row["n_studies"], len(counted), row["id"])
            self.assertEqual(row["n_pending"], len(row["study_ids"]) - len(counted), row["id"])
        self.assertEqual(self.map["pbm-skin-appearance"]["label"], "none")          # leads only until verified
        self.assertGreater(self.map["pbm-skin-appearance"]["n_pending"], 0)

    def test_medical_and_avoid_topics_stay_blocked_whatever_the_evidence(self):
        for row in self.map.values():
            if row["class"] in ("medical", "avoid"):
                self.assertIn(row["id"], {t.id for t in claims.load_profile("pbm").topics if t.klass in ("medical", "avoid")})

    def test_conflicting_sport_evidence_is_not_hidden(self):
        self.assertEqual(self.map["pbm-exercise-performance"]["label"], "contested")
        counts = self.map["pbm-muscle-recovery"]["direction_counts"]
        self.assertGreater(counts["contradicts"] + counts["mixed"], 0)


def V_ledger_studies():
    return V.ledger().studies


def all_pairs(ledger):
    out = []
    for topic in V.claims()["topics"]:
        out.extend(ledger.evidence_for(topic["id"]))
    return out


class ResearchDataTests(unittest.TestCase):
    """Brand profile and strategy gathered from public sources: sourced, modest and free of personal data."""

    def test_brand_profile_is_sourced_and_free_of_personal_data(self):
        profile = V.brand_profile()
        self.assertGreaterEqual(len(profile["facts"]), 20)
        self.assertGreaterEqual(len(profile["unknowns"]), 8)
        text = json.dumps(profile, ensure_ascii=False)
        self.assertNotRegex(text, r"[\w.+-]+@[\w-]+\.[\w.]+")              # no e-mail address
        self.assertNotRegex(text, r"\d[\d ,.]*\s?CZK")                      # no price snapshots
        for name in ("Procházk", "Žufánek", "Schlesinger"):
            self.assertNotIn(name, text)                                   # no individuals
        for fact in profile["facts"]:
            self.assertTrue(fact["fact_cs"] and fact["fact_en"], fact)
            self.assertTrue(fact["source_url"].startswith("https://"), fact)
            self.assertIn(fact["confidence"], ("high", "medium", "low"))
            self.assertIn(fact["origin"], ("brand", "third-party"))

    def test_the_two_similar_brand_names_are_kept_apart(self):
        text = json.dumps(V.brand_profile(), ensure_ascii=False)
        self.assertIn("Mito Red Light", text)

    def test_hook_bank_passes_the_claims_profile(self):
        hooks = V.strategy()["hooks"]
        self.assertGreaterEqual(len(hooks["cs"]), 30)
        self.assertGreaterEqual(len(hooks["en"]), 30)
        shield = TrustShield()
        for lang in ("cs", "en"):
            brief = V.briefs()[f"mito-light-{lang}"]
            for item in hooks[lang]:
                self.assertLessEqual(len(item["text"]), 90, item["text"])
                errors = [i.code for i in shield.check(item["text"], brief) if i.severity == "error"]
                self.assertEqual(errors, [], item["text"])

    def test_strategy_sections_are_complete(self):
        st = V.strategy()
        self.assertEqual(len(st["topic_clusters"]), 10)
        for cluster in st["topic_clusters"]:
            self.assertTrue(cluster["questions_cs"] and cluster["questions_en"] and cluster["keywords_cs"], cluster["id"])
            for topic in cluster["claim_topics"]:
                self.assertIn(topic, {t["id"] for t in V.claims()["topics"]}, cluster["id"])
        self.assertGreaterEqual(len(st["observed_patterns"]), 20)
        self.assertEqual(len(st["calendar_themes"]), 4)
        self.assertIn("research_notes", st)

    def test_added_bosses_fit_the_game(self):
        self.assertGreaterEqual(len(V.bosses()), 12)
        self.assertEqual(sum(1 for b in V.bosses() if b["lang"] == "cs") >= 4, True)


class SampleBriefTests(unittest.TestCase):
    def test_sample_briefs_use_only_verified_sources(self):
        briefs = V.briefs()
        self.assertEqual({b.lang for b in briefs.values()}, {"cs", "en"})
        verified = {s.id for s in V.ledger().studies if s.verified}
        ids = V._json("briefs.json")["source_ids"]
        for brief in briefs.values():
            self.assertEqual((brief.vertical, brief.claims_profile, brief.brand), ("pbm", "wellness", "MITO LIGHT"))
            self.assertGreaterEqual(len(brief.sources), 3)
            for source in brief.sources:
                self.assertIn(ids[source["id"]], verified)
                self.assertRegex(source["id"], r"^[A-Za-z0-9_.:-]+$")           # usable as [[cite:<id>]]
                self.assertTrue(source["claim"])

    def test_an_unverified_study_never_becomes_a_source(self):
        ledger = V.ledger()
        data = V._json("briefs.json")
        broken = dict(data["source_ids"], vanin2018="seed:pbm-wunsch2014")        # an unverified lead
        V._cache["briefs.json"] = {**data, "source_ids": broken}
        try:
            names = {s["id"] for s in V.briefs(ledger)["mito-light-en"].sources}
        finally:
            V._cache["briefs.json"] = data
        self.assertNotIn("vanin2018", names)

    def test_sample_facts_do_not_claim_regulatory_status_falsely(self):
        for brief in V.briefs().values():
            text = " ".join(brief.facts).lower()
            self.assertTrue("not a medical device" in text or "není zdravotnickým prostředkem" in text)


class GameContentTests(unittest.TestCase):
    def test_bosses_are_well_formed(self):
        bosses = V.bosses()
        self.assertGreaterEqual(len(bosses), 6)
        self.assertEqual(len({b["id"] for b in bosses}), len(bosses))
        for b in bosses:
            self.assertIn(b["cohort"], V.cohorts)
            self.assertIn(b["lang"], ("cs", "en"))
            self.assertIn(b["tier"], (1, 2, 3))
            self.assertIn(b["percentile"], (60, 75, 90))
            for key in ("name", "brief_en", "brief_cs", "taunt_en", "taunt_cs"):
                self.assertTrue(b[key], (b["id"], key))

    def test_myths_are_well_formed(self):
        myths = V.myths()
        self.assertGreaterEqual(len(myths), 10)
        self.assertEqual(len({m["id"] for m in myths}), len(myths))
        for m in myths:
            self.assertIn(m["answer"], ("myth", "fact"))
            for key in ("en", "cs", "why_en", "why_cs", "ref"):
                self.assertTrue(m[key].strip(), (m["id"], key))
        self.assertGreaterEqual(sum(m["answer"] == "myth" for m in myths), 4)
        self.assertGreaterEqual(sum(m["answer"] == "fact" for m in myths), 2)

    def test_the_demo_corpus_is_claim_safe(self):
        """Every simulated hook the game shows is itself good practice for a non-medical device."""
        brands, items = generate_corpus(config=V.synth())
        self.assertEqual({b.cohort for b in brands} - set(V.cohorts), set())
        shield = TrustShield()
        brief = V.briefs()["mito-light-en"]
        for item in items:
            brief.lang = item.lang
            codes = {i.code for i in shield.check(item.title, brief)} & PROFILE_CODES
            self.assertEqual(codes, set(), item.title)

    def test_the_default_corpus_is_unchanged_by_the_vertical_option(self):
        brands, items = generate_corpus()
        self.assertEqual((len(brands), len(items)), (25, 1000))


class PackAndPlanTests(unittest.TestCase):
    def test_sample_packs_have_no_claim_errors_and_end_with_a_safety_note(self):
        for brief in V.briefs().values():
            pack = build_pack(brief, V.demo_formats(), ledger=V.ledger(), improve_rounds=0)
            self.assertEqual(pack.summary["claims_profile"], "wellness")
            for item in pack.items:
                found = {i["code"] for i in item.issues}
                self.assertEqual(found & (PROFILE_CODES - {"SAFETY_NOTE_MISSING"}), set(), (brief.lang, item.format, found))
                self.assertNotEqual(item.verdict, "blocked", (brief.lang, item.format))
                if item.format in ("seo_article", "geo_answer_page", "newsletter"):
                    self.assertIn("safety_note", item.parts, item.format)
                    self.assertNotIn("SAFETY_NOTE_MISSING", found)

    def test_hook_candidates_that_would_be_blocked_are_dropped(self):
        brief = V.briefs()["mito-light-cs"]
        brief.topic, brief.topic_forms = "bolest zad", {}
        pack = build_pack(brief, ["hook_set"], improve_rounds=0)
        shield = TrustShield()
        for hook in [pack.items[0].hook] + [a["text"] for a in pack.items[0].alt_hooks]:
            self.assertFalse([i for i in shield.check(hook, brief) if i.severity == "error"], hook)

    def test_plan_uses_the_vertical_wording_and_queries(self):
        brief = V.briefs()["mito-light-cs"]
        plan = build_plan(brief)
        names = {p["id"]: p["name_cs"] for p in plan.pillars}
        self.assertEqual(set(names), set(PILLARS))
        self.assertTrue(all("Vzdělávej" in n or "Dokaž" in n or "Příběh" in n or "Prodej" in n for n in names.values()))
        self.assertIn("Co je fotobiomodulace?", plan.geo["queries"])
        self.assertTrue(any("Profil tvrzení" in g for g in plan.guardrails_cs))
        self.assertTrue(plan.experiments and all(e["hypothesis_cs"] for e in plan.experiments))
        shield = TrustShield()
        for entry in plan.calendar:
            self.assertFalse([i for i in shield.check(entry["hook"], brief) if i.severity == "error"], entry["hook"])

    def test_a_generic_brief_still_gets_the_generic_plan(self):
        from dopamine_king.generate.types import Brief
        plan = build_plan(Brief(brand="Zorvia", topic="running shoes", audience="beginner runners"))
        self.assertEqual(plan.pillars[0]["name_en"], "Educate")


class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build_bundle(vertical="pbm")

    def test_bundle_carries_the_edition(self):
        b = self.bundle
        self.assertEqual(b["meta"]["vertical"], "pbm")
        self.assertTrue(b["meta"]["synthetic"])
        self.assertEqual(b["vertical"]["id"], "pbm")
        self.assertEqual(len(b["claims"]["topics"]), len(V.claims()["topics"]))
        self.assertEqual(set(b["claims"]["classes"]), {"wellness", "cosmetic", "medical", "avoid", "context"})
        self.assertTrue(b["claim_rules"]["disease_terms"]["cs"])
        self.assertEqual({t["id"] for t in b["claim_rules"]["topics"]}, {t["id"] for t in b["claims"]["topics"]})

    def test_the_game_content_is_the_vertical_s_own(self):
        b = self.bundle
        self.assertEqual({x["id"] for x in b["bosses"]}, {x["id"] for x in V.bosses()})
        ids = {m["id"] for m in b["myths"]}
        self.assertTrue({m["id"] for m in V.myths()} <= ids)
        self.assertIn("m-peeking", ids)
        self.assertTrue(all(d["cohort"] in V.cohorts for d in b["arena"]))
        self.assertGreaterEqual(len(b["arena"]), 100)

    def test_samples_are_the_brand_in_both_languages(self):
        b = self.bundle
        self.assertEqual(sorted(p["brief"]["lang"] for p in b["forge_samples"]), ["cs", "en"])
        self.assertEqual(sorted(p["brief"]["lang"] for p in b["guru_samples"]), ["cs", "en"])
        for pack in b["forge_samples"]:
            self.assertEqual(pack["brief"]["brand"], "MITO LIGHT")
            self.assertEqual(pack["summary"]["claims_profile"], "wellness")
            self.assertEqual(pack["summary"]["verdicts"]["blocked"], 0)

    def test_the_vault_holds_the_vertical_studies_and_the_general_ones(self):
        studies = {s["id"] for s in self.bundle["vault"]["studies"]}
        self.assertIn("doi:10.1007/s40279-022-01714-y", studies)
        self.assertIn("doi:10.1509/jmr.10.0353", studies)

    def test_the_generic_bundle_has_no_edition(self):
        b = build_bundle()
        self.assertNotIn("claims", b)
        self.assertIsNone(b["meta"]["vertical"])


class CommandLineTests(unittest.TestCase):
    def test_claims_map(self):
        code, out, _ = run_cli("evidence", "claims", "--vertical", "pbm")
        self.assertEqual(code, 0)
        self.assertIn("pbm-muscle-recovery", out)
        self.assertIn("verified studies only", out)
        with self.assertRaises(SystemExit):
            run_cli("evidence", "claims")

    def test_sources_list_uses_the_vertical_registry(self):
        code, out, _ = run_cli("sources", "list", "--vertical", "pbm", "--cohort", "pbm-cz-sk")
        self.assertEqual(code, 0)
        self.assertIn("mitolight.cz", out)

    def test_forge_sample_applies_the_wellness_profile(self):
        code, out, err = run_cli("forge", "--vertical", "pbm", "--sample", "mito-light-en", "--formats", "hook_set,newsletter",
                                 "--writer", "offline", "--json")
        self.assertEqual(code, 0, err)
        pack = json.loads(out)
        self.assertEqual(pack["brief"]["claims_profile"], "wellness")
        self.assertIn("safety_note", next(i for i in pack["items"] if i["format"] == "newsletter")["parts"])

    def test_vertical_flag_switches_a_plain_brief_to_the_profile(self):
        code, out, _ = run_cli("forge", "--brand", "X", "--topic", "red light panels", "--audience", "athletes", "--vertical", "pbm",
                               "--formats", "hook_set", "--writer", "offline", "--json")
        self.assertEqual(json.loads(out)["brief"]["claims_profile"], "wellness")

    def test_audit_flags_existing_copy_and_sets_the_exit_code(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "page.txt"
            bad.write_text("Červené světlo zmírňuje zánět a bolest zad. Zrychluje hojení jizev. Bez vedlejších účinků.", "utf-8")
            good = Path(tmp) / "ok.txt"
            good.write_text("Mnoho lidí zařazuje sezení pod červeným světlem do večerní rutiny. Před použitím si přečtěte návod výrobce.", "utf-8")
            code, out, _ = run_cli("audit", str(bad))
            self.assertEqual(code, 1)
            for needle in ("CLAIM_MEDICAL", "SAFETY_ABSOLUTE", "Zdravotní tvrzení"):
                self.assertIn(needle, out)
            code, out, _ = run_cli("audit", str(bad), "--json")
            rows = json.loads(out)
            self.assertEqual((code, rows[0]["lang"]), (1, "cs"))
            self.assertGreaterEqual(rows[0]["errors"], 3)
            code, out, _ = run_cli("audit", str(good))
            self.assertEqual(code, 0)
            self.assertIn("0 errors", out)
            with self.assertRaises(SystemExit):
                run_cli("audit", str(Path(tmp) / "missing.txt"))

    def test_audit_accepts_brand_facts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "p.txt"
            page.write_text("The panel is certified to the ETL electrical safety standard.", "utf-8")
            code, out, _ = run_cli("audit", str(page), "--lang", "en")
            code_with, out_with, _ = run_cli("audit", str(page), "--lang", "en", "--fact", "The panel is certified to the ETL electrical safety standard.")
            self.assertNotIn("STATUS_CLAIM", out_with)

    def test_bad_input_is_a_plain_error(self):
        for argv in (["forge", "--sample", "x"], ["forge", "--vertical", "nope", "--brand", "a", "--topic", "b", "--audience", "c"],
                     ["forge", "--vertical", "pbm", "--sample", "missing"]):
            with self.assertRaises(SystemExit):
                run_cli(*argv)


class WriterPromptTests(unittest.TestCase):
    def test_the_prompt_carries_the_rules_and_the_claim_map(self):
        from dopamine_king.generate.providers import brief_block
        text = brief_block(V.briefs()["mito-light-en"])
        self.assertIn("Regulatory profile: wellness", text)
        self.assertIn("Never write about:", text)
        self.assertIn("Hair growth", text)
        self.assertIn("Only with hedged wording and a cited source:", text)
        self.assertIn("evidence:", text)
        from dopamine_king.generate.types import Brief
        self.assertNotIn("Regulatory profile", brief_block(Brief(brand="B", topic="t", audience="a")))


if __name__ == "__main__":
    unittest.main()
