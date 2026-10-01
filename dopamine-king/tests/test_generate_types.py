import unittest

from dopamine_king.generate.types import Brief, Draft, OfflineWriter, Skeleton, Slot


class SkeletonTests(unittest.TestCase):
    def make(self):
        return Skeleton(
            format="demo", lang="en",
            template="# {{hook}}\n\n{{intro}}\n\n{{outro}}",
            slots=[
                Slot("hook", "Write the title", max_chars=60, default="7 mistakes new runners make"),
                Slot("intro", "Write the intro"),
                Slot("outro", "Write the outro", default="Start today."),
            ],
            fixed={"channel": "blog"},
            assemble=lambda sk, values: {"words": sum(len(v.split()) for v in values.values())},
        )

    def test_offline_render_marks_open_slots(self):
        sk = self.make()
        draft = sk.render(OfflineWriter().fill(sk, Brief(brand="B", topic="t", audience="a")))
        self.assertIsInstance(draft, Draft)
        self.assertEqual(draft.hook, "7 mistakes new runners make")
        self.assertEqual(draft.slots_open, ["intro"])
        self.assertIn("[[ADD: Write the intro]]", draft.body)
        self.assertEqual(draft.parts["channel"], "blog")
        self.assertGreater(draft.parts["words"], 5)
        self.assertEqual(draft.parts["slots"]["outro"], "Start today.")

    def test_fills_override_defaults_and_blank_fills_fall_back(self):
        sk = self.make()
        draft = sk.render({"intro": "Hello there", "outro": "   ", "hook": "Custom title"})
        self.assertEqual(draft.hook, "Custom title")
        self.assertEqual(draft.slots_open, [])
        self.assertIn("Start today.", draft.body)

    def test_brief_helpers_and_roundtrip(self):
        b = Brief(brand="Zorvia", topic="bezecke boty", audience="zacatecnici", lang="cs",
                  topic_forms={"gen": "bezeckych bot"})
        self.assertEqual(b.topic_in("gen"), "bezeckych bot")
        self.assertEqual(b.topic_in("dat"), "bezecke boty")
        self.assertEqual(b.primary_keyword, "bezecke boty")
        self.assertEqual(Brief.from_dict(b.to_dict()), b)


if __name__ == "__main__":
    unittest.main()
