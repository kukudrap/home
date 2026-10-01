import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dopamine_king.ingest.signals import enrich_signals, hn_signal, import_analytics_csv, parse_hn_response
from dopamine_king.models import Brand, ContentItem, item_id_for_url
from dopamine_king.net import FakeFetcher, FetchError
from dopamine_king.store import Store

FX = Path(__file__).parent / "fixtures" / "ingest"
HN = json.loads((FX / "hn_response.json").read_text("utf-8"))
PAGE = "https://acme.example/blog/spring-trail-shoes-2026"
NOW = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)


def hn_fetcher(payload=HN, status=200):
    return FakeFetcher({"https://hn.algolia.com/api/v1/search*": (status, json.dumps(payload))})


class ParseHnTests(unittest.TestCase):
    def test_best_matching_story_wins(self):
        # two stories match (http+www+utm and https): the higher scored one is reported with its own comment count
        self.assertEqual(parse_hn_response(HN, PAGE), {"hn_points": 87.0, "hn_comments": 23.0})

    def test_url_canonicalisation(self):
        variants = [
            PAGE,
            PAGE + "/",
            "https://www.acme.example/blog/spring-trail-shoes-2026?utm_source=newsletter&fbclid=abc",
            "http://acme.example/blog/spring-trail-shoes-2026#comments",
        ]
        for url in variants:
            with self.subTest(url=url):
                self.assertEqual(parse_hn_response(HN, url)["hn_points"], 87.0)

    def test_no_match_gives_an_empty_dict(self):
        self.assertEqual(parse_hn_response(HN, "https://acme.example/blog/unknown"), {})
        self.assertEqual(parse_hn_response({"hits": []}, PAGE), {})
        self.assertEqual(parse_hn_response(HN, "https://other.example/blog/spring-trail-shoes-2026"), {})

    def test_other_pages_of_the_same_site_do_not_match(self):
        self.assertEqual(parse_hn_response(HN, "https://acme.example/blog/another-page")["hn_points"], 300.0)

    def test_hits_without_a_url_and_odd_payloads_are_ignored(self):
        for payload in ({}, [], None, "text", {"hits": "nope"}, {"hits": [None, 5, {"url": 7}, {"title": "x"}]}):
            with self.subTest(payload=payload):
                self.assertEqual(parse_hn_response(payload, PAGE), {})

    def test_missing_points_and_comments_count_as_zero(self):
        payload = {"hits": [{"url": PAGE, "points": None}]}
        self.assertEqual(parse_hn_response(payload, PAGE), {"hn_points": 0.0, "hn_comments": 0.0})


class HnSignalTests(unittest.TestCase):
    def test_request_url_and_result(self):
        fetcher = hn_fetcher()
        signal = hn_signal(fetcher, PAGE + "?utm_source=x")
        self.assertEqual(signal, {"hn_points": 87.0, "hn_comments": 23.0})
        self.assertEqual(fetcher.calls, [
            "https://hn.algolia.com/api/v1/search?query=https%3A%2F%2Facme.example%2Fblog%2Fspring-trail-shoes-2026%3Futm_source%3Dx"
            "&restrictSearchableAttributes=url&tags=story&hitsPerPage=5"])

    def test_http_errors_and_garbage_give_an_empty_dict(self):
        self.assertEqual(hn_signal(hn_fetcher(status=500), PAGE), {})
        self.assertEqual(hn_signal(FakeFetcher({"https://hn.algolia.com/*": "<html>oops</html>"}), PAGE), {})

    def test_network_errors_propagate_to_the_caller(self):
        with self.assertRaises(FetchError):
            hn_signal(FakeFetcher({"https://hn.algolia.com/*": FetchError("offline")}), PAGE)


class CsvImportTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.store.upsert_brand(Brand(id="acme", name="Acme", cohort="fashion-beauty"))

    def tearDown(self):
        self.store.close()

    def items(self):
        return {i.title: i for i in self.store.iter_items(brand_id="acme")}

    def test_czech_semicolon_file_with_bom_and_decimal_commas(self):
        count = import_analytics_csv(self.store, FX / "analytics_cs_semicolon.csv", "acme")
        self.assertEqual(count, 2)  # the row without a title is skipped
        first = self.items()["Jarní kolekce je tady"]
        self.assertEqual(first.id, item_id_for_url("https://www.example.cz/blog/jarni-kolekce"))
        self.assertEqual(first.url, "https://example.cz/blog/jarni-kolekce")
        self.assertEqual(first.signals, {"impressions": 12345.0, "clicks": 321.0, "likes": 1204.0, "shares": 56.0,
                                         "comments": 18.0, "saves": 77.0, "ctr": 2.6})
        self.assertEqual(first.published_at, "2026-03-14T00:00:00+00:00")
        self.assertEqual(first.lang, "cs")
        self.assertEqual((first.platform, first.format), ("blog", "post"))
        self.assertIs(first.meta["first_party"], True)
        self.assertTrue(first.excerpt.startswith("Představujeme novou jarní kolekci"))
        second = self.items()["Příběh naší značky"]
        self.assertEqual(second.id, "fp-" + hashlib.sha1("acmePříběh naší značky".encode("utf-8")).hexdigest()[:12])
        self.assertIsNone(second.url)
        self.assertEqual(second.signals["ctr"], 1.7)
        self.assertEqual(second.published_at, "2026-03-02T00:00:00+00:00")

    def test_comma_delimited_text_with_quoted_thousands(self):
        text = (FX / "analytics_comma_en.csv").read_text("utf-8")
        self.assertEqual(import_analytics_csv(self.store, text, "acme", platform="instagram", format="carousel"), 2)
        item = self.items()["Launch day, behind the scenes"]
        self.assertEqual((item.platform, item.format), ("instagram", "carousel"))
        self.assertEqual(item.excerpt, "A short caption, with a comma")
        self.assertEqual(item.signals["likes"], 1234.0)  # "1,234" inside a comma separated file is a thousands separator
        self.assertEqual(item.signals["watch_time"], 1200.5)
        self.assertEqual((item.signals["impressions"], item.signals["views"], item.signals["ctr"]), (15000.0, 9000.0, 2.8))
        sparse = self.items()["Second post"]
        self.assertEqual(sparse.signals, {"impressions": 2500.0})  # empty cells are absent, not zero
        self.assertEqual(sparse.published_at, "2026-03-05T10:00:00+00:00")

    def test_tab_separated_file_and_english_aliases(self):
        self.assertEqual(import_analytics_csv(self.store, FX / "analytics_tab.tsv", "acme"), 1)
        item = self.items()["Tabbed post"]
        self.assertEqual(item.signals, {"impressions": 4200.0, "views": 3.5})  # Reach -> impressions, tab means decimal comma
        self.assertEqual(item.url, "https://example.com/t/1")

    def test_path_string_and_text_are_both_accepted(self):
        path = str(FX / "analytics_tab.tsv")
        self.assertEqual(import_analytics_csv(self.store, path, "acme"), 1)
        self.assertEqual(import_analytics_csv(self.store, Path(path), "acme"), 1)
        self.assertEqual(import_analytics_csv(self.store, "title,views\nOne,5\nTwo,6\n", "acme"), 2)
        self.assertEqual(len(self.items()), 3)

    def test_header_aliases_ignore_case_and_diacritics(self):
        text = "NADPIS;ZOBRAZENÍ;Zhlédnutí;Sdílení;Uložení;Watch Time;Kliknutí;Lajky;Komentáře\nPost;1;2;3;4;5;6;7;8\n"
        import_analytics_csv(self.store, text, "acme")
        self.assertEqual(self.items()["Post"].signals, {
            "impressions": 1.0, "views": 2.0, "shares": 3.0, "saves": 4.0, "watch_time": 5.0, "clicks": 6.0,
            "likes": 7.0, "comments": 8.0})

    def test_when_two_columns_share_a_meaning_the_first_one_wins(self):
        import_analytics_csv(self.store, "title;Zobrazení;Dosah\nPost;100;40\n", "acme")
        self.assertEqual(self.items()["Post"].signals, {"impressions": 100.0})

    def test_number_formats(self):
        cases = {"1 234,5": 1234.5, "1.234.567": 1234567.0, "12 %": 12.0, "3.5": 3.5, "-5": -5.0, "1" + chr(0xA0) + "000": 1000.0}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                import_analytics_csv(self.store, f"title;views\nrow;{raw}\n", "acme")
                self.assertEqual(self.items()["row"].signals["views"], expected)
        for junk in ("-", "n/a", "", "abc", "1,2,3x"):
            with self.subTest(junk=junk):
                import_analytics_csv(self.store, f"title;views\njunk row;{junk}\n", "acme")
                self.assertNotIn("views", self.items()["junk row"].signals)

    def test_date_formats(self):
        cases = {
            "2026-03-05T10:00:00Z": "2026-03-05T10:00:00+00:00",
            "14. 3. 2026": "2026-03-14T00:00:00+00:00",
            "14.3.2026 10:30": "2026-03-14T10:30:00+00:00",
            "03/25/2026": "2026-03-25T00:00:00+00:00",  # only valid as month first
            "05/03/2026": "2026-03-05T00:00:00+00:00",  # ambiguous: day first
            "2026-03-05": "2026-03-05T00:00:00+00:00",
            "someday": None,
            "": None,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                import_analytics_csv(self.store, f"title,date\nrow,{raw}\n", "acme")
                self.assertEqual(self.items()["row"].published_at, expected)

    def test_rows_without_a_title_and_empty_input(self):
        self.assertEqual(import_analytics_csv(self.store, "title,views\n,5\n  ,6\n", "acme"), 0)
        self.assertEqual(import_analytics_csv(self.store, "url,views\nhttps://x.test/a,5\n", "acme"), 0)  # no title column
        self.assertEqual(import_analytics_csv(self.store, "title,views\n", "acme"), 0)
        self.assertEqual(import_analytics_csv(self.store, "\n", "acme"), 0)
        self.assertEqual(self.store.count_items(), 0)

    def test_reimport_is_idempotent(self):
        text = "url,title,views\nhttps://x.test/a,A,1\n,No url,2\n"
        import_analytics_csv(self.store, text, "acme")
        import_analytics_csv(self.store, text.replace(",1\n", ",9\n"), "acme")
        self.assertEqual(self.store.count_items(brand_id="acme"), 2)
        self.assertEqual(self.items()["A"].signals["views"], 9.0)

    def test_excerpt_is_capped_and_ragged_rows_survive(self):
        text = "title,text,views\nLong," + "word " * 300 + ",5\nShort row\n"
        self.assertEqual(import_analytics_csv(self.store, text, "acme"), 2)
        self.assertLessEqual(len(self.items()["Long"].excerpt), 300)
        self.assertEqual(self.items()["Short row"].signals, {})

    def test_legacy_encodings(self):
        text = "Nadpis;Zobrazení\nŘádek s diakritikou;1 500\n"
        with tempfile.TemporaryDirectory() as tmp:
            cp1250 = Path(tmp) / "cp1250.csv"
            cp1250.write_bytes(text.encode("cp1250"))
            utf16 = Path(tmp) / "utf16.csv"
            utf16.write_bytes(text.encode("utf-16"))
            self.assertEqual(import_analytics_csv(self.store, cp1250, "acme"), 1)
            self.assertEqual(import_analytics_csv(self.store, utf16, "acme"), 1)
        item = self.items()["Řádek s diakritikou"]
        self.assertEqual(item.signals["impressions"], 1500.0)

    def test_importing_for_a_brand_that_is_not_in_the_store_still_stores_items(self):
        import_analytics_csv(self.store, "title,views\nOrphan,1\n", "ghost")
        self.assertEqual(len([i for i in self.store.iter_items(brand_id="ghost")]), 0)  # joins need a brand row
        self.store.upsert_brand(Brand(id="ghost", name="Ghost", cohort="tech"))
        self.assertEqual(self.store.count_items(brand_id="ghost"), 1)


class EnrichSignalsTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.store.upsert_brand(Brand(id="acme", name="Acme", cohort="tech"))

    def tearDown(self):
        self.store.close()

    def add(self, name, url="auto", day=1, **kw):
        url = f"https://acme.example/blog/{name}" if url == "auto" else url
        item = ContentItem(id=f"id-{name}", brand_id="acme", platform="blog", format="article", title=name, url=url,
                           published_at=f"2026-03-{day:02d}T10:00:00+00:00", **kw)
        self.store.upsert_item(item)
        return item

    def test_matching_items_get_hn_signals(self):
        self.add("spring-trail-shoes-2026", signals={"comments": 3.0})
        self.add("unrelated")
        fetcher = hn_fetcher()
        self.assertEqual(enrich_signals(self.store, fetcher), 1)
        item = self.store.get_item("id-spring-trail-shoes-2026")
        self.assertEqual(item.signals, {"comments": 3.0, "hn_points": 87.0, "hn_comments": 23.0})
        self.assertIn("hn_checked", item.meta)
        self.assertNotIn("hn_points", self.store.get_item("id-unrelated").signals)
        self.assertEqual(len(fetcher.calls), 2)

    def test_synthetic_urlless_and_already_enriched_items_are_skipped(self):
        self.add("synthetic-one", synthetic=True)
        self.add("no-url", url=None)
        self.add("done", signals={"hn_points": 5.0})
        fetcher = hn_fetcher()
        self.assertEqual(enrich_signals(self.store, fetcher), 0)
        self.assertEqual(fetcher.calls, [])

    def test_items_without_a_match_are_not_asked_again_until_the_recheck_window_passes(self):
        self.add("nothing-here")
        fetcher = hn_fetcher({"hits": []})
        enrich_signals(self.store, fetcher, now=lambda: NOW)
        enrich_signals(self.store, fetcher, now=lambda: NOW + timedelta(days=3))
        self.assertEqual(len(fetcher.calls), 1)
        enrich_signals(self.store, fetcher, now=lambda: NOW + timedelta(days=15))
        self.assertEqual(len(fetcher.calls), 2)

    def test_limit_applies_per_call_and_later_calls_make_progress(self):
        for n in range(5):
            self.add(f"post-{n}", day=n + 1)
        fetcher = hn_fetcher({"hits": []})
        enrich_signals(self.store, fetcher, limit=2)
        self.assertEqual(len(fetcher.calls), 2)
        enrich_signals(self.store, fetcher, limit=2)
        enrich_signals(self.store, fetcher, limit=2)
        self.assertEqual(len(fetcher.calls), 5)
        self.assertEqual(len(set(fetcher.calls)), 5)  # newest first, nothing asked twice

    def test_failures_leave_items_untouched_and_do_not_stop_the_batch(self):
        self.add("spring-trail-shoes-2026", day=3)
        self.add("flaky", day=2)
        self.add("server-error", day=1)

        def route(url, headers):
            if "flaky" in url:
                return FetchError("timeout")
            if "server-error" in url:
                return (503, "unavailable")
            return (200, json.dumps(HN))

        fetcher = FakeFetcher({"https://hn.algolia.com/*": route})
        self.assertEqual(enrich_signals(self.store, fetcher), 1)
        self.assertNotIn("hn_checked", self.store.get_item("id-flaky").meta)
        self.assertNotIn("hn_checked", self.store.get_item("id-server-error").meta)  # retried on the next run
        self.assertIn("hn_checked", self.store.get_item("id-spring-trail-shoes-2026").meta)

    def test_other_sources_are_ignored(self):
        self.add("spring-trail-shoes-2026")
        fetcher = hn_fetcher()
        self.assertEqual(enrich_signals(self.store, fetcher, sources=("reddit",)), 0)
        self.assertEqual(fetcher.calls, [])

    def test_first_party_rows_can_be_enriched_too(self):
        import_analytics_csv(self.store, "url,title,views\nhttps://acme.example/blog/spring-trail-shoes-2026,Own post,10\n", "acme")
        self.assertEqual(enrich_signals(self.store, hn_fetcher()), 1)
        item = next(self.store.iter_items(brand_id="acme"))
        self.assertEqual((item.signals["views"], item.signals["hn_points"]), (10.0, 87.0))
        self.assertIs(item.meta["first_party"], True)


if __name__ == "__main__":
    unittest.main()
