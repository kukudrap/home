"""Page metadata and derived numeric features from HTML, plus small text and date helpers.

Only features are derived here (counts, flags, dates). The full text is never kept: ``PageMeta`` holds
a first paragraph of at most 300 characters and a boolean ``has_byline`` instead of author names.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..models import Serializable, canonical_url

_BLOCK_TAGS = frozenset({
    "p", "div", "br", "li", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td",
    "th", "table", "section", "article", "blockquote", "figure", "figcaption", "pre", "hr", "main",
    "details", "summary", "header", "footer", "aside", "nav", "form",
})
_SKIP_CONTENT = frozenset({"script", "style", "template", "noscript"})
_VOID_TAGS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr",
})
_CZECH_CHARS = set("řěščžůŘĚŠČŽŮ")
_WORD = re.compile(r"[^\W_]+(?:['" + chr(0x2019) + r"\-.][^\W_]+)*")
_TAG_LIKE = re.compile(r"</?[a-zA-Z][^>]*>")
_NAMED_ZONES = {"CET": "+0100", "CEST": "+0200", "EET": "+0200", "EEST": "+0300", "BST": "+0100", "WET": "+0000",
                "WEST": "+0100"}
_MONTHS = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_WORDY_DATE = re.compile(
    r"^(?:[A-Za-z]+,?\s+)?(?:(?P<d1>\d{1,2})(?:st|nd|rd|th)?\s+(?P<m1>[A-Za-z]{3,9})\.?,?|"
    r"(?P<m2>[A-Za-z]{3,9})\.?\s+(?P<d2>\d{1,2})(?:st|nd|rd|th)?,?)\s+(?P<y>\d{4})"
    r"(?:[ ,T]+(?P<h>\d{1,2}):(?P<mi>\d{2}))?\s*$"
)
_ISO_DATE = re.compile(
    r"^(\d{4})-?(\d{2})-?(\d{2})"
    r"(?:[T ](\d{2}):?(\d{2})(?::?(\d{2})(?:[.,]\d+)?)?)?"
    r"\s*(Z|UTC|GMT|[+-]\d{2}(?::?\d{2})?)?$",
    re.I,
)


# -- text helpers ---------------------------------------------------------------------
class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_CONTENT:
            self._skip += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_CONTENT:
            self._skip = max(0, self._skip - 1)
        elif tag in _BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def strip_html(text: str) -> str:
    """Plain text of an HTML fragment with whitespace collapsed. Never raises."""
    if not text:
        return ""
    for _ in range(2):  # a second pass undoes double-escaped markup
        if "<" not in text and "&" not in text:
            break
        parser = _TextExtractor()
        try:
            parser.feed(text)
            parser.close()
        except Exception:
            pass
        text = "".join(parser.parts)
        if not _TAG_LIKE.search(text):
            break
    return " ".join(text.split())


def shorten(text: str, limit: int) -> str:
    """Collapse whitespace and cut at a word boundary so the result is never longer than ``limit``."""
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[: max(limit - 3, 0)].rstrip()
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,;:.-") + "..."


def count_words(text: str) -> int:
    return len(_WORD.findall(text))


def guess_lang(text: str) -> str:
    """Cheap language guess: Czech when diacritics typical for it are frequent enough, else English."""
    letters = sum(1 for ch in text if ch.isalpha())
    czech = sum(1 for ch in text if ch in _CZECH_CHARS)
    return "cs" if czech >= 2 and czech / max(letters, 1) >= 0.015 else "en"


def primary_lang(value: str | None) -> str | None:
    """``"cs_CZ"`` or ``"en-US"`` to ``"cs"`` or ``"en"``; None when empty."""
    match = re.match(r"[A-Za-z]{2,3}", (value or "").strip())
    return match.group(0).lower() if match else None


# -- dates ----------------------------------------------------------------------------
def parse_datetime(value: Any) -> datetime | None:
    """Parse ISO 8601 or RFC 822 dates to an aware UTC datetime; naive values are taken as UTC."""
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    parsed: datetime | None = None
    match = _ISO_DATE.match(text)
    try:
        if match:
            year, month, day, hour, minute, second, zone = match.groups()
            parsed = datetime(int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0))
            if zone and zone.upper() not in ("Z", "UTC", "GMT"):
                sign = -1 if zone[0] == "-" else 1
                digits = zone[1:].replace(":", "")
                offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:4] or 0))
                parsed = parsed.replace(tzinfo=timezone(sign * offset))
        elif wordy := _WORDY_DATE.match(text):
            month = _MONTHS.get((wordy["m1"] or wordy["m2"])[:3].lower())
            if month is None:
                return None
            day = int(wordy["d1"] or wordy["d2"])
            parsed = datetime(int(wordy["y"]), month, day, int(wordy["h"] or 0), int(wordy["mi"] or 0))
        else:
            parsed = parsedate_to_datetime(re.sub(
                r"\b(CEST|CET|EEST|EET|BST|WEST|WET)\s*$", lambda m: _NAMED_ZONES[m.group(1)], text))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        parsed = parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return parsed if 1990 <= parsed.year <= 2100 else None


def to_iso(value: Any) -> str | None:
    """Normalise a date string to ``2026-03-01T09:30:00+00:00`` (UTC), or None when unparseable."""
    parsed = parse_datetime(value)
    return parsed.isoformat(timespec="seconds") if parsed else None


# -- result model ---------------------------------------------------------------------
@dataclass
class PageMeta(Serializable):
    url: str
    canonical_url: str
    title: str = ""
    description: str = ""
    lang: str | None = None
    published_at: str | None = None
    modified_at: str | None = None
    site_name: str | None = None
    has_byline: bool = False
    schema_types: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    h1_count: int = 0
    h2_count: int = 0
    h3_count: int = 0
    list_items: int = 0
    image_count: int = 0
    has_video: bool = False
    has_faq: bool = False
    word_count: int = 0
    first_paragraph: str = ""
    links_internal: int = 0
    links_external: int = 0
    tdm_reservation: bool = False
    og_type: str | None = None


# -- JSON-LD --------------------------------------------------------------------------
_ARTICLE_TYPES = frozenset({
    "Article", "NewsArticle", "BlogPosting", "TechArticle", "ScholarlyArticle", "Report",
    "SocialMediaPosting", "LiveBlogPosting", "OpinionNewsArticle", "AnalysisNewsArticle", "Review",
})


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [] if value is None else [value]


def _types_of(node: dict[str, Any]) -> list[str]:
    return [t.rsplit("/", 1)[-1] for t in _as_list(node.get("@type")) if isinstance(t, str)]


def jsonld_nodes(blocks: list[str]) -> list[dict[str, Any]]:
    """Top-level JSON-LD nodes, with ``@graph`` members and list items flattened in."""
    nodes: list[dict[str, Any]] = []

    def visit(obj: Any, depth: int = 0) -> None:
        if isinstance(obj, list):
            for item in obj:
                visit(item, depth)
        elif isinstance(obj, dict):
            graph = obj.get("@graph")
            if graph is not None and depth < 3:
                visit(graph, depth + 1)
            if "@type" in obj or graph is None:
                nodes.append(obj)

    for raw in blocks:
        try:
            visit(json.loads(raw.strip(), strict=False))
        except ValueError:
            continue
    return nodes


def _text_value(value: Any) -> str:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, dict):
        return _text_value(value.get("name") or value.get("@value") or "")
    if isinstance(value, list):
        return next((t for t in (_text_value(v) for v in value) if t), "")
    return ""


def _author_present(node: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> bool:
    """True when the node names a human author. Organisation authors do not count as a byline."""
    for author in _as_list(node.get("author") or node.get("creator")):
        if isinstance(author, dict) and set(author) <= {"@id"} and author.get("@id") in by_id:
            author = by_id[author["@id"]]
        if isinstance(author, dict):
            if "Organization" in _types_of(author) and "Person" not in _types_of(author):
                continue
            if _text_value(author) or "@id" in author:
                return True
        elif isinstance(author, str) and author.strip():
            return True
    return False


# -- HTML parser ----------------------------------------------------------------------
_CHROME = frozenset({"nav", "header", "footer", "aside", "form"})   # not part of the readable body
_STRUCT_SKIP = frozenset({"nav", "footer", "aside", "form"})        # excluded from structure counts
_RAW = frozenset({"script", "style", "template", "noscript", "head", "svg"})
_HEAD_TAGS = frozenset({"html", "head", "title", "meta", "link", "script", "style", "base", "noscript", "template"})
_CLOSES_P = frozenset({
    "p", "div", "ul", "ol", "dl", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article",
    "blockquote", "pre", "hr", "form", "header", "footer", "nav", "aside", "main", "figure", "details",
})
_BYLINE_CLASSES = frozenset({
    "byline", "author", "author-name", "post-author", "entry-author", "article-author", "posted-by", "meta-author",
})
_META_LINE_CLASSES = _BYLINE_CLASSES | frozenset({
    "meta", "post-meta", "entry-meta", "article-meta", "dateline", "post-date", "entry-date", "posted-on", "published",
})
# Lead paragraph candidates that are really bylines or datelines are skipped, so names never reach the excerpt.
_BYLINE_TEXT = re.compile(
    r"^\W*(?i:(?:(?:posted|written|words|text|photos?)\s+)?by|napsal|napsala|autor|autorem|od)\s+[A-ZÀ-Ž]"
    r"|^\W*(?i:published|updated|posted|last updated|publikováno|zveřejněno|aktualizováno|author|autor|autorem)"
    r"\b\s*[:\d.-]"
)


def strip_byline_lead(text: str) -> str:
    """Drop a leading byline or dateline sentence ("By Jane Doe. ...") so author names stay out of excerpts."""
    if not _BYLINE_TEXT.search(text):
        return text
    parts = re.split(r"(?<=[.!?])\s+|\n", text.strip(), maxsplit=1)
    return parts[1] if len(parts) > 1 else ""

_VIDEO_HOSTS = ("youtube.com/embed", "youtube-nocookie.com", "player.vimeo.com", "wistia.", "dailymotion.com/embed",
                "fast.wistia", "loom.com/embed", "vidyard.com", "brightcove")
_FAQ_HEADING = re.compile(r"\bfaqs?\b|frequently asked|časté dotazy|často kladené|nejčastější dotazy", re.I)
# en dash, em dash, middle dot and bullet are built from code points; the hyphen goes last so it stays literal
_TITLE_SEPARATORS = "|:" + chr(0x2013) + chr(0x2014) + chr(0xB7) + chr(0x2022) + "-"
_PUBLISHED_CLASS = re.compile(r"publish|posted|entry-date|post-date|pubdate|dateline", re.I)
_MODIFIED_CLASS = re.compile(r"updated|modified|edited", re.I)


class _PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.stack: list[str] = []
        self.counts: dict[str, int] = {}
        self.meta: dict[str, list[str]] = {}
        self.html_lang: str | None = None
        self.title = ""
        self.canonical_href: str | None = None
        self.jsonld: list[str] = []
        self.h1 = self.h2 = self.h3 = 0
        self.first_h1 = ""
        self.heading_texts: list[str] = []
        self.list_items = 0
        self.images = 0
        self.has_video = False
        self.itemtypes: list[str] = []
        self.byline_hint = False
        self.times: list[dict[str, str]] = []
        self.paragraphs: list[str] = []
        self.text_chunks: list[str] = []
        self._meta_open: list[bool] = []  # parallel to the open elements: does one mark a byline or date line?
        self.links: set[str] = set()
        self._title_buf: list[str] | None = None
        self._jsonld_buf: list[str] | None = None
        self._heading: tuple[str, list[str]] | None = None
        self._para: list[str] | None = None
        self._para_is_meta = False
        self._seen_text = False

    # -- helpers --------------------------------------------------------------------
    def _in(self, names: frozenset[str]) -> bool:
        return any(self.counts.get(name, 0) for name in names)

    def _pop_to(self, tag: str) -> None:
        while self.stack:
            top = self.stack.pop()
            self._meta_open.pop()
            self.counts[top] -= 1
            self._closed(top)
            if top == tag:
                return

    def finish(self) -> None:
        while self.stack:
            top = self.stack.pop()
            self._meta_open.pop()
            self.counts[top] -= 1
            self._closed(top)

    def _closed(self, tag: str) -> None:
        if tag == "title" and self._title_buf is not None:
            if not self.title:
                self.title = " ".join("".join(self._title_buf).split())
            self._title_buf = None
        elif tag == "script" and self._jsonld_buf is not None:
            self.jsonld.append("".join(self._jsonld_buf))
            self._jsonld_buf = None
        elif tag == "p" and self._para is not None:
            text = " ".join("".join(self._para).split())
            if text and not self._para_is_meta and not _BYLINE_TEXT.search(text):
                self.paragraphs.append(text)
            self._para = None
        elif self._heading and self._heading[0] == tag:
            text = " ".join("".join(self._heading[1]).split())
            if tag == "h1" and text and not self.first_h1:
                self.first_h1 = text
            if tag in ("h2", "h3") and text:
                self.heading_texts.append(text)
            self._heading = None

    # -- events ---------------------------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in _CLOSES_P and self.counts.get("p"):
            self._pop_to("p")
        if self.counts.get("head") and tag not in _HEAD_TAGS:  # a missing </head> ends at the first body element
            self._pop_to("head")
        structure_ok = not self._in(_STRUCT_SKIP | _RAW)
        text_ok = not self._in(_CHROME | _RAW)
        classes = set(a.get("class", "").lower().split())

        if tag == "html":
            self.html_lang = a.get("lang") or a.get("xml:lang") or None
        elif tag == "base" and a.get("href"):
            self.base_url = urljoin(self.base_url, a["href"])
        elif tag == "meta":
            content = " ".join(a.get("content", "").split())
            for key in (a.get("property"), a.get("name"), a.get("itemprop"), a.get("http-equiv")):
                if key and "content" in a:
                    self.meta.setdefault(key.strip().lower(), []).append(content)
        elif tag == "link":
            if "canonical" in a.get("rel", "").lower().split() and a.get("href") and not self.canonical_href:
                self.canonical_href = a["href"]
        elif tag == "title" and not self.counts.get("svg"):
            self._title_buf = []
        elif tag == "script" and "ld+json" in a.get("type", "").lower():
            self._jsonld_buf = []
        elif tag in ("h1", "h2", "h3") and structure_ok:
            setattr(self, tag, getattr(self, tag) + 1)
            self._heading = (tag, [])
        elif tag == "li" and text_ok:
            self.list_items += 1
        elif tag == "img" and structure_ok:
            tiny = any(a.get(dim, "").strip() in ("0", "1", "2") for dim in ("width", "height"))
            logo = bool(self.counts.get("header")) and not self.counts.get("article")
            if not tiny and not logo:
                self.images += 1
        elif tag in ("video", "lite-youtube", "lite-vimeo", "youtube-video") and structure_ok:
            self.has_video = True
        elif tag in ("iframe", "embed", "source") and structure_ok:
            src = (a.get("src") or a.get("data-src") or "").lower()
            if any(host in src for host in _VIDEO_HOSTS) or a.get("type", "").lower().startswith("video/"):
                self.has_video = True
        elif tag == "a" and a.get("href"):
            if "author" in a.get("rel", "").lower().split() and not self._in(_STRUCT_SKIP):
                self.byline_hint = True
            if text_ok:
                self._add_link(a["href"])
        elif tag == "time" and a.get("datetime") and not self._in(_STRUCT_SKIP):
            self.times.append({"datetime": a["datetime"], "itemprop": a.get("itemprop", "").lower(),
                               "class": a.get("class", "")})
        elif tag == "p" and text_ok:
            self._para = []
            self._para_is_meta = any(self._meta_open) or bool(classes & _META_LINE_CLASSES)

        if a.get("itemprop", "").lower() == "author" and not self.counts.get("nav"):
            self.byline_hint = True
        if classes & _BYLINE_CLASSES and not self.counts.get("nav"):
            self.byline_hint = True
        if a.get("itemtype"):
            self.itemtypes.append(a["itemtype"].rstrip("/").rsplit("/", 1)[-1])
        if tag in _BLOCK_TAGS:
            self.text_chunks.append("\n")
        if tag not in _VOID_TAGS:
            # a form opened before any text wraps the whole page (ASP.NET style) and is not page chrome
            name = "form-wrap" if tag == "form" and not self._seen_text else tag
            self.stack.append(name)
            self._meta_open.append(bool(classes & _META_LINE_CLASSES) or a.get("itemprop", "").lower() == "author")
            self.counts[name] = self.counts.get(name, 0) + 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _BLOCK_TAGS:
            self.text_chunks.append("\n")
        if tag in self.counts and self.counts[tag] > 0:
            self._pop_to(tag)

    def handle_data(self, data: str) -> None:
        if self._jsonld_buf is not None:
            self._jsonld_buf.append(data)
            return
        if self._title_buf is not None:
            self._title_buf.append(data)
        if self._heading is not None:
            self._heading[1].append(data)
        if data.strip() and not self._in(_RAW):
            self._seen_text = True
        if self._in(_CHROME | _RAW):
            return
        self.text_chunks.append(data)
        if self._para is not None:
            self._para.append(data)

    def _add_link(self, href: str) -> None:
        href = href.strip()
        if not href or href.startswith("#"):
            return
        full = urljoin(self.base_url, href)
        if urlsplit(full).scheme in ("http", "https"):
            self.links.add(full.split("#", 1)[0])


# -- public entry point ---------------------------------------------------------------
def same_site(host_a: str, host_b: str) -> bool:
    a, b = host_a.lower().removeprefix("www."), host_b.lower().removeprefix("www.")
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def _pick_canonical(url: str, candidates: list[str | None]) -> str:
    """The page's canonical URL. Cross-host and blanket homepage canonicals are never trusted."""
    page = canonical_url(url)
    page_parts = urlsplit(page)
    for href in candidates:
        if not href:
            continue
        full = urljoin(url, href.strip())
        if urlsplit(full).scheme not in ("http", "https"):
            continue
        parts = urlsplit(canonical_url(full))
        if parts.netloc != page_parts.netloc:
            continue
        if parts.path == "/" and page_parts.path != "/":
            continue
        return canonical_url(full)
    return page


def _clean_title(title: str, site_name: str | None) -> str:
    title = " ".join(title.split())
    if site_name:
        trimmed = re.sub(r"\s*[" + _TITLE_SEPARATORS + r"]\s*" + re.escape(site_name) + r"\s*$", "", title, flags=re.I)
        title = trimmed or title
    return title


def _first_date(values: list[str | None]) -> str | None:
    for value in values:
        iso = to_iso(value)
        if iso:
            return iso
    return None


def extract_page(html: str, url: str) -> PageMeta:
    """Derive metadata and numeric features from one HTML page. Tolerates malformed markup."""
    parser = _PageParser(url)
    try:
        parser.feed(html or "")
        parser.close()
    except Exception:  # keep whatever was collected before the parser gave up
        pass
    parser.finish()

    meta = parser.meta

    def first(*keys: str) -> str:
        return next((v for key in keys for v in meta.get(key, []) if v), "")

    nodes = jsonld_nodes(parser.jsonld)
    by_id = {n["@id"]: n for n in nodes if isinstance(n.get("@id"), str)}
    articles = [n for n in nodes if _ARTICLE_TYPES & set(_types_of(n))]
    article_ids = {id(n) for n in articles}
    ordered = articles + [n for n in nodes if id(n) not in article_ids]

    def ld(*fields: str) -> str:
        for node in ordered:
            for name in fields:
                text = _text_value(node.get(name))
                if text:
                    return text
        return ""

    schema_types: list[str] = []
    for node in nodes:
        for kind in _types_of(node):
            if kind not in schema_types:
                schema_types.append(kind)
    for kind in parser.itemtypes:
        if kind and kind not in schema_types:
            schema_types.append(kind)

    site_name = (
        first("og:site_name", "application-name", "apple-mobile-web-app-title")
        or next((_text_value(n.get("publisher")) for n in ordered if _text_value(n.get("publisher"))), "")
        or next((_text_value(n.get("name")) for n in nodes if "WebSite" in _types_of(n)), "")
        or None
    )
    title = _clean_title(
        first("og:title") or first("twitter:title") or ld("headline") or parser.title or parser.first_h1,
        site_name,
    )
    description = strip_html(first("description", "og:description", "twitter:description") or ld("description"))

    times = parser.times
    pub_times = [t["datetime"] for t in times if t["itemprop"] == "datepublished"]
    pub_times += [t["datetime"] for t in times
                  if _PUBLISHED_CLASS.search(t["class"]) and t["itemprop"] != "datemodified"]
    pub_times += [t["datetime"] for t in times
                  if t["itemprop"] != "datemodified" and not _MODIFIED_CLASS.search(t["class"])]
    mod_times = [t["datetime"] for t in times if t["itemprop"] == "datemodified" or _MODIFIED_CLASS.search(t["class"])]
    published = _first_date([
        first("article:published_time", "og:published_time"), ld("datePublished"),
        first("datepublished", "date", "pubdate", "publishdate", "publish_date", "dc.date.issued", "dc.date",
              "sailthru.date"),
        *pub_times,
    ])
    modified = _first_date([
        first("article:modified_time", "og:updated_time", "og:modified_time"), ld("dateModified"),
        first("datemodified", "last-modified"), *mod_times,
    ])

    brand_names = {(site_name or "").casefold()}
    meta_author = first("author", "article:author", "parsely-author", "sailthru.author", "dc.creator", "byl")
    has_byline = (
        parser.byline_hint
        or any(_author_present(n, by_id) for n in ordered)
        or bool(meta_author and meta_author.casefold() not in brand_names)
    )

    keywords: list[str] = []
    raw_keywords = [k for v in meta.get("keywords", []) for k in v.split(",")] + meta.get("article:tag", [])
    for node in ordered:
        raw_keywords += [k for v in _as_list(node.get("keywords")) if isinstance(v, str) for k in v.split(",")]
    for word in raw_keywords:
        word = word.strip()
        if word and word.casefold() not in {k.casefold() for k in keywords}:
            keywords.append(word)

    paragraphs = parser.paragraphs
    first_paragraph = next((p for p in paragraphs if len(p) >= 40), paragraphs[0] if paragraphs else "")

    page_host = urlsplit(url).hostname or ""
    internal = external = 0
    for link in parser.links:
        if same_site(urlsplit(link).hostname or "", page_host):
            internal += 1
        else:
            external += 1

    og_type = first("og:type") or None
    return PageMeta(
        url=url,
        canonical_url=_pick_canonical(url, [parser.canonical_href, first("og:url")]),
        title=title,
        description=description,
        lang=primary_lang(parser.html_lang) or primary_lang(first("og:locale"))
        or primary_lang(ld("inLanguage")) or primary_lang(first("content-language", "language", "dc.language")),
        published_at=published,
        modified_at=modified,
        site_name=site_name,
        has_byline=has_byline,
        schema_types=schema_types,
        keywords=keywords[:20],
        h1_count=parser.h1,
        h2_count=parser.h2,
        h3_count=parser.h3,
        list_items=parser.list_items,
        image_count=parser.images,
        has_video=parser.has_video or bool(first("og:video", "og:video:url")) or (og_type or "").startswith("video")
        or "VideoObject" in schema_types,
        has_faq="FAQPage" in schema_types or any(_FAQ_HEADING.search(t) for t in parser.heading_texts),
        word_count=count_words("".join(parser.text_chunks)),
        first_paragraph=shorten(first_paragraph, 300),
        links_internal=internal,
        links_external=external,
        tdm_reservation=any(v.strip() == "1" for v in meta.get("tdm-reservation", [])),
        og_type=og_type,
    )
