import json
import re
import unittest
from collections import Counter

from dopamine_king.research.grading import grade_study
from dopamine_king.research.ledger import SEED_PATH, Ledger
from dopamine_king.research.models import CONFIDENCES, DESIGNS, DIRECTIONS, DOI_RE
from dopamine_king.research.tactics import TACTICS

LONG_DASH = chr(0x2014)

# DOI -> design exactly as briefed (DOIs lower-cased, which is how ids are built)
BRIEF = {
    "10.1509/jmr.10.0353": "observational",
    "10.1037/0033-2909.116.1.75": "theory",
    "10.1126/science.275.5306.1593": "theory",
    "10.1016/s0165-0173(98)00019-8": "theory",
    "10.1038/nn.2726": "lab-experiment",
    "10.2307/1914185": "theory",
    "10.1109/hicss.2014.377": "systematic-review",
    "10.1007/s10648-019-09498-w": "meta-analysis",
    "10.1145/2181037.2181040": "theory",
    "10.1037/0033-2909.125.6.627": "meta-analysis",
    "10.1145/1541948.1541999": "theory",
    "10.1126/science.aap9559": "observational",
    "10.1073/pnas.1618923114": "observational",
    "10.1073/pnas.1320040111": "field-experiment",
    "10.1073/pnas.1710966114": "field-experiment",
    "10.1177/0022242919841034": "observational",
    "10.1145/3637528.3671900": "lab-experiment",
    "10.1145/3097983.3097992": "theory",
    "10.1017/9781108653985": "book",
    "10.1509/jmkr.48.5.869": "observational",
    "10.1177/1088868309341564": "theory",
}
# (tactic, study id, direction) links named in the brief
BRIEFED_LINKS = [
    ("dopamine-myth", "doi:10.1016/s0165-0173(98)00019-8", "supports"),
    ("dopamine-myth", "doi:10.1126/science.275.5306.1593", "context"),
    ("streaks-loss-aversion", "doi:10.2307/1914185", "supports"),
    ("streaks-loss-aversion", "doi:10.1037/0033-2909.125.6.627", "mixed"),
    ("gamification-points-badges", "doi:10.1109/hicss.2014.377", "supports"),
    ("gamification-points-badges", "doi:10.1007/s10648-019-09498-w", "supports"),
    ("gamification-points-badges", "doi:10.1037/0033-2909.125.6.627", "mixed"),
    ("geo-cite-sources", "doi:10.1145/3637528.3671900", "supports"),
    ("geo-statistics", "doi:10.1145/3637528.3671900", "supports"),
    ("geo-quotations", "doi:10.1145/3637528.3671900", "supports"),
    ("geo-keyword-stuffing", "doi:10.1145/3637528.3671900", "supports"),
    ("ab-testing-peeking", "doi:10.1145/3097983.3097992", "supports"),
    ("scaled-content-abuse", "seed:google-spam-policies", "supports"),
]
AUTHOR_FORMAT = re.compile(r"^[^,]+, [A-Z]\.(-[A-Z]\.)?( [A-Z]\.(-[A-Z]\.)?)*$")


class SeedLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = SEED_PATH.read_text("utf-8")
        cls.data = json.loads(cls.raw)
        cls.ledger = Ledger.load()
        cls.by_id = {s["id"]: s for s in cls.data["studies"]}

    # -- structure ------------------------------------------------------------------
    def test_envelope_and_size(self):
        self.assertEqual(self.data["version"], 1)
        self.assertGreaterEqual(len(self.data["studies"]), 27)
        self.assertGreater(len(self.data["links"]), 40)

    def test_study_ids_are_unique(self):
        ids = [s["id"] for s in self.data["studies"]]
        self.assertEqual([i for i, n in Counter(ids).items() if n > 1], [])

    def test_every_link_points_to_an_existing_study_and_tactic(self):
        for l in self.data["links"]:
            self.assertIn(l["study_id"], self.by_id, l)
            self.assertIn(l["tactic_id"], TACTICS, l)
            self.assertIn(l["direction"], DIRECTIONS, l)

    def test_one_link_per_tactic_and_study(self):
        pairs = [(l["tactic_id"], l["study_id"]) for l in self.data["links"]]
        self.assertEqual([p for p, n in Counter(pairs).items() if n > 1], [])

    def test_ledger_validates_cleanly(self):
        self.assertEqual(self.ledger.validate(), [])

    def test_no_long_dash_anywhere_in_the_json(self):
        self.assertNotIn(LONG_DASH, self.raw)

    def test_only_plain_punctuation_besides_czech_letters(self):
        odd = {c for c in self.raw if ord(c) > 127}
        self.assertTrue(odd <= set("áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"), "".join(sorted(odd)))

    # -- bibliographic fields ---------------------------------------------------------
    def test_every_doi_is_well_formed_and_ids_follow_the_rule(self):
        for s in self.data["studies"]:
            if s["doi"]:
                self.assertRegex(s["doi"], r"^10\.\d{4,9}/\S+$")
                self.assertTrue(DOI_RE.match(s["doi"]))
                self.assertEqual(s["id"], "doi:" + s["doi"].lower())
            else:
                self.assertTrue(s["id"].startswith("seed:"), s["id"])

    def test_briefed_dois_and_designs_are_present_as_given(self):
        for doi, design in BRIEF.items():
            study = self.by_id.get(f"doi:{doi}")
            self.assertIsNotNone(study, doi)
            self.assertEqual(study["design"], design, doi)

    def test_seed_records_state_how_they_were_verified_and_carry_no_invented_numbers(self):
        for s in self.data["studies"]:
            self.assertEqual(s["source"], "seed")
            if s["verified"]:
                self.assertIn("2026-10-01", s["verification_note"], s["id"])
            if s["verification_note"]:
                self.assertIn("2026-10-01", s["verification_note"], s["id"])
            self.assertFalse(s["retracted"])
            self.assertIsNone(s["cited_by"], s["id"])
            self.assertIsNone(s["abstract"], s["id"])
            self.assertIn(s["design"], DESIGNS)
            self.assertIn(s["confidence"], CONFIDENCES)

    def test_verified_records_have_a_doi_or_are_guideline_pages(self):
        for s in self.data["studies"]:
            if s["verified"]:
                self.assertTrue(s["doi"] or s["design"] == "guideline", s["id"])
        # the entries whose DOI was not displayed in the sources checked stay unverified
        for sid in ("doi:10.1037/0033-2909.116.1.75", "doi:10.1126/science.275.5306.1593", "doi:10.2307/1914185",
                    "doi:10.1037/0033-2909.125.6.627", "seed:oppenheimer-2006"):
            self.assertFalse(self.by_id[sid]["verified"], sid)

    def test_authors_use_surname_comma_initials(self):
        for s in self.data["studies"]:
            for a in s["authors"]:
                self.assertRegex(a, AUTHOR_FORMAT)

    def test_uncertain_fields_stay_null(self):
        gruber = self.by_id["doi:10.1016/j.neuron.2014.08.060"]       # DOI added after the web check
        self.assertEqual((gruber["confidence"], gruber["verified"]), ("high", True))
        self.assertEqual(self.by_id["doi:10.1177/1088868309341564"]["confidence"], "medium")
        for slug in ("ferster-skinner-1957", "eyal-2014", "cialdini-2021"):
            study = self.by_id[f"seed:{slug}"]
            self.assertEqual((study["doi"], study["design"]), (None, "book"))
        google = self.by_id["seed:google-spam-policies"]
        self.assertEqual((google["doi"], google["year"], google["design"], google["peer_reviewed"]), (None, None, "guideline", False))
        self.assertEqual(google["url"], "https://developers.google.com/search/docs/essentials/spam-policies")
        # anything without a confirmed DOI has no DOI and medium confidence
        extras = [s for s in self.data["studies"] if s["id"].startswith("seed:") and s["design"] not in ("book", "guideline")]
        self.assertTrue(extras)
        for s in extras:
            self.assertEqual((s["doi"], s["confidence"]), (None, "medium"), s["id"])

    def test_peer_review_flags(self):
        for doi in BRIEF:
            s = self.by_id[f"doi:{doi}"]
            if s["design"] == "book":
                self.assertIsNone(s["peer_reviewed"])
            else:
                self.assertTrue(s["peer_reviewed"], doi)
        self.assertFalse(self.by_id["seed:eyal-2014"]["peer_reviewed"])

    def test_stored_grades_match_a_fresh_grading(self):
        for study in self.ledger.studies:
            letter, score, _ = grade_study(study, today_year=2026)
            self.assertEqual((study.grade, study.grade_score), (letter, score), study.id)

    # -- links ------------------------------------------------------------------------
    def test_links_named_in_the_brief_exist_with_the_right_direction(self):
        have = {(l["tactic_id"], l["study_id"]): l["direction"] for l in self.data["links"]}
        for tactic, study_id, direction in BRIEFED_LINKS:
            self.assertEqual(have.get((tactic, study_id)), direction, (tactic, study_id))

    def test_notes_exist_in_both_languages(self):
        for l in self.data["links"]:
            self.assertTrue(l["note_en"].strip() and l["note_cs"].strip(), l)
            self.assertNotEqual(l["note_en"], l["note_cs"])
            self.assertEqual(bool(l["caveat_en"]), bool(l["caveat_cs"]), l)

    def test_caveats_are_present_where_the_brief_names_a_limitation(self):
        by_pair = {(l["tactic_id"], l["study_id"]): l for l in self.data["links"]}
        for tactic, study_id in [
            ("dopamine-myth", "doi:10.1016/s0165-0173(98)00019-8"),      # animal research
            ("variable-reward", "seed:ferster-skinner-1957"),             # animal research
            ("streaks-loss-aversion", "doi:10.2307/1914185"),             # theory, marketing effects vary
            ("geo-cite-sources", "doi:10.1145/3637528.3671900"),          # one benchmark
            ("prediction-error", "doi:10.1126/science.aap9559"),          # novelty can be abused
            ("emotional-arousal", "doi:10.1073/pnas.1320040111"),         # ethics controversy
            ("personalization", "doi:10.1073/pnas.1710966114"),           # privacy and ethics
            ("emotional-arousal", "doi:10.1509/jmr.10.0353"),             # observational, not causal
        ]:
            self.assertTrue(by_pair[(tactic, study_id)]["caveat_en"], (tactic, study_id))
        self.assertIn("animal", by_pair[("variable-reward", "seed:ferster-skinner-1957")]["caveat_en"].lower())
        self.assertIn("benchmark", by_pair[("geo-cite-sources", "doi:10.1145/3637528.3671900")]["caveat_en"])
        self.assertIn("ethically", by_pair[("emotional-arousal", "doi:10.1073/pnas.1320040111")]["caveat_en"])

    # -- summaries --------------------------------------------------------------------
    def test_every_tactic_has_a_complete_summary(self):
        for tid in TACTICS:
            s = self.ledger.summary(tid)
            self.assertIn(s.label, ("strong", "moderate", "limited", "contested", "none"), tid)
            self.assertTrue(s.headline_en and s.headline_cs, tid)
            self.assertEqual(len(s.caveats_en), len(s.caveats_cs), tid)
            self.assertEqual(sum(s.direction_counts.values()), len(self.ledger.evidence_for(tid)), tid)

    def test_tactics_without_an_honest_fit_have_no_links(self):
        for tid in ("numbers-specificity", "video-hook-first-seconds", "answer-first-structure"):
            self.assertEqual(self.ledger.summary(tid).label, "none", tid)
            self.assertEqual(self.ledger.evidence_for(tid), [], tid)

    def test_labels_follow_the_rules_for_known_cases(self):
        expected = {
            "geo-statistics": "moderate",             # one B study from a single benchmark
            "ab-testing-peeking": "limited",          # a statistical result, graded as theory
            "scaled-content-abuse": "limited",        # a guideline, graded D
            "variable-reward": "limited",             # animal work and a practitioner book
            "streaks-loss-aversion": "limited",
            "gamification-points-badges": "strong",   # two A rated reviews, one mixed A study
            "dopamine-myth": "moderate",
        }
        for tid, label in expected.items():
            self.assertEqual(self.ledger.summary(tid).label, label, tid)
        self.assertIn("mixed", self.ledger.summary("gamification-points-badges").headline_en.lower())

    def test_no_seed_tactic_is_contested_or_overclaimed_by_weak_evidence(self):
        for tid in TACTICS:
            s = self.ledger.summary(tid)
            if s.label in ("strong", "moderate"):
                supporters = [st for st, l in self.ledger.evidence_for(tid) if l.direction == "supports"]
                self.assertTrue(any(st.grade in ("A", "B") for st in supporters) or len(supporters) >= 2, tid)

    # -- search and stats -------------------------------------------------------------
    def test_search_text_finds_seed_studies_in_both_languages(self):
        self.assertEqual([s.title for s in self.ledger.search_text("prospect theory")][:1],
                         ["Prospect Theory: An Analysis of Decision under Risk"])
        czech = {s.id for s in self.ledger.search_text("zvedavost")}
        self.assertIn("doi:10.1037/0033-2909.116.1.75", czech)       # Loewenstein, found through a Czech note
        self.assertIn("doi:10.1016/j.neuron.2014.08.060", czech)
        self.assertTrue(self.ledger.search_text("kramer"))

    def test_stats(self):
        stats = self.ledger.stats()
        self.assertEqual(stats["studies"], len(self.data["studies"]))
        self.assertEqual((stats["verified"], stats["by_source"]),
                         (sum(1 for x in self.data["studies"] if x["verified"]), {"seed": stats["studies"]}))
        self.assertEqual(sum(stats["by_grade"].values()), stats["studies"])
        self.assertEqual(set(stats["by_design"]) - set(DESIGNS), set())


if __name__ == "__main__":
    unittest.main()
