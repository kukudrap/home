import json
import unittest

from dopamine_king.models import COHORT_LABELS
from dopamine_king.webdata import BOSSES, DROP_RATES, MYTHS, build_bundle, bundle_json


class BundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build_bundle()

    def test_top_level_shape(self):
        expected = {"meta", "spec", "calibration", "cohort_labels", "benchmarks", "arena", "bosses", "patterns", "myths",
                    "lab", "vault", "loot", "forge_samples", "guru_sample"}
        self.assertEqual(set(self.bundle), expected)
        self.assertTrue(self.bundle["meta"]["synthetic"])
        self.assertIn("SIMULATED", self.bundle["meta"]["note"])

    def test_json_roundtrip_and_no_long_dash(self):
        text = bundle_json(self.bundle)
        self.assertEqual(json.loads(text)["meta"]["version"], 1)
        self.assertNotIn(chr(0x2014), text)
        self.assertNotIn(chr(0x2013), text)

    def test_arena_pairs_are_consistent(self):
        arena = self.bundle["arena"]
        self.assertEqual(len(arena), 120)
        self.assertEqual(len({p["id"] for p in arena}), 120)
        counts = {d: sum(1 for p in arena if p["difficulty"] == d) for d in ("easy", "medium", "hard")}
        self.assertEqual(counts, {"easy": 36, "medium": 48, "hard": 36})
        for p in arena:
            winner, loser = (p["a"], p["b"]) if p["winner"] == "a" else (p["b"], p["a"])
            self.assertGreater(winner["success"], loser["success"])
            gap = winner["success"] - loser["success"]
            self.assertGreaterEqual(gap, 5.5)
            self.assertNotEqual(p["a"]["text"].lower(), p["b"]["text"].lower())
            if p["upset"]:
                self.assertNotEqual(p["model_p_a"] >= 0.5, p["winner"] == "a")
        self.assertGreater(sum(p["upset"] for p in arena), 5)
        self.assertTrue({p["lang"] for p in arena} == {"en", "cs"})

    def test_benchmarks_are_monotonic(self):
        for name, data in self.bundle["benchmarks"].items():
            q = data["quantiles"]
            self.assertEqual(len(q), 101, name)
            self.assertEqual(q, sorted(q), name)
        self.assertIn("all", self.bundle["benchmarks"])

    def test_bosses_and_myths(self):
        for boss in BOSSES:
            self.assertIn(boss["cohort"], COHORT_LABELS)
            self.assertIn(boss["percentile"], (60, 75, 90))
            self.assertIn(boss["lang"], ("en", "cs"))
            for key in ("brief_en", "brief_cs", "taunt_en", "taunt_cs", "name"):
                self.assertTrue(boss[key])
        self.assertEqual(len({m["id"] for m in MYTHS}), len(MYTHS))
        for m in MYTHS:
            self.assertIn(m["answer"], ("myth", "fact"))
            for key in ("en", "cs", "why_en", "why_cs", "ref"):
                self.assertTrue(m[key], (m["id"], key))
        self.assertGreaterEqual(sum(m["answer"] == "myth" for m in MYTHS), 4)
        self.assertGreaterEqual(sum(m["answer"] == "fact" for m in MYTHS), 4)

    def test_loot_rates_are_published_and_sum_to_one(self):
        self.assertAlmostEqual(sum(DROP_RATES.values()), 1.0)
        self.assertEqual(self.bundle["loot"]["rates"], DROP_RATES)
        cards = self.bundle["loot"]["cards"]
        self.assertGreater(len(cards), 10)
        self.assertEqual(len({c["id"] for c in cards}), len(cards))
        self.assertTrue(all(c["rarity"] in DROP_RATES for c in cards))
        self.assertTrue(all(c["demo"] for c in cards if c["kind"] == "pattern"))

    def test_deterministic_except_timestamp(self):
        other = build_bundle()
        for key in ("arena", "patterns", "bosses", "benchmarks", "calibration"):
            self.assertEqual(self.bundle[key], other[key], key)


if __name__ == "__main__":
    unittest.main()
