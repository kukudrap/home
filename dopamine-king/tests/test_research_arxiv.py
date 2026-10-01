import unittest
from urllib.parse import parse_qs, urlsplit

from dopamine_king.net import FakeFetcher, FetchError
from dopamine_king.research.arxiv import ArxivClient, normalize_arxiv_id, parse_feed
from dopamine_king.research.grading import apply_grade
from dopamine_king.research.models import ResearchApiError
from tests.test_research_common import ARXIV_QUERY, arxiv_entry, arxiv_feed, fixture_bytes, fixture_text


def query_of(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


class ArxivParsingTests(unittest.TestCase):
    def setUp(self):
        self.fetcher = FakeFetcher({ARXIV_QUERY: fixture_text("arxiv_search.xml")})
        self.studies = ArxivClient(self.fetcher).search("headline experiments", max_results=2)

    def test_two_entries_with_versions_stripped_from_the_ids(self):
        self.assertEqual([s.id for s in self.studies], ["arxiv:2999.12345", "arxiv:synth/0000001"])

    def test_first_entry_with_several_authors_and_messy_whitespace(self):
        s = self.studies[0]
        self.assertEqual(s.title, "Headline Experiments at Scale: A Synthetic Example")
        self.assertEqual(s.authors, ["Doe, J. Q.", "Novák, J.", "van der Meer, A."])
        self.assertEqual(
            s.abstract,
            "We describe a synthetic preprint used only in tests. The abstract spans several lines and has irregular spacing.",
        )
        self.assertEqual(s.year, 2029)
        self.assertEqual(s.url, "https://arxiv.org/abs/2999.12345")
        self.assertIsNone(s.doi)
        self.assertIsNone(s.cited_by)

    def test_every_arxiv_study_is_an_unreviewed_preprint(self):
        for s in self.studies:
            self.assertEqual((s.design, s.peer_reviewed, s.source, s.venue), ("preprint", False, "arxiv", "arXiv"))
            self.assertFalse(s.verified)
            self.assertFalse(s.retracted)

    def test_arxiv_doi_is_taken_when_present_but_the_id_stays_arxiv(self):
        s = self.studies[1]
        self.assertEqual(s.doi, "10.5555/preprint.published.2020.5")
        self.assertEqual(s.id, "arxiv:synth/0000001")
        self.assertEqual(s.authors, ["Garcia, M."])
        self.assertEqual(s.url, "https://arxiv.org/abs/synth/0000001")

    def test_graded_preprint_is_never_better_than_c(self):
        apply_grade(self.studies[0], today_year=2030)
        self.assertEqual(self.studies[0].grade, "C")

    def test_error_entry_and_empty_feed_yield_nothing(self):
        self.assertEqual(parse_feed(fixture_bytes("arxiv_error.xml")), [])
        self.assertEqual(parse_feed(fixture_bytes("arxiv_empty.xml")), [])

    def test_parse_feed_accepts_text_and_skips_entries_without_title(self):
        feed = arxiv_feed(arxiv_entry("2999.00001", "Kept"), arxiv_entry("2999.00002", ""))
        self.assertEqual([s.title for s in parse_feed(feed)], ["Kept"])


class ArxivRequestTests(unittest.TestCase):
    def test_search_url(self):
        fetcher = FakeFetcher({ARXIV_QUERY: fixture_text("arxiv_empty.xml")})
        ArxivClient(fetcher).search("generative engine optimization", max_results=7)
        url = fetcher.calls[0]
        self.assertTrue(url.startswith("http://export.arxiv.org/api/query?"))
        q = query_of(url)
        self.assertEqual(q["search_query"], ["all:generative AND all:engine AND all:optimization"])
        self.assertEqual((q["start"], q["max_results"]), (["0"], ["7"]))
        self.assertEqual(q["sortBy"], ["relevance"])

    def test_punctuation_is_reduced_to_word_tokens(self):
        fetcher = FakeFetcher({ARXIV_QUERY: fixture_text("arxiv_empty.xml")})
        ArxivClient(fetcher).search("A/B testing: peeking!")
        self.assertEqual(query_of(fetcher.calls[0])["search_query"], ["all:A AND all:B AND all:testing AND all:peeking"])

    def test_empty_query_makes_no_request(self):
        fetcher = FakeFetcher({ARXIV_QUERY: fixture_text("arxiv_empty.xml")})
        self.assertEqual(ArxivClient(fetcher).search("  ?! "), [])
        self.assertEqual(fetcher.calls, [])

    def test_max_results_is_clamped(self):
        fetcher = FakeFetcher({ARXIV_QUERY: fixture_text("arxiv_empty.xml")})
        client = ArxivClient(fetcher)
        client.search("x", max_results=0)
        client.search("x", max_results=10_000)
        self.assertEqual([query_of(u)["max_results"] for u in fetcher.calls], [["1"], ["100"]])

    def test_custom_base_url(self):
        fetcher = FakeFetcher({"https://mirror.test/api?*": fixture_text("arxiv_empty.xml")})
        ArxivClient(fetcher, base_url="https://mirror.test/api").search("x")
        self.assertTrue(fetcher.calls[0].startswith("https://mirror.test/api?"))

    def test_by_id_accepts_prefixes_urls_and_versions(self):
        fetcher = FakeFetcher({ARXIV_QUERY: fixture_text("arxiv_search.xml")})
        client = ArxivClient(fetcher)
        for raw in ("2999.12345", "arXiv:2999.12345v3", "https://arxiv.org/abs/2999.12345v2",
                    "https://arxiv.org/pdf/2999.12345v2.pdf"):
            study = client.by_id(raw)
            self.assertEqual(study.id, "arxiv:2999.12345", raw)
        self.assertTrue(all(query_of(u)["id_list"] == ["2999.12345"] for u in fetcher.calls))

    def test_by_id_unknown_and_malformed(self):
        fetcher = FakeFetcher({ARXIV_QUERY: fixture_text("arxiv_error.xml")})
        client = ArxivClient(fetcher)
        self.assertIsNone(client.by_id("2999.99999"))          # the API answers with an Error entry
        n = len(fetcher.calls)
        self.assertIsNone(client.by_id("not an id"))
        self.assertEqual(len(fetcher.calls), n)


class ArxivFailureTests(unittest.TestCase):
    def test_http_error_invalid_xml_and_network_error(self):
        with self.assertRaises(ResearchApiError):
            ArxivClient(FakeFetcher({ARXIV_QUERY: (503, "busy")})).search("x")
        with self.assertRaises(ResearchApiError):
            ArxivClient(FakeFetcher({ARXIV_QUERY: "<feed><unclosed></feed>"})).search("x")
        with self.assertRaises(FetchError):
            ArxivClient(FakeFetcher({ARXIV_QUERY: FetchError("no route")})).search("x")

    def test_documents_with_a_dtd_are_refused(self):
        bomb = '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaa">]><feed xmlns="http://www.w3.org/2005/Atom">&a;</feed>'
        with self.assertRaises(ResearchApiError):
            parse_feed(bomb)


class NormalizeIdTests(unittest.TestCase):
    def test_valid_forms(self):
        self.assertEqual(normalize_arxiv_id("2311.09735"), "2311.09735")
        self.assertEqual(normalize_arxiv_id(" arXiv:2311.09735v3 "), "2311.09735")
        self.assertEqual(normalize_arxiv_id("http://arxiv.org/abs/hep-th/9901001v2"), "hep-th/9901001")
        self.assertEqual(normalize_arxiv_id("https://export.arxiv.org/pdf/1706.03762v7.pdf"), "1706.03762")

    def test_invalid_forms(self):
        for raw in (None, "", "12345", "arxiv:", "2311.9735x", "hello world"):
            self.assertIsNone(normalize_arxiv_id(raw), raw)


if __name__ == "__main__":
    unittest.main()
