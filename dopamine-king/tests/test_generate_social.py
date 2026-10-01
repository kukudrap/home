import unittest

from dopamine_king.generate import social
from dopamine_king.generate.formats import build_skeleton, formats_by_module, get_format, has_disclosure, validate_draft
from dopamine_king.generate.hooks import generate_hooks
from dopamine_king.generate.social import (
    GBP_CTA_BUTTONS, gbp_default_button, has_affiliation_disclosure, links_to_brand, x_length,
)
from dopamine_king.generate.types import Brief, OfflineWriter

CS_FORMS = {"gen": "běžeckých bot", "acc": "běžecké boty", "loc": "běžeckých botách", "ins": "běžeckými botami", "dat": "běžeckým botám"}
SOCIAL_IDS = formats_by_module()["social"]


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


def issues(fid, brief, fills=None, **kw):
    sk, draft = render(fid, brief, fills, **kw)
    return get_format(fid).validate(draft)


def codes(found):
    return {i.code for i in found}


def severity(found, code):
    return {i.severity for i in found if i.code == code}


def worst_case(sk, fills=None):
    """Render with every slot filled to its limit, to prove the template stays inside the platform limit."""
    values = {}
    for s in sk.slots:
        if s.max_chars is not None:
            values[s.id] = "x" * s.max_chars
        elif s.max_words is not None:
            values[s.id] = " ".join(["word"] * s.max_words)
        else:
            values[s.id] = "text"
    values.update(fills or {})
    return sk.render(values)


class BuilderTests(unittest.TestCase):
    def test_twelve_social_formats(self):
        self.assertEqual(len(SOCIAL_IDS), 12)
        for fid in SOCIAL_IDS:
            spec = get_format(fid)
            self.assertEqual(spec.family, "social")
            self.assertTrue(spec.limits, fid)

    def test_linkedin_post_structure(self):
        sk, draft = render("linkedin_post", en())
        self.assertEqual([s.id for s in sk.slots], ["hook", "context", "insight", "proof", "points", "closing", "hashtags"])
        self.assertEqual(sk.slot("hook").max_chars, 140)
        self.assertLessEqual(len(draft.hook), 140)
        self.assertTrue(draft.body.startswith(draft.hook))
        self.assertEqual(draft.slots_open, ["context", "insight", "points"])
        self.assertEqual(draft.parts["slots"]["proof"], "Tested by 1,200 runners over 6 months")
        self.assertEqual(draft.parts["slots"]["closing"], "Download the free fit guide")
        self.assertEqual(draft.parts["slots"]["hashtags"], "#RunningShoes #BeginnerRunners")
        self.assertTrue(draft.body.rstrip().endswith("#RunningShoes #BeginnerRunners"))

    def test_linkedin_post_without_facts_or_cta_leaves_them_open(self):
        _, draft = render("linkedin_post", en(facts=[], cta=None))
        self.assertIn("proof", draft.slots_open)
        self.assertIn("closing", draft.slots_open)
        self.assertEqual(sorted(draft.slots_open), ["closing", "context", "insight", "points", "proof"])

    def test_prose_slots_never_have_defaults(self):
        prose = {
            "linkedin_post": ["context", "insight", "points"], "x_post": ["point"], "instagram_caption": ["body"],
            "facebook_post": ["body"], "threads_post": ["body"], "pinterest_pin": ["description", "alt_text"],
            "youtube_community_post": ["body"], "reddit_answer": ["details", "caveats"], "google_business_post": ["details"],
        }
        for fid, ids in prose.items():
            for brief in (en(), cs()):
                sk = build_skeleton(fid, brief)
                for sid in ids:
                    self.assertIsNone(sk.slot(sid).default, (fid, sid))

    def test_worst_case_stays_inside_the_platform_limits(self):
        limits = {"linkedin_post": 3000, "x_post": 280, "instagram_caption": 2200, "threads_post": 500, "youtube_community_post": 1000}
        for fid, limit in limits.items():
            for brief in (en(), cs(), en(sponsored=True), cs(sponsored=True)):
                sk = build_skeleton(fid, brief)
                draft = worst_case(sk)
                length = x_length(draft.body) if fid == "x_post" else len(draft.body)
                self.assertLessEqual(length, limit, (fid, brief.lang, brief.sponsored, length))

    def test_x_post_worst_case_without_the_poll_section(self):
        sk = build_skeleton("youtube_community_post", en(), options={"poll": 4})
        draft = worst_case(sk)
        self.assertLessEqual(len(social.compose(draft, ["hook", "body", "cta", "disclosure"])), 1000)

    def test_x_thread_options_and_shape(self):
        for given, expected in ((None, 7), (3, 5), (5, 5), (10, 10), (12, 10), ("bad", 7)):
            opts = None if given is None else {"posts": given}
            sk, draft = render("x_thread", en(), options=opts)
            self.assertEqual(len(draft.parts["posts"]), expected, given)
            self.assertEqual(sk.fixed["posts_count"], expected)
        sk, draft = render("x_thread", en(), options={"posts": 6})
        posts = draft.parts["posts"]
        self.assertEqual([p["n"] for p in posts], [1, 2, 3, 4, 5, 6])
        self.assertTrue(posts[0]["text"].startswith("1/6 "))
        self.assertIn(draft.hook, posts[0]["text"])
        self.assertTrue(posts[-1]["text"].startswith("6/6 "))
        self.assertIn("Download the free fit guide", posts[-1]["text"])
        self.assertEqual(sk.slot("hook").max_chars, 240)
        self.assertEqual([s.id for s in sk.slots if s.id.startswith("post_")], ["post_02", "post_03", "post_04", "post_05"])
        self.assertIn("recap", [s.id for s in sk.slots])

    def test_x_thread_worst_case_fits_every_post(self):
        for brief in (en(), cs(sponsored=True)):
            sk = build_skeleton("x_thread", brief, options={"posts": 10})
            draft = worst_case(sk)
            for p in draft.parts["posts"]:
                self.assertLessEqual(p["chars"], 270, p["n"])

    def test_instagram_caption_structure(self):
        sk, draft = render("instagram_caption", en())
        self.assertEqual(sk.slot("hook").max_chars, 125)
        self.assertLessEqual(len(draft.hook), 125)
        tags = draft.parts["slots"]["hashtags"].split()
        self.assertTrue(3 <= len(tags) <= 5, tags)
        sk, draft = render("instagram_caption", en(sponsored=True))
        self.assertTrue(draft.body.startswith("#ad"))

    def test_facebook_post_is_short(self):
        for brief in (en(), cs(), en(sponsored=True)):
            sk = build_skeleton("facebook_post", brief)
            draft = worst_case(sk)
            self.assertLessEqual(len(social.strip_placeholders(draft.body).split()), 80)
            self.assertEqual(sk.fixed["aim_words"], 80)
            self.assertLessEqual(len(sk.slot("hook").default.split()), 15)

    def test_threads_post_structure(self):
        sk, draft = render("threads_post", cs())
        self.assertEqual(sk.fixed["max_chars"], 500)
        self.assertIn("one topic tag", " ".join(sk.notes))
        self.assertLessEqual(len(draft.body), 500)

    def test_linkedin_carousel_shape(self):
        for given, expected in ((None, 10), (8, 8), (12, 12), (3, 8), (30, 12)):
            opts = None if given is None else {"slides": given}
            sk, draft = render("linkedin_carousel", en(), options=opts)
            slides = draft.parts["slides"]
            self.assertEqual(len(slides), expected, given)
            self.assertEqual(slides[0]["role"], "hook")
            self.assertEqual(slides[-1]["role"], "cta")
            self.assertEqual(sk.slot(f"title_{expected:02d}").default, "Next step")
            for s in sk.slots:
                if s.id.startswith("title_"):
                    self.assertEqual(s.max_words, 8)
                if s.id.startswith("body_"):
                    self.assertEqual(s.max_words, 30)
        _, draft = render("linkedin_carousel", en())
        self.assertEqual(draft.parts["slides"][0]["title"], draft.hook)
        self.assertEqual(draft.parts["slides"][-1]["body"], "Download the free fit guide")
        self.assertLessEqual(len(draft.hook.split()), 8)

    def test_linkedin_carousel_czech_labels(self):
        sk, draft = render("linkedin_carousel", cs())
        self.assertEqual(draft.parts["slides"][-1]["title"], "Další krok")
        self.assertEqual(draft.parts["slides"][0]["body"], "Téma: běžecké boty")
        self.assertTrue(any("Slide 2" in s.instruction for s in sk.slots))

    def test_instagram_carousel_shape(self):
        for given, expected in ((None, 7), (3, 3), (10, 10), (14, 10), (1, 3)):
            opts = None if given is None else {"slides": given}
            sk, draft = render("instagram_carousel", en(), options=opts)
            self.assertEqual(len(draft.parts["slides"]), expected, given)
            for s in sk.slots:
                if s.id.startswith("slide_"):
                    self.assertEqual(s.max_words, 25)
        sk, draft = render("instagram_carousel", en())
        self.assertEqual(draft.parts["slides"][0]["text"], draft.hook)
        self.assertEqual(draft.parts["slides"][-1]["text"], "Download the free fit guide")
        self.assertIn("caption", draft.slots_open)
        self.assertIn("first 125 characters", sk.slot("caption").instruction)

    def test_pinterest_pin_structure(self):
        sk, draft = render("pinterest_pin", en())
        self.assertEqual(sk.hook_slot, "title")
        self.assertLessEqual(len(draft.parts["slots"]["title"]), 100)
        self.assertIn("running shoes for flat feet", draft.parts["slots"]["title"].lower())
        self.assertEqual(sk.slot("description").must_include, ["running shoes for flat feet"])
        self.assertEqual(sk.slot("description").max_chars, 500)
        self.assertIn("alt_text", [s.id for s in sk.slots])
        self.assertEqual(sorted(draft.slots_open), ["alt_text", "description"])

    def test_youtube_community_poll_options(self):
        sk, draft = render("youtube_community_post", en())
        self.assertIsNone(draft.parts["poll"])
        self.assertEqual(sk.fixed["poll_options"], 0)
        self.assertNotIn("poll_question", [s.id for s in sk.slots])
        sk, draft = render("youtube_community_post", en(), options={"poll": 3})
        self.assertEqual(len(draft.parts["poll"]["options"]), 3)
        self.assertEqual(sk.fixed["poll_options"], 3)
        sk, draft = render("youtube_community_post", en(), options={"poll": ["Road", "Trail"]})
        self.assertEqual(draft.parts["poll"]["options"], ["Road", "Trail"])
        self.assertIn("poll_question", draft.slots_open)
        self.assertNotIn("poll_option_1", draft.slots_open)
        for given, expected in ((9, 4), (1, 2), (["a"], 2), (["a", "b", "c", "d", "e", "f"], 4)):
            sk, draft = render("youtube_community_post", en(), options={"poll": given})
            self.assertEqual(len(draft.parts["poll"]["options"]), expected, given)

    def test_reddit_answer_never_contains_sales_copy(self):
        sk, draft = render("reddit_answer", en())
        defaults = {s.id: s.default for s in sk.slots if s.default}
        self.assertEqual(defaults, {"disclosure": "Disclosure: I work at Zorvia."})
        self.assertEqual(sorted(draft.slots_open), ["caveats", "details", "direct_answer"])
        self.assertTrue(draft.body.rstrip().endswith("Disclosure: I work at Zorvia."))
        self.assertNotIn("Download the free fit guide", draft.body)
        self.assertIn("no promotion", sk.slot("direct_answer").instruction.lower())
        self.assertIn("No brand mention, no links", sk.slot("details").instruction)
        self.assertEqual(sk.hook_slot, "direct_answer")

    def test_reddit_answer_variants(self):
        sk, _ = render("reddit_answer", cs())
        self.assertEqual(sk.slot("disclosure").default, "Upozornění: pracuji pro Zorvia.")
        sk, _ = render("reddit_answer", en(sponsored=True))
        self.assertIn("sponsored", sk.slot("disclosure").default)
        sk, _ = render("reddit_answer", en(), options={"subreddit": "r/running"})
        self.assertEqual(sk.fixed["subreddit"], "r/running")
        self.assertTrue(any("r/running" in n for n in sk.notes))
        self.assertTrue(any("subreddit rules" in n for n in sk.notes))

    def test_google_business_post_structure(self):
        sk, draft = render("google_business_post", en())
        self.assertEqual(list(sk.fixed["cta_buttons"]), ["Book", "Order online", "Buy", "Learn more", "Sign up", "Call now"])
        self.assertEqual(sk.fixed["aim_chars"], [150, 300])
        self.assertEqual(draft.parts["slots"]["cta_button"], "Learn more")
        total = worst_case(sk)
        self.assertLessEqual(len(social.compose(total, ["hook", "details", "cta"])), 300)

    def test_google_business_default_button(self):
        cases = {"Book a table": "Book", "Rezervujte si místo": "Book", "Order online today": "Order online",
                 "Objednejte si": "Order online", "Buy now": "Buy", "Sign up for the newsletter": "Sign up",
                 "Call us today": "Call now", "Zavolejte nám": "Call now", "Read the guide": "Learn more", None: "Learn more"}
        for cta, expected in cases.items():
            self.assertEqual(gbp_default_button(en(cta=cta)), expected, cta)
        self.assertTrue(set(cases.values()) <= set(GBP_CTA_BUTTONS))

    def test_sponsored_adds_a_disclosure_slot_with_a_default(self):
        for fid in SOCIAL_IDS:
            if fid == "reddit_answer":
                continue
            for brief, tag in ((en(sponsored=True), "#ad"), (cs(sponsored=True), "#reklama")):
                sk = build_skeleton(fid, brief)
                self.assertEqual(sk.slot("disclosure").default, tag, fid)
                plain = build_skeleton(fid, en())
                self.assertNotIn("disclosure", [s.id for s in plain.slots], fid)

    def test_hooks_come_from_the_hook_library(self):
        library = {c.text for c in generate_hooks(en(), n=36, max_chars=140)}
        sk = build_skeleton("linkedin_post", en())
        self.assertIn(sk.slot("hook").default, library)
        self.assertEqual(sk.slot("hook").default, generate_hooks(en(), n=1, max_chars=140)[0].text)


class ValidatorTests(unittest.TestCase):
    def test_placeholders_are_ignored_by_limits(self):
        for fid in SOCIAL_IDS:
            for brief in (en(), cs()):
                found = issues(fid, brief)
                self.assertFalse([i for i in found if i.severity == "error"], (fid, [i.code for i in found]))

    def test_linkedin_char_limit_is_an_error(self):
        found = issues("linkedin_post", en(), {"insight": "x" * 800, "context": "y" * 300, "points": "z" * 700, "closing": "c" * 200,
                                                 "proof": "p" * 300, "hook": "h" * 140})
        self.assertNotIn("CHAR_LIMIT", codes(found))
        found = issues("linkedin_post", en(), {"hook": "Short hook", "insight": "x" * 3100})
        self.assertEqual(severity(found, "CHAR_LIMIT"), {"error"})

    def test_hook_truncation_and_position(self):
        found = issues("linkedin_post", en(), {"hook": "H" * 150})
        self.assertEqual(severity(found, "HOOK_TRUNCATED"), {"warn"})
        found = issues("instagram_caption", en(), {"hook": "H" * 130})
        self.assertIn("HOOK_TRUNCATED", codes(found))
        sk, draft = render("linkedin_post", en())
        draft.body = "Some other first line that is not the hook, long enough to push it away.\n\n" + draft.body
        self.assertIn("HOOK_MISSING", codes(get_format("linkedin_post").validate(draft)))

    def test_hashtag_counts(self):
        found = issues("linkedin_post", en(), {"hashtags": "#a1 #b2 #c3 #d4"})
        self.assertEqual(severity(found, "HASHTAG_COUNT"), {"warn"})
        self.assertNotIn("HASHTAG_COUNT", codes(issues("linkedin_post", en(), {"hashtags": "#One #Two #Three"})))
        self.assertIn("HASHTAG_COUNT", codes(issues("instagram_caption", en(), {"hashtags": "#One #Two"})))
        self.assertIn("HASHTAG_COUNT", codes(issues("instagram_caption", en(), {"hashtags": "#a1 #b2 #c3 #d4 #e5 #f6"})))
        self.assertNotIn("HASHTAG_COUNT", codes(issues("instagram_caption", en(), {"hashtags": "#a1 #b2 #c3 #d4 #e5"})))
        self.assertIn("HASHTAG_COUNT", codes(issues("threads_post", en(), {"body": "Tags #one #two here"})))
        self.assertIn("HASHTAG_COUNT", codes(issues("facebook_post", en(), {"body": "#a1 #b2 #c3 #d4 words"})))

    def test_emoji_in_first_line(self):
        three = "\U0001F680\U0001F525" + chr(0x2728) + " Start now"
        four = "\U0001F680\U0001F525" + chr(0x2728) + "\U0001F4A1 Start now"
        self.assertNotIn("EMOJI_OVERUSE", codes(issues("linkedin_post", en(), {"hook": three})))
        self.assertEqual(severity(issues("linkedin_post", en(), {"hook": four}), "EMOJI_OVERUSE"), {"warn"})

    def test_all_caps_ratio(self):
        found = issues("linkedin_post", en(), {"insight": "BUY NOW AND SAVE BIG TODAY with this offer"})
        self.assertEqual(severity(found, "ALL_CAPS"), {"warn"})
        self.assertNotIn("ALL_CAPS", codes(issues("linkedin_post", en(), {"insight": "Our SEO and CRM tips help the whole team"})))

    def test_engagement_bait_in_both_languages(self):
        for brief, text in ((en(), "Like and share to win a free pair. Tag a friend!"), (en(), "Comment YES below"),
                            (cs(), "Označ kamaráda a sdílej, ať vyhraješ"), (cs(), "Napiš ANO do komentářů")):
            found = issues("linkedin_post", brief, {"insight": text})
            self.assertEqual(severity(found, "ENGAGEMENT_BAIT"), {"warn"}, text)
        self.assertNotIn("ENGAGEMENT_BAIT", codes(issues("linkedin_post", en(), {"insight": "What is your take on trail shoes?"})))
        self.assertIn("ENGAGEMENT_BAIT", codes(issues("x_post", en(), {"point": "Tag a friend who runs"})))
        self.assertIn("ENGAGEMENT_BAIT", codes(issues("x_thread", en(), {"post_02": "Like and share to win"})))

    def test_missing_cta_is_a_warning(self):
        found = issues("linkedin_post", en(cta=None), {"closing": "That is all for today."})
        self.assertEqual(severity(found, "CTA_MISSING"), {"warn"})
        self.assertNotIn("CTA_MISSING", codes(issues("linkedin_post", en(cta=None), {"closing": "Which shoe fits your stride best?"})))
        self.assertNotIn("CTA_MISSING", codes(issues("linkedin_post", en(cta=None), {"closing": "Download the checklist."})))
        self.assertIn("CTA_MISSING", codes(issues("facebook_post", en(cta=None), {"cta": "That is all."})))
        self.assertIn("CTA_MISSING", codes(issues("instagram_caption", en(cta=None), {"cta": "Nothing more."})))
        self.assertNotIn("CTA_MISSING", codes(issues("linkedin_post", cs(cta=None), {"closing": "Stáhněte si seznam."})))

    def test_sponsored_disclosure_rules(self):
        for fid in SOCIAL_IDS:
            if fid == "reddit_answer":
                continue
            for brief in (en(sponsored=True), cs(sponsored=True)):
                with self.subTest(format=fid, lang=brief.lang):
                    self.assertNotIn("DISCLOSURE_MISSING", codes(issues(fid, brief)))
                    found = issues(fid, brief, {"disclosure": "Thanks for reading"})
                    self.assertEqual(severity(found, "DISCLOSURE_MISSING"), {"error"})
        self.assertNotIn("DISCLOSURE_MISSING", codes(issues("linkedin_post", en(sponsored=True), {"disclosure": "Paid partnership with Zorvia"})))
        for text in ("#sponsored", "Reklama", "#reklama", "Spolupráce se Zorvia", "Sponzorováno", "paid partnership"):
            self.assertNotIn("DISCLOSURE_MISSING", codes(issues("linkedin_post", en(sponsored=True), {"disclosure": text})), text)
        self.assertNotIn("DISCLOSURE_MISSING", codes(issues("linkedin_post", en(sponsored=False), {"disclosure": "x"})))

    def test_disclosure_may_sit_anywhere_in_the_text(self):
        found = issues("linkedin_post", en(sponsored=True), {"disclosure": "x", "closing": "Download it now. #ad"})
        self.assertNotIn("DISCLOSURE_MISSING", codes(found))

    def test_x_post_counts_links_and_emoji_like_x(self):
        self.assertEqual(x_length("a" * 280), 280)
        self.assertEqual(x_length("see https://example.com/some/very/long/path/to/a/page/that/goes/on"), 4 + 23)
        self.assertEqual(x_length("go \U0001F680"), 3 + 1 + 1)
        ok = issues("x_post", en(), {"hook": "h" * 100, "point": "p" * 115, "cta": "c" * 40})
        self.assertNotIn("CHAR_LIMIT", codes(ok))
        sk, draft = render("x_post", en(), {"hook": "h" * 100, "point": "p" * 115, "cta": "c" * 40})
        draft.body = "a" * 281
        self.assertEqual(severity(get_format("x_post").validate(draft), "CHAR_LIMIT"), {"error"})
        draft.body = "a" * 270 + " https://example.com/very/long/url/that/should/count/as/twentythree"
        self.assertEqual(severity(get_format("x_post").validate(draft), "CHAR_LIMIT"), {"error"})
        draft.body = "a" * 279 + "\U0001F680"      # 280 code points but the emoji weighs 2
        self.assertEqual(severity(get_format("x_post").validate(draft), "CHAR_LIMIT"), {"error"})
        draft.body = "a" * 278 + "\U0001F680"
        self.assertNotIn("CHAR_LIMIT", codes(get_format("x_post").validate(draft)))
        draft.body = "a" * 255 + " https://example.com/very/long/url/that/should/count/as/twentythree"
        self.assertNotIn("CHAR_LIMIT", codes(get_format("x_post").validate(draft)))

    def test_x_thread_validator(self):
        found = issues("x_thread", en(), {"post_02": "x" * 275}, options={"posts": 6})
        self.assertEqual(severity(found, "CHAR_LIMIT"), {"error"})
        sk, draft = render("x_thread", en(), options={"posts": 6})
        draft.parts["posts"] = draft.parts["posts"][:3]
        self.assertEqual(severity(get_format("x_thread").validate(draft), "POST_COUNT"), {"error"})
        found = issues("x_thread", en(cta=None), {"recap": "Summary of it all.", "cta": "Thanks for reading."}, options={"posts": 5})
        self.assertIn("CTA_MISSING", codes(found))
        found = issues("x_thread", en(), {"hook": "Hook with #one #two #three"}, options={"posts": 5})
        self.assertIn("HASHTAG_COUNT", codes(found))

    def test_linkedin_carousel_validator(self):
        found = issues("linkedin_carousel", en(), {"title_02": "one two three four five six seven eight nine",
                                                    "body_03": " ".join(["w"] * 31)})
        self.assertEqual(severity(found, "SLIDE_TITLE_LONG"), {"warn"})
        self.assertEqual(severity(found, "SLIDE_BODY_LONG"), {"warn"})
        sk, draft = render("linkedin_carousel", en())
        draft.parts["slides"] = draft.parts["slides"][:5]
        self.assertEqual(severity(get_format("linkedin_carousel").validate(draft), "SLIDE_COUNT"), {"error"})
        found = issues("linkedin_carousel", en(cta=None), {"title_10": "Thanks", "body_10": "That is all."})
        self.assertIn("CTA_MISSING", codes(found))
        found = issues("linkedin_carousel", en(), {"body_04": "Like and share to win"})
        self.assertIn("ENGAGEMENT_BAIT", codes(found))

    def test_instagram_carousel_validator(self):
        found = issues("instagram_carousel", en(), {"slide_02": " ".join(["w"] * 26)})
        self.assertEqual(severity(found, "SLIDE_TEXT_LONG"), {"warn"})
        found = issues("instagram_carousel", en(), {"caption": "c" * 2300})
        self.assertEqual(severity(found, "CHAR_LIMIT"), {"error"})
        sk, draft = render("instagram_carousel", en())
        draft.parts["slides"] = draft.parts["slides"] * 2
        self.assertEqual(severity(get_format("instagram_carousel").validate(draft), "SLIDE_COUNT"), {"error"})
        found = issues("instagram_carousel", en(cta=None), {"slide_07": "Bye"})
        self.assertIn("CTA_MISSING", codes(found))

    def test_instagram_caption_limit(self):
        found = issues("instagram_caption", en(), {"body": "b" * 1500, "hook": "h" * 125, "cta": "c" * 150, "hashtags": " ".join(["#tag"] * 5)})
        self.assertNotIn("CHAR_LIMIT", codes(found))
        sk, draft = render("instagram_caption", en())
        draft.body = draft.body + "x" * 2300
        self.assertEqual(severity(get_format("instagram_caption").validate(draft), "CHAR_LIMIT"), {"error"})

    def test_facebook_length_aim(self):
        found = issues("facebook_post", en(), {"body": " ".join(["word"] * 100)})
        self.assertEqual(severity(found, "LENGTH_AIM"), {"warn"})
        self.assertNotIn("LENGTH_AIM", codes(issues("facebook_post", en(), {"body": "Short and sweet."})))

    def test_threads_limit(self):
        sk, draft = render("threads_post", en())
        draft.body = draft.body + "x" * 500
        self.assertEqual(severity(get_format("threads_post").validate(draft), "CHAR_LIMIT"), {"error"})

    def test_pinterest_validator(self):
        found = issues("pinterest_pin", en(), {"title": "t" * 101, "description": "d" * 501, "alt_text": "a" * 501})
        self.assertEqual([i.where for i in found if i.code == "CHAR_LIMIT"], ["title", "description", "alt_text"])
        found = issues("pinterest_pin", en(), {"alt_text": "a" * 200})
        self.assertEqual(severity(found, "ALT_TEXT_LONG"), {"info"})
        found = issues("pinterest_pin", en(), {"title": "Great shoes", "description": "A nice description. Learn more today."})
        self.assertEqual(severity(found, "KEYWORD_MISSING"), {"warn"})
        found = issues("pinterest_pin", en(), {"description": "Everything about running shoes for flat feet. Learn more."})
        self.assertNotIn("KEYWORD_MISSING", codes(found))

    def test_pinterest_waits_for_the_description_before_judging_keyword_and_cta(self):
        found = issues("pinterest_pin", en(), {"title": "A title without the phrase"})
        self.assertFalse({"KEYWORD_MISSING", "CTA_MISSING"} & codes(found))
        found = issues("pinterest_pin", en(), {"title": "A title without the phrase", "description": "Plain words only."})
        self.assertTrue({"KEYWORD_MISSING", "CTA_MISSING"} <= codes(found))

    def test_youtube_community_validator(self):
        found = issues("youtube_community_post", en(), {"body": "b" * 680, "hook": "h" * 140, "cta": "c" * 120})
        self.assertNotIn("CHAR_LIMIT", codes(found))
        sk, draft = render("youtube_community_post", en())
        draft.body = draft.body + "x" * 1000
        found = get_format("youtube_community_post").validate(draft)
        self.assertNotIn("CHAR_LIMIT", codes(found))      # the checked text is assembled from the slots
        found = issues("youtube_community_post", en(), {"body": "x" * 1100})
        self.assertEqual(severity(found, "CHAR_LIMIT"), {"error"})

    def test_youtube_poll_validation(self):
        sk, draft = render("youtube_community_post", en(), options={"poll": ["A", "B", "C"]})
        spec = get_format("youtube_community_post")
        self.assertNotIn("POLL_OPTIONS", codes(spec.validate(draft)))
        draft.parts["poll"]["options"] = ["only one"]
        self.assertEqual(severity(spec.validate(draft), "POLL_OPTIONS"), {"error"})
        draft.parts["poll"]["options"] = ["a", "b", "c", "d", "e"]
        self.assertEqual(severity(spec.validate(draft), "POLL_OPTIONS"), {"error"})
        draft.parts["poll"]["options"] = ["a", "b" * 70]
        self.assertEqual(severity(spec.validate(draft), "CHAR_LIMIT"), {"error"})
        draft.parts["poll"]["options"] = ["Same", "same"]
        self.assertEqual(severity(spec.validate(draft), "POLL_DUPLICATE"), {"warn"})

    def test_reddit_brand_link_in_the_first_300_characters(self):
        early = "Use a wider toe box. See https://www.zorvia.com/guide for details. " + "More words here. " * 5
        found = issues("reddit_answer", en(), {"direct_answer": early})
        self.assertEqual(severity(found, "BRAND_LINK_EARLY"), {"error"})
        found = issues("reddit_answer", en(), {"direct_answer": "Check zorvia.cz for the guide."})
        self.assertEqual(severity(found, "BRAND_LINK_EARLY"), {"error"})
        late = "Use a wider toe box and test on a slope. " + "Words that help and explain the fit in detail. " * 8
        found = issues("reddit_answer", en(), {"direct_answer": late, "details": "Longer notes. More at https://zorvia.com/guide"})
        self.assertNotIn("BRAND_LINK_EARLY", codes(found))
        found = issues("reddit_answer", en(), {"direct_answer": "See https://runnersworld.com/fit for details."})
        self.assertNotIn("BRAND_LINK_EARLY", codes(found))

    def test_reddit_disclosure_and_promotion(self):
        found = issues("reddit_answer", en(), {"disclosure": "Just my two cents."})
        self.assertEqual(severity(found, "DISCLOSURE_MISSING"), {"error"})
        self.assertNotIn("DISCLOSURE_MISSING", codes(issues("reddit_answer", en(), {"disclosure": "Full disclosure, I work at Zorvia."})))
        self.assertNotIn("DISCLOSURE_MISSING", codes(issues("reddit_answer", cs())))
        self.assertNotIn("DISCLOSURE_MISSING", codes(issues("reddit_answer", cs(), {"disclosure": "Jsem z Zorvia a píšu za sebe."})))
        found = issues("reddit_answer", en(), {"details": "Zorvia makes the best shoes, check out our shop and use code RUN10."})
        self.assertEqual(severity(found, "BRAND_PROMOTION"), {"warn"})
        self.assertEqual(severity(found, "PROMO_LANGUAGE"), {"warn"})
        found = issues("reddit_answer", en(), {"details": "Rotate two pairs and check the wear pattern."})
        self.assertFalse({"BRAND_PROMOTION", "PROMO_LANGUAGE"} & codes(found))
        found = issues("reddit_answer", en(), {"details": "Like and share to win"})
        self.assertIn("ENGAGEMENT_BAIT", codes(found))

    def test_reddit_sponsored_needs_a_sponsored_label(self):
        self.assertNotIn("DISCLOSURE_MISSING", codes(issues("reddit_answer", en(sponsored=True))))
        found = issues("reddit_answer", en(sponsored=True), {"disclosure": "Disclosure: I work at Zorvia."})
        self.assertEqual(severity(found, "DISCLOSURE_MISSING"), {"error"})

    def test_reddit_helpers(self):
        self.assertTrue(links_to_brand("go to http://zorvia.com/x", "Zorvia"))
        self.assertTrue(links_to_brand("go to www.zorvia.shop", "Zorvia"))
        self.assertTrue(links_to_brand("ZORVIA.IO", "Zorvia"))
        self.assertFalse(links_to_brand("go to https://example.com", "Zorvia"))
        self.assertFalse(links_to_brand("Zorvia makes shoes", "Zorvia"))
        self.assertFalse(links_to_brand("http://zorvia.com", "Zo"))
        self.assertTrue(has_affiliation_disclosure("I work at Zorvia.", "Zorvia"))
        self.assertTrue(has_affiliation_disclosure("Pracuji pro Zorvia.", "Zorvia"))
        self.assertFalse(has_affiliation_disclosure("I like Zorvia.", "Zorvia"))
        self.assertFalse(has_affiliation_disclosure("I work at Acme.", "Zorvia"))

    def test_google_business_validator(self):
        found = issues("google_business_post", en(), {"hook": "h" * 90, "details": "d" * 150, "cta": "c" * 50})
        self.assertNotIn("CHAR_LIMIT", codes(found))
        sk, draft = render("google_business_post", en(), {"details": "x" * 1400, "hook": "h" * 90})
        draft.parts["slots"]["details"] = "x" * 1600
        self.assertEqual(severity(get_format("google_business_post").validate(draft), "CHAR_LIMIT"), {"error"})
        found = issues("google_business_post", en(), {"details": "Short."})
        self.assertEqual(severity(found, "LENGTH_AIM"), {"warn"})
        found = issues("google_business_post", en(), {"details": "d" * 150, "hook": "h" * 90, "cta": "c" * 50})
        self.assertNotIn("LENGTH_AIM", codes(found))
        found = issues("google_business_post", en(), {"cta_button": "Click me"})
        self.assertEqual(severity(found, "INVALID_CTA_BUTTON"), {"error"})
        for button in GBP_CTA_BUTTONS:
            self.assertNotIn("INVALID_CTA_BUTTON", codes(issues("google_business_post", en(), {"cta_button": button})))

    def test_validate_draft_adds_generic_checks_to_social_drafts(self):
        sk, draft = render("linkedin_post", en(), {"insight": "A claim " + chr(0x2014) + " with a dash"})
        found = validate_draft(draft)
        self.assertIn("EM_DASH", codes(found))
        self.assertIn("SLOTS_OPEN", codes(found))
        self.assertTrue(has_disclosure("#ad"))


if __name__ == "__main__":
    unittest.main()
