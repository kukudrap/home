import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from dopamine_king.generate.providers import (
    FALLBACK_BETA, SYSTEM_PROMPT, AnthropicWriter, WriterError, WriterRefused, all_violations, brief_block,
    build_user_prompt, normalize_dashes, select_writer, slot_violations, slots_schema,
)
from dopamine_king.generate.types import Brief, OfflineWriter, Skeleton, Slot

EM, EN = chr(0x2014), chr(0x2013)


def response(payload=None, *, text=None, stop_reason="end_turn", details=None):
    body = text if text is not None else json.dumps(payload)
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=body)],
        stop_reason=stop_reason, stop_details=details, model="claude-opus-5-5",
        usage=SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=0),
    )


class FakeMessages:
    def __init__(self, owner, beta):
        self.owner, self.beta = owner, beta

    def create(self, **kwargs):
        self.owner.calls.append({"beta": self.beta, **kwargs})
        item = self.owner.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = FakeMessages(self, False)
        self.beta = SimpleNamespace(messages=FakeMessages(self, True))


class StatusError(Exception):
    status_code = 400


def skeleton():
    return Skeleton(
        format="linkedin_post", lang="en", template="{{hook}}\n\n{{body}}\n\n{{cta}}",
        slots=[
            Slot("hook", "Write the hook", max_chars=40, kind="title", default="7 mistakes new runners make"),
            Slot("body", "Write the body", max_words=20, must_include=["shoes"]),
            Slot("cta", "Write the CTA", default="Try it today."),
        ],
        notes=["Keep paragraphs short."],
    )


BRIEF = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="running shoes",
              facts=["Our shoes weigh 210 g."], sources=[{"id": "s1", "title": "Study", "claim": "c", "url": "https://x.test"}],
              avoid=["cheap"], cta="Try the Aero 2")


class TextHelperTests(unittest.TestCase):
    def test_normalize_dashes(self):
        self.assertEqual(normalize_dashes(f"fast {EM} and clean"), "fast - and clean")
        self.assertEqual(normalize_dashes(f"fast{EM}clean"), "fast - clean")
        self.assertEqual(normalize_dashes(f"5{EN}10 km"), "5-10 km")
        self.assertEqual(normalize_dashes(f"a {EN} b"), "a - b")
        self.assertNotIn(EM, normalize_dashes(EM * 3))

    def test_slot_violations(self):
        slot = Slot("x", "i", max_chars=10, min_chars=3, max_words=2, must_include=["Shoe"])
        self.assertEqual(slot_violations(slot, "shoe fits"), [])
        self.assertEqual(len(slot_violations(slot, "this is far too long for it")), 3)
        self.assertEqual(slot_violations(slot, "ab"), ["2 characters, minimum is 3", "must include 'Shoe'"])
        self.assertEqual(all_violations(skeleton(), {"hook": "x" * 50, "cta": "ok"}).keys(), {"hook"})

    def test_prompts_carry_brief_template_and_slots(self):
        sk = skeleton()
        prompt = build_user_prompt(sk, BRIEF, sk.slots)
        for needle in ("Zorvia", "Our shoes weigh 210 g.", "id=s1", "{{hook}}", "- hook (title, max 40 chars)",
                       "must include: \"shoes\"", "current draft: 7 mistakes", "Keep paragraphs short.", "Avoid: cheap"):
            self.assertIn(needle, prompt)
        self.assertIn("(none provided: do not invent any)", brief_block(Brief(brand="B", topic="t", audience="a")))
        self.assertIn("Never invent statistics", SYSTEM_PROMPT)
        self.assertIn("return an empty string", SYSTEM_PROMPT)               # real data the brief lacks stays an open slot
        self.assertIn("never mention the brief", SYSTEM_PROMPT)
        self.assertNotIn(EM, SYSTEM_PROMPT + prompt)

    def test_schema(self):
        schema = slots_schema(["a", "b"])
        self.assertEqual(schema["required"], ["a", "b"])
        self.assertFalse(schema["additionalProperties"])


class AnthropicWriterTests(unittest.TestCase):
    def test_fill_request_shape_and_result(self):
        client = FakeClient([response({"hook": "5 shoe myths " + EM + " busted", "body": "Great shoes for new runners.", "cta": "Go."})])
        writer = AnthropicWriter(client=client)
        fills = writer.fill(skeleton(), BRIEF)
        call = client.calls[0]
        self.assertTrue(call["beta"])
        self.assertEqual(call["model"], "claude-opus-5-5")
        self.assertEqual(call["betas"], [FALLBACK_BETA])
        self.assertEqual(call["fallbacks"], "default")
        self.assertEqual(call["output_config"]["effort"], "medium")
        fmt = call["output_config"]["format"]
        self.assertEqual(fmt["type"], "json_schema")
        self.assertEqual(fmt["schema"]["required"], ["hook", "body", "cta"])
        self.assertNotIn("thinking", call)
        self.assertEqual(fills["hook"], "5 shoe myths - busted")
        self.assertEqual((writer.usage.calls, writer.usage.input_tokens, writer.usage.output_tokens), (1, 100, 50))

    def test_missing_slot_falls_back_to_default(self):
        client = FakeClient([response({"hook": "Short hook", "body": "Shoes matter."})])
        fills = AnthropicWriter(client=client).fill(skeleton(), BRIEF)
        self.assertEqual(fills["cta"], "Try it today.")

    def test_repair_loop_only_resends_violating_slots(self):
        too_long = " ".join(["shoes"] * 40)
        client = FakeClient([
            response({"hook": "Fine hook", "body": too_long, "cta": "Go."}),
            response({"body": "Short shoes advice for beginners."}),
        ])
        fills = AnthropicWriter(client=client).fill(skeleton(), BRIEF)
        self.assertEqual(len(client.calls), 2)
        repair = client.calls[1]
        self.assertEqual(repair["output_config"]["format"]["schema"]["required"], ["body"])
        self.assertIn("problems to fix: 40 words, maximum is 20", repair["messages"][0]["content"])
        self.assertEqual(fills["body"], "Short shoes advice for beginners.")
        self.assertEqual(fills["hook"], "Fine hook")

    def test_repair_gives_up_after_max_repairs_without_raising(self):
        bad = {"hook": "x" * 80, "body": "no keyword here", "cta": "Go."}
        client = FakeClient([response(bad)] * 3)
        fills = AnthropicWriter(client=client, max_repairs=2).fill(skeleton(), BRIEF)
        self.assertEqual(len(client.calls), 3)
        self.assertEqual(fills["hook"], "x" * 80)

    def test_refusal_is_raised_before_content_is_read(self):
        details = SimpleNamespace(category="cyber", explanation="no")
        client = FakeClient([response(text="not json", stop_reason="refusal", details=details)])
        with self.assertRaises(WriterRefused) as ctx:
            AnthropicWriter(client=client).fill(skeleton(), BRIEF)
        self.assertEqual(ctx.exception.category, "cyber")

    def test_truncation_and_invalid_json_raise_writer_error(self):
        with self.assertRaises(WriterError):
            AnthropicWriter(client=FakeClient([response(text='{"hook": "x', stop_reason="max_tokens")])).fill(skeleton(), BRIEF)
        with self.assertRaises(WriterError):
            AnthropicWriter(client=FakeClient([response(text="plain prose")])).fill(skeleton(), BRIEF)

    def test_old_sdk_typeerror_uses_extra_body(self):
        client = FakeClient([TypeError("unexpected keyword 'fallbacks'"), response({"hook": "H", "body": "shoes", "cta": "c"})])
        AnthropicWriter(client=client).fill(skeleton(), BRIEF)
        self.assertEqual(client.calls[1]["extra_body"], {"fallbacks": "default"})
        self.assertNotIn("fallbacks", client.calls[1])

    def test_platform_without_fallback_beta_retries_plain(self):
        client = FakeClient([StatusError("bad beta"), response({"hook": "H", "body": "shoes", "cta": "c"})])
        AnthropicWriter(client=client).fill(skeleton(), BRIEF)
        self.assertFalse(client.calls[1]["beta"])
        self.assertNotIn("betas", client.calls[1])

    def test_fallbacks_can_be_disabled_and_model_overridden(self):
        client = FakeClient([response({"hook": "H", "body": "shoes", "cta": "c"})])
        AnthropicWriter(client=client, use_fallbacks=False, tier="economy", effort="high").fill(skeleton(), BRIEF)
        call = client.calls[0]
        self.assertFalse(call["beta"])
        self.assertEqual(call["model"], "claude-sonnet-5-5")
        self.assertEqual(call["output_config"]["effort"], "high")

    def test_revise_touches_only_feedback_slots(self):
        client = FakeClient([response({"cta": "Run your first 5k with Zorvia."})])
        writer = AnthropicWriter(client=client)
        base = {"hook": "Keep me", "body": "Shoes help.", "cta": "Go."}
        out = writer.revise(skeleton(), BRIEF, base, {"cta": ["too generic"]})
        self.assertEqual(out["hook"], "Keep me")
        self.assertEqual(out["cta"], "Run your first 5k with Zorvia.")
        self.assertEqual(client.calls[0]["output_config"]["format"]["schema"]["required"], ["cta"])
        self.assertEqual(writer.revise(skeleton(), BRIEF, base, {}), base)

    def test_missing_sdk_or_credentials_gives_helpful_error(self):
        with self.assertRaises(WriterError) as ctx:
            AnthropicWriter().fill(skeleton(), BRIEF)
        self.assertRegex(str(ctx.exception).lower(), "anthropic")


class SelectWriterTests(unittest.TestCase):
    def test_selection(self):
        self.assertIsInstance(select_writer("offline"), OfflineWriter)
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsInstance(select_writer("auto"), OfflineWriter)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "k"}, clear=True):
            self.assertIsInstance(select_writer("auto"), AnthropicWriter)
        with self.assertRaises(ValueError):
            select_writer("gpt")

    def test_model_tiers(self):
        from dopamine_king.config import anthropic_model
        self.assertEqual(anthropic_model(), "claude-opus-5-5")
        self.assertEqual(anthropic_model("fast"), "claude-haiku-4-5")
        with mock.patch.dict(os.environ, {"KING_MODEL": "claude-sonnet-5-5"}):
            self.assertEqual(anthropic_model(), "claude-sonnet-5-5")


if __name__ == "__main__":
    unittest.main()
