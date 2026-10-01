import json
import unittest
from urllib.parse import parse_qs, unquote, urlsplit

from dopamine_king.net import FakeFetcher, FetchError
from dopamine_king.research.ledger import Ledger
from tests.test_research_common import (
    CROSSREF_SEARCH, CROSSREF_WORK, cr_item, cr_search_payload, cr_work_payload, make_study,
)


class CrossrefStub:
    """Answers Crossref by-DOI and bibliographic-search requests from two dictionaries."""

    def __init__(self, works=None, searches=None):
        self.works = works or {}            # lower-case doi -> payload str, (status, body) or Exception
        self.searches = searches or {}      # title -> payload str
        self.headers = []

    def __call__(self, url, headers):
        self.headers.append(headers)
        parts = urlsplit(url)
        if parts.path.startswith("/works/"):
            return self.works.get(unquote(parts.path[len("/works/"):]), (404, "Resource not found."))
        title = parse_qs(parts.query)["query.bibliographic"][0]
        return self.searches.get(title, cr_search_payload())

    def fetcher(self):
        return FakeFetcher({CROSSREF_WORK: self, CROSSREF_SEARCH: self})


def one(ledger, fetcher, **kw):
    (result,) = ledger.verify(fetcher, **kw)
    return result


class VerifyByDoiTests(unittest.TestCase):
    def check(self, study, payload, **kw):
        stub = CrossrefStub(works={study.doi: payload})
        ledger = Ledger([study])
        return one(ledger, stub.fetcher(), **kw), study

    def test_matching_title_and_year_verifies(self):
        s = make_study("Curiosity Gaps in Headline Writing", doi="10.5555/ok.1", year=2020)
        result, _ = self.check(s, cr_work_payload(cr_item("10.5555/ok.1", "Curiosity gaps in headline writing", year=2020)))
        self.assertEqual((result["status"], result["study_id"]), ("verified", s.id))
        self.assertTrue(s.verified)
        self.assertEqual(s.verification_note, result["detail"])
        self.assertIn("confirms", s.verification_note)

    def test_result_dicts_carry_exactly_the_documented_keys(self):
        s = make_study("T", doi="10.5555/ok.2", year=2020)
        result, _ = self.check(s, cr_work_payload(cr_item("10.5555/ok.2", "T", year=2020)))
        self.assertEqual(set(result), {"study_id", "status", "detail"})

    def test_different_title_is_a_mismatch(self):
        s = make_study("Completely Different Paper", doi="10.5555/bad.2", year=2020)
        result, _ = self.check(s, cr_work_payload(cr_item("10.5555/bad.2", "Another Subject Entirely", year=2020)))
        self.assertEqual(result["status"], "mismatch")
        self.assertFalse(s.verified)
        self.assertIn("title differs", s.verification_note)
        self.assertIn("Another Subject Entirely", s.verification_note)

    def test_different_year_is_a_mismatch(self):
        s = make_study("Same Title Here", doi="10.5555/yr.3", year=2010)
        result, _ = self.check(s, cr_work_payload(cr_item("10.5555/yr.3", "Same Title Here", year=2020)))
        self.assertEqual(result["status"], "mismatch")
        self.assertIn("year differs", s.verification_note)

    def test_issue_year_matches_when_crossref_lists_online_first_earlier(self):
        s = make_study("Online First Paper", doi="10.5555/of.4", year=2021)
        item = cr_item("10.5555/of.4", "Online First Paper", year=2020, **{"published-print": {"date-parts": [[2021, 3]]}})
        result, _ = self.check(s, cr_work_payload(item))
        self.assertEqual(result["status"], "verified")

    def test_title_without_subtitle_still_verifies(self):
        s = make_study("The psychology of curiosity: A review and reinterpretation", doi="10.5555/sub.5", year=1994)
        result, _ = self.check(s, cr_work_payload(cr_item("10.5555/sub.5", "The psychology of curiosity", year=1994)))
        self.assertEqual(result["status"], "verified")

    def test_unknown_doi_is_not_found_and_unverified(self):
        s = make_study("Ghost", doi="10.5555/ghost.6", year=2020, verified=True)
        result, _ = self.check(s, (404, "Resource not found."))
        self.assertEqual(result["status"], "not_found")
        self.assertFalse(s.verified)

    def test_malformed_doi_is_reported_without_a_request(self):
        s = make_study("Typo", doi="10.5555/ok.1", year=2020)
        s.doi = "10.55"
        stub = CrossrefStub()
        result = one(Ledger([s]), stub.fetcher())
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(stub.headers, [])

    def test_crossref_retraction_flags_the_study_and_regrades_it(self):
        s = make_study("Viral Emotions", doi="10.5555/ret.7", year=2019, design="meta-analysis")
        ledger = Ledger([s])
        self.assertEqual(s.grade, "A")
        item = cr_item("10.5555/ret.7", "Viral Emotions", year=2019,
                       **{"updated-by": [{"DOI": "10.5555/ret.7n", "type": "retraction", "label": "Retraction"}]})
        (result,) = ledger.verify(CrossrefStub(works={s.doi: cr_work_payload(item)}).fetcher())
        self.assertEqual(result["status"], "verified")
        self.assertIn("retraction", result["detail"])
        self.assertTrue(s.retracted)
        self.assertEqual(s.grade, "D")

    def test_a_mismatching_record_never_transfers_its_retraction(self):
        s = make_study("My Honest Study", doi="10.5555/ret.8", year=2019)
        item = cr_item("10.5555/ret.8", "A Totally Unrelated Retracted Paper", year=2019, relation={"is-retracted-by": []})
        result, _ = self.check(s, cr_work_payload(item))
        self.assertEqual(result["status"], "mismatch")
        self.assertFalse(s.retracted)


class VerifyFailureTests(unittest.TestCase):
    def test_network_failure_is_reported_and_leaves_the_study_untouched(self):
        s = make_study("Flaky", doi="10.5555/net.1", year=2020, verified=True, verification_note="earlier note")
        ledger = Ledger([s])
        stub = CrossrefStub(works={s.doi: FetchError("connection reset")})
        result = one(ledger, stub.fetcher())
        self.assertEqual(result["status"], "error")
        self.assertIn("connection reset", result["detail"])
        self.assertTrue(s.verified)
        self.assertEqual(s.verification_note, "earlier note")

    def test_http_error_is_an_error_not_a_not_found(self):
        s = make_study("Busy", doi="10.5555/busy.1", year=2020)
        result = one(Ledger([s]), CrossrefStub(works={s.doi: (503, "overloaded")}).fetcher())
        self.assertEqual(result["status"], "error")
        self.assertFalse(s.verified)
        self.assertEqual(s.verification_note, "")

    def test_one_failure_does_not_stop_the_rest(self):
        a = make_study("Alpha Study", doi="10.5555/a.1", year=2020)
        b = make_study("Beta Study", doi="10.5555/b.1", year=2020)
        stub = CrossrefStub(works={a.doi: FetchError("boom"), b.doi: cr_work_payload(cr_item(b.doi, "Beta Study"))})
        results = Ledger([a, b]).verify(stub.fetcher())
        self.assertEqual([(r["study_id"], r["status"]) for r in results], [(a.id, "error"), (b.id, "verified")])

    def test_garbage_response_is_an_error(self):
        s = make_study("Garbage", doi="10.5555/g.1", year=2020)
        result = one(Ledger([s]), CrossrefStub(works={s.doi: "<html>not json</html>"}).fetcher())
        self.assertEqual(result["status"], "error")


class VerifySuggestionTests(unittest.TestCase):
    TITLE = "Hooked Habits in Synthetic Products"

    def suggest(self, items, year=2014, title=None):
        s = make_study(title or self.TITLE, year=year)           # no DOI
        stub = CrossrefStub(searches={s.title: cr_search_payload(*items)})
        result = one(Ledger([s]), stub.fetcher())
        return result, s

    def test_single_close_match_with_equal_year_is_suggested_not_applied(self):
        result, s = self.suggest([cr_item("10.5555/suggested.7", self.TITLE, year=2014)])
        self.assertEqual(result["status"], "suggestion")
        self.assertIn("10.5555/suggested.7", s.verification_note)
        self.assertIn("Not applied", s.verification_note)
        self.assertIsNone(s.doi)
        self.assertFalse(s.verified)

    def test_two_matches_are_ambiguous_and_nothing_is_suggested(self):
        result, s = self.suggest([cr_item("10.5555/one.1", self.TITLE), cr_item("10.5555/two.2", self.TITLE)], year=2020)
        self.assertEqual(result["status"], "not_found")
        self.assertNotIn("10.5555", s.verification_note)
        self.assertIsNone(s.doi)

    def test_no_match_year_mismatch_or_weak_title_means_no_suggestion(self):
        for items, year in (
            ([], 2014),
            ([cr_item("10.5555/y.1", self.TITLE, year=2015)], 2014),                       # year differs
            ([cr_item("10.5555/t.1", "Hooked on Something Rather Different", year=2014)], 2014),  # title too far
        ):
            result, s = self.suggest(items, year=year)
            self.assertEqual(result["status"], "not_found", items)
            self.assertIsNone(s.doi)
            self.assertNotIn("Suggested", s.verification_note)

    def test_suggestion_needs_a_year_on_our_side(self):
        s = make_study(self.TITLE, year=None)
        stub = CrossrefStub(searches={self.TITLE: cr_search_payload(cr_item("10.5555/s.1", self.TITLE, year=2014))})
        self.assertEqual(one(Ledger([s]), stub.fetcher())["status"], "not_found")

    def test_search_failure_is_an_error(self):
        s = make_study(self.TITLE, year=2014)
        fetcher = FakeFetcher({CROSSREF_SEARCH: FetchError("offline")})
        self.assertEqual(one(Ledger([s]), fetcher)["status"], "error")


class VerifyRequestTests(unittest.TestCase):
    def test_every_study_gets_one_result_in_ledger_order(self):
        a = make_study("A", doi="10.5555/a.1")
        b = make_study("B")
        c = make_study("C", doi="10.5555/c.1")
        results = Ledger([a, b, c]).verify(CrossrefStub().fetcher())
        self.assertEqual([r["study_id"] for r in results], [a.id, b.id, c.id])

    def test_mailto_goes_into_the_user_agent(self):
        s = make_study("A", doi="10.5555/a.1")
        stub = CrossrefStub()
        Ledger([s]).verify(stub.fetcher(), mailto="dev@example.org")
        self.assertIn("mailto:dev@example.org", stub.headers[0]["User-Agent"])

    def test_dois_with_special_characters_are_percent_encoded_in_the_request(self):
        s = make_study("Wanting", doi="10.1016/s0165-0173(98)00019-8")
        fetcher = CrossrefStub().fetcher()
        Ledger([s]).verify(fetcher)
        self.assertIn("/works/10.1016/s0165-0173%2898%2900019-8", fetcher.calls[0])

    def test_verify_never_edits_identifiers(self):
        s = make_study("Hooked Habits in Synthetic Products", year=2014)
        stub = CrossrefStub(searches={s.title: cr_search_payload(cr_item("10.5555/new.1", s.title, year=2014))})
        ledger = Ledger([s])
        before = (s.id, s.doi, s.title, s.year)
        ledger.verify(stub.fetcher())
        self.assertEqual((s.id, s.doi, s.title, s.year), before)
        self.assertTrue(json.dumps(ledger.to_dict()))


class VerifySeedTests(unittest.TestCase):
    """The seed ledger run against a Crossref that echoes each seed record back."""

    def test_every_seed_doi_verifies_against_an_echoing_crossref_and_the_rest_are_not_found(self):
        ledger = Ledger.load()
        works = {
            s.doi: cr_work_payload(cr_item(s.doi, s.title, year=s.year)) for s in ledger.studies if s.doi
        }
        results = ledger.verify(CrossrefStub(works=works).fetcher())
        by_id = {r["study_id"]: r["status"] for r in results}
        for study in ledger.studies:
            expected = "verified" if study.doi else "not_found"
            self.assertEqual(by_id[study.id], expected, study.id)
            self.assertEqual(study.verified, bool(study.doi), study.id)
        self.assertEqual(ledger.stats()["verified"], sum(1 for s in ledger.studies if s.doi))


if __name__ == "__main__":
    unittest.main()
