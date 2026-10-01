import math
import unittest

from dopamine_king.lab import (
    AudienceSimulator, bayes_ab, compare_policies, holm_bonferroni, peeking_false_positive_rate,
    sample_size_per_arm, simulate, two_proportion_test, wilson_interval,
)
from dopamine_king.lab.sim import binomial


class FrequentistTests(unittest.TestCase):
    def test_known_z_and_p(self):
        r = two_proportion_test(100, 1000, 130, 1000)
        self.assertAlmostEqual(r.z, 2.1027, places=3)
        self.assertAlmostEqual(r.p_value, 0.0355, places=3)
        self.assertTrue(r.significant)
        self.assertAlmostEqual(r.rel_uplift, 0.3)
        self.assertLess(r.ci_diff[0], 0.03)
        self.assertGreater(r.ci_diff[1], 0.03)
        self.assertGreater(r.ci_diff[0], 0.0)

    def test_identical_arms_are_not_significant(self):
        r = two_proportion_test(50, 1000, 50, 1000)
        self.assertEqual(r.z, 0.0)
        self.assertAlmostEqual(r.p_value, 1.0)
        self.assertFalse(r.significant)

    def test_wilson_interval_reference_value(self):
        lo, hi = wilson_interval(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)
        self.assertAlmostEqual(hi, 0.7634, places=3)
        self.assertEqual(wilson_interval(0, 0), (0.0, 1.0))

    def test_sample_size_matches_textbook(self):
        self.assertAlmostEqual(sample_size_per_arm(0.05, 0.2), 8158, delta=6)
        self.assertGreater(sample_size_per_arm(0.05, 0.1), sample_size_per_arm(0.05, 0.2))
        with self.assertRaises(ValueError):
            sample_size_per_arm(0.9, 0.5)

    def test_holm_bonferroni(self):
        self.assertEqual(holm_bonferroni([0.01, 0.04, 0.03]), [True, False, False])
        self.assertEqual(holm_bonferroni([0.001, 0.002, 0.003]), [True, True, True])
        self.assertEqual(holm_bonferroni([0.2, 0.5]), [False, False])


class BayesTests(unittest.TestCase):
    def test_clear_winner(self):
        r = bayes_ab(100, 1000, 130, 1000, seed=3)
        self.assertGreater(r.p_b_better, 0.96)
        self.assertGreater(r.expected_uplift, 0.15)
        self.assertLess(r.expected_loss_choose_b, r.expected_loss_choose_a)

    def test_symmetry_and_determinism(self):
        r = bayes_ab(80, 1000, 80, 1000, seed=5)
        self.assertAlmostEqual(r.p_b_better, 0.5, delta=0.03)
        self.assertEqual(bayes_ab(80, 1000, 90, 1000, seed=1).to_dict(), bayes_ab(80, 1000, 90, 1000, seed=1).to_dict())

    def test_credible_intervals_contain_rate(self):
        r = bayes_ab(100, 1000, 130, 1000)
        self.assertTrue(r.credible_a[0] < 0.1 < r.credible_a[1])
        self.assertTrue(r.credible_b[0] < 0.13 < r.credible_b[1])


class PeekingTests(unittest.TestCase):
    def test_peeking_inflates_false_positives(self):
        single = peeking_false_positive_rate(looks=1, trials=500, seed=1)
        many = peeking_false_positive_rate(looks=10, trials=500, seed=1)
        self.assertLess(single, 0.10)
        self.assertGreater(many, 0.12)
        self.assertGreater(many, single + 0.05)


class BanditTests(unittest.TestCase):
    RATES = [0.03, 0.05, 0.04, 0.06]

    def test_invariants_and_determinism(self):
        a = simulate(self.RATES, 2000, "thompson", seed=4)
        b = simulate(self.RATES, 2000, "thompson", seed=4)
        self.assertEqual(a.to_dict(), b.to_dict())
        self.assertEqual(sum(a.pulls), 2000)
        curve = [v for _, v in a.regret_curve]
        self.assertEqual(curve, sorted(curve))
        self.assertEqual(a.regret_curve[-1][0], 2000)

    def test_thompson_beats_uniform_on_regret(self):
        res = compare_policies(self.RATES, 4000, policies=("uniform", "thompson", "ucb1"), seeds=8)
        self.assertLess(res["thompson"]["mean_regret"], res["uniform"]["mean_regret"] * 0.6)
        self.assertGreater(res["thompson"]["mean_best_arm_share"], 0.5)
        self.assertAlmostEqual(res["uniform"]["mean_best_arm_share"], 0.25, places=2)

    def test_unknown_policy_raises(self):
        with self.assertRaises(KeyError):
            simulate(self.RATES, 10, "nope")


class SimulatorTests(unittest.TestCase):
    def test_stronger_hook_has_higher_true_ctr(self):
        sim = AudienceSimulator(seed=1)
        strong = sim.true_ctr("7 mistakes every beginner runner makes (and how to fix them)")
        weak = sim.true_ctr("Our Q3 company update")
        bait = sim.true_ctr("You won't BELIEVE this one trick!!!")
        self.assertGreater(strong, weak)
        self.assertGreater(strong, bait)

    def test_duel_is_labelled_simulated_and_consistent(self):
        res = AudienceSimulator(seed=2).duel("7 mistakes every beginner runner makes", "Our Q3 company update", 20000)
        self.assertTrue(res["simulated"])
        self.assertEqual(len(res["variants"]), 2)
        self.assertGreater(res["variants"][0]["clicks"], res["variants"][1]["clicks"])
        self.assertLess(res["frequentist"]["p_value"], 0.05)
        self.assertGreater(res["bayesian"]["p_b_better"], -1)

    def test_binomial_mean(self):
        import random
        rng = random.Random(0)
        mean = sum(binomial(rng, 1000, 0.1) for _ in range(300)) / 300
        self.assertAlmostEqual(mean, 100, delta=3)
        self.assertEqual(binomial(rng, 0, 0.5), 0)
        self.assertEqual(binomial(rng, 10, 1.0), 10)
        small = sum(binomial(rng, 10, 0.3) for _ in range(500)) / 500
        self.assertAlmostEqual(small, 3.0, delta=0.4)


if __name__ == "__main__":
    unittest.main()
