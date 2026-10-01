import gzip
import tempfile
import unittest
from pathlib import Path

from dopamine_king.models import Brand, ContentItem, canonical_url, item_id_for_url
from dopamine_king.net import FakeFetcher, FetchError, HttpFetcher, Response, maybe_gunzip
from dopamine_king.store import Store


class CanonicalUrlTests(unittest.TestCase):
    def test_strips_tracking_fragment_www_and_trailing_slash(self):
        a = canonical_url("https://www.Example.com/Blog/post/?utm_source=x&b=2&a=1#section")
        b = canonical_url("https://example.com/Blog/post?a=1&b=2")
        self.assertEqual(a, b)
        self.assertEqual(item_id_for_url("https://example.com/p/?fbclid=zzz"), item_id_for_url("https://www.example.com/p"))

    def test_default_ports_dropped_custom_kept(self):
        self.assertEqual(canonical_url("https://example.com:443/x"), "https://example.com/x")
        self.assertEqual(canonical_url("http://example.com:8080/x"), "http://example.com:8080/x")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.store.upsert_brand(Brand(id="acme", name="Acme", cohort="tech", country="US"))
        self.store.upsert_brand(Brand(id="kofi", name="Kofi", cohort="cz-local", synthetic=True))

    def tearDown(self):
        self.store.close()

    def _item(self, i, brand="acme", **kw):
        return ContentItem(id=f"i{i}", brand_id=brand, platform="blog", format="article",
                           title=f"Title {i}", published_at=f"2026-01-0{i}T10:00:00+00:00", **kw)

    def test_roundtrip_filters_and_counts(self):
        self.assertTrue(self.store.upsert_item(self._item(1, signals={"views": 10.0})))
        self.assertFalse(self.store.upsert_item(self._item(1, signals={"views": 12.0})))
        self.store.upsert_item(self._item(2, brand="kofi", synthetic=True))
        self.assertEqual(self.store.get_item("i1").signals["views"], 12.0)
        self.assertEqual(self.store.count_items(), 2)
        self.assertEqual(self.store.count_items(cohort="cz-local"), 1)
        self.assertEqual([i.id for i in self.store.iter_items(synthetic=False)], ["i1"])
        self.assertEqual(self.store.stats()["by_cohort"], {"tech": 1, "cz-local": 1})

    def test_kv_analysis_and_fetch_log(self):
        self.store.kv_set("cursor", {"page": 3})
        self.assertEqual(self.store.kv_get("cursor"), {"page": 3})
        self.assertIsNone(self.store.kv_get("missing"))
        self.store.set_analysis("i1", {"score": 61.5})
        self.assertEqual(self.store.get_analysis("i1"), {"score": 61.5})
        self.store.log_fetch("https://example.com", 200, 123, "ok")
        self.assertEqual(self.store.recent_fetches(1)[0]["status"], 200)

    def test_persists_on_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "k.sqlite"
            with Store(path) as s:
                s.upsert_brand(Brand(id="b", name="B", cohort="tech"))
            with Store(path) as s:
                self.assertEqual(s.get_brand("b").name, "B")


class FakeFetcherTests(unittest.TestCase):
    def test_routes_wildcards_and_404(self):
        f = FakeFetcher({"https://a.test/x": "hello", "https://b.test/*": (201, b"ok", {"X-Y": "1"})})
        self.assertEqual(f.get("https://a.test/x").text, "hello")
        r = f.get("https://b.test/anything")
        self.assertEqual((r.status, r.header("x-y")), (201, "1"))
        self.assertEqual(f.get("https://nope.test/").status, 404)
        self.assertEqual(len(f.calls), 3)

    def test_exception_route_raises(self):
        f = FakeFetcher({"https://a.test/": FetchError("boom")})
        with self.assertRaises(FetchError):
            f.get("https://a.test/")


class HttpFetcherTests(unittest.TestCase):
    def make(self, script, **kw):
        calls, sleeps = [], []
        queue = list(script)

        def transport(url, headers, timeout, max_bytes):
            calls.append(dict(headers))
            item = queue.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        t = [0.0]

        def clock():
            return t[0]

        def sleep(s):
            sleeps.append(s)
            t[0] += s

        fetcher = HttpFetcher("test-agent", transport=transport, sleep=sleep, clock=clock, now=lambda: 1000 + t[0], **kw)
        return fetcher, calls, sleeps

    def test_retries_503_with_retry_after_then_succeeds(self):
        f, calls, sleeps = self.make([Response("u", 503, {"retry-after": "7"}), Response("u", 200, {}, b"fine")],
                                     min_interval=0)
        self.assertEqual(f.get("https://h.test/a").text, "fine")
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [7.0])

    def test_gives_up_after_max_retries_on_network_error(self):
        f, calls, _ = self.make([FetchError("x")] * 3, max_retries=2, min_interval=0)
        with self.assertRaises(FetchError):
            f.get("https://h.test/a")
        self.assertEqual(len(calls), 3)

    def test_per_host_rate_limit(self):
        f, _, sleeps = self.make([Response("u", 200, {}, b"1"), Response("u", 200, {}, b"2"),
                                  Response("u", 200, {}, b"3")], min_interval=2.0)
        f.get("https://h.test/a")
        f.get("https://h.test/b")
        f.get("https://other.test/c")
        self.assertEqual(sleeps, [2.0])
        f.set_host_delay("h.test", 5.0)

    def test_cache_ttl_and_conditional_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            f, calls, _ = self.make(
                [Response("u", 200, {"etag": '"v1"', "content-type": "text/xml"}, b"<a/>"), Response("u", 304, {})],
                min_interval=0, cache_dir=tmp, cache_ttl=10,
            )
            first = f.get("https://h.test/feed")
            self.assertFalse(first.from_cache)
            again = f.get("https://h.test/feed")
            self.assertTrue(again.from_cache)
            self.assertEqual(len(calls), 1)
            f._now = lambda: 5000  # expire the cache
            third = f.get("https://h.test/feed")
            self.assertTrue(third.from_cache)
            self.assertEqual(calls[1]["If-None-Match"], '"v1"')
            self.assertEqual(third.body, b"<a/>")


class ResponseTests(unittest.TestCase):
    def test_text_charset_and_json(self):
        r = Response("u", 200, {"content-type": "text/html; charset=iso-8859-2"}, "žluťoučký".encode("iso-8859-2"))
        self.assertEqual(r.text, "žluťoučký")
        self.assertEqual(Response("u", 200, {}, b'{"a": 1}').json(), {"a": 1})

    def test_maybe_gunzip(self):
        self.assertEqual(maybe_gunzip(gzip.compress(b"<urlset/>")), b"<urlset/>")
        self.assertEqual(maybe_gunzip(b"plain"), b"plain")


if __name__ == "__main__":
    unittest.main()
