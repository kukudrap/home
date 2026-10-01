import json
import tempfile
import unittest
from pathlib import Path

from dopamine_king.research.ledger import SEED_PATH, EvidenceSummary, Ledger
from dopamine_king.research.models import EvidenceLink
from tests.test_research_common import make_study


def meta(title="Meta A"):          # grade A
    return make_study(title, design="meta-analysis", peer=True, year=2019, authors=["Roe, R.", "Poe, P."])


def obs(title="Observational B"):  # grade B
    return make_study(title, design="observational", peer=True, year=2018)


def theory(title="Theory C"):      # grade C
    return make_study(title, design="theory", peer=True, year=2017)


def book(title="Book D"):          # grade D
    return make_study(title, design="book", peer=None, year=2016)


def link(tactic, study, direction="supports", **kw):
    return EvidenceLink(tactic, study.id, direction, "Note.", "Poznámka.", **kw)


def ledger_with(*pairs):
    """pairs of (study, direction) all linked to tactic "t"."""
    studies = [s for s, _ in pairs]
    return Ledger(studies, [link("t", s, d) for s, d in pairs])


class SummaryLabelTests(unittest.TestCase):
    def test_no_links_means_none(self):
        s = Ledger().summary("t")
        self.assertIsInstance(s, EvidenceSummary)
        self.assertEqual((s.label, s.grade, s.n_studies), ("none", "", 0))
        self.assertEqual(s.direction_counts, {"supports": 0, "mixed": 0, "contradicts": 0, "context": 0})
        self.assertTrue(s.headline_en and s.headline_cs)
        self.assertEqual((s.caveats_en, s.caveats_cs), ([], []))

    def test_two_good_supporters_and_no_good_contradiction_is_strong(self):
        s = ledger_with((meta(), "supports"), (obs(), "supports")).summary("t")
        self.assertEqual((s.label, s.grade, s.n_studies), ("strong", "A", 2))
        self.assertEqual(s.direction_counts["supports"], 2)

    def test_a_weak_contradiction_does_not_block_strong(self):
        s = ledger_with((meta(), "supports"), (obs(), "supports"), (theory(), "contradicts")).summary("t")
        self.assertEqual(s.label, "strong")

    def test_good_supporter_and_good_contradiction_is_contested(self):
        s = ledger_with((meta(), "supports"), (obs(), "contradicts")).summary("t")
        self.assertEqual(s.label, "contested")
        self.assertIn("1 supporting", s.headline_en)

    def test_one_good_supporter_is_moderate(self):
        self.assertEqual(ledger_with((obs(), "supports")).summary("t").label, "moderate")

    def test_two_c_supporters_are_moderate_but_one_is_limited(self):
        self.assertEqual(ledger_with((theory("T1"), "supports"), (theory("T2"), "supports")).summary("t").label, "moderate")
        self.assertEqual(ledger_with((theory(), "supports")).summary("t").label, "limited")

    def test_weak_or_odd_evidence_is_limited(self):
        self.assertEqual(ledger_with((book(), "supports")).summary("t").label, "limited")
        self.assertEqual(ledger_with((meta(), "mixed")).summary("t").label, "limited")
        self.assertEqual(ledger_with((obs(), "contradicts")).summary("t").label, "limited")

    def test_context_only_links_are_limited_and_say_so(self):
        s = ledger_with((meta(), "context")).summary("t")
        self.assertEqual(s.label, "limited")
        self.assertIn("background", s.headline_en)
        self.assertEqual(s.grade, "A")               # best letter, taken from the only study linked

    def test_limited_headlines_name_the_actual_situation(self):
        mixed = ledger_with((meta(), "mixed"), (theory(), "supports")).summary("t")
        self.assertIn("mixed results", mixed.headline_en)
        self.assertIn("smíšené", mixed.headline_cs)
        contradicted = ledger_with((obs(), "contradicts")).summary("t")
        self.assertIn("contradict", contradicted.headline_en)
        weak = ledger_with((book(), "supports"), (meta(), "context")).summary("t")
        self.assertIn("1 study bears directly", weak.headline_en)     # the context study is not counted
        self.assertEqual(weak.n_studies, 2)

    def test_best_grade_ignores_context_when_direct_evidence_exists(self):
        s = ledger_with((meta(), "context"), (theory(), "supports")).summary("t")
        self.assertEqual(s.grade, "C")

    def test_contradiction_by_good_study_beats_two_weak_supporters(self):
        s = ledger_with((theory("T1"), "supports"), (theory("T2"), "supports"), (obs(), "contradicts")).summary("t")
        self.assertEqual(s.label, "limited")

    def test_mixed_good_evidence_is_flagged_in_the_headline_of_a_strong_tactic(self):
        s = ledger_with((meta("M1"), "supports"), (meta("M2"), "supports"), (obs(), "mixed")).summary("t")
        self.assertEqual(s.label, "strong")
        self.assertIn("mixed", s.headline_en.lower())
        self.assertIn("smíšen", s.headline_cs.lower())

    def test_retracted_studies_do_not_count_and_add_a_caveat(self):
        bad = meta("Retracted meta")
        bad.retracted = True
        ledger = Ledger([bad, obs()], [link("t", bad), link("t", obs())])
        ledger.regrade()
        s = ledger.summary("t")
        self.assertEqual(s.label, "moderate")        # only the observational study counts
        self.assertTrue(any("retracted" in c for c in s.caveats_en))
        self.assertTrue(any("stažena" in c for c in s.caveats_cs))

    def test_headlines_exist_in_both_languages_for_every_label(self):
        cases = [
            [], [(meta(), "supports"), (obs(), "supports")], [(meta(), "supports"), (obs(), "contradicts")],
            [(obs(), "supports")], [(theory(), "supports")], [(meta(), "context")],
        ]
        for pairs in cases:
            s = ledger_with(*pairs).summary("t")
            self.assertTrue(s.headline_en.strip() and s.headline_cs.strip(), s.label)
            self.assertNotEqual(s.headline_en, s.headline_cs)

    def test_caveats_are_prefixed_with_a_short_citation_and_stay_parallel(self):
        a, b = meta(), obs("Another Study")
        ledger = Ledger([a, b], [
            link("t", a, caveat_en="Small sample.", caveat_cs="Malý vzorek."),
            link("t", b, caveat_en="Observational.", caveat_cs="Pozorovací."),
        ])
        s = ledger.summary("t")
        self.assertEqual(s.caveats_en, ["Roe & Poe 2019: Small sample.", "Doe 2018: Observational."])
        self.assertEqual(s.caveats_cs, ["Roe & Poe 2019: Malý vzorek.", "Doe 2018: Pozorovací."])

    def test_summary_is_serialisable(self):
        s = ledger_with((obs(), "supports")).summary("t")
        self.assertEqual(EvidenceSummary.from_dict(s.to_dict()), s)


class EvidenceForTests(unittest.TestCase):
    def test_sorted_by_grade_score_descending(self):
        studies = [book(), theory(), meta(), obs()]
        ledger = Ledger(studies, [link("t", s) for s in studies])
        self.assertEqual([s.grade for s, _ in ledger.evidence_for("t")], ["A", "B", "C", "D"])

    def test_ties_break_by_direction_then_year(self):
        a, b = obs("Older"), obs("Newer")
        b.year = 2022
        ledger = Ledger([a, b], [link("t", a, "context"), link("t", b, "supports")])
        self.assertEqual([s.title for s, _ in ledger.evidence_for("t")], ["Newer", "Older"])

    def test_other_tactics_and_dangling_links_are_ignored(self):
        s = obs()
        ledger = Ledger([s], [link("t", s), link("other", s), EvidenceLink("t", "doi:10.5555/gone", "supports", "n", "n")])
        self.assertEqual(len(ledger.evidence_for("t")), 1)
        self.assertEqual(ledger.summary("t").n_studies, 1)
        self.assertEqual(ledger.evidence_for("unknown"), [])

    def test_returns_the_link_belonging_to_each_study(self):
        s = obs()
        ledger = Ledger([s], [link("t", s, caveat_en="care")])
        (study, found), = ledger.evidence_for("t")
        self.assertIs(study, s)
        self.assertEqual(found.caveat_en, "care")


class MutationTests(unittest.TestCase):
    def test_add_study_grades_ungraded_studies_and_replaces_same_id(self):
        ledger = Ledger()
        s = obs()
        self.assertEqual(s.grade, "")
        ledger.add_study(s)
        self.assertEqual(s.grade, "B")
        updated = make_study("Observational B", design="meta-analysis", peer=True, year=2018)
        ledger.add_study(updated)
        self.assertEqual(len(ledger.studies), 1)
        self.assertEqual(ledger.get_study(s.id).design, "meta-analysis")
        self.assertIsNone(ledger.get_study("seed:nope"))

    def test_link_replaces_same_pair_and_rejects_bad_direction(self):
        s = obs()
        ledger = Ledger([s])
        ledger.link(link("t", s, "supports"))
        ledger.link(link("t", s, "mixed"))
        self.assertEqual([l.direction for l in ledger.links], ["mixed"])
        with self.assertRaises(ValueError):
            ledger.link(link("t", s, "sideways"))

    def test_regrade_refreshes_grades_after_a_change(self):
        s = obs()
        ledger = Ledger([s])
        s.retracted = True
        ledger.regrade(today_year=2025)
        self.assertEqual(s.grade, "D")


class SearchTextTests(unittest.TestCase):
    def setUp(self):
        self.curiosity = make_study("Curiosity and Memory", design="lab-experiment", peer=True, authors=["Novák, J.", "Dvořák, P."],
                                    abstract="Participants learned more when curious.")
        self.fluency = make_study("Fluency in Reading", design="theory", peer=True, authors=["Smith, A."])
        self.ledger = Ledger([self.fluency, self.curiosity], [
            EvidenceLink("curiosity-gap", self.curiosity.id, "supports", "Curiosity improves memory.", "Zvědavost zlepšuje paměť."),
            EvidenceLink("cognitive-fluency", self.fluency.id, "supports", "Easy text is liked.", "Snadný text se líbí."),
        ])

    def titles(self, text):
        return [s.title for s in self.ledger.search_text(text)]

    def test_matches_title_case_insensitively(self):
        self.assertEqual(self.titles("CURIOSITY"), ["Curiosity and Memory"])

    def test_matches_authors_ignoring_diacritics(self):
        self.assertEqual(self.titles("novak"), ["Curiosity and Memory"])
        self.assertEqual(self.titles("Dvořák"), ["Curiosity and Memory"])
        self.assertEqual(self.titles("dvorak"), ["Curiosity and Memory"])

    def test_matches_czech_notes_with_or_without_diacritics(self):
        self.assertEqual(self.titles("zvědavost"), ["Curiosity and Memory"])
        self.assertEqual(self.titles("ZVEDAVOST pamet"), ["Curiosity and Memory"])
        self.assertEqual(self.titles("snadny"), ["Fluency in Reading"])

    def test_matches_abstract_and_requires_every_word(self):
        self.assertEqual(self.titles("participants curious"), ["Curiosity and Memory"])
        self.assertEqual(self.titles("curiosity banana"), [])

    def test_blank_query_finds_nothing_and_results_are_best_grade_first(self):
        self.assertEqual(self.ledger.search_text("   "), [])
        both = self.ledger.search_text("e")        # letter present in both titles
        self.assertEqual([s.grade for s in both], sorted(s.grade for s in both))


class PersistenceTests(unittest.TestCase):
    def test_save_load_round_trip_keeps_everything_and_czech_text(self):
        s = obs()
        s.verified = True
        s.verification_note = "ok"
        ledger = Ledger([s, theory()], [link("t", s, caveat_en="c", caveat_cs="Čeština")])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "dir" / "ledger.json"
            ledger.save(path)
            raw = path.read_text("utf-8")
            self.assertIn("Poznámka.", raw)                    # written as UTF-8, not escaped
            self.assertNotIn("\\u", raw)
            self.assertTrue(raw.endswith("\n"))
            self.assertEqual(sorted(p.name for p in path.parent.iterdir()), ["ledger.json"])
            again = Ledger.load(str(path))
        self.assertEqual(again.to_dict(), ledger.to_dict())
        self.assertEqual(json.loads(raw)["version"], 1)
        self.assertTrue(again.get_study(s.id).verified)

    def test_load_rejects_newer_versions_and_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            newer = Path(tmp) / "newer.json"
            newer.write_text(json.dumps({"version": 99, "studies": [], "links": []}), "utf-8")
            with self.assertRaises(ValueError):
                Ledger.load(newer)
            s = obs().to_dict()
            dupes = Path(tmp) / "dupes.json"
            dupes.write_text(json.dumps({"version": 1, "studies": [s, s], "links": []}), "utf-8")
            with self.assertRaises(ValueError):
                Ledger.load(dupes)

    def test_load_tolerates_missing_sections_and_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "min.json"
            path.write_text(json.dumps({"studies": [{**obs().to_dict(), "new_field": 1}]}), "utf-8")
            ledger = Ledger.load(path)
        self.assertEqual((len(ledger.studies), len(ledger.links)), (1, 0))

    def test_default_load_reads_the_packaged_seed(self):
        self.assertTrue(SEED_PATH.exists())
        self.assertEqual(Ledger.load().to_dict(), Ledger.load(SEED_PATH).to_dict())


class StatsAndValidationTests(unittest.TestCase):
    def test_stats_count_by_design_grade_source_and_verification(self):
        a, b, c = meta(), obs(), book()
        b.verified = True
        c.source = "openalex"
        c.retracted = True
        ledger = Ledger([a, b, c], [link("t1", a), link("t2", b)])
        stats = ledger.stats()
        self.assertEqual((stats["studies"], stats["links"], stats["tactics_linked"]), (3, 2, 2))
        self.assertEqual(stats["by_design"], {"book": 1, "meta-analysis": 1, "observational": 1})
        self.assertEqual(stats["by_grade"], {"A": 1, "B": 1, "D": 1})
        self.assertEqual(stats["by_source"], {"openalex": 1, "seed": 2})
        self.assertEqual((stats["verified"], stats["unverified"], stats["retracted"]), (1, 2, 1))

    def test_validate_reports_structural_problems(self):
        s = obs()
        s.design = "bogus"
        s.doi = "not-a-doi"
        ledger = Ledger([s], [EvidenceLink("no-such-tactic", "seed:missing", "supports", "", "")])
        problems = " | ".join(ledger.validate())
        for expected in ("unknown design", "malformed doi", "unknown study", "unknown tactic", "note missing"):
            self.assertIn(expected, problems)

    def test_validate_flags_the_long_dash(self):
        s = obs(f"A title {chr(0x2014)} with a long dash")
        self.assertTrue(any("long dash" in p for p in Ledger([s]).validate()))

    def test_a_clean_ledger_validates(self):
        s = obs()
        self.assertEqual(Ledger([s], [link("curiosity-gap", s)]).validate(), [])


if __name__ == "__main__":
    unittest.main()
