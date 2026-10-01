import tempfile
import unittest
from pathlib import Path

from dopamine_king.analysis import (
    Benchmark, Calibration, analyze_items, calibrate_weights, compare_hooks, derived_signals, mine_patterns,
    success_index, win_probability,
)
from dopamine_king.analysis.linalg import (
    bootstrap_coef_ci, kfold_r2, nnls, pearson, percentile_rank, quantile, ridge_fit, solve, spearman,
)
from dopamine_king.models import COHORTS, ContentItem
from dopamine_king.store import Store
from dopamine_king.synth import PLANTED_EFFECTS, generate_corpus, populate_store


class LinalgTests(unittest.TestCase):
    def test_solve(self):
        x = solve([[2.0, 1.0], [1.0, 3.0]], [5.0, 10.0])
        self.assertAlmostEqual(x[0], 1.0)
        self.assertAlmostEqual(x[1], 3.0)
        with self.assertRaises(ValueError):
            solve([[1.0, 2.0], [2.0, 4.0]], [1.0, 2.0])

    def _data(self, n=300):
        import random
        rng = random.Random(3)
        rows = [[rng.gauss(0, 1), rng.gauss(5, 2), rng.random() < 0.3 and 1.0 or 0.0] for _ in range(n)]
        y = [2.0 + 3.0 * r[0] - 1.0 * r[1] + 4.0 * r[2] + rng.gauss(0, 0.5) for r in rows]
        return rows, y

    def test_ridge_recovers_coefficients(self):
        rows, y = self._data()
        fit = ridge_fit(rows, y, lam=0.1)
        self.assertAlmostEqual(fit.coef[0], 3.0, delta=0.15)
        self.assertAlmostEqual(fit.coef[1], -1.0, delta=0.1)
        self.assertAlmostEqual(fit.coef[2], 4.0, delta=0.4)
        self.assertGreater(fit.r2, 0.95)
        self.assertAlmostEqual(fit.predict_one(rows[0]), y[0], delta=2.0)

    def test_cv_and_bootstrap(self):
        rows, y = self._data()
        self.assertGreater(kfold_r2(rows, y, 0.1), 0.9)
        cis = bootstrap_coef_ci(rows, y, 0.1, n_boot=40)
        self.assertTrue(all(lo < hi for lo, hi in cis))
        self.assertTrue(cis[0][0] < 3.0 < cis[0][1])

    def test_nnls_is_non_negative(self):
        rows, y = self._data()
        w = nnls(rows, y)
        self.assertTrue(all(v >= 0 for v in w))
        self.assertAlmostEqual(w[0], 3.0, delta=0.3)
        self.assertEqual(w[1], 0.0)

    def test_stats_helpers(self):
        self.assertAlmostEqual(pearson([1, 2, 3, 4], [2, 4, 6, 8]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [1, 4, 9, 16]), 1.0)
        self.assertEqual(pearson([1, 1, 1], [1, 2, 3]), 0.0)
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertEqual(quantile(data, 0.5), 3.0)
        self.assertEqual(quantile(data, 0.25), 2.0)
        self.assertEqual(percentile_rank(data, 3.0), 50.0)
        self.assertEqual(percentile_rank(data, 0.0), 0.0)
        self.assertEqual(percentile_rank(data, 99.0), 100.0)


class SynthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.brands, cls.items = generate_corpus()

    def test_shape_and_flags(self):
        self.assertEqual(len(self.brands), 25)
        self.assertEqual(len(self.items), 1000)
        self.assertTrue(all(b.synthetic for b in self.brands))
        self.assertTrue(all(i.synthetic for i in self.items))
        self.assertEqual(len({b.id for b in self.brands}), 25)
        self.assertEqual(len({i.id for i in self.items}), 1000)
        self.assertTrue({b.cohort for b in self.brands} <= set(COHORTS))
        self.assertTrue(all(i.title.strip() for i in self.items))
        self.assertNotIn(chr(0x2014), " ".join(i.title for i in self.items))

    def test_czech_only_in_cz_local(self):
        cohort = {b.id: b.cohort for b in self.brands}
        for it in self.items:
            self.assertEqual(it.lang == "cs", cohort[it.brand_id] == "cz-local")

    def test_deterministic(self):
        again = generate_corpus()[1]
        self.assertEqual([i.title for i in self.items[:50]], [i.title for i in again[:50]])
        self.assertEqual(self.items[10].signals, again[10].signals)
        other = generate_corpus(seed=8)[1]
        self.assertNotEqual([i.title for i in self.items[:50]], [i.title for i in other[:50]])

    def test_planted_flags_recorded(self):
        flags = {f for i in self.items for f in i.meta["planted_flags"]}
        self.assertEqual(flags, set(PLANTED_EFFECTS))

    def test_populate_store(self):
        with Store() as s:
            self.assertEqual(populate_store(s, items_per_brand=5), (25, 125))
            self.assertEqual(s.stats()["synthetic_items"], 125)


class SuccessIndexTests(unittest.TestCase):
    def item(self, i, **signals):
        return ContentItem(id=f"i{i}", brand_id="b", platform="blog", format="article", title="t", signals=signals)

    def test_derived_signals_use_rates_or_raw_comments(self):
        d = derived_signals(self.item(1, views=1000.0, likes=50.0, comments=5.0, shares=10.0))
        self.assertAlmostEqual(d["like_rate"], 0.05)
        self.assertAlmostEqual(d["share_rate"], 0.01)
        raw = derived_signals(self.item(2, comments=7.0))
        self.assertEqual(raw, {"comments_raw": 7.0})
        self.assertEqual(derived_signals(self.item(3)), {})

    def test_ranks_inside_group_and_none_without_signals(self):
        items = [self.item(i, views=1000.0, likes=float(i)) for i in range(1, 31)] + [self.item(99)]
        idx = success_index(items, {"b": "tech"})
        self.assertGreater(idx["i30"], idx["i1"])
        self.assertGreater(idx["i30"], 95)
        self.assertLess(idx["i1"], 5)
        self.assertIsNone(idx["i99"])

    def test_small_groups_are_not_ranked(self):
        items = [self.item(i, views=1000.0, likes=float(i)) for i in range(1, 6)]
        self.assertTrue(all(v is None for v in success_index(items, {"b": "tech"}).values()))


class AnalysisOnCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        brands, items = generate_corpus()
        cls.cohort = {b.id: b.cohort for b in brands}
        cls.items = items
        cls.analyses = analyze_items(items, cls.cohort)

    def test_success_tracks_planted_quality_and_score_tracks_success(self):
        q = {i.id: i.meta["planted_quality"] for i in self.items}
        rows = [a for a in self.analyses if a.success is not None]
        self.assertEqual(len(rows), 1000)
        self.assertGreater(pearson([a.success for a in rows], [q[a.item_id] for a in rows]), 0.6)
        self.assertGreater(spearman([a.score.total for a in rows], [a.success for a in rows]), 0.3)

    def test_pattern_mining_recovers_planted_effects(self):
        pats = {p.feature: p for p in mine_patterns(self.analyses, n_boot=40)}
        for feature in ("curiosity_hits", "practical_hits", "contrast_hits", "second_person_hits", "has_number"):
            self.assertGreater(pats[feature].adj_effect, 1.0, feature)
            self.assertTrue(pats[feature].significant, feature)
        self.assertLess(pats["exclaim"].adj_effect, -1.0)
        self.assertLess(pats["n_words"].adj_effect, 0.0)
        d = pats["has_number"].to_dict()
        self.assertEqual(d["kind"], "binary")
        self.assertIn("label_cs", d)

    def test_pattern_mining_needs_enough_data(self):
        self.assertEqual(mine_patterns(self.analyses[:10], n_boot=10), [])

    def test_pattern_examples_come_from_titles(self):
        titles = {i.id: i.title for i in self.items}
        pats = mine_patterns(self.analyses, titles, n_boot=20)
        number = next(p for p in pats if p.feature == "has_number")
        self.assertTrue(number.examples)
        self.assertTrue(all(any(ch.isdigit() for ch in e) for e in number.examples))

    def test_calibration_and_win_probability(self):
        cal = calibrate_weights(self.analyses)
        self.assertAlmostEqual(sum(cal.weights.values()), 1.0, places=6)
        self.assertGreaterEqual(cal.cv_spearman_calibrated, cal.cv_spearman_default - 1e-9)
        self.assertGreater(cal.logit_scale, 3.0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cal.json"
            cal.save(path)
            self.assertEqual(Calibration.load(path).weights.keys(), cal.weights.keys())
        self.assertAlmostEqual(win_probability(50, 50), 0.5)
        self.assertGreater(win_probability(70, 40), 0.9)
        self.assertLess(win_probability(40, 70), 0.1)

    def test_calibration_falls_back_on_tiny_corpus(self):
        cal = calibrate_weights(self.analyses[:20])
        self.assertTrue(cal.notes)
        self.assertEqual(cal.cv_spearman_calibrated, 0.0)

    def test_benchmark(self):
        b = Benchmark(self.analyses)
        self.assertIn("sport", b.cohorts())
        stats = b.stats("sport")
        self.assertLess(stats["p25"], stats["p50"])
        self.assertLess(stats["p50"], stats["p90"])
        self.assertLess(b.percentile(10, "sport"), b.percentile(60, "sport"))
        res = b.compare("7 mistakes every beginner runner makes (and how to fix them)", cohort="sport")
        self.assertGreater(res["percentile"], 85)
        self.assertEqual(len(res["feature_gaps"]), 5)
        weak = b.compare("Our Q3 company update", cohort="sport")
        self.assertLess(weak["percentile"], 40)
        self.assertTrue(b.top_profile("sport"))
        self.assertEqual(Benchmark([]).percentile(50.0), 50.0)


class CompareTests(unittest.TestCase):
    def test_clear_winner_with_reasons(self):
        c = compare_hooks("7 mistakes every beginner runner makes (and how to fix them)", "Our Q3 company update")
        self.assertEqual(c.winner, "a")
        self.assertGreater(c.p_a_wins, 0.8)
        self.assertTrue(c.reasons_en and c.reasons_cs)
        d = c.to_dict()
        self.assertEqual(d["winner"], "a")

    def test_clickbait_flagged_in_reasons(self):
        c = compare_hooks("Why most marketing dashboards lie to you", "You won't BELIEVE this one trick!!!")
        self.assertEqual(c.winner, "a")
        self.assertTrue(any("clickbait" in r.lower() for r in c.reasons_en))

    def test_tie_and_symmetry(self):
        c = compare_hooks("Why most dashboards lie", "Why most dashboards lie")
        self.assertEqual(c.winner, "tie")
        self.assertAlmostEqual(c.p_a_wins, 0.5)
        ab = compare_hooks("7 ways to cut churn", "Our update")
        ba = compare_hooks("Our update", "7 ways to cut churn")
        self.assertAlmostEqual(ab.p_a_wins + ba.p_a_wins, 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
