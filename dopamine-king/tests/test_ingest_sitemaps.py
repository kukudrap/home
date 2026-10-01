import gzip
import unittest
from pathlib import Path

from dopamine_king.ingest.sitemaps import (
    DEFAULT_CONTENT_PATTERN,
    SitemapDoc,
    SitemapEntry,
    content_pattern,
    iter_sitemap_urls,
    parse_sitemap,
)
from dopamine_king.net import FakeFetcher

FX = Path(__file__).parent / "fixtures" / "ingest"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def fixture(name: str) -> bytes:
    return (FX / name).read_bytes()


def urlset(*locs: str) -> str:
    return f'<urlset xmlns="{NS}">' + "".join(f"<url><loc>{u}</loc></url>" for u in locs) + "</urlset>"


def index(*locs: str) -> str:
    return f'<sitemapindex xmlns="{NS}">' + "".join(f"<sitemap><loc>{u}</loc></sitemap>" for u in locs) + "</sitemapindex>"


def acme_fetcher(**extra) -> FakeFetcher:
    routes = {
        "https://acme.example/sitemap.xml": fixture("sitemap_index.xml"),
        "https://acme.example/post-sitemap.xml": fixture("sitemap_posts.xml"),
        "https://acme.example/news-sitemap.xml.gz": gzip.compress(fixture("sitemap_news.xml")),
        "https://acme.example/broken-post-sitemap.xml": (500, "server error"),
        "https://acme.example/sitemap-products.xml": urlset("https://acme.example/products/a"),
    }
    routes.update(extra)
    return FakeFetcher(routes)


class ParseSitemapTests(unittest.TestCase):
    def test_urlset_with_image_and_video_extensions(self):
        doc = parse_sitemap(fixture("sitemap_posts.xml"))
        self.assertIsInstance(doc, SitemapDoc)
        self.assertEqual(doc.kind, "urlset")
        first = doc.entries[0]
        self.assertEqual(first.loc, "https://acme.example/blog/spring-trail-shoes-2026")
        self.assertEqual(first.lastmod, "2026-03-01T09:30:00+00:00")
        self.assertEqual((first.image_count, first.video_count), (2, 1))
        self.assertEqual(doc.entries[1], SitemapEntry("https://acme.example/blog/pack-your-bag", "2026-02-20", 0, 0))
        self.assertIsNone(doc.entries[4].lastmod)

    def test_sitemap_index(self):
        doc = parse_sitemap(fixture("sitemap_index.xml"))
        self.assertEqual(doc.kind, "index")
        self.assertEqual(len(doc.entries), 4)
        self.assertEqual(doc.entries[1].loc, "https://acme.example/post-sitemap.xml")

    def test_gzip_is_detected_by_magic_bytes(self):
        doc = parse_sitemap(gzip.compress(fixture("sitemap_news.xml")))
        self.assertEqual([e.loc for e in doc.entries],
                         ["https://acme.example/newsroom/q1-results", "https://acme.example/newsroom/new-store"])

    def test_str_input_and_bom(self):
        self.assertEqual(len(parse_sitemap(urlset("https://x.test/a")).entries), 1)
        self.assertEqual(len(parse_sitemap(b"\xef\xbb\xbf" + urlset("https://x.test/a").encode()).entries), 1)

    def test_plain_text_sitemap(self):
        doc = parse_sitemap("https://x.test/a\nhttps://x.test/b\n\nnot a url\n")
        self.assertEqual((doc.kind, [e.loc for e in doc.entries]), ("urlset", ["https://x.test/a", "https://x.test/b"]))

    def test_entries_without_a_valid_loc_are_dropped(self):
        doc = parse_sitemap(urlset("https://x.test/a", "ftp://x.test/b", "   ", "/relative"))
        self.assertEqual([e.loc for e in doc.entries], ["https://x.test/a"])

    def test_documents_that_are_not_sitemaps_raise_value_error(self):
        for bad in ("<html><body/></html>", "plain words only", "", b"\x1f\x8b\x08 broken gzip", "<urlset>"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_sitemap(bad)


class ContentPatternTests(unittest.TestCase):
    GOOD = [
        "https://acme.example/blog/spring-post",
        "https://blog.hubspot.com/marketing/seo-tips",
        "https://www.apple.com/newsroom/2026/03/foo/",
        "https://example.com/press-releases/2026/launch",
        "https://example.com/en-us/stories/jane-and-co",
        "https://example.com/product-updates/new-thing",
        "https://example.com/case-studies/acme",
        "https://example.com/magazine/issue-5/article-one",
        "https://news.example.com/world/event",
        "https://example.com/learn/intro-to-seo",
        "https://example.com/insights/q1-report",
    ]
    BAD = [
        "https://acme.example/blog/",                      # index page, not an article
        "https://acme.example/blog",
        "https://acme.example/blog/tag/running",
        "https://acme.example/blog/category/gear",
        "https://acme.example/blog/author/jane",
        "https://acme.example/blog/page/2",
        "https://acme.example/blog/post?page=2",
        "https://acme.example/blog/2026/03/",              # date archive
        "https://acme.example/blog/feed",
        "https://acme.example/shop/learn-to-code-kit",     # term inside a product slug
        "https://acme.example/blogging/tips",
        "https://acme.example/careers/blog-writer",
        "https://acme.example/products/trail-shoe-x",
        "https://acme.example/privacy",
        "https://acme.example/legal/terms",
        "https://acme.example/news/photo.jpg",
        "https://acme.example/news/press-kit.pdf",
        "https://acme.example/search?q=blog",
        "https://blog.example.com/",
    ]

    def test_content_urls_match(self):
        for url in self.GOOD:
            with self.subTest(url=url):
                self.assertTrue(DEFAULT_CONTENT_PATTERN.search(url))

    def test_junk_urls_do_not_match(self):
        for url in self.BAD:
            with self.subTest(url=url):
                self.assertFalse(DEFAULT_CONTENT_PATTERN.search(url))

    def test_brand_content_paths_widen_the_pattern(self):
        pattern = content_pattern(["/our-world", "/x/"])
        self.assertTrue(pattern.search("https://x.com/our-world/a-post"))
        self.assertTrue(pattern.search("https://x.com/blog/y"))  # the default still applies
        self.assertFalse(pattern.search("https://x.com/our-world/"))
        self.assertFalse(pattern.search("https://x.com/our-world/tag/z"))
        self.assertFalse(pattern.search("https://x.com/shop/y"))
        self.assertIs(content_pattern([]), DEFAULT_CONTENT_PATTERN)


class IterSitemapUrlsTests(unittest.TestCase):
    def test_index_recursion_newest_first_with_content_filter(self):
        fetcher = acme_fetcher()
        found = iter_sitemap_urls(fetcher, "https://acme.example/sitemap.xml")
        self.assertEqual([e.loc for e in found], [
            "https://acme.example/blog/spring-trail-shoes-2026",   # 2026-03-01
            "https://acme.example/newsroom/q1-results",            # 2026-02-27 (gzipped child)
            "https://acme.example/blog/pack-your-bag",             # 2026-02-20
            "https://acme.example/newsroom/new-store",             # 2026-02-10
            "https://acme.example/news/old-announcement",          # 2024-01-15
        ])
        self.assertEqual(found[0].image_count, 2)

    def test_content_looking_sub_sitemaps_are_fetched_before_the_rest(self):
        fetcher = acme_fetcher()
        iter_sitemap_urls(fetcher, "https://acme.example/sitemap.xml")
        self.assertEqual(fetcher.calls[0], "https://acme.example/sitemap.xml")
        self.assertEqual(fetcher.calls[-1], "https://acme.example/sitemap-products.xml")
        self.assertEqual(fetcher.calls[1], "https://acme.example/post-sitemap.xml")  # newest content sitemap first

    def test_one_broken_sub_sitemap_does_not_abort_the_rest(self):
        errors = []
        found = iter_sitemap_urls(acme_fetcher(), "https://acme.example/sitemap.xml",
                                  on_error=lambda url, err: errors.append((url, str(err))))
        self.assertEqual(len(found), 5)
        self.assertEqual(errors, [("https://acme.example/broken-post-sitemap.xml", "HTTP 500")])

    def test_unparseable_and_failing_sub_sitemaps_are_tolerated(self):
        fetcher = acme_fetcher(**{
            "https://acme.example/post-sitemap.xml": "<<< not xml",
            "https://acme.example/news-sitemap.xml.gz": OSError("disk on fire"),
        })
        found = iter_sitemap_urls(fetcher, "https://acme.example/sitemap.xml")
        self.assertEqual(found, [])  # nothing readable, but no exception either

    def test_top_level_failure_returns_an_empty_list(self):
        self.assertEqual(iter_sitemap_urls(FakeFetcher(), "https://nowhere.example/sitemap.xml"), [])

    def test_since_filters_entries_and_whole_stale_sub_sitemaps(self):
        fetcher = acme_fetcher()
        found = iter_sitemap_urls(fetcher, "https://acme.example/sitemap.xml", since="2026-02-15")
        self.assertEqual([e.loc.rsplit("/", 1)[-1] for e in found],
                         ["spring-trail-shoes-2026", "q1-results", "pack-your-bag"])
        fetcher = acme_fetcher()
        recent = iter_sitemap_urls(fetcher, "https://acme.example/sitemap.xml", since="2026-02-28")
        self.assertEqual([e.loc.rsplit("/", 1)[-1] for e in recent], ["spring-trail-shoes-2026"])
        self.assertNotIn("https://acme.example/news-sitemap.xml.gz", fetcher.calls)  # child lastmod is older than the cutoff
        self.assertEqual(iter_sitemap_urls(acme_fetcher(), "https://acme.example/sitemap.xml", since="2026-03-05"), [])

    def test_max_urls_keeps_the_newest(self):
        found = iter_sitemap_urls(acme_fetcher(), "https://acme.example/sitemap.xml", max_urls=2)
        self.assertEqual([e.loc.rsplit("/", 1)[-1] for e in found], ["spring-trail-shoes-2026", "q1-results"])

    def test_max_sitemaps_caps_the_number_of_requests(self):
        fetcher = acme_fetcher()
        iter_sitemap_urls(fetcher, "https://acme.example/sitemap.xml", max_sitemaps=2)
        self.assertEqual(len(fetcher.calls), 2)

    def test_max_depth_stops_the_recursion(self):
        fetcher = acme_fetcher()
        self.assertEqual(iter_sitemap_urls(fetcher, "https://acme.example/sitemap.xml", max_depth=0), [])
        self.assertEqual(fetcher.calls, ["https://acme.example/sitemap.xml"])

    def test_nested_indexes_and_cycles(self):
        fetcher = FakeFetcher({
            "https://x.test/a.xml": index("https://x.test/b.xml", "https://x.test/a.xml"),
            "https://x.test/b.xml": index("https://x.test/c.xml"),
            "https://x.test/c.xml": urlset("https://x.test/blog/deep"),
        })
        self.assertEqual([e.loc for e in iter_sitemap_urls(fetcher, "https://x.test/a.xml")], ["https://x.test/blog/deep"])
        self.assertEqual(fetcher.calls.count("https://x.test/a.xml"), 1)
        self.assertEqual(iter_sitemap_urls(fetcher, "https://x.test/a.xml", max_depth=1), [])

    def test_duplicates_collapse_by_canonical_url(self):
        fetcher = FakeFetcher({"https://x.test/s.xml": urlset(
            "https://www.x.test/blog/a?utm_source=x", "https://x.test/blog/a/", "https://x.test/blog/b")})
        self.assertEqual(len(iter_sitemap_urls(fetcher, "https://x.test/s.xml")), 2)

    def test_pattern_none_and_custom_pattern(self):
        fetcher = FakeFetcher({"https://x.test/s.xml": urlset("https://x.test/products/a", "https://x.test/blog/b")})
        self.assertEqual(len(iter_sitemap_urls(fetcher, "https://x.test/s.xml", pattern=None)), 2)
        self.assertEqual(len(iter_sitemap_urls(fetcher, "https://x.test/s.xml", pattern=r"/products/")), 1)

    def test_errors_without_a_callback_are_silent(self):
        found = iter_sitemap_urls(FakeFetcher({"https://x.test/s.xml": (404, "")}), "https://x.test/s.xml")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
