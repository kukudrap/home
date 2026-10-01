import json
import unittest
from pathlib import Path

from dopamine_king.ingest.extract import (
    PageMeta,
    extract_page,
    guess_lang,
    parse_datetime,
    primary_lang,
    shorten,
    strip_html,
    to_iso,
)

FX = Path(__file__).parent / "fixtures" / "ingest"
URL = "https://www.acme.example/blog/post"


def fixture(name: str) -> str:
    return (FX / name).read_text(encoding="utf-8")


def page(head: str = "", body: str = "", lang: str = "") -> str:
    attr = f' lang="{lang}"' if lang else ""
    return f"<!doctype html><html{attr}><head>{head}</head><body>{body}</body></html>"


def ld(*nodes: dict) -> str:
    return f'<script type="application/ld+json">{json.dumps(list(nodes))}</script>'


class JsonLdAndOpenGraphTests(unittest.TestCase):
    def setUp(self):
        self.meta = extract_page(fixture("article_jsonld.html"), "https://www.acme.example/blog/spring-trail-shoes-2026/?utm_campaign=x")

    def test_graph_article_and_faq_page_types(self):
        for kind in ("Article", "BlogPosting", "FAQPage", "WebSite", "Organization"):
            self.assertIn(kind, self.meta.schema_types)
        self.assertEqual(len(self.meta.schema_types), len(set(self.meta.schema_types)))
        self.assertTrue(self.meta.has_faq)

    def test_open_graph_and_basic_fields(self):
        self.assertIsInstance(self.meta, PageMeta)
        self.assertEqual(self.meta.title, "Spring trail shoes: what changed in 2026")  # og:title beats twitter, JSON-LD, <title>
        self.assertEqual(self.meta.og_type, "article")
        self.assertEqual(self.meta.site_name, "Acme Outdoor")
        self.assertEqual(self.meta.lang, "en")
        self.assertEqual(self.meta.description, "Lighter foams, wider lasts and a few surprises from testing 14 pairs.")

    def test_canonical_url_drops_tracking_and_www(self):
        self.assertEqual(self.meta.canonical_url, "https://acme.example/blog/spring-trail-shoes-2026")
        self.assertTrue(self.meta.url.endswith("?utm_campaign=x"))

    def test_dates_are_utc_iso(self):
        self.assertEqual(self.meta.published_at, "2026-03-01T08:30:00+00:00")
        self.assertEqual(self.meta.modified_at, "2026-03-04T09:00:00+00:00")

    def test_keywords_merge_meta_tags_and_json_ld_without_duplicates(self):
        self.assertEqual(self.meta.keywords, ["trail", "shoes", "running", "trail running", "foam"])

    def test_structure_counts_ignore_sidebars_and_navigation(self):
        self.assertEqual((self.meta.h1_count, self.meta.h2_count, self.meta.h3_count), (1, 2, 1))
        self.assertEqual(self.meta.list_items, 3)
        self.assertEqual(self.meta.image_count, 2)  # logo in the site header and the 1x1 pixel do not count
        self.assertTrue(self.meta.has_video)  # youtube embed
        self.assertTrue(self.meta.has_byline)
        self.assertEqual((self.meta.links_internal, self.meta.links_external), (1, 1))

    def test_word_count_counts_visible_body_text_only(self):
        self.assertEqual(self.meta.word_count, 57)

    def test_no_author_name_anywhere_in_the_result(self):
        self.assertNotIn("Jane Doe", json.dumps(self.meta.to_dict()))

    def test_json_ld_variants_are_tolerated(self):
        broken = '<script type="application/ld+json">{ this is not json }</script>'
        top_list = ld({"@type": "NewsArticle", "headline": "Listed headline"}, {"@type": "FAQPage"})
        meta = extract_page(page(broken + top_list), URL)
        self.assertEqual(meta.title, "Listed headline")
        self.assertTrue(meta.has_faq)
        nested = '<script type="application/ld+json">{"@graph": [{"@type": "Article", "headline": "Nested"}]}</script>'
        self.assertEqual(extract_page(page(nested), URL).title, "Nested")
        raw_newline = '<script type="application/ld+json">{"@type": "Article", "headline": "Line\nbreak"}</script>'
        self.assertEqual(extract_page(page(raw_newline), URL).title, "Line break")


class TitleAndDateTests(unittest.TestCase):
    def test_title_preference_order(self):
        og = '<meta property="og:title" content="OG">'
        tw = '<meta name="twitter:title" content="TW">'
        headline = ld({"@type": "Article", "headline": "LD"})
        title = "<title>TITLE</title>"
        h1 = "<h1>H1</h1>"
        self.assertEqual(extract_page(page(og + tw + headline + title, h1), URL).title, "OG")
        self.assertEqual(extract_page(page(tw + headline + title, h1), URL).title, "TW")
        self.assertEqual(extract_page(page(headline + title, h1), URL).title, "LD")
        self.assertEqual(extract_page(page(title, h1), URL).title, "TITLE")
        self.assertEqual(extract_page(page("", h1), URL).title, "H1")
        self.assertEqual(extract_page(page("", "<p>no title at all</p>"), URL).title, "")

    def test_site_name_suffix_is_trimmed_from_the_title(self):
        head = '<title>Great post | Acme</title><meta property="og:site_name" content="Acme">'
        self.assertEqual(extract_page(page(head), URL).title, "Great post")
        dash = "<title>Great post " + chr(0x2013) + " Acme</title>" + '<meta property="og:site_name" content="Acme">'
        self.assertEqual(extract_page(page(dash), URL).title, "Great post")

    def test_publication_date_sources_in_order(self):
        og = '<meta property="article:published_time" content="2026-01-01T10:00:00Z">'
        ldd = ld({"@type": "Article", "datePublished": "2026-02-02"})
        time = '<time datetime="2026-03-03T12:00:00+01:00">March</time>'
        self.assertEqual(extract_page(page(og + ldd, time), URL).published_at, "2026-01-01T10:00:00+00:00")
        self.assertEqual(extract_page(page(ldd, time), URL).published_at, "2026-02-02T00:00:00+00:00")
        self.assertEqual(extract_page(page("", time), URL).published_at, "2026-03-03T11:00:00+00:00")
        self.assertIsNone(extract_page(page("", "<p>no date</p>"), URL).published_at)

    def test_time_elements_are_classified_by_itemprop_and_class(self):
        body = ('<time class="updated" datetime="2026-04-10">upd</time>'
                '<time itemprop="datePublished" datetime="2026-04-01">pub</time>')
        meta = extract_page(page("", body), URL)
        self.assertEqual(meta.published_at, "2026-04-01T00:00:00+00:00")
        self.assertEqual(meta.modified_at, "2026-04-10T00:00:00+00:00")

    def test_unparseable_dates_are_none(self):
        meta = extract_page(page('<meta property="article:published_time" content="someday">'), URL)
        self.assertIsNone(meta.published_at)


class CzechAndMalformedTests(unittest.TestCase):
    def test_czech_page_keeps_diacritics(self):
        meta = extract_page(fixture("page_cs.html"), "https://www.sportovni-svet.example.cz/clanky/boty")
        self.assertEqual(meta.lang, "cs")
        self.assertEqual(meta.title, "Jak vybrat běžecké boty")  # the " | Sportovní svět" suffix of <title> is trimmed
        self.assertEqual(meta.site_name, "Sportovní svět")
        self.assertTrue(meta.first_paragraph.startswith("Výběr správných běžeckých bot"))
        self.assertEqual(meta.published_at, "2026-02-14T06:15:00+00:00")
        self.assertEqual((meta.h2_count, meta.list_items), (1, 3))
        self.assertEqual(meta.word_count, 47)
        self.assertEqual(guess_lang(f"{meta.title} {meta.description}"), "cs")

    def test_czech_faq_heading_is_detected(self):
        self.assertTrue(extract_page(page("", "<h2>Časté dotazy</h2><p>text</p>"), URL).has_faq)
        self.assertTrue(extract_page(page("", "<h3>FAQ</h3>"), URL).has_faq)
        self.assertFalse(extract_page(page("", "<h2>Faqir stories</h2>"), URL).has_faq)

    def test_malformed_html_does_not_raise_and_yields_sensible_numbers(self):
        meta = extract_page(fixture("malformed.html"), "https://messy.example/page")
        self.assertEqual(meta.title, "Messy but readable")
        self.assertTrue(meta.first_paragraph.startswith("The first paragraph is long enough"))
        self.assertEqual((meta.h1_count, meta.h2_count), (0, 1))
        self.assertEqual(meta.list_items, 3)
        self.assertEqual(meta.image_count, 1)
        self.assertEqual(meta.links_internal, 1)
        self.assertNotIn("document", meta.first_paragraph)

    def test_garbage_input_never_raises(self):
        for junk in ("", "<<<>>>", "<div" * 50, "</p></div></nav>" * 20, "<html><body><p>" + "<b>" * 5000, "\x00\x01 binary"):
            with self.subTest(junk=junk[:20]):
                self.assertIsInstance(extract_page(junk, URL), PageMeta)
        self.assertEqual(extract_page("", URL).word_count, 0)

    def test_entities_in_attributes_and_text_are_decoded(self):
        meta = extract_page(page('<meta property="og:title" content="Tom &amp; Jerry &quot;live&quot;">', "<p>a&nbsp;b &amp; c</p>"), URL)
        self.assertEqual(meta.title, 'Tom & Jerry "live"')
        self.assertEqual(meta.word_count, 3)  # a, b, c: the lone ampersand is not a word


class TextFeatureTests(unittest.TestCase):
    def test_word_count_excludes_script_style_nav_header_footer_aside_form(self):
        body = ("<header>head words here</header><nav>nav words here</nav><script>var a = 'script words';</script>"
                "<style>.x { content: 'style words' }</style><noscript>noscript words</noscript>"
                "<main><p>one two three</p></main><aside>aside words</aside><form><label>form words</label></form>"
                "<footer>footer words here</footer>")
        self.assertEqual(extract_page(page("<title>ignored title words</title>", body), URL).word_count, 3)

    def test_inline_markup_does_not_split_words_but_blocks_do(self):
        self.assertEqual(extract_page(page("", "<p>super<b>market</b> sale</p>"), URL).word_count, 2)
        self.assertEqual(extract_page(page("", "<ul><li>one</li><li>two</li></ul><p>three<br>four</p>"), URL).word_count, 4)

    def test_hyphenated_and_apostrophe_words_count_once(self):
        self.assertEqual(extract_page(page("", "<p>e-mail don't 3.5</p>"), URL).word_count, 3)

    def test_heading_and_list_counts(self):
        body = ("<h1>a</h1><h2>b</h2><h2>c</h2><h3>d</h3><h3>e</h3><h3>f</h3>"
                "<ul><li>1</li><li>2</li></ul><ol><li>3</li></ol><nav><h2>nav</h2><ul><li>x</li></ul></nav>"
                "<footer><h3>foot</h3></footer>")
        meta = extract_page(page("", body), URL)
        self.assertEqual((meta.h1_count, meta.h2_count, meta.h3_count, meta.list_items), (1, 2, 3, 3))

    def test_a_missing_head_end_tag_does_not_hide_the_body(self):
        html = ("<html><head><title>T</title><meta property='og:site_name' content='S'>"
                "<body><h1>Title</h1><p>one two three four five</p></body></html>")
        meta = extract_page(html, URL)
        self.assertEqual((meta.title, meta.site_name, meta.h1_count, meta.word_count), ("T", "S", 1, 6))

    def test_a_page_wide_form_is_content_but_a_later_form_is_chrome(self):
        aspnet = ("<html><body><form method='post' id='form1'><div><h1>Page</h1>"
                  "<p>alpha beta gamma delta</p></div></form></body></html>")
        meta = extract_page(aspnet, URL)
        self.assertEqual((meta.h1_count, meta.word_count, meta.first_paragraph), (1, 5, "alpha beta gamma delta"))
        late = ("<html><body><p>real content here with words</p>"
                "<form><label>Email</label><input><button>Subscribe now</button></form></body></html>")
        self.assertEqual(extract_page(late, URL).word_count, 5)

    def test_first_paragraph_skips_short_lines_and_is_capped(self):
        long_p = "word " * 200
        meta = extract_page(page("", f"<p>By someone</p><p>{long_p}</p>"), URL)
        self.assertLessEqual(len(meta.first_paragraph), 300)
        self.assertTrue(meta.first_paragraph.endswith("..."))
        self.assertFalse(meta.first_paragraph.startswith("By someone"))
        self.assertEqual(extract_page(page("", "<p>Short only</p>"), URL).first_paragraph, "Short only")

    def test_byline_and_dateline_paragraphs_never_become_the_lead(self):
        body = ('<article><p class="meta">Posted by Jane Doe on March 3, 2026 in Product Updates</p>'
                "<p>By Jane Doe, Senior Editor | 5 min read</p>"
                '<div class="byline"><p>Jane Doe is our editor and she wrote this long text about many things.</p></div>'
                "<p>Published: March 3, 2026, updated twice since then by the editorial team</p>"
                "<p>The real lead paragraph starts here and is long enough to be picked up as an excerpt.</p></article>")
        meta = extract_page(page("", body), URL)
        self.assertEqual(meta.first_paragraph, "The real lead paragraph starts here and is long enough to be picked up as an excerpt.")
        self.assertNotIn("Jane Doe", json.dumps(meta.to_dict()))
        self.assertTrue(meta.has_byline)

    def test_leads_that_merely_start_like_a_byline_are_kept(self):
        for lead in ("By 2030 the market for electric bikes is expected to triple in size.",
                     "By the way, this is the first long paragraph of the article, nothing more.",
                     "Published in 1998, the book remains popular among runners and coaches alike.",
                     "Od roku 2020 se situace na trhu s běžeckou obuví výrazně změnila a zlevnila."):
            with self.subTest(lead=lead):
                self.assertEqual(extract_page(page("", f"<p>{lead}</p>"), URL).first_paragraph, lead)
        self.assertEqual(extract_page(page("", "<p>By Jane Doe</p>"), URL).first_paragraph, "")
        self.assertEqual(extract_page(page("", "<p>Autor: Jan Novák</p>"), URL).first_paragraph, "")

    def test_paragraphs_inside_navigation_are_ignored(self):
        meta = extract_page(page("", "<nav><p>menu paragraph that is quite long indeed, longer than forty chars</p></nav>"
                                     "<p>Real content paragraph that is certainly long enough to qualify.</p>"), URL)
        self.assertTrue(meta.first_paragraph.startswith("Real content"))

    def test_images_header_logo_vs_article_header(self):
        body = ('<header><img src="logo.png"></header><article><header><img src="hero.jpg"></header>'
                '<img src="a.jpg" width="640"><img src="pixel.gif" width="1" height="1"></article>'
                '<footer><img src="f.png"></footer><nav><img src="n.png"></nav>')
        self.assertEqual(extract_page(page("", body), URL).image_count, 2)

    def test_video_detection_variants(self):
        cases = {
            "video tag": ("", "<video src='a.mp4'></video>"),
            "youtube iframe": ("", "<iframe src='https://www.youtube-nocookie.com/embed/x'></iframe>"),
            "vimeo iframe": ("", "<iframe data-src='https://player.vimeo.com/video/1'></iframe>"),
            "og:video": ('<meta property="og:video" content="https://x.test/v.mp4">', ""),
            "og:type video": ('<meta property="og:type" content="video.movie">', ""),
            "VideoObject": (ld({"@type": "VideoObject", "name": "v"}), ""),
        }
        for label, (head, body) in cases.items():
            with self.subTest(label):
                self.assertTrue(extract_page(page(head, body), URL).has_video)
        self.assertFalse(extract_page(page("", "<iframe src='https://maps.example/embed'></iframe>"), URL).has_video)

    def test_microdata_types_and_faq(self):
        body = '<div itemscope itemtype="https://schema.org/FAQPage"><div itemtype="http://schema.org/Article/"></div></div>'
        meta = extract_page(page("", body), URL)
        self.assertTrue(meta.has_faq)
        self.assertEqual(meta.schema_types, ["FAQPage", "Article"])

    def test_link_classification(self):
        body = ('<p><a href="/a">1</a><a href="/a#frag">dup</a><a href="https://blog.acme.example/b">sub</a>'
                '<a href="https://www.acme.example/c">www</a><a href="https://other.example/d">ext</a>'
                '<a href="mailto:x@y.z">m</a><a href="javascript:void(0)">j</a><a href="#top">t</a><a href="tel:123">tel</a></p>')
        meta = extract_page(page("", body), URL)
        self.assertEqual((meta.links_internal, meta.links_external), (3, 1))

    def test_base_href_changes_link_resolution(self):
        meta = extract_page(page('<base href="https://other.example/">', '<p><a href="x">x</a></p>'), URL)
        self.assertEqual((meta.links_internal, meta.links_external), (0, 1))


class CanonicalAndPolicyTests(unittest.TestCase):
    def canonical(self, head: str, url: str = URL) -> str:
        return extract_page(page(head), url).canonical_url

    def test_canonical_resolution_rules(self):
        self.assertEqual(self.canonical('<link rel="canonical" href="/blog/real-post/">'), "https://acme.example/blog/real-post")
        self.assertEqual(self.canonical('<meta property="og:url" content="https://acme.example/blog/og-post">'),
                         "https://acme.example/blog/og-post")
        self.assertEqual(self.canonical(""), "https://acme.example/blog/post")

    def test_untrustworthy_canonicals_are_ignored(self):
        self.assertEqual(self.canonical('<link rel="canonical" href="https://medium.example/p/1">'), "https://acme.example/blog/post")
        self.assertEqual(self.canonical('<link rel="canonical" href="https://www.acme.example/">'), "https://acme.example/blog/post")
        self.assertEqual(self.canonical('<link rel="canonical" href="javascript:void(0)">'), "https://acme.example/blog/post")

    def test_tdm_reservation_meta(self):
        self.assertTrue(extract_page(fixture("tdm_meta.html"), "https://reserved.example/p").tdm_reservation)
        self.assertFalse(extract_page(page('<meta name="tdm-reservation" content="0">'), URL).tdm_reservation)
        self.assertFalse(extract_page(page(), URL).tdm_reservation)

    def test_byline_is_only_a_boolean(self):
        cases = {
            "rel=author": ("", '<a rel="author" href="/a">Someone</a>', True),
            "byline class": ("", '<span class="post byline">Someone</span>', True),
            "meta author": ('<meta name="author" content="Someone">', "", True),
            "json-ld string author": (ld({"@type": "Article", "author": "Someone"}), "", True),
            "json-ld person author": (ld({"@type": "Article", "author": [{"@type": "Person", "name": "Someone"}]}), "", True),
            "organisation author": (ld({"@type": "Article", "author": {"@type": "Organization", "name": "Acme"}}), "", False),
            "meta author is the brand": ('<meta name="author" content="Acme"><meta property="og:site_name" content="Acme">', "", False),
            "nothing": ("", "<p>plain</p>", False),
        }
        for label, (head, body, expected) in cases.items():
            with self.subTest(label):
                meta = extract_page(page(head, body), URL)
                self.assertIs(meta.has_byline, expected)
                self.assertNotIn("Someone", json.dumps(meta.to_dict()))


class HelperTests(unittest.TestCase):
    def test_strip_html(self):
        self.assertEqual(strip_html("<p>Hello <b>world</b></p><script>x()</script><style>p{}</style> &amp; more&nbsp;text"),
                         "Hello world & more text")
        self.assertEqual(strip_html("a<br>b</p><p>c"), "a b c")
        self.assertEqual(strip_html("&lt;p&gt;double &amp;amp; escaped&lt;/p&gt;"), "double & escaped")
        self.assertEqual(strip_html(""), "")
        self.assertEqual(strip_html("  plain   text \n"), "plain text")

    def test_shorten_never_exceeds_the_limit(self):
        for limit in (10, 50, 300, 500):
            for text in ("word " * 400, "x" * 1000, "short", "Příliš žluťoučký kůň " * 40):
                with self.subTest(limit=limit, size=len(text)):
                    self.assertLessEqual(len(shorten(text, limit)), limit)
        self.assertEqual(shorten("short text", 300), "short text")
        self.assertEqual(shorten("  spaced \n out  ", 300), "spaced out")
        self.assertTrue(shorten("alpha beta gamma delta epsilon", 20).endswith("..."))

    def test_guess_lang(self):
        self.assertEqual(guess_lang("Příliš žluťoučký kůň úpěl ďábelské ódy"), "cs")
        self.assertEqual(guess_lang("The quick brown fox"), "en")
        self.assertEqual(guess_lang("Review of the Škoda Octavia and its engines"), "en")  # one diacritic is not enough
        self.assertEqual(guess_lang(""), "en")

    def test_primary_lang(self):
        self.assertEqual(primary_lang("cs_CZ"), "cs")
        self.assertEqual(primary_lang("en-US"), "en")
        self.assertEqual(primary_lang(" DE "), "de")
        self.assertIsNone(primary_lang(""))
        self.assertIsNone(primary_lang(None))

    def test_parse_datetime_and_to_iso(self):
        self.assertEqual(to_iso("2026-03-01T09:30:00+01:00"), "2026-03-01T08:30:00+00:00")
        self.assertEqual(to_iso("Mon, 02 Mar 2026 09:30:00 +0100"), "2026-03-02T08:30:00+00:00")
        self.assertEqual(to_iso("20260301T0930Z"), "2026-03-01T09:30:00+00:00")
        self.assertEqual(to_iso("Mon, 2 Mar 2026 07:00:00 CET"), "2026-03-02T06:00:00+00:00")
        self.assertEqual(to_iso("Thu, 2 Jul 2026 07:00:00 CEST"), "2026-07-02T05:00:00+00:00")
        self.assertEqual(to_iso("March 1, 2026"), "2026-03-01T00:00:00+00:00")
        self.assertEqual(to_iso("1st Sept 2026 10:15"), "2026-09-01T10:15:00+00:00")
        self.assertIsNone(to_iso("Foo 1, 2026"))
        self.assertIsNone(to_iso("31 Feb 2026"))
        self.assertIsNone(to_iso(None))
        self.assertIsNone(to_iso("1850-01-01"))
        self.assertIsNone(to_iso("2026-13-45"))
        self.assertEqual(parse_datetime("2026-03-01").tzinfo.utcoffset(None).total_seconds(), 0)


if __name__ == "__main__":
    unittest.main()


class StripBylineLeadTests(unittest.TestCase):
    def test_removes_byline_and_dateline_leads_in_english_and_czech(self):
        from dopamine_king.ingest.extract import strip_byline_lead
        self.assertEqual(strip_byline_lead("By Jane Doe. Shoes that last."), "Shoes that last.")
        self.assertEqual(strip_byline_lead("Napsal Jan Novák. Boty, které vydrží."), "Boty, které vydrží.")
        self.assertEqual(strip_byline_lead("Published: 12 March 2026\nShoes that last."), "Shoes that last.")
        self.assertEqual(strip_byline_lead("By Jane Doe"), "")

    def test_leaves_ordinary_leads_alone(self):
        from dopamine_king.ingest.extract import strip_byline_lead
        for text in ("Shoes that last.", "Why stability matters by the numbers.", "Byl to dobrý rok.", ""):
            self.assertEqual(strip_byline_lead(text), text)
