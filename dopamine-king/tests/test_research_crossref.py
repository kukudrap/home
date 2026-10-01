import json
import unittest
from urllib.parse import parse_qs, urlsplit

from dopamine_king.net import FakeFetcher, FetchError, Response
from dopamine_king.research.crossref import CrossrefClient, is_retracted, parse_message, years_in
from dopamine_king.research.models import ResearchApiError
from tests.test_research_common import (
    CROSSREF_SEARCH, CROSSREF_WORK, cr_item, cr_search_payload, cr_work_payload, fixture_json, fixture_text,
)

DOI = "10.5555/curiosity.2021.001"


class CrossrefByDoiTests(unittest.TestCase):
    def setUp(self):
        self.fetcher = FakeFetcher({CROSSREF_WORK: fixture_text("crossref_work.json")})
        self.client = CrossrefClient(self.fetcher, mailto="dev@example.org")
        self.study = self.client.by_doi(DOI)

    def test_core_fields(self):
        s = self.study
        self.assertEqual(s.id, f"doi:{DOI}")
        self.assertEqual(s.doi, DOI)                     # upper case input in the payload is normalised
        self.assertEqual(s.title, "Curiosity Gaps in Headline Writing: A randomized controlled trial")
        self.assertEqual(s.authors, ["Doe, J. Q.", "Novák, J.", "Headline Research Consortium"])
        self.assertEqual(s.venue, "Journal of Synthetic Media Studies")
        self.assertEqual(s.cited_by, 88)
        self.assertEqual(s.url, f"https://doi.org/{DOI}")
        self.assertEqual((s.source, s.design, s.peer_reviewed), ("crossref", "rct", True))
        self.assertFalse(s.retracted)
        self.assertFalse(s.verified)

    def test_year_comes_from_issued_and_lookup_lists_every_known_year(self):
        self.assertEqual(self.study.year, 2020)
        study, years = self.client.lookup(DOI)
        self.assertEqual(study.id, self.study.id)
        self.assertEqual(years, frozenset({2020, 2021}))      # online-first 2020, print issue 2021

    def test_jats_markup_is_stripped_from_the_abstract(self):
        self.assertEqual(
            self.study.abstract,
            "We randomly assigned readers to curiosity gap headlines and measured clicks (p < 0.05). "
            "Effects were larger when the article answered the question.",
        )

    def test_request_url_and_polite_headers(self):
        seen = []

        def route(url, headers):
            seen.append((url, headers))
            return fixture_text("crossref_work.json")

        client = CrossrefClient(FakeFetcher({CROSSREF_WORK: route}), mailto="dev@example.org")
        client.by_doi("https://doi.org/10.5555/Curiosity.2021.001")
        url, headers = seen[0]
        self.assertEqual(url, f"https://api.crossref.org/works/{DOI}")
        self.assertIn("mailto:dev@example.org", headers["User-Agent"])
        self.assertIn("DopamineKing", headers["User-Agent"])
        self.assertEqual(headers["Accept"], "application/json")

    def test_without_mailto_the_fetchers_own_user_agent_is_kept(self):
        seen = []
        client = CrossrefClient(FakeFetcher({CROSSREF_WORK: lambda u, h: (seen.append(h) or fixture_text("crossref_work.json"))}))
        client.by_doi(DOI)
        self.assertNotIn("User-Agent", seen[0])

    def test_special_characters_in_the_doi_are_percent_encoded(self):
        fetcher = FakeFetcher({CROSSREF_WORK: (404, "Resource not found.")})
        CrossrefClient(fetcher).by_doi("10.1016/S0165-0173(98)00019-8")
        self.assertEqual(fetcher.calls[0], "https://api.crossref.org/works/10.1016/s0165-0173%2898%2900019-8")

    def test_unknown_and_malformed_dois(self):
        fetcher = FakeFetcher({CROSSREF_WORK: (404, "Resource not found.")})
        client = CrossrefClient(fetcher)
        self.assertIsNone(client.by_doi("10.5555/missing.1"))
        self.assertIsNone(client.lookup("10.5555/missing.1"))
        n = len(fetcher.calls)
        self.assertIsNone(client.by_doi("definitely not a doi"))
        self.assertEqual(len(fetcher.calls), n)


class CrossrefSearchTests(unittest.TestCase):
    def setUp(self):
        self.fetcher = FakeFetcher({CROSSREF_SEARCH: fixture_text("crossref_search.json")})
        self.client = CrossrefClient(self.fetcher)
        self.studies = {s.doi: s for s in self.client.search("headline curiosity", rows=9)}

    def test_item_without_title_is_skipped(self):
        self.assertEqual(len(self.studies), 8)
        self.assertNotIn("10.5555/untitled.2020.016", self.studies)

    def test_query_parameters(self):
        q = parse_qs(urlsplit(self.fetcher.calls[0]).query)
        self.assertEqual(q["query.bibliographic"], ["headline curiosity"])
        self.assertEqual(q["rows"], ["9"])
        self.assertIn("is-referenced-by-count", q["select"][0])
        self.assertIn("updated-by", q["select"][0])

    def test_sparse_record_keeps_missing_fields_null(self):
        s = self.studies["10.5555/sparse.2018.007"]
        self.assertEqual(s.year, 2018)                    # falls back to published-online
        self.assertEqual(s.authors, [])
        self.assertIsNone(s.venue)
        self.assertIsNone(s.abstract)
        self.assertEqual((s.cited_by, s.design), (0, "unknown"))

    def test_retraction_signals(self):
        flagged = {doi for doi, s in self.studies.items() if s.retracted}
        self.assertEqual(flagged, {
            "10.5555/retraction.2022.010",      # notice with update-to type retraction
            "10.5555/retracted.2019.003",        # updated-by type retraction
            "10.5555/relation.2017.011",         # relation is-retracted-by
            "10.5555/titleflag.2016.013",        # title starts with RETRACTED:
        })
        self.assertFalse(self.studies["10.5555/correction.2020.014"].retracted)

    def test_posted_content_is_a_preprint(self):
        s = self.studies["10.5555/posted.2023.015"]
        self.assertEqual((s.design, s.peer_reviewed), ("preprint", False))
        self.assertIsNone(s.venue)                        # empty container-title list

    def test_blank_query_makes_no_request(self):
        fetcher = FakeFetcher({CROSSREF_SEARCH: fixture_text("crossref_search.json")})
        self.assertEqual(CrossrefClient(fetcher).search(""), [])
        self.assertEqual(fetcher.calls, [])

    def test_search_matches_search_detailed(self):
        detailed = self.client.search_detailed("x")
        self.assertEqual([s.id for s, _ in detailed], [s.id for s in self.client.search("x")])
        self.assertTrue(all(isinstance(years, frozenset) for _, years in detailed))

    def test_a_rejected_select_key_falls_back_to_the_plain_query(self):
        def route(url, headers):
            if "select=" in url:
                return 400, "Select key not recognised"
            return fixture_text("crossref_search.json")

        fetcher = FakeFetcher({CROSSREF_SEARCH: route})
        self.assertEqual(len(CrossrefClient(fetcher).search("x")), 8)
        self.assertEqual(len(fetcher.calls), 2)
        self.assertNotIn("select=", fetcher.calls[1])


class CrossrefFailureTests(unittest.TestCase):
    def test_http_errors_and_bad_payloads(self):
        for body, status in (("boom", 503), ("<html/>", 200), (json.dumps({"status": "ok"}), 200),
                             (json.dumps({"message": {"items": "x"}}), 200)):
            client = CrossrefClient(FakeFetcher({CROSSREF_SEARCH: (status, body), CROSSREF_WORK: (status, body)}))
            with self.assertRaises(ResearchApiError, msg=(status, body)):
                client.search("x")

    def test_by_doi_http_error_is_not_confused_with_not_found(self):
        client = CrossrefClient(FakeFetcher({CROSSREF_WORK: (500, "oops")}))
        with self.assertRaises(ResearchApiError):
            client.by_doi(DOI)

    def test_network_error_propagates(self):
        client = CrossrefClient(FakeFetcher({CROSSREF_WORK: FetchError("timeout")}))
        with self.assertRaises(FetchError):
            client.by_doi(DOI)


class ParseMessageTests(unittest.TestCase):
    def test_requires_valid_doi_and_title(self):
        self.assertIsNone(parse_message({"title": ["No DOI"]}))
        self.assertIsNone(parse_message({"DOI": "bogus", "title": ["Bad DOI"]}))
        self.assertIsNone(parse_message({"DOI": "10.5555/x.1"}))
        study, years = parse_message({"DOI": "10.5555/X.1", "title": ["Ok"]})
        self.assertEqual((study.id, years), ("doi:10.5555/x.1", frozenset()))
        self.assertIsNone(study.year)

    def test_subtitle_is_appended_unless_already_in_the_title(self):
        a, _ = parse_message({"DOI": "10.5555/a.1", "title": ["Main"], "subtitle": ["The sub"]})
        b, _ = parse_message({"DOI": "10.5555/b.1", "title": ["Main: the sub"], "subtitle": ["The sub"]})
        self.assertEqual(a.title, "Main: The sub")
        self.assertEqual(b.title, "Main: the sub")

    def test_markup_and_entities_in_titles_are_cleaned(self):
        s, _ = parse_message({"DOI": "10.5555/a.1", "title": ["Dopamine &amp; <i>wanting</i>"]})
        self.assertEqual(s.title, "Dopamine & wanting")

    def test_abstract_title_element_and_leading_label_are_dropped(self):
        raw = {"DOI": "10.5555/a.1", "title": ["T"],
               "abstract": "<jats:title>Abstract</jats:title><jats:p>Body text.</jats:p>"}
        self.assertEqual(parse_message(raw)[0].abstract, "Body text.")
        raw["abstract"] = "Abstract: Body text."
        self.assertEqual(parse_message(raw)[0].abstract, "Body text.")
        raw["abstract"] = "<jats:p>  </jats:p>"
        self.assertIsNone(parse_message(raw)[0].abstract)

    def test_book_and_proceedings_types(self):
        book, _ = parse_message({"DOI": "10.5555/b.1", "title": ["A Book"], "type": "monograph"})
        proc, _ = parse_message({"DOI": "10.5555/p.1", "title": ["A Paper"], "type": "proceedings-article"})
        self.assertEqual((book.design, book.peer_reviewed), ("book", None))
        self.assertEqual(proc.peer_reviewed, True)

    def test_years_in_and_date_parts_with_nulls(self):
        self.assertEqual(years_in({"issued": {"date-parts": [[None]]}}), frozenset())
        self.assertEqual(
            years_in({"issued": {"date-parts": [[2019, 5]]}, "published-print": {"date-parts": [[2020]]}}),
            frozenset({2019, 2020}),
        )

    def test_is_retracted_unit(self):
        self.assertFalse(is_retracted({}))
        self.assertTrue(is_retracted({"update-to": [{"type": "withdrawal", "label": "Withdrawal"}]}))
        self.assertFalse(is_retracted({"update-to": [{"type": "expression_of_concern"}]}))
        self.assertTrue(is_retracted({}, "Retraction Note: Something"))
        self.assertFalse(is_retracted({}, "Retraction of papers in psychology: a study"))


class FixtureSanityTests(unittest.TestCase):
    def test_work_fixture_uses_the_real_envelope(self):
        data = fixture_json("crossref_work.json")
        self.assertEqual((data["status"], data["message-type"]), ("ok", "work"))
        self.assertIn("message", data)

    def test_response_helper_roundtrip(self):
        resp = Response("u", 200, {}, cr_work_payload(cr_item("10.5555/z.1", "Z")).encode())
        self.assertEqual(resp.json()["message"]["DOI"], "10.5555/z.1")
        self.assertEqual(len(json.loads(cr_search_payload(cr_item("10.5555/z.1", "Z")))["message"]["items"]), 1)


if __name__ == "__main__":
    unittest.main()
