"""Feed parsing (RSS 2.0, RSS 1.0 RDF, Atom 1.0, JSON Feed) and feed autodiscovery from HTML.

Feeds are the preferred source: entries already carry title, date and summary, so pages need not be
fetched. Authors are never kept, only the boolean ``has_byline``.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.entities import name2codepoint
from html.parser import HTMLParser
from typing import Any, Iterable
from urllib.parse import urljoin, urlsplit

from ..models import Serializable
from .extract import shorten, strip_html, to_iso

NS_ATOM = "http://www.w3.org/2005/Atom"
NS_RSS1 = "http://purl.org/rss/1.0/"
NS_USERLAND = "http://backend.userland.com/rss2"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_CONTENT = "http://purl.org/rss/1.0/modules/content/"
NS_SLASH = "http://purl.org/rss/1.0/modules/slash/"
NS_MEDIA = "http://search.yahoo.com/mrss/"
NS_THR = "http://purl.org/syndication/thread/1.0"
NS_FEEDBURNER = "http://rssnamespace.org/feedburner/ext/1.0"
XML_BASE = "{http://www.w3.org/XML/1998/namespace}base"

SUMMARY_LIMIT = 500
_BOM = chr(0xFEFF)
_IMG_SRC = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["']""", re.I)
_IMAGE_EXT = re.compile(r"\.(?:jpe?g|png|gif|webp|avif|svg)(?:\?|$)", re.I)
_FEED_TYPES = frozenset({
    "application/rss+xml", "application/atom+xml", "application/feed+json", "application/rdf+xml",
})


@dataclass
class FeedEntry(Serializable):
    title: str
    url: str
    published_at: str | None = None   # ISO 8601 UTC
    summary: str = ""                 # plain text, at most 500 characters
    categories: list[str] = field(default_factory=list)
    has_byline: bool = False
    comments: int | None = None
    image: str | None = None


# -- XML loading ----------------------------------------------------------------------
def _repair_xml(raw: bytes) -> bytes:
    """Best-effort fix of the usual feed sins: HTML entities, bare ampersands, control characters."""
    declared = re.match(rb"""\s*<\?xml[^>]*encoding=["']([\w.-]+)["']""", raw)
    try:
        text = raw.decode(declared.group(1).decode("ascii") if declared else "utf-8", errors="replace")
    except LookupError:
        text = raw.decode("utf-8", errors="replace")

    def entity(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in ("amp", "lt", "gt", "quot", "apos"):
            return match.group(0)
        code = name2codepoint.get(name)
        return f"&#{code};" if code else f"&amp;{name};"

    text = re.sub(r"&([a-zA-Z][a-zA-Z0-9]*);", entity, text)
    text = re.sub(r"&(?!(?:[a-zA-Z][a-zA-Z0-9]*|#\d+|#x[0-9a-fA-F]+);)", "&amp;", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    return text.encode("utf-8")


def load_xml(data: bytes | str) -> ET.Element:
    """Parse untrusted XML. Entity declarations are refused (entity expansion attacks)."""
    if isinstance(data, str):
        raw = re.sub(r"^\s*<\?xml[^>]*\?>", "", data.lstrip(_BOM)).encode("utf-8")
    else:
        raw = data
    raw = raw.lstrip(b"\xef\xbb\xbf \t\r\n")
    if re.search(rb"<!ENTITY", raw):
        raise ValueError("XML with entity declarations is not accepted")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        pass
    try:
        return ET.fromstring(_repair_xml(raw))
    except ET.ParseError as err:
        raise ValueError(f"not a well-formed XML document: {err}") from err


def qname(el: ET.Element) -> tuple[str, str]:
    """(namespace, local name) of an element; comments and processing instructions give ("", "")."""
    tag = el.tag
    if not isinstance(tag, str):
        return "", ""
    if tag.startswith("{"):
        ns, _, local = tag[1:].partition("}")
        return ns, local
    return "", tag


# -- helpers --------------------------------------------------------------------------
def _text(el: ET.Element | None) -> str:
    return "".join(el.itertext()).strip() if el is not None else ""


def _kids(el: ET.Element) -> list[tuple[str, str, ET.Element]]:
    return [(*qname(child), child) for child in el if isinstance(child.tag, str)]


def _find(kids: list[tuple[str, str, ET.Element]], local: str, namespaces: Iterable[str] = ("",)) -> ET.Element | None:
    allowed = tuple(namespaces)
    return next((el for ns, name, el in kids if name == local and ns in allowed), None)


def _abs(base: str, href: str | None) -> str | None:
    if not href or not href.strip():
        return None
    full = urljoin(base, href.strip())
    return full if urlsplit(full).scheme in ("http", "https") else None


def _clean_summary(*candidates: str) -> str:
    for raw in candidates:
        text = strip_html(raw)
        if text:
            return shorten(text, SUMMARY_LIMIT)
    return ""


def _first_image_in_html(html: str, base: str) -> str | None:
    match = _IMG_SRC.search(html or "")
    return _abs(base, match.group(1)) if match else None


def _first_image_in_element(el: ET.Element | None, base: str) -> str | None:
    """First ``<img src>`` of embedded (x)html markup, for Atom ``content type="xhtml"``."""
    for node in el.iter() if el is not None else []:
        if qname(node)[1] == "img" and node.get("src"):
            return _abs(base, node.get("src"))
    return None


def _is_image(url: str, mime: str | None, medium: str | None = None) -> bool:
    if mime:
        return mime.lower().startswith("image/")
    return (medium or "").lower() == "image" or bool(_IMAGE_EXT.search(url))


def _media_image(kids: list[tuple[str, str, ET.Element]], base: str) -> str | None:
    for ns, name, el in kids:
        if ns == NS_MEDIA and name == "group":
            found = _media_image(_kids(el), base)
            if found:
                return found
        if ns == NS_MEDIA and name in ("thumbnail", "content") and el.get("url"):
            if name == "thumbnail" or _is_image(el.get("url", ""), el.get("type"), el.get("medium")):
                url = _abs(base, el.get("url"))
                if url:
                    return url
    return None


def _int(value: str | None) -> int | None:
    try:
        number = int((value or "").strip())
    except ValueError:
        return None
    return number if number >= 0 else None


def _categories(values: Iterable[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        value = " ".join(strip_html(value).split())
        if value and value.casefold() not in {c.casefold() for c in seen}:
            seen.append(value)
    return seen[:20]


def _first_date(*values: str) -> str | None:
    for value in values:
        iso = to_iso(value)
        if iso:
            return iso
    return None


# -- RSS 2.0 and RSS 1.0 --------------------------------------------------------------
def _parse_rss_item(item: ET.Element, base: str) -> FeedEntry | None:
    kids = _kids(item)
    plain = ("", NS_RSS1, NS_USERLAND)
    title = strip_html(_text(_find(kids, "title", plain)))
    link = _text(_find(kids, "link", plain))
    orig = _text(_find(kids, "origLink", (NS_FEEDBURNER,)))
    if orig and re.search(r"feedproxy\.google|feeds\.feedburner", link or "x"):
        link = orig
    if not link:
        guid = _text(_find(kids, "guid", plain))
        link = guid if guid.lower().startswith("http") else ""
    url = _abs(base, link)
    if not url:
        return None

    description = _text(_find(kids, "description", plain))
    encoded = _text(_find(kids, "encoded", (NS_CONTENT,)))
    summary = _clean_summary(description, encoded, _text(_find(kids, "description", (NS_DC,))))
    published = _first_date(
        _text(_find(kids, "pubDate", plain)), _text(_find(kids, "date", (NS_DC,))),
        _text(_find(kids, "published", (NS_ATOM, ""))), _text(_find(kids, "updated", (NS_ATOM, ""))),
    )
    categories = _categories(
        [_text(el) for ns, name, el in kids
         if (name == "category" and ns in plain) or (name == "subject" and ns == NS_DC)]
    )
    byline = any(
        _text(el) for ns, name, el in kids
        if (name == "author" and ns in plain) or (name == "creator" and ns == NS_DC)
        or (name == "author" and ns.endswith("itunes-1.0.dtd"))
    )
    comments = _int(_text(_find(kids, "comments", (NS_SLASH,))))

    image = _media_image(kids, base)
    if not image:
        for ns, name, el in kids:
            if name == "enclosure" and ns in plain and _is_image(el.get("url", ""), el.get("type")):
                image = _abs(base, el.get("url"))
                break
            if name == "image" and ns.endswith("itunes-1.0.dtd") and el.get("href"):
                image = _abs(base, el.get("href"))
                break
    image = image or _first_image_in_html(encoded or description, base)
    return FeedEntry(title or url, url, published, summary, categories, byline, comments, image)


# -- Atom -----------------------------------------------------------------------------
def _atom_text(el: ET.Element | None) -> str:
    """Text of an Atom text construct (text, html or xhtml) with markup removed."""
    if el is None:
        return ""
    kind = (el.get("type") or "text").lower()
    return strip_html(_text(el)) if kind in ("html", "xhtml", "text/html") or len(el) else _text(el)


def _parse_atom_entry(entry: ET.Element, base: str) -> FeedEntry | None:
    base = urljoin(base, entry.get(XML_BASE, ""))
    kids = _kids(entry)
    atom = (NS_ATOM,)
    links = [el for ns, name, el in kids if name == "link" and ns == NS_ATOM]
    alternate = [el for el in links if (el.get("rel") or "alternate") == "alternate" and el.get("href")]
    html_first = sorted(alternate, key=lambda el: 0 if "html" in (el.get("type") or "html") else 1)
    url = _abs(base, html_first[0].get("href")) if html_first else None
    if not url:
        ident = _text(_find(kids, "id", atom))
        url = ident if ident.lower().startswith("http") else None
    if not url:
        return None

    title = _atom_text(_find(kids, "title", atom))
    content_el = _find(kids, "content", atom)
    summary = _clean_summary(_text(_find(kids, "summary", atom)), _text(content_el))
    published = _first_date(
        _text(_find(kids, "published", atom)), _text(_find(kids, "updated", atom)),
        _text(_find(kids, "date", (NS_DC,))),
    )
    categories = _categories(
        [el.get("label") or el.get("term") or "" for ns, name, el in kids if name == "category" and ns == NS_ATOM]
        + [_text(el) for ns, name, el in kids if name == "subject" and ns == NS_DC]
    )
    byline = any(
        any(_text(child) for _, cname, child in _kids(el) if cname in ("name", "email", "uri"))
        for ns, name, el in kids if name == "author" and ns == NS_ATOM
    ) or any(_text(el) for ns, name, el in kids if name == "creator" and ns == NS_DC)

    comments = _int(_text(_find(kids, "total", (NS_THR,))))
    if comments is None:
        for el in links:
            if el.get("rel") == "replies":
                comments = _int(el.get(f"{{{NS_THR}}}count"))
                if comments is not None:
                    break

    image = _media_image(kids, base)
    if not image:
        for el in links:
            if el.get("rel") == "enclosure" and _is_image(el.get("href", ""), el.get("type")):
                image = _abs(base, el.get("href"))
                break
    html = _text(content_el) or _text(_find(kids, "summary", atom))
    image = image or _first_image_in_html(html, base) or _first_image_in_element(content_el, base)
    return FeedEntry(title or url, url, published, summary, categories, byline, comments, image)


# -- JSON Feed ------------------------------------------------------------------------
def _parse_json_feed(doc: dict[str, Any], base: str) -> list[FeedEntry]:
    entries: list[FeedEntry] = []
    for item in doc.get("items") or []:
        try:
            if not isinstance(item, dict):
                continue
            ident = str(item.get("id") or "")
            listed = item.get("url") or item.get("external_url")
            if not listed and ident.lower().startswith("http"):
                listed = ident
            url = _abs(base, listed)
            if not url:
                continue
            html = item.get("content_html") or ""
            authors = item.get("authors") or ([item["author"]] if item.get("author") else [])
            entries.append(FeedEntry(
                title=strip_html(str(item.get("title") or "")) or url,
                url=url,
                published_at=_first_date(str(item.get("date_published") or ""), str(item.get("date_modified") or "")),
                summary=_clean_summary(str(item.get("summary") or ""), str(item.get("content_text") or ""), html),
                categories=_categories(str(t) for t in item.get("tags") or []),
                has_byline=any(isinstance(a, dict) and str(a.get("name") or "").strip() for a in authors),
                image=_abs(base, item.get("image") or item.get("banner_image")) or _first_image_in_html(html, base),
            ))
        except Exception:
            continue
    return entries


# -- public API -----------------------------------------------------------------------
def parse_feed(data: bytes | str, base_url: str = "") -> list[FeedEntry]:
    """Entries of an RSS 2.0, RSS 1.0, Atom or JSON feed. Entries that cannot be read are skipped.

    Raises ``ValueError`` only when the document is not a feed at all.
    """
    head = data[:64].lstrip(b"\xef\xbb\xbf \t\r\n") if isinstance(data, bytes) else data[:64].lstrip(_BOM + " \t\r\n")
    if head[:1] in (b"{", "{"):
        text = data.decode("utf-8-sig", errors="replace") if isinstance(data, bytes) else data
        try:
            doc = json.loads(text)
        except ValueError as err:
            raise ValueError(f"not a feed: {err}") from err
        if not isinstance(doc, dict) or not isinstance(doc.get("items"), list):
            raise ValueError("not a feed: JSON without an items list")
        return _parse_json_feed(doc, base_url)

    root = load_xml(data)
    kind = qname(root)[1].lower()
    if kind == "rss":
        base = urljoin(base_url, root.get(XML_BASE, ""))
        items = [el for el in root.iter() if qname(el)[1] == "item"]
        parse = _parse_rss_item
    elif kind == "rdf":
        base = base_url
        items = [el for el in root if qname(el)[1] == "item"]
        parse = _parse_rss_item
    elif kind == "feed":
        base = urljoin(base_url, root.get(XML_BASE, ""))
        items = [el for el in root if qname(el)[1] == "entry"]
        parse = _parse_atom_entry
    else:
        raise ValueError(f"not a feed: root element <{qname(root)[1]}>")

    entries: list[FeedEntry] = []
    for node in items:
        try:
            entry = parse(node, base)
        except Exception:  # one bad entry must not cost the whole feed
            continue
        if entry is not None:
            entries.append(entry)
    return entries


class _LinkCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []
        self.base: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "base" and a.get("href") and self.base is None:
            self.base = a["href"]
        elif tag == "link" and a.get("href"):
            self.links.append(a)


def discover_feeds(html: str, base_url: str) -> list[str]:
    """Absolute feed URLs advertised with ``<link rel="alternate">``, de-duplicated, in page order."""
    collector = _LinkCollector()
    try:
        collector.feed((html or "")[:600_000])
        collector.close()
    except Exception:
        pass
    base = urljoin(base_url, collector.base) if collector.base else base_url
    found: list[str] = []
    for a in collector.links:
        if "alternate" not in a.get("rel", "").lower().split():
            continue
        if a.get("type", "").split(";")[0].strip().lower() not in _FEED_TYPES:
            continue
        if "comment" in a.get("title", "").lower():
            continue
        url = _abs(base, a["href"])
        if url and "/comments/" not in urlsplit(url).path and url not in found:
            found.append(url)
    return found
