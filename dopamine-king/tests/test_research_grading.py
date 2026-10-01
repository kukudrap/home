import copy
import unittest

from dopamine_king.research.grading import (
    DESIGN_SCORES, MAX_CITATION_BONUS, apply_grade, classify_design, grade_study,
)
from tests.test_research_common import make_study

TODAY = 2025


def score_of(**kw) -> float:
    return grade_study(make_study(**kw), today_year=TODAY)[1]


class ClassifyDesignTests(unittest.TestCase):
    def test_meta_analysis_variants(self):
        for title in ("A meta-analysis of gamification", "Meta analysis of nudges", "A meta-analytic review of rewards"):
            self.assertEqual(classify_design(title), "meta-analysis", title)

    def test_systematic_review_and_scoping_review(self):
        self.assertEqual(classify_design("A systematic review of headline testing"), "systematic-review")
        self.assertEqual(classify_design("A scoping review of AI search"), "systematic-review")
        self.assertEqual(classify_design("Systematic literature review: gamification"), "systematic-review")

    def test_plain_literature_review_is_not_upgraded(self):
        self.assertEqual(classify_design("A literature review of gamification"), "unknown")

    def test_randomised_trial_and_field_experiment(self):
        self.assertEqual(classify_design("A randomized controlled trial of email nudges"), "rct")
        self.assertEqual(classify_design("A randomised controlled trial of email nudges"), "rct")
        self.assertEqual(classify_design("A field experiment on subject lines"), "field-experiment")
        self.assertEqual(classify_design("A natural experiment in news feeds"), "field-experiment")

    def test_ab_test_needs_a_claim_in_the_abstract(self):
        self.assertEqual(classify_design("Subject lines", "We ran an A/B test with 40,000 recipients."), "field-experiment")
        # a methods paper about A/B testing is not itself a field experiment
        self.assertEqual(
            classify_design(
                "Peeking at A/B tests: why it matters",
                "A/B testing is ubiquitous. In this work we describe a new approach to A/B testing.",
            ),
            "unknown",
        )

    def test_we_conducted_n_experiments_is_a_lab_experiment(self):
        self.assertEqual(classify_design("Persuasion", "We conducted three experiments with consumers."), "lab-experiment")
        self.assertEqual(classify_design("Persuasion", "Participants were randomly assigned to conditions."), "lab-experiment")

    def test_survey_case_study_and_theory(self):
        self.assertEqual(classify_design("A survey of newsroom editors"), "survey")
        self.assertEqual(classify_design("A case study of a B2B newsroom"), "qualitative")
        self.assertEqual(classify_design("Prospect theory: an analysis of decision under risk"), "theory")
        self.assertEqual(classify_design("A conceptual framework for engagement"), "theory")

    def test_observational_keywords(self):
        self.assertEqual(classify_design("Sharing on social media: a cross-sectional analysis"), "observational")

    def test_preprint_server_and_record_types(self):
        self.assertEqual(classify_design("Anything at all", venue="arXiv"), "preprint")
        self.assertEqual(classify_design("Anything", work_type="posted-content"), "preprint")
        self.assertEqual(classify_design("Anything", work_type="book"), "book")

    def test_unknown_when_unsure(self):
        self.assertEqual(classify_design("Insights about content"), "unknown")
        self.assertEqual(classify_design("", None, None), "unknown")

    def test_mentioning_earlier_meta_analyses_does_not_claim_the_design(self):
        self.assertEqual(
            classify_design("Gamification in classrooms", "Unlike previous meta-analyses, we study ten classrooms."),
            "unknown",
        )
        self.assertEqual(
            classify_design("Gamification in classrooms", "In this paper we conducted a meta-analysis of 38 studies."),
            "meta-analysis",
        )

    def test_authors_must_claim_the_design_for_their_own_paper(self):
        claims = {
            "rct": ["Our randomized controlled trial of reminders shows large effects.",
                    "We conducted a large-scale randomized controlled trial with 5,000 users."],
            "field-experiment": ["We ran several large online A/B tests on subject lines."],
            "lab-experiment": ["In three experiments, participants read headlines.", "We report two experiments on consumer judgement."],
            "meta-analysis": ["This meta-analysis synthesizes 38 studies."],
            "systematic-review": ["We performed a systematic review of 40 studies."],
            "qualitative": ["We interviewed 12 editors."],
        }
        for design, abstracts in claims.items():
            for text in abstracts:
                self.assertEqual(classify_design("Untitled", text), design, text)

    def test_reviewing_or_discussing_a_design_is_not_claiming_it(self):
        for text in (
            "We review field experiments in marketing.",
            "This paper reviews 40 randomized controlled trials of nudges.",
            "We conducted a study on A/B testing practices.",
            "This paper reviews 12 meta-analyses of gamification.",
            "We build on prior randomized controlled trials to propose a framework.",
        ):
            self.assertNotIn(
                classify_design("Untitled", text), ("rct", "field-experiment", "lab-experiment", "meta-analysis"), text)

    def test_a_review_title_does_not_become_an_experiment(self):
        self.assertEqual(classify_design("Field experiments in marketing: a review"), "unknown")
        self.assertEqual(classify_design("A literature survey of randomized controlled trials"), "survey")

    def test_strongest_design_wins_when_several_keywords_appear(self):
        self.assertEqual(classify_design("A meta-analysis and survey of framework use"), "meta-analysis")


class GradeHierarchyTests(unittest.TestCase):
    def test_base_scores_follow_the_brief(self):
        expected = {
            "meta-analysis": 1.0, "systematic-review": 1.0, "rct": 0.85, "field-experiment": 0.85,
            "lab-experiment": 0.7, "observational": 0.55, "survey": 0.5, "theory": 0.4, "qualitative": 0.35,
            "preprint": 0.4, "book": 0.3, "guideline": 0.3, "unknown": 0.25,
        }
        self.assertEqual(DESIGN_SCORES, expected)
        for design, value in expected.items():
            self.assertAlmostEqual(score_of(design=design, peer=None), value, msg=design)

    def test_design_dominates_citations(self):
        cited_observational = score_of(design="observational", peer=True, cited=500_000, year=2000)
        uncited_meta = score_of(design="meta-analysis", peer=None, cited=None)
        self.assertLess(cited_observational, uncited_meta)

    def test_letter_thresholds(self):
        cases = [
            ("meta-analysis", True, "A"), ("rct", True, "A"), ("rct", None, "A"),
            ("lab-experiment", True, "B"), ("observational", True, "B"),   # exactly 0.6
            ("observational", None, "C"), ("survey", True, "C"), ("theory", None, "C"),  # exactly 0.4
            ("qualitative", True, "C"),                                    # 0.35 + 0.05 = exactly 0.4
            ("qualitative", None, "D"), ("book", None, "D"), ("unknown", True, "D"),
        ]
        for design, peer, letter in cases:
            got = grade_study(make_study(design=design, peer=peer), today_year=TODAY)[0]
            self.assertEqual(got, letter, f"{design} peer={peer}")

    def test_unknown_design_string_is_treated_as_unknown(self):
        self.assertAlmostEqual(score_of(design="made-up", peer=None), 0.25)


class CitationBonusTests(unittest.TestCase):
    def test_full_bonus_at_one_hundred_citations_per_year(self):
        # published 2020, graded in 2025 -> 6 years, 600 citations -> 100 per year
        self.assertAlmostEqual(score_of(design="observational", peer=None, year=2020, cited=600), 0.65)

    def test_bonus_is_capped(self):
        low = score_of(design="observational", peer=None, year=2020, cited=600)
        huge = score_of(design="observational", peer=None, year=2020, cited=10**9)
        self.assertAlmostEqual(huge - 0.55, MAX_CITATION_BONUS)
        self.assertAlmostEqual(low, huge)

    def test_log_scaled_and_monotonic(self):
        scores = [score_of(design="observational", peer=None, year=2020, cited=c) for c in (0, 6, 60, 600)]
        self.assertEqual(scores, sorted(scores))
        self.assertAlmostEqual(scores[0], 0.55)
        # one citation per year earns only a sliver
        self.assertAlmostEqual(scores[1] - 0.55, 0.015, places=3)

    def test_missing_data_means_no_bonus_and_says_so(self):
        letter, score, reasons = grade_study(make_study(design="observational", peer=None, cited=None), today_year=TODAY)
        self.assertAlmostEqual(score, 0.55)
        self.assertTrue(any("no citation data" in r for r in reasons))
        self.assertAlmostEqual(score_of(design="observational", peer=None, year=None, cited=999), 0.55)

    def test_future_year_and_negative_counts_are_safe(self):
        self.assertGreaterEqual(score_of(design="observational", peer=None, year=2030, cited=50), 0.55)
        self.assertAlmostEqual(score_of(design="observational", peer=None, year=2020, cited=-5), 0.55)


class PeerReviewAndRetractionTests(unittest.TestCase):
    def test_peer_review_adds_five_hundredths(self):
        self.assertAlmostEqual(score_of(design="observational", peer=True) - score_of(design="observational", peer=None), 0.05)

    def test_explicitly_not_peer_reviewed_gets_no_bonus_and_a_reason(self):
        _, score, reasons = grade_study(make_study(design="observational", peer=False), today_year=TODAY)
        self.assertAlmostEqual(score, 0.55)
        self.assertTrue(any("not peer reviewed" in r for r in reasons))

    def test_unreviewed_work_is_capped_at_letter_b(self):
        for design in ("meta-analysis", "field-experiment"):
            letter, score, reasons = grade_study(
                make_study(design=design, peer=False, year=2020, cited=100_000), today_year=TODAY)
            self.assertEqual(letter, "B", design)
            self.assertLess(score, 0.8)
            self.assertTrue(any("capped" in r for r in reasons))

    def test_unknown_review_status_is_not_capped(self):
        self.assertEqual(grade_study(make_study(design="meta-analysis", peer=None), today_year=TODAY)[0], "A")

    def test_preprint_design_never_reaches_a(self):
        letter, score, _ = grade_study(make_study(design="preprint", peer=False, year=2024, cited=100_000), today_year=TODAY)
        self.assertIn(letter, ("B", "C"))
        self.assertLess(score, 0.8)

    def test_retraction_forces_d_with_a_reason(self):
        study = make_study(design="meta-analysis", peer=True, cited=5000, retracted=True)
        letter, score, reasons = grade_study(study, today_year=TODAY)
        self.assertEqual((letter, score), ("D", 0.0))
        self.assertTrue(any("retracted" in r for r in reasons))


class DeterminismTests(unittest.TestCase):
    def test_same_input_same_output_and_no_mutation(self):
        study = make_study(design="lab-experiment", peer=True, year=2015, cited=321)
        before = copy.deepcopy(study.to_dict())
        results = {repr(grade_study(study, today_year=TODAY)) for _ in range(5)}
        self.assertEqual(len(results), 1)
        self.assertEqual(study.to_dict(), before)

    def test_reasons_are_plain_strings_starting_with_the_design(self):
        _, _, reasons = grade_study(make_study(design="rct"), today_year=TODAY)
        self.assertTrue(reasons and all(isinstance(r, str) and r for r in reasons))
        self.assertIn("rct", reasons[0])

    def test_apply_grade_fills_the_study_in_place(self):
        study = make_study(design="rct", peer=True)
        self.assertEqual((study.grade, study.grade_score), ("", 0.0))
        out = apply_grade(study, today_year=TODAY)
        self.assertIs(out, study)
        self.assertEqual((study.grade, study.grade_score), ("A", 0.9))

    def test_scores_are_rounded_to_three_places(self):
        score = score_of(design="observational", peer=True, year=2020, cited=7)
        self.assertEqual(score, round(score, 3))


if __name__ == "__main__":
    unittest.main()
