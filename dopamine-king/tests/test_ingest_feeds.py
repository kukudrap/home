import json
import unittest
from pathlib import Path

from dopamine_king.ingest.feeds import FeedEntry, discover_feeds, parse_feed

FX = Path(__file__).parent / "fixtures" / "ingest"


def fixture(name: str) -> bytes:
    return (FX / name).read_bytes()


def rss(items: str, extra_ns: str = "") -> str:
    return f'<?xml version="1.0"?><rss version="2.0" {extra_ns}><channel><title>t</title>{items}</channel></rss>'


class Rss2Tests(unittest.TestCase):
    def setUp(self):
        self.entries = parse_feed(fixture("rss2.xml"), "https://acme.example/blog/feed")
        self.by_url = {e.url: e for e in self.entries}

    def test_entries_without_any_link_are_skipped(self):
        self.assertEqual(len(self.entries), 4)
        self.assertNotIn("An entry without any link", [e.title for e in self.entries])
        self.assertTrue(all(isinstance(e, FeedEntry) for e in self.entries))

    def test_fields_of_a_full_entry(self):
        e = self.by_url["https://acme.example/blog/spring-trail-shoes-2026?utm_source=rss"]
        self.assertEqual(e.title, "Spring trail shoes: what changed in 2026")
        self.assertEqual(e.published_at, "2026-03-01T08:30:00+00:00")
        self.assertEqual(e.categories, ["Trail", "Shoes"])  # case-insensitive de-duplication
        self.assertEqual(e.comments, 12)
        self.assertTrue(e.has_byline)
        self.assertEqual(e.image, "https://acme.example/img/spring-shoes-thumb.jpg")  # media:thumbnail beats the inline img

    def test_html_is_stripped_from_the_summary(self):
        e = self.by_url["https://acme.example/blog/spring-trail-shoes-2026?utm_source=rss"]
        self.assertEqual(
            e.summary, "Lighter foams, wider lasts and a few surprises. Here is what we learned testing 14 pairs."
        )
        self.assertNotIn("<", e.summary)

    def test_escaped_html_and_entities_are_decoded(self):
        e = self.by_url["https://acme.example/blog/pack-your-bag"]
        self.assertEqual(e.summary, "A short checklist & three mistakes to avoid.")

    def test_relative_links_are_resolved_against_the_base_url(self):
        self.assertIn("https://acme.example/blog/pack-your-bag", self.by_url)
        e = self.by_url["https://acme.example/blog/pack-your-bag"]
        self.assertEqual(e.image, "https://acme.example/img/bag.png")  # image enclosure
        self.assertIsNone(e.comments)  # the plain <comments> element is a URL, not a count

    def test_guid_is_used_when_the_link_is_missing(self):
        e = self.by_url["https://acme.example/blog/guid-only"]
        self.assertTrue(e.has_byline)  # <author> present, the name itself is never kept
        self.assertEqual(e.published_at, "2026-03-05T13:00:00+00:00")  # -0500 offset converted to UTC

    def test_unparseable_date_becomes_none(self):
        self.assertIsNone(self.by_url["https://acme.example/blog/odd-date"].published_at)

    def test_no_author_names_in_any_entry(self):
        dumped = json.dumps([e.to_dict() for e in self.entries])
        self.assertNotIn("Jane Doe", dumped)
        self.assertNotIn("Acme Press", dumped)

    def test_str_input_with_encoding_declaration_works(self):
        entries = parse_feed(fixture("rss2.xml").decode("utf-8"), "https://acme.example/")
        self.assertEqual(len(entries), 4)


class Rss1AndAtomTests(unittest.TestCase):
    def test_rss1_rdf(self):
        entries = parse_feed(fixture("rss1_rdf.xml"), "https://news.example.org/")
        self.assertEqual([e.url for e in entries],
                         ["https://news.example.org/press/launch", "https://news.example.org/press/results"])
        first, second = entries
        self.assertEqual(first.published_at, "2026-02-10T11:00:00+00:00")  # dc:date with +01:00
        self.assertEqual(first.categories, ["Product"])
        self.assertTrue(first.has_byline)
        self.assertEqual(second.summary, "Revenue grew 12%.")
        self.assertFalse(second.has_byline)

    def test_atom_entries(self):
        entries = parse_feed(fixture("atom.xml"), "https://studio.example/journal/atom.xml")
        self.assertEqual(len(entries), 2)  # the entry without a link is skipped
        first, second = entries
        self.assertEqual(first.url, "https://studio.example/journal/calm-interfaces")  # xml:base applied
        self.assertEqual(first.title, "Designing for calm interfaces")
        self.assertEqual(first.published_at, "2026-03-02T08:00:00+00:00")
        self.assertEqual(first.categories, ["Design", "UX"])
        self.assertEqual(first.comments, 7)  # thr:count on the replies link
        self.assertEqual(first.image, "https://studio.example/img/calm.jpg")
        self.assertTrue(first.has_byline)
        self.assertEqual(first.summary, "How we remove noise from product screens.")

    def test_atom_falls_back_to_updated_and_thr_total_and_xhtml(self):
        second = parse_feed(fixture("atom.xml"), "https://studio.example/journal/atom.xml")[1]
        self.assertEqual(second.published_at, "2026-03-08T14:30:00+00:00")  # updated, +02:00 converted
        self.assertEqual(second.comments, 3)  # thr:total element
        self.assertEqual(second.summary, "Notes on type pairing.")  # xhtml content
        self.assertFalse(second.has_byline)  # feed level author is not inherited
        self.assertEqual(second.image, "https://studio.example/img/type.png")  # first img of the content

    def test_json_feed(self):
        doc = {"version": "https://jsonfeed.org/version/1.1", "items": [
            {"id": "1", "url": "https://x.test/a", "title": "A", "date_published": "2026-01-02T03:04:05Z",
             "tags": ["a", "b"], "authors": [{"name": "Zed"}], "content_html": "<p>Hi <b>there</b></p>"},
            {"id": "no-url-and-not-http"},
        ]}
        entries = parse_feed(json.dumps(doc).encode(), "https://x.test/feed.json")
        self.assertEqual(len(entries), 1)
        self.assertEqual((entries[0].summary, entries[0].categories, entries[0].has_byline), ("Hi there", ["a", "b"], True))
        self.assertNotIn("Zed", json.dumps(entries[0].to_dict()))


class FeedRobustnessTests(unittest.TestCase):
    def test_html_entities_and_bare_ampersands_are_repaired(self):
        entries = parse_feed(fixture("feed_cs_malformed.xml"), "https://brand.example.cz/rss")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "Nová limonáda & zdravější složení")
        self.assertIn("Příliš žluťoučký kůň", entries[0].summary)
        self.assertEqual(entries[0].published_at, "2026-03-02T06:00:00+00:00")

    def test_legacy_czech_encodings_including_the_repair_path(self):
        template = ('<?xml version="1.0" encoding="{enc}"?><rss version="2.0"><channel><title>t</title><item>'
                    "<title>{title}</title><link>https://x.cz/a</link></item></channel></rss>")
        for enc in ("windows-1250", "iso-8859-2"):
            for title, expected in (("Příliš žluťoučký kůň", "Příliš žluťoučký kůň"), ("Žluťoučký & kůň", "Žluťoučký & kůň")):
                with self.subTest(enc=enc, title=title):
                    body = template.format(enc=enc, title=title).encode(enc)
                    self.assertEqual(parse_feed(body)[0].title, expected)

    def test_a_bad_entry_never_costs_the_whole_feed(self):
        body = rss("<item><title>Good</title><link>https://x.test/good</link></item>"
                   "<item><title>Bad link</title><link>javascript:alert(1)</link></item>"
                   "<item><title>Empty</title></item>"
                   "<item><title>Also good</title><link>https://x.test/also</link><slash:comments>many</slash:comments></item>",
                   'xmlns:slash="http://purl.org/rss/1.0/modules/slash/"')
        entries = parse_feed(body)
        self.assertEqual([e.url for e in entries], ["https://x.test/good", "https://x.test/also"])
        self.assertIsNone(entries[1].comments)

    def test_documents_that_are_not_feeds_raise_value_error(self):
        for bad in ("<html><body><p>hello</p></body></html>", "just some text", "", b"\x00\x01\x02", "<a><b></a>",
                    "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'/>", '{"no": "items"}', "[1, 2]"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_feed(bad)

    def test_empty_feed_is_valid(self):
        self.assertEqual(parse_feed(rss("")), [])

    def test_entity_declarations_are_refused(self):
        bomb = '<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;">]><rss><channel/></rss>'
        with self.assertRaises(ValueError):
            parse_feed(bomb)

    def test_leading_whitespace_and_bom_are_tolerated(self):
        body = b"\xef\xbb\xbf  \n" + rss("<item><title>T</title><link>https://x.test/a</link></item>").encode()
        self.assertEqual(len(parse_feed(body)), 1)

    def test_summary_is_capped_at_500_characters(self):
        long_text = "word " * 400
        entries = parse_feed(rss(f"<item><title>T</title><link>https://x.test/a</link><description>{long_text}</description></item>"))
        self.assertLessEqual(len(entries[0].summary), 500)
        self.assertTrue(entries[0].summary.endswith("..."))

    def test_script_and_style_content_never_reaches_the_summary(self):
        desc = "&lt;p&gt;Visible&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;&lt;style&gt;p{}&lt;/style&gt;"
        entries = parse_feed(rss(f"<item><title>T</title><link>https://x.test/a</link><description>{desc}</description></item>"))
        self.assertEqual(entries[0].summary, "Visible")

    def test_content_encoded_is_the_fallback_summary(self):
        body = rss("<item><title>T</title><link>https://x.test/a</link>"
                   "<content:encoded><![CDATA[<p>Only the full text</p>]]></content:encoded></item>",
                   'xmlns:content="http://purl.org/rss/1.0/modules/content/"')
        self.assertEqual(parse_feed(body)[0].summary, "Only the full text")

    def test_legacy_userland_default_namespace(self):
        body = ('<rss version="2.0" xmlns="http://backend.userland.com/rss2"><channel><title>t</title>'
                "<item><title>Old school</title><link>https://x.test/old</link>"
                "<pubDate>Mon, 02 Mar 2026 07:00:00 CET</pubDate><description>Plain</description></item></channel></rss>")
        entry = parse_feed(body)[0]
        self.assertEqual((entry.title, entry.summary, entry.published_at), ("Old school", "Plain", "2026-03-02T06:00:00+00:00"))

    def test_feedburner_original_link_replaces_the_redirect(self):
        body = rss("<item><title>T</title><link>https://feedproxy.google.com/~r/x/1</link>"
                   "<feedburner:origLink>https://x.test/real</feedburner:origLink></item>",
                   'xmlns:feedburner="http://rssnamespace.org/feedburner/ext/1.0"')
        self.assertEqual(parse_feed(body)[0].url, "https://x.test/real")


class DateNormalisationTests(unittest.TestCase):
    def date_of(self, value: str):
        body = rss(f"<item><title>T</title><link>https://x.test/a</link><pubDate>{value}</pubDate></item>")
        return parse_feed(body)[0].published_at

    def test_rfc_822_with_offsets_and_named_zones(self):
        cases = {
            "Sun, 01 Mar 2026 09:30:00 +0100": "2026-03-01T08:30:00+00:00",
            "Tue, 03 Mar 2026 14:00:00 GMT": "2026-03-03T14:00:00+00:00",
            "Thu, 05 Mar 2026 08:00:00 -0500": "2026-03-05T13:00:00+00:00",
            "Thu, 05 Mar 2026 08:00:00 EST": "2026-03-05T13:00:00+00:00",
            "5 Mar 2026 08:00 +0530": "2026-03-05T02:30:00+00:00",
            "Thu, 05 Mar 2026 08:00:00 -0000": "2026-03-05T08:00:00+00:00",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.date_of(raw), expected)

    def test_iso_8601_variants(self):
        cases = {
            "2026-03-01T09:30:00Z": "2026-03-01T09:30:00+00:00",
            "2026-03-01T09:30:00+01:00": "2026-03-01T08:30:00+00:00",
            "2026-03-01T09:30:00.123456-08:00": "2026-03-01T17:30:00+00:00",
            "2026-03-01T09:30:00+0200": "2026-03-01T07:30:00+00:00",
            "2026-03-01 09:30:00": "2026-03-01T09:30:00+00:00",
            "2026-03-01": "2026-03-01T00:00:00+00:00",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.date_of(raw), expected)

    def test_garbage_and_implausible_dates_are_none(self):
        for raw in ("", "yesterday", "32 Feb 2026", "0001-01-01T00:00:00Z", "99999"):
            with self.subTest(raw=raw):
                self.assertIsNone(self.date_of(raw))


class DiscoverFeedsTests(unittest.TestCase):
    def test_finds_deduplicates_and_resolves_in_page_order(self):
        urls = discover_feeds(fixture("home_with_feeds.html").decode(), "https://acme.example/")
        self.assertEqual(urls, ["https://acme.example/blog/feed", "https://acme.example/atom.xml",
                                "https://acme.example/feed.json"])

    def test_comment_feeds_oembed_and_stylesheets_are_ignored(self):
        html = ('<link rel="alternate" type="application/rss+xml" title="Comments on X" href="/comments/feed">'
                '<link rel="alternate" type="application/json+oembed" href="/oembed">'
                '<link rel="stylesheet" type="application/rss+xml" href="/not-a-feed">'
                '<link rel="alternate" type="text/html" href="/de/">')
        self.assertEqual(discover_feeds(html, "https://x.test/"), [])

    def test_base_href_and_odd_markup(self):
        html = ('<base href="https://cdn.x.test/sub/"><LINK REL="Alternate" TYPE="application/atom+xml" HREF="a.xml">'
                "<link rel='alternate feed' type='application/rss+xml;charset=utf-8' href='//y.test/rss'>")
        self.assertEqual(discover_feeds(html, "https://x.test/"), ["https://cdn.x.test/sub/a.xml", "https://y.test/rss"])

    def test_garbage_input_gives_an_empty_list(self):
        self.assertEqual(discover_feeds("", "https://x.test/"), [])
        self.assertEqual(discover_feeds("<<<>>> not html at all", "https://x.test/"), [])


if __name__ == "__main__":
    unittest.main()
