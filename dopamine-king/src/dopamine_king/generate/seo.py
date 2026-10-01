"""SEO article format: builder, JSON-LD helpers, SEO score and the anti-slop quality gate.

Integrity rules: the builder never invents facts. Prose slots without a default stay open
(``[[ADD: ...]]``), citations are only vetted ``brief.sources`` entries referenced as
``[[cite:<id>]]``, and the quality gate refuses to call a draft publishable without first-party
experience (mass produced, low-value pages risk being treated as scaled content abuse however
they are made). The output is a draft for a human to finish.

This module also hosts the small text helpers shared by ``geo``, ``longform`` and ``guard``.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable, Sequence

from ..scoring import fold, rank_hooks
from .types import Brief, Draft, FormatSpec, Issue, Skeleton, Slot

# -- shared text helpers ---------------------------------------------------------------
PLACEHOLDER_RE = re.compile(r"\[\[ADD\b.*?\]\]", re.S)
CITE_RE = re.compile(r"\[\[cite:([A-Za-z0-9_.:-]+)\]\]")
_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_FENCE_RE = re.compile(r"```.*?```", re.S)
_FRONT_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]*)[^)]*\)")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
_ABBREV_RE = re.compile(r"\b(e\.g|i\.e|vs|dr|mr|mrs|ms|prof|approx|např|tzv|tj|apod|atd|resp|cca|tzn|ing|mgr|bc)\.", re.I)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])[\"')\]]*\s+|\n+")
_HEADING_LINE_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t#]*$", re.M)
_SLUG_MAP = str.maketrans({"ß": "ss", "ø": "o", "đ": "d", "ł": "l", "æ": "ae", "œ": "oe", "þ": "th"})

_MONTHS = {
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"),
    "cs": ("ledna", "února", "března", "dubna", "května", "června", "července", "srpna", "září",
           "října", "listopadu", "prosince"),
}


def norm_lang(lang: str | None) -> str:
    return "cs" if (lang or "").lower().startswith("cs") else "en"


def tr(lang: str | None, en: str, cs: str) -> str:
    """Pick the English or Czech variant of a message."""
    return cs if norm_lang(lang) == "cs" else en


def cap_first(text: str) -> str:
    return text[:1].upper() + text[1:]


def format_date(value: str | date | None, lang: str = "en") -> str:
    """Human readable date ("October 1, 2026" / "1. října 2026"); unparsable input is returned as is."""
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        d = value.date()
    elif isinstance(value, date):
        d = value
    else:
        try:
            d = date.fromisoformat(str(value).strip()[:10])
        except ValueError:
            return str(value)
    if norm_lang(lang) == "cs":
        return f"{d.day}. {_MONTHS['cs'][d.month - 1]} {d.year}"
    return f"{_MONTHS['en'][d.month - 1]} {d.day}, {d.year}"


def front_matter(body: str) -> tuple[dict[str, str], str]:
    """Split a leading ``---`` block of simple ``key: value`` lines from a Markdown body."""
    m = _FRONT_RE.match(body or "")
    if not m:
        return {}, body or ""
    fields: dict[str, str] = {}
    for line in m.group(1).splitlines():
        key, sep, val = line.partition(":")
        if sep:
            fields[key.strip().lower()] = val.strip()
    return fields, body[m.end():]


def plain_text(md: str) -> str:
    """All readable text of a Markdown draft: no syntax, cite markers, placeholders or URLs."""
    t = _FENCE_RE.sub(" ", md or "")
    t = PLACEHOLDER_RE.sub(" ", t)
    t = CITE_RE.sub("", t)
    t = _IMG_RE.sub(r"\1", t)
    t = _LINK_RE.sub(r"\1", t)
    t = _URL_RE.sub(" ", t)
    out: list[str] = []
    for line in t.splitlines():
        s = line.strip()
        if re.fullmatch(r"[-=_*|:\s]*", s):          # blank line, rule or table separator
            continue
        s = re.sub(r"^(?:#{1,6}\s+|>\s*|[-*+]\s+|\d{1,3}[.)]\s+)+", "", s)
        s = re.sub(r"[*_`]+", "", s.replace("|", " "))
        out.append(s.strip())
    return "\n".join(out)


def prose_paragraphs(md: str) -> list[str]:
    """Running text paragraphs: no front matter, headings, tables or code; list items and quotes stand alone."""
    _, body = front_matter(md)
    body = _FENCE_RE.sub("\n", body)
    paras: list[str] = []
    cur: list[str] = []

    def flush() -> None:
        if cur:
            paras.append(plain_text(" ".join(cur)).replace("\n", " ").strip())
            cur.clear()

    for raw in body.splitlines():
        s = raw.strip()
        if not s or s.startswith(("#", "|", "---", "***")):
            flush()
            continue
        if re.match(r"\s*(?:>|[-*+]\s|\d{1,3}[.)]\s)", raw):
            flush()
        cur.append(s)
    flush()
    return [p for p in paras if p]


def count_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def split_sentences(text: str) -> list[str]:
    protected = _ABBREV_RE.sub(lambda m: m.group(0).replace(".", "\x00"), text or "")
    parts = _SENT_SPLIT_RE.split(protected)
    return [p.replace("\x00", ".").strip() for p in parts if p and p.strip()]


def avg_sentence_words(md: str) -> float:
    sents = [s for p in prose_paragraphs(md) for s in split_sentences(p)]
    if not sents:
        return 0.0
    return sum(count_words(s) for s in sents) / len(sents)


def parse_headings(md: str) -> list[tuple[int, str]]:
    """(level, text) for every Markdown heading outside code fences and front matter."""
    _, body = front_matter(md)
    body = _FENCE_RE.sub("", body)
    return [(len(m.group(1)), re.sub(r"[*_`]+", "", m.group(2)).strip()) for m in _HEADING_LINE_RE.finditer(body)]


def parse_faq(md: str) -> list[tuple[str, str]]:
    """FAQ pairs: question headings (H3 or deeper) with an answer, plus ``Q:`` / ``A:`` line pairs."""
    _, body = front_matter(md)
    body = _FENCE_RE.sub("", body)
    pairs: list[tuple[str, str]] = []
    heading: tuple[int, str] | None = None
    buf: list[str] = []

    def close() -> None:
        if heading and heading[0] >= 3 and heading[1].rstrip().endswith("?"):
            answer = plain_text("\n".join(buf)).strip()
            if count_words(answer) >= 4:
                pairs.append((heading[1], answer))

    for line in body.splitlines():
        m = _HEADING_LINE_RE.match(line)
        if m:
            close()
            heading, buf = (len(m.group(1)), re.sub(r"[*_`]+", "", m.group(2)).strip()), []
        else:
            buf.append(line)
    close()
    for m in re.finditer(r"^\s*\**(?:Q|Otázka)[:.]\**\s*(.+?)\s*\n\s*\**(?:A|Odpověď)[:.]\**\s*(.+)$", body, re.M):
        pairs.append((m.group(1).strip(), m.group(2).strip()))
    return pairs


def cite_ids(text: str) -> list[str]:
    """Distinct ``[[cite:id]]`` ids in order of first appearance."""
    seen: list[str] = []
    for m in CITE_RE.finditer(text or ""):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def render_citations(text: str, sources: Sequence[dict[str, Any]]) -> str:
    """Replace ``[[cite:id]]`` with numbered references ``[n]`` (numbering follows ``sources``).

    Unknown ids stay untouched so a guard can still flag them.
    """
    order = {s.get("id"): i for i, s in enumerate(sources, 1) if s.get("id")}
    return CITE_RE.sub(lambda m: f"[{order[m.group(1)]}]" if m.group(1) in order else m.group(0), text or "")


def sources_block(sources: Sequence[dict[str, Any]], heading: str) -> str:
    """Numbered Markdown Sources section from vetted sources ("" when there are none)."""
    if not sources:
        return ""
    lines = [f"## {heading}", ""]
    for i, s in enumerate(sources, 1):
        title = str(s.get("title") or s.get("url") or s.get("id") or "").strip()
        url = str(s.get("url") or "").strip()
        lines.append(f"{i}. [{title}]({url})" if url else f"{i}. {title}")
    return "\n".join(lines)


def _tok(text: str) -> list[str]:
    return [fold(w).lower() for w in _WORD_RE.findall(text or "")]


def _same_word(a: str, b: str, fuzzy: bool) -> bool:
    if a == b:
        return True
    if not fuzzy:                                   # English: tolerate plural -s
        return min(len(a), len(b)) > 3 and a.rstrip("s") == b.rstrip("s")
    if min(len(a), len(b)) < 3:
        return False
    k = 0
    for x, y in zip(a, b):
        if x != y:
            break
        k += 1
    return k >= max(3, min(len(a), len(b)) - 2)      # Czech: tolerate case endings


def count_keyword(text: str, keyword: str, lang: str = "en") -> int:
    """Non overlapping occurrences of a keyword phrase (diacritics and case insensitive).

    Czech matching tolerates declension endings so "bezeckych bot" still counts for "bezecke boty".
    """
    kw = _tok(keyword)
    toks = _tok(text)
    if not kw:
        return 0
    fuzzy = norm_lang(lang) == "cs"
    n, i, hits = len(kw), 0, 0
    while i <= len(toks) - n:
        if all(_same_word(toks[i + j], kw[j], fuzzy) for j in range(n)):
            hits += 1
            i += n
        else:
            i += 1
    return hits


def keyword_density(text: str, keyword: str, lang: str = "en") -> tuple[int, int, float]:
    """(keyword occurrences, total words, occurrences per 100 words)."""
    words = count_words(text)
    hits = count_keyword(text, keyword, lang)
    return hits, words, (100.0 * hits / words if words else 0.0)


# -- slugs and intent --------------------------------------------------------------------
def slugify(text: str, lang: str = "en", max_len: int = 70) -> str:
    """URL slug: diacritics stripped, lowercase, hyphen separated, cut at a word boundary."""
    s = unicodedata.normalize("NFKC", text or "").lower().translate(_SLUG_MAP)
    s = fold(s).replace("&", " and " if norm_lang(lang) == "en" else " a ")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    if len(s) > max_len:
        cut = s[:max_len]
        if s[max_len] != "-" and "-" in cut:
            cut = cut.rsplit("-", 1)[0]
        s = cut.strip("-")
    return s


INTENTS = ("informational", "commercial", "transactional", "navigational")
# Cue tables are matched on lowercase, diacritics-free tokens. Weights: how-to starters 3,
# question starters 2, commercial 2, transactional 2, navigational 3, weak informational 1.
_HOWTO_START = {"en": ("how to", "how do i", "how can i", "how do you"), "cs": ("jak", "jak na")}
_QUESTION_START = {
    "en": ("what is", "what are", "what does", "why", "when", "can i", "should i", "is it", "do i"),
    "cs": ("co je", "co jsou", "proc", "kdy", "muzu", "mam", "lze"),
}
_CUES = {
    "navigational": {
        "en": ("login", "log in", "sign in", "official site", "official website", "homepage", "customer service", "contact"),
        "cs": ("prihlaseni", "prihlasit", "oficialni", "kontakt", "zakaznicka podpora", "domovska stranka"),
    },
    "transactional": {
        "en": ("buy", "order", "purchase", "price", "prices", "pricing", "cheap", "discount", "coupon", "deal", "deals",
               "for sale", "near me", "shop", "free trial", "quote"),
        "cs": ("koupit", "kup", "objednat", "objednavka", "cena", "ceny", "cenik", "levne", "levny", "sleva", "slevy",
               "akce", "eshop", "e-shop", "prodej", "kolik stoji"),
    },
    "commercial": {
        "en": ("best", "top", "vs", "versus", "review", "reviews", "compare", "comparison", "alternative", "alternatives",
               "recommended", "worth it"),
        "cs": ("nejlepsi", "nejlepsich", "top", "vs", "versus", "recenze", "srovnani", "porovnani", "alternativa",
               "alternativy", "zkusenosti", "doporucene", "test", "testy", "vyplati se"),
    },
    "informational": {
        "en": ("guide", "tutorial", "tips", "ideas", "examples", "meaning", "definition", "explained"),
        "cs": ("navod", "pruvodce", "tipy", "priklady", "vyznam", "definice"),
    },
}
_INTENT_PRIORITY = ("navigational", "transactional", "commercial", "informational")


def _intent_scores(padded: str, lang: str) -> dict[str, int]:
    scores = {k: 0 for k in INTENTS}
    for cue in _HOWTO_START[lang]:
        if padded.startswith(f" {cue} "):
            scores["informational"] += 3
    for cue in _QUESTION_START[lang]:
        if padded.startswith(f" {cue} "):
            scores["informational"] += 2
    for intent, by_lang in _CUES.items():
        weight = {"navigational": 3, "transactional": 2, "commercial": 2, "informational": 1}[intent]
        for cue in by_lang[lang]:
            if f" {cue} " in padded:
                scores[intent] += weight
    return scores


def detect_intent(keyword: str, lang: str = "en") -> str:
    """Search intent of a keyword from en/cs cues: informational, commercial, transactional or navigational.

    The cue table of ``lang`` is tried first; the other language is a fallback for mixed keywords.
    No cue at all means informational.
    """
    toks = _tok(keyword)
    if not toks:
        return "informational"
    padded = " " + " ".join(toks) + " "
    primary = norm_lang(lang)
    for code in (primary, "en" if primary == "cs" else "cs"):
        scores = _intent_scores(padded, code)
        if any(scores.values()):
            best = max(scores.values())
            return next(i for i in _INTENT_PRIORITY if scores[i] == best)
    return "informational"


# -- JSON-LD -----------------------------------------------------------------------------
# Note: Google has limited FAQ rich results (mostly well known government and health sites) and
# retired HowTo rich results. The markup is still cheap, valid and helps other machine readers
# (answer engines, assistants, validators), so the builders keep emitting it.
SCHEMA_CONTEXT = "https://schema.org"


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Drop blank values and unfilled placeholders so markup never carries them."""
    out: dict[str, Any] = {}
    for k, v in data.items():
        if v is None or v == "" or v == [] or v == {}:
            continue
        if isinstance(v, str) and PLACEHOLDER_RE.search(v):
            continue
        out[k] = v
    return out


def _text_clean(text: Any) -> str:
    t = CITE_RE.sub("", str(text or ""))
    t = _LINK_RE.sub(r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def _person(author: dict[str, Any] | None) -> dict[str, Any] | None:
    if not author or not author.get("name"):
        return None
    return _clean({"@type": "Person", "name": author["name"], "jobTitle": author.get("role")})


def jsonld_organization(name: str, *, url: str | None = None, logo: str | None = None,
                        same_as: Sequence[str] | None = None, description: str | None = None) -> dict[str, Any]:
    return _clean({"@context": SCHEMA_CONTEXT, "@type": "Organization", "name": name, "url": url, "logo": logo,
                   "sameAs": list(same_as or []), "description": description})


def jsonld_article(headline: str, *, description: str | None = None, url: str | None = None, lang: str = "en",
                   author: dict[str, Any] | None = None, publisher: str | None = None,
                   published: str | None = None, modified: str | None = None, image: str | None = None,
                   keywords: Sequence[str] | None = None, word_count: int | None = None,
                   article_type: str = "Article") -> dict[str, Any]:
    """schema.org Article (``article_type`` may be BlogPosting, NewsArticle, ...)."""
    return _clean({
        "@context": SCHEMA_CONTEXT, "@type": article_type, "headline": _text_clean(headline)[:110],
        "description": _text_clean(description) or None, "inLanguage": norm_lang(lang),
        "mainEntityOfPage": {"@type": "WebPage", "@id": url} if url else None,
        "author": _person(author), "publisher": {"@type": "Organization", "name": publisher} if publisher else None,
        "datePublished": published, "dateModified": modified or published, "image": image,
        "keywords": ", ".join(keywords) if keywords else None, "wordCount": word_count,
    })


def jsonld_faq(pairs: Iterable[Any]) -> dict[str, Any]:
    """FAQPage from (question, answer) tuples or {"q","a"} dicts; unfilled pairs are skipped.

    ``mainEntity`` is empty when no pair is usable: callers should then omit the node.
    """
    entities = []
    for pair in pairs:
        q, a = (pair["q"], pair["a"]) if isinstance(pair, dict) else pair
        q, a = _text_clean(q), _text_clean(a)
        if not q or not a or PLACEHOLDER_RE.search(f"{q} {a}"):
            continue
        entities.append({"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}})
    return {"@context": SCHEMA_CONTEXT, "@type": "FAQPage", "mainEntity": entities}


def jsonld_howto(name: str, steps: Sequence[Any], *, description: str | None = None, total_time: str | None = None,
                 tools: Sequence[str] | None = None, supplies: Sequence[str] | None = None) -> dict[str, Any]:
    """HowTo from step strings or {"name","text"} dicts; ``total_time`` is an ISO 8601 duration (PT30M)."""
    items = []
    for step in steps:
        text = _text_clean(step.get("text") or step.get("name")) if isinstance(step, dict) else _text_clean(step)
        if not text:
            continue
        item: dict[str, Any] = {"@type": "HowToStep", "position": len(items) + 1, "text": text}
        if isinstance(step, dict) and step.get("name"):
            item["name"] = _text_clean(step["name"])
        items.append(item)
    return _clean({
        "@context": SCHEMA_CONTEXT, "@type": "HowTo", "name": _text_clean(name), "description": _text_clean(description) or None,
        "totalTime": total_time, "tool": [{"@type": "HowToTool", "name": t} for t in tools or []],
        "supply": [{"@type": "HowToSupply", "name": s} for s in supplies or []], "step": items,
    })


def jsonld_video(name: str, description: str, *, thumbnail_url: str | None = None, upload_date: str | None = None,
                 duration: str | None = None, content_url: str | None = None,
                 embed_url: str | None = None) -> dict[str, Any]:
    """VideoObject; Google expects name, thumbnailUrl and uploadDate, so provide them when known."""
    return _clean({
        "@context": SCHEMA_CONTEXT, "@type": "VideoObject", "name": _text_clean(name),
        "description": _text_clean(description) or None, "thumbnailUrl": thumbnail_url, "uploadDate": upload_date,
        "duration": duration, "contentUrl": content_url, "embedUrl": embed_url,
    })


def jsonld_breadcrumbs(items: Sequence[Any]) -> dict[str, Any]:
    """BreadcrumbList from (name, url) tuples or {"name","url"} dicts; the last url may be omitted."""
    elements = []
    for i, item in enumerate(items, 1):
        name, url = (item.get("name"), item.get("url")) if isinstance(item, dict) else (item[0], item[1] if len(item) > 1 else None)
        elements.append(_clean({"@type": "ListItem", "position": i, "name": name, "item": url}))
    return {"@context": SCHEMA_CONTEXT, "@type": "BreadcrumbList", "itemListElement": elements}


def render_jsonld(nodes: dict[str, Any] | Sequence[dict[str, Any]]) -> str:
    """``<script type="application/ld+json">`` blocks, with ``</`` escaped so text cannot close the tag."""
    items = [nodes] if isinstance(nodes, dict) else list(nodes)
    blocks = []
    for node in items:
        data = json.dumps(node, ensure_ascii=False, indent=2).replace("</", "<\\/")
        blocks.append(f'<script type="application/ld+json">\n{data}\n</script>')
    return "\n".join(blocks)


# -- builder data ------------------------------------------------------------------------
# Outline per intent: (key, English heading, Czech heading, writer instruction). The Czech headings read
# naturally with any topic (a nominative topic before a colon, or no topic at all), so no case form is needed.
_OUTLINES: dict[str, list[tuple[str, str, str, str]]] = {
    "informational": [
        ("definition", "What do we mean by {kw}?", "{Kw}: o co jde?",
         "Define {kw} in plain language for {audience}: the category, the key parts and one example. No history lesson."),
        ("why", "Why should you care about {kw}?", "Proč na tom záleží?",
         "Explain why {kw} matters to {audience}. Use only first-party facts or vetted sources, no generic claims."),
        ("steps", "How do you get started with {kw}, step by step?", "Jak na to krok za krokem?",
         "Give 4-6 numbered, concrete steps a beginner can follow, each with one sentence on why it matters."),
        ("mistakes", "Which mistakes should you avoid?", "Jakým chybám se vyhnout?",
         "Describe 3-5 common mistakes and how to avoid each, based on what the brand has itself observed."),
        ("examples", "What does it look like in practice?", "Jak to vypadá v praxi?",
         "Show one or two concrete examples from the brand's own experience or the supplied facts. Never invent customers."),
        ("tools", "Which tools and resources help?", "Které nástroje a zdroje pomáhají?",
         "List useful tools, checklists or resources. Mention the brand's own offer only where it genuinely fits."),
        ("who", "Who is it for, and who can skip it?", "Pro koho to je a pro koho ne?",
         "Say who benefits most and who does not need this. Be honest about the limits."),
        ("measure", "How do you know it is working?", "Jak poznáte, že to funguje?",
         "Name 2-4 signals that show progress and how to track them."),
    ],
    "commercial": [
        ("criteria", "What should you look for when choosing {kw}?", "{Kw}: podle čeho vybírat?",
         "List the 4-6 selection criteria that matter most to {audience}, each with a short reason."),
        ("comparison", "How do the main options compare?", "Jak si jednotlivé možnosti stojí v porovnání?",
         "Compare the main options on the criteria above. Use only supplied facts; keep claims about competitors verifiable."),
        ("proscons", "What are the pros and cons?", "Jaké jsou výhody a nevýhody?",
         "Give honest pros and cons, including the brand's own offer. A fair list builds trust."),
        ("pricing", "What should you expect to pay?", "Kolik to stojí?",
         "Explain what drives the price and typical price ranges, using only supplied facts or sources."),
        ("alternatives", "What are the alternatives?", "Jaké existují alternativy?",
         "Name realistic alternatives and when each is the better choice."),
        ("who", "Who should choose what?", "Pro koho se co hodí?",
         "Match option types to reader situations in a short list."),
        ("checklist", "What should you check before you commit?", "Co si ověřit, než se rozhodnete?",
         "Give a short pre-purchase checklist."),
        ("questions", "Which questions should you ask a seller?", "Na co se zeptat prodejce?",
         "List 4-6 practical questions a buyer should ask."),
    ],
    "transactional": [
        ("offer", "What exactly do you get?", "Co přesně dostanete?",
         "Describe the offer ({offer}) concretely: what is included, what is not, who delivers it."),
        ("benefits", "What are the benefits?", "Jaké jsou výhody?",
         "State the benefits for {audience} as outcomes, each tied to a supplied fact. No superlatives without proof."),
        ("proof", "What does the evidence say?", "Co ukazují fakta a zkušenosti?",
         "Present the proof: first-party data, tests or customer results the brand supplied, and cited sources. Never invent any."),
        ("order", "How do you order?", "Jak objednat?",
         "Explain the ordering steps in order, including payment, delivery or setup, and how to get help."),
        ("who", "Who is it for?", "Pro koho je to určené?",
         "Say who this is for and who should look elsewhere."),
        ("after", "What happens after you order?", "Co se děje po objednání?",
         "Describe what happens next, with realistic timing from supplied facts only."),
        ("plans", "Which options are available?", "Jaké jsou k dispozici možnosti?",
         "Describe the variants or plans and how to pick one."),
        ("fit", "What if it is not the right fit?", "Co když to není pro vás?",
         "Explain returns, cancellation or support exactly as the brand's real policy states. Do not invent terms."),
    ],
}
_OUTLINES["navigational"] = _OUTLINES["informational"]

_TITLE_PATTERNS: dict[str, dict[str, dict[str, list[str]]]] = {
    "en": {
        "noun": {
            "informational": ["{Kw}: a practical guide for {audience}", "{Kw}: what to know before you start",
                              "{Kw} explained: steps, mistakes and examples", "How to get started with {kw}",
                              "{Kw}: a clear guide"],
            "commercial": ["How to choose {kw}: criteria that matter", "{Kw} compared: criteria, pros and cons",
                           "{Kw}: how to choose and compare", "Choosing {kw}: what to compare"],
            "transactional": ["{Kw}: what you get and how to order", "{Kw}: offer, benefits and how to order",
                              "Order {kw}: options and how it works", "{Kw}: options, benefits and ordering"],
        },
        "question": {
            "all": ["{Kw}: a practical guide for {audience}", "{Kw}: a clear, practical answer", "{Kw}? A practical guide",
                    "{Kw}: what to know"],
        },
    },
    "cs": {
        "noun": {
            "informational": ["{Kw}: praktický průvodce", "{Kw}: co je dobré vědět", "{Kw} krok za krokem",
                              "{Kw}: základy, chyby a příklady", "Vše o {loc}: praktický průvodce"],
            "commercial": ["{Kw}: jak vybrat a na co se zaměřit", "{Kw}: srovnání a kritéria výběru", "{Kw}: jak vybrat",
                           "Jak vybrat {acc}: na co se zaměřit", "Výběr {gen}: srovnání a kritéria"],
            "transactional": ["{Kw}: co dostanete a jak objednat", "{Kw}: nabídka, výhody a objednání",
                              "{Kw}: možnosti a postup objednání", "Objednávka {gen}: možnosti a postup"],
        },
        "question": {
            "all": ["{Kw}: srozumitelná odpověď", "{Kw}: praktický průvodce", "{Kw}? Praktický průvodce"],
        },
    },
}

_META_PATTERNS: dict[str, dict[str, list[str]]] = {
    "en": {
        "informational": ["A practical guide to {kw} for {audience}: definition, step-by-step approach, common mistakes and examples. By {brand}.",
                          "A practical guide to {kw}: definition, steps, common mistakes and examples. By {brand}.",
                          "A practical guide to {kw}: definition, steps, common mistakes and examples."],
        "commercial": ["How to choose {kw}: criteria, a comparison, pros and cons, pricing and alternatives, explained for {audience} by {brand}.",
                       "How to choose {kw}: criteria, comparison, pros and cons, pricing and alternatives. By {brand}.",
                       "How to choose {kw}: criteria, comparison, pros and cons, pricing and alternatives."],
        "transactional": ["{Kw}: what is included, the benefits, the evidence and how to order, explained for {audience} by {brand}.",
                          "{Kw}: what is included, the benefits, the evidence and how to order. By {brand}.",
                          "{Kw}: what is included, the benefits, the evidence and how to order."],
    },
    "cs": {
        "informational": ["Vše o {loc}: základní pojmy, postup krok za krokem, časté chyby a příklady od značky {brand}.",
                          "Praktický průvodce: {kw}. Základní pojmy, postup krok za krokem, časté chyby a příklady od značky {brand}.",
                          "Praktický průvodce: {kw}. Postup, časté chyby a příklady od značky {brand}.",
                          "Praktický průvodce: {kw}. Postup, časté chyby a příklady."],
        "commercial": ["Jak vybrat {acc}: kritéria, srovnání, výhody a nevýhody, ceny a alternativy. Průvodce od značky {brand}.",
                       "{Kw}: jak vybrat, kritéria, srovnání, výhody a nevýhody, ceny a alternativy. Průvodce od značky {brand}.",
                       "{Kw}: jak vybrat, kritéria, srovnání, výhody a nevýhody a alternativy. Od značky {brand}.",
                       "{Kw}: jak vybrat, kritéria, srovnání, výhody a nevýhody a alternativy."],
        "transactional": ["{Kw}: co je součástí nabídky, výhody, důkazy a jak objednat. Informace od značky {brand}.",
                          "{Kw}: co je součástí nabídky, výhody a jak objednat. Od značky {brand}.",
                          "{Kw}: co je součástí nabídky, výhody a jak objednat."],
    },
}
_META_TAIL = {"en": "Includes answers to frequent questions.", "cs": "Součástí jsou odpovědi na časté dotazy."}

_FAQ_PATTERNS: dict[str, dict[str, dict[str, list[str]]]] = {
    "en": {
        "noun": {
            "informational": ["What should you know about {kw} before you start?", "How do I get started with {kw}?",
                              "What mistakes should {audience} avoid with {kw}?", "Who should use {kw}?"],
            "commercial": ["How do I choose {kw}?", "How much should I budget for {kw}?",
                           "Is it worth investing in {kw}?", "What are the alternatives to {kw}?"],
            "transactional": ["How do I order {kw}?", "How much does it cost and what is included?",
                              "How do returns or cancellations work?", "How long do delivery or setup take?"],
        },
        "question": {"all": ["{Kw}?", "What do I need to get started?", "What mistakes should {audience} avoid?",
                             "What should I do next?"]},
    },
    "cs": {
        "noun": {
            "informational": ["Co je dobré vědět o {loc} na začátku?|{Kw}: co je dobré vědět na začátku?", "{Kw}: jak začít?", "{Kw}: jakých chyb se vyvarovat?",
                              "{Kw}: pro koho se to hodí?"],
            "commercial": ["Jak vybrat {acc}?|{Kw}: jak vybrat?", "{Kw}: kolik to stojí?", "{Kw}: vyplatí se to?", "{Kw}: jaké jsou alternativy?"],
            "transactional": ["Jak objednat {acc}?|{Kw}: jak objednat?", "{Kw}: kolik to stojí a co je v ceně?",
                              "{Kw}: jak funguje vrácení nebo zrušení?", "{Kw}: jak dlouho trvá dodání nebo zavedení?"],
        },
        "question": {"all": ["{Kw}?", "Co je potřeba na začátek?", "Jakých chyb se vyvarovat?", "Co dělat dál?"]},
    },
}

_Q_START_EN = {"how", "what", "why", "when", "where", "which", "who"}
_Q_START_EN2 = {("can", "i"), ("should", "i"), ("is", "it"), ("do", "i"), ("does", "it")}
_Q_START_CS = {"jak", "co", "proc", "kdy", "kde", "ktery", "ktera", "ktere", "kdo", "kolik", "jaky", "jaka", "jake"}


def is_question_keyword(keyword: str) -> bool:
    """True when the keyword is itself a question ("how to choose running shoes", "jak vybrat boty")."""
    toks = _tok(keyword)
    if len(toks) < 2:
        return False
    return toks[0] in _Q_START_EN or toks[0] in _Q_START_CS or tuple(toks[:2]) in _Q_START_EN2


def _ph(slot_id: str) -> str:
    return "{{" + slot_id + "}}"


def _case_forms(brief: Brief, kw: str) -> dict[str, str]:
    """Topic case forms, usable only when the keyword is the topic itself."""
    if fold(kw).lower() != fold(brief.topic).lower():
        return {}
    return {c: brief.topic_forms.get(c, "") for c in ("gen", "dat", "acc", "loc", "ins")}


def _usable(pattern: str, ctx: dict[str, str]) -> bool:
    return all(ctx.get(t) for t in ("gen", "dat", "acc", "loc", "ins") if "{" + t + "}" in pattern)


def _resolve(pattern: str, ctx: dict[str, str]) -> str | None:
    """First usable alternative of a ``a|b`` pattern, formatted ("" forms make an alternative unusable)."""
    for alt in pattern.split("|"):
        if _usable(alt, ctx):
            return alt.format(**ctx)
    return None


def _pick_title(cands: Sequence[str], lang: str, max_len: int = 60) -> str | None:
    fit = [c for c in dict.fromkeys(cands) if len(c) <= max_len]
    if not fit:
        return None
    ranked = rank_hooks(fit, lang=lang)
    for text, sc in ranked:
        if sc.clickbait_risk <= 0.3:           # never clickbait
            return text
    return ranked[0][0]


def _fit_meta(cands: Sequence[str], tail: str, lo: int = 120, hi: int = 155) -> str:
    pool = list(cands) + [f"{c} {tail}" for c in cands]
    for c in pool:
        if lo <= len(c) <= hi:
            return c
    best = min(pool, key=lambda c: lo - len(c) if len(c) < lo else len(c) - hi)
    if len(best) > hi:
        best = best[:hi].rsplit(" ", 1)[0].rstrip(",;:- ")
        if not best.endswith((".", "!", "?")):
            best += "."
    return best


def _clean_links(raw: Any) -> list[dict[str, str]]:
    out = []
    for item in raw or []:
        if isinstance(item, dict) and str(item.get("url") or "").strip():
            url = str(item["url"]).strip()
            out.append({"url": url, "anchor": str(item.get("anchor") or url).strip()})
    return out


def _source_entries(brief: Brief) -> list[dict[str, Any]]:
    out = []
    for i, s in enumerate(brief.sources, 1):
        out.append({"n": i, "id": s.get("id"), "title": s.get("title"), "url": s.get("url"), "claim": s.get("claim")})
    return out


def _source_hint(brief: Brief) -> str:
    if not brief.sources:
        return ""
    return " Vetted sources: " + "; ".join(f"{s.get('id')} ({s.get('claim') or s.get('title') or ''})" for s in brief.sources) + "."


def _make_assemble(lang: str, brand: str, kw: str, headings: list[str], links: list[dict[str, str]],
                   word_target: int, author: dict[str, Any] | None, published: str | None, url: str | None, n_faq: int):
    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        title = values.get("title", "")
        h1 = values.get("h1", "") or title
        nodes: list[dict[str, Any]] = [jsonld_article(
            h1, description=values.get("meta_description"), url=url, lang=lang, author=author, publisher=brand,
            published=published, keywords=[kw], word_count=word_target)]
        faq = jsonld_faq((values.get(f"faq_q{i}", ""), values.get(f"faq_a{i}", "")) for i in range(1, n_faq + 1))
        if faq["mainEntity"]:
            nodes.append(faq)
        questions = sum(1 for h in headings if h.rstrip().endswith("?"))
        return {
            "json_ld": nodes, "outline": list(headings), "slug": slugify(title or kw, lang),
            "toc": [{"level": 2, "title": h, "anchor": slugify(h, lang)} for h in headings],
            "internal_links": list(links), "word_target": word_target,
            "question_ratio": round(questions / len(headings), 3) if headings else 0.0,
        }
    return assemble


_META_Q = {
    "en": ["{Kw}? A practical answer for {audience}: key steps, common mistakes and examples. By {brand}.",
           "{Kw}? A practical answer: key steps, common mistakes and examples. By {brand}.",
           "{Kw}? A practical answer: key steps, common mistakes and examples."],
    "cs": ["{Kw}? Praktická odpověď: postup, časté chyby a příklady od značky {brand}.",
           "{Kw}? Praktická odpověď: postup, časté chyby a příklady."],
}


def _shorten(text: str, n: int) -> str:
    if len(text) <= n:
        return text
    return text[:n].rsplit(" ", 1)[0] or text[:n]


# -- the builder -------------------------------------------------------------------------
def build_seo_article(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """SEO article skeleton.

    options: intent, word_target (default 1500), sections (default 6, clamped to 3..8), internal_links
    (list of {"url","anchor"}), published (ISO date), author ({"name","role"}), url (canonical URL).
    """
    opts = dict(options or {})
    lang = norm_lang(brief.lang)
    kw_clean = brief.primary_keyword.strip().rstrip("?!. ")
    kind = "question" if is_question_keyword(kw_clean) else "noun"
    intent = opts.get("intent") if opts.get("intent") in INTENTS else detect_intent(kw_clean, lang)
    pat_intent = intent if intent in ("commercial", "transactional") else "informational"
    outline = _OUTLINES[intent]
    word_target = max(1, int(opts.get("word_target") or 1500))
    n_sec = max(3, min(int(opts.get("sections") or 6), len(outline)))
    links = _clean_links(opts.get("internal_links"))
    author = opts["author"] if isinstance(opts.get("author"), dict) and opts["author"].get("name") else None
    published = opts.get("published") or None
    url = opts.get("url") or None

    subj = kw_clean if kind == "noun" else brief.topic
    base = {"audience": brief.audience, "brand": brief.brand, "offer": brief.offer or "the offer",
            "gen": "", "dat": "", "acc": "", "loc": "", "ins": ""}
    tctx = {**base, "kw": kw_clean, "Kw": cap_first(kw_clean), **_case_forms(brief, kw_clean)}
    sctx = {**tctx, "kw": subj, "Kw": cap_first(subj)}

    # defaults: title ranked by the hook score, meta fitted to 120-155 characters, never invented facts
    pats = _TITLE_PATTERNS[lang][kind]["all" if kind == "question" else pat_intent]
    title_default = _pick_title([p.format(**tctx) for p in pats if _usable(p, tctx)], lang) or _shorten(cap_first(kw_clean), 60)
    h1_default = title_default
    if hook and hook.strip():
        hook = hook.strip()
        if len(hook) <= 60 and count_keyword(hook, kw_clean, lang):
            title_default = h1_default = hook
        elif len(hook) <= 70:
            h1_default = hook
    meta_pats = _META_Q[lang] if kind == "question" else _META_PATTERNS[lang][pat_intent]
    meta_default = _fit_meta([m for m in (_resolve(p, tctx) for p in meta_pats) if m], _META_TAIL[lang])
    qs = [q for q in (_resolve(p, tctx) for p in _FAQ_PATTERNS[lang][kind]["all" if kind == "question" else pat_intent]) if q]
    n_faq = 4

    per = max(60, (word_target - 520) // n_sec)
    min_w, max_w = int(per * 0.75), int(per * 1.3)
    hint = _source_hint(brief)
    slots: list[Slot] = [
        Slot("title", f"SEO title of at most 60 characters containing the keyword '{kw_clean}'. Plain and honest: no clickbait, no ALL CAPS.",
             max_chars=60, min_chars=15, must_include=[kw_clean], kind="title", default=title_default),
        Slot("meta_description", f"Meta description of 120-155 characters containing '{kw_clean}'. Say what the reader gets; no hype.",
             max_chars=155, min_chars=120, must_include=[kw_clean], kind="line", default=meta_default),
        Slot("h1", f"Page H1: one clear headline containing '{kw_clean}', at most 70 characters.",
             max_chars=70, kind="title", default=h1_default),
        Slot("answer_lead", f"Answer-first paragraph of 40-60 words that directly answers the query '{kw_clean}' for {brief.audience}; "
             "the keyword appears in the first sentence. No filler intro.", max_words=60, min_chars=200, must_include=[kw_clean]),
        Slot("experience", f"First-party experience (required): what {brief.brand} itself saw, measured, tested or learned about "
             f"{brief.topic}. Concrete, 25-90 words, only real data supplied by the brand. Never invent numbers or customers.",
             max_words=120, min_chars=40, default=brief.facts[0].strip() if brief.facts and brief.facts[0].strip() else None),
    ]
    sec_heads: list[str] = []
    for i, (_, h_en, h_cs, instr) in enumerate(outline[:n_sec], 1):
        sec_heads.append((h_cs if lang == "cs" else h_en).format(**sctx))
        slots.append(Slot(f"sec_{i}", f"{instr.format(**sctx)} Write {min_w}-{max_w} words. Cite supplied sources only "
                          f"with the cite marker for their id (see notes); never invent facts, numbers or quotes.{hint}",
                          max_words=max_w, min_chars=min_w * 5))
    for i in range(1, n_faq + 1):
        slots.append(Slot(f"faq_q{i}", "FAQ question a real reader asks about the topic, under 100 characters.",
                          max_chars=120, kind="line", default=qs[i - 1] if i <= len(qs) else None))
        slots.append(Slot(f"faq_a{i}", f"Answer the question in faq_q{i} in 40-80 words, direct answer first, no filler. "
                          f"Cite supplied sources only with the cite marker for their id (see notes).{hint}", max_words=90, min_chars=100))
    slots += [
        Slot("conclusion", f"Conclusion of 40-80 words: the one takeaway and the next step for {brief.audience}. No new claims.",
             max_words=90, min_chars=120),
        Slot("cta", "One short call to action, at most 60 characters.", max_chars=60, kind="line",
             default=brief.cta.strip() if brief.cta and brief.cta.strip() else None),
        Slot("author_box", f"Author box: the real author's name, role and credentials, plus {brief.brand}. Only real information.",
             kind="line", default=(f"{author['name']}, {author['role']}, {brief.brand}" if author and author.get("role")
                                   else f"{author['name']}, {brief.brand}" if author else None)),
    ]

    faq_h, concl_h, src_h = tr(lang, "Frequently asked questions", "Časté dotazy"), tr(lang, "Conclusion", "Závěr"), tr(lang, "Sources", "Zdroje")
    lines = ["---", f"title: {_ph('title')}", f"description: {_ph('meta_description')}", "---", "", f"# {_ph('h1')}", ""]
    if published:
        lines += [f"*{tr(lang, 'Published', 'Publikováno')}: {format_date(published, lang)}*", ""]
    lines += [_ph("answer_lead"), "", f"> **{tr(lang, 'From our own experience:', 'Z naší vlastní zkušenosti:')}** {_ph('experience')}", ""]
    for i, h in enumerate(sec_heads, 1):
        lines += [f"## {h}", "", _ph(f"sec_{i}"), ""]
    lines += [f"## {faq_h}", ""]
    for i in range(1, n_faq + 1):
        lines += [f"### {_ph(f'faq_q{i}')}", "", _ph(f"faq_a{i}"), ""]
    lines += [f"## {concl_h}", "", _ph("conclusion"), "", f"**{_ph('cta')}**", ""]
    if links:
        lines += [f"**{tr(lang, 'Related reading:', 'Související čtení:')}**", ""] + [f"- [{l['anchor']}]({l['url']})" for l in links] + [""]
    if brief.sources:
        lines += [sources_block(brief.sources, src_h), ""]
    lines += ["---", "", f"**{tr(lang, 'About the author:', 'Autorství:')}** {_ph('author_box')}"]

    headings = sec_heads + [faq_h, concl_h] + ([src_h] if brief.sources else [])
    notes = [
        tr(lang, "Draft for a human to finish: add first-party experience, verify every fact and cut filler before publishing.",
           "Koncept, který má dokončit člověk: doplňte vlastní zkušenost, ověřte každý fakt a před zveřejněním vyřaďte vatu."),
        tr(lang, "Mass produced, low-value pages risk being treated as scaled content abuse however they are made; this skeleton only gives structure.",
           "Hromadně vyráběné stránky s nízkou hodnotou mohou být posouzeny jako zneužití škálovaného obsahu bez ohledu na to, jak vznikly; kostra dává jen strukturu."),
        tr(lang, "Cite only the supplied sources, written as [[cite:<source_id>]].",
           "Citujte jen dodané zdroje ve tvaru [[cite:<source_id>]]."),
    ]
    if intent == "navigational":
        notes.append(tr(lang, "Navigational intent: the informational outline is used as a fallback.",
                        "Navigační záměr: použita je informační osnova jako záložní varianta."))
    return Skeleton(
        format="seo_article", lang=lang, template="\n".join(lines), slots=slots, hook_slot="title", notes=notes,
        fixed={"intent": intent, "keyword_kind": kind, "headings": sec_heads, "sources": _source_entries(brief),
               "facts": list(brief.facts)},
        meta={"goal": brief.goal, "cta": brief.cta, "sponsored": brief.sponsored, "keyword": kw_clean, "lang": lang,
              "brand": brief.brand, "topic": brief.topic, "audience": brief.audience, "intent": intent,
              "word_target": word_target},
        assemble=_make_assemble(lang, brief.brand, kw_clean, headings, links, word_target, author, published, url, n_faq),
    )


# -- SEO score ---------------------------------------------------------------------------
@dataclass
class Check:
    id: str
    passed: bool
    weight: float                  # 0.0 means "not applicable": ignored by the score
    message: str


@dataclass
class SeoReport:
    score: float                   # 0..100
    checks: list[Check]
    issues: list[Issue]
    density: float | None = None   # keyword occurrences per 100 words
    penalty: float = 0.0           # points removed for keyword stuffing


_SOURCES_HEAD_RE = re.compile(r"^#{2,3}[ \t]+(?:sources|references|reference|zdroje|literatura|použité zdroje)\b.*$", re.I | re.M)
_SECTION_END_RE = re.compile(r"^(?:#{1,2}[ \t]+\S|---[ \t]*$)", re.M)


def _split_sources(body: str) -> tuple[str, str]:
    """(body without the Sources section, text of the Sources section)."""
    m = _SOURCES_HEAD_RE.search(body)
    if not m:
        return body, ""
    rest = body[m.end():]
    end = _SECTION_END_RE.search(rest)
    cut = end.start() if end else len(rest)
    return body[:m.start()] + rest[cut:], rest[:cut]


def _real(value: Any) -> str:
    """Slot text without placeholders (an unfilled slot counts as empty)."""
    text = str(value or "").strip()
    return "" if PLACEHOLDER_RE.search(text) else text


def _draft_view(draft: Draft, brief: Brief | None) -> dict[str, Any]:
    slots = draft.parts.get("slots") if isinstance(draft.parts.get("slots"), dict) else {}
    fm, body = front_matter(draft.body)
    heads = parse_headings(draft.body)
    h1s = [t for level, t in heads if level == 1]
    main, src_section = _split_sources(body)
    keyword = ((brief.primary_keyword if brief else None) or draft.meta.get("keyword") or "").strip() or None
    return {
        "lang": norm_lang(draft.lang or (brief.lang if brief else None)),
        "keyword": keyword, "heads": heads, "h1s": h1s, "body": body, "main": main, "src_section": src_section,
        "title": _real(slots.get("title")) or _real(fm.get("title")) or (h1s[0] if h1s else ""),
        "meta": _real(slots.get("meta_description")) or _real(fm.get("description")),
        "text": plain_text(main),
    }


def _issue(severity: str, code: str, message: str, where: str | None = None) -> Issue:
    return Issue(severity, code, message, where)


_SEO_CODES = {
    "title": "TITLE_INVALID", "meta_description": "META_DESCRIPTION_INVALID", "single_h1": "H1_COUNT",
    "heading_hierarchy": "HEADING_HIERARCHY", "keyword_early": "KEYWORD_NOT_EARLY", "keyword_density": "KEYWORD_DENSITY",
    "sentence_length": "LONG_SENTENCES", "internal_links": "INTERNAL_LINKS_FEW", "faq": "FAQ_MISSING",
    "sources": "SOURCES_MISSING", "word_count": "WORD_COUNT_OFF_TARGET", "unique_headings": "DUPLICATE_HEADINGS",
}


def seo_score(draft: Draft, brief: Brief | None = None) -> SeoReport:
    """Checklist score (0..100) for an SEO article draft; works on crafted drafts as well as rendered skeletons."""
    v = _draft_view(draft, brief)
    lang, kw, text = v["lang"], v["keyword"], v["text"]
    checks: list[Check] = []

    def add(cid: str, ok: bool, weight: float, en: str, cs: str) -> None:
        checks.append(Check(cid, bool(ok), weight, tr(lang, en, cs)))

    def num(x: float, nd: int = 2) -> str:
        s = f"{x:.{nd}f}"
        return s.replace(".", ",") if lang == "cs" else s

    title, meta = v["title"], v["meta"]
    t_kw = (not kw) or count_keyword(title, kw, lang) > 0
    add("title", 0 < len(title) <= 60 and t_kw, 0.10,
        f"Title length: {len(title)} characters (max 60); keyword {'present' if t_kw else 'missing'}.",
        f"Délka titulku: {len(title)} znaků (max. 60); klíčové slovo {'je přítomno' if t_kw else 'chybí'}.")
    m_kw = (not kw) or count_keyword(meta, kw, lang) > 0
    add("meta_description", 120 <= len(meta) <= 155 and m_kw, 0.08,
        f"Meta description length: {len(meta)} characters (target 120-155); keyword {'present' if m_kw else 'missing'}.",
        f"Délka meta popisu: {len(meta)} znaků (cíl 120-155); klíčové slovo {'je přítomno' if m_kw else 'chybí'}.")
    n_h1 = len(v["h1s"])
    add("single_h1", n_h1 == 1, 0.08, f"H1 headings: {n_h1} (exactly 1 expected).",
        f"Počet nadpisů H1: {n_h1} (očekává se právě 1).")
    levels = [lv for lv, _ in v["heads"]]
    clean = bool(levels) and levels[0] == 1 and all(b <= a + 1 for a, b in zip(levels, levels[1:]))
    add("heading_hierarchy", clean, 0.06,
        "Heading levels follow a clean hierarchy." if clean else "Heading levels skip a level or do not start with H1.",
        "Úrovně nadpisů na sebe správně navazují." if clean else "Úrovně nadpisů přeskakují úroveň nebo nezačínají nadpisem H1.")

    first100 = " ".join(plain_text("\n".join(l for l in v["main"].splitlines() if not re.match(r"\s*#\s", l))).split()[:100])
    density: float | None = None
    penalty = 0.0
    if kw:
        early = count_keyword(first100, kw, lang) > 0
        add("keyword_early", early, 0.08, f"Keyword in the first 100 words: {'yes' if early else 'no'}.",
            f"Klíčové slovo v prvních 100 slovech: {'ano' if early else 'ne'}.")
        hits, words, density = keyword_density(text, kw, lang)
        add("keyword_density", 0.5 <= density <= 2.5, 0.10,
            f"Keyword density: {num(density)}% (target 0.5-2.5%; above 3% is stuffing).",
            f"Hustota klíčového slova: {num(density)} % (cíl 0,5-2,5 %; nad 3 % jde o přeplňování).")
        if density > 3.0:
            penalty = min(25.0, 10.0 + (density - 3.0) * 5.0)
    else:
        add("keyword_early", True, 0.0, "No keyword known: check skipped.", "Klíčové slovo není známo: kontrola přeskočena.")
        add("keyword_density", True, 0.0, "No keyword known: check skipped.", "Klíčové slovo není známo: kontrola přeskočena.")

    avg = avg_sentence_words(v["main"])
    add("sentence_length", 0 < avg <= 22, 0.08, f"Average sentence length: {num(avg, 1)} words (max 22).",
        f"Průměrná délka věty: {num(avg, 1)} slov (max. 22).")

    provided = [l.get("url") for l in (draft.parts.get("internal_links") or []) if isinstance(l, dict) and l.get("url")]
    if provided:
        found = sum(1 for u in provided if f"]({u}" in v["body"])
        need = min(3, len(provided))
        add("internal_links", found >= need, 0.06, f"Internal links in the text: {found} of {need} required.",
            f"Interní odkazy v textu: {found} z požadovaných {need}.")
    else:
        add("internal_links", True, 0.0, "Internal links: none provided, check skipped.",
            "Interní odkazy: nebyly zadány, kontrola přeskočena.")

    faq = parse_faq(v["body"])
    add("faq", len(faq) >= 3, 0.08, f"FAQ: {len(faq)} answered questions (at least 3 expected).",
        f"FAQ: zodpovězených otázek {len(faq)} (očekávají se alespoň 3).")

    internal = set(provided)
    urls = {u for u in _URL_RE.findall(v["body"]) if u not in internal}
    items = len(re.findall(r"^\s*(?:\d{1,3}[.)]|[-*])\s+\S", v["src_section"], re.M))
    n_src = max(len(cite_ids(v["body"])), len(urls), items)
    add("sources", n_src >= 2, 0.12, f"Sources: {n_src} distinct (at least 2 expected).",
        f"Zdroje: {n_src} různých (očekávají se alespoň 2).")

    words_total = count_words(text)
    target = int(draft.parts.get("word_target") or draft.meta.get("word_target") or 1500)
    add("word_count", abs(words_total - target) <= 0.25 * target, 0.12,
        f"Word count: {words_total} (target {target} +/- 25%).", f"Počet slov: {words_total} (cíl {target} +/- 25 %).")

    norm_heads = [re.sub(r"\s+", " ", fold(t).lower()) for _, t in v["heads"]]
    dups = len(norm_heads) - len(set(norm_heads))
    add("unique_headings", dups == 0, 0.04, f"Duplicate headings: {dups}.", f"Duplicitní nadpisy: {dups}.")

    applicable = [c for c in checks if c.weight > 0]
    total_w = sum(c.weight for c in applicable)
    earned = sum(c.weight for c in applicable if c.passed)
    score = max(0.0, min(100.0, (100.0 * earned / total_w if total_w else 0.0) - penalty))

    issues: list[Issue] = []
    for c in checks:
        if c.weight > 0 and not c.passed:
            issues.append(_issue("error" if c.id == "single_h1" else "warn", _SEO_CODES[c.id], c.message))
    if density is not None and density > 3.0:
        issues.append(_issue("warn", "KEYWORD_STUFFING", tr(
            lang, f"Keyword stuffing: {num(density)}% density (above 3%). Rewrite naturally and use variations.",
            f"Přeplňování klíčovým slovem: hustota {num(density)} % (nad 3 %). Přepište přirozeněji a používejte varianty.")))
    return SeoReport(round(score, 1), checks, issues, None if density is None else round(density, 3), round(penalty, 1))


# -- quality gate ------------------------------------------------------------------------
_CLICHES = {
    "en": ("in today's fast-paced world", "in today's fast paced world", "in today's digital age", "in today's digital world",
           "in today's world", "in the ever-evolving", "in the ever evolving", "in this article we will",
           "in this article, we will", "have you ever wondered", "welcome to our blog", "when it comes to",
           "it goes without saying", "in the world of", "look no further", "in this day and age",
           "whether you're a beginner or", "let's dive in", "dive into the world of", "unlock the power of"),
    "cs": ("v dnešní rychlé době", "v dnešní uspěchané době", "v dnešní digitální době", "v dnešním světě",
           "v dnešní době", "v této době", "vítejte na našem blogu", "v tomto článku se dozvíte",
           "ať už jste začátečník", "ať už jste zkušený", "určitě jste se už někdy ptali", "není žádným tajemstvím",
           "pokud hledáte nejlepší", "ponořte se do světa", "pojďme se na to podívat"),
}


def _norm_phrase(s: str) -> str:
    return re.sub(r"\s+", " ", fold(s.lower().replace("’", "'"))).strip()


def first_party_text(draft: Draft, brief: Brief | None) -> str:
    """The first-party experience or fact text found in a draft ("" when there is none).

    Counts a filled ``experience`` slot (at least 6 words), a brief fact quoted in the body, or the text
    after the "From our own experience" label.
    """
    slots = draft.parts.get("slots") if isinstance(draft.parts.get("slots"), dict) else {}
    exp = _real(slots.get("experience"))
    if exp and count_words(exp) >= 6:
        return exp
    body = _norm_phrase(draft.body)
    facts = list(brief.facts) if brief else list(draft.parts.get("facts") or [])
    for fact in facts:
        f = _norm_phrase(str(fact))
        if len(f) >= 12 and f in body:
            return str(fact)
    m = re.search(r"(?:from our own experience|z naší vlastní zkušenosti):?\**\s*(.+)", draft.body, re.I)
    if m and not PLACEHOLDER_RE.search(m.group(1)) and count_words(m.group(1)) >= 6:
        return m.group(1).strip()
    return ""


def quality_gate(draft: Draft, brief: Brief | None = None) -> list[Issue]:
    """Anti-slop gate: refuses to call an article publishable without first-party experience or facts.

    Without a ``brief`` the gate falls back to the facts and sources stored in ``draft.parts``.
    """
    lang = norm_lang(draft.lang or (brief.lang if brief else None))
    issues: list[Issue] = []
    placeholders = PLACEHOLDER_RE.findall(draft.body)
    open_ids = list(draft.slots_open)
    if open_ids or placeholders:
        n = len(open_ids) or len(placeholders)
        names = ", ".join(open_ids[:6]) + (", ..." if len(open_ids) > 6 else "")
        issues.append(_issue("error", "SLOTS_OPEN", tr(
            lang, f"{n} slot(s) still hold [[ADD ...]] placeholders ({names}). Fill them before publishing.",
            f"Počet slotů, které stále obsahují zástupné [[ADD ...]] texty: {n} ({names}). Vyplňte je před zveřejněním."),
            (placeholders[0] if placeholders else names)[:80]))
    if not first_party_text(draft, brief):
        issues.append(_issue("error", "NOT_PUBLISHABLE_NO_EXPERIENCE", tr(
            lang, "Not publishable: the draft has no first-party experience or facts. Add what the brand itself saw, measured "
                  "or did; mass produced, low-value pages risk being treated as scaled content abuse however they are made.",
            "Nelze zveřejnit: koncept neobsahuje vlastní zkušenost ani fakta. Doplňte, co značka sama viděla, změřila nebo "
            "udělala; hromadně vyráběné stránky s nízkou hodnotou mohou být posouzeny jako zneužití škálovaného obsahu."),
            "experience"))
    sources = brief.sources if brief else (draft.parts.get("sources") or [])
    facts = brief.facts if brief else (draft.parts.get("facts") or [])
    evidence = {str(s.get("id")) for s in sources if s.get("id")} | set(cite_ids(draft.body)) | {f.strip().lower() for f in facts if f.strip()}
    if len(evidence) < 2:
        issues.append(_issue("warn", "THIN_SOURCES", tr(
            lang, f"Thin evidence: {len(evidence)} distinct source(s) or fact(s). Add at least 2 vetted sources or first-party facts.",
            f"Slabé podklady: počet různých zdrojů nebo faktů je {len(evidence)}. Přidejte alespoň 2 ověřené zdroje nebo vlastní fakta."),
            "sources"))
    intro_words = plain_text("\n".join(l for l in front_matter(draft.body)[1].splitlines() if not re.match(r"\s*#", l))).split()[:120]
    intro = " ".join(intro_words)
    folded_intro = _norm_phrase(intro)
    for phrase in _CLICHES["en"] + _CLICHES["cs"]:
        if _norm_phrase(phrase) in folded_intro:
            issues.append(_issue("warn", "GENERIC_INTRO", tr(
                lang, f"Generic opener ('{phrase}'): start with the answer or a concrete fact instead.",
                f"Obecné klišé na začátku ('{phrase}'): začněte odpovědí nebo konkrétním faktem."), intro[:80]))
            break
    issues.append(_issue("info", "HUMAN_REVIEW_REQUIRED", tr(
        lang, "A human editor must review this draft: add first-party experience, verify every claim and edit for voice before publishing.",
        "Tento koncept musí před zveřejněním zkontrolovat člověk: doplnit vlastní zkušenost, ověřit každé tvrzení a upravit styl.")))
    return issues


def validate_seo_article(draft: Draft) -> list[Issue]:
    """FormatSpec validator: SEO checklist issues plus the quality gate (from the draft alone)."""
    return seo_score(draft).issues + quality_gate(draft, None)


FORMAT_SPECS: list[FormatSpec] = [
    FormatSpec(
        id="seo_article", name_en="SEO article", name_cs="SEO článek", family="article", platform="blog",
        build=build_seo_article, validate=validate_seo_article,
        limits={"title_max": 60, "meta_min": 120, "meta_max": 155, "answer_lead_words": (40, 60), "word_target": 1500,
                "sections": 6, "faq": 4},
        description_en="Answer-first long-form article with intent based outline, FAQ, JSON-LD and a quality gate that blocks slop.",
        description_cs="Dlouhý článek s odpovědí na začátku, osnovou podle záměru, FAQ, JSON-LD a kontrolou, která blokuje vatu.",
    ),
]
