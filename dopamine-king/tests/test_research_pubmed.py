import json
import unittest
from urllib.parse import parse_qs, urlsplit

from dopamine_king.net import FakeFetcher
from dopamine_king.research.models import ResearchApiError
from dopamine_king.research.pubmed import PubMedClient, _author, parse_summary
from dopamine_king.research.search import ALL_SOURCES, SOURCES, search_studies

ESEARCH = json.dumps({"esearchresult": {"count": "3", "idlist": ["29202116", "30000001", "30000002", "30000003"]}})
ESUMMARY = json.dumps({"result": {
    "uids": ["29202116", "30000001", "30000002", "30000003"],
    "29202116": {
        "uid": "29202116", "pubdate": "2018 Feb", "source": "Lasers Med Sci", "fulljournalname": "Lasers in medical science",
        "title": "Photobiomodulation therapy for the improvement of muscular performance and reduction of muscular fatigue associated with exercise in healthy people: a systematic review and meta-analysis.",
        "authors": [{"name": "Vanin AA", "authtype": "Author"}, {"name": "Verhagen E", "authtype": "Author"}, {"name": "Some Collective", "authtype": "CollectiveName"}],
        "pubtype": ["Journal Article", "Meta-Analysis", "Systematic Review"], "pmcrefcount": 120,
        "articleids": [{"idtype": "pubmed", "value": "29202116"}, {"idtype": "doi", "value": "10.1007/s10103-017-2368-6"}]},
    "30000001": {
        "uid": "30000001", "pubdate": "2019", "source": "J Test", "title": "A randomised trial of red light.",
        "authors": [{"name": "Novak J", "authtype": "Author"}], "pubtype": ["Journal Article", "Randomized Controlled Trial"],
        "articleids": [{"idtype": "pubmed", "value": "30000001"}], "elocationid": "doi: 10.5555/Trial.2019.001"},
    "30000002": {
        "uid": "30000002", "pubdate": "2020 Mar 5", "source": "Old J", "title": "A paper that was withdrawn",
        "authors": [], "pubtype": ["Journal Article", "Retracted Publication"], "articleids": []},
    "30000003": {"uid": "30000003", "title": "", "pubtype": []},
}})


def query_of(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query)


class ParsingTests(unittest.TestCase):
    def setUp(self):
        self.fetcher = FakeFetcher({
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?*": ESEARCH,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?*": ESUMMARY,
        })
        self.studies = PubMedClient(self.fetcher, mailto="dev@example.org").search("photobiomodulation exercise", retmax=4)
        self.by_id = {s.id: s for s in self.studies}

    def test_untitled_record_is_skipped_and_order_is_kept(self):
        self.assertEqual(list(self.by_id), ["doi:10.1007/s10103-017-2368-6", "doi:10.5555/trial.2019.001", "pmid:30000002"])

    def test_meta_analysis_from_publication_types(self):
        s = self.by_id["doi:10.1007/s10103-017-2368-6"]
        self.assertEqual(s.design, "meta-analysis")
        self.assertEqual((s.year, s.source, s.peer_reviewed, s.cited_by), (2018, "pubmed", True, 120))
        self.assertEqual(s.venue, "Lasers in medical science")
        self.assertEqual(s.authors, ["Vanin, A. A.", "Verhagen, E."])          # collective names are not people
        self.assertTrue(s.title.endswith("meta-analysis"))                      # the trailing full stop is dropped
        self.assertEqual(s.url, "https://doi.org/10.1007/s10103-017-2368-6")
        self.assertIsNone(s.abstract)
        self.assertFalse(s.verified)

    def test_doi_from_elocationid_and_rct_type(self):
        s = self.by_id["doi:10.5555/trial.2019.001"]
        self.assertEqual((s.design, s.year, s.doi), ("rct", 2019, "10.5555/trial.2019.001"))

    def test_retracted_and_no_doi(self):
        s = self.by_id["pmid:30000002"]
        self.assertTrue(s.retracted)
        self.assertEqual(s.url, "https://pubmed.ncbi.nlm.nih.gov/30000002/")
        self.assertIsNone(s.doi)

    def test_requests_are_polite_and_well_formed(self):
        first, second = self.fetcher.calls
        q = query_of(first)
        self.assertEqual((q["db"], q["retmode"], q["tool"], q["email"]), (["pubmed"], ["json"], ["dopamine-king"], ["dev@example.org"]))
        self.assertEqual(q["term"], ["photobiomodulation exercise"])
        self.assertEqual(query_of(second)["id"], ["29202116,30000001,30000002,30000003"])

    def test_year_filter_and_api_key(self):
        fetcher = FakeFetcher({"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?*": json.dumps({"esearchresult": {"idlist": []}})})
        PubMedClient(fetcher, api_key="k").search("x", year_from=2020)
        q = query_of(fetcher.calls[0])
        self.assertEqual((q["mindate"], q["datetype"], q["api_key"]), (["2020"], ["pdat"], ["k"]))
        self.assertEqual(len(fetcher.calls), 1)                                   # no ids, so no second request

    def test_author_formatting(self):
        self.assertEqual(_author("Hamblin MR"), "Hamblin, M. R.")
        self.assertEqual(_author("de Freitas LF"), "de Freitas, L. F.")
        self.assertEqual(_author("WALT"), "WALT")
        self.assertIsNone(_author(""))

    def test_empty_query_searches_nothing(self):
        self.assertEqual(PubMedClient(FakeFetcher({})).search("  "), [])
        self.assertIsNone(parse_summary({"uid": "1", "title": ""}))


class ErrorTests(unittest.TestCase):
    def test_http_error_and_bad_payloads_are_reported(self):
        for body, status in (("", 500), ("not json", 200), ("[]", 200), (json.dumps({"esearchresult": {}}), 200)):
            fetcher = FakeFetcher({"https://eutils.ncbi.nlm.nih.gov/*": (status, body)})
            with self.assertRaises(ResearchApiError, msg=body):
                PubMedClient(fetcher).search("x")


class FederatedSearchTests(unittest.TestCase):
    def test_pubmed_is_opt_in(self):
        self.assertNotIn("pubmed", SOURCES)
        self.assertIn("pubmed", ALL_SOURCES)

    def test_search_studies_can_use_pubmed(self):
        fetcher = FakeFetcher({
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?*": ESEARCH,
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?*": ESUMMARY,
        })
        studies, errors = search_studies("photobiomodulation exercise", fetcher, sources=("pubmed",), limit=5)
        self.assertEqual(errors, [])
        self.assertEqual(studies[0].id, "doi:10.1007/s10103-017-2368-6")          # a meta-analysis ranks first
        self.assertTrue(all(s.grade for s in studies))


if __name__ == "__main__":
    unittest.main()
