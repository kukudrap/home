import json
import unittest

from dopamine_king.generate.types import Brief
from dopamine_king.generate.visibility import AnswerRecord, VisibilityReport, analyze_answers, suggest_queries


def rec(query, engine, text, *urls):
    return AnswerRecord(query, engine, text, list(urls))


EN = Brief(brand="Zorvia", topic="running shoes", audience="beginner runners", keyword="running shoes for flat feet")
CS = Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs")
CS_FORMS = Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs",
                 topic_forms={"acc": "běžecké boty", "gen": "běžeckých bot"})


class MentionTests(unittest.TestCase):
    def mention_rate(self, text, brand="Zorvia", **kw):
        return analyze_answers([rec("q", "e", text)], brand, **kw).mention_rate

    def test_case_and_diacritics_insensitive(self):
        self.assertEqual(self.mention_rate("I like zorvia and ZORVIA."), 1.0)
        self.assertEqual(self.mention_rate("Nejlepší je škoda octavia", brand="Škoda"), 1.0)
        self.assertEqual(self.mention_rate("Nejlepsi je SKODA octavia", brand="Škoda"), 1.0)
        self.assertEqual(self.mention_rate("Kupte si Škodu", brand="Skoda"), 0.0)           # inflection is not guessed

    def test_word_boundaries(self):
        for text in ("Zorvian shoes are fine.", "The Zorviano brand", "azorvia", "zorvia2", "Zorvias are shoes"):
            self.assertEqual(self.mention_rate(text), 0.0, text)
        for text in ("Zorvia.", "(Zorvia)", "Zorvia's shoes", "Zorvia-branded shoes", "I wear Zorvia, and you?"):
            self.assertEqual(self.mention_rate(text), 1.0, text)

    def test_multi_word_brands_and_punctuation(self):
        self.assertEqual(self.mention_rate("Try red bull today", brand="Red Bull"), 1.0)
        self.assertEqual(self.mention_rate("Try red-bull today", brand="Red Bull"), 1.0)
        self.assertEqual(self.mention_rate("Try red\n  bull today", brand="Red Bull"), 1.0)
        self.assertEqual(self.mention_rate("Try redbull today", brand="Red Bull"), 0.0)
        self.assertEqual(self.mention_rate("Ben & Jerry's is good", brand="Ben & Jerry's"), 1.0)

    def test_aliases_cover_inflected_czech_forms(self):
        text = "Doporučuji boty od Zorvie."
        self.assertEqual(self.mention_rate(text), 0.0)
        self.assertEqual(self.mention_rate(text, aliases={"Zorvia": ["Zorvie", "Zorvii"]}), 1.0)

    def test_empty_input(self):
        r = analyze_answers([], "Zorvia", ["Nike"], brand_domains=["zorvia.com"])
        self.assertEqual((r.n_answers, r.mention_rate, r.citation_rate, r.avg_first_mention_position, r.sentiment), (0, 0.0, 0.0, None, 0.0))
        self.assertEqual(r.share_of_voice, {"Zorvia": 0.0, "Nike": 0.0})
        self.assertEqual((r.per_engine, r.per_query, r.gaps), ({}, [], []))


class CitationTests(unittest.TestCase):
    def citation_rate(self, urls, domains=("zorvia.com",)):
        return analyze_answers([rec("q", "e", "Zorvia is mentioned.", *urls)], "Zorvia", brand_domains=list(domains)).citation_rate

    def test_hosts_match_exactly_or_by_subdomain(self):
        for url in ("https://zorvia.com/guide", "https://www.zorvia.com", "http://blog.zorvia.com/post?x=1", "zorvia.com/page", "HTTPS://WWW.ZORVIA.COM/A"):
            self.assertEqual(self.citation_rate([url]), 1.0, url)

    def test_lookalike_hosts_and_other_domains_do_not_match(self):
        for url in ("https://notzorvia.com/x", "https://zorvia.com.evil.org/x", "https://example.org/zorvia.com", "https://zorvia.co/x", ""):
            self.assertEqual(self.citation_rate([url]), 0.0, url)

    def test_domain_input_forms_and_no_domains(self):
        self.assertEqual(self.citation_rate(["https://zorvia.com/a"], domains=["https://www.Zorvia.com/"]), 1.0)
        self.assertEqual(self.citation_rate(["https://zorvia.com/a"], domains=[]), 0.0)
        self.assertEqual(self.citation_rate(["https://other.org", "https://blog.zorvia.com"], domains=["other.net", "zorvia.com"]), 1.0)

    def test_rate_is_per_answer(self):
        records = [rec("a", "e", "Zorvia.", "https://zorvia.com/1"), rec("b", "e", "Zorvia.", "https://x.org"), rec("c", "e", "Zorvia."), rec("d", "e", "Zorvia.", "https://zorvia.com/2", "https://zorvia.com/3")]
        self.assertEqual(analyze_answers(records, "Zorvia", brand_domains=["zorvia.com"]).citation_rate, 0.5)

    def test_citation_without_a_mention_still_counts_as_a_citation(self):
        r = analyze_answers([rec("q", "e", "Great shoes exist.", "https://zorvia.com/x")], "Zorvia", brand_domains=["zorvia.com"])
        self.assertEqual((r.mention_rate, r.citation_rate), (0.0, 1.0))


class PositionAndShareTests(unittest.TestCase):
    def test_first_mention_position_is_relative(self):
        text = "Zorvia leads." + " filler" * 20
        r = analyze_answers([rec("q", "e", text)], "Zorvia")
        self.assertEqual(r.avg_first_mention_position, 0.0)
        late = "x" * 50 + " Zorvia"
        r = analyze_answers([rec("q", "e", late)], "Zorvia")
        self.assertAlmostEqual(r.avg_first_mention_position, 51 / len(late), places=3)
        self.assertTrue(0 < r.avg_first_mention_position < 1)

    def test_position_averages_only_answers_that_mention_the_brand(self):
        records = [rec("a", "e", "Zorvia first."), rec("b", "e", "Nothing here at all."), rec("c", "e", "x" * 90 + " Zorvia")]
        r = analyze_answers(records, "Zorvia")
        self.assertGreater(r.avg_first_mention_position, 0.4)
        self.assertLess(r.avg_first_mention_position, 0.6)
        self.assertAlmostEqual(r.mention_rate, 2 / 3, places=3)
        self.assertIsNone(analyze_answers([rec("a", "e", "Nope.")], "Zorvia").avg_first_mention_position)

    def test_share_of_voice_math(self):
        records = [rec("a", "e", "Zorvia, Zorvia and Zorvia beat Nike."), rec("b", "e", "Asics is fine. Zorvia too.")]
        r = analyze_answers(records, "Zorvia", ["Nike", "Asics"])
        self.assertAlmostEqual(r.share_of_voice["Zorvia"], 4 / 6, places=3)
        self.assertAlmostEqual(r.share_of_voice["Nike"], 1 / 6, places=3)
        self.assertAlmostEqual(r.share_of_voice["Asics"], 1 / 6, places=3)
        self.assertAlmostEqual(sum(r.share_of_voice.values()), 1.0, places=2)
        self.assertEqual(list(r.share_of_voice), ["Zorvia", "Nike", "Asics"])

    def test_share_of_voice_without_any_mention_and_duplicate_competitors(self):
        r = analyze_answers([rec("a", "e", "Nothing relevant.")], "Zorvia", ["Nike"])
        self.assertEqual(r.share_of_voice, {"Zorvia": 0.0, "Nike": 0.0})
        r = analyze_answers([rec("a", "e", "Zorvia and Nike.")], "Zorvia", ["zorvia", "Nike"])
        self.assertEqual(list(r.share_of_voice), ["Zorvia", "Nike"])
        self.assertEqual(r.share_of_voice["Zorvia"], 0.5)

    def test_competitors_match_without_diacritics(self):
        r = analyze_answers([rec("a", "e", "Zorvia nebo ŠKODA?")], "Zorvia", ["Škoda"])
        self.assertEqual(r.share_of_voice["Škoda"], 0.5)


class SentimentTests(unittest.TestCase):
    def sentiment(self, text, lang="en", brand="Zorvia"):
        return analyze_answers([rec("q", "e", text)], brand, lang=lang).sentiment

    def test_polarity_and_bounds(self):
        self.assertEqual(self.sentiment("Zorvia is great and reliable."), 1.0)
        self.assertEqual(self.sentiment("Zorvia is poor and overpriced."), -1.0)
        self.assertEqual(self.sentiment("Zorvia is great but expensive."), 0.0)
        self.assertEqual(self.sentiment("Zorvia makes shoes."), 0.0)
        self.assertEqual(self.sentiment("Nothing about the brand here."), 0.0)

    def test_negation_flips_polarity(self):
        self.assertLess(self.sentiment("Zorvia is not good."), 0)
        self.assertLess(self.sentiment("Zorvia isn't reliable."), 0)
        self.assertGreater(self.sentiment("Zorvia is not bad at all."), 0)
        self.assertGreater(self.sentiment("Zorvia never fails."), 0)

    def test_only_sentences_that_mention_the_brand_count(self):
        text = "Nike is terrible and slow. Zorvia is excellent. The weather is bad."
        self.assertEqual(self.sentiment(text), 1.0)
        mixed = "Zorvia is excellent. Zorvia is overpriced."
        self.assertEqual(self.sentiment(mixed), 0.0)

    def test_czech_lexicon_with_and_without_diacritics(self):
        self.assertEqual(self.sentiment("Zorvia je skvělá a spolehlivá.", "cs"), 1.0)
        self.assertEqual(self.sentiment("zorvia je skvela a spolehliva", "cs"), 1.0)
        self.assertEqual(self.sentiment("Zorvia je špatná a drahá.", "cs"), -1.0)
        self.assertLess(self.sentiment("Zorvia není dobrá.", "cs"), 0)
        self.assertEqual(self.sentiment("Zorvia je skvělá a spolehlivá.", "en"), 0.0)

    def test_language_can_be_detected_per_answer(self):
        records = [rec("a", "e", "Zorvia is excellent."), rec("b", "e", "Zorvia je skvělá.")]
        self.assertEqual(analyze_answers(records, "Zorvia", lang="auto").sentiment, 1.0)
        self.assertEqual(analyze_answers(records, "Zorvia", lang="en").sentiment, 1.0)
        self.assertEqual(analyze_answers([records[1]], "Zorvia", lang="en").sentiment, 0.0)


class GapAndBreakdownTests(unittest.TestCase):
    RECORDS = [
        rec("best running shoes", "chatgpt", "Nike and Asics lead the field."),
        rec("Best  Running shoes", "perplexity", "Asics is a safe pick."),
        rec("running shoes for flat feet", "chatgpt", "Zorvia and Nike both make stability shoes.", "https://zorvia.com/a"),
        rec("running shoes for flat feet", "gemini", "Pick a stable shoe."),
        rec("how to size a shoe", "chatgpt", "Measure your foot in the afternoon."),
    ]

    def report(self, competitors=("Nike", "Asics")):
        return analyze_answers(self.RECORDS, "Zorvia", list(competitors), brand_domains=["zorvia.com"])

    def test_gaps_are_queries_where_rivals_appear_and_the_brand_does_not(self):
        r = self.report()
        self.assertEqual(r.gaps, ["best running shoes"])

    def test_no_competitors_means_no_gaps(self):
        self.assertEqual(self.report(()).gaps, [])

    def test_a_single_mention_closes_the_gap(self):
        records = self.RECORDS + [rec("best running shoes", "claude", "Zorvia is a solid option too.")]
        r = analyze_answers(records, "Zorvia", ["Nike", "Asics"])
        self.assertEqual(r.gaps, [])

    def test_per_query_groups_case_and_whitespace_insensitively(self):
        r = self.report()
        self.assertEqual([q["query"] for q in r.per_query], ["best running shoes", "running shoes for flat feet", "how to size a shoe"])
        best = r.per_query[0]
        self.assertEqual((best["n_answers"], best["mentioned"], best["engines"]), (2, 0, ["chatgpt", "perplexity"]))
        self.assertEqual(best["competitors_named"], {"Nike": 1, "Asics": 2})
        flat = r.per_query[1]
        self.assertEqual((flat["mention_rate"], flat["cited"], flat["citation_rate"]), (0.5, 1, 0.5))
        self.assertEqual(r.per_query[2]["competitors_named"], {})

    def test_per_engine_breakdown(self):
        r = self.report()
        self.assertEqual(set(r.per_engine), {"chatgpt", "perplexity", "gemini"})
        chat = r.per_engine["chatgpt"]
        self.assertEqual(chat["n_answers"], 3)
        self.assertAlmostEqual(chat["mention_rate"], 1 / 3, places=3)
        self.assertAlmostEqual(chat["citation_rate"], 1 / 3, places=3)
        self.assertEqual(r.per_engine["gemini"]["mention_rate"], 0.0)
        self.assertIsNone(r.per_engine["gemini"]["avg_first_mention_position"])

    def test_overall_numbers_and_serialisation(self):
        r = self.report()
        self.assertEqual((r.brand, r.n_answers), ("Zorvia", 5))
        self.assertEqual(r.mention_rate, 0.2)
        self.assertEqual(r.citation_rate, 0.2)
        self.assertIsInstance(r, VisibilityReport)
        data = json.loads(json.dumps(r.to_dict()))
        self.assertEqual(data["gaps"], ["best running shoes"])
        self.assertEqual(AnswerRecord.from_dict({"query": "q", "engine": "e", "text": "t"}).cited_urls, [])


class SuggestQueriesTests(unittest.TestCase):
    def test_english_questions_buyers_ask(self):
        qs = suggest_queries(EN)
        self.assertEqual(len(qs), 15)
        self.assertEqual(len({q.lower() for q in qs}), 15)
        for expected in ("What should I know about running shoes?", "Best running shoes for beginner runners", "How do I choose running shoes?",
                         "Zorvia vs alternatives", "Zorvia reviews", "Is Zorvia worth it?", "What are the alternatives to Zorvia?",
                         "What are the pros and cons of running shoes?"):
            self.assertIn(expected, qs)
        self.assertTrue(any("price" in q.lower() or "pay" in q.lower() for q in qs))
        for q in qs:
            self.assertNotIn("{", q)
            self.assertNotIn(chr(0x2014), q)

    def test_keyword_variants_when_the_keyword_differs_from_the_topic(self):
        qs = suggest_queries(EN, 20)
        self.assertIn("Best running shoes for flat feet", qs)
        self.assertIn("running shoes for flat feet price", qs)
        plain = suggest_queries(Brief(brand="Zorvia", topic="running shoes", audience="beginner runners"), 20)
        self.assertNotIn("Best running shoes for flat feet", plain)

    def test_n_controls_the_count(self):
        self.assertEqual(len(suggest_queries(EN, 3)), 3)
        self.assertEqual(suggest_queries(EN, 0), [])
        self.assertEqual(suggest_queries(EN, -4), [])
        self.assertGreaterEqual(len(suggest_queries(EN, 100)), 20)
        self.assertEqual(suggest_queries(EN, 5), suggest_queries(EN, 15)[:5])

    def test_czech_queries_are_keyword_style_and_number_agnostic(self):
        qs = suggest_queries(CS)
        self.assertEqual(len(qs), 15)
        for expected in ("běžecké boty co to je", "nejlepší běžecké boty", "běžecké boty jak vybrat", "Zorvia vs alternativy", "běžecké boty cena",
                         "Zorvia recenze", "Zorvia zkušenosti", "alternativy k Zorvia", "vyplatí se běžecké boty"):
            self.assertIn(expected, qs)
        for q in qs:
            self.assertNotIn("{", q)
        self.assertFalse(any(q.startswith("Co je ") for q in qs))

    def test_czech_case_forms_are_used_when_known(self):
        qs = suggest_queries(CS_FORMS, 20)
        self.assertIn("jak vybrat běžecké boty", qs)
        self.assertIn("výhody a nevýhody běžeckých bot", qs)
        self.assertNotIn("běžecké boty jak vybrat", qs)
        self.assertIn("běžecké boty jak vybrat", suggest_queries(CS, 20))

    def test_czech_keyword_variants(self):
        b = Brief(brand="Zorvia", topic="běžecké boty", audience="začínající běžci", lang="cs", keyword="běžecké boty na ploché nohy")
        qs = suggest_queries(b, 20)
        self.assertIn("nejlepší běžecké boty na ploché nohy", qs)
        self.assertIn("běžecké boty na ploché nohy cena", qs)


if __name__ == "__main__":
    unittest.main()
