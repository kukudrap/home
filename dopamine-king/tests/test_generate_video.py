import math
import re
import unittest

from dopamine_king.generate import video
from dopamine_king.generate.formats import build_skeleton, formats_by_module, get_format, validate_draft
from dopamine_king.generate.types import Brief, OfflineWriter
from dopamine_king.generate.video import (
    CUT_EVERY_S, HOOK_MAX_S, PLAN_STYLES, SHORT_DURATIONS, SHORT_STYLES, beat_label, estimate_duration, fmt_time, parse_srt,
    plan_beats, plan_podcast, plan_youtube, speech_rate, split_seconds, timeline_md, to_srt,
)

CS_FORMS = {"gen": "běžeckých bot", "acc": "běžecké boty", "loc": "běžeckých botách", "ins": "běžeckými botami", "dat": "běžeckým botám"}
VIDEO_IDS = formats_by_module()["video"]


def en(**kw):
    base = dict(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="running shoes for flat feet",
                cta="Download the free fit guide", facts=["Tested by 1,200 runners over 6 months"])
    base.update(kw)
    return Brief(**base)


def cs(**kw):
    base = dict(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", keyword="běžecké boty pro ploché nohy",
                cta="Stáhněte si průvodce výběrem", topic_forms=dict(CS_FORMS))
    base.update(kw)
    return Brief(**base)


def render(fid, brief, fills=None, **kw):
    sk = build_skeleton(fid, brief, **kw)
    values = OfflineWriter().fill(sk, brief)
    values.update(fills or {})
    return sk, sk.render(values)


def check(fid, brief, fills=None, **kw):
    sk, draft = render(fid, brief, fills, **kw)
    return get_format(fid).validate(draft)


def codes(found):
    return {i.code for i in found}


def severity(found, code):
    return {i.severity for i in found if i.code == code}


def fill_all_voiceovers(sk, words_per_second=1.0):
    """Fill every vo slot with about words_per_second words per second of its beat."""
    fills = {}
    for b in sk.fixed["plan"]:
        n = max(1, int((b["end"] - b["start"]) * words_per_second))
        fills[f"vo_{b['id']}"] = " ".join(f"word{i}" for i in range(n)) + "."
        if f"loop_{b['id']}" in {s.id for s in sk.slots}:
            fills[f"loop_{b['id']}"] = "What comes next?"
    return fills


class TimingModelTests(unittest.TestCase):
    def test_speech_rate(self):
        self.assertEqual(speech_rate("en"), 2.6)
        self.assertEqual(speech_rate("cs"), 2.4)
        self.assertEqual(speech_rate("de"), 2.6)

    def test_estimate_duration(self):
        self.assertAlmostEqual(estimate_duration(" ".join(["w"] * 26), "en"), 10.0)
        self.assertAlmostEqual(estimate_duration(" ".join(["w"] * 24), "cs"), 10.0)
        self.assertEqual(estimate_duration("", "en"), 0.0)
        self.assertAlmostEqual(estimate_duration("one two [[ADD: lots of words here]] three", "en"), 3 / 2.6)

    def test_fmt_time(self):
        self.assertEqual([fmt_time(s) for s in (0, 5, 65, 600, 3599)], ["0:00", "0:05", "1:05", "10:00", "59:59"])

    def test_split_seconds_is_exact_and_respects_the_minimum(self):
        for total in range(12, 120):
            parts = split_seconds(total, [1.0, 1.3, 1.3, 1.0])
            self.assertEqual(sum(parts), total)
            self.assertTrue(all(p >= 3 for p in parts))
        self.assertEqual(split_seconds(10, [1, 1]), [5, 5])
        with self.assertRaises(ValueError):
            split_seconds(5, [1, 1])

    def test_plan_beats_sums_exactly_for_every_duration_style_and_language(self):
        for duration in SHORT_DURATIONS:
            for style in PLAN_STYLES:
                for lang in ("en", "cs"):
                    for disclosure in (False, True):
                        if style == "pas" and duration < 30:
                            continue
                        beats = plan_beats(duration, style, lang, disclosure=disclosure)
                        self.assertEqual(sum(b["end"] - b["start"] for b in beats), duration, (duration, style))
                        self.assertEqual(beats[0]["start"], 0)
                        self.assertEqual(beats[-1]["end"], duration)
                        for a, b in zip(beats, beats[1:]):
                            self.assertEqual(a["end"], b["start"])
                        ids = [b["id"] for b in beats]
                        self.assertEqual(len(ids), len(set(ids)))
                        for b in beats:
                            self.assertIsInstance(b["start"], int)
                            self.assertGreater(b["end"], b["start"])

    def test_hook_is_first_and_at_most_three_seconds_and_cta_is_last(self):
        for duration in SHORT_DURATIONS:
            for style in SHORT_STYLES:
                beats = plan_beats(duration, style)
                self.assertEqual(beats[0]["id"], "hook")
                self.assertLessEqual(beats[0]["end"] - beats[0]["start"], HOOK_MAX_S)
                self.assertEqual(beats[-1]["id"], "cta")
                self.assertEqual([b["id"] for b in beats].count("cta"), 1)

    def test_disclosure_beat_only_when_requested(self):
        plain = plan_beats(30, "ugc")
        self.assertNotIn("disclosure", [b["id"] for b in plain])
        sponsored = plan_beats(30, "ugc", disclosure=True)
        self.assertEqual([b["id"] for b in sponsored][:2], ["hook", "disclosure"])
        self.assertEqual(sponsored[1]["end"] - sponsored[1]["start"], video.DISCLOSURE_S)

    def test_word_budgets_follow_duration_times_rate(self):
        for lang in ("en", "cs"):
            for b in plan_beats(60, "talking_head", lang):
                self.assertEqual(b["max_words"], int((b["end"] - b["start"]) * speech_rate(lang)))

    def test_a_visual_change_at_least_every_four_seconds(self):
        for duration in SHORT_DURATIONS:
            for style in PLAN_STYLES:
                if style == "pas" and duration < 30:
                    continue
                beats = plan_beats(duration, style, disclosure=duration % 2 == 0)
                changes = sorted(c for b in beats for c in b["visual_changes"])
                self.assertEqual(changes[0], 0)
                points = changes + [duration]
                gaps = [b - a for a, b in zip(points, points[1:])]
                self.assertLessEqual(max(gaps), CUT_EVERY_S, (duration, style, gaps))
                for b in beats:
                    self.assertEqual(b["cuts"], len(b["visual_changes"]))
                    self.assertEqual(b["cuts"], math.ceil((b["end"] - b["start"]) / CUT_EVERY_S))
                    self.assertTrue(all(b["start"] <= c < b["end"] for c in b["visual_changes"]))

    def test_pattern_interrupts(self):
        for duration in SHORT_DURATIONS:
            beats = plan_beats(duration, "talking_head")
            self.assertTrue(beats[0]["pattern_interrupt"])
            self.assertFalse(beats[-1]["pattern_interrupt"])
            flagged = [b["start"] for b in beats if b["pattern_interrupt"]]
            self.assertGreaterEqual(len(flagged), 2)
            points = flagged + [duration]
            self.assertLessEqual(max(b - a for a, b in zip(points, points[1:])), 15, duration)
            for b in beats:
                if b["id"] == "proof":
                    self.assertTrue(b["pattern_interrupt"])

    def test_invalid_plans_raise(self):
        with self.assertRaises(ValueError) as ctx:
            plan_beats(30, "mime")
        self.assertIn("talking_head", str(ctx.exception))
        with self.assertRaises(ValueError):
            plan_beats(10)
        with self.assertRaises(ValueError):
            plan_beats(15, "pas")

    def test_labels(self):
        self.assertEqual(beat_label("point_2", "talking_head", "en"), "Point 2")
        self.assertEqual(beat_label("point_2", "screen_demo", "en"), "Step 2")
        self.assertEqual(beat_label("problem", "screen_demo", "en"), "Setup")
        self.assertEqual(beat_label("proof", "screen_demo", "cs"), "Výsledek")
        self.assertEqual(beat_label("cta", "ugc", "cs"), "Výzva k akci")
        self.assertEqual([b["label"] for b in plan_beats(15, "talking_head", "cs")], ["Hook", "Bod 1", "Bod 2", "Výzva k akci"])

    def test_plan_structure_by_duration(self):
        self.assertEqual([b["id"] for b in plan_beats(15)], ["hook", "point_1", "point_2", "cta"])
        self.assertEqual([b["id"] for b in plan_beats(30)], ["hook", "problem", "point_1", "point_2", "proof", "cta"])
        self.assertEqual(len(plan_beats(90)), 10)
        self.assertEqual([b["id"] for b in plan_beats(30, "pas")], ["hook", "problem", "agitate", "solution", "proof", "cta"])


class SrtTests(unittest.TestCase):
    BEATS = [
        {"id": "hook", "start": 0, "end": 3, "voiceover": "Stop buying shoes by looks, check this first."},
        {"id": "skip", "start": 3, "end": 10, "voiceover": "[[ADD: still to be written]]"},
        {"id": "long", "start": 10, "end": 20, "voiceover": "People pick a pair in five minutes, and then they regret it for months because nobody explained how to test the fit."},
    ]

    def test_format(self):
        srt = to_srt(self.BEATS, "en")
        self.assertTrue(srt.endswith("\n"))
        blocks = srt.strip().split("\n\n")
        for i, block in enumerate(blocks, 1):
            lines = block.split("\n")
            self.assertEqual(lines[0], str(i))
            self.assertRegex(lines[1], r"^\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}$")
            self.assertGreaterEqual(len(lines), 3)
        self.assertIn("00:00:00,000 -->", srt)

    def test_chunks_are_short_and_wrapped(self):
        for cue in parse_srt(to_srt(self.BEATS, "en")):
            self.assertLessEqual(len(cue["lines"]), 2)
            self.assertLessEqual(sum(len(l.split()) for l in cue["lines"]), 7)
        text = " ".join(["interesting"] * 7)
        cue = parse_srt(to_srt([{"id": "a", "start": 0, "end": 7, "voiceover": text}], "en"))[0]
        self.assertEqual(len(cue["lines"]), 2)
        self.assertEqual(" ".join(cue["lines"]), text)

    def test_placeholder_beats_are_skipped(self):
        cues = parse_srt(to_srt(self.BEATS, "en"))
        self.assertTrue(all(c["end"] <= 3000 or c["start"] >= 10000 for c in cues))
        self.assertEqual(to_srt([{"id": "a", "start": 0, "end": 5, "voiceover": "[[ADD: x]]"}], "en"), "")
        self.assertEqual(to_srt([], "en"), "")
        mixed = to_srt([{"id": "a", "start": 0, "end": 5, "voiceover": "Real words [[ADD: more]]"}], "en")
        self.assertIn("Real words", mixed)
        self.assertNotIn("ADD", mixed)

    def test_never_overlaps_and_never_leaves_the_beat(self):
        for beats in (self.BEATS, [{"id": str(i), "start": i * 7, "end": i * 7 + 7, "voiceover": "word " * (3 + i * 5)} for i in range(6)]):
            cues = parse_srt(to_srt(beats, "en"))
            prev = 0
            for cue in cues:
                self.assertGreater(cue["end"], cue["start"])
                self.assertGreaterEqual(cue["start"], prev)
                prev = cue["end"]
                self.assertTrue(any(b["start"] * 1000 <= cue["start"] and cue["end"] <= b["end"] * 1000 for b in beats))
            self.assertEqual([c["index"] for c in cues], list(range(1, len(cues) + 1)))

    def test_timing_is_proportional_to_words_inside_the_beat(self):
        beat = {"id": "a", "start": 10, "end": 24, "voiceover": " ".join(["w"] * 14)}
        cues = parse_srt(to_srt([beat], "en"))
        self.assertEqual([(c["start"], c["end"]) for c in cues], [(10000, 17000), (17000, 24000)])
        beat = {"id": "a", "start": 0, "end": 10, "voiceover": "One two three four five six seven. Eight."}
        cues = parse_srt(to_srt([beat], "en"))
        self.assertEqual(len(cues), 2)
        self.assertEqual(cues[0]["end"], 8750)
        self.assertEqual(cues[-1]["end"], 10000)

    def test_czech_text_and_unicode_survive(self):
        srt = to_srt([{"id": "a", "start": 0, "end": 3, "voiceover": "Běžecké boty: přestaňte plýtvat časem"}], "cs")
        self.assertIn("Běžecké boty: přestaňte plýtvat časem", srt.replace("\n", " "))

    def test_parse_srt_rejects_garbage(self):
        for bad in ("nonsense", "1\n00:00:01,000 -> 00:00:02,000\ntext", "x\n00:00:01,000 --> 00:00:02,000\ntext"):
            with self.assertRaises(ValueError):
                parse_srt(bad)
        self.assertEqual(parse_srt(""), [])

    def test_timeline_markdown(self):
        beats = [{"id": "hook", "label": "Hook", "start": 0, "end": 3, "voiceover": "Hi | there", "on_screen_text": "[[ADD: x]]",
                  "visual": "Wide shot", "pattern_interrupt": True},
                 {"id": "cta", "label": "Call to action", "start": 3, "end": 9, "voiceover": "Go", "on_screen_text": "Go", "visual": "v",
                  "pattern_interrupt": False}]
        md = timeline_md(beats, "en")
        lines = md.split("\n")
        self.assertTrue(lines[0].startswith("| Time | Beat |"))
        self.assertEqual(lines[1], "|---|---|---|---|---|")
        self.assertIn("| 0:00-0:03 | Hook * | Hi / there | (open) | Wide shot |", md)
        self.assertIn("| 0:03-0:09 | Call to action | Go | Go | v |", md)
        self.assertIn("pattern interrupt", lines[-1])
        self.assertIn("(doplnit)", timeline_md(beats, "cs"))


class ShortVideoTests(unittest.TestCase):
    def test_defaults(self):
        sk, draft = render("short_video_script", en())
        self.assertEqual(sk.fixed["duration"], 30)
        self.assertEqual(sk.fixed["style"], "talking_head")
        self.assertEqual(sk.meta["duration_s"], 30)
        self.assertEqual(sk.hook_slot, "vo_hook")
        beats = draft.parts["beats"]
        self.assertEqual([b["id"] for b in beats], ["hook", "problem", "point_1", "point_2", "proof", "cta"])
        self.assertEqual(draft.hook, beats[0]["voiceover"])
        self.assertLessEqual(len(draft.hook.split()), 7)

    def test_every_duration_and_style_builds(self):
        for duration in SHORT_DURATIONS:
            for style in SHORT_STYLES:
                for brief in (en(), cs(sponsored=True)):
                    sk, draft = render("short_video_script", brief, options={"duration": duration, "style": style})
                    beats = draft.parts["beats"]
                    self.assertEqual(sum(b["end"] - b["start"] for b in beats), duration)
                    self.assertEqual(len(beats), len(sk.fixed["plan"]))
                    self.assertEqual(draft.parts["style"], style)
                    self.assertEqual([i for i in get_format("short_video_script").validate(draft) if i.severity == "error"], [])

    def test_invalid_options_raise(self):
        for opts in ({"duration": 20}, {"duration": "30"}, {"style": "mime"}):
            with self.assertRaises(ValueError):
                build_skeleton("short_video_script", en(), options=opts)

    def test_three_slots_per_beat_with_limits(self):
        sk = build_skeleton("short_video_script", en(), options={"duration": 45})
        for b in sk.fixed["plan"]:
            vo, tx, vis = sk.slot(f"vo_{b['id']}"), sk.slot(f"text_{b['id']}"), sk.slot(f"visual_{b['id']}")
            self.assertEqual(vo.max_words, b["max_words"])
            self.assertEqual(tx.max_words, 6)
            self.assertIn(f"Plan {b['cuts']} shot", vis.instruction)
            self.assertIsNone(vis.default if b["id"] != "disclosure" else None)
        ids = [s.id for s in sk.slots]
        self.assertEqual(len([i for i in ids if i.startswith("vo_")]), len(sk.fixed["plan"]))
        self.assertIn("caption", ids)
        self.assertIn("hashtags", ids)

    def test_prose_and_proof_have_no_defaults(self):
        sk = build_skeleton("short_video_script", en(), options={"duration": 60})
        for b in sk.fixed["plan"]:
            if b["id"] not in ("hook", "cta"):
                self.assertIsNone(sk.slot(f"vo_{b['id']}").default, b["id"])
                self.assertIsNone(sk.slot(f"text_{b['id']}").default, b["id"])
        self.assertIn("Never invent", sk.slot("vo_proof").instruction)

    def test_defaults_restate_the_brief_only(self):
        sk, draft = render("short_video_script", en())
        self.assertEqual(draft.parts["slots"]["vo_cta"], "Download the free fit guide")
        self.assertEqual(draft.parts["slots"]["text_cta"], "Download the free fit guide")
        self.assertEqual(draft.parts["slots"]["hashtags"], "#RunningShoes #BeginnerRunners #Zorvia")
        sk, draft = render("short_video_script", en(cta=None))
        self.assertIn("vo_cta", draft.slots_open)
        sk, draft = render("short_video_script", en(cta="A very long call to action that cannot fit in four seconds of speech"))
        self.assertIn("vo_cta", draft.slots_open)

    def test_hook_argument_and_style_hints(self):
        sk = build_skeleton("short_video_script", en(), hook="Stop guessing your shoe size", options={"style": "screen_demo"})
        self.assertEqual(sk.slot("vo_hook").default, "Stop guessing your shoe size")
        self.assertIn("Screen recording", sk.slot("visual_hook").instruction)
        sk = build_skeleton("short_video_script", en(), options={"style": "ugc"})
        self.assertIn("Handheld", sk.slot("visual_hook").instruction)
        sk = build_skeleton("short_video_script", en(), options={"style": "voiceover_broll"})
        self.assertIn("B-roll", sk.slot("visual_hook").instruction)
        sk = build_skeleton("short_video_script", en(), options={"style": "screen_demo"})
        self.assertIn("Step 1", sk.slot("vo_point_1").instruction)
        self.assertIn("Setup", sk.slot("vo_problem").instruction)

    def test_assemble_output_shape(self):
        sk, draft = render("short_video_script", en())
        beats = draft.parts["beats"]
        required = {"id", "label", "start", "end", "voiceover", "on_screen_text", "visual", "pattern_interrupt"}
        for b in beats:
            self.assertTrue(required <= set(b), b)
        self.assertEqual(beats[0]["label"], "Hook")
        md = draft.parts["timeline_md"]
        self.assertEqual(len(md.split("\n")), 2 + len(beats) + 2)
        self.assertIn("| 0:00-0:03 | Hook * |", md)
        self.assertIsInstance(draft.parts["srt"], str)
        self.assertEqual(draft.parts["duration"], 30)
        self.assertEqual(draft.parts["plan"][0]["id"], "hook")

    def test_srt_only_covers_filled_voiceovers(self):
        sk, draft = render("short_video_script", en())
        cues = parse_srt(draft.parts["srt"])
        self.assertEqual({(c["start"] // 1000) for c in cues} <= {0, 26, 27, 28, 29}, True)
        sk = build_skeleton("short_video_script", en())
        draft = sk.render({**OfflineWriter().fill(sk, en()), **fill_all_voiceovers(sk, 2.0)})
        cues = parse_srt(draft.parts["srt"])
        self.assertGreater(len(cues), len(sk.fixed["plan"]))
        self.assertEqual(cues[-1]["end"], 30000)
        self.assertEqual([i for i in get_format("short_video_script").validate(draft) if i.severity != "info"], [])

    def test_sponsored_adds_a_disclosure_beat_in_both_languages(self):
        sk, draft = render("short_video_script", en(sponsored=True))
        beat = draft.parts["beats"][1]
        self.assertEqual(beat["id"], "disclosure")
        self.assertEqual(beat["voiceover"], "Paid partnership with Zorvia.")
        self.assertEqual(beat["on_screen_text"], "#ad")
        self.assertEqual(draft.parts["slots"]["disclosure"], "#ad")
        sk, draft = render("short_video_script", cs(sponsored=True))
        beat = draft.parts["beats"][1]
        self.assertEqual(beat["voiceover"], "Reklamní spolupráce se značkou Zorvia.")
        self.assertEqual(beat["on_screen_text"], "#reklama")
        self.assertLessEqual(len(beat["voiceover"].split()), beat["max_words"])
        self.assertEqual(validate_draft(draft)[0].code, "SLOTS_OPEN")

    def test_czech_labels_and_budget(self):
        sk, draft = render("short_video_script", cs())
        self.assertEqual(draft.parts["beats"][0]["max_words"], 7)
        self.assertEqual(draft.parts["beats"][-1]["label"], "Výzva k akci")
        self.assertIn("Scénář krátkého videa", draft.body)
        self.assertIn("**Popisek:**", draft.body)
        self.assertIn("Text na obrazovce", draft.body)


class UgcAdTests(unittest.TestCase):
    def test_problem_agitate_solution_structure(self):
        sk, draft = render("ugc_ad_script", en())
        self.assertEqual([b["id"] for b in draft.parts["beats"]], ["hook", "problem", "agitate", "solution", "proof", "cta"])
        self.assertEqual(sk.fixed["duration"], 30)
        self.assertIsNone(sk.slot("vo_proof").default)
        self.assertIsNone(sk.slot("text_proof").default)
        self.assertIn("vo_proof", draft.slots_open)
        self.assertIn("Never invent numbers or testimonials", sk.slot("vo_proof").instruction)

    def test_disclosure_beat_when_sponsored(self):
        for brief in (en(sponsored=True), cs(sponsored=True)):
            sk, draft = render("ugc_ad_script", brief)
            ids = [b["id"] for b in draft.parts["beats"]]
            self.assertEqual(ids[:2], ["hook", "disclosure"])
            self.assertEqual(sum(b["end"] - b["start"] for b in draft.parts["beats"]), 30)
            self.assertNotIn("DISCLOSURE_MISSING", codes(get_format("ugc_ad_script").validate(draft)))
        _, draft = render("ugc_ad_script", en())
        self.assertNotIn("disclosure", [b["id"] for b in draft.parts["beats"]])
        self.assertIn("DISCLOSURE_REMINDER", codes(get_format("ugc_ad_script").validate(draft)))

    def test_durations(self):
        for duration in (30, 45, 60):
            _, draft = render("ugc_ad_script", en(), options={"duration": duration})
            self.assertEqual(draft.parts["beats"][-1]["end"], duration)
        with self.assertRaises(ValueError):
            build_skeleton("ugc_ad_script", en(), options={"duration": 15})

    def test_missing_disclosure_in_a_sponsored_ad_is_an_error(self):
        sk, draft = render("ugc_ad_script", en(sponsored=True), {"vo_disclosure": "Thanks for watching", "text_disclosure": "Hi",
                                                                 "disclosure": "nothing", "caption": "Great shoes"})
        self.assertEqual(severity(get_format("ugc_ad_script").validate(draft), "DISCLOSURE_MISSING"), {"error"})
        sk, draft = render("ugc_ad_script", en(sponsored=True), {"vo_disclosure": "Thanks", "text_disclosure": "Hi",
                                                                 "disclosure": "x", "caption": "Great shoes #ad"})
        self.assertNotIn("DISCLOSURE_MISSING", codes(get_format("ugc_ad_script").validate(draft)))


class YoutubeScriptTests(unittest.TestCase):
    def test_plan_for_every_length(self):
        for minutes in range(5, 16):
            beats = plan_youtube(minutes)
            self.assertEqual(beats[-1]["end"], minutes * 60)
            self.assertEqual(sum(b["end"] - b["start"] for b in beats), minutes * 60)
            chapters = [b for b in beats if b["id"].startswith("ch")]
            self.assertEqual(len(chapters), 3 if minutes <= 6 else 4 if minutes <= 10 else 5, minutes)
            self.assertEqual((beats[0]["id"], beats[0]["start"], beats[0]["end"]), ("hook", 0, 30))
            self.assertEqual((beats[1]["id"], beats[1]["end"]), ("cred", 45))
            self.assertEqual(beats[-1]["id"], "cta")
            ids = [b["id"] for b in beats]
            self.assertEqual(ids.count("recap"), 1)
            self.assertEqual(ids[ids.index("recap") - 1], f"ch{math.ceil(len(chapters) / 2)}")
            self.assertTrue(all(c["end"] - c["start"] >= 30 for c in chapters))
            for b in beats:
                self.assertEqual(b["max_words"], int((b["end"] - b["start"]) * 2.6))
        self.assertEqual([b["id"] for b in plan_youtube(8)], ["hook", "cred", "ch1", "ch2", "recap", "ch3", "ch4", "cta"])
        self.assertEqual(plan_youtube(99)[-1]["end"], 900)
        self.assertEqual(plan_youtube(1)[-1]["end"], 300)

    def test_options(self):
        for given, expected in ((None, 8), (5, 5), (15, 15), (3, 5), (40, 15), ("x", 8)):
            opts = None if given is None else {"minutes": given}
            sk, draft = render("youtube_script", en(), options=opts)
            self.assertEqual(sk.fixed["minutes"], expected, given)
            self.assertEqual(draft.parts["beats"][-1]["end"], expected * 60)

    def test_structure_and_slots(self):
        sk, draft = render("youtube_script", en())
        ids = [s.id for s in sk.slots]
        self.assertEqual(sk.hook_slot, "vo_hook")
        for k in range(1, 5):
            for prefix in ("vo_ch", "title_ch", "loop_ch", "text_ch", "visual_ch"):
                self.assertIn(f"{prefix}{k}", ids)
            self.assertEqual(sk.slot(f"loop_ch{k}").max_words, 25)
            self.assertEqual(sk.slot(f"vo_ch{k}").max_words, int(90 * 2.6) - 25)
            self.assertIsNone(sk.slot(f"vo_ch{k}").default)
        self.assertIn("recap", " ".join(ids))
        self.assertIn("### 0:45-2:15 Chapter 1:", draft.body)
        title = sk.slot("title")
        self.assertLessEqual(len(title.default), 70)
        self.assertIn("running shoes for flat feet", title.default.lower())
        self.assertEqual(sk.slot("vo_hook").default, title.default)
        self.assertEqual(sk.slot("vo_hook").max_words, 78)
        self.assertEqual(sk.slot("description").must_include, ["running shoes for flat feet"])
        self.assertIn("Promise only what the video delivers", sk.slot("vo_hook").instruction)
        self.assertIn("opens a loop", sk.slot("loop_ch1").instruction)
        self.assertIn("recap and next step", sk.slot("loop_ch4").instruction)

    def test_chapters_have_increasing_timestamps(self):
        sk, draft = render("youtube_script", en(), {"title_ch1": "Fit basics", "title_ch2": "Cushioning", "title_ch3": "Drop", "title_ch4": "Budget"})
        chapters = draft.parts["chapters"]
        self.assertEqual(chapters[0], {"id": "intro", "start": 0, "timestamp": "0:00", "title": "Intro"})
        starts = [c["start"] for c in chapters]
        self.assertEqual(starts, sorted(set(starts)))
        self.assertEqual([c["id"] for c in chapters], ["intro", "ch1", "ch2", "recap", "ch3", "ch4", "cta"])
        self.assertEqual(chapters[1]["title"], "Fit basics")
        self.assertRegex(" ".join(c["timestamp"] for c in chapters), r"^(\d{1,2}:\d{2} ?)+$")
        self.assertTrue(draft.parts["chapters_text"].startswith("0:00 Intro\n0:45 Fit basics"))
        self.assertIn("Chapters:\n0:00 Intro\n0:45 Fit basics", draft.body)
        self.assertEqual(sk.fixed["chapter_times"][0]["timestamp"], "0:00")
        self.assertEqual(sk.fixed["chapter_count"], 4)

    def test_open_chapter_titles_stay_as_placeholders_in_the_description(self):
        sk, draft = render("youtube_script", en())
        self.assertIn("[[ADD: Chapter 1 title", draft.body.split("Chapters:")[1])
        self.assertIn("title_ch1", draft.slots_open)

    def test_chapter_voiceover_includes_the_open_loop(self):
        sk, draft = render("youtube_script", en(), {"vo_ch1": "Chapter one script.", "loop_ch1": "But what about cushioning?"})
        beat = next(b for b in draft.parts["beats"] if b["id"] == "ch1")
        self.assertEqual(beat["voiceover"], "Chapter one script. But what about cushioning?")

    def test_czech_labels(self):
        sk, draft = render("youtube_script", cs())
        self.assertEqual(draft.parts["chapters"][0]["title"], "Úvod")
        self.assertIn("Kapitoly:", draft.body)
        self.assertIn("Scénář pro YouTube", draft.body)
        self.assertEqual(draft.parts["beats"][0]["label"], "Úvodní hook")
        self.assertEqual(sk.slot("vo_hook").max_words, int(30 * 2.4))

    def test_sponsored_adds_a_description_disclosure(self):
        sk, draft = render("youtube_script", en(sponsored=True))
        self.assertEqual(draft.parts["slots"]["disclosure"], "#ad")
        self.assertNotIn("DISCLOSURE_MISSING", codes(get_format("youtube_script").validate(draft)))
        sk, draft = render("youtube_script", en(sponsored=True), {"disclosure": "hello"})
        self.assertEqual(severity(get_format("youtube_script").validate(draft), "DISCLOSURE_MISSING"), {"error"})

    def test_validator_on_the_offline_draft(self):
        found = check("youtube_script", en())
        self.assertEqual([i for i in found if i.severity != "info"], [])

    def test_validator_catches_broken_chapters_and_metadata(self):
        spec = get_format("youtube_script")
        sk, draft = render("youtube_script", en(), {"title_ch1": "A", "title_ch2": "B", "title_ch3": "C", "title_ch4": "D"})
        draft.parts["chapters"] = draft.parts["chapters"][:2]
        self.assertEqual(severity(spec.validate(draft), "CHAPTERS"), {"error"})
        sk, draft = render("youtube_script", en())
        draft.parts["chapters"][0]["start"] = 5
        self.assertIn("CHAPTERS", codes(spec.validate(draft)))
        sk, draft = render("youtube_script", en())
        draft.parts["chapters"][2]["start"] = draft.parts["chapters"][1]["start"]
        self.assertIn("CHAPTERS", codes(spec.validate(draft)))
        sk, draft = render("youtube_script", en())
        draft.parts["chapters"][1]["start"] = draft.parts["chapters"][0]["start"] + 5
        self.assertIn("CHAPTERS", codes(spec.validate(draft)))
        sk, draft = render("youtube_script", en())
        draft.parts["chapters"][1]["timestamp"] = "1h05"
        self.assertIn("CHAPTERS", codes(spec.validate(draft)))
        found = check("youtube_script", en(), {"title": "t" * 80})
        self.assertEqual(severity(found, "TITLE_LONG"), {"warn"})
        found = check("youtube_script", en(), {"title": "t" * 101})
        self.assertEqual(severity(found, "CHAR_LIMIT"), {"error"})
        found = check("youtube_script", en(), {"description": "A description without the phrase."})
        self.assertEqual(severity(found, "KEYWORD_MISSING"), {"warn"})
        found = check("youtube_script", en(), {"description": "Everything about running shoes for flat feet."})
        self.assertNotIn("KEYWORD_MISSING", codes(found))
        found = check("youtube_script", en(), {"description": "x" * 1600})
        self.assertEqual(severity(found, "CHAR_LIMIT"), {"error"})
        found = check("youtube_script", en(), {"title_ch1": "t" * 70})
        self.assertEqual(severity(found, "CHAPTER_TITLE_LONG"), {"warn"})

    def test_budget_checks_use_the_chapter_budget(self):
        found = check("youtube_script", en(), {"vo_ch1": " ".join(["w"] * 400)})
        self.assertIn("WORDS_OVER_BUDGET", codes(found))
        found = check("youtube_script", en(), {"vo_ch1": " ".join(["w"] * 150), "loop_ch1": "Next?"})
        self.assertNotIn("WORDS_OVER_BUDGET", codes(found))


class BeatValidatorTests(unittest.TestCase):
    SPEC = "short_video_script"

    def draft(self, **fills):
        return render(self.SPEC, en(), fills)[1]

    def test_clean_filled_script_has_no_warnings(self):
        sk = build_skeleton(self.SPEC, en())
        fills = fill_all_voiceovers(sk, 2.0)
        for b in sk.fixed["plan"]:
            fills[f"text_{b['id']}"] = "Short text"
            fills[f"visual_{b['id']}"] = "Shot"
        fills["caption"] = "A caption"
        draft = sk.render({**OfflineWriter().fill(sk, en()), **fills})
        self.assertEqual(get_format(self.SPEC).validate(draft), [])

    def test_word_budget_thresholds(self):
        spec = get_format(self.SPEC)
        budget = 7
        for words, expected in ((7, set()), (8, {"warn"}), (9, {"warn"}), (10, {"error"}), (15, {"error"})):
            draft = self.draft(vo_hook=" ".join(["w"] * words))
            found = [i for i in spec.validate(draft) if i.code == "WORDS_OVER_BUDGET"]
            self.assertEqual({i.severity for i in found}, expected, words)
            if found:
                self.assertEqual(found[0].where, "hook")
        self.assertGreater(8, budget * 1.1)
        self.assertLessEqual(9, budget * 1.4)
        self.assertGreater(10, budget * 1.4)

    def test_hook_beat_length(self):
        draft = self.draft()
        draft.parts["beats"][0]["end"] = 5
        self.assertEqual(severity(get_format(self.SPEC).validate(draft), "HOOK_BEAT_LONG"), {"error"})
        self.assertIn("TIMELINE_BROKEN", codes(get_format(self.SPEC).validate(draft)))

    def test_cta_beat_must_exist_and_be_last(self):
        spec = get_format(self.SPEC)
        draft = self.draft()
        draft.parts["beats"] = draft.parts["beats"][:-1]
        self.assertEqual(severity(spec.validate(draft), "CTA_BEAT_MISSING"), {"error"})
        draft = self.draft()
        beats = draft.parts["beats"]
        beats[-1], beats[-2] = beats[-2], beats[-1]
        self.assertEqual(severity(spec.validate(draft), "CTA_BEAT_NOT_LAST"), {"error"})
        draft = self.draft()
        draft.parts["beats"] = []
        self.assertEqual(codes(spec.validate(draft)), {"NO_BEATS"})

    def test_duration_must_match(self):
        draft = self.draft()
        draft.meta["duration_s"] = 45
        self.assertEqual(severity(get_format(self.SPEC).validate(draft), "DURATION_MISMATCH"), {"error"})

    def test_on_screen_text_length(self):
        found = get_format(self.SPEC).validate(self.draft(text_hook="one two three four five six seven"))
        self.assertEqual(severity(found, "ONSCREEN_TEXT_LONG"), {"warn"})
        found = get_format(self.SPEC).validate(self.draft(text_hook="one two three four five six"))
        self.assertNotIn("ONSCREEN_TEXT_LONG", codes(found))

    def test_srt_well_formedness(self):
        spec = get_format(self.SPEC)
        draft = self.draft(vo_problem="A short problem statement here.")
        self.assertNotIn("SRT_MALFORMED", codes(spec.validate(draft)))
        good = draft.parts["srt"]
        for bad in ("garbage", good.replace("00:00:00,000", "00:00:00;000", 1)):
            draft.parts["srt"] = bad
            self.assertEqual(severity(spec.validate(draft), "SRT_MALFORMED"), {"error"}, bad)
        draft.parts["srt"] = "1\n00:00:00,000 --> 00:00:02,000\nhello there\n\n2\n00:00:01,000 --> 00:00:03,000\nagain here\n"
        self.assertIn("overlaps", " ".join(i.message for i in spec.validate(draft)))
        draft.parts["srt"] = "1\n00:00:00,000 --> 00:00:01,000\none two three four five six seven eight\n"
        self.assertIn("SRT_MALFORMED", codes(spec.validate(draft)))
        draft.parts["srt"] = "1\n00:00:00,000 --> 00:00:01,000\na\nb\nc\n"
        self.assertIn("SRT_MALFORMED", codes(spec.validate(draft)))
        draft.parts["srt"] = "1\n00:00:00,000 --> 00:00:04,000\nruns past the hook beat\n"
        self.assertIn("beat window", " ".join(i.message for i in spec.validate(draft)))
        draft.parts["srt"] = "2\n00:00:00,000 --> 00:00:01,000\nwrong index\n"
        self.assertIn("SRT_MALFORMED", codes(spec.validate(draft)))
        draft.parts["srt"] = "1\n00:00:02,000 --> 00:00:01,000\nbackwards\n"
        self.assertIn("SRT_MALFORMED", codes(spec.validate(draft)))

    def test_visual_cadence_and_pattern_interrupt(self):
        spec = get_format(self.SPEC)
        draft = self.draft()
        for b in draft.parts["beats"]:
            b["visual_changes"] = b["visual_changes"][:1]
        self.assertEqual(severity(spec.validate(draft), "VISUAL_CADENCE"), {"warn"})
        draft = self.draft()
        draft.parts["beats"][0]["pattern_interrupt"] = False
        self.assertEqual(severity(spec.validate(draft), "PATTERN_INTERRUPT_MISSING"), {"warn"})

    def test_open_placeholders_are_info_for_video(self):
        found = get_format(self.SPEC).validate(self.draft())
        opened = [i for i in found if i.code == "SLOTS_OPEN"]
        self.assertEqual([i.severity for i in opened], ["info"])
        self.assertEqual(severity(validate_draft(self.draft()), "SLOTS_OPEN"), {"info"})

    def test_sponsored_video_needs_a_disclosure(self):
        spec = get_format(self.SPEC)
        sk, draft = render(self.SPEC, en(sponsored=True), {"vo_disclosure": "Hello", "text_disclosure": "Hi", "caption": "Nice", "disclosure": "x"})
        self.assertEqual(severity(spec.validate(draft), "DISCLOSURE_MISSING"), {"error"})
        sk, draft = render(self.SPEC, en(sponsored=True), {"vo_disclosure": "Hello", "text_disclosure": "Hi", "caption": "Nice #sponsored", "disclosure": "x"})
        self.assertNotIn("DISCLOSURE_MISSING", codes(spec.validate(draft)))
        sk, draft = render(self.SPEC, cs(sponsored=True), {"vo_disclosure": "Hello", "text_disclosure": "Hi", "caption": "Nice", "disclosure": "Reklama"})
        self.assertNotIn("DISCLOSURE_MISSING", codes(spec.validate(draft)))


class TitleSetTests(unittest.TestCase):
    def test_ten_titles_ranked_by_score(self):
        for brief in (en(), cs(), en(keyword=None, facts=[]), cs(topic_forms={})):
            sk, draft = render("youtube_title_set", brief)
            slots = [s for s in sk.slots if s.id.startswith("title_")]
            self.assertEqual(len(slots), 10)
            self.assertTrue(all(s.max_chars == 70 and s.default and len(s.default) <= 70 for s in slots), brief.lang)
            scores = [t["score"] for t in sk.fixed["titles"]]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertEqual([t["text"] for t in sk.fixed["titles"]], [s.default for s in slots])
            self.assertEqual(draft.hook, slots[0].default)
            self.assertEqual(sk.hook_slot, "title_01")
            self.assertEqual(len(set(s.default for s in slots)), 10)

    def test_hook_argument_is_pinned_to_the_first_title(self):
        sk = build_skeleton("youtube_title_set", en(), hook="My own title")
        self.assertEqual(sk.slot("title_01").default, "My own title")
        self.assertEqual(sk.fixed["titles"][0]["style"], "provided")
        self.assertEqual(len(sk.fixed["titles"]), 10)
        rest = [t["score"] for t in sk.fixed["titles"][1:]]
        self.assertEqual(rest, sorted(rest, reverse=True))

    def test_four_thumbnail_texts_and_a_concept_slot(self):
        for brief in (en(), cs()):
            sk, draft = render("youtube_title_set", brief)
            thumbs = [s for s in sk.slots if s.id.startswith("thumb_")]
            self.assertEqual(len(thumbs), 4)
            self.assertTrue(all(s.max_words == 4 and s.default and len(s.default.split()) <= 4 for s in thumbs))
            scores = [t["score"] for t in sk.fixed["thumbnail_texts"]]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertEqual(sk.slot("thumbnail_concept").default, None)
            self.assertEqual(draft.slots_open, ["thumbnail_concept"])
            self.assertIn("{{thumbnail_concept}}", sk.template)
        self.assertTrue(all(t.isascii() for t in [s.default for s in build_skeleton("youtube_title_set", en()).slots if s.id.startswith("thumb_")]))
        self.assertIn("Koncept náhledu", render("youtube_title_set", cs())[1].body)

    def test_thumbnail_phrases_fit_the_limit(self):
        for lang_phrases in (video._THUMB_EN, video._THUMB_CS):
            for phrase in lang_phrases:
                self.assertLessEqual(len(phrase.format(n=7).split()), 4, phrase)
                self.assertNotIn(chr(0x2014), phrase)

    def test_validator(self):
        spec = get_format("youtube_title_set")
        found = check("youtube_title_set", en(), {"title_03": "t" * 71})
        self.assertEqual(severity(found, "CHAR_LIMIT"), {"error"})
        found = check("youtube_title_set", en(), {"title_02": "Same title", "title_03": "same title"})
        self.assertEqual(severity(found, "TITLE_DUPLICATE"), {"warn"})
        found = check("youtube_title_set", en(), {"title_02": "You won't BELIEVE this one trick"})
        self.assertEqual(severity(found, "CLICKBAIT_RISK"), {"warn"})
        found = check("youtube_title_set", en(), {"thumb_2": "this is way too many words"})
        self.assertEqual(severity(found, "THUMB_TEXT_LONG"), {"error"})
        self.assertEqual([i for i in check("youtube_title_set", en()) if i.severity == "error"], [])
        self.assertTrue(spec.limits["titles"] == 10)


class PodcastTests(unittest.TestCase):
    def test_plan(self):
        beats = plan_podcast(30, 3)
        self.assertEqual([b["id"] for b in beats], ["cold_open", "intro", "seg1", "seg2", "seg3", "outro"])
        self.assertEqual([(b["start"], b["end"]) for b in beats][:2], [(0, 60), (60, 180)])
        self.assertEqual(beats[-1]["end"], 1800)
        for a, b in zip(beats, beats[1:]):
            self.assertEqual(a["end"], b["start"])
        self.assertEqual({b["end"] - b["start"] for b in beats if b["id"].startswith("seg")}, {500})
        self.assertEqual(beats[2]["timestamp"], "3:00")
        self.assertEqual(len(plan_podcast(45, 4)), 7)
        self.assertEqual(plan_podcast(5, 1)[-1]["end"], 900)
        self.assertEqual(len([b for b in plan_podcast(60, 9) if b["id"].startswith("seg")]), 4)

    def test_builder(self):
        sk, draft = render("podcast_outline", en())
        self.assertEqual(sk.fixed["minutes"], 30)
        self.assertEqual(len(draft.parts["segments"]), 3)
        self.assertEqual(draft.parts["segments"][0]["timestamp"], "3:00")
        self.assertEqual(len(draft.parts["questions"]), 5)
        ids = [s.id for s in sk.slots]
        for q in range(1, 6):
            self.assertIn(f"q_{q}", ids)
            self.assertEqual(sk.slot(f"q_{q}").max_words, 25)
        self.assertEqual(sk.slot("show_notes").must_include, ["running shoes for flat feet"])
        self.assertEqual(sk.hook_slot, "vo_hook")
        self.assertEqual(sk.slot("vo_hook").max_words, 156)
        self.assertEqual(sk.slot("cta").default, "Download the free fit guide")
        self.assertIn("0:00-1:00 Cold open", draft.body)
        self.assertIn("## 3:00-11:20 Segment 1:", draft.body)
        self.assertEqual(sorted(draft.slots_open)[0], "q_1")

    def test_options(self):
        for given, expected in ((4, 4), (2, 3), (9, 4)):
            _, draft = render("podcast_outline", en(), options={"segments": given})
            self.assertEqual(len(draft.parts["segments"]), expected)
        _, draft = render("podcast_outline", en(), options={"minutes": 60})
        self.assertEqual(draft.parts["plan"][-1]["end"], 3600)
        _, draft = render("podcast_outline", en(), options={"minutes": "x", "segments": "y"})
        self.assertEqual(draft.parts["plan"][-1]["end"], 1800)

    def test_czech_and_sponsored(self):
        sk, draft = render("podcast_outline", cs(sponsored=True))
        self.assertIn("Osnova podcastu", draft.body)
        self.assertEqual(sk.slot("disclosure").default, "Sponzorováno značkou Zorvia.")
        self.assertEqual(sk.slot("vo_hook").max_words, int(60 * 2.4))
        self.assertNotIn("DISCLOSURE_MISSING", codes(get_format("podcast_outline").validate(draft)))
        sk, draft = render("podcast_outline", en(sponsored=True), {"disclosure": "hello", "show_notes": "notes", "vo_intro": "intro", "cta": "go"})
        self.assertEqual(severity(get_format("podcast_outline").validate(draft), "DISCLOSURE_MISSING"), {"error"})

    def test_validator(self):
        spec = get_format("podcast_outline")
        found = check("podcast_outline", en())
        self.assertEqual([i.severity for i in found if i.code == "SLOTS_OPEN"], ["info"])
        self.assertEqual([i for i in found if i.severity == "error"], [])
        found = check("podcast_outline", en(), {"q_1": "Tell me about shoes", "q_2": "Why?"})
        self.assertEqual(severity(found, "QUESTION_FORM"), {"warn"})
        found = check("podcast_outline", en(), {"q_1": "Why?", "q_2": "why?"})
        self.assertEqual(severity(found, "QUESTION_DUPLICATE"), {"warn"})
        found = check("podcast_outline", en(), {"q_1": " ".join(["word"] * 30) + "?"})
        self.assertEqual(severity(found, "QUESTION_LONG"), {"warn"})
        found = check("podcast_outline", en(), {"show_notes": "Nothing relevant here."})
        self.assertEqual(severity(found, "KEYWORD_MISSING"), {"warn"})
        found = check("podcast_outline", en(), {"show_notes": "x" * 1600})
        self.assertEqual(severity(found, "CHAR_LIMIT"), {"error"})
        found = check("podcast_outline", en(), {"vo_hook": " ".join(["w"] * 230)})      # budget 156, error above 218
        self.assertEqual(severity(found, "WORDS_OVER_BUDGET"), {"error"})
        found = check("podcast_outline", en(), {"vo_hook": " ".join(["w"] * 180)})      # warn above 171
        self.assertEqual(severity(found, "WORDS_OVER_BUDGET"), {"warn"})
        found = check("podcast_outline", en(), {"vo_hook": " ".join(["w"] * 165)})
        self.assertNotIn("WORDS_OVER_BUDGET", codes(found))
        sk, draft = render("podcast_outline", en())
        draft.parts["segments"] = draft.parts["segments"][:2]
        self.assertEqual(severity(spec.validate(draft), "SEGMENT_COUNT"), {"error"})
        sk, draft = render("podcast_outline", en())
        draft.parts["plan"][3]["start"] += 5
        self.assertEqual(severity(spec.validate(draft), "TIMELINE_BROKEN"), {"error"})
        sk, draft = render("podcast_outline", en())
        draft.meta["duration_s"] = 1700
        self.assertEqual(severity(spec.validate(draft), "DURATION_MISMATCH"), {"error"})
        sk, draft = render("podcast_outline", en())
        draft.parts["questions"] = draft.parts["questions"][:3]
        self.assertEqual(severity(spec.validate(draft), "QUESTION_COUNT"), {"warn"})


class VideoFamilyTests(unittest.TestCase):
    def test_every_video_format_has_family_and_limits(self):
        for fid in VIDEO_IDS:
            spec = get_format(fid)
            self.assertIn(spec.family, ("video", "audio"))
            self.assertTrue(spec.limits)
        self.assertEqual(get_format("podcast_outline").family, "audio")
        self.assertEqual(get_format("youtube_script").platform, "youtube")

    def test_video_output_never_contains_the_long_dash(self):
        for fid in VIDEO_IDS:
            for brief in (en(), cs(sponsored=True)):
                _, draft = render(fid, brief)
                self.assertNotIn(chr(0x2014), draft.body)
                self.assertNotIn(chr(0x2014), str(draft.parts.get("timeline_md", "")))
                self.assertFalse([i for i in validate_draft(draft) if i.code == "EM_DASH"])

    def test_offline_video_drafts_report_only_info(self):
        for fid in ("short_video_script", "youtube_script", "ugc_ad_script", "podcast_outline"):
            for brief in (en(), cs()):
                _, draft = render(fid, brief)
                severities = {i.severity for i in validate_draft(draft)}
                self.assertEqual(severities, {"info"}, (fid, brief.lang))


if __name__ == "__main__":
    unittest.main()
