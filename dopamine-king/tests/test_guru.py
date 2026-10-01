import unittest

from dopamine_king.generate.types import Brief
from dopamine_king.guru import build_plan
from dopamine_king.guru.planner import CHANNELS, DAYS, PILLAR_SHARE, _largest_remainder
from dopamine_king.lab.ab import sample_size_per_arm

EN = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", goal="awareness", cohort="sport",
           facts=["Our Aero 2 weighs 210 g."], offer="The Aero 2 running shoe")
B2B = Brief(brand="Quillo", topic="CRM onboarding", audience="sales teams at small companies", goal="conversion", cohort="b2b-saas")
CS = Brief(brand="Hrnek a Hvězda", topic="domácí káva", audience="začátečníci", goal="consideration", lang="cs", cohort="cz-local")


class PlanTests(unittest.TestCase):
    def test_shape_and_counts(self):
        plan = build_plan(EN, weeks=4, posts_per_week=5)
        self.assertEqual(len(plan.calendar), 20)
        self.assertEqual({e["week"] for e in plan.calendar}, {1, 2, 3, 4})
        self.assertTrue(all(e["day"] in DAYS for e in plan.calendar))
        self.assertAlmostEqual(sum(c["posts_per_week"] for c in plan.channels), 5.0, delta=0.05)
        self.assertAlmostEqual(sum(p["share"] for p in plan.pillars), 1.0)
        d = plan.to_dict()
        for key in ("brief", "positioning", "pillars", "channels", "calendar", "experiments", "kpis", "geo", "guardrails_en", "guardrails_cs"):
            self.assertIn(key, d)

    def test_every_calendar_format_is_a_known_channel_format(self):
        known = {f for c in CHANNELS.values() for f in c["formats"]}
        for brief in (EN, B2B, CS):
            for e in build_plan(brief).calendar:
                self.assertIn(e["format"], known)
                self.assertIn(e["format"], CHANNELS[e["channel"]]["formats"])

    def test_b2b_vs_b2c_channel_mix(self):
        b2b = {c["id"] for c in build_plan(B2B).channels}
        b2c = {c["id"] for c in build_plan(EN).channels}
        self.assertIn("linkedin", b2b)
        self.assertNotIn("short_video", b2b)
        self.assertIn("short_video", b2c)
        self.assertNotIn("linkedin", b2c)
        self.assertIn("facebook", {c["id"] for c in build_plan(CS).channels})

    def test_pillar_shares_follow_goal(self):
        counts = {}
        for e in build_plan(B2B, posts_per_week=10).calendar:
            counts[e["pillar"]] = counts.get(e["pillar"], 0) + 1
        self.assertEqual(counts["convert"], 14)
        self.assertEqual(counts["prove"], 14)
        self.assertEqual(sum(counts.values()), 40)

    def test_each_week_has_one_experiment_with_distinct_variant(self):
        plan = build_plan(EN)
        exps = [e for e in plan.calendar if e["experiment"]]
        self.assertEqual([e["week"] for e in exps], [1, 2, 3, 4])
        for e in exps:
            self.assertTrue(e["experiment"]["variant_b"])
            self.assertNotEqual(e["experiment"]["variant_b"], e["hook"])

    def test_hooks_are_unique_across_the_calendar(self):
        hooks = [e["hook"] for e in build_plan(EN).calendar]
        self.assertEqual(len(hooks), len(set(hooks)))

    def test_experiments_use_lab_sample_size_and_flag_baseline(self):
        plan = build_plan(EN, baseline_ctr=0.05, mde_rel=0.2)
        self.assertEqual(plan.experiments[0]["n_per_arm"], sample_size_per_arm(0.05, 0.2))
        self.assertTrue(plan.experiments[0]["note_en"])

    def test_needs_input_lists_missing_material_and_never_invents_facts(self):
        plan = build_plan(B2B)
        self.assertEqual(len(plan.needs_input), 3)
        self.assertIn("[[ADD", plan.positioning)
        rich = build_plan(EN)
        self.assertIn("Our Aero 2 weighs 210 g.", rich.positioning)
        self.assertEqual(len(rich.needs_input), 1)

    def test_czech_plan_and_markdown(self):
        plan = build_plan(CS)
        md = plan.to_markdown("cs")
        self.assertIn("Obsahový plán", md)
        self.assertIn("Kalendář", md)
        self.assertIn("Chybí vstup od vás", md)
        self.assertIn("Slib", plan.positioning)
        self.assertTrue(all("angles" in p for p in plan.pillars))
        self.assertIn("Content plan", build_plan(EN).to_markdown("en"))

    def test_primary_kpi_matches_goal_and_no_long_dash(self):
        plan = build_plan(B2B)
        self.assertEqual([k["goal"] for k in plan.kpis if k["primary"]], ["conversion"])
        text = plan.to_markdown("en") + plan.to_markdown("cs")
        self.assertNotIn(chr(0x2014), text)
        self.assertNotIn(chr(0x2013), text)

    def test_custom_channels_and_largest_remainder(self):
        plan = build_plan(EN, channels=["x", "email"], posts_per_week=3)
        self.assertEqual({c["id"] for c in plan.channels}, {"x", "email"})
        self.assertEqual(_largest_remainder({"a": 0.5, "b": 0.3, "c": 0.2}, 7), {"a": 4, "b": 2, "c": 1})
        for shares in PILLAR_SHARE.values():
            self.assertAlmostEqual(sum(shares.values()), 1.0)


if __name__ == "__main__":
    unittest.main()
