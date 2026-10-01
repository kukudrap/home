import unittest

from dopamine_king.generate import ads
from dopamine_king.generate.ads import (
    HEADLINE_MIX, claim_hits, linkedin_default_button, rsa_headline_defaults, subject_problems,
)
from dopamine_king.generate.formats import build_skeleton, formats_by_module, get_format, validate_draft
from dopamine_king.generate.types import Brief, OfflineWriter

CS_FORMS = {"gen": "běžeckých bot", "acc": "běžecké boty", "loc": "běžeckých botách", "ins": "běžeckými botami", "dat": "běžeckým botám"}
ADS_IDS = formats_by_module()["ads"]


def en(**kw):
    base = dict(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="running shoes for flat feet",
                cta="Shop the fit guide", offer="Free fit consultation", secondary_keywords=["flat feet shoes", "arch support"],
                facts=["Tested by 1,200 runners over 6 months"])
    base.update(kw)
    return Brief(**base)


def cs(**kw):
    base = dict(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", keyword="běžecké boty pro ploché nohy",
                cta="Vyberte si boty", offer="Poradenství zdarma", topic_forms=dict(CS_FORMS))
    base.update(kw)
    return Brief(**base)


def render(fid, brief, fills=None, **kw):
    sk = build_skeleton(fid, brief, **kw)
    values = OfflineWriter().fill(sk, brief)
    values.update(fills or {})
    return sk, sk.render(values)


def check(fid, brief, fills=None, **kw):
    _, draft = render(fid, brief, fills, **kw)
    return get_format(fid).validate(draft)


def codes(found):
    return {i.code for i in found}


def severity(found, code):
    return {i.severity for i in found if i.code == code}


RSA_KW = "flat feet running shoes"


def rsa_en(**kw):
    return en(keyword=RSA_KW, **kw)


def full_rsa(keyword=RSA_KW):
    """A fully filled, valid set of RSA assets: the keyword sits in three headlines and every description."""
    fills = {}
    for i in range(1, 16):
        fills[f"h{i:02d}"] = [keyword, f"Our {keyword}", f"Shop {keyword}"][i - 1] if i <= 3 else f"Distinct headline {i}"
    for i, letter in enumerate("ABCD", 1):
        fills[f"d{i}"] = f"Description {letter} about {keyword} with a clear next step."
    fills["substantiation"] = "n/a"
    return fills


class GoogleRsaTests(unittest.TestCase):
    def test_slots_and_limits(self):
        sk = build_skeleton("google_rsa", en())
        ids = [s.id for s in sk.slots]
        self.assertEqual(ids[:15], [f"h{i:02d}" for i in range(1, 16)])
        self.assertEqual(ids[15:19], ["d1", "d2", "d3", "d4"])
        self.assertEqual(ids[-1], "substantiation")
        self.assertTrue(all(sk.slot(f"h{i:02d}").max_chars == 30 for i in range(1, 16)))
        self.assertTrue(all(sk.slot(f"d{i}").max_chars == 90 for i in range(1, 5)))
        self.assertEqual(sk.hook_slot, "h01")
        self.assertEqual(get_format("google_rsa").limits["headline_chars"], 30)

    def test_headline_mix_guidance(self):
        sk = build_skeleton("google_rsa", en())
        mix = sk.fixed["headline_mix"]
        self.assertEqual({k: len(v) for k, v in mix.items()}, {"keyword": 4, "benefit": 4, "proof": 3, "cta": 2, "brand": 2})
        flat = [i for ids in mix.values() for i in ids]
        self.assertEqual(sorted(flat), [f"h{i:02d}" for i in range(1, 16)])
        self.assertEqual(mix, HEADLINE_MIX)
        self.assertIn("keyword type", sk.slot("h02").instruction)
        self.assertIn("benefit type", sk.slot("h05").instruction)
        self.assertIn("proof type", sk.slot("h09").instruction)
        self.assertIn("call to action", sk.slot("h12").instruction)
        self.assertIn("brand type", sk.slot("h14").instruction)

    def test_defaults_come_only_from_the_brief_and_fit(self):
        sk = build_skeleton("google_rsa", en())
        defaults = {s.id: s.default for s in sk.slots if s.default}
        self.assertEqual(defaults["h01"], "Running shoes for flat feet")
        self.assertEqual(defaults["h02"], "Running shoes")
        self.assertEqual(defaults["h03"], "Flat feet shoes")
        self.assertEqual(defaults["h04"], "Arch support")
        self.assertEqual(defaults["h12"], "Shop the fit guide")
        self.assertEqual(defaults["h13"], "Free fit consultation")
        self.assertEqual(defaults["h14"], "Zorvia")
        self.assertEqual(defaults["h15"], "Zorvia: running shoes")
        self.assertEqual(defaults["d4"], "Shop the fit guide")
        for sid in ("h05", "h06", "h07", "h08", "h09", "h10", "h11", "d1", "d2", "d3", "substantiation"):
            self.assertNotIn(sid, defaults)
        lowered = [v.lower() for k, v in defaults.items() if k.startswith("h")]
        self.assertEqual(len(lowered), len(set(lowered)))
        self.assertTrue(all(len(v) <= 30 for k, v in defaults.items() if k.startswith("h")))

    def test_defaults_skip_text_that_does_not_fit(self):
        long = en(cta="A call to action that is far too long for a headline", offer="x" * 40, keyword="a keyword phrase that is longer than thirty characters")
        defaults = rsa_headline_defaults(long, None)
        self.assertNotIn("h12", defaults)
        self.assertNotIn("h13", defaults)
        self.assertEqual(defaults["h01"], "Running shoes")
        sk = build_skeleton("google_rsa", long)
        self.assertIsNone(sk.slot("d4").default)

    def test_defaults_are_unique_when_keyword_equals_topic(self):
        defaults = rsa_headline_defaults(Brief(brand="Zorvia", topic="running shoes", audience="x"), None)
        self.assertEqual(defaults["h01"], "Running shoes")
        self.assertNotIn("h02", defaults)
        values = [v.lower() for v in defaults.values()]
        self.assertEqual(len(values), len(set(values)))

    def test_hook_argument_goes_to_the_first_headline_when_it_fits(self):
        defaults = rsa_headline_defaults(en(), "Stop guessing your fit")
        self.assertEqual(defaults["h01"], "Stop guessing your fit")
        self.assertEqual(defaults["h02"], "Running shoes for flat feet")
        self.assertEqual(rsa_headline_defaults(en(), "x" * 31)["h01"], "Running shoes for flat feet")

    def test_czech_defaults(self):
        sk, draft = render("google_rsa", cs())
        self.assertEqual(draft.parts["slots"]["h01"], "Běžecké boty pro ploché nohy")
        self.assertEqual(draft.parts["slots"]["h12"], "Vyberte si boty")
        self.assertEqual(draft.parts["slots"]["h13"], "Poradenství zdarma")
        self.assertIn("Nadpisy", draft.body)
        self.assertIn("Doložení tvrzení", draft.body)

    def test_mixed_case_brand_words_keep_their_case(self):
        defaults = rsa_headline_defaults(Brief(brand="eBay", topic="iPhone cases", audience="x"), None)
        self.assertEqual(defaults["h01"], "iPhone cases")
        self.assertEqual(defaults["h14"], "eBay")

    def test_assemble_lists(self):
        sk, draft = render("google_rsa", en())
        self.assertEqual(len(draft.parts["headlines"]), 15)
        self.assertEqual(len(draft.parts["descriptions"]), 4)
        self.assertEqual(draft.parts["headlines"][0], "Running shoes for flat feet")

    def test_valid_set_has_no_issues(self):
        found = check("google_rsa", en(), full_rsa())
        self.assertEqual(found, [])
        self.assertEqual(validate_draft(render("google_rsa", en(), full_rsa())[1]), [])

    def test_every_limit_is_enforced(self):
        found = check("google_rsa", en(), {**full_rsa(), "h05": "x" * 31})
        self.assertEqual([(i.code, i.severity, i.where) for i in found if i.code == "CHAR_LIMIT"], [("CHAR_LIMIT", "error", "h05")])
        found = check("google_rsa", en(), {**full_rsa(), "h06": "y" * 30, "d2": "z" * 91})
        self.assertEqual([(i.where) for i in found if i.code == "CHAR_LIMIT"], ["d2"])
        found = check("google_rsa", cs(), {**full_rsa("běžecké boty"), "h15": "ž" * 31})
        self.assertEqual([i.where for i in found if i.code == "CHAR_LIMIT"], ["h15"])

    def test_duplicates_are_errors(self):
        found = check("google_rsa", en(), {**full_rsa(), "h07": "Distinct headline 8"})
        self.assertEqual(severity(found, "DUPLICATE_ASSET"), {"error"})
        found = check("google_rsa", en(), {**full_rsa(), "h07": "DISTINCT HEADLINE 8!"})
        self.assertIn("DUPLICATE_ASSET", codes(found))
        found = check("google_rsa", en(), {**full_rsa(), "d2": "Description number 1 about running shoes for flat feet with a clear next step."})
        self.assertIn("DUPLICATE_ASSET", codes(found))

    def test_keyword_coverage(self):
        fills = full_rsa()
        for i in (1, 2, 3):
            fills[f"h{i:02d}"] = f"Unrelated headline {i}"
        found = check("google_rsa", en(), fills)
        self.assertEqual(severity(found, "KEYWORD_COVERAGE"), {"warn"})
        fills["h04"] = "Running shoes for flat feet"
        fills["h05"] = "More running shoes for flat feet"
        self.assertNotIn("KEYWORD_COVERAGE", codes(check("google_rsa", en(), fills)))
        fills = full_rsa()
        for i in range(1, 5):
            fills[f"d{i}"] = "A description that never says the phrase."
        self.assertEqual(severity(check("google_rsa", en(), fills), "KEYWORD_COVERAGE"), {"warn"})
        self.assertNotIn("KEYWORD_COVERAGE", codes(check("google_rsa", en())))

    def test_keyword_coverage_ignores_case_and_diacritics(self):
        fills = full_rsa("běžecké boty")
        fills["h01"] = "BEZECKE BOTY pro vás"
        fills["h02"] = "Nejlepší běžecké boty"
        found = check("google_rsa", cs(keyword="běžecké boty"), fills)
        self.assertNotIn("KEYWORD_COVERAGE", codes(found))

    def test_at_most_two_exclamation_headlines(self):
        fills = full_rsa()
        fills.update({"h05": "Run today!", "h06": "Fit matters!"})
        self.assertNotIn("EXCLAMATION_LIMIT", codes(check("google_rsa", en(), fills)))
        fills["h07"] = "Try it now!"
        self.assertEqual(severity(check("google_rsa", en(), fills), "EXCLAMATION_LIMIT"), {"warn"})
        fills = full_rsa()
        fills["d1"] = "Description one! With two! Marks! About running shoes for flat feet."
        self.assertNotIn("EXCLAMATION_LIMIT", codes(check("google_rsa", en(), fills)))

    def test_unsubstantiated_claims_english(self):
        for text in ("Best running shoes", "The #1 choice", "Guaranteed fit", "100% comfort", "Top-rated by runners", "Fastest delivery",
                     "Proven results", "Number one in fit", "World's best shoes", "Risk-free returns"):
            found = check("google_rsa", en(), {**full_rsa(), "h08": text, "substantiation": ""})
            self.assertEqual(severity(found, "UNSUBSTANTIATED_CLAIM"), {"warn"}, text)
            self.assertEqual([i.where for i in found if i.code == "UNSUBSTANTIATED_CLAIM"], ["h08"], text)

    def test_unsubstantiated_claims_czech(self):
        for text in ("Nejlepší běžecké boty", "Zaručeně pohodlné", "Číslo 1 mezi botami", "Nejlevnější doprava", "Garance vrácení peněz",
                     "Jediný správný výběr", "Osvědčený výběr", "Bez rizika"):
            fills = {**full_rsa("běžecké boty"), "h08": text, "substantiation": ""}
            found = check("google_rsa", cs(), fills)
            self.assertEqual(severity(found, "UNSUBSTANTIATED_CLAIM"), {"warn"}, text)

    def test_claims_in_descriptions_are_found_too(self):
        found = check("google_rsa", en(), {**full_rsa(), "d3": "We are the best choice for running shoes for flat feet.", "substantiation": ""})
        self.assertEqual([i.where for i in found if i.code == "UNSUBSTANTIATED_CLAIM"], ["d3"])

    def test_substantiation_note_silences_the_warning(self):
        fills = {**full_rsa(), "h08": "Best running shoes", "substantiation": "Runner's World test, March 2026"}
        self.assertNotIn("UNSUBSTANTIATED_CLAIM", codes(check("google_rsa", en(), fills)))
        fills["substantiation"] = "n/a"
        self.assertIn("UNSUBSTANTIATED_CLAIM", codes(check("google_rsa", en(), fills)))
        fills["substantiation"] = "N/A."
        self.assertIn("UNSUBSTANTIATED_CLAIM", codes(check("google_rsa", en(), fills)))
        fills["substantiation"] = "žádné"
        self.assertIn("UNSUBSTANTIATED_CLAIM", codes(check("google_rsa", cs(), {**full_rsa("běžecké boty"), "h08": "Nejlepší boty", "substantiation": "ne"})))

    def test_claim_detector_has_no_czech_false_positives(self):
        for text in ("Nejen boty, ale i rady", "Nejsou to jen boty", "Nejde o značku", "Our best friends run", "Rest of the range"):
            if text.startswith("Our best"):
                self.assertEqual(claim_hits(text), ["best"])
            else:
                self.assertEqual(claim_hits(text), [], text)
        self.assertEqual(claim_hits("[[ADD: best claim]]"), [])

    def test_all_caps_and_minimum_assets(self):
        found = check("google_rsa", en(), {**full_rsa(), "h09": "BUY NOW"})
        self.assertEqual(severity(found, "ALL_CAPS"), {"warn"})
        self.assertNotIn("ALL_CAPS", codes(check("google_rsa", en(), {**full_rsa(), "h09": "Our SEO and CRM tips"})))
        sk, draft = render("google_rsa", en(), full_rsa())
        draft.parts["slots"] = {k: v for k, v in draft.parts["slots"].items() if k in ("h01", "h02", "d1")}
        draft.slots_open = []
        found = get_format("google_rsa").validate(draft)
        self.assertEqual(severity(found, "TOO_FEW_ASSETS"), {"error"})

    def test_placeholders_do_not_trigger_limit_errors(self):
        found = check("google_rsa", en())
        self.assertEqual([i for i in found if i.severity == "error"], [])


class MetaAdTests(unittest.TestCase):
    def test_slots_and_limits(self):
        sk, draft = render("meta_ad", en())
        ids = [s.id for s in sk.slots]
        for i in (1, 2, 3):
            self.assertEqual(sk.slot(f"primary_{i}").max_chars, 500)
            self.assertEqual(sk.slot(f"headline_{i}").max_chars, 40)
            self.assertEqual(sk.slot(f"description_{i}").max_chars, 30)
            self.assertIn(f"primary_{i}", ids)
        self.assertEqual(len(draft.parts["variants"]), 3)
        self.assertEqual(sk.hook_slot, "primary_1")
        self.assertIn("125", sk.slot("primary_1").instruction)
        self.assertEqual(sk.fixed["visible_chars"], 125)

    def test_defaults_are_distinct_hooks_and_brief_fields(self):
        sk, draft = render("meta_ad", en())
        primaries = [sk.slot(f"primary_{i}").default for i in (1, 2, 3)]
        self.assertEqual(len(set(primaries)), 3)
        self.assertTrue(all(p and len(p) <= 125 for p in primaries))
        self.assertEqual(sk.slot("headline_1").default, "Free fit consultation")
        self.assertEqual(sk.slot("headline_2").default, "Shop the fit guide")
        self.assertEqual(sk.slot("headline_3").default, "Running shoes for flat feet")
        self.assertIsNone(sk.slot("description_1").default)
        sk = build_skeleton("meta_ad", en(), hook="My opening hook")
        self.assertEqual(sk.slot("primary_1").default, "My opening hook")
        self.assertEqual(len({sk.slot(f"primary_{i}").default for i in (1, 2, 3)}), 3)

    def test_limits_are_enforced(self):
        found = check("meta_ad", en(), {"primary_1": "p" * 501, "headline_2": "h" * 41, "description_3": "d" * 31})
        self.assertEqual([(i.code, i.where) for i in found if i.severity == "error"],
                         [("CHAR_LIMIT", "primary_1"), ("CHAR_LIMIT", "headline_2"), ("CHAR_LIMIT", "description_3")])
        found = check("meta_ad", en(), {"primary_1": "p" * 500, "headline_2": "h" * 40, "description_3": "d" * 30})
        self.assertEqual([i for i in found if i.severity == "error"], [])

    def test_visible_text_cut_is_informational(self):
        found = check("meta_ad", en(), {"primary_1": "p" * 200})
        self.assertEqual(severity(found, "VISIBLE_TEXT_CUT"), {"info"})
        found = check("meta_ad", en(), {"primary_1": "p" * 125})
        self.assertNotIn("VISIBLE_TEXT_CUT", codes(found))

    def test_identical_variants_and_claims(self):
        same = "Same text here"
        found = check("meta_ad", en(), {"primary_1": same, "primary_2": same.upper()})
        self.assertEqual(severity(found, "DUPLICATE_ASSET"), {"warn"})
        found = check("meta_ad", en(), {"headline_1": "The best fit in town", "substantiation": ""})
        self.assertEqual([i.where for i in found if i.code == "UNSUBSTANTIATED_CLAIM"], ["headline_1"])
        found = check("meta_ad", cs(), {"primary_2": "Nejlepší boty na trhu", "substantiation": "Test časopisu, 2026"})
        self.assertNotIn("UNSUBSTANTIATED_CLAIM", codes(found))

    def test_czech_variant(self):
        sk, draft = render("meta_ad", cs())
        self.assertIn("Varianta 1", draft.body)
        self.assertIn("Primární text", draft.body)
        self.assertEqual(sk.slot("headline_1").default, "Poradenství zdarma")


class LinkedinAdTests(unittest.TestCase):
    def test_slots(self):
        sk, draft = render("linkedin_ad", en())
        self.assertEqual([s.id for s in sk.slots], ["intro_text", "headline", "cta_button", "substantiation"])
        self.assertEqual(sk.slot("intro_text").max_chars, 600)
        self.assertEqual(sk.slot("headline").max_chars, 200)
        self.assertEqual(sk.fixed["intro_recommended"], 150)
        self.assertEqual(sk.fixed["headline_recommended"], 70)
        self.assertEqual(sk.hook_slot, "intro_text")
        self.assertLessEqual(len(draft.hook), 150)
        self.assertEqual(draft.parts["slots"]["cta_button"], "Learn more")
        self.assertEqual(draft.parts["slots"]["headline"], "Free fit consultation")

    def test_variants_option(self):
        for given, expected in ((None, 1), (2, 2), (3, 3), (0, 1), (9, 3), ("x", 1)):
            opts = None if given is None else {"variants": given}
            sk = build_skeleton("linkedin_ad", en(), options=opts)
            self.assertEqual(sk.fixed["variants"], expected, given)
            self.assertEqual(len([s for s in sk.slots if s.id.startswith("intro_text")]), expected)
        sk = build_skeleton("linkedin_ad", en(), options={"variants": 2})
        self.assertIn("intro_text_2", [s.id for s in sk.slots])
        self.assertIn("headline_2", [s.id for s in sk.slots])
        self.assertNotEqual(sk.slot("intro_text").default, sk.slot("intro_text_2").default)

    def test_default_button_follows_the_cta(self):
        cases = {"Download the guide": "Download", "Stáhněte si průvodce": "Download", "Request a demo": "Request demo", "Register today": "Register",
                 "Zaregistrujte se": "Sign up", "Subscribe now": "Subscribe", "Join us": "Join", "Apply now": "Apply", "Read more": "Learn more", None: "Learn more"}
        for cta, expected in cases.items():
            self.assertEqual(linkedin_default_button(en(cta=cta)), expected, cta)
            self.assertIn(expected, ads.LINKEDIN_CTA_BUTTONS)

    def test_limits(self):
        found = check("linkedin_ad", en(), {"intro_text": "i" * 601, "headline": "h" * 201})
        self.assertEqual([(i.code, i.where) for i in found if i.severity == "error"], [("CHAR_LIMIT", "intro_text"), ("CHAR_LIMIT", "headline")])
        found = check("linkedin_ad", en(), {"intro_text": "i" * 300, "headline": "h" * 100})
        self.assertEqual({i.where for i in found if i.code == "LENGTH_RECOMMENDED"}, {"intro_text", "headline"})
        self.assertEqual(severity(found, "LENGTH_RECOMMENDED"), {"warn"})
        found = check("linkedin_ad", en(), {"intro_text": "i" * 150, "headline": "h" * 70})
        self.assertEqual(found[0].code if found else None, None)

    def test_button_and_claims(self):
        found = check("linkedin_ad", en(), {"cta_button": "Click here"})
        self.assertEqual(severity(found, "INVALID_CTA_BUTTON"), {"error"})
        for button in ads.LINKEDIN_CTA_BUTTONS:
            self.assertNotIn("INVALID_CTA_BUTTON", codes(check("linkedin_ad", en(), {"cta_button": button})))
        found = check("linkedin_ad", en(), {"intro_text": "The leading platform for runners", "substantiation": ""})
        self.assertEqual(severity(found, "UNSUBSTANTIATED_CLAIM"), {"warn"})

    def test_czech(self):
        sk, draft = render("linkedin_ad", cs())
        self.assertEqual(draft.parts["slots"]["cta_button"], "Learn more")
        self.assertIn("Úvodní text", draft.body)
        self.assertIn("Tlačítko", draft.body)
        self.assertEqual(linkedin_default_button(cs(cta="Stáhněte si průvodce výběrem")), "Download")


class EmailSubjectTests(unittest.TestCase):
    def fills(self, **over):
        values = {f"subject_{i:02d}": f"Subject number {i} for runners" for i in range(1, 11)}
        values.update({f"preheader_{i:02d}": f"A preheader that continues the thought for subject {i}" for i in range(1, 11)})
        values.update(over)
        return values

    def test_ten_ranked_subjects(self):
        for brief in (en(), cs(), en(keyword=None), cs(topic_forms={})):
            sk, draft = render("email_subject_set", brief)
            subjects = [s for s in sk.slots if s.id.startswith("subject_")]
            self.assertEqual(len(subjects), 10)
            self.assertTrue(all(s.default and len(s.default) <= 50 and s.max_chars == 50 for s in subjects))
            scores = [r["score"] for r in sk.fixed["subjects"]]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertEqual(len({s.default for s in subjects}), 10)
            self.assertEqual(draft.hook, subjects[0].default)
            self.assertEqual(sk.hook_slot, "subject_01")

    def test_preheader_slots(self):
        sk, draft = render("email_subject_set", en())
        pre = [s for s in sk.slots if s.id.startswith("preheader_")]
        self.assertEqual(len(pre), 10)
        self.assertTrue(all(s.min_chars == 40 and s.max_chars == 100 and s.default is None for s in pre))
        self.assertEqual(len(draft.parts["pairs"]), 10)
        self.assertEqual(len(draft.slots_open), 10)
        self.assertEqual(sk.fixed["preheader_chars"], [40, 100])

    def test_hook_argument_is_pinned_first(self):
        sk = build_skeleton("email_subject_set", en(), hook="Your fit questions answered")
        self.assertEqual(sk.slot("subject_01").default, "Your fit questions answered")
        self.assertEqual(sk.fixed["subjects"][0]["style"], "provided")
        self.assertEqual(len(sk.fixed["subjects"]), 10)

    def test_valid_set_has_no_issues(self):
        self.assertEqual(check("email_subject_set", en(), self.fills()), [])
        self.assertEqual([i for i in check("email_subject_set", en()) if i.severity == "error"], [])

    def test_length_limits(self):
        found = check("email_subject_set", en(), self.fills(subject_03="s" * 51))
        self.assertEqual([(i.code, i.severity, i.where) for i in found if i.code == "CHAR_LIMIT"], [("CHAR_LIMIT", "error", "subject_03")])
        found = check("email_subject_set", en(), self.fills(preheader_04="p" * 101))
        self.assertEqual([(i.code, i.where) for i in found if i.code == "CHAR_LIMIT"], [("CHAR_LIMIT", "preheader_04")])
        found = check("email_subject_set", en(), self.fills(preheader_02="Too short"))
        self.assertEqual(severity(found, "PREHEADER_SHORT"), {"warn"})
        found = check("email_subject_set", en(), self.fills(subject_05="s" * 50, preheader_05="p" * 100))
        self.assertEqual(found, [])

    def test_deceptive_subjects_are_errors(self):
        bad = ["RE: your order", "Fwd: special for you", "FW: invoice", "re:meeting", "FREE!!! shoes", "Hello!! big news", "Is this real?!",
               "HUGE SALE today", "Big SALE inside", "Odp: vaše objednávka", "ZDARMA!!! jen dnes", "Pozor, VÝPRODEJ začíná"]
        for text in bad:
            found = check("email_subject_set", cs() if "ZDARMA" in text or "Odp" in text or "VÝPRODEJ" in text else en(), self.fills(subject_02=text))
            self.assertEqual(severity(found, "DECEPTIVE_SUBJECT"), {"error"}, text)
            self.assertEqual([i.where for i in found if i.code == "DECEPTIVE_SUBJECT"], ["subject_02"], text)

    def test_clean_subjects_are_not_flagged(self):
        for text in ("Our SEO checklist is ready", "One exclamation is fine!", "Is your fit right?", "Re-think your running shoes",
                     "Free fit consultation this week", "Čtyři otázky před nákupem bot", "Fwdtool update", "Résumé tips for 2026"):
            found = check("email_subject_set", en(), self.fills(subject_02=text))
            self.assertNotIn("DECEPTIVE_SUBJECT", codes(found), text)

    def test_subject_problems_helper(self):
        self.assertEqual(subject_problems("Plain subject"), [])
        self.assertEqual(subject_problems("RE: hi"), ["fake reply or forward prefix"])
        self.assertEqual(subject_problems("Wow!! so good"), ["repeated exclamation or question marks"])
        self.assertEqual(subject_problems("SALE"), ["words in ALL CAPS"])
        self.assertEqual(len(subject_problems("RE: SALE!!")), 3)
        self.assertEqual(subject_problems("[[ADD: placeholder RE: text]]"), [])

    def test_spam_words_duplicates_clickbait_and_emoji(self):
        found = check("email_subject_set", en(), self.fills(subject_02="Act now and claim your cash"))
        self.assertEqual(severity(found, "SPAM_WORDS"), {"warn"})
        found = check("email_subject_set", cs(), self.fills(subject_02="Vyhrajte nové boty"))
        self.assertEqual(severity(found, "SPAM_WORDS"), {"warn"})
        found = check("email_subject_set", en(), self.fills(subject_02="Subject number 1 for runners"))
        self.assertEqual(severity(found, "DUPLICATE_ASSET"), {"warn"})
        found = check("email_subject_set", en(), self.fills(subject_02="You won't believe this one trick"))
        self.assertEqual(severity(found, "CLICKBAIT_RISK"), {"warn"})
        found = check("email_subject_set", en(), self.fills(subject_02="New \U0001F680\U0001F525 drop"))
        self.assertEqual(severity(found, "EMOJI_OVERUSE"), {"warn"})
        found = check("email_subject_set", en(), self.fills(preheader_03="Subject number 3 for runners and more"))
        self.assertEqual(severity(found, "PREHEADER_REPEATS"), {"info"})

    def test_czech_set(self):
        sk, draft = render("email_subject_set", cs())
        self.assertIn("Předměty e-mailu", draft.body)
        self.assertIn("**Předmět:**", draft.body)
        self.assertTrue(all("běžeck" in s.default.lower() or "začínající" in s.default.lower() for s in sk.slots if s.id.startswith("subject_")))


class AdsFamilyTests(unittest.TestCase):
    def test_specs(self):
        self.assertEqual(set(ADS_IDS), {"google_rsa", "meta_ad", "linkedin_ad", "email_subject_set"})
        for fid in ("google_rsa", "meta_ad", "linkedin_ad"):
            self.assertEqual(get_format(fid).family, "ad")
        self.assertEqual(get_format("email_subject_set").family, "email")
        self.assertEqual(get_format("google_rsa").platform, "google")
        self.assertEqual(get_format("meta_ad").platform, "meta")
        self.assertEqual(get_format("email_subject_set").limits["subject_chars"], 50)

    def test_offline_drafts_pass_validation_without_errors(self):
        for fid in ADS_IDS:
            for brief in (en(), cs(), en(sponsored=True), cs(keyword=None, facts=[])):
                _, draft = render(fid, brief)
                issues = validate_draft(draft)
                self.assertEqual([i for i in issues if i.severity == "error"], [], (fid, brief.lang))
                self.assertEqual({i.code for i in issues}, {"SLOTS_OPEN"}, (fid, brief.lang))

    def test_defaults_never_carry_claims(self):
        for fid in ADS_IDS:
            for brief in (en(), cs()):
                sk, draft = render(fid, brief)
                self.assertNotIn("UNSUBSTANTIATED_CLAIM", codes(get_format(fid).validate(draft)))

    def test_claim_detector_basics(self):
        self.assertEqual(claim_hits("Guaranteed results"), ["guaranteed"])
        self.assertEqual(claim_hits("Zaručeně nejlepší"), ["zarucene", "nejlepsi"])
        self.assertEqual(claim_hits("A calm, fitted shoe"), [])


if __name__ == "__main__":
    unittest.main()
