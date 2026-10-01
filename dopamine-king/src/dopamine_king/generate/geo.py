"""GEO (generative engine optimization): answer page builder, GEO score, llms.txt and robots.txt helpers.

GEO here means making honest, well structured, citable content that answer engines can quote. It never
means hidden text, prompt injection aimed at models, cloaking or fake reviews; the trust shield flags all
of those. The score weights follow the GEO research (Aggarwal et al., KDD 2024): adding citations,
quotations and statistics improved visibility in generative engine answers most, while keyword stuffing
did not help. Nothing here promises a ranking: engines change, so treat the score as a checklist.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..models import Serializable
from ..scoring import detect_lang, fold
from .seo import (
    _FAQ_PATTERNS, _FENCE_RE, _URL_RE, CITE_RE, PLACEHOLDER_RE, _case_forms, _clean_links, _make_assemble, _ph, _real,
    _resolve, _shorten, _source_entries, _source_hint, _split_sources, avg_sentence_words, cap_first, cite_ids, count_keyword,
    count_words, detect_intent, format_date, front_matter, is_question_keyword, jsonld_article, jsonld_organization,
    keyword_density, norm_lang, parse_faq, parse_headings, plain_text, quality_gate, sources_block, split_sentences, tr,
)
from .types import Brief, Draft, FormatSpec, Issue, Skeleton, Slot

_H1_PATTERNS = {
    "en": {"noun": ["{Kw}: definition, key facts and answers", "{Kw}: key facts, steps and FAQ"],
           "question": ["{Kw}? Short answer, key facts and FAQ"]},
    "cs": {"noun": ["{Kw}: definice, klíčová fakta a odpovědi", "{Kw}: klíčová fakta, postup a časté dotazy"],
           "question": ["{Kw}? Stručná odpověď, klíčová fakta a časté dotazy"]},
}
_HEADINGS = {
    "definition": ("What do we mean by {kw}?", "{Kw}: o co jde?"),
    "facts": ("What are the key facts?", "Jaká jsou klíčová fakta?"),
    "steps": ("How does it work, step by step?", "Jak to funguje krok za krokem?"),
    "compare": ("How does it compare?", "Jak se to srovnává?"),
    "stats": ("What do the numbers say?", "Co říkají čísla?"),
    "experts": ("What do experts say?", "Co říkají odborníci?"),
}
STAT_SLOTS = ("stat_1", "stat_2", "stat_3")


def _split_fact(fact: str, i: int, lang: str) -> tuple[str, str]:
    """Label and value for a key facts row; facts without a "label: value" shape get a numbered label."""
    for sep in (": ", " = ", " - "):
        if sep in fact:
            a, b = fact.split(sep, 1)
            if 0 < len(a.strip()) <= 60 and b.strip():
                return a.strip(), b.strip()
    return tr(lang, f"Fact {i}", f"Fakt {i}"), fact.strip()


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def build_geo_answer_page(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Answer page designed to be quoted by answer engines.

    options: updated (ISO date shown as "Last updated"), author ({"name","role"}), url, org_url, faq (3..6,
    default 4), quotes (1..3, default 1), fact_rows (3..8, default follows brief.facts).
    Key facts rows come only from ``brief.facts``; statistics need a cite marker; quotes are never invented.
    """
    opts = dict(options or {})
    lang = norm_lang(brief.lang)
    kw = brief.primary_keyword.strip().rstrip("?!. ")
    kind = "question" if is_question_keyword(kw) else "noun"
    intent = detect_intent(kw, lang)
    pat_intent = intent if intent in ("commercial", "transactional") else "informational"
    subj = kw if kind == "noun" else brief.topic
    n_faq = _clamp(opts.get("faq"), 3, 6, 4)
    n_quotes = _clamp(opts.get("quotes"), 1, 3, 1)
    n_rows = _clamp(opts.get("fact_rows"), 3, 8, max(3, min(len(brief.facts), 8)))
    author = opts["author"] if isinstance(opts.get("author"), dict) and opts["author"].get("name") else None
    updated = opts.get("updated") or None
    ctx = {"audience": brief.audience, "brand": brief.brand, "offer": brief.offer or "the offer", "gen": "", "dat": "",
           "acc": "", "loc": "", "ins": "", "kw": kw, "Kw": cap_first(kw), **_case_forms(brief, kw)}
    sctx = {**ctx, "kw": subj, "Kw": cap_first(subj)}
    hint = _source_hint(brief)

    h1_cands = [p.format(**ctx) for p in _H1_PATTERNS[lang][kind]]
    h1_default = next((c for c in h1_cands if len(c) <= 70), _shorten(h1_cands[0], 70))
    if hook and hook.strip() and len(hook.strip()) <= 90:
        h1_default = hook.strip()
    qs = [q for q in (_resolve(p, ctx) for p in _FAQ_PATTERNS[lang][kind]["all" if kind == "question" else pat_intent]) if q]

    slots: list[Slot] = [
        Slot("h1", f"Page H1 containing '{kw}', at most 90 characters; descriptive, not clickbait.", max_chars=90,
             kind="title", default=h1_default),
        Slot("updated", "Date of the last substantive update (ISO date, YYYY-MM-DD). Only a real date.", kind="line",
             max_chars=40, default=format_date(updated, lang) if updated else None),
        Slot("definition", f"Entity definition block of 40-80 words that answers '{kw}' directly. Sentence one reads "
             f"'X is a <category> that <does what> for {brief.audience}' and names the category; then name {brief.brand} "
             "and its role in 1-2 plain sentences. No superlatives. Use the keyword once.",
             max_words=80, min_chars=200, must_include=[kw]),
    ]
    for i in range(1, n_rows + 1):
        label, value = _split_fact(brief.facts[i - 1], i, lang) if i <= len(brief.facts) and brief.facts[i - 1].strip() else (None, None)
        slots.append(Slot(f"fact_label_{i}", "Short label of one key fact (max 40 characters). Only facts the brand supplied.",
                          max_chars=40, kind="line", default=label))
        slots.append(Slot(f"fact_value_{i}", "The value or detail for this key fact. Only facts the brand supplied; never invent.",
                          max_chars=140, kind="line", default=value))
    slots += [
        Slot("steps", f"Numbered list of 3-7 steps, one imperative sentence each, that show how {subj} works or how to do it. "
             "Only steps the brand can stand behind.", kind="list"),
        Slot("comparison_table", "Markdown table comparing the realistic options on 3-5 criteria, first column = option names. "
             f"Verifiable facts only; include {brief.brand} only where it is a fair match; no invented competitor data.", kind="text"),
    ]
    for i, sid in enumerate(STAT_SLOTS, 1):
        slots.append(Slot(sid, f"One sentence with one concrete number about {brief.topic}, ending with the cite marker of a "
                          f"vetted source (required, see notes). Never invent numbers.{hint}", max_words=45, kind="line"))
    for i in range(1, n_quotes + 1):
        slots += [
            Slot(f"quote_{i}_text", "Verbatim quotation (15-60 words) from a named expert. Use only text the user supplied; never invent quotes.",
                 max_words=70, kind="line"),
            Slot(f"quote_{i}_name", "Full name of the person quoted. Real person supplied by the user only.", max_chars=60, kind="line"),
            Slot(f"quote_{i}_credential", "Role or credential of the person quoted, with organisation.", max_chars=100, kind="line"),
        ]
    for i in range(1, n_faq + 1):
        slots.append(Slot(f"faq_q{i}", "FAQ question a real reader asks, under 100 characters.", max_chars=120, kind="line",
                          default=qs[i - 1] if i <= len(qs) else None))
        slots.append(Slot(f"faq_a{i}", f"Answer the question in faq_q{i} in 40-80 words, direct answer first. Cite supplied "
                          f"sources only with the cite marker for their id (see notes).{hint}", max_words=90, min_chars=100))
    slots.append(Slot("author_box", f"Byline: the real author's name, role or credentials and the organisation ({brief.brand}).",
                      kind="line", default=(f"{author['name']}, {author['role']}, {brief.brand}" if author and author.get("role")
                                            else f"{author['name']}, {brief.brand}" if author else None)))

    def h(key: str) -> str:
        en, cs = _HEADINGS[key]
        return (cs if lang == "cs" else en).format(**sctx)

    faq_h, src_h = tr(lang, "Frequently asked questions", "Časté dotazy"), tr(lang, "Sources", "Zdroje")
    lines = [f"# {_ph('h1')}", "", f"*{tr(lang, 'Last updated', 'Naposledy aktualizováno')}: {_ph('updated')}*", "",
             f"## {h('definition')}", "", _ph("definition"), "", f"## {h('facts')}", "",
             f"| {tr(lang, 'Fact', 'Údaj')} | {tr(lang, 'Value', 'Hodnota')} |", "|---|---|"]
    lines += [f"| {_ph(f'fact_label_{i}')} | {_ph(f'fact_value_{i}')} |" for i in range(1, n_rows + 1)]
    lines += ["", f"## {h('steps')}", "", _ph("steps"), "", f"## {h('compare')}", "", _ph("comparison_table"), "",
              f"## {h('stats')}", ""] + [f"- {_ph(s)}" for s in STAT_SLOTS] + ["", f"## {h('experts')}", ""]
    for i in range(1, n_quotes + 1):
        lines += [f'> "{_ph(f"quote_{i}_text")}"', f"> - {_ph(f'quote_{i}_name')}, {_ph(f'quote_{i}_credential')}", ""]
    lines += [f"## {faq_h}", ""]
    for i in range(1, n_faq + 1):
        lines += [f"### {_ph(f'faq_q{i}')}", "", _ph(f"faq_a{i}"), ""]
    if brief.sources:
        lines += [sources_block(brief.sources, src_h), ""]
    lines += ["---", "", f"**{tr(lang, 'Author and organisation:', 'Autor a organizace:')}** {_ph('author_box')}"]

    headings = [h("definition"), h("facts"), h("steps"), h("compare"), h("stats"), h("experts"), faq_h] + ([src_h] if brief.sources else [])
    notes = [
        tr(lang, "GEO means honest, well structured, citable content. No hidden text, no prompts aimed at models, no cloaking, no fake reviews.",
           "GEO znamená poctivý, přehledný a citovatelný obsah. Žádný skrytý text, žádné pokyny určené "
           "modelům, žádný cloaking, žádné falešné recenze."),
        tr(lang, "Statistics need a cite marker such as [[cite:<source_id>]] from the vetted sources; quotes only from user supplied material.",
           "Statistiky potřebují značku citace ve tvaru [[cite:<source_id>]] z ověřených zdrojů; citace jen z dodaného materiálu."),
        tr(lang, "Draft for a human to finish: add first-party facts, verify every number and keep the date honest.",
           "Koncept, který má dokončit člověk: doplňte vlastní fakta, ověřte každé číslo a datum uvádějte pravdivě."),
    ]
    iso_updated = str(updated)[:10] if updated and re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", str(updated)) else None
    base_assemble = _make_assemble(lang, brief.brand, kw, headings, _clean_links(opts.get("internal_links")), 0, author, None,
                                   opts.get("url") or None, n_faq)

    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        base = base_assemble(sk, values)
        definition = _real(values.get("definition"))
        desc = _shorten(plain_text(definition).replace("\n", " "), 160) if definition else None
        article = jsonld_article(values.get("h1", ""), description=desc, url=opts.get("url") or None, lang=lang, author=author,
                                 publisher=brief.brand, modified=iso_updated, keywords=[kw], article_type="Article")
        nodes = [article] + [n for n in base["json_ld"] if n.get("@type") == "FAQPage"]
        nodes.append(jsonld_organization(brief.brand, url=opts.get("org_url") or None))
        rows = [{"label": values.get(f"fact_label_{i}", ""), "value": values.get(f"fact_value_{i}", "")} for i in range(1, n_rows + 1)]
        quotes = [{"text": values.get(f"quote_{i}_text", ""), "name": values.get(f"quote_{i}_name", ""),
                   "credential": values.get(f"quote_{i}_credential", "")} for i in range(1, n_quotes + 1)]
        return {"json_ld": nodes, "outline": list(headings), "updated": values.get("updated", ""),
                "key_facts": [r for r in rows if _real(r["label"]) and _real(r["value"])],
                "quotes": [q for q in quotes if all(_real(q[k]) for k in q)],
                "stats": [values[s] for s in STAT_SLOTS if _real(values.get(s))]}

    return Skeleton(
        format="geo_answer_page", lang=lang, template="\n".join(lines), slots=slots, hook_slot="h1", notes=notes,
        fixed={"keyword_kind": kind, "intent": intent, "sources": _source_entries(brief), "facts": list(brief.facts),
               "cite_required_slots": list(STAT_SLOTS)},
        meta={"goal": brief.goal, "cta": brief.cta, "sponsored": brief.sponsored, "keyword": kw, "lang": lang,
              "brand": brief.brand, "topic": brief.topic, "audience": brief.audience},
        assemble=assemble,
    )


# -- GEO score ---------------------------------------------------------------------------
@dataclass
class GeoCheck(Serializable):
    id: str
    passed: bool
    weight: float
    message_en: str
    message_cs: str


@dataclass
class GeoReport(Serializable):
    score: float                       # 0..100
    checks: list[GeoCheck]
    tips: list[str]                    # one tip per failed check, in the report language
    penalty: float = 0.0               # points removed for keyword stuffing
    density: float | None = None       # keyword occurrences per 100 words
    lang: str = "en"
    tips_en: list[str] = field(default_factory=list)   # the same tips in both languages, whatever the report language
    tips_cs: list[str] = field(default_factory=list)


GEO_WEIGHTS = {
    "cite_sources": 0.15, "statistics": 0.15, "quotations": 0.12, "answer_first": 0.12, "structure": 0.10,
    "faq": 0.08, "entity_clarity": 0.08, "freshness": 0.06, "author_eeat": 0.06, "schema": 0.04, "readability": 0.04,
}
_TIPS = {
    "cite_sources": ("Cite at least 3 distinct vetted sources with cite markers or links; engines quote pages that show where facts come from.",
                     "Uveďte alespoň 3 různé ověřené zdroje pomocí značek citací nebo odkazů; odpovědní asistenti "
                     "citují stránky, které ukazují, odkud fakta pocházejí."),
    "statistics": ("Add at least 3 concrete numbers, each next to its citation; unsourced numbers are not trusted.",
                   "Přidejte alespoň 3 konkrétní čísla, každé vedle citace; čísla bez zdroje nikdo nebere vážně."),
    "quotations": ("Quote a named expert with a credential at least once, using only text you were given.",
                   "Citujte alespoň jednou jmenovaného odborníka s jeho kvalifikací, a to jen z podkladů, které máte."),
    "answer_first": ("Open with a direct answer of 40-80 words that contains the keyword, within the first 120 words.",
                     "Začněte přímou odpovědí o 40 až 80 slovech s klíčovým slovem, a to v prvních 120 slovech."),
    "structure": ("Use at least 2 lists or tables and phrase headings as the questions people ask.",
                  "Použijte alespoň 2 seznamy nebo tabulky a formulujte nadpisy jako otázky, které lidé kladou."),
    "faq": ("Add at least 3 question and answer pairs.", "Přidejte alespoň 3 dvojice otázky a odpovědi."),
    "entity_clarity": ("Name the brand and define the category in the first 100 words (\"Brand is a ...\") and spell the "
                       "name the same way everywhere.",
                       "V prvních 100 slovech pojmenujte značku a vymezte kategorii (\"Značka je ...\") a název pište všude stejně."),
    "freshness": ("Show a visible \"Last updated\" date.", "Zobrazte viditelné datum poslední aktualizace."),
    "author_eeat": ("Add a byline with the author's role or credentials and the organisation.",
                    "Přidejte podpis autora s jeho rolí nebo kvalifikací a názvem organizace."),
    "schema": ("Add JSON-LD structured data (Article, FAQPage, Organization).",
               "Přidejte strukturovaná data JSON-LD (Article, FAQPage, Organization)."),
    "readability": ("Shorten sentences to 22 words on average.", "Zkraťte věty na průměrně 22 slov."),
    "stuffing": ("Keyword density is above 2.5%: stuffing did not help visibility in the research, so use natural wording.",
                 "Hustota klíčového slova je nad 2,5 %: přeplňování ve výzkumu viditelnost nezlepšilo, pište přirozeně."),
}
_UPPER = "A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
_NAME = rf"[{_UPPER}][\w'’.-]*(?:\s+[{_UPPER}][\w'’.-]*)+"
_PERSON_TITLE = r"(?:(?:Dr|Prof|Ing|Mgr|MUDr|PhDr|Bc)\.?\s+)?"
_ATTR_VERBS = r"(?i:says that|says|said|explains|notes|according to|uvádí|uvedl|uvedla|řekl|řekla|říká|vysvětluje|tvrdí|dodává|podle)"
_DASHES = "-" + chr(0x2013) + chr(0x2014)          # hyphen, en dash, em dash as attribution marks
_QUOTE_RE = re.compile(r'"([^"\n]{20,500})"|“([^”\n]{20,500})”|„([^“\n]{20,500})“')
_AFTER_RE = re.compile(rf"^[\s>,.]*(?:[{_DASHES}~]+|{_ATTR_VERBS})\s*{_PERSON_TITLE}({_NAME})")
_BEFORE_RE = re.compile(rf"(?:{_ATTR_VERBS}\s+{_PERSON_TITLE}{_NAME}|{_PERSON_TITLE}{_NAME}\s+{_ATTR_VERBS})[^\"\n“„]{{0,60}}[:,]?\s*$")
_BYLINE_RE = re.compile(
    rf"(?i:by|written by|reviewed by|author and organi[sz]ation|author|autor a organizace|autorství|autorka|autor|napsal|napsala|"
    rf"recenzoval|recenzovala|about the author|o autorovi)\s*:?\**\s+{_PERSON_TITLE}({_NAME})\s*[,(]\s*([^\n,)]{{3,}})")
_LD_RE = re.compile(r"<script[^>]*ld\+json[^>]*>.*?</script>", re.S | re.I)
_NUM_RE = re.compile(r"(?<![\w/.-])(\d+(?:[.,]\d+)*)(\s?(?:%|percent\b|per cent\b|procent\w*))?", re.I)
_MONTHS_RE = ("january|february|march|april|may|june|july|august|september|october|november|december|"
              "ledna|unora|brezna|dubna|kvetna|cervna|cervence|srpna|zari|rijna|listopadu|prosince")
_FRESH_RE = re.compile(
    rf"(?:last updated|updated|published|aktualizovano|naposledy aktualizovano|publikovano|zverejneno)\s*:?\s*(?:on\s+|dne\s+)?"
    rf"(?:\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}\.\s?\d{{1,2}}\.\s?\d{{4}}|\d{{1,2}}\.?\s+(?:{_MONTHS_RE})\s+\d{{4}}|"
    rf"(?:{_MONTHS_RE})\s+\d{{1,2}},?\s+\d{{4}})")
_DEF_VERB_RE = re.compile(
    r"\b(?:is|are|provides|offers|makes|builds|helps|sells|designs|develops|specialises|specializes|je|jsou|nabizi|poskytuje|"
    r"vyrabi|pomaha|prodava|navrhuje|vyviji|specializuje se)\b")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", fold(text.lower().replace("’", "'"))).strip()


def _blocks(md: str) -> list[tuple[str, str]]:
    """(kind, text) blocks of a Markdown draft: h heading, p paragraph, l list item, t table row, q quote line."""
    _, body = front_matter(md)
    body = _FENCE_RE.sub("\n", body)
    blocks: list[tuple[str, str]] = []
    cur: list[str] = []

    def flush() -> None:
        if cur:
            blocks.append(("p", plain_text(" ".join(cur)).replace("\n", " ").strip()))
            cur.clear()

    for raw in body.splitlines():
        s = raw.strip()
        if not s or re.fullmatch(r"[-=_*]{3,}", s):
            flush()
        elif s.startswith("#"):
            flush()
            blocks.append(("h", plain_text(s).strip()))
        elif s.startswith("|"):
            flush()
            blocks.append(("t", plain_text(s).strip()))
        elif re.match(r"[-*+]\s|\d{1,3}[.)]\s", s):
            flush()
            blocks.append(("l", plain_text(s).strip()))
        elif s.startswith(">"):
            flush()
            blocks.append(("q", plain_text(s).strip()))
        else:
            cur.append(s)
    flush()
    return [(k, t) for k, t in blocks if t]


def _marker_sentences(md: str) -> list[str]:
    """Sentences of the running text with cite markers and links kept (needed to see what supports a number)."""
    _, body = front_matter(md)
    out: list[str] = []
    for raw in _FENCE_RE.sub("\n", body).splitlines():
        s = raw.strip()
        if not s or s.startswith(("#", "|")) or re.fullmatch(r"[-=_*|:\s]*", s):
            continue
        s = PLACEHOLDER_RE.sub(" ", re.sub(r"^(?:>\s*|[-*+]\s+|\d{1,3}[.)]\s+)+", "", s))
        out.extend(split_sentences(s))
    return out


def _has_source(sentence: str) -> bool:
    return bool(CITE_RE.search(sentence) or _URL_RE.search(sentence) or re.search(r"\[\d+\]", sentence))


def _has_stat(sentence: str) -> bool:
    s = re.sub(r"\[\d+\]", " ", _URL_RE.sub(" ", CITE_RE.sub(" ", sentence)))
    for m in _NUM_RE.finditer(s):
        num, pct = m.group(1), m.group(2)
        if pct:
            return True
        if re.fullmatch(r"(?:19|20)\d{2}", num):          # a year, not a statistic
            continue
        if re.search(r"\d[.,]\d", num) or int(re.sub(r"[.,]", "", num)) >= 10:
            return True
    return False


def _attributed_quotes(text: str) -> int:
    """Quotes of at least 5 words that sit next to an attributed, named person."""
    text = re.sub(r"[*_]", "", PLACEHOLDER_RE.sub(" ", text))
    n = 0
    for m in _QUOTE_RE.finditer(text):
        quote = next(g for g in m.groups() if g)
        if count_words(quote) < 5:
            continue
        after = text[m.end():m.end() + 160]
        before = text[max(0, m.start() - 140):m.start()]
        if _AFTER_RE.match(after) or _BEFORE_RE.search(before):
            n += 1
    return n


def _first_words(text: str, n: int) -> str:
    """The first n words of a text, keeping line breaks (headings and paragraphs stay separate sentences)."""
    out: list[str] = []
    count = 0
    for line in text.splitlines():
        words = line.split()[: n - count]
        if words:
            out.append(" ".join(words))
            count += len(words)
        if count >= n:
            break
    return "\n".join(out)


def _entity_ok(text: str, brand: str | None, topic: str | None, keyword: str | None, lang: str) -> bool:
    """Brand and category defined in the first 100 words, and the brand spelled one way throughout."""
    first = split_sentences(_first_words(text, 100))
    if not brand:                                    # text only: infer "X is a ..." from the opening
        m = re.search(rf"(?:^|[.!?]\s+|\n)({_NAME}|[{_UPPER}]\w+)\s+(?:is|are|je|jsou)\b", _first_words(text, 100))
        if not m:
            return False
        brand = m.group(1)
    b = re.escape(_norm(brand))
    in_brand = [i for i, s in enumerate(first) if re.search(rf"(?<!\w){b}(?!\w)", _norm(s))]
    defined = False
    for i in in_brand:
        if not _DEF_VERB_RE.search(_norm(first[i])):
            continue
        around = " ".join(first[max(0, i - 1):i + 2])
        if (not topic and not keyword) or (topic and count_keyword(around, topic, lang)) or (keyword and count_keyword(around, keyword, lang)):
            defined = True
            break
    all_ci = len(re.findall(re.escape(brand), text, re.I))
    return bool(in_brand) and defined and all_ci >= 1 and text.count(brand) == all_ci


def geo_score(draft_or_text: Draft | str, brief: Brief | None = None, *, lang: str | None = None) -> GeoReport:
    """GEO checklist score (0..100) with tips in the report language for every failed check."""
    if isinstance(draft_or_text, Draft):
        body, parts, meta, dlang = draft_or_text.body, draft_or_text.parts, draft_or_text.meta, draft_or_text.lang
    else:
        body, parts, meta, dlang = str(draft_or_text or ""), {}, {}, None
    lang = norm_lang(lang or dlang or (brief.lang if brief else None) or detect_lang(body))
    keyword = ((brief.primary_keyword if brief else None) or meta.get("keyword") or "").strip() or None
    brand = (brief.brand if brief else None) or meta.get("brand") or None
    topic = (brief.topic if brief else None) or meta.get("topic") or None
    has_markup = bool(_LD_RE.search(body))
    body = _LD_RE.sub(" ", body)                      # structured data is not page text: no sources or numbers come from it
    _, text_md = front_matter(body)
    main_md, _src = _split_sources(text_md)
    plain = plain_text(main_md)
    sents = _marker_sentences(main_md)
    blocks = _blocks(main_md)
    internal = {l.get("url") for l in (parts.get("internal_links") or []) if isinstance(l, dict)}
    checks: list[GeoCheck] = []

    def add(cid: str, ok: bool, en: str, cs: str) -> None:
        checks.append(GeoCheck(cid, bool(ok), GEO_WEIGHTS[cid], en, cs))

    # cite_sources: distinct sources by cite id (resolved to a URL when the brief knows it) or http link
    url_by_id = {s.get("id"): s.get("url") for s in (brief.sources if brief else parts.get("sources") or []) if s.get("id")}
    keys = {url_by_id.get(i) or f"id:{i}" for i in cite_ids(body)}
    keys |= {u.rstrip(".,;") for u in _URL_RE.findall(body) if u not in internal}
    add("cite_sources", len(keys) >= 3, f"Distinct sources cited: {len(keys)} (at least 3 expected).",
        f"Počet různých citovaných zdrojů: {len(keys)} (očekávají se alespoň 3).")

    supported = sum(1 for i, s in enumerate(sents)
                    if _has_stat(s) and (_has_source(s) or (i + 1 < len(sents) and _has_source(sents[i + 1]))))
    add("statistics", supported >= 3, f"Numbers backed by a citation: {supported} (at least 3 expected).",
        f"Čísla podložená citací: {supported} (očekávají se alespoň 3).")

    nq = _attributed_quotes(main_md)
    add("quotations", nq >= 1, f"Quotes with a named, attributed person: {nq} (at least 1 expected).",
        f"Citace s uvedenou jmenovanou osobou: {nq} (očekává se alespoň 1).")

    answer = False
    offset = 0
    for kind, t in blocks:
        n = count_words(t)
        if kind == "p" and 40 <= n <= 80 and offset + n <= 120 and (not keyword or count_keyword(t, keyword, lang)):
            answer = True
            break
        offset += n
        if offset > 120:
            break
    add("answer_first", answer, "Direct 40-80 word answer with the keyword within the first 120 words: " + ("yes." if answer else "no."),
        "Přímá odpověď o 40 až 80 slovech s klíčovým slovem v prvních 120 slovech: " + ("ano." if answer else "ne."))

    kinds = [k for k, _ in blocks]
    groups = 0
    for kind in ("l", "t"):
        run = 0
        for k in kinds + ["-"]:
            if k == kind:
                run += 1
            else:
                groups += 1 if run >= 2 else 0
                run = 0
    qheads = sum(1 for lv, t in parse_headings(main_md) if lv >= 2 and t.rstrip().endswith("?"))
    add("structure", groups >= 2 and qheads >= 2, f"Lists or tables: {groups}; question headings: {qheads} (at least 2 of each expected).",
        f"Seznamy nebo tabulky: {groups}; nadpisy ve formě otázky: {qheads} (očekávají se alespoň 2 od každého).")

    n_faq = len(parse_faq(main_md))
    add("faq", n_faq >= 3, f"FAQ pairs: {n_faq} (at least 3 expected).", f"Počet dvojic otázky a odpovědi: {n_faq} (očekávají se alespoň 3).")

    ent_ok = _entity_ok(plain, brand, topic, keyword, lang)
    add("entity_clarity", ent_ok, "Brand and category defined in the first 100 words with consistent naming: " + ("yes." if ent_ok else "no."),
        "Značka a kategorie vymezeny v prvních 100 slovech a název je psán jednotně: " + ("ano." if ent_ok else "ne."))

    fresh = bool(_FRESH_RE.search(_norm(body)))
    add("freshness", fresh, "Visible updated or published date: " + ("yes." if fresh else "no."),
        "Viditelné datum aktualizace nebo zveřejnění: " + ("ano." if fresh else "ne."))

    by = _BYLINE_RE.search(text_md)
    eeat = False
    if by:
        line_end = text_md.find("\n", by.end())
        line = text_md[text_md.rfind("\n", 0, by.start()) + 1:len(text_md) if line_end == -1 else line_end]
        eeat = (not brand) or bool(re.search(re.escape(_norm(brand)), _norm(line)))
    add("author_eeat", eeat, "Byline with role or credentials and organisation: " + ("yes." if eeat else "no."),
        "Podpis autora s rolí nebo kvalifikací a organizací: " + ("ano." if eeat else "ne."))

    schema = bool(parts.get("json_ld")) or has_markup
    add("schema", schema, "JSON-LD structured data present: " + ("yes." if schema else "no."),
        "Strukturovaná data JSON-LD jsou přítomna: " + ("ano." if schema else "ne."))

    avg = avg_sentence_words(main_md)
    add("readability", 0 < avg <= 22, f"Average sentence length: {avg:.1f} words (max 22).",
        f"Průměrná délka věty: {str(round(avg, 1)).replace('.', ',')} slov (max. 22).")

    density: float | None = None
    penalty = 0.0
    if keyword and not PLACEHOLDER_RE.search(body) and not (isinstance(draft_or_text, Draft) and draft_or_text.slots_open):
        _, n_words, measured = keyword_density(plain, keyword, lang)
        if n_words >= 100:                              # density is only judged on complete text of a useful length
            density = measured
            if density > 2.5:
                penalty = min(25.0, (density - 2.5) * 10.0)
    earned = sum(c.weight for c in checks if c.passed)
    score = max(0.0, min(100.0, 100.0 * earned - penalty))
    failed = [c.id for c in checks if not c.passed] + (["stuffing"] if penalty else [])
    tips_en, tips_cs = [_TIPS[cid][0] for cid in failed], [_TIPS[cid][1] for cid in failed]
    return GeoReport(round(score, 1), checks, tips_cs if lang == "cs" else tips_en, round(penalty, 1),
                     None if density is None else round(density, 3), lang, tips_en, tips_cs)


# -- llms.txt and robots.txt -------------------------------------------------------------
def _one_line(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _llms_item(page: dict[str, Any]) -> str | None:
    url = _one_line(page.get("url"))
    if not url:
        return None
    title = _one_line(page.get("title")) or url
    title = title.replace("[", "(").replace("]", ")")
    note = _one_line(page.get("note"))
    return f"- [{title}]({url})" + (f": {note}" if note else "")


def llms_txt(brand: str, summary: str, pages: Sequence[dict[str, Any]], optional: Sequence[dict[str, Any]] | None = None) -> str:
    """Build an ``/llms.txt`` file following the llmstxt.org proposal.

    Layout: an H1 with the name, a blockquote summary, then H2 sections with ``- [title](url): note`` lists
    (pages can carry a ``section`` key; the default section is "Key pages"). Items under "Optional" may be
    skipped by a reader that is short on context. This is a community proposal and adoption by answer
    engines is unconfirmed: treat the file as cheap, harmless documentation for models, not a ranking lever.
    """
    lines = [f"# {_one_line(brand)}", ""]
    if _one_line(summary):
        lines += [f"> {_one_line(summary)}", ""]
    sections: dict[str, list[str]] = {}
    for page in pages:
        item = _llms_item(page)
        if item:
            sections.setdefault(_one_line(page.get("section")) or "Key pages", []).append(item)
    for name, items in sections.items():
        lines += [f"## {name}", ""] + items + [""]
    extra = [i for i in (_llms_item(p) for p in optional or []) if i]
    if extra:
        lines += ["## Optional", ""] + extra + [""]
    return "\n".join(lines).rstrip() + "\n"


AI_AGENTS: tuple[tuple[str, str, str], ...] = (
    # (user agent token, vendor, role): training = model training, search = answer engine index, user = fetch on a user's request
    ("GPTBot", "OpenAI", "training"), ("OAI-SearchBot", "OpenAI", "search"), ("ChatGPT-User", "OpenAI", "user"),
    ("ClaudeBot", "Anthropic", "training"), ("Claude-SearchBot", "Anthropic", "search"), ("Claude-User", "Anthropic", "user"),
    ("PerplexityBot", "Perplexity", "search"), ("Perplexity-User", "Perplexity", "user"),
    ("Google-Extended", "Google", "training"), ("Applebot-Extended", "Apple", "training"),
    ("CCBot", "Common Crawl", "training"), ("Bytespider", "ByteDance", "training"),
    ("Amazonbot", "Amazon", "training"), ("meta-externalagent", "Meta", "training"),
)
ROBOTS_POLICIES = ("allow_all", "block_all", "allow_search_block_training")


def robots_ai_snippet(policy: str = "allow_search_block_training", extra_agents: Sequence[str] | None = None) -> str:
    """robots.txt block for known AI crawlers.

    Policies: ``allow_all``, ``block_all`` and ``allow_search_block_training`` (allow the search and
    user-action agents, block the training agents). ``extra_agents`` are handled like training crawlers.
    Agent names and behaviour change: verify each entry against the vendor's current documentation, and
    remember that robots.txt is advisory (a crawler that ignores it is not technically stopped).
    """
    if policy not in ROBOTS_POLICIES:
        raise ValueError(f"unknown policy {policy!r}; expected one of {ROBOTS_POLICIES}")
    extra = []
    for name in extra_agents or []:
        if not re.fullmatch(r"[A-Za-z0-9._-]+", str(name)):
            raise ValueError(f"invalid user agent token {name!r}")
        extra.append(str(name))
    training = [a for a, _, role in AI_AGENTS if role == "training"] + extra
    allowed = [a for a, _, role in AI_AGENTS if role != "training"]
    lines = [
        f"# AI crawler policy: {policy}",
        "# Verify every user agent against each vendor's current documentation before deploying; names and behaviour change.",
        "# robots.txt is advisory: it asks crawlers to behave, it does not technically stop one that ignores it.",
        "# Google-Extended and Applebot-Extended are control tokens for AI training use, not separate crawlers;",
        "# blocking them is not meant to affect ordinary search indexing (check the vendors' notes).",
        "",
    ]

    def group(title: str, agents: list[str], rule: str) -> None:
        lines.extend([f"# {title}"] + [f"User-agent: {a}" for a in agents] + [rule, ""])

    if policy == "allow_all":
        group("All AI agents: allowed", training + allowed, "Allow: /")
    elif policy == "block_all":
        group("All AI agents: blocked", training + allowed, "Disallow: /")
    else:
        group("Training crawlers: blocked", training, "Disallow: /")
        group("Search and user-action agents: allowed", allowed, "Allow: /")
    return "\n".join(lines).rstrip() + "\n"


# -- validator and registry --------------------------------------------------------------
def validate_geo_page(draft: Draft) -> list[Issue]:
    """Statistics need a known cite marker, quotes a named source; plus failed GEO checks and the SEO quality gate.

    The gate means a page with open slots or no first-party facts is never called publishable.
    """
    lang = norm_lang(draft.lang)
    slots = draft.parts.get("slots") if isinstance(draft.parts.get("slots"), dict) else {}
    known = {str(s.get("id")) for s in draft.parts.get("sources") or [] if s.get("id")}
    issues: list[Issue] = []
    for sid in draft.parts.get("cite_required_slots") or STAT_SLOTS:
        text = _real(slots.get(sid))
        if not text:
            continue
        ids = cite_ids(text)
        if not ids:
            issues.append(Issue("error", "STAT_NEEDS_CITATION", tr(
                lang, f"Statistic slot {sid} has no cite marker; every number needs a vetted source.",
                f"Statistika ve slotu {sid} nemá značku citace; každé číslo potřebuje ověřený zdroj."), text[:80]))
        for cid in ids:
            if known and cid not in known:
                issues.append(Issue("error", "CITATION_UNKNOWN", tr(
                    lang, f"Citation {cid} is not one of the vetted sources.", f"Citace {cid} není mezi ověřenými zdroji."),
                    f"[[cite:{cid}]]"))
    for i in range(1, 4):
        if f"quote_{i}_text" not in slots or not _real(slots.get(f"quote_{i}_text")):
            continue
        if not (_real(slots.get(f"quote_{i}_name")) and _real(slots.get(f"quote_{i}_credential"))):
            issues.append(Issue("error", "QUOTE_NOT_ATTRIBUTED", tr(
                lang, f"Quote {i} needs the person's full name and credential.",
                f"Citace {i} potřebuje celé jméno osoby a její kvalifikaci."), _real(slots.get(f"quote_{i}_text"))[:80]))
    for c in geo_score(draft).checks:
        if not c.passed:
            issues.append(Issue("warn", f"GEO_{c.id.upper()}", c.message_cs if lang == "cs" else c.message_en))
    return issues + quality_gate(draft, None)


FORMAT_SPECS: list[FormatSpec] = [
    FormatSpec(
        id="geo_answer_page", name_en="GEO answer page", name_cs="GEO odpovědní stránka", family="article", platform="blog",
        build=build_geo_answer_page, validate=validate_geo_page,
        limits={"definition_words": (40, 80), "stats": 3, "faq": 4, "quotes": 1},
        description_en="Page structured to be quoted by answer engines: definition, key facts, cited statistics, expert quotes, FAQ and JSON-LD.",
        description_cs="Stránka postavená tak, aby ji odpovědní asistenti mohli citovat: definice, klíčová fakta, "
                       "citované statistiky, citace expertů, FAQ a JSON-LD.",
    ),
]
