import unittest

from dopamine_king.scoring import (
    SPEC_PATH, FEATURE_NAMES, LEX_CATEGORIES, detect_lang, feature_vector, find_matches, fold, load_spec,
    normalize, rank_hooks, score_hook, tokenize,
)


def total(text, **kw):
    return score_hook(text, **kw).total


class TokenizerTests(unittest.TestCase):
    def test_numbers_apostrophes_and_unicode(self):
        norms = [t.norm for t in tokenize("1,000 users, 3.5 h: you’re Zoo_Tycoon Český")]
        self.assertEqual(norms[:4], ["1,000", "users", "3.5", "h"])
        self.assertIn("you're", norms)
        self.assertIn("český", norms)

    def test_spans_point_into_text(self):
        text = "Why most dashboards lie to you"
        res = score_hook(text)
        for span in res.spans:
            self.assertEqual(text[span.start:span.end], span.text)
        cats = {s.category for s in res.spans}
        self.assertTrue({"curiosity", "contrast", "second_person"} <= cats)


class MatcherTests(unittest.TestCase):
    def test_longest_match_non_overlapping_and_wildcards(self):
        compiled = [(("how",), (False,)), (("how", "to"), (False, False)), (("tajn",), (True,))]
        norms = ["how", "to", "x", "how", "tajne", "tajn"]
        self.assertEqual(find_matches(norms, compiled), [(0, 2), (3, 4), (4, 5), (5, 6)])

    def test_fold_and_czech_without_diacritics(self):
        self.assertEqual(fold("špatně žluťoučký"), "spatne zlutoucky")
        with_marks = score_hook("7 chyb, které dělá každý začátečník (a jak se jim vyhnout)")
        without = score_hook("7 chyb, ktere dela kazdy zacatecnik (a jak se jim vyhnout)")
        self.assertEqual(with_marks.lang, "cs")
        self.assertEqual(without.lang, "cs")
        self.assertGreater(without.total, 30)


class LanguageTests(unittest.TestCase):
    def test_detection(self):
        self.assertEqual(detect_lang("Why your CRM is costing you deals"), "en")
        self.assertEqual(detect_lang("Proč váš web nepřináší zákazníky"), "cs")
        self.assertEqual(detect_lang("Jak zacit s marketingem"), "cs")
        self.assertEqual(detect_lang(""), "en")


class ScoreShapeTests(unittest.TestCase):
    def test_result_is_bounded_and_complete(self):
        for text in ["", "Win", "7 mistakes every beginner makes", "A" * 500, "!!!!!!", "1 2 3 4 5 6 7 8 9"]:
            r = score_hook(text)
            self.assertGreaterEqual(r.total, 0.0)
            self.assertLessEqual(r.total, 100.0)
            self.assertTrue(0.0 <= r.clickbait_risk <= 1.0)
            self.assertEqual(set(r.parts), {"curiosity", "surprise", "emotion", "relevance", "utility", "fluency"})
            self.assertEqual(len(feature_vector(r)), len(FEATURE_NAMES))
            for v in r.parts.values():
                self.assertTrue(0.0 <= v <= 100.0)

    def test_to_dict_rounding_and_full_precision(self):
        r = score_hook("Why most dashboards lie to you")
        d = r.to_dict()
        self.assertEqual(d["total"], round(r.total, 2))
        self.assertEqual(r.to_dict(ndigits=None)["total"], r.total)

    def test_spec_integrity(self):
        spec = load_spec()
        for lang in ("en", "cs"):
            block = spec["langs"][lang]
            self.assertEqual(set(block["lexicons"]), set(LEX_CATEGORIES))
            for cat, entries in block["lexicons"].items():
                self.assertGreater(len(entries), 8, (lang, cat))
                self.assertEqual(len(entries), len(set(entries)), f"duplicate entries in {lang}/{cat}")
        self.assertAlmostEqual(sum(spec["params"]["weights"].values()), 1.0)
        self.assertNotIn(chr(0x2014), SPEC_PATH.read_text("utf-8"))


class OrderingTests(unittest.TestCase):
    """The model is a heuristic; these are the relations it must always respect."""

    def test_weak_corporate_vs_strong_hook(self):
        self.assertLess(total("Our Q3 company update"), 15)
        self.assertGreater(total("7 mistakes every beginner runner makes (and how to fix them)"), 55)

    def test_clickbait_is_penalised_below_honest_equivalent(self):
        honest = score_hook("Why most marketing dashboards lie to you")
        bait = score_hook("You won't BELIEVE this one trick!!!")
        self.assertGreater(bait.clickbait_risk, 0.7)
        self.assertLess(honest.clickbait_risk, 0.1)
        self.assertGreater(honest.total, bait.total + 25)
        self.assertEqual(bait.tips[0]["key"], "reduce_clickbait")

    def test_overclaim_raises_risk(self):
        self.assertGreater(score_hook("Guaranteed growth overnight, no risk").clickbait_risk, 0.5)
        self.assertGreater(score_hook("Zaručený růst přes noc bez rizika").clickbait_risk, 0.5)

    def test_numbers_questions_and_second_person_help(self):
        base = total("Marketing dashboards")
        self.assertGreater(total("7 marketing dashboards"), base)
        self.assertGreater(total("Why do marketing dashboards fail?"), base)
        self.assertGreater(total("Your marketing dashboards"), base)

    def test_too_long_is_less_fluent(self):
        short = score_hook("7 ways to cut churn")
        long = score_hook("7 ways to cut churn in a subscription business that sells to enterprise customers in highly regulated industries across Europe")
        self.assertGreater(short.parts["fluency"], long.parts["fluency"] + 15)
        self.assertIn("shorten", [t["key"] for t in long.tips])

    def test_years_are_not_listicle_numbers(self):
        self.assertEqual(score_hook("Best CRM tools 2026").features["starts_with_number"], 0.0)
        self.assertEqual(score_hook("2026 CRM tools").features["starts_with_number"], 0.0)
        self.assertEqual(score_hook("10 CRM tools").features["starts_with_number"], 1.0)

    def test_decimal_tokens_of_four_characters_do_not_crash(self):
        expected = {  # text: (has_number, starts_with_number)
            "Save 12.5 percent on shoes": (1.0, 0.0),
            "1.25 liters a day": (1.0, 1.0),
            "12,5 procenta ro\u010dn\u011b": (1.0, 1.0),
            "2026.5 forecast": (1.0, 1.0),      # a decimal is a number, never a year
            "1900.0 hours": (1.0, 1.0),
            "Best CRM tools 2026": (0.0, 0.0),  # a plain year is not a listicle number
        }
        for text, (has_number, starts) in expected.items():
            f = score_hook(text).features
            self.assertEqual((f["has_number"], f["starts_with_number"]), (has_number, starts), text)

    def test_promise_gap_flags_missing_list_items(self):
        body_ok = "\n".join(f"{i}. item {i}" for i in range(1, 8))
        body_short = "1. only one\n2. only two"
        ok = score_hook("7 ways to cut churn", body_ok)
        gap = score_hook("7 ways to cut churn", body_short)
        self.assertEqual(ok.features["promise_gap"], 0.0)
        self.assertGreater(gap.features["promise_gap"], 0.6)
        self.assertGreater(gap.clickbait_risk, ok.clickbait_risk)
        self.assertIn("keep_promise", [t["key"] for t in gap.tips])

    def test_custom_weights_change_the_ranking(self):
        text = "Why most dashboards lie to you"
        curiosity_only = score_hook(text, weights={"curiosity": 1, "surprise": 0, "emotion": 0, "relevance": 0, "utility": 0})
        utility_only = score_hook(text, weights={"curiosity": 0, "surprise": 0, "emotion": 0, "relevance": 0, "utility": 1})
        self.assertGreater(curiosity_only.total, utility_only.total)

    def test_ship_it_tip_for_strong_clean_hook(self):
        r = score_hook("7 mistakes every beginner runner makes (and how to fix them)")
        self.assertGreaterEqual(r.total, 55)
        self.assertTrue(r.tips == [] or r.tips[0]["key"] != "reduce_clickbait")

    def test_rank_hooks_orders_best_first(self):
        ranked = rank_hooks(["Our Q3 company update", "7 mistakes every beginner runner makes", "Win"])
        self.assertEqual(ranked[0][0], "7 mistakes every beginner runner makes")
        self.assertGreaterEqual(ranked[0][1].total, ranked[1][1].total)

    def test_deterministic(self):
        a = score_hook("Stop posting every day: what 1,000 brand accounts taught us").to_dict(ndigits=None)
        b = score_hook("Stop posting every day: what 1,000 brand accounts taught us").to_dict(ndigits=None)
        self.assertEqual(a, b)
        self.assertEqual(normalize("é"), "é")


if __name__ == "__main__":
    unittest.main()
