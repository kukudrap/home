import json
import unittest
from urllib.parse import parse_qs, urlsplit

from dopamine_king.net import FakeFetcher, FetchError
from dopamine_king.research.grading import apply_grade
from dopamine_king.research.models import ResearchApiError
from dopamine_king.research.openalex import OpenAlexClient, abstract_from_inverted_index, parse_work
from tests.test_research_common import OPENALEX_SEARCH, OPENALEX_WORK, fixture_text

ABSTRACT = (
    "We randomly assigned readers to curiosity gap headlines or plain headlines and measured clicks. "
    "Curiosity gap headlines raised clicks, but only when the article answered the question."
)


def query_of(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


class OpenAlexParsingTests(unittest.TestCase):
    def setUp(self):
        self.fetcher = FakeFetcher({OPENALEX_SEARCH: fixture_text("openalex_search.json")})
        self.client = OpenAlexClient(self.fetcher, mailto="dev@example.org")
        self.studies = self.client.search("curiosity gap", per_page=6)
        self.by_id = {s.id: s for s in self.studies}

    def test_untitled_work_is_skipped(self):
        self.assertEqual(len(self.studies), 5)
        self.assertEqual(
            list(self.by_id),
            ["doi:10.5555/curiosity.2021.001", "oa:W4300000002", "doi:10.5555/retracted.2019.003",
             "oa:W4300000004", "doi:10.5555/review.2022.005"],
        )

    def test_complete_article(self):
        s = self.by_id["doi:10.5555/curiosity.2021.001"]
        self.assertEqual(s.title, "Curiosity Gaps in Headline Writing: A Randomized Controlled Trial")
        self.assertEqual(s.authors, ["Doe, J. Q.", "Novák, J."])
        self.assertEqual((s.year, s.cited_by), (2021, 87))
        self.assertEqual(s.venue, "Journal of Synthetic Media Studies")
        self.assertEqual(s.doi, "10.5555/curiosity.2021.001")
        self.assertEqual(s.url, "https://doi.org/10.5555/curiosity.2021.001")
        self.assertEqual(s.abstract, ABSTRACT)
        self.assertEqual((s.design, s.source, s.peer_reviewed), ("rct", "openalex", True))
        self.assertFalse(s.retracted)
        self.assertFalse(s.verified)

    def test_null_fields_stay_null(self):
        s = self.by_id["oa:W4300000002"]
        self.assertIsNone(s.doi)
        self.assertIsNone(s.year)
        self.assertIsNone(s.abstract)
        self.assertIsNone(s.venue)
        self.assertEqual(s.authors, [])
        self.assertEqual(s.url, "https://openalex.org/W4300000002")
        self.assertEqual((s.design, s.peer_reviewed), ("preprint", False))

    def test_retracted_flag_makes_the_study_grade_d(self):
        s = self.by_id["doi:10.5555/retracted.2019.003"]
        self.assertTrue(s.retracted)
        self.assertEqual(s.authors, ["van der Berg, R."])
        apply_grade(s)
        self.assertEqual(s.grade, "D")

    def test_book_type_hint_and_landing_page_url(self):
        s = self.by_id["oa:W4300000004"]
        self.assertEqual(s.design, "book")
        self.assertIsNone(s.venue)
        self.assertIsNone(s.peer_reviewed)
        self.assertEqual(s.url, "https://example.org/books/persuasion")

    def test_display_name_fallback_and_review_design(self):
        s = self.by_id["doi:10.5555/review.2022.005"]
        self.assertEqual(s.title, "A Systematic Review of Gamification in Marketing")
        self.assertEqual(s.design, "systematic-review")
        self.assertTrue(s.peer_reviewed)

    def test_parse_work_needs_an_identifier_and_a_title(self):
        self.assertIsNone(parse_work({"title": "No id at all"}))
        self.assertIsNone(parse_work({"id": "https://openalex.org/W1"}))
        s = parse_work({"id": "https://openalex.org/W1", "title": "Only Id and Title"})
        self.assertEqual((s.id, s.doi, s.cited_by, s.year), ("oa:W1", None, None, None))


class OpenAlexRequestTests(unittest.TestCase):
    def test_search_url_carries_query_page_size_select_and_mailto(self):
        fetcher = FakeFetcher({OPENALEX_SEARCH: fixture_text("openalex_search.json")})
        OpenAlexClient(fetcher, mailto="dev@example.org").search("curiosity gap", per_page=6)
        url = fetcher.calls[0]
        self.assertEqual(urlsplit(url).path, "/works")
        q = query_of(url)
        self.assertEqual(q["search"], ["curiosity gap"])
        self.assertEqual(q["per-page"], ["6"])
        self.assertEqual(q["mailto"], ["dev@example.org"])
        self.assertIn("abstract_inverted_index", q["select"][0])
        self.assertNotIn("filter", q)

    def test_year_filter_and_no_mailto(self):
        fetcher = FakeFetcher({OPENALEX_SEARCH: fixture_text("openalex_search.json")})
        OpenAlexClient(fetcher).search("x", year_from=2020)
        q = query_of(fetcher.calls[0])
        self.assertEqual(q["filter"], ["from_publication_date:2020-01-01"])
        self.assertNotIn("mailto", q)

    def test_blank_query_makes_no_request(self):
        fetcher = FakeFetcher({OPENALEX_SEARCH: oa_empty()})
        self.assertEqual(OpenAlexClient(fetcher).search("   "), [])
        self.assertEqual(fetcher.calls, [])

    def test_page_size_is_clamped(self):
        fetcher = FakeFetcher({OPENALEX_SEARCH: oa_empty()})
        client = OpenAlexClient(fetcher)
        client.search("x", per_page=0)
        client.search("x", per_page=5000)
        self.assertEqual([query_of(u)["per-page"] for u in fetcher.calls], [["1"], ["200"]])

    def test_by_doi_builds_a_doi_path_and_parses_the_work(self):
        fetcher = FakeFetcher({OPENALEX_WORK: fixture_text("openalex_work.json")})
        study = OpenAlexClient(fetcher, mailto="dev@example.org").by_doi("https://doi.org/10.5555/Curiosity.2021.001")
        self.assertEqual(study.id, "doi:10.5555/curiosity.2021.001")
        self.assertEqual(urlsplit(fetcher.calls[0]).path, "/works/doi:10.5555/curiosity.2021.001")
        self.assertEqual(query_of(fetcher.calls[0])["mailto"], ["dev@example.org"])

    def test_by_doi_percent_encodes_special_characters(self):
        fetcher = FakeFetcher({OPENALEX_WORK: (404, "{}")})
        OpenAlexClient(fetcher).by_doi("10.1016/S0165-0173(98)00019-8")
        self.assertIn("/works/doi:10.1016/s0165-0173%2898%2900019-8", fetcher.calls[0])

    def test_by_doi_unknown_or_invalid_returns_none(self):
        fetcher = FakeFetcher({OPENALEX_WORK: (404, "{}")})
        client = OpenAlexClient(fetcher)
        self.assertIsNone(client.by_doi("10.5555/missing.1"))
        calls_before = len(fetcher.calls)
        self.assertIsNone(client.by_doi("not a doi"))
        self.assertEqual(len(fetcher.calls), calls_before)      # no request for a malformed DOI


class OpenAlexFailureTests(unittest.TestCase):
    def test_http_error_raises_research_api_error(self):
        client = OpenAlexClient(FakeFetcher({OPENALEX_SEARCH: (500, "boom"), OPENALEX_WORK: (429, "slow down")}))
        with self.assertRaises(ResearchApiError) as ctx:
            client.search("x")
        self.assertIn("HTTP 500", str(ctx.exception))
        with self.assertRaises(ResearchApiError):
            client.by_doi("10.5555/x.1")

    def test_malformed_payloads_raise_research_api_error(self):
        for body in ("<html>nope</html>", "[]", json.dumps({"meta": {}})):
            client = OpenAlexClient(FakeFetcher({OPENALEX_SEARCH: body}))
            with self.assertRaises(ResearchApiError, msg=body):
                client.search("x")

    def test_network_errors_propagate_as_fetch_error(self):
        client = OpenAlexClient(FakeFetcher({OPENALEX_SEARCH: FetchError("dns failure")}))
        with self.assertRaises(FetchError):
            client.search("x")


class InvertedIndexTests(unittest.TestCase):
    def test_rebuilds_text_in_position_order_even_when_keys_are_shuffled(self):
        index = {"world": [1, 3], "Hello": [0], "again": [4], "wide": [2]}
        self.assertEqual(abstract_from_inverted_index(index), "Hello world wide world again")

    def test_empty_none_and_malformed_inputs(self):
        self.assertIsNone(abstract_from_inverted_index(None))
        self.assertIsNone(abstract_from_inverted_index({}))
        self.assertEqual(abstract_from_inverted_index({"ok": [0], "bad": "x", "worse": ["a"]}), "ok")


def oa_empty() -> str:
    return json.dumps({"meta": {"count": 0}, "results": []})


if __name__ == "__main__":
    unittest.main()
