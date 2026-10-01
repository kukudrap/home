import json
import re
import unittest

from dopamine_king.generate import longform as lf
from dopamine_king.generate.types import Brief, Draft, OfflineWriter

EN = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="running shoes for flat feet", cta="Take the quiz",
           offer="Cloudrunner 2", facts=["Weight: 240 g"])
CS = Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", keyword="běžecké boty", cta="Vyzkoušejte test",
           offer="Cloudrunner 2")
BARE = Brief(brand="Acme", topic="invoicing", audience="freelancers")
SPEC = {s.id: s for s in lf.FORMAT_SPECS}
SENT = ["Beginners often pick shoes by colour and then wonder why their knees hurt.", "A short gait check takes ten minutes and costs nothing.",
        "Try shoes in the afternoon because feet swell during the day.", "Leave a thumb width of space in front of the longest toe."]


def words(n):
    out, i = [], 0
    while sum(len(s.split()) for s in out) < n:
        out.append(SENT[i % len(SENT)])
        i += 1
    return " ".join(out)


SAMPLES = {
    "headline": "Zorvia launches Cloudrunner 2 for beginner runners", "subhead": "A fit-first running shoe for people who just started.",
    "lead": "Zorvia today launched Cloudrunner 2 in Prague to help beginner runners choose a shoe that fits their feet.",
    "boilerplate": "Zorvia designs running shoes for beginners. The company runs a free gait lab in Prague.",
    "media_contact": "Jana Novakova, press manager, press@zorvia.example", "quote_1_name": "Petra Svobodova", "quote_1_title": "head of product",
    "quote_1_text": "We built the shoe around a ten minute gait check that every beginner can do in a store.",
    "hero_headline": "Find running shoes that fit your feet", "hero_subhead": "Cloudrunner 2 is a fit-first shoe for new runners.",
    "meta_description": "Cloudrunner 2 is a running shoe for beginner runners, matched to your feet with a ten minute gait check before you buy it.",
    "proof_stat_1": "412 beginner runners took part in our 2025 gait lab.", "testimonial_quote": "The gait check told me what to buy in ten minutes.",
    "testimonial_name": "Eva K., runner", "final_cta_text": "Take the quiz and find your fit.", "subject": "Three fit checks before you buy",
    "preheader": "A short checklist that saves you a return trip", "footer_identity": "Zorvia s.r.o., Example street 1, Prague",
    "main_heading": "Why fit beats price",
}


def sample_for(slot):
    if slot.id in SAMPLES:
        return SAMPLES[slot.id]
    if re.fullmatch(r"e\d_subject", slot.id):
        return "Three fit checks before you buy"
    if re.fullmatch(r"e\d_preheader", slot.id):
        return "A short checklist that saves you a trip"
    if slot.id.endswith(("_title", "_heading")) or slot.id.startswith(("faq_q", "e")) and slot.kind == "line":
        return "Gait check basics"
    return words(max(15, int((slot.max_words or 40) * 0.6)))


def render_filled(spec_id, brief=EN, options=None, **over):
    sk = SPEC[spec_id].build(brief, options=options)
    fills = OfflineWriter().fill(sk, brief)
    for s in sk.slots:
        if s.id not in fills:
            fills[s.id] = sample_for(s)
    fills.update(over)
    return sk.render(fills)


class RegistryTests(unittest.TestCase):
    def test_registered_formats(self):
        self.assertEqual([f.id for f in lf.FORMAT_SPECS], ["press_release", "landing_page", "newsletter", "email_sequence"])
        self.assertEqual({f.id: (f.family, f.platform) for f in lf.FORMAT_SPECS},
                         {"press_release": ("article", "newsroom"), "landing_page": ("article", "web"), "newsletter": ("email", "email"),
                          "email_sequence": ("email", "email")})
        for f in lf.FORMAT_SPECS:
            self.assertTrue(callable(f.build) and callable(f.validate) and f.limits)
            self.assertNotIn(chr(0x2014), json.dumps([f.name_en, f.name_cs, f.description_en, f.description_cs]))

    def test_every_format_builds_and_renders_offline_in_both_languages(self):
        for brief in (EN, CS, BARE):
            for spec in lf.FORMAT_SPECS:
                sk = spec.build(brief)
                ids = [s.id for s in sk.slots]
                self.assertEqual(len(ids), len(set(ids)), spec.id)
                for sid in re.findall(r"\{\{([a-z0-9_]+)\}\}", sk.template):
                    self.assertIn(sid, ids, (spec.id, sid))
                for key in ("goal", "cta", "sponsored", "keyword", "lang"):
                    self.assertIn(key, sk.meta, (spec.id, key))
                d = sk.render(OfflineWriter().fill(sk, brief))
                self.assertEqual((d.format, d.lang), (spec.id, brief.lang))
                self.assertTrue(d.slots_open)
                self.assertIn("[[ADD:", d.body)
                self.assertNotIn("{{", d.body)
                self.assertNotIn(chr(0x2014), d.body)
                self.assertEqual(d.meta["lang"], brief.lang)

    def test_defaults_only_restate_the_brief(self):
        defaults = {spec.id: {s.id: s.default for s in spec.build(EN).slots if s.default} for spec in lf.FORMAT_SPECS}
        self.assertEqual(defaults["press_release"], {"boilerplate": "Zorvia"})
        self.assertEqual(defaults["landing_page"], {"meta_title": "Cloudrunner 2 | Zorvia", "cta": "Take the quiz",
                                                    "faq_q1": "Is this right for beginner runners?", "faq_q2": "How much does it cost?",
                                                    "faq_q3": "What if it is not right for me?"})
        self.assertEqual(defaults["newsletter"], {"cta": "Take the quiz"})
        self.assertEqual(defaults["email_sequence"], {f"e{i}_cta": "Take the quiz" for i in range(1, 5)})
        bare = {spec.id: {s.id: s.default for s in spec.build(BARE).slots if s.default} for spec in lf.FORMAT_SPECS}
        self.assertEqual(bare["press_release"], {"boilerplate": "Acme"})
        self.assertEqual(bare["newsletter"], {})
        self.assertEqual(bare["email_sequence"], {})
        self.assertNotIn("cta", bare["landing_page"])

    def test_proof_quotes_and_contacts_are_never_defaulted(self):
        pr = {s.id: s for s in SPEC["press_release"].build(EN).slots}
        for sid in ("quote_1_text", "quote_1_name", "quote_1_title", "media_contact", "lead", "headline"):
            self.assertIsNone(pr[sid].default, sid)
        landing = {s.id: s for s in SPEC["landing_page"].build(EN).slots}
        for sid in ("proof_stat_1", "proof_stat_2", "testimonial_quote", "testimonial_name", "problem", "solution", "benefit_1_body", "faq_a1"):
            self.assertIsNone(landing[sid].default, sid)


class SourcesTests(unittest.TestCase):
    WITH_SOURCES = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", cta="Take the quiz", offer="Cloudrunner 2",
                         sources=[{"id": "s1", "title": "Fit study", "url": "https://example.org/study", "claim": "Fit matters"}])

    def test_press_release_and_landing_page_list_vetted_sources_only(self):
        for fid in ("press_release", "landing_page"):
            d = SPEC[fid].build(self.WITH_SOURCES).render()
            self.assertIn("## Sources\n\n1. [Fit study](https://example.org/study)", d.body, fid)
            self.assertEqual(d.parts["sources"], [{"n": 1, "id": "s1", "title": "Fit study", "url": "https://example.org/study", "claim": "Fit matters"}])
            self.assertIn("Vetted sources: s1 (Fit matters)", d.body)
        for fid in ("press_release", "landing_page", "newsletter", "email_sequence"):
            self.assertEqual(SPEC[fid].build(BARE).render().parts["sources"], [], fid)
            self.assertNotIn("## Sources", SPEC[fid].build(BARE).render().body, fid)

    def test_press_release_keeps_the_end_mark_last_and_landing_keeps_its_cta_rules(self):
        pr = SPEC["press_release"].build(self.WITH_SOURCES).render()
        self.assertTrue(pr.body.rstrip().endswith("###"))
        self.assertLess(pr.body.index("## Sources"), pr.body.index("## About Zorvia"))
        landing = render_filled("landing_page", self.WITH_SOURCES)
        self.assertEqual(lf.validate_landing_page(landing), [])
        self.assertEqual(landing.body.count("**[Take the quiz](#cta)**"), 2)

    def test_czech_sources_heading(self):
        b = Brief(brand="Zorvia", topic="běžecké boty", audience="běžci", lang="cs", cta="Vyzkoušejte test",
                  sources=[{"id": "s1", "title": "Studie", "url": "https://example.org/s", "claim": "Obuv záleží"}])
        self.assertIn("## Zdroje", SPEC["landing_page"].build(b).render().body)


class PressReleaseTests(unittest.TestCase):
    def test_structure_and_end_mark(self):
        d = SPEC["press_release"].build(EN).render()
        self.assertTrue(d.body.startswith("FOR IMMEDIATE RELEASE\n\n# "))
        self.assertTrue(d.body.rstrip().endswith("\n###"))
        self.assertIn("## About Zorvia\n\nZorvia\n", d.body)
        self.assertIn("## Media contact", d.body)
        self.assertEqual(d.parts["end_mark"], "###")
        cs = SPEC["press_release"].build(CS).render()
        self.assertTrue(cs.body.startswith("TISKOVÁ ZPRÁVA"))
        self.assertIn("## O značce Zorvia", cs.body)
        self.assertIn("## Kontakt pro média", cs.body)
        self.assertIn(", uvádí ", cs.body)

    def test_dateline_default_needs_city_and_date(self):
        self.assertIsNone(SPEC["press_release"].build(EN).slot("dateline").default)
        self.assertIsNone(lf.build_press_release(EN, options={"city": "Prague"}).slot("dateline").default)
        self.assertEqual(lf.build_press_release(EN, options={"city": "Prague", "date": "2026-10-12"}).slot("dateline").default, "PRAGUE, October 12, 2026")
        self.assertEqual(lf.build_press_release(CS, options={"city": "Praha", "date": "2026-10-12"}).slot("dateline").default, "Praha, 12. října 2026")

    def test_headline_default_only_from_a_fitting_hook(self):
        self.assertEqual(lf.build_press_release(EN, hook="Zorvia launches Cloudrunner 2").slot("headline").default, "Zorvia launches Cloudrunner 2")
        self.assertIsNone(lf.build_press_release(EN, hook="x" * 120).slot("headline").default)
        self.assertEqual(lf.build_press_release(EN).hook_slot, "headline")

    def test_second_quote_option(self):
        ids = [s.id for s in lf.build_press_release(EN, options={"quotes": 2}).slots]
        self.assertIn("quote_2_name", ids)
        self.assertNotIn("quote_2_name", [s.id for s in lf.build_press_release(EN).slots])

    def test_offline_draft_only_reports_the_brand_only_boilerplate(self):
        d = SPEC["press_release"].build(EN).render(OfflineWriter().fill(SPEC["press_release"].build(EN), EN))
        issues = lf.validate_press_release(d)
        self.assertEqual([i.code for i in issues], ["PR_BOILERPLATE_BRAND_ONLY"])

    def test_good_release_has_no_issues(self):
        d = render_filled("press_release", options={"city": "Prague", "date": "2026-10-12"}, boilerplate=SAMPLES["boilerplate"])
        self.assertEqual(d.slots_open, [])
        self.assertEqual(lf.validate_press_release(d), [])

    def test_headline_lead_and_end_mark_violations(self):
        d = render_filled("press_release", options={"city": "Prague", "date": "2026-10-12"}, headline="H" * 101,
                          lead="Zorvia today launched a shoe. " + words(70))
        codes = {i.code: i for i in lf.validate_press_release(d)}
        self.assertEqual(codes["PR_HEADLINE_LENGTH"].severity, "warn")
        self.assertEqual(codes["PR_LEAD_TOO_LONG"].severity, "warn")
        self.assertLessEqual(len(codes["PR_HEADLINE_LENGTH"].where), 80)
        broken = Draft(format="press_release", lang="en", hook="", body="# Headline\n\nPRAGUE, Oct 1 - Zorvia did a thing.\n\nMore text.", parts={}, meta={"brand": "Zorvia"})
        got = [i.code for i in lf.validate_press_release(broken)]
        self.assertIn("PR_END_MARK_MISSING", got)
        self.assertIn("PR_MEDIA_CONTACT_MISSING", got)
        self.assertIn("PR_QUOTE_MISSING", got)
        self.assertIn("PR_SUBHEAD_MISSING", got)

    def test_missing_headline_and_dateline(self):
        d = Draft(format="press_release", lang="en", hook="", body="Some text without structure at all, just a long sentence about nothing in particular.\n\n###", parts={}, meta={})
        codes = [i.code for i in lf.validate_press_release(d)]
        self.assertIn("PR_HEADLINE_MISSING", codes)
        self.assertIn("PR_DATELINE_MISSING", codes)

    def test_unattributed_quote_is_an_error(self):
        d = render_filled("press_release", options={"city": "Prague", "date": "2026-10-12"})
        slots = dict(d.parts["slots"])
        slots["quote_1_title"] = "[[ADD: Role]]"
        broken = Draft(format="press_release", lang="en", hook="", body=d.body, parts={"slots": slots}, meta=d.meta)
        self.assertIn("PR_QUOTE_UNATTRIBUTED", [i.code for i in lf.validate_press_release(broken)])

    def test_five_w_hint_names_what_is_missing(self):
        d = render_filled("press_release", lead="A new shoe exists and people may like it a lot.")
        hint = [i for i in lf.validate_press_release(d) if i.code == "PR_LEAD_5W"]
        self.assertEqual(len(hint), 1)
        self.assertEqual(hint[0].severity, "info")
        for word in ("who", "when", "where", "why"):
            self.assertIn(word, hint[0].message)

    def test_superlatives_need_substantiation(self):
        bad = render_filled("press_release", options={"city": "Prague", "date": "2026-10-12"}, body_1="Cloudrunner 2 is the best and most innovative shoe, a revolutionary design.")
        found = [i.message for i in lf.validate_press_release(bad) if i.code == "PR_UNSUBSTANTIATED_SUPERLATIVE"]
        self.assertTrue(any("best" in m for m in found) and any("revolutionary" in m for m in found))
        good = render_filled("press_release", options={"city": "Prague", "date": "2026-10-12"},
                             body_1="Cloudrunner 2 is the best rated shoe in our 2025 lab test of 412 runners.")
        self.assertNotIn("PR_UNSUBSTANTIATED_SUPERLATIVE", [i.code for i in lf.validate_press_release(good)])
        cited = render_filled("press_release", options={"city": "Prague", "date": "2026-10-12"}, body_1="It is a unique design. The fit study agrees [[cite:s1]].")
        self.assertNotIn("PR_UNSUBSTANTIATED_SUPERLATIVE", [i.code for i in lf.validate_press_release(cited)])

    def test_czech_superlatives_and_messages(self):
        d = render_filled("press_release", CS, options={"city": "Praha", "date": "2026-10-12"}, body_1="Je to nejlepší a revoluční řešení na trhu.",
                          boilerplate="Zorvia")
        issues = lf.validate_press_release(d)
        self.assertTrue(any(i.code == "PR_UNSUBSTANTIATED_SUPERLATIVE" and "Superlativ" in i.message for i in issues))
        self.assertTrue(any(i.code == "PR_BOILERPLATE_BRAND_ONLY" and "Medailonek" in i.message for i in issues))

    def test_unsubstantiated_superlatives_helper(self):
        self.assertEqual(lf.unsubstantiated_superlatives("We make the best shoes."), ["best"])
        self.assertEqual(lf.unsubstantiated_superlatives("We make the best shoes, rated 4.8 by 300 runners."), [])
        self.assertEqual(lf.unsubstantiated_superlatives("Toto je Nejlepší řešení."), ["nejlepší"])
        self.assertEqual(lf.unsubstantiated_superlatives("The bestseller and the bestowed award."), [])
        self.assertEqual(lf.unsubstantiated_superlatives("It is the world's first shoe that adapts."), ["world's first"])


class LandingPageTests(unittest.TestCase):
    def test_one_primary_cta_is_rendered_in_hero_and_at_the_end(self):
        d = SPEC["landing_page"].build(EN).render(OfflineWriter().fill(SPEC["landing_page"].build(EN), EN))
        self.assertEqual(d.body.count("**[Take the quiz](#cta)**"), 2)
        first, last = d.body.index("**[Take the quiz]"), d.body.rindex("**[Take the quiz]")
        self.assertLess(first, d.body.index("## The problem"))
        self.assertGreater(last, d.body.index("## Ready to start?"))
        custom = lf.build_landing_page(EN, options={"cta_url": "https://zorvia.com/quiz"}).render()
        self.assertEqual(custom.body.count("(https://zorvia.com/quiz)"), 2)
        self.assertEqual(custom.parts["cta_url"], "https://zorvia.com/quiz")

    def test_three_benefits_proof_and_objection_faq(self):
        sk = lf.build_landing_page(EN)
        ids = [s.id for s in sk.slots]
        for i in (1, 2, 3):
            self.assertIn(f"benefit_{i}_title", ids)
            self.assertIn(f"benefit_{i}_body", ids)
        d = sk.render()
        for heading in ("## The problem", "## The solution", "## What you get", "## Proof", "## Questions you may have", "## Ready to start?"):
            self.assertIn(heading, d.body)
        self.assertEqual(sk.hook_slot, "hero_headline")
        self.assertEqual(sk.slot("hero_headline").max_words, 12)

    def test_czech_landing_page(self):
        d = lf.build_landing_page(CS).render()
        for text in ("## Problém", "## Řešení", "## Co získáte", "## Důkazy", "## Na co se lidé ptají", "## Chcete začít?", "### Hodí se to pro mě?", "### Kolik to stojí?"):
            self.assertIn(text, d.body)
        self.assertEqual(d.parts["slots"]["cta"], "Vyzkoušejte test")

    def test_meta_title_default_fits_or_is_absent(self):
        self.assertEqual(lf.build_landing_page(EN).slot("meta_title").default, "Cloudrunner 2 | Zorvia")
        long = Brief(brand="Zorvia", topic="t", audience="a", offer="O" * 55)
        self.assertEqual(lf.build_landing_page(long).slot("meta_title").default, "O" * 55)
        self.assertIsNone(lf.build_landing_page(Brief(brand="B", topic="t", audience="a", offer="O" * 70)).slot("meta_title").default)

    def test_hook_becomes_the_headline_only_when_short(self):
        self.assertEqual(lf.build_landing_page(EN, hook="Find shoes that fit").slot("hero_headline").default, "Find shoes that fit")
        self.assertIsNone(lf.build_landing_page(EN, hook="one two three four five six seven eight nine ten eleven twelve thirteen").slot("hero_headline").default)

    def test_offline_draft_has_no_errors_but_asks_for_proof(self):
        sk = lf.build_landing_page(EN)
        issues = lf.validate_landing_page(sk.render(OfflineWriter().fill(sk, EN)))
        self.assertEqual([i.code for i in issues], ["LANDING_NO_PROOF"])

    def test_good_landing_page_has_no_issues(self):
        d = render_filled("landing_page")
        self.assertEqual(d.slots_open, [])
        self.assertEqual(lf.validate_landing_page(d), [])

    def test_headline_length(self):
        d = render_filled("landing_page", hero_headline="Find running shoes that fit your feet the very first time you buy a pair")
        issue = next(i for i in lf.validate_landing_page(d) if i.code == "LANDING_HEADLINE_LONG")
        self.assertIn("15", issue.message)

    def test_cta_consistency_and_presence(self):
        base = "# Headline\n\nSub.\n\n{a}\n\n## Proof\n\n- 412 runners took part in the lab.\n\n{b}"
        same = Draft(format="landing_page", lang="en", hook="", body=base.format(a="**[Take the quiz](#cta)**", b="**[take the QUIZ](#cta)**"), parts={}, meta={})
        self.assertEqual(lf.validate_landing_page(same), [])
        mixed = Draft(format="landing_page", lang="en", hook="", body=base.format(a="**[Take the quiz](#cta)**", b="**[Buy now](#cta)**"), parts={}, meta={})
        self.assertIn("LANDING_CTA_INCONSISTENT", [i.code for i in lf.validate_landing_page(mixed)])
        once = Draft(format="landing_page", lang="en", hook="", body=base.format(a="**[Take the quiz](#cta)**", b=""), parts={}, meta={})
        self.assertIn("LANDING_CTA_NOT_REPEATED", [i.code for i in lf.validate_landing_page(once)])
        none = Draft(format="landing_page", lang="en", hook="", body=base.format(a="", b=""), parts={}, meta={})
        issue = next(i for i in lf.validate_landing_page(none) if i.code == "LANDING_CTA_MISSING")
        self.assertEqual(issue.severity, "error")

    def test_proof_present_or_missing(self):
        d = render_filled("landing_page", proof_stat_1="[[ADD: x]]")
        self.assertNotIn("LANDING_NO_PROOF", [i.code for i in lf.validate_landing_page(d)])
        slots = dict(d.parts["slots"])
        for key in ("proof_stat_1", "proof_stat_2", "testimonial_quote"):
            slots[key] = "[[ADD: placeholder]]"
        empty = Draft(format="landing_page", lang="en", hook="", body=d.body, parts={"slots": slots}, meta=d.meta)
        self.assertIn("LANDING_NO_PROOF", [i.code for i in lf.validate_landing_page(empty)])
        crafted = Draft(format="landing_page", lang="en", hook="", body="# H\n\n**[Go](#cta)**\n\n## Proof\n\nNothing yet.\n\n**[Go](#cta)**", parts={}, meta={})
        self.assertIn("LANDING_NO_PROOF", [i.code for i in lf.validate_landing_page(crafted)])

    def test_meta_lengths_and_superlatives(self):
        d = render_filled("landing_page", meta_title="T" * 70, meta_description="Too short.", solution="We are the best and the leading option, a revolutionary shoe.")
        codes = [i.code for i in lf.validate_landing_page(d)]
        self.assertIn("LANDING_META_TITLE_LENGTH", codes)
        self.assertIn("LANDING_META_DESCRIPTION_LENGTH", codes)
        self.assertIn("LANDING_UNSUBSTANTIATED_SUPERLATIVE", codes)

    def test_czech_issue_messages(self):
        d = render_filled("landing_page", CS, hero_headline="Najděte běžecké boty které vám sednou hned napoprvé a bez zbytečných chyb při výběru")
        issue = next(i for i in lf.validate_landing_page(d) if i.code == "LANDING_HEADLINE_LONG")
        self.assertIn("Hlavní titulek", issue.message)


class NewsletterTests(unittest.TestCase):
    def test_structure_and_footer(self):
        sk = lf.build_newsletter(EN)
        d = sk.render(OfflineWriter().fill(sk, EN))
        self.assertTrue(d.body.startswith("Subject: [[ADD:"))
        self.assertIn("Preheader: [[ADD:", d.body)
        self.assertEqual(d.body.count("**[Take the quiz](#cta)**"), 1)
        self.assertIn("## Quick hits", d.body)
        self.assertIn("You are receiving this email because you subscribed to updates from Zorvia. You can unsubscribe at any time", d.body)
        self.assertEqual(sk.hook_slot, "hook")
        self.assertEqual(sk.slot("subject").max_chars, 50)
        self.assertEqual(lf.build_newsletter(EN, hook="Fit beats price").slot("hook").default, "Fit beats price")

    def test_czech_newsletter(self):
        d = lf.build_newsletter(CS).render()
        self.assertTrue(d.body.startswith("Předmět: [[ADD:"))
        self.assertIn("## Ve zkratce", d.body)
        self.assertIn("Odběr můžete kdykoli zrušit pomocí odkazu pro odhlášení", d.body)
        self.assertIn("od Zorvia", d.body)

    def test_offline_draft_has_no_validation_issues_and_good_draft_neither(self):
        sk = lf.build_newsletter(EN)
        self.assertEqual(lf.validate_newsletter(sk.render(OfflineWriter().fill(sk, EN))), [])
        good = render_filled("newsletter")
        self.assertEqual(good.slots_open, [])
        self.assertEqual(lf.validate_newsletter(good), [])

    def test_subject_rules(self):
        for subject, code, severity in (("S" * 55, "SUBJECT_TOO_LONG", "warn"), ("RE: your order", "SUBJECT_DECEPTIVE", "error"),
                                        ("Fwd: Important update", "SUBJECT_DECEPTIVE", "error"), ("FINAL NOTICE TO ALL RUNNERS", "SUBJECT_ALL_CAPS", "warn"),
                                        ("Look at this!!!", "SUBJECT_PUNCTUATION", "warn")):
            issues = lf.validate_newsletter(render_filled("newsletter", subject=subject))
            hit = [i for i in issues if i.code == code]
            self.assertEqual([i.severity for i in hit], [severity], subject)
        czech = lf.validate_newsletter(render_filled("newsletter", CS, subject="Odp: vaše objednávka"))
        self.assertIn("klamavé", next(i for i in czech if i.code == "SUBJECT_DECEPTIVE").message)

    def test_preheader_rules(self):
        codes = lambda **kw: [i.code for i in lf.validate_newsletter(render_filled("newsletter", **kw))]
        self.assertIn("PREHEADER_REPEATS_SUBJECT", codes(preheader="Three fit checks before you buy"))
        self.assertIn("PREHEADER_TOO_LONG", codes(preheader="p" * 120))
        crafted = Draft(format="newsletter", lang="en", hook="", body="Subject: A good subject\n\n## Story\n\ntext\n\n### One\n\nx\n\n### Two\n\ny\n\nunsubscribe here", parts={}, meta={})
        self.assertIn("PREHEADER_MISSING", [i.code for i in lf.validate_newsletter(crafted)])

    def test_unsubscribe_cta_and_structure_rules(self):
        crafted = Draft(format="newsletter", lang="en", hook="", body="Subject: A good subject\nPreheader: Something extra here\n\nHello.", parts={}, meta={})
        issues = {i.code: i.severity for i in lf.validate_newsletter(crafted)}
        self.assertEqual(issues["NEWSLETTER_NO_UNSUBSCRIBE"], "error")
        self.assertEqual(issues["NEWSLETTER_NO_CTA"], "warn")
        self.assertEqual(issues["NEWSLETTER_STRUCTURE"], "warn")
        two = render_filled("newsletter")
        two = Draft(format="newsletter", lang="en", hook="", body=two.body + "\n\n**[Second action](#cta)**", parts=two.parts, meta=two.meta)
        self.assertIn("NEWSLETTER_MULTIPLE_CTA", [i.code for i in lf.validate_newsletter(two)])
        no_subject = Draft(format="newsletter", lang="en", hook="", body="## Story\n\nunsubscribe", parts={}, meta={})
        self.assertIn("NEWSLETTER_SUBJECT_MISSING", [i.code for i in lf.validate_newsletter(no_subject)])

    def test_unsubscribe_detection_without_diacritics_and_in_czech(self):
        for text in ("Unsubscribe", "opt out", "Odhlásit odběr", "odhlaseni", "Zrušit odběr kdykoli"):
            self.assertTrue(lf._has_unsubscribe(text), text)
        self.assertFalse(lf._has_unsubscribe("Subscribe now"))


class EmailSequenceTests(unittest.TestCase):
    def test_goals_and_timing_by_length(self):
        expected = {3: ["welcome", "value", "offer"], 4: ["welcome", "value", "proof", "offer"], 5: ["welcome", "value", "proof", "offer", "last_call"]}
        days = [0, 2, 4, 7, 9]
        for n, goals in expected.items():
            sk = lf.build_email_sequence(EN, options={"emails": n})
            self.assertEqual([t["goal"] for t in sk.fixed["timing"]], goals)
            self.assertEqual([t["day"] for t in sk.fixed["timing"]], days[:n])
            self.assertEqual(sk.fixed["emails"], n)
            self.assertEqual(len([s for s in sk.slots if s.id.endswith("_subject")]), n)
        self.assertEqual(lf.build_email_sequence(EN).fixed["emails"], 4)
        self.assertEqual(lf.build_email_sequence(EN, options={"emails": 1}).fixed["emails"], 3)
        self.assertEqual(lf.build_email_sequence(EN, options={"emails": 12}).fixed["emails"], 5)
        self.assertEqual(lf.build_email_sequence(EN, options={"emails": "x"}).fixed["emails"], 4)

    def test_each_email_has_subject_preheader_body_one_cta_and_unsubscribe_line(self):
        d = lf.build_email_sequence(EN, options={"emails": 5}).render()
        blocks = re.split(r"(?m)^## Email \d+: ", d.body)[1:]
        self.assertEqual(len(blocks), 5)
        for block in blocks:
            self.assertEqual(block.count("Subject: "), 1)
            self.assertEqual(block.count("Preheader: "), 1)
            self.assertEqual(block.count("**[Take the quiz](#cta)**"), 1)
            self.assertIn("unsubscribe", block)
        self.assertIn("## Email 1: Welcome (day 0)", d.body)
        self.assertIn("## Email 5: Last call (day 9)", d.body)
        self.assertEqual(d.parts["timing"][3], {"n": 4, "goal": "offer", "day": 7})

    def test_czech_sequence(self):
        d = lf.build_email_sequence(CS).render()
        self.assertIn("## E-mail 1: Uvítání (den 0)", d.body)
        self.assertIn("## E-mail 4: Nabídka (den 7)", d.body)
        self.assertIn("Předmět: [[ADD:", d.body)
        self.assertIn("odkazu pro odhlášení", d.body)

    def test_last_call_never_invents_urgency(self):
        sk = lf.build_email_sequence(EN, options={"emails": 5})
        instruction = sk.slot("e5_body").instruction
        self.assertIn("no fake urgency", instruction)
        self.assertIn("supplied facts", instruction)

    def test_offline_and_good_sequences_are_clean(self):
        sk = lf.build_email_sequence(EN)
        self.assertEqual(lf.validate_email_sequence(sk.render(OfflineWriter().fill(sk, EN))), [])
        good = render_filled("email_sequence")
        self.assertEqual(good.slots_open, [])
        self.assertEqual(lf.validate_email_sequence(good), [])

    def test_validator_catches_per_email_violations(self):
        d = render_filled("email_sequence", e2_subject="RE: our chat", e3_subject="S" * 60, e1_preheader="Three fit checks before you buy")
        issues = lf.validate_email_sequence(d)
        by_code = {i.code: i for i in issues}
        self.assertEqual(by_code["SUBJECT_DECEPTIVE"].severity, "error")
        self.assertIn("[email 2]", by_code["SUBJECT_DECEPTIVE"].message)
        self.assertIn("[email 3]", by_code["SUBJECT_TOO_LONG"].message)
        self.assertEqual(by_code["PREHEADER_REPEATS_SUBJECT"].where, "Three fit checks before you buy")

    def test_cta_and_unsubscribe_rules(self):
        d = render_filled("email_sequence")
        body = d.body.replace("**[Take the quiz](#cta)**", "**[Take the quiz](#cta)**\n\n**[Another action](#cta)**", 1)
        body = body.replace("You are receiving this email because you subscribed to updates from Zorvia. You can unsubscribe at any time using the unsubscribe link in this email.", "Thanks.", 1)
        issues = lf.validate_email_sequence(Draft(format="email_sequence", lang="en", hook="", body=body, parts=d.parts, meta=d.meta))
        self.assertEqual([(i.code, i.where) for i in issues if i.code in ("EMAIL_MULTIPLE_CTA", "EMAIL_NO_UNSUBSCRIBE")],
                         [("EMAIL_MULTIPLE_CTA", "email 1"), ("EMAIL_NO_UNSUBSCRIBE", "email 1")])
        no_cta = Draft(format="email_sequence", lang="en", hook="", body="## Email 1: Welcome (day 0)\n\nSubject: Hello there friend\nPreheader: Something new\n\nBody.\n\nunsubscribe", parts={}, meta={})
        codes = [i.code for i in lf.validate_email_sequence(no_cta)]
        self.assertIn("EMAIL_NO_CTA", codes)
        self.assertIn("SEQUENCE_LENGTH", codes)

    def test_timing_validation(self):
        d = render_filled("email_sequence")
        bad = Draft(format="email_sequence", lang="en", hook="", body=d.body, parts={"timing": [{"day": 0}, {"day": 4}, {"day": 3}, {"day": 7}]}, meta=d.meta)
        self.assertIn("SEQUENCE_TIMING", [i.code for i in lf.validate_email_sequence(bad)])
        late_start = Draft(format="email_sequence", lang="en", hook="", body=d.body, parts={"timing": [{"day": 1}, {"day": 2}]}, meta=d.meta)
        self.assertIn("SEQUENCE_TIMING", [i.code for i in lf.validate_email_sequence(late_start)])
        self.assertNotIn("SEQUENCE_TIMING", [i.code for i in lf.validate_email_sequence(d)])

    def test_czech_issue_messages(self):
        d = render_filled("email_sequence", CS, e1_subject="Fwd: důležité")
        issue = next(i for i in lf.validate_email_sequence(d) if i.code == "SUBJECT_DECEPTIVE")
        self.assertIn("[email 1]", issue.message)
        self.assertIn("klamavé", issue.message)


if __name__ == "__main__":
    unittest.main()
