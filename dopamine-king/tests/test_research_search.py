import unittest
from urllib.parse import parse_qs, urlsplit

from dopamine_king.net import FakeFetcher, FetchError
from dopamine_king.research.search import dedupe_key, merge_studies, search_studies
from tests.test_research_common import (
    ARXIV_QUERY, CROSSREF_SEARCH, OPENALEX_SEARCH, arxiv_entry, arxiv_feed, cr_item, cr_search_payload,
    make_study, oa_payload, oa_work,
)


def fetcher_with(oa=None, cr=None, ax=None) -> FakeFetcher:
    routes = {}
    if oa is not None:
        routes[OPENALEX_SEARCH] = oa
    if cr is not None:
        routes[CROSSREF_SEARCH] = cr
    if ax is not None:
        routes[ARXIV_QUERY] = ax
    return FakeFetcher(routes)


class MergeAndDedupeTests(unittest.TestCase):
    def test_same_doi_across_sources_becomes_one_richer_record(self):
        fetcher = fetcher_with(
            oa=oa_payload(oa_work("W1", "Curiosity and clicks", doi="10.5555/a.1", cited=50, abstract="OpenAlex abstract text.")),
            cr=cr_search_payload(cr_item("10.5555/A.1", "Curiosity and clicks", cited=80)),
        )
        studies, errors = search_studies("curiosity", fetcher, sources=("openalex", "crossref"))
        self.assertEqual(errors, [])
        self.assertEqual(len(studies), 1)
        s = studies[0]
        self.assertEqual((s.id, s.cited_by), ("doi:10.5555/a.1", 80))      # best citation count wins
        self.assertEqual(s.abstract, "OpenAlex abstract text.")             # gap filled from the other source

    def test_records_without_doi_merge_on_normalised_title(self):
        fetcher = fetcher_with(
            oa=oa_payload(oa_work("W9", "Headline Questions: Do They Work?", year=2021)),
            ax=arxiv_feed(arxiv_entry("2999.00007", "Headline questions - do they work", year=2021)),
        )
        studies, errors = search_studies("headline", fetcher, sources=("openalex", "arxiv"))
        self.assertEqual((len(studies), errors), (1, []))

    def test_preprint_collapses_into_its_published_version(self):
        fetcher = fetcher_with(
            cr=cr_search_payload(cr_item("10.5555/pub.1", "Scaling Headline Tests", year=2022, abstract=None)),
            ax=arxiv_feed(arxiv_entry("2999.00008", "Scaling headline tests", year=2021, summary="Preprint abstract.")),
        )
        studies, _ = search_studies("scaling", fetcher, sources=("crossref", "arxiv"))
        self.assertEqual(len(studies), 1)
        s = studies[0]
        self.assertEqual((s.id, s.doi, s.peer_reviewed), ("doi:10.5555/pub.1", "10.5555/pub.1", True))
        self.assertEqual(s.abstract, "Preprint abstract.")                   # borrowed from the preprint

    def test_arxiv_record_with_the_published_doi_merges_by_doi(self):
        fetcher = fetcher_with(
            cr=cr_search_payload(cr_item("10.5555/pub.2", "Different Wording In Journal")),
            ax=arxiv_feed(arxiv_entry("2999.00009", "Another preprint title", doi="10.5555/PUB.2")),
        )
        studies, _ = search_studies("x", fetcher, sources=("crossref", "arxiv"))
        self.assertEqual(len(studies), 1)

    def test_datacite_arxiv_doi_merges_with_the_arxiv_record(self):
        fetcher = fetcher_with(
            oa=oa_payload(oa_work("W3", "Generative Engines Under Test", doi="10.48550/arXiv.2999.12345", source_type=None)),
            ax=arxiv_feed(arxiv_entry("2999.12345", "Generative Engines Under Test")),
        )
        studies, _ = search_studies("generative", fetcher, sources=("openalex", "arxiv"))
        self.assertEqual(len(studies), 1)

    def test_two_published_dois_with_one_title_stay_separate(self):
        fetcher = fetcher_with(cr=cr_search_payload(
            cr_item("10.5555/one.1", "Introduction"), cr_item("10.5555/two.2", "Introduction")))
        studies, _ = search_studies("introduction", fetcher, sources=("crossref",))
        self.assertEqual(len(studies), 2)

    def test_retraction_reported_by_one_source_wins_and_sinks_the_record(self):
        fetcher = fetcher_with(
            oa=oa_payload(oa_work("W1", "Viral Emotions", doi="10.5555/r.1", retracted=True, cited=10),
                          oa_work("W2", "Solid Study", doi="10.5555/s.1", cited=1)),
            cr=cr_search_payload(cr_item("10.5555/r.1", "Viral Emotions", cited=12)),
        )
        studies, _ = search_studies("emotions", fetcher, sources=("openalex", "crossref"))
        self.assertEqual([s.doi for s in studies], ["10.5555/s.1", "10.5555/r.1"])
        self.assertTrue(studies[1].retracted)
        self.assertEqual(studies[1].grade, "D")

    def test_dedupe_key_unit(self):
        self.assertEqual(dedupe_key(make_study(doi="10.5555/a.1")), "doi:10.5555/a.1")
        self.assertEqual(dedupe_key(make_study(doi="10.48550/arxiv.2311.09735v2")), "arxiv:2311.09735")
        self.assertEqual(dedupe_key(make_study(study_id="arxiv:2999.1234")), "arxiv:2999.1234")
        self.assertEqual(dedupe_key(make_study("Hello, World!")), "title:hello world")

    def test_merge_studies_keeps_distinct_records_and_fills_unknown_design(self):
        a = make_study("Same Title", design="unknown", doi="10.5555/x.1", cited=1, authors=[])
        b = make_study("same title", design="rct", doi="10.5555/x.1", cited=9, authors=["Roe, R."])
        c = make_study("Another")
        merged = merge_studies([a, b, c])
        self.assertEqual(len(merged), 2)
        self.assertEqual((merged[0].design, merged[0].authors, merged[0].cited_by), ("rct", ["Roe, R."], 9))


class RankingTests(unittest.TestCase):
    def test_sorted_by_grade_score_then_citations(self):
        fetcher = fetcher_with(oa=oa_payload(
            oa_work("W5", "Remarks on content", year=None, cited=0),
            oa_work("W3", "Notes on content", doi="10.5555/d3", year=None, cited=5),
            oa_work("W2", "A field experiment on subject lines", doi="10.5555/d2", year=2020, cited=30),
            oa_work("W4", "Thoughts on content", doi="10.5555/d4", year=None, cited=9),
            oa_work("W1", "Emotion and sharing: a meta-analysis", doi="10.5555/d1", year=2020, cited=3),
        ))
        studies, _ = search_studies("content", fetcher, sources=("openalex",))
        self.assertEqual(
            [s.id for s in studies],
            ["doi:10.5555/d1", "doi:10.5555/d2", "doi:10.5555/d4", "doi:10.5555/d3", "oa:W5"],
        )
        self.assertEqual([s.grade for s in studies], ["A", "A", "D", "D", "D"])

    def test_limit_applies_after_ranking(self):
        works = [oa_work(f"W{i}", f"Plain note {i}", doi=f"10.5555/n{i}", cited=i, year=None) for i in range(1, 6)]
        fetcher = fetcher_with(oa=oa_payload(*works))
        top, _ = search_studies("note", fetcher, sources=("openalex",), limit=2)
        self.assertEqual([s.doi for s in top], ["10.5555/n5", "10.5555/n4"])
        self.assertEqual(search_studies("note", fetcher, sources=("openalex",), limit=0)[0], [])

    def test_results_are_graded_and_unverified(self):
        fetcher = fetcher_with(oa=oa_payload(oa_work("W1", "Some study", doi="10.5555/g.1")))
        (s,), _ = search_studies("study", fetcher, sources=("openalex",))
        self.assertIn(s.grade, ("A", "B", "C", "D"))
        self.assertGreater(s.grade_score, 0)
        self.assertFalse(s.verified)


class ErrorIsolationTests(unittest.TestCase):
    def test_a_network_failure_in_one_source_does_not_stop_the_others(self):
        fetcher = fetcher_with(
            oa=oa_payload(oa_work("W1", "Survivor", doi="10.5555/s.1")),
            cr=FetchError("timeout"),
            ax=arxiv_feed(arxiv_entry("2999.00010", "Another survivor")),
        )
        studies, errors = search_studies("x", fetcher)
        self.assertEqual(len(studies), 2)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("crossref:"))
        self.assertIn("timeout", errors[0])

    def test_http_errors_are_reported_per_source(self):
        fetcher = fetcher_with(oa=(500, "boom"), cr=cr_search_payload(cr_item("10.5555/c.1", "From Crossref")))
        studies, errors = search_studies("x", fetcher, sources=("openalex", "crossref"))
        self.assertEqual(len(studies), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("openalex", errors[0])
        self.assertIn("HTTP 500", errors[0])

    def test_all_sources_failing_returns_empty_results_and_three_errors(self):
        fetcher = fetcher_with(oa=(503, ""), cr=FetchError("down"), ax="<broken")
        studies, errors = search_studies("x", fetcher)
        self.assertEqual(studies, [])
        self.assertEqual([e.split(":")[0] for e in errors], ["openalex", "crossref", "arxiv"])

    def test_unknown_source_and_empty_query_are_reported_not_raised(self):
        fetcher = fetcher_with(oa=oa_payload(oa_work("W1", "A", doi="10.5555/a.1")))
        studies, errors = search_studies("x", fetcher, sources=("openalex", "scholar"))
        self.assertEqual(len(studies), 1)
        self.assertIn("scholar", errors[0])
        self.assertEqual(search_studies("   ", fetcher), ([], ["empty query"]))


class ParameterTests(unittest.TestCase):
    def test_year_from_filters_all_sources_and_reaches_openalex(self):
        fetcher = fetcher_with(
            oa=oa_payload(oa_work("W1", "Old", doi="10.5555/o.1", year=2015), oa_work("W2", "New", doi="10.5555/n.1", year=2022),
                          oa_work("W3", "Undated", doi="10.5555/u.1", year=None)),
            ax=arxiv_feed(arxiv_entry("2999.00011", "Old preprint", year=2012)),
        )
        studies, _ = search_studies("x", fetcher, sources=("openalex", "arxiv"), year_from=2020)
        self.assertEqual([s.title for s in studies], ["New"])
        q = parse_qs(urlsplit(fetcher.calls[0]).query)
        self.assertEqual(q["filter"], ["from_publication_date:2020-01-01"])

    def test_mailto_reaches_openalex_and_crossref(self):
        seen = []

        def crossref_route(url, headers):
            seen.append(headers)
            return cr_search_payload()

        fetcher = FakeFetcher({OPENALEX_SEARCH: oa_payload(), CROSSREF_SEARCH: crossref_route})
        search_studies("x", fetcher, sources=("openalex", "crossref"), mailto="dev@example.org")
        self.assertEqual(parse_qs(urlsplit(fetcher.calls[0]).query)["mailto"], ["dev@example.org"])
        self.assertIn("mailto:dev@example.org", seen[0]["User-Agent"])

    def test_duplicate_source_names_run_once(self):
        fetcher = fetcher_with(oa=oa_payload())
        search_studies("x", fetcher, sources=("openalex", "openalex"))
        self.assertEqual(len(fetcher.calls), 1)


if __name__ == "__main__":
    unittest.main()
