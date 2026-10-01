import json
import re
import unittest

from dopamine_king.generate import geo
from dopamine_king.generate.types import Brief, Draft, OfflineWriter

SOURCES = [
    {"id": "s1", "title": "Footwear fit study", "url": "https://example.org/study", "claim": "Fit matters for injury risk"},
    {"id": "s2", "title": "Runner guide", "url": "https://example.org/guide", "claim": "Replace shoes regularly"},
    {"id": "s3", "title": "Gait survey", "url": "https://example.org/survey", "claim": "Most beginners skip a gait check"},
]
FACTS = ["Weight: 240 g", "In our 2025 gait lab, 38% of 412 beginner runners picked shoes that did not match their foot type."]
EN = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="running shoes for flat feet",
           cta="Take the quiz", facts=FACTS, sources=SOURCES)
CS = Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", keyword="běžecké boty",
           facts=["Hmotnost: 240 g"], sources=SOURCES)
BARE = Brief(brand="Acme", topic="project management software", audience="small teams")

STRONG_FILLS = {
    "definition": ("Running shoes for flat feet are shoes with firm arch support and a stable heel that keep the foot from rolling inward. "
                   "Zorvia is a running shoe maker that fits shoes to beginner runners using a short gait check. "
                   "The check takes ten minutes and needs no special equipment at all."),
    "steps": "1. Take a gait check.\n2. Pick a stable shoe.\n3. Test it in the afternoon.",
    "comparison_table": "| Option | Support |\n|---|---|\n| Stability shoe | High |\n| Neutral shoe | Low |",
    "stat_1": "About 38% of beginners pick the wrong shoe type [[cite:s1]].",
    "stat_2": "A typical pair lasts 600 km before the midsole flattens [[cite:s2]].",
    "stat_3": "Around 25% of runners report heel slip in new shoes [[cite:s3]].",
    "quote_1_text": "A short gait check saves most beginners from buying the wrong shoe in the first place.",
    "quote_1_name": "Petra Svobodova", "quote_1_credential": "physiotherapist, Sports Clinic Prague",
    "faq_a1": "Choose a stable shoe with firm arch support and check the fit in the afternoon when feet are largest.",
    "faq_a2": "Start with a short gait check and two easy runs per week while you learn how the shoe feels.",
    "faq_a3": "Avoid buying by colour, skipping the fit check and keeping worn out shoes for too long.",
    "faq_a4": "Beginner runners with flat feet benefit most, while runners with high arches may prefer neutral shoes.",
}
OPTIONS = {"updated": "2026-09-30", "author": {"name": "Jana Novakova", "role": "running coach"}}


def strong_draft(brief=EN, **fills):
    sk = geo.build_geo_answer_page(brief, options=OPTIONS)
    values = OfflineWriter().fill(sk, brief)
    values.update(STRONG_FILLS)
    values.update(fills)
    return sk.render(values)


PAGE = {
    "h1": "# Running shoes for flat feet: definition, key facts and answers",
    "date": "*Last updated: September 30, 2026*",
    "def_h": "## What do we mean by running shoes for flat feet?",
    "definition": STRONG_FILLS["definition"],
    "facts": "## What are the key facts?\n\n| Fact | Value |\n|---|---|\n| Weight | 240 g |\n| Drop | 8 mm |",
    "steps": "## How does it work, step by step?\n\n1. Take a gait check.\n2. Pick a stable shoe.\n3. Test it in the afternoon.",
    "stats": ("## What do the numbers say?\n\n- About 38% of beginners pick the wrong shoe type [[cite:s1]].\n"
              "- A typical pair lasts 600 km before the midsole flattens [[cite:s2]].\n- Around 25% of runners report heel slip in new shoes [[cite:s3]]."),
    "quote": ('## What do experts say?\n\n> "A short gait check saves most beginners from buying the wrong shoe in the first place."\n'
              "> - Petra Svobodova, physiotherapist, Sports Clinic Prague"),
    "faq": ("## Frequently asked questions\n\n### How do I choose?\n\nChoose a stable shoe with firm arch support today.\n\n"
            "### Where do I start?\n\nStart with a short gait check at a store near you.\n\n### What should I avoid?\n\nAvoid buying by colour alone."),
    "byline": "---\n\n**Author and organisation:** Jana Novakova, running coach, Zorvia",
    "schema": '<script type="application/ld+json">{"@context": "https://schema.org"}</script>',
}


def page(**over):
    """The strong page as Markdown text; ``key=None`` removes a block, ``key="text"`` replaces it."""
    merged = {**PAGE, **over}
    return "\n\n".join(v for v in merged.values() if v)


def check(report, cid):
    return next(c for c in report.checks if c.id == cid)


class BuilderTests(unittest.TestCase):
    def test_slots_follow_the_integrity_rule(self):
        sk = geo.build_geo_answer_page(EN)
        for sid in ("definition", "steps", "comparison_table", "stat_1", "stat_2", "stat_3", "quote_1_text", "quote_1_name",
                    "quote_1_credential", "faq_a1", "faq_a4"):
            self.assertIsNone(sk.slot(sid).default, sid)
        self.assertEqual(sk.format, "geo_answer_page")
        self.assertEqual(sk.fixed["cite_required_slots"], ["stat_1", "stat_2", "stat_3"])
        for key in ("goal", "cta", "sponsored", "keyword", "lang"):
            self.assertIn(key, sk.meta)
        ids = [s.id for s in sk.slots]
        self.assertEqual(len(ids), len(set(ids)))
        for sid in re.findall(r"\{\{([a-z0-9_]+)\}\}", sk.template):
            self.assertIn(sid, ids)

    def test_key_facts_rows_come_only_from_brief_facts(self):
        sk = geo.build_geo_answer_page(EN)
        self.assertEqual((sk.slot("fact_label_1").default, sk.slot("fact_value_1").default), ("Weight", "240 g"))
        self.assertEqual(sk.slot("fact_label_2").default, "Fact 2")
        self.assertEqual(sk.slot("fact_value_2").default, FACTS[1])
        self.assertIsNone(sk.slot("fact_label_3").default)           # a third row exists, but stays open
        self.assertIsNone(sk.slot("fact_value_3").default)
        bare = geo.build_geo_answer_page(BARE)
        self.assertEqual([s.default for s in bare.slots if s.id.startswith("fact_")], [None] * 6)
        many = Brief(brand="B", topic="t", audience="a", facts=[f"Fact number {i}" for i in range(12)])
        self.assertEqual(len([s for s in geo.build_geo_answer_page(many).slots if s.id.startswith("fact_label_")]), 8)

    def test_offline_render_lists_exactly_the_prose_that_needs_a_writer(self):
        sk = geo.build_geo_answer_page(EN, options=OPTIONS)
        d = sk.render(OfflineWriter().fill(sk, EN))
        self.assertEqual(d.slots_open, ["definition", "fact_label_3", "fact_value_3", "steps", "comparison_table", "stat_1", "stat_2", "stat_3",
                                        "quote_1_text", "quote_1_name", "quote_1_credential", "faq_a1", "faq_a2", "faq_a3", "faq_a4"])
        self.assertIn("| Weight | 240 g |", d.body)
        self.assertIn("*Last updated: September 30, 2026*", d.body)
        self.assertIn("Jana Novakova, running coach, Zorvia", d.body)
        self.assertEqual(d.parts["key_facts"][0], {"label": "Weight", "value": "240 g"})
        self.assertEqual(d.parts["quotes"], [])
        self.assertEqual(d.parts["stats"], [])

    def test_updated_is_open_without_an_option_and_never_invented(self):
        sk = geo.build_geo_answer_page(EN)
        self.assertIsNone(sk.slot("updated").default)
        self.assertIsNone(sk.slot("author_box").default)
        self.assertIn("updated", sk.render().slots_open)
        self.assertEqual(geo.build_geo_answer_page(CS, options={"updated": "2026-10-01"}).slot("updated").default, "1. října 2026")

    def test_json_ld_parts_follow_the_filled_values(self):
        d = strong_draft()
        types = [n["@type"] for n in d.parts["json_ld"]]
        self.assertEqual(types, ["Article", "FAQPage", "Organization"])
        article = d.parts["json_ld"][0]
        self.assertEqual(article["dateModified"], "2026-09-30")
        self.assertEqual(article["publisher"]["name"], "Zorvia")
        self.assertTrue(article["description"].startswith("Running shoes for flat feet are shoes"))
        self.assertEqual(len(d.parts["json_ld"][1]["mainEntity"]), 4)
        self.assertEqual(d.parts["json_ld"][2]["name"], "Zorvia")
        sk = geo.build_geo_answer_page(EN)
        empty = sk.render()
        self.assertEqual([n["@type"] for n in empty.parts["json_ld"]], ["Article", "Organization"])
        self.assertNotIn("[[ADD", json.dumps(empty.parts["json_ld"]))
        self.assertEqual(len(d.parts["stats"]), 3)
        self.assertEqual(d.parts["quotes"][0]["name"], "Petra Svobodova")

    def test_options_for_quotes_faq_and_rows(self):
        sk = geo.build_geo_answer_page(EN, options={"quotes": 2, "faq": 6, "fact_rows": 5})
        ids = [s.id for s in sk.slots]
        self.assertIn("quote_2_credential", ids)
        self.assertIn("faq_a6", ids)
        self.assertIn("fact_value_5", ids)
        clamped = geo.build_geo_answer_page(EN, options={"quotes": 9, "faq": 1})
        self.assertIn("quote_3_name", [s.id for s in clamped.slots])
        self.assertNotIn("quote_4_name", [s.id for s in clamped.slots])
        self.assertIn("faq_q3", [s.id for s in clamped.slots])
        self.assertNotIn("faq_q4", [s.id for s in clamped.slots])

    def test_headings_are_mostly_questions(self):
        for brief in (EN, CS, BARE):
            d = geo.build_geo_answer_page(brief).render()
            h2 = [t for lv, t in geo.parse_headings(d.body) if lv == 2]
            self.assertGreaterEqual(sum(t.endswith("?") for t in h2) / len(h2), 0.7, h2)

    def test_czech_page_uses_czech_labels_and_diacritics(self):
        d = geo.build_geo_answer_page(CS, options={"updated": "2026-10-01", "author": {"name": "Jana", "role": "trenérka"}}).render()
        for text in ("Naposledy aktualizováno", "| Údaj | Hodnota |", "## Časté dotazy", "## Zdroje", "Autor a organizace:", "Jana, trenérka, Zorvia"):
            self.assertIn(text, d.body)
        self.assertNotRegex(d.body.replace("{{", ""), r"\{[a-zA-Z]+\}")
        self.assertNotIn(chr(0x2014), d.body)

    def test_hook_becomes_the_h1(self):
        sk = geo.build_geo_answer_page(EN, hook="Which running shoes suit flat feet?")
        self.assertEqual(sk.slot("h1").default, "Which running shoes suit flat feet?")
        self.assertEqual(sk.hook_slot, "h1")

    def test_question_keyword_uses_the_topic_in_headings(self):
        b = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="how to choose running shoes")
        d = geo.build_geo_answer_page(b).render()
        self.assertIn("## What do we mean by running shoes?", d.body)
        self.assertTrue(d.parts["slots"]["h1"].startswith("How to choose running shoes?"))


class GeoScoreTests(unittest.TestCase):
    def test_strong_rendered_page_passes_every_check(self):
        r = geo.geo_score(strong_draft(), EN)
        self.assertEqual([c.id for c in r.checks if not c.passed], [])
        self.assertEqual(r.score, 100.0)
        self.assertEqual(r.tips, [])
        self.assertEqual(r.penalty, 0.0)
        self.assertEqual(r.lang, "en")

    def test_strong_crafted_text_page_passes_too(self):
        r = geo.geo_score(page(), EN)
        self.assertEqual([c.id for c in r.checks if not c.passed], [])
        self.assertEqual(r.score, 100.0)

    def test_thin_page_scores_low_and_has_a_tip_for_every_failed_check(self):
        thin = "# Running shoes\n\nRunning shoes are great. Buy them now."
        r = geo.geo_score(thin, EN)
        failed = [c for c in r.checks if not c.passed]
        self.assertLess(r.score, 15)
        self.assertEqual(len(r.tips), len(failed))
        self.assertGreaterEqual(len(failed), 9)
        self.assertGreater(geo.geo_score(page(), EN).score, r.score + 80)

    def test_weights_sum_to_one_and_match_the_research_ranking(self):
        r = geo.geo_score(page(), EN)
        self.assertAlmostEqual(sum(c.weight for c in r.checks), 1.0)
        w = {c.id: c.weight for c in r.checks}
        self.assertEqual(w, {"cite_sources": 0.15, "statistics": 0.15, "quotations": 0.12, "answer_first": 0.12, "structure": 0.10,
                             "faq": 0.08, "entity_clarity": 0.08, "freshness": 0.06, "author_eeat": 0.06, "schema": 0.04, "readability": 0.04})
        self.assertEqual(max(w.values()), w["cite_sources"])

    def test_cite_sources(self):
        two = page(stats="## What do the numbers say?\n\n- About 38% of beginners pick the wrong type [[cite:s1]].\n- A pair lasts 600 km [[cite:s2]].")
        self.assertFalse(check(geo.geo_score(two, EN), "cite_sources").passed)
        links = page(stats="## What do the numbers say?\n\n- See https://a.org/x and https://b.org/y and https://c.org/z for details.")
        self.assertTrue(check(geo.geo_score(links), "cite_sources").passed)
        same = page(stats="## What do the numbers say?\n\n- 38% [[cite:s1]]. 20% [[cite:s1]]. 30% [[cite:s1]].")
        self.assertFalse(check(geo.geo_score(same), "cite_sources").passed)
        self.assertEqual(check(geo.geo_score(page()), "cite_sources").message_en, "Distinct sources cited: 3 (at least 3 expected).")

    def test_statistics_need_numbers_near_a_citation(self):
        none = page(stats="## What do the numbers say?\n\n- About 38% of beginners pick the wrong shoe type.\n- A pair lasts 600 km.\n- Around 25% report heel slip.")
        self.assertFalse(check(geo.geo_score(none, EN), "statistics").passed)
        next_sentence = page(stats="## What do the numbers say?\n\n- About 38% of beginners pick the wrong shoe type. See [[cite:s1]].\n"
                                   "- A pair lasts 600 km. See [[cite:s2]].\n- Around 25% report heel slip. See [[cite:s3]].")
        self.assertTrue(check(geo.geo_score(next_sentence, EN), "statistics").passed)
        years = page(stats="## What do the numbers say?\n\n- In 2024 [[cite:s1]]. In 2025 [[cite:s2]]. In 2026 [[cite:s3]].")
        self.assertFalse(check(geo.geo_score(years, EN), "statistics").passed)

    def test_quotations_need_a_named_person(self):
        anon = page(quote='## What do experts say?\n\n> "A short gait check saves most beginners from buying the wrong shoe in the first place."')
        self.assertFalse(check(geo.geo_score(anon, EN), "quotations").passed)
        said = page(quote='## What do experts say?\n\n"A short gait check saves most beginners from the wrong shoe," said Petra Svobodova, a physiotherapist.')
        self.assertTrue(check(geo.geo_score(said, EN), "quotations").passed)
        before = page(quote='## What do experts say?\n\nAccording to Petra Svobodova, "a short gait check saves most beginners from the wrong shoe".')
        self.assertTrue(check(geo.geo_score(before, EN), "quotations").passed)
        czech = page(quote='## Co říkají odborníci?\n\n"Krátké vyšetření chůze ušetří většině začátečníků špatnou koupi bot", uvádí Petra Svobodová.')
        self.assertTrue(check(geo.geo_score(czech, EN), "quotations").passed)
        short = page(quote='## What do experts say?\n\n> "Fit matters"\n> - Petra Svobodova, physiotherapist')
        self.assertFalse(check(geo.geo_score(short, EN), "quotations").passed)

    def test_answer_first_window_length_and_keyword(self):
        late = page(def_h=PAGE["def_h"], definition="Filler words. " * 40 + "\n\n" + STRONG_FILLS["definition"])
        self.assertFalse(check(geo.geo_score(late, EN), "answer_first").passed)
        short = page(definition="Running shoes for flat feet need support. Zorvia is a shoe maker.")
        self.assertFalse(check(geo.geo_score(short, EN), "answer_first").passed)
        long = page(definition=" ".join(["Running shoes for flat feet need support and a stable heel."] * 12))
        self.assertFalse(check(geo.geo_score(long, EN), "answer_first").passed)
        no_kw = page(definition=STRONG_FILLS["definition"].replace("Running shoes for flat feet", "These shoes").replace("running shoe", "shoe"))
        self.assertFalse(check(geo.geo_score(no_kw, EN), "answer_first").passed)
        self.assertTrue(check(geo.geo_score(no_kw), "answer_first").passed)        # without a known keyword only the length counts

    def test_structure_needs_lists_or_tables_and_question_headings(self):
        no_lists = page(facts="## What are the key facts?\n\nThe weight is 240 g.", steps="## How does it work, step by step?\n\nTake a gait check first.",
                        stats="## What do the numbers say?\n\nAbout 38% [[cite:s1]].")
        self.assertFalse(check(geo.geo_score(no_lists, EN), "structure").passed)
        flat = (page().replace("What do we mean by running shoes for flat feet?", "Definition").replace("What are the key facts?", "Key facts")
                .replace("How does it work, step by step?", "How it works").replace("What do the numbers say?", "Numbers")
                .replace("What do experts say?", "Experts").replace("How do I choose?", "Choosing").replace("Where do I start?", "Starting")
                .replace("What should I avoid?", "Avoiding"))
        self.assertFalse(check(geo.geo_score(flat, EN), "structure").passed)

    def test_faq_needs_three_answered_questions(self):
        two = page(faq="## Frequently asked questions\n\n### How do I choose?\n\nChoose a stable shoe with firm support.\n\n### Where do I start?\n\nStart with a gait check.")
        self.assertFalse(check(geo.geo_score(two, EN), "faq").passed)
        empty_answers = page(faq="## FAQ\n\n### One?\n\n### Two?\n\n### Three?\n\n")
        self.assertFalse(check(geo.geo_score(empty_answers, EN), "faq").passed)
        qa = page(faq="## FAQ\n\nQ: One?\nA: Because the answer has enough words.\n\nQ: Two?\nA: Because the answer has enough words too.\n\nQ: Three?\nA: Because the answer has enough words again.")
        self.assertTrue(check(geo.geo_score(qa, EN), "faq").passed)

    def test_entity_clarity(self):
        missing = page(definition=STRONG_FILLS["definition"].replace("Zorvia", "The company"))
        self.assertFalse(check(geo.geo_score(missing, EN), "entity_clarity").passed)
        not_defined = page(definition=STRONG_FILLS["definition"].replace("Zorvia is a running shoe maker", "Zorvia was visited by runners"))
        self.assertFalse(check(geo.geo_score(not_defined, EN), "entity_clarity").passed)
        inconsistent = page(byline="---\n\n**Author and organisation:** Jana Novakova, running coach, ZORVIA")
        self.assertFalse(check(geo.geo_score(inconsistent, EN), "entity_clarity").passed)
        late = page(definition="Footwear matters for runners with flat arches and it takes a while to explain why. " * 6 + STRONG_FILLS["definition"])
        self.assertFalse(check(geo.geo_score(late, EN), "entity_clarity").passed)
        self.assertTrue(check(geo.geo_score(page()), "entity_clarity").passed)         # inferred from "Zorvia is a ..."

    def test_freshness_accepts_several_date_styles(self):
        for date_line in ("*Last updated: 2026-09-30*", "Updated: 30 September 2026", "Published on September 30, 2026", "Aktualizováno: 30. 9. 2026",
                          "Naposledy aktualizováno: 30. září 2026", "Publikováno: 2026-09-30"):
            self.assertTrue(check(geo.geo_score(page(date=date_line), EN), "freshness").passed, date_line)
        for bad in ("", "*Written some time ago*", "Updated: recently"):
            self.assertFalse(check(geo.geo_score(page(date=bad), EN), "freshness").passed, bad)

    def test_author_eeat_needs_role_and_organisation(self):
        self.assertFalse(check(geo.geo_score(page(byline=None), EN), "author_eeat").passed)
        self.assertFalse(check(geo.geo_score(page(byline="By Jana Novakova"), EN), "author_eeat").passed)
        self.assertTrue(check(geo.geo_score(page(byline="Written by Jana Novakova, running coach at Zorvia"), EN), "author_eeat").passed)
        no_org = page(byline="Written by Jana Novakova, running coach")
        self.assertFalse(check(geo.geo_score(no_org, EN), "author_eeat").passed)
        self.assertTrue(check(geo.geo_score(no_org), "author_eeat").passed)
        self.assertTrue(check(geo.geo_score(page(byline="Autor: Jana Nováková, trenérka, Zorvia"), EN), "author_eeat").passed)

    def test_schema_check_uses_parts_or_markup(self):
        self.assertFalse(check(geo.geo_score(page(schema=None), EN), "schema").passed)
        d = Draft(format="x", lang="en", hook="", body=page(schema=None), parts={"json_ld": [{"@type": "Article"}]}, meta={})
        self.assertTrue(check(geo.geo_score(d, EN), "schema").passed)

    def test_readability(self):
        long = " ".join(["word"] * 60) + "."
        self.assertFalse(check(geo.geo_score(page(definition=" ".join([long] * 15)), EN), "readability").passed)
        self.assertTrue(check(geo.geo_score(page(), EN), "readability").passed)

    def test_keyword_stuffing_is_penalised(self):
        stuffed = page(definition="Running shoes for flat feet are running shoes for flat feet. " * 8 + STRONG_FILLS["definition"])
        r = geo.geo_score(stuffed, EN)
        self.assertGreater(r.density, 2.5)
        self.assertGreater(r.penalty, 0)
        self.assertLess(r.score, geo.geo_score(page(), EN).score)
        self.assertTrue(any("stuffing" in t for t in r.tips))
        self.assertLessEqual(r.penalty, 25.0)
        cs = geo.geo_score(stuffed, EN, lang="cs")
        self.assertTrue(any("přeplňování" in t for t in cs.tips))

    def test_tips_and_messages_exist_in_both_languages(self):
        r = geo.geo_score("# Title\n\nShort.", EN)
        for c in r.checks:
            self.assertTrue(c.message_en and c.message_cs, c.id)
        self.assertTrue(all(not re.search(r"[ěščřžýáíé]", t) for t in r.tips))
        cs = geo.geo_score("# Title\n\nShort.", EN, lang="cs")
        self.assertEqual(len(cs.tips), len(r.tips))
        self.assertTrue(all(re.search(r"[ěščřžýáíéůú]", t) for t in cs.tips))
        self.assertEqual(cs.lang, "cs")

    def test_language_resolution(self):
        czech_text = "Běžecké boty jsou dobré pro začátečníky. Zkuste je."
        self.assertEqual(geo.geo_score(czech_text).lang, "cs")
        self.assertEqual(geo.geo_score("Running shoes are good for beginners.").lang, "en")
        d = strong_draft(CS)
        self.assertEqual(geo.geo_score(d).lang, "cs")
        self.assertEqual(geo.geo_score(d, lang="en").lang, "en")
        self.assertEqual(geo.geo_score("text", EN).lang, "en")

    def test_score_is_always_bounded(self):
        for text in ("", "#", "x" * 5000, page(), "1 2 3 4 5 " * 300):
            r = geo.geo_score(text, EN)
            self.assertTrue(0.0 <= r.score <= 100.0)
            self.assertIsInstance(r.score, float)


class LlmsTxtTests(unittest.TestCase):
    def test_format_follows_the_proposal(self):
        text = geo.llms_txt("Zorvia", "Running shoes for\nbeginners.", [
            {"title": "Fit guide", "url": "https://zorvia.com/fit", "note": "How to size a shoe"},
            {"title": "Returns", "url": "https://zorvia.com/returns"},
        ], optional=[{"title": "Blog [archive]", "url": "https://zorvia.com/blog", "note": "Older posts"}])
        self.assertEqual(text, "# Zorvia\n\n> Running shoes for beginners.\n\n## Key pages\n\n- [Fit guide](https://zorvia.com/fit): How to size a shoe\n"
                               "- [Returns](https://zorvia.com/returns)\n\n## Optional\n\n- [Blog (archive)](https://zorvia.com/blog): Older posts\n")
        self.assertNotIn(chr(0x2014), text)

    def test_sections_and_skipped_entries(self):
        text = geo.llms_txt("Z", "Summary.", [{"title": "A", "url": "https://z.com/a", "section": "Docs"},
                                               {"title": "B", "url": "https://z.com/b", "section": "Docs"},
                                               {"title": "No url"}, {"url": "https://z.com/c", "section": "Policies"}])
        self.assertEqual(text.count("## Docs"), 1)
        self.assertIn("- [https://z.com/c](https://z.com/c)", text)
        self.assertNotIn("No url", text)
        self.assertNotIn("## Optional", text)
        self.assertTrue(text.index("## Docs") < text.index("## Policies"))

    def test_minimal_file(self):
        self.assertEqual(geo.llms_txt("Z", "", []), "# Z\n")
        self.assertTrue(geo.llms_txt("Z", "S", []).endswith("> S\n"))


class RobotsSnippetTests(unittest.TestCase):
    def groups(self, text):
        out, agents = {}, []
        for line in text.splitlines():
            if line.startswith("User-agent:"):
                agents.append(line.split(": ", 1)[1])
            elif line.startswith(("Allow:", "Disallow:")):
                out[line] = out.get(line, []) + agents
                agents = []
        return out

    def test_allow_search_block_training_is_the_default(self):
        text = geo.robots_ai_snippet()
        g = self.groups(text)
        self.assertEqual(set(g["Disallow: /"]), {"GPTBot", "ClaudeBot", "Google-Extended", "Applebot-Extended", "CCBot", "Bytespider", "Amazonbot",
                                                 "meta-externalagent"})
        self.assertEqual(set(g["Allow: /"]), {"OAI-SearchBot", "ChatGPT-User", "Claude-SearchBot", "Claude-User", "PerplexityBot", "Perplexity-User"})
        self.assertIn("allow_search_block_training", text)
        self.assertIn("Verify every user agent", text)
        self.assertIn("advisory", text)

    def test_all_known_agents_appear_in_every_policy(self):
        names = [a for a, _, _ in geo.AI_AGENTS]
        self.assertEqual(len(names), 14)
        for policy in geo.ROBOTS_POLICIES:
            text = geo.robots_ai_snippet(policy)
            for name in names:
                self.assertEqual(text.count(f"User-agent: {name}\n"), 1, (policy, name))

    def test_allow_all_and_block_all(self):
        allow = geo.robots_ai_snippet("allow_all")
        self.assertNotIn("Disallow", allow.replace("# ", ""))
        self.assertIn("Allow: /", allow)
        block = geo.robots_ai_snippet("block_all")
        self.assertNotIn("Allow: /", block)
        self.assertIn("Disallow: /", block)

    def test_extra_agents_are_treated_like_training_crawlers(self):
        g = self.groups(geo.robots_ai_snippet("allow_search_block_training", ["MyBot", "Other-Bot_2"]))
        self.assertIn("MyBot", g["Disallow: /"])
        g = self.groups(geo.robots_ai_snippet("allow_all", ["MyBot"]))
        self.assertIn("MyBot", g["Allow: /"])

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValueError):
            geo.robots_ai_snippet("allow_everything")
        with self.assertRaises(ValueError):
            geo.robots_ai_snippet("allow_all", ["Bad Bot\nDisallow: /"])


class ValidatorTests(unittest.TestCase):
    def codes(self, issues, severity=None):
        return [i.code for i in issues if severity is None or i.severity == severity]

    def test_filled_page_has_no_errors(self):
        self.assertEqual(self.codes(geo.validate_geo_page(strong_draft()), "error"), [])

    def test_statistic_without_cite_marker_is_an_error(self):
        d = strong_draft(stat_2="A typical pair lasts 600 km before the midsole flattens.")
        issues = geo.validate_geo_page(d)
        bad = [i for i in issues if i.code == "STAT_NEEDS_CITATION"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0].severity, "error")
        self.assertIn("stat_2", bad[0].message)

    def test_unknown_citation_id_is_an_error(self):
        d = strong_draft(stat_3="Around 25% of runners report heel slip [[cite:nope]].")
        self.assertIn("CITATION_UNKNOWN", self.codes(geo.validate_geo_page(d), "error"))

    def test_quote_needs_name_and_credential(self):
        d = strong_draft(quote_1_name="Petra Svobodova", quote_1_credential="")
        # an empty fill falls back to the open placeholder, so the quote counts as unattributed
        self.assertIn("QUOTE_NOT_ATTRIBUTED", self.codes(geo.validate_geo_page(d), "error"))

    def test_offline_page_reports_failed_checks_as_warnings(self):
        sk = geo.build_geo_answer_page(BARE)
        issues = geo.validate_geo_page(sk.render(OfflineWriter().fill(sk, BARE)))
        self.assertEqual(self.codes(issues, "error"), [])
        self.assertIn("GEO_CITE_SOURCES", self.codes(issues, "warn"))
        cs_issues = geo.validate_geo_page(geo.build_geo_answer_page(CS).render())
        self.assertTrue(any("Počet" in i.message or "Citace" in i.message for i in cs_issues))

    def test_registry(self):
        self.assertEqual([f.id for f in geo.FORMAT_SPECS], ["geo_answer_page"])
        spec = geo.FORMAT_SPECS[0]
        self.assertEqual((spec.family, spec.platform), ("article", "blog"))
        self.assertIs(spec.build, geo.build_geo_answer_page)
        self.assertIs(spec.validate, geo.validate_geo_page)
        self.assertNotIn(chr(0x2014), json.dumps([spec.name_en, spec.name_cs, spec.description_en, spec.description_cs]))


if __name__ == "__main__":
    unittest.main()
