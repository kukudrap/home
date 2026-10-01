import json
import re
import types
import unittest
from unittest import mock

from dopamine_king.generate import formats
from dopamine_king.generate.formats import (
    BUILTIN_MODULES, EM_DASH, all_formats, build_skeleton, caps_words,
    emoji_count, engagement_bait, fit, formats_by_module, generic_checks, get_format, has_cta, has_disclosure,
    hashtags_in, keyword_in, list_formats, record_replaced_hook, strip_placeholders, to_hashtag, topic_hashtags, validate_draft,
    word_count,
)
from dopamine_king.generate.types import SLOT_RE, Brief, Draft, FormatSpec, OfflineWriter, Skeleton, Slot

FAMILIES = {"article", "social", "video", "ad", "email", "audio", "hooks"}
MY_MODULES = ("hooks", "social", "video", "ads")
CS_FORMS = {"gen": "běžeckých bot", "dat": "běžeckým botám", "acc": "běžecké boty", "loc": "běžeckých botách",
            "ins": "běžeckými botami"}


def briefs():
    return {
        "en_full": Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="best running shoes for flat feet",
                         cta="Download the free fit guide", offer="Free fit consultation", secondary_keywords=["flat feet shoes"],
                         facts=["Tested by 1,200 runners over 6 months"]),
        "en_plain": Brief(brand="Zorvia", topic="running shoes", audience="beginner runners"),
        "en_sponsored": Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", sponsored=True, cta="Shop now"),
        "cs_full": Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", keyword="běžecké boty pro ploché nohy",
                         cta="Stáhněte si průvodce výběrem", offer="Poradenství zdarma", topic_forms=dict(CS_FORMS),
                         facts=["Otestovalo je 1 200 běžců"]),
        "cs_plain": Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs"),
        "cs_sponsored": Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", sponsored=True),
    }


def render_offline(format_id, brief, **kw):
    sk = build_skeleton(format_id, brief, **kw)
    return sk, sk.render(OfflineWriter().fill(sk, brief))


class RegistryTests(unittest.TestCase):
    def test_builtin_modules_and_unique_ids(self):
        self.assertEqual(BUILTIN_MODULES, ("hooks", "social", "video", "ads", "seo", "geo", "longform"))
        specs = all_formats()
        by_module = formats_by_module()
        flat = [i for ids in by_module.values() for i in ids]
        self.assertEqual(len(flat), len(set(flat)))
        self.assertEqual(list(specs), flat)
        for key, spec in specs.items():
            self.assertEqual(key, spec.id)

    def test_formats_of_this_slice(self):
        by_module = formats_by_module()
        self.assertEqual(by_module["hooks"], ["hook_set"])
        self.assertEqual(set(by_module["social"]), {
            "linkedin_post", "linkedin_carousel", "x_post", "x_thread", "instagram_caption", "instagram_carousel", "facebook_post",
            "threads_post", "pinterest_pin", "youtube_community_post", "reddit_answer", "google_business_post"})
        self.assertEqual(set(by_module["video"]), {"short_video_script", "youtube_script", "ugc_ad_script", "youtube_title_set", "podcast_outline"})
        self.assertEqual(set(by_module["ads"]), {"google_rsa", "meta_ad", "linkedin_ad", "email_subject_set"})

    def test_every_spec_is_complete(self):
        for spec in all_formats().values():
            self.assertIsInstance(spec, FormatSpec)
            self.assertTrue(spec.name_en.strip() and spec.name_cs.strip(), spec.id)
            self.assertNotEqual(spec.name_en, spec.name_cs + "x")
            self.assertIn(spec.family, FAMILIES, spec.id)
            self.assertTrue(spec.platform.strip(), spec.id)
            self.assertTrue(callable(spec.build) and callable(spec.validate), spec.id)
            self.assertTrue(re.fullmatch(r"[a-z0-9_]+", spec.id), spec.id)

    def test_my_specs_describe_themselves_in_both_languages(self):
        for module in MY_MODULES:
            for fid in formats_by_module()[module]:
                spec = get_format(fid)
                self.assertTrue(spec.description_en.strip() and spec.description_cs.strip(), fid)
                self.assertTrue(spec.limits, fid)
                self.assertNotIn(EM_DASH, spec.name_en + spec.name_cs + spec.description_en + spec.description_cs)

    def test_czech_names_use_diacritics_where_needed(self):
        self.assertEqual(get_format("hook_set").name_cs, "Sada hooků")
        self.assertIn("příspěvek", get_format("linkedin_post").name_cs.lower())

    def test_missing_builtin_module_is_skipped(self):
        with mock.patch.object(formats, "BUILTIN_MODULES", ("hooks", "does_not_exist_zz")):
            self.assertEqual(list(all_formats()), ["hook_set"])

    def test_missing_dependency_inside_a_module_is_not_swallowed(self):
        real = formats.importlib.import_module

        def fake(name, *a, **k):
            if name.endswith(".social"):
                raise ModuleNotFoundError("No module named 'zzz_dep'", name="zzz_dep")
            return real(name, *a, **k)

        with mock.patch.object(formats, "BUILTIN_MODULES", ("hooks", "social")), \
                mock.patch.object(formats.importlib, "import_module", side_effect=fake):
            with self.assertRaises(ModuleNotFoundError):
                all_formats()

    def test_duplicate_ids_raise(self):
        spec = FormatSpec("dup_id", "A", "B", "social", "x", build=lambda *a, **k: None, validate=lambda d: [])
        mods = {"a": types.SimpleNamespace(FORMAT_SPECS=[spec]), "b": types.SimpleNamespace(FORMAT_SPECS=[spec])}

        def fake(name, *a, **k):
            return mods[name.rsplit(".", 1)[1]]

        with mock.patch.object(formats, "BUILTIN_MODULES", ("a", "b")), mock.patch.object(formats.importlib, "import_module", side_effect=fake):
            with self.assertRaises(ValueError) as ctx:
                all_formats()
        self.assertIn("dup_id", str(ctx.exception))

    def test_get_format_error_lists_valid_ids(self):
        with self.assertRaises(KeyError) as ctx:
            get_format("no_such_format")
        message = str(ctx.exception)
        for fid in ("hook_set", "linkedin_post", "google_rsa", "short_video_script"):
            self.assertIn(fid, message)
        self.assertEqual(get_format("x_post").id, "x_post")

    def test_list_formats_by_family(self):
        self.assertEqual([s.id for s in list_formats("hooks")], ["hook_set"])
        social = {s.id for s in list_formats("social")}
        self.assertTrue(set(formats_by_module()["social"]) <= social)
        self.assertEqual(len(list_formats()), len(all_formats()))
        self.assertEqual(list_formats("no-such-family"), [])
        self.assertTrue({"google_rsa", "meta_ad", "linkedin_ad"} <= {s.id for s in list_formats("ad")})
        self.assertIn("email_subject_set", {s.id for s in list_formats("email")})
        self.assertIn("podcast_outline", {s.id for s in list_formats("audio")})


class BuildEverythingTests(unittest.TestCase):
    def test_every_registered_format_builds_and_renders_offline(self):
        for fid, spec in all_formats().items():
            for name, brief in briefs().items():
                with self.subTest(format=fid, brief=name):
                    sk, draft = render_offline(fid, brief)
                    self.assertEqual(draft.format, fid)
                    self.assertEqual(draft.lang, brief.lang)
                    self.assertTrue(draft.body.strip())
                    self.assertNotIn("{{", draft.body)
                    self.assertTrue(draft.hook.strip())
                    self.assertTrue(set(draft.slots_open) <= {s.id for s in sk.slots})
                    for key in ("goal", "cta", "sponsored", "keyword"):
                        self.assertIn(key, draft.meta)
                    self.assertEqual(draft.meta["sponsored"], brief.sponsored)
                    self.assertIn(draft.meta["keyword"], (brief.keyword, brief.primary_keyword))
                    self.assertIsInstance(validate_draft(draft), list)

    def test_drafts_serialise_to_json(self):
        for module in MY_MODULES:
            for fid in formats_by_module()[module]:
                for name in ("en_full", "cs_sponsored"):
                    _, draft = render_offline(fid, briefs()[name])
                    restored = Draft.from_dict(json.loads(json.dumps(draft.to_dict())))
                    self.assertEqual(restored.body, draft.body, fid)
                    self.assertEqual(restored.parts.get("slots"), draft.parts.get("slots"), fid)

    def test_hook_argument_becomes_the_hook_slot_default(self):
        for fid in formats_by_module()["social"] + formats_by_module()["ads"] + formats_by_module()["video"]:
            if fid in ("google_rsa", "reddit_answer"):
                continue
            with self.subTest(format=fid):
                sk = build_skeleton(fid, briefs()["en_plain"], hook="My custom hook")
                self.assertEqual(sk.slot(sk.hook_slot).default, "My custom hook")
                self.assertEqual(sk.render({}).hook, "My custom hook")

    def test_hook_argument_for_rsa_and_reddit(self):
        sk = build_skeleton("google_rsa", briefs()["en_plain"], hook="Short hook")
        self.assertEqual(sk.slot("h01").default, "Short hook")
        long = build_skeleton("google_rsa", briefs()["en_plain"], hook="This hook is much too long for a headline")
        self.assertNotEqual(long.slot("h01").default, "This hook is much too long for a headline")
        sk = build_skeleton("reddit_answer", briefs()["en_plain"], hook="Use a wider toe box.")
        self.assertEqual(sk.slot("direct_answer").default, "Use a wider toe box.")

    def test_a_hook_that_does_not_fit_is_replaced_and_recorded(self):
        too_long = {
            "x_post": "word " * 30, "short_video_script": "one two three four five six seven eight nine ten",
            "ugc_ad_script": "one two three four five six seven eight nine ten", "linkedin_carousel": "one two three four five six seven eight nine ten",
            "instagram_carousel": "word " * 13, "facebook_post": "word " * 16, "email_subject_set": "Subject " * 8,
            "youtube_title_set": "Title " * 14, "meta_ad": "word " * 30, "google_rsa": "A headline that is too long to fit",
            "reddit_answer": "Answer " * 50, "pinterest_pin": "Pin " * 30, "google_business_post": "word " * 20,
        }
        for fid, hook in too_long.items():
            hook = hook.strip()
            with self.subTest(format=fid):
                sk = build_skeleton(fid, briefs()["en_plain"], hook=hook)
                slot = sk.slot(sk.hook_slot)
                self.assertNotEqual(slot.default, hook)
                self.assertEqual(sk.fixed["hook_requested"], hook)
                self.assertTrue(any("does not fit the hook slot" in n for n in sk.notes))
                if slot.max_chars is not None and slot.default:
                    self.assertLessEqual(len(slot.default), slot.max_chars)
                if slot.max_words is not None and slot.default:
                    self.assertLessEqual(len(slot.default.split()), slot.max_words)
                _, draft = render_offline(fid, briefs()["en_plain"], hook=hook)
                self.assertEqual([i for i in validate_draft(draft) if i.severity == "error"], [])

    def test_a_fitting_hook_is_kept_without_a_note(self):
        for fid in ("x_post", "short_video_script", "email_subject_set", "linkedin_carousel", "meta_ad", "youtube_script"):
            sk = build_skeleton(fid, briefs()["en_plain"], hook="Fits everywhere")
            self.assertNotIn("hook_requested", sk.fixed, fid)
            self.assertFalse(any("does not fit" in n for n in sk.notes), fid)

    def test_record_replaced_hook_helper(self):
        slot = Slot("hook", "x", default="Library hook")
        sk = Skeleton("f", "en", "{{hook}}", [slot])
        self.assertIs(record_replaced_hook(sk, None), sk)
        self.assertNotIn("hook_requested", sk.fixed)
        record_replaced_hook(sk, "  Library hook ")
        self.assertNotIn("hook_requested", sk.fixed)
        record_replaced_hook(sk, "Something else")
        self.assertEqual(sk.fixed["hook_requested"], "Something else")
        self.assertEqual(len(sk.notes), 1)
        empty = Skeleton("f", "en", "text", [])
        self.assertEqual(record_replaced_hook(empty, "x").fixed, {})

    def test_slot_and_template_consistency_in_this_slice(self):
        for module in MY_MODULES:
            for fid in formats_by_module()[module]:
                for name in ("en_full", "cs_plain", "en_sponsored"):
                    with self.subTest(format=fid, brief=name):
                        sk = build_skeleton(fid, briefs()[name])
                        ids = [s.id for s in sk.slots]
                        self.assertEqual(len(ids), len(set(ids)))
                        for sid in ids:
                            self.assertRegex(sid, r"^[a-z0-9_]+$")
                        used = set(SLOT_RE.findall(sk.template))
                        self.assertEqual(used, set(ids))
                        if sk.slots:
                            self.assertIn(sk.hook_slot, ids)
                        for s in sk.slots:
                            self.assertTrue(s.instruction.strip())
                            self.assertEqual(s.instruction, " ".join(s.instruction.split()))

    def test_defaults_respect_their_slot_limits(self):
        for module in MY_MODULES:
            for fid in formats_by_module()[module]:
                for name, brief in briefs().items():
                    sk = build_skeleton(fid, brief)
                    for s in sk.slots:
                        if s.default is None:
                            continue
                        with self.subTest(format=fid, brief=name, slot=s.id):
                            if s.max_chars is not None:
                                self.assertLessEqual(len(s.default), s.max_chars)
                            if s.max_words is not None:
                                self.assertLessEqual(len(s.default.split()), s.max_words)
                            if s.min_chars is not None and s.default:
                                self.assertGreaterEqual(len(s.default), s.min_chars)

    def test_this_slice_never_writes_the_long_dash(self):
        for module in MY_MODULES:
            for fid in formats_by_module()[module]:
                for brief in briefs().values():
                    sk, draft = render_offline(fid, brief)
                    blob = " ".join([draft.body, draft.hook, " ".join(draft.notes), sk.template]
                                    + [s.instruction + (s.default or "") for s in sk.slots])
                    self.assertNotIn(EM_DASH, blob, fid)
                    self.assertFalse([i for i in validate_draft(draft) if i.code == "EM_DASH"], fid)

    def test_offline_drafts_have_no_errors_for_clean_briefs(self):
        for module in MY_MODULES:
            for fid in formats_by_module()[module]:
                for name in ("en_full", "cs_full", "en_plain", "cs_plain", "en_sponsored", "cs_sponsored"):
                    _, draft = render_offline(fid, briefs()[name])
                    errors = [i for i in validate_draft(draft) if i.severity == "error"]
                    self.assertEqual(errors, [], (fid, name))

    def test_notes_carry_language_and_integrity_guidance(self):
        sk = build_skeleton("linkedin_post", briefs()["cs_plain"])
        self.assertIn("Write all prose in Czech.", sk.notes)
        self.assertTrue(any("do not add statistics" in n for n in sk.notes))
        sk = build_skeleton("linkedin_post", briefs()["en_full"])
        self.assertTrue(any("Tested by 1,200 runners" in n for n in sk.notes))


class HookSetTests(unittest.TestCase):
    def test_hook_set_structure(self):
        sk, draft = render_offline("hook_set", briefs()["en_full"], options={"n": 6})
        self.assertEqual(sk.slots, [])
        hooks = draft.parts["hooks"]
        self.assertEqual(len(hooks), 6)
        self.assertEqual([h["score"] for h in hooks], sorted((h["score"] for h in hooks), reverse=True))
        self.assertEqual(set(hooks[0]), {"text", "style", "score", "risk"})
        for i, h in enumerate(hooks, 1):
            self.assertIn(f"{i}. **{h['text']}**", draft.body)
        self.assertEqual(draft.hook, hooks[0]["text"])
        self.assertEqual(draft.slots_open, [])
        self.assertEqual(validate_draft(draft), [])

    def test_hook_set_options_and_czech(self):
        _, draft = render_offline("hook_set", briefs()["cs_full"], options={"n": 4, "styles": ["myth_bust"]})
        self.assertEqual({h["style"] for h in draft.parts["hooks"]}, {"myth_bust"})
        self.assertIn("Sada hooků", draft.body)
        self.assertIn("Skóre", draft.body)
        _, draft = render_offline("hook_set", briefs()["en_plain"], options={"n": 50})
        self.assertLessEqual(len(draft.parts["hooks"]), 36)
        _, draft = render_offline("hook_set", briefs()["en_plain"], options={"max_chars": 30, "n": 5})
        self.assertTrue(all(len(h["text"]) <= 30 for h in draft.parts["hooks"]))

    def test_hook_set_includes_a_provided_hook(self):
        _, draft = render_offline("hook_set", briefs()["en_plain"], hook="My own opening line", options={"n": 3})
        texts = [h["text"] for h in draft.parts["hooks"]]
        self.assertIn("My own opening line", texts)
        self.assertEqual(len(texts), 3)
        self.assertIn("provided", [h["style"] for h in draft.parts["hooks"]])

    def test_hook_set_validator(self):
        spec = get_format("hook_set")
        empty = Draft("hook_set", "en", "", "x", parts={"hooks": []})
        self.assertEqual(spec.validate(empty)[0].code, "HOOKS_EMPTY")
        bad = Draft("hook_set", "en", "a", "x", parts={"hooks": [
            {"text": "Same hook", "style": "q", "score": 10, "risk": 0.0},
            {"text": "same  hook", "style": "q", "score": 20, "risk": 0.9},
            {"text": "x" * 150, "style": "q", "score": 5, "risk": 0.0}]})
        codes = {i.code for i in spec.validate(bad)}
        self.assertTrue({"HOOK_DUPLICATE", "HOOK_RISK", "HOOK_LONG", "HOOKS_UNSORTED"} <= codes)


class GenericCheckTests(unittest.TestCase):
    def draft(self, body="Fine text", **kw):
        base = dict(format="x_post", lang="en", hook="Fine", body=body, parts={"slots": {}}, meta={}, slots_open=[])
        base.update(kw)
        return Draft(**base)

    def codes(self, draft):
        return {(i.severity, i.code) for i in generic_checks(draft)}

    def test_clean_draft_has_no_issues(self):
        self.assertEqual(generic_checks(self.draft()), [])

    def test_open_slots_warn_and_list_ids(self):
        issues = generic_checks(self.draft(slots_open=["a", "b_2"]))
        self.assertEqual(issues[0].code, "SLOTS_OPEN")
        self.assertEqual(issues[0].severity, "warn")
        self.assertIn("a, b_2", issues[0].message)

    def test_leftover_placeholder_is_an_error(self):
        self.assertIn(("error", "UNRESOLVED_PLACEHOLDER"), self.codes(self.draft("Hello {{missing}}")))

    def test_whitespace_is_info(self):
        self.assertIn(("info", "WHITESPACE"), self.codes(self.draft("Trailing space \nnext")))
        self.assertIn(("info", "WHITESPACE"), self.codes(self.draft("one\n\n\n\ntwo")))
        self.assertIn(("info", "WHITESPACE"), self.codes(self.draft("ends with newline\n")))
        self.assertNotIn(("info", "WHITESPACE"), self.codes(self.draft("one\n\ntwo")))

    def test_em_dash_warns(self):
        self.assertIn(("warn", "EM_DASH"), self.codes(self.draft("a " + EM_DASH + " b")))
        self.assertIn(("warn", "EM_DASH"), self.codes(self.draft("fine", hook="x" + EM_DASH)))
        self.assertNotIn(("warn", "EM_DASH"), self.codes(self.draft("a - b, c: d (e)")))

    def test_empty_body_is_an_error(self):
        self.assertIn(("error", "EMPTY_DRAFT"), self.codes(self.draft("   ")))


class ValidateDraftTests(unittest.TestCase):
    def test_dispatches_to_the_format_validator_and_generic_checks(self):
        body = "x" * 300 + " a " + EM_DASH + " b {{oops}} \n\n\n\nend"
        draft = Draft("x_post", "en", "x", body, parts={"slots": {}}, meta={"sponsored": False, "cta": None}, slots_open=["point"])
        codes = {i.code for i in validate_draft(draft)}
        self.assertTrue({"CHAR_LIMIT", "EM_DASH", "SLOTS_OPEN", "UNRESOLVED_PLACEHOLDER", "WHITESPACE"} <= codes)

    def test_errors_come_first(self):
        draft = Draft("x_post", "en", "x", "y" * 400 + " ", parts={"slots": {}}, meta={}, slots_open=["a"])
        severities = [i.severity for i in validate_draft(draft)]
        self.assertEqual(severities, sorted(severities, key=["error", "warn", "info"].index))
        self.assertEqual(severities[0], "error")

    def test_unknown_format_is_reported_not_raised(self):
        issues = validate_draft(Draft("nope", "en", "h", "body"))
        self.assertEqual(issues[0].code, "UNKNOWN_FORMAT")
        self.assertEqual(issues[0].severity, "error")

    def test_video_open_slots_are_info_and_reported_once(self):
        _, draft = render_offline("short_video_script", briefs()["en_plain"])
        opened = [i for i in validate_draft(draft) if i.code == "SLOTS_OPEN"]
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].severity, "info")
        _, draft = render_offline("linkedin_post", briefs()["en_plain"])
        opened = [i for i in validate_draft(draft) if i.code == "SLOTS_OPEN"]
        self.assertEqual((len(opened), opened[0].severity), (1, "warn"))

    def test_filled_offline_draft_is_clean(self):
        sk = build_skeleton("x_post", briefs()["en_full"])
        draft = sk.render({"point": "Fit matters more than brand, so test on your own feet."})
        self.assertEqual([i for i in validate_draft(draft) if i.severity != "info"], [])


class HelperTests(unittest.TestCase):
    def test_disclosure_detection_english_and_czech(self):
        for text in ("Great run #ad", "#sponsored by Zorvia", "Paid partnership with Zorvia", "Reklama: boty", "#reklama",
                     "Ve spolupráci se značkou Zorvia", "Sponzorováno", "Příspěvek je sponzorovaný", "Spolupráce s Zorvia"):
            self.assertTrue(has_disclosure(text), text)
        for text in ("#adventure awaits", "I read a reklamace form", "Our partnership is great", "No label here", ""):
            self.assertFalse(has_disclosure(text), text)

    def test_engagement_bait_english(self):
        for text in ("Like and share to win a pair!", "Tag a friend who runs", "Comment YES if you agree", "Double tap if you love it",
                     "Share with 3 friends", "Like if you agree", "Smash that like button", "Tag someone who needs this"):
            self.assertTrue(engagement_bait(text), text)

    def test_engagement_bait_czech(self):
        for text in ("Označ kamaráda, který běhá", "Dej like a sdílej", "Sdílejte a vyhrajte boty", "Napiš ANO do komentářů",
                     "Lajkni a sleduj nás", "Označte kamaráda"):
            self.assertTrue(engagement_bait(text), text)

    def test_engagement_bait_negatives(self):
        for text in ("Tell us what you think in the comments", "Share your results if you like", "Napište nám, jak se vám běhá",
                     "A tag line for the brand", ""):
            self.assertEqual(engagement_bait(text), [], text)

    def test_text_helpers(self):
        self.assertEqual(strip_placeholders("a [[ADD: do this]] b"), "a  b")
        self.assertEqual(word_count("Don't stop [[ADD: x y z]] running now"), 4)
        self.assertEqual(hashtags_in("Go #Run #run2 and not #1 or a#b"), ["#Run", "#run2"])
        self.assertEqual(emoji_count("Go \U0001F680\U0001F525 now"), 2)
        self.assertEqual(caps_words("This is SHOUTING about SEO and CRM"), ["SHOUTING"])
        self.assertTrue(keyword_in("Běžecké BOTY pro vás", "bezecke boty"))
        self.assertFalse(keyword_in("anything", None))
        self.assertEqual(fit("  a b  c ", max_words=3), "a b c")
        self.assertIsNone(fit("too long", max_chars=3))
        self.assertIsNone(fit(None))

    def test_cta_detection(self):
        self.assertTrue(has_cta("Download the guide", None))
        self.assertTrue(has_cta("Stáhněte si průvodce", None))
        self.assertTrue(has_cta("Totally custom words here", "totally custom"))
        self.assertFalse(has_cta("Just a statement about shoes", None))

    def test_hashtags_come_only_from_the_brief(self):
        b = briefs()["en_full"]
        # the six word keyword is too long for a hashtag and is skipped
        self.assertEqual(topic_hashtags(b, 10), ["#RunningShoes", "#BeginnerRunners", "#Zorvia", "#FlatFeetShoes"])
        self.assertEqual(topic_hashtags(b, 2), ["#RunningShoes", "#BeginnerRunners"])
        self.assertEqual(topic_hashtags(b, 0), [])
        self.assertEqual(to_hashtag("běžecké boty"), "#BěžeckéBoty")
        self.assertIsNone(to_hashtag("2026"))
        self.assertIsNone(to_hashtag("one two three four"))


if __name__ == "__main__":
    unittest.main()
