import re
import unittest

from dopamine_king.generate import hooks
from dopamine_king.generate.hooks import (
    HOOK_STYLES, STYLE_CAP, HookCandidate, all_templates, best_hook, build_context, choose_hook, generate_hooks,
    list_counts, norm_key, proof_facts, render_template, templates_for,
)
from dopamine_king.generate.types import Brief
from dopamine_king.scoring import score_hook

EM_DASH = chr(0x2014)
CS_FORMS = {"gen": "běžeckých bot", "dat": "běžeckým botám", "acc": "běžecké boty", "loc": "běžeckých botách",
            "ins": "běžeckými botami"}


def en_brief(**kw):
    base = dict(brand="Zorvia", topic="running shoes", audience="beginner runners",
                keyword="best running shoes for flat feet", facts=["Tested by 1,200 runners over 6 months"])
    base.update(kw)
    return Brief(**base)


def cs_brief(**kw):
    base = dict(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs",
                keyword="běžecké boty pro ploché nohy", facts=["Otestovalo je 1 200 běžců"], topic_forms=dict(CS_FORMS))
    base.update(kw)
    return Brief(**base)


def plain(lang="en", **kw):
    if lang == "cs":
        return Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", **kw)
    return Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", **kw)


class GenerationTests(unittest.TestCase):
    def test_deterministic(self):
        for brief in (en_brief(), cs_brief()):
            a = [c.to_dict() for c in generate_hooks(brief, n=20)]
            b = [c.to_dict() for c in generate_hooks(brief, n=20)]
            self.assertEqual(a, b)

    def test_english_and_czech_candidates(self):
        en = generate_hooks(en_brief())
        cs = generate_hooks(cs_brief())
        self.assertGreaterEqual(len(en), 10)
        self.assertGreaterEqual(len(cs), 10)
        self.assertTrue(all(isinstance(c, HookCandidate) for c in en + cs))
        self.assertEqual({c.lang for c in en}, {"en"})
        self.assertEqual({c.lang for c in cs}, {"cs"})
        self.assertTrue(all("running shoes" in c.text.lower() or "beginner runners" in c.text.lower() or "flat feet" in c.text.lower()
                            or "zorvia" in c.text.lower() for c in en))
        self.assertTrue(any("běžeck" in c.text.lower() for c in cs))

    def test_scores_are_sorted_and_match_the_scorer(self):
        for brief in (en_brief(), cs_brief()):
            found = generate_hooks(brief, n=36)
            self.assertEqual([c.score for c in found], sorted((c.score for c in found), reverse=True))
            for c in found:
                s = score_hook(c.text, lang=brief.lang)
                self.assertEqual(c.score, round(s.total, 2))
                self.assertEqual(c.clickbait_risk, round(s.clickbait_risk, 4))

    def test_n_limits_the_result(self):
        self.assertEqual(len(generate_hooks(en_brief(), n=3)), 3)
        self.assertEqual(generate_hooks(en_brief(), n=0), [])

    def test_risk_filter(self):
        risky = en_brief(topic="guaranteed overnight results", keyword=None)
        strict = generate_hooks(risky, n=36)
        relaxed = generate_hooks(risky, n=36, max_risk=1.0)
        self.assertTrue(all(c.clickbait_risk <= 0.35 for c in strict))
        self.assertGreater(len(relaxed), len(strict))
        self.assertTrue(any(c.clickbait_risk > 0.35 for c in relaxed))
        zero = generate_hooks(en_brief(), n=36, max_risk=0.0)
        self.assertTrue(all(c.clickbait_risk == 0 for c in zero))

    def test_diversity_cap_per_style(self):
        for brief in (en_brief(), cs_brief()):
            found = generate_hooks(brief, n=36)
            counts = {}
            for c in found:
                counts[c.style] = counts.get(c.style, 0) + 1
            self.assertLessEqual(max(counts.values()), STYLE_CAP)
            self.assertGreaterEqual(len(counts), 8)

    def test_restricted_styles_lift_the_cap(self):
        found = generate_hooks(en_brief(), n=8, styles=["how_to"])
        self.assertGreater(len(found), STYLE_CAP)
        self.assertEqual({c.style for c in found}, {"how_to"})
        two = generate_hooks(en_brief(), n=40, styles=("question", "myth_bust"))
        self.assertEqual({c.style for c in two}, {"question", "myth_bust"})

    def test_a_single_style_name_is_accepted(self):
        self.assertEqual({c.style for c in generate_hooks(en_brief(), n=5, styles="how_to")}, {"how_to"})

    def test_unknown_style_raises(self):
        with self.assertRaises(ValueError) as ctx:
            generate_hooks(en_brief(), styles=["clickbait"])
        self.assertIn("curiosity_gap", str(ctx.exception))

    def test_max_chars_and_max_words(self):
        for limit in (30, 45, 60):
            found = generate_hooks(en_brief(), n=36, max_chars=limit)
            self.assertTrue(found)
            self.assertTrue(all(len(c.text) <= limit for c in found), limit)
        short = generate_hooks(cs_brief(), n=36, max_words=6)
        self.assertTrue(short)
        self.assertTrue(all(len(c.text.split()) <= 6 for c in short))

    def test_near_duplicates_are_dropped(self):
        found = generate_hooks(en_brief(), n=36, styles=list(HOOK_STYLES))
        keys = [norm_key(c.text, "en") for c in found]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(norm_key("Jak  začít?", "cs"), norm_key("jak zacit", "cs"))

    def test_keyword_equal_to_topic_adds_no_duplicates(self):
        brief = en_brief(keyword="Running shoes")
        self.assertNotIn("keyword", build_context(brief))
        self.assertEqual(len({norm_key(c.text, "en") for c in generate_hooks(brief, n=36)}), len(generate_hooks(brief, n=36)))

    def test_every_hook_starts_with_a_capital_and_has_no_stray_whitespace(self):
        for brief in (en_brief(), cs_brief(), plain(), plain("cs")):
            for c in generate_hooks(brief, n=36):
                self.assertTrue(c.text[0].isupper() or c.text[0].isdigit(), c.text)
                self.assertEqual(c.text, " ".join(c.text.split()))
                self.assertNotIn("{", c.text)

    def test_sentence_start_after_question_mark_is_capitalised(self):
        found = generate_hooks(cs_brief(), n=36, styles=["myth_bust"])
        self.assertTrue(any("Mýtus, nebo pravda? Běžecké boty" == c.text for c in found))

    def test_audience_is_optional(self):
        found = generate_hooks(Brief(brand="Zorvia", topic="running shoes", audience=""), n=36)
        self.assertTrue(found)
        self.assertTrue(all("  " not in c.text and "{" not in c.text for c in found))


class StyleRuleTests(unittest.TestCase):
    def test_proof_skipped_without_numeric_fact(self):
        for brief in (plain(), plain("cs"), plain(facts=["We love running"]), plain(facts=["Founded in 2019"])):
            found = generate_hooks(brief, n=36, styles=["proof"])
            self.assertEqual(found, [], brief.facts)
            self.assertNotIn("proof", {c.style for c in generate_hooks(brief, n=36)})

    def test_proof_uses_the_real_fact_verbatim(self):
        found = generate_hooks(en_brief(), n=36, styles=["proof"])
        self.assertGreaterEqual(len(found), 6)
        self.assertTrue(all("Tested by 1,200 runners over 6 months" in c.text for c in found))
        found_cs = generate_hooks(cs_brief(), n=36, styles=["proof"])
        self.assertTrue(found_cs)
        self.assertTrue(all("Otestovalo je 1 200 běžců" in c.text for c in found_cs))

    def test_proof_rotates_through_several_facts(self):
        brief = en_brief(facts=["Tested by 1,200 runners", "Returns accepted within 30 days"])
        texts = " ".join(c.text for c in generate_hooks(brief, n=36, styles=["proof"]))
        self.assertIn("1,200 runners", texts)
        self.assertIn("30 days", texts)

    def test_long_facts_are_not_used_as_proof(self):
        long_fact = "Tested by 1,200 runners " + "and more " * 20
        self.assertEqual(proof_facts(plain(facts=[long_fact])), [])
        self.assertEqual(proof_facts(plain(facts=["Founded in 2019, 1,200 runners tested it."])), ["Founded in 2019, 1,200 runners tested it"])

    def test_list_counts_default_and_from_facts(self):
        self.assertEqual(list_counts(plain(), "en"), [7, 5])
        self.assertEqual(list_counts(plain(facts=["We publish 9 tips every month"]), "en"), [9])
        self.assertEqual(list_counts(plain(facts=["3 steps to a better fit"]), "en"), [3])
        self.assertEqual(list_counts(plain("cs", facts=["3 kroky k lepší obuvi"]), "cs"), [7, 5])
        self.assertEqual(list_counts(plain("cs", facts=["Máme 6 tipů pro začátečníky"]), "cs"), [6])
        self.assertEqual(list_counts(plain(facts=["Tested by 1,200 runners"]), "en"), [7, 5])

    def test_number_list_uses_the_count(self):
        found = generate_hooks(plain(facts=["9 tips for new runners"]), n=10, styles=["number_list"])
        self.assertTrue(all(c.text.startswith("9 ") for c in found if c.text[0].isdigit()))
        default = generate_hooks(plain(), n=10, styles=["number_list"])
        self.assertTrue({c.text.split()[0] for c in default if c.text[0].isdigit()} <= {"5", "7"})

    def test_czech_without_forms_never_uses_case_templates(self):
        found = generate_hooks(plain("cs"), n=36, styles=list(HOOK_STYLES))
        for c in found:
            self.assertNotIn("botách", c.text)
            self.assertNotIn("bot,", c.text)
        self.assertTrue(all("běžecké boty" in c.text.lower() or "začínající" in c.text.lower() for c in found))

    def test_czech_forms_are_used_when_given(self):
        texts = " | ".join(c.text for c in generate_hooks(cs_brief(), n=36, styles=list(HOOK_STYLES)))
        self.assertIn("běžeckých botách", texts)
        self.assertTrue("běžeckých bot" in texts)

    def test_czech_counts_are_never_below_five(self):
        found = generate_hooks(plain("cs", facts=["3 kroky k lepší obuvi"]), n=36, styles=["number_list", "challenge", "myth_bust"])
        for c in found:
            for m in re.finditer(r"\b(\d+) (?:chyb|mýtů|dní|kroků|tipů|věcí)", c.text):
                self.assertGreaterEqual(int(m.group(1)), 5, c.text)


class BestHookTests(unittest.TestCase):
    def test_best_hook_is_the_top_candidate(self):
        brief = en_brief()
        self.assertEqual(best_hook(brief), generate_hooks(brief, n=1)[0])
        self.assertIsInstance(best_hook(cs_brief()), HookCandidate)

    def test_best_hook_respects_limits(self):
        h = best_hook(en_brief(), max_chars=40)
        self.assertLessEqual(len(h.text), 40)
        h = best_hook(cs_brief(), max_words=5)
        self.assertLessEqual(len(h.text.split()), 5)

    def test_best_hook_falls_back_when_everything_is_filtered(self):
        h = best_hook(en_brief(topic="a very long topic that never fits"), max_chars=8)
        self.assertEqual(h.style, hooks.HOOK_PLAIN)
        self.assertLessEqual(len(h.text), 8)
        self.assertTrue(h.text)

    def test_best_hook_relaxes_risk_once(self):
        risky = en_brief(topic="guaranteed miracle cure", keyword=None, audience="")
        h = best_hook(risky, max_risk=0.0)
        self.assertTrue(h.text)

    def test_a_supplied_hook_that_breaks_the_limits_is_replaced(self):
        brief = en_brief()
        long_hook = "This supplied hook is much longer than a three second video beat allows"
        self.assertEqual(choose_hook(brief, long_hook), long_hook)
        replaced = choose_hook(brief, long_hook, max_words=7)
        self.assertNotEqual(replaced, long_hook)
        self.assertLessEqual(len(replaced.split()), 7)
        self.assertEqual(choose_hook(brief, "Five words fit here fine", max_words=7), "Five words fit here fine")
        self.assertNotEqual(choose_hook(brief, long_hook, max_chars=30), long_hook)
        self.assertLessEqual(len(choose_hook(brief, long_hook, max_chars=30)), 30)
        self.assertTrue(hooks.hook_fits("abc", 3, 1))
        self.assertFalse(hooks.hook_fits("abcd", 3))
        self.assertFalse(hooks.hook_fits("a b", None, 1))

    def test_choose_hook(self):
        self.assertEqual(choose_hook(en_brief(), "  My own hook "), "My own hook")
        self.assertEqual(choose_hook(en_brief()), best_hook(en_brief()).text)
        picked = choose_hook(en_brief(), prefer="flat feet")
        self.assertIn("flat feet", picked.lower())
        self.assertLessEqual(len(choose_hook(en_brief(), max_chars=35)), 35)


class TemplateLibraryTests(unittest.TestCase):
    def test_all_styles_have_templates_in_both_languages(self):
        for lang in ("en", "cs"):
            for style in HOOK_STYLES:
                self.assertGreaterEqual(len(templates_for(lang, style)), 6, (lang, style))
        self.assertEqual(set(hooks.TEMPLATES_EN), set(HOOK_STYLES))
        self.assertEqual(set(hooks.TEMPLATES_CS), set(HOOK_STYLES))

    def test_base_templates_are_usable_without_keyword_forms_or_facts(self):
        for lang in ("en", "cs"):
            ctx = build_context(plain(lang))
            ctx["n"] = "7"
            for style in HOOK_STYLES:
                if style == "proof":
                    continue
                usable = [t for t in templates_for(lang, style) if "{fact}" not in t and render_template(t, ctx)]
                self.assertGreaterEqual(len(usable), 6, (lang, style))

    def test_no_em_dash_or_fancy_punctuation_in_any_template(self):
        for lang, style, text in all_templates():
            self.assertNotIn(EM_DASH, text)
            self.assertNotIn(chr(0x2013), text)
            self.assertNotIn(chr(0x2026), text)
            self.assertFalse(set(text) & {chr(c) for c in (0x201c, 0x201d, 0x201e, 0x2019, 0x2018)}, text)
            if lang == "en":
                self.assertTrue(text.isascii(), text)

    def test_every_template_renders_without_leftover_braces(self):
        for lang in ("en", "cs"):
            full_brief = en_brief() if lang == "en" else cs_brief()
            full = build_context(full_brief)
            full.update({"n": "7", "fact": proof_facts(full_brief)[0]})
            bare = build_context(plain(lang))
            bare.update({"n": "7"})
            for style in HOOK_STYLES:
                for template in templates_for(lang, style):
                    text = render_template(template, full)
                    self.assertIsNotNone(text, template)
                    self.assertNotRegex(text, r"[{}]", template)
                    out = render_template(template, bare)
                    if out is not None:
                        self.assertNotRegex(out, r"[{}]", template)
                    else:
                        self.assertRegex(template, r"\{(?:keyword|fact|topic_\w+)\}")

    def test_czech_case_templates_require_the_matching_form(self):
        ctx = build_context(plain("cs"))
        for style, items in hooks.TEMPLATES_CS_CASES.items():
            for t in items:
                needs = set(re.findall(r"\{topic_(\w+)\}", t))
                if needs:
                    self.assertIsNone(render_template(t, {**ctx, "n": "7", "fact": "x 1"}), t)
        partial = build_context(plain("cs", topic_forms={"loc": "běžeckých botách"}))
        self.assertEqual(render_template("Pravda o {topic_loc}", partial), "Pravda o běžeckých botách")
        self.assertIsNone(render_template("Pravda o {topic_gen}", partial))

    def test_templates_use_only_known_fields(self):
        known = {"topic", "audience", "keyword", "brand", "n", "fact", "topic_gen", "topic_dat", "topic_acc", "topic_loc", "topic_ins"}
        for _, _, text in all_templates():
            self.assertTrue(set(re.findall(r"\{(\w+)\}", text)) <= known, text)

    def test_czech_templates_carry_diacritics_naturally(self):
        czech = " ".join(t for lang, _, t in all_templates() if lang == "cs")
        for word in ("přestaňte", "děláte", "příběh", "výzva", "mýtus"):
            self.assertIn(word, czech)

    def test_render_capitalises_but_keeps_brand_start(self):
        self.assertEqual(render_template("{topic}: x", {"topic": "running shoes"}), "Running shoes: x")
        self.assertEqual(render_template("{brand} says", {"brand": "eBay"}), "eBay says")
        self.assertIsNone(render_template("{topic} {audience}", {"topic": "a"}))


if __name__ == "__main__":
    unittest.main()
