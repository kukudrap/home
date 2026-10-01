import unittest

from dopamine_king.research.models import DRIVERS, Tactic
from dopamine_king.research.tactics import TACTICS, get_tactic, tactics_by_driver

REQUIRED_IDS = {
    "curiosity-gap", "anticipation-payoff", "prediction-error", "emotional-arousal", "negativity-bias",
    "social-currency", "triggers-cues", "social-proof", "practical-value", "cognitive-fluency",
    "numbers-specificity", "headline-questions", "storytelling", "personalization", "variable-reward",
    "streaks-loss-aversion", "gamification-points-badges", "intrinsic-vs-extrinsic-motivation",
    "scarcity-urgency", "dopamine-myth", "video-hook-first-seconds", "ab-testing-basics", "ab-testing-peeking",
    "geo-cite-sources", "geo-statistics", "geo-quotations", "geo-keyword-stuffing", "answer-first-structure",
    "eeat-experience", "scaled-content-abuse",
}
CZECH_LETTERS = set("áčďéěíňóřšťúůýž")
LONG_DASH = chr(0x2014)


class TacticCatalogueTests(unittest.TestCase):
    def test_every_required_tactic_exists(self):
        self.assertEqual(REQUIRED_IDS - set(TACTICS), set())
        self.assertGreaterEqual(len(TACTICS), 30)

    def test_ids_are_unique_kebab_case_and_match_their_keys(self):
        for key, tactic in TACTICS.items():
            self.assertEqual(key, tactic.id)
            self.assertRegex(key, r"^[a-z]+(-[a-z]+)*$")
        self.assertEqual(len({t.id for t in TACTICS.values()}), len(TACTICS))

    def test_every_driver_is_valid_and_every_driver_is_used(self):
        used = {t.driver for t in TACTICS.values()}
        self.assertTrue(used <= set(DRIVERS), used - set(DRIVERS))
        self.assertEqual(set(DRIVERS) - used, set())

    def test_names_and_summaries_exist_in_both_languages(self):
        for t in TACTICS.values():
            for field in ("name_en", "name_cs", "summary_en", "summary_cs"):
                self.assertTrue(getattr(t, field).strip(), f"{t.id}.{field}")

    def test_czech_text_differs_from_english_and_uses_diacritics(self):
        with_diacritics = 0
        for t in TACTICS.values():
            self.assertNotEqual(t.summary_cs, t.summary_en, t.id)
            self.assertNotEqual(t.name_cs, t.name_en, t.id)
            if CZECH_LETTERS & set(t.summary_cs.lower()):
                with_diacritics += 1
        self.assertGreaterEqual(with_diacritics, len(TACTICS) - 1)

    def test_ethics_notes_come_in_both_languages_or_not_at_all(self):
        for t in TACTICS.values():
            self.assertEqual(bool(t.ethics_en), bool(t.ethics_cs), t.id)

    def test_tactics_with_manipulation_risk_carry_an_ethics_note(self):
        for tid in ("scarcity-urgency", "variable-reward", "emotional-arousal", "social-proof", "personalization",
                    "negativity-bias", "curiosity-gap", "scaled-content-abuse"):
            self.assertTrue(get_tactic(tid).ethics_en, tid)
        self.assertIn("truthful", get_tactic("scarcity-urgency").ethics_en)

    def test_dopamine_myth_states_what_dopamine_is_not(self):
        t = get_tactic("dopamine-myth")
        self.assertIn("not a simple pleasure chemical", t.summary_en)
        for word in ("wanting", "anticipation", "prediction error"):
            self.assertIn(word, t.summary_en)

    def test_no_long_dash_anywhere(self):
        for t in TACTICS.values():
            self.assertNotIn(LONG_DASH, "".join(str(v) for v in t.to_dict().values()), t.id)


class TacticLookupTests(unittest.TestCase):
    def test_get_tactic(self):
        self.assertIsInstance(get_tactic("geo-quotations"), Tactic)
        with self.assertRaises(KeyError):
            get_tactic("no-such-tactic")

    def test_tactics_by_driver_keeps_definition_order(self):
        geo = tactics_by_driver("geo")
        self.assertEqual([t.id for t in geo],
                         ["geo-cite-sources", "geo-statistics", "geo-quotations", "geo-keyword-stuffing"])
        self.assertEqual(tactics_by_driver("nonsense"), [])
        self.assertEqual(sum(len(tactics_by_driver(d)) for d in DRIVERS), len(TACTICS))

    def test_dict_round_trip(self):
        t = get_tactic("curiosity-gap")
        self.assertEqual(Tactic.from_dict(t.to_dict()), t)


if __name__ == "__main__":
    unittest.main()
