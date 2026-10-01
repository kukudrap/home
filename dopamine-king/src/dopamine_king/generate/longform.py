"""Long-form formats: press release, landing page, newsletter and email sequence.

Same integrity rules as the article builders: offline output never invents facts, customers, quotes,
testimonials or numbers. Anything that needs real content has no default and shows ``[[ADD: ...]]``.
Validators only report on filled values; unfilled slots are the job of the quality gate and the trust shield.
"""
from __future__ import annotations

import re
from typing import Any

from ..scoring import fold
from .seo import (
    CITE_RE, PLACEHOLDER_RE, _URL_RE, _ph, _real, count_words, format_date, front_matter, norm_lang,
    parse_headings, plain_text, split_sentences, tr,
)
from .types import Brief, Draft, FormatSpec, Issue, Skeleton, Slot

_BUTTON_RE = re.compile(r"\*\*\[(.+?)\]\(([^)]*)\)\*\*")               # a CTA rendered as a bold link
_SUBJECT_RE = re.compile(r"^(?:Subject|Předmět):[ \t]*(.*)$", re.M)
_PREHEADER_RE = re.compile(r"^Preheader:[ \t]*(.*)$", re.M)
_UNSUB_RE = re.compile(r"unsubscribe|opt out|odhlasit|odhlaseni|zrusit odber|zruseni odberu|zrusit prihlaseni")
_DECEPTIVE_SUBJECT_RE = re.compile(r"^\s*(?:re|fw|fwd|aw|odp|vs)\s*:", re.I)


def _slots(draft: Draft) -> dict[str, str]:
    value = draft.parts.get("slots")
    return value if isinstance(value, dict) else {}


def _clamp(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _section_text(body: str, pattern: str) -> str:
    """Text under the first heading matching ``pattern`` (until the next heading, rule or ### end mark)."""
    m = re.search(rf"^#{{1,3}}[ \t]+(?:{pattern})[^\n]*$", body, re.I | re.M)
    if not m:
        return ""
    rest = body[m.end():]
    end = re.search(r"^(?:#{1,3}[ \t]+\S|###[ \t]*$|---[ \t]*$)", rest, re.M)
    return rest[: end.start() if end else len(rest)].strip()


def _lang_of(draft: Draft) -> str:
    return norm_lang(draft.lang)


def _cta_buttons(body: str) -> list[str]:
    return [m.group(1).strip() for m in _BUTTON_RE.finditer(body)]


def _short(text: str, n: int = 80) -> str:
    return re.sub(r"\s+", " ", text).strip()[:n]


# Superlatives that need substantiation (a number, a link or a cite marker nearby). Matched on folded text.
_SUPERLATIVES = (
    "best", "leading", "revolutionary", "world-class", "world class", "unique", "world's first", "first-ever", "first ever",
    "the first to", "fastest", "most innovative", "cutting-edge", "cutting edge", "groundbreaking", "game-changing",
    "game changing", "unrivaled", "unrivalled", "unparalleled", "number one", "industry-leading", "state-of-the-art",
    "market leader", "best-in-class", "ultimate", "most advanced", "no. 1",
    "nejlepsi", "predni", "revolucni", "unikatni", "jedinecny", "prvni na svete", "prvni na trhu", "nejrychlejsi",
    "nejinovativnejsi", "spickovy", "prulomovy", "bezkonkurencni", "cislo jedna", "svetova trida", "lidr trhu",
    "nejuspesnejsi", "nejmodernejsi", "nejpokrocilejsi",
)


def unsubstantiated_superlatives(text: str) -> list[str]:
    """Superlative claims with no number, link or cite marker in the same or the next sentence."""
    sents = split_sentences(PLACEHOLDER_RE.sub(" ", text or ""))
    found: list[str] = []
    for i, s in enumerate(sents):
        folded = " " + re.sub(r"[^a-z0-9.' -]+", " ", fold(s.lower().replace("’", "'"))) + " "
        hit = next((w for w in _SUPERLATIVES if re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", folded)), None)
        if not hit:
            continue
        window = s + " " + (sents[i + 1] if i + 1 < len(sents) else "")
        if not (CITE_RE.search(window) or _URL_RE.search(window) or re.search(r"\d", window)):
            found.append(hit)
    return found


# -- press release -----------------------------------------------------------------------
def build_press_release(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Press release: headline, subhead, dateline, 5W lead, body, quotes (never invented), boilerplate, contact, ###.

    options: city and date (ISO) build the dateline default, quotes (1..2, default 1).
    """
    opts = dict(options or {})
    lang = norm_lang(brief.lang)
    n_quotes = _clamp(opts.get("quotes"), 1, 2, 1)
    city = str(opts.get("city") or "").strip()
    dateline = None
    if city and opts.get("date"):
        dateline = f"{city.upper() if lang == 'en' else city}, {format_date(opts['date'], lang)}"
    news = f" The news is about: {brief.offer}." if brief.offer else ""
    headline_default = hook.strip() if hook and 0 < len(hook.strip()) <= 100 else None

    slots = [
        Slot("headline", f"News headline of at most 100 characters: a verb, the news and {brief.brand}. Factual, no hype.",
             max_chars=100, kind="title", default=headline_default),
        Slot("subhead", "One supporting sentence (max 25 words) that adds the most important detail the headline left out.",
             max_words=25, kind="line"),
        Slot("dateline", "Dateline: city and date of the announcement. Real values only.", max_chars=60, kind="line", default=dateline),
        Slot("lead", f"Lead paragraph of at most 60 words answering who ({brief.brand}), what, when, where and why in the first "
             f"sentences. Lead with the news, not the company history.{news}", max_words=60, min_chars=120),
        Slot("body_1", "Key details: what is new, how it works, availability. Short paragraph, supplied facts only.", max_words=120),
        Slot("body_2", f"Context: the problem this solves for {brief.audience}, backed only by supplied facts or vetted sources.",
             max_words=120),
    ]
    for i in range(1, n_quotes + 1):
        slots += [
            Slot(f"quote_{i}_text", "Quote (15-50 words) from a named spokesperson. Use only words the user supplied; never invent quotes.",
                 max_words=60, kind="line"),
            Slot(f"quote_{i}_name", "Full name of the person quoted. Real person only.", max_chars=60, kind="line"),
            Slot(f"quote_{i}_title", f"Role of the person quoted at {brief.brand}.", max_chars=80, kind="line"),
        ]
    slots += [
        Slot("body_3", "Availability and next steps: where and when readers can get it and how to learn more. Supplied facts only.",
             max_words=100),
        Slot("boilerplate", f"Two or three sentences describing {brief.brand}: what it does and for whom. Real facts only.",
             max_words=70, default=brief.brand),
        Slot("media_contact", "Media contact: name, role, email and phone of a real person. Never invent contact details.", kind="line"),
    ]
    quotes = []
    for i in range(1, n_quotes + 1):
        q, n, t = _ph(f"quote_{i}_text"), _ph(f"quote_{i}_name"), _ph(f"quote_{i}_title")
        quotes.append(f'"{q}," said {n}, {t}.' if lang == "en" else f'"{q}", uvádí {n}, {t}.')
    lines = [tr(lang, "FOR IMMEDIATE RELEASE", "TISKOVÁ ZPRÁVA"), "", f"# {_ph('headline')}", "", f"*{_ph('subhead')}*", "",
             f"{_ph('dateline')} - {_ph('lead')}", "", _ph("body_1"), "", _ph("body_2"), ""]
    lines += [quotes[0], "", _ph("body_3"), ""] + [f"{q}\n" for q in quotes[1:]]
    lines += [f"## {tr(lang, 'About', 'O značce')} {brief.brand}", "", _ph("boilerplate"), "",
              f"## {tr(lang, 'Media contact', 'Kontakt pro média')}", "", _ph("media_contact"), "", "###"]
    return Skeleton(
        format="press_release", lang=lang, template="\n".join(lines), slots=slots, hook_slot="headline",
        notes=[tr(lang, "Quotes, contact details and the boilerplate must come from real people and facts; nothing is generated here.",
                  "Citace, kontakty a medailonek firmy musí pocházet od skutečných lidí a z ověřených faktů; nic se zde negeneruje."),
               tr(lang, "Inverted pyramid: the most important news first, details later, boilerplate last.",
                  "Obrácená pyramida: nejdůležitější zpráva první, podrobnosti později, medailonek firmy nakonec.")],
        fixed={"end_mark": "###"},
        meta={"goal": brief.goal, "cta": brief.cta, "sponsored": brief.sponsored, "keyword": brief.primary_keyword,
              "lang": lang, "brand": brief.brand, "topic": brief.topic, "offer": brief.offer},
    )


_DATE_CUE_RE = re.compile(
    r"\b(?:\d{4}|today|tonight|tomorrow|yesterday|this (?:week|month|year)|monday|tuesday|wednesday|thursday|friday|"
    r"january|february|march|april|may|june|july|august|september|october|november|december|dnes|zítra|včera|"
    r"tento týden|tento měsíc|letos|ledna|února|března|dubna|května|června|července|srpna|září|října|listopadu|prosince)\b", re.I)
_WHY_CUE_RE = re.compile(
    r"\b(?:to|so that|because|in order to|designed to|helps?|aims? to|aby|protože|cílem|navržen\w*|pomáhá|umožňuje|abychom)\b", re.I)


def validate_press_release(draft: Draft) -> list[Issue]:
    lang = _lang_of(draft)
    slots = _slots(draft)
    fm, body = front_matter(draft.body)
    issues: list[Issue] = []
    heads = parse_headings(body)
    h1_lines = [t for lv, t in heads if lv == 1]
    headline = _real(slots.get("headline")) or _real(h1_lines[0] if h1_lines else "")
    if not headline and not h1_lines:
        issues.append(Issue("error", "PR_HEADLINE_MISSING", tr(lang, "The press release has no headline.", "Tisková zpráva nemá titulek.")))
    elif len(headline) > 100:
        issues.append(Issue("warn", "PR_HEADLINE_LENGTH", tr(
            lang, f"Headline is {len(headline)} characters; keep it at 100 or fewer.",
            f"Titulek má {len(headline)} znaků; držte se nejvýše 100."), _short(headline)))
    subhead = _real(slots.get("subhead")) or _real(next(iter(re.findall(r"^\*([^*\n]+)\*\s*$", body, re.M)), ""))
    if not subhead and "subhead" not in slots:
        issues.append(Issue("warn", "PR_SUBHEAD_MISSING", tr(lang, "Add a one-sentence subhead under the headline.",
                                                             "Přidejte pod titulek podtitulek o jedné větě.")))
    lead_para = ""
    for para in re.split(r"\n\s*\n", body):
        text = para.strip()
        if text and not text.startswith(("#", "*", "FOR IMMEDIATE", "TISKOVÁ")) and count_words(text) >= 10:
            lead_para = text
            break
    dateline = _real(slots.get("dateline"))
    lead = _real(slots.get("lead")) or (lead_para.split(" - ", 1)[1] if " - " in lead_para[:90] else lead_para)
    lead = "" if PLACEHOLDER_RE.search(lead) else lead
    if not dateline and not (" - " in lead_para[:90] and "," in lead_para.split(" - ", 1)[0]) and "dateline" not in slots:
        issues.append(Issue("warn", "PR_DATELINE_MISSING", tr(lang, "Start the lead with a dateline (city and date).",
                                                              "Začněte perex datovou linkou (město a datum).")))
    if lead:
        n = count_words(lead)
        if n > 60:
            issues.append(Issue("warn", "PR_LEAD_TOO_LONG", tr(lang, f"Lead is {n} words; keep it to 60 or fewer.",
                                                              f"Perex má {n} slov; držte se nejvýše 60."), _short(lead)))
        missing = []
        brand = str(draft.meta.get("brand") or "")
        if brand and brand.lower() not in lead.lower():
            missing.append(tr(lang, "who", "kdo"))
        if not (dateline or _DATE_CUE_RE.search(lead_para[:200])):
            missing.append(tr(lang, "when", "kdy"))
        if not (dateline or re.search(r"\b(?:in|at|v|ve|na)\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]", lead)):
            missing.append(tr(lang, "where", "kde"))
        if not _WHY_CUE_RE.search(lead):
            missing.append(tr(lang, "why", "proč"))
        if missing:
            issues.append(Issue("info", "PR_LEAD_5W", tr(
                lang, "The lead may not answer all of who, what, when, where and why. Check: " + ", ".join(missing) + ".",
                "Perex možná neodpovídá na všechny otázky kdo, co, kdy, kde a proč. Zkontrolujte: " + ", ".join(missing) + "."), _short(lead)))
    long_paras = [p for p in re.split(r"\n\s*\n", body) if count_words(plain_text(p)) > 120]
    if long_paras:
        issues.append(Issue("info", "PR_LONG_PARAGRAPH", tr(
            lang, "A paragraph is over 120 words; keep paragraphs short and put details after the lead (inverted pyramid).",
            "Odstavec má přes 120 slov; držte odstavce krátké a podrobnosti dávejte až za perex (obrácená pyramida)."), _short(long_paras[0])))
    if not (_real(slots.get("quote_1_text")) or re.search(r'"[^"\n]{20,}"[^\n]{0,20}(?:said|uvádí|uvedl|řekl)', body)) and "quote_1_text" not in slots:
        issues.append(Issue("warn", "PR_QUOTE_MISSING", tr(lang, "Add at least one quote from a named spokesperson.",
                                                         "Přidejte alespoň jednu citaci jmenovaného mluvčího.")))
    for i in (1, 2):
        if _real(slots.get(f"quote_{i}_text")) and not (_real(slots.get(f"quote_{i}_name")) and _real(slots.get(f"quote_{i}_title"))):
            issues.append(Issue("error", "PR_QUOTE_UNATTRIBUTED", tr(
                lang, f"Quote {i} needs the speaker's full name and role.", f"Citace {i} potřebuje celé jméno a roli řečníka."),
                _short(slots[f"quote_{i}_text"])))
    boiler = _real(slots.get("boilerplate")) or _section_text(body, r"about|o značce|o společnosti|o firmě")
    if boiler and count_words(boiler) <= 3:
        issues.append(Issue("warn", "PR_BOILERPLATE_BRAND_ONLY", tr(
            lang, "The boilerplate is only the brand name; add two or three factual sentences about the company.",
            "Medailonek obsahuje jen název značky; přidejte dvě až tři věcné věty o firmě."), _short(boiler)))
    contact = _real(slots.get("media_contact")) or _section_text(body, r"media contact|press contact|kontakt pro média")
    if not contact and "media_contact" not in slots:
        issues.append(Issue("warn", "PR_MEDIA_CONTACT_MISSING", tr(lang, "Add a media contact.", "Přidejte kontakt pro média.")))
    tail = [l.strip() for l in body.strip().splitlines() if l.strip()]
    if not tail or tail[-1] not in ("###", "-30-", "- 30 -"):
        issues.append(Issue("warn", "PR_END_MARK_MISSING", tr(lang, "End the release with the ### end mark.",
                                                            "Ukončete zprávu značkou ###.")))
    for word in dict.fromkeys(unsubstantiated_superlatives(plain_text(body))):
        issues.append(Issue("warn", "PR_UNSUBSTANTIATED_SUPERLATIVE", tr(
            lang, f"Superlative '{word}' without a number, source or cite marker nearby; substantiate or remove it.",
            f"Superlativ '{word}' bez čísla, zdroje nebo značky citace poblíž; doložte ho, nebo ho vypusťte."), word))
    return issues


# -- landing page ------------------------------------------------------------------------
_LANDING_FAQ = {
    "en": ["Is this right for {audience}?", "How much does it cost?", "What if it is not right for me?"],
    "cs": ["Hodí se to pro mě?", "Kolik to stojí?", "Co když mi to nebude vyhovovat?"],
}
_LANDING_HEADS = {
    "problem": ("The problem", "Problém"), "solution": ("The solution", "Řešení"), "benefits": ("What you get", "Co získáte"),
    "proof": ("Proof", "Důkazy"), "faq": ("Questions you may have", "Na co se lidé ptají"), "final": ("Ready to start?", "Chcete začít?"),
}


def build_landing_page(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Landing page: hero, problem, solution, 3 benefit blocks, proof (never invented), objections FAQ, final CTA.

    One primary CTA slot (``cta``, default ``brief.cta``) is rendered in the hero and again at the end, so the
    call to action is consistent by construction. options: cta_url (default "#cta").
    """
    opts = dict(options or {})
    lang = norm_lang(brief.lang)
    cta_url = str(opts.get("cta_url") or "#cta")
    core = (brief.offer or brief.primary_keyword).strip()
    meta_title = next((c for c in (f"{core} | {brief.brand}", core) if len(c) <= 60), None)
    hero_default = hook.strip() if hook and 0 < len(hook.split()) <= 12 else None
    slots = [
        Slot("meta_title", "Page title of at most 60 characters: what it is and who it is from.", max_chars=60, kind="title", default=meta_title),
        Slot("meta_description", "Meta description of 120-155 characters: the offer and its main benefit. No hype.", max_chars=155, min_chars=120, kind="line"),
        Slot("hero_headline", f"Hero headline of at most 12 words stating the main benefit for {brief.audience}. Clear beats clever.",
             max_words=12, kind="title", default=hero_default),
        Slot("hero_subhead", "One or two sentences (max 30 words) saying what it is and who it is for.", max_words=30),
        Slot("cta", "Primary call to action as button text, 2-5 words. The same text is used in the hero and at the end.",
             max_chars=40, kind="line", default=brief.cta.strip() if brief.cta and brief.cta.strip() else None),
        Slot("problem", f"The problem {brief.audience} face, in their own terms (40-80 words). Real, specific, no fear mongering.", max_words=90, min_chars=150),
        Slot("solution", f"How {brief.offer or brief.brand} solves it (40-80 words). Concrete mechanism, supplied facts only.", max_words=90, min_chars=150),
    ]
    for i in (1, 2, 3):
        slots.append(Slot(f"benefit_{i}_title", f"Benefit {i} title: an outcome for the reader, max 8 words.", max_words=8, kind="line"))
        slots.append(Slot(f"benefit_{i}_body", f"Benefit {i} body (20-40 words): how the benefit comes about. Supplied facts only.", max_words=45, min_chars=80))
    slots += [
        Slot("proof_stat_1", "Proof number: one real first-party result or a cited statistic (use the cite marker). Never invent numbers.", max_words=35, kind="line"),
        Slot("proof_stat_2", "Second proof number, same rules. Leave nothing invented.", max_words=35, kind="line"),
        Slot("testimonial_quote", "Real customer testimonial, verbatim, supplied by the user. Never invent testimonials.", max_words=60, kind="line"),
        Slot("testimonial_name", "Name and role of the person giving the testimonial, as supplied by the user.", max_chars=80, kind="line"),
    ]
    for i, q in enumerate(_LANDING_FAQ[lang], 1):
        slots.append(Slot(f"faq_q{i}", "Objection phrased as a question, in the reader's words.", max_chars=100, kind="line",
                          default=q.format(audience=brief.audience)))
        slots.append(Slot(f"faq_a{i}", f"Answer to the question in faq_q{i} in 30-60 words. Honest, supplied facts only.", max_words=70, min_chars=80))
    slots.append(Slot("final_cta_text", "One sentence (max 20 words) that restates the benefit and invites the click.", max_words=20, kind="line"))

    def hd(key: str) -> str:
        return tr(lang, *_LANDING_HEADS[key])

    button = f"**[{_ph('cta')}]({cta_url})**"
    lines = ["---", f"title: {_ph('meta_title')}", f"description: {_ph('meta_description')}", "---", "", f"# {_ph('hero_headline')}", "",
             _ph("hero_subhead"), "", button, "", f"## {hd('problem')}", "", _ph("problem"), "", f"## {hd('solution')}", "", _ph("solution"), "",
             f"## {hd('benefits')}", ""]
    for i in (1, 2, 3):
        lines += [f"### {_ph(f'benefit_{i}_title')}", "", _ph(f"benefit_{i}_body"), ""]
    lines += [f"## {hd('proof')}", "", f"- {_ph('proof_stat_1')}", f"- {_ph('proof_stat_2')}", "",
              f'> "{_ph("testimonial_quote")}"', f"> - {_ph('testimonial_name')}", "", f"## {hd('faq')}", ""]
    for i in (1, 2, 3):
        lines += [f"### {_ph(f'faq_q{i}')}", "", _ph(f"faq_a{i}"), ""]
    lines += [f"## {hd('final')}", "", _ph("final_cta_text"), "", button]
    return Skeleton(
        format="landing_page", lang=lang, template="\n".join(lines), slots=slots, hook_slot="hero_headline",
        notes=[tr(lang, "Proof must be real: first-party numbers, cited statistics and verbatim testimonials supplied by the user.",
                  "Důkazy musí být skutečné: vlastní čísla, citované statistiky a doslovné reference dodané uživatelem."),
               tr(lang, "One primary CTA, repeated; set the real button URL when publishing.",
                  "Jedna hlavní výzva k akci, opakovaná; při zveřejnění nastavte skutečnou adresu tlačítka.")],
        fixed={"cta_url": cta_url},
        meta={"goal": brief.goal, "cta": brief.cta, "sponsored": brief.sponsored, "keyword": brief.primary_keyword,
              "lang": lang, "brand": brief.brand, "topic": brief.topic, "offer": brief.offer},
    )


def validate_landing_page(draft: Draft) -> list[Issue]:
    lang = _lang_of(draft)
    slots = _slots(draft)
    fm, body = front_matter(draft.body)
    issues: list[Issue] = []
    headline = _real(slots.get("hero_headline")) or _real(next((t for lv, t in parse_headings(body) if lv == 1), ""))
    if headline and count_words(headline) > 12:
        issues.append(Issue("warn", "LANDING_HEADLINE_LONG", tr(
            lang, f"Hero headline has {count_words(headline)} words; keep it to 12 or fewer.",
            f"Hlavní titulek má {count_words(headline)} slov; držte se nejvýše 12."), _short(headline)))
    buttons = [b for b in _cta_buttons(body)]
    real_buttons = [b for b in buttons if not PLACEHOLDER_RE.search(b)]
    if not buttons:
        issues.append(Issue("error", "LANDING_CTA_MISSING", tr(lang, "The page has no call to action button.",
                                                              "Stránka nemá tlačítko s výzvou k akci.")))
    else:
        if len({b.lower() for b in real_buttons}) > 1:
            issues.append(Issue("warn", "LANDING_CTA_INCONSISTENT", tr(
                lang, "The page uses different CTA texts; keep one primary CTA and repeat it.",
                "Stránka používá různé texty výzev; ponechte jednu hlavní výzvu a opakujte ji."), _short(" / ".join(real_buttons))))
        if len(buttons) < 2:
            issues.append(Issue("warn", "LANDING_CTA_NOT_REPEATED", tr(
                lang, "Repeat the primary CTA at the end of the page.", "Zopakujte hlavní výzvu k akci na konci stránky.")))
    proof_keys = ("proof_stat_1", "proof_stat_2", "testimonial_quote")
    if any(k in slots for k in proof_keys):
        has_proof = any(_real(slots.get(k)) for k in proof_keys)
    else:
        sec = _section_text(body, r"proof|evidence|results|testimonials|důkazy|výsledky|reference|reálné výsledky")
        has_proof = count_words(sec) >= 5 and not PLACEHOLDER_RE.search(sec)
    if not has_proof:
        issues.append(Issue("warn", "LANDING_NO_PROOF", tr(
            lang, "No proof yet: add a real first-party number, a cited statistic or a verbatim testimonial.",
            "Zatím chybí důkaz: doplňte skutečné vlastní číslo, citovanou statistiku nebo doslovnou referenci.")))
    title = _real(slots.get("meta_title")) or _real(fm.get("title"))
    if title and len(title) > 60:
        issues.append(Issue("warn", "LANDING_META_TITLE_LENGTH", tr(
            lang, f"Page title is {len(title)} characters; keep it at 60 or fewer.",
            f"Titulek stránky má {len(title)} znaků; držte se nejvýše 60."), _short(title)))
    desc = _real(slots.get("meta_description")) or _real(fm.get("description"))
    if desc and not 120 <= len(desc) <= 155:
        issues.append(Issue("warn", "LANDING_META_DESCRIPTION_LENGTH", tr(
            lang, f"Meta description is {len(desc)} characters; aim for 120-155.",
            f"Meta popis má {len(desc)} znaků; cílem je 120-155."), _short(desc)))
    for word in dict.fromkeys(unsubstantiated_superlatives(plain_text(body))):
        issues.append(Issue("warn", "LANDING_UNSUBSTANTIATED_SUPERLATIVE", tr(
            lang, f"Superlative '{word}' without a number, source or cite marker nearby; substantiate or remove it.",
            f"Superlativ '{word}' bez čísla, zdroje nebo značky citace poblíž; doložte ho, nebo ho vypusťte."), word))
    return issues


# -- email helpers -----------------------------------------------------------------------
def _footer_text(lang: str, brand: str) -> str:
    return tr(lang,
              f"You are receiving this email because you subscribed to updates from {brand}. "
              "You can unsubscribe at any time using the unsubscribe link in this email.",
              f"Tento e-mail dostáváte, protože jste se přihlásili k odběru novinek od {brand}. "
              "Odběr můžete kdykoli zrušit pomocí odkazu pro odhlášení v tomto e-mailu.")


def _check_subject(subject: str, lang: str, where: str) -> list[Issue]:
    issues: list[Issue] = []
    if len(subject) > 50:
        issues.append(Issue("warn", "SUBJECT_TOO_LONG", tr(
            lang, f"Subject is {len(subject)} characters; keep it at 50 or fewer so it is not cut off.",
            f"Předmět má {len(subject)} znaků; držte se nejvýše 50, ať se neořízne."), _short(subject)))
    if _DECEPTIVE_SUBJECT_RE.match(subject):
        issues.append(Issue("error", "SUBJECT_DECEPTIVE", tr(
            lang, "Subject fakes a reply or forward (RE:, FWD:); deceptive subject lines are not allowed.",
            "Předmět předstírá odpověď nebo přeposlání (RE:, FWD:); klamavé předměty nejsou přípustné."), _short(subject)))
    letters = [c for c in subject if c.isalpha()]
    if len(letters) >= 8 and all(c.isupper() for c in letters):
        issues.append(Issue("warn", "SUBJECT_ALL_CAPS", tr(lang, "Subject is written in capitals; use normal case.",
                                                          "Předmět je psaný velkými písmeny; použijte běžná písmena."), _short(subject)))
    if re.search(r"[!?]{2,}", subject):
        issues.append(Issue("warn", "SUBJECT_PUNCTUATION", tr(lang, "Subject has repeated punctuation; drop it.",
                                                             "Předmět obsahuje opakovanou interpunkci; vypusťte ji."), _short(subject)))
    return issues


def _check_preheader(pre: str, subject: str, lang: str) -> list[Issue]:
    issues: list[Issue] = []
    if len(pre) > 100:
        issues.append(Issue("warn", "PREHEADER_TOO_LONG", tr(lang, f"Preheader is {len(pre)} characters; keep it at 100 or fewer.",
                                                            f"Preheader má {len(pre)} znaků; držte se nejvýše 100."), _short(pre)))
    if subject and pre.strip().lower() == subject.strip().lower():
        issues.append(Issue("warn", "PREHEADER_REPEATS_SUBJECT", tr(lang, "The preheader repeats the subject; add new information.",
                                                                   "Preheader opakuje předmět; přidejte novou informaci."), _short(pre)))
    return issues


def _has_unsubscribe(text: str) -> bool:
    return bool(_UNSUB_RE.search(fold(text.lower())))


# -- newsletter --------------------------------------------------------------------------
def build_newsletter(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Newsletter: subject and preheader, hook, one main story, two quick hits, one CTA and a legal footer.

    options: cta_url (default "#cta").
    """
    opts = dict(options or {})
    lang = norm_lang(brief.lang)
    cta_url = str(opts.get("cta_url") or "#cta")
    slots = [
        Slot("subject", "Subject line of at most 50 characters. Specific and honest; no RE:/FWD: tricks, no ALL CAPS.", max_chars=50, kind="title"),
        Slot("preheader", "Preheader of 40-90 characters that adds to the subject instead of repeating it.", max_chars=100, kind="line"),
        Slot("hook", f"Opening line (1-2 sentences) that earns the next paragraph for {brief.audience}. Specific, no greeting filler.",
             max_words=40, default=hook.strip() if hook and hook.strip() else None),
        Slot("main_heading", "Main story headline, at most 70 characters.", max_chars=70, kind="title"),
        Slot("main_body", "Main story in 120-180 words: one idea, supplied facts or vetted sources only, one concrete takeaway.",
             max_words=190, min_chars=500),
        Slot("quick_1_heading", "Quick hit 1 headline, at most 60 characters.", max_chars=60, kind="title"),
        Slot("quick_1_body", "Quick hit 1 in 30-60 words. Supplied facts only.", max_words=70, min_chars=120),
        Slot("quick_2_heading", "Quick hit 2 headline, at most 60 characters.", max_chars=60, kind="title"),
        Slot("quick_2_body", "Quick hit 2 in 30-60 words. Supplied facts only.", max_words=70, min_chars=120),
        Slot("cta", "The single call to action as button text, max 40 characters.", max_chars=40, kind="line",
             default=brief.cta.strip() if brief.cta and brief.cta.strip() else None),
        Slot("footer_identity", "Sender identity for the footer: legal name and postal address. Real details only.", kind="line"),
    ]
    lines = [f"{tr(lang, 'Subject', 'Předmět')}: {_ph('subject')}", f"Preheader: {_ph('preheader')}", "", "---", "", _ph("hook"), "",
             f"## {_ph('main_heading')}", "", _ph("main_body"), "", f"## {tr(lang, 'Quick hits', 'Ve zkratce')}", "",
             f"### {_ph('quick_1_heading')}", "", _ph("quick_1_body"), "", f"### {_ph('quick_2_heading')}", "", _ph("quick_2_body"), "",
             f"**[{_ph('cta')}]({cta_url})**", "", "---", "", _footer_text(lang, brief.brand), "", _ph("footer_identity")]
    return Skeleton(
        format="newsletter", lang=lang, template="\n".join(lines), slots=slots, hook_slot="hook",
        notes=[tr(lang, "Keep one CTA. The footer must carry a working unsubscribe link and the sender identity.",
                  "Ponechte jednu výzvu k akci. Zápatí musí obsahovat funkční odkaz pro odhlášení a identifikaci odesílatele.")],
        fixed={"cta_url": cta_url},
        meta={"goal": brief.goal, "cta": brief.cta, "sponsored": brief.sponsored, "keyword": brief.primary_keyword,
              "lang": lang, "brand": brief.brand, "topic": brief.topic},
    )


def validate_newsletter(draft: Draft) -> list[Issue]:
    lang = _lang_of(draft)
    slots = _slots(draft)
    body = draft.body
    issues: list[Issue] = []
    m = _SUBJECT_RE.search(body)
    subject = _real(slots.get("subject")) or (_real(m.group(1)) if m else "")
    if subject:
        issues += _check_subject(subject, lang, "subject")
    elif not m and "subject" not in slots:
        issues.append(Issue("error", "NEWSLETTER_SUBJECT_MISSING", tr(lang, "The newsletter has no subject line.",
                                                                     "Newsletter nemá předmět.")))
    p = _PREHEADER_RE.search(body)
    pre = _real(slots.get("preheader")) or (_real(p.group(1)) if p else "")
    if pre:
        issues += _check_preheader(pre, subject, lang)
    elif not p and "preheader" not in slots:
        issues.append(Issue("warn", "PREHEADER_MISSING", tr(lang, "Add a preheader.", "Přidejte preheader.")))
    buttons = _cta_buttons(body)
    if not buttons:
        issues.append(Issue("warn", "NEWSLETTER_NO_CTA", tr(lang, "The newsletter has no call to action.",
                                                           "Newsletter nemá výzvu k akci.")))
    elif len(buttons) > 1:
        issues.append(Issue("warn", "NEWSLETTER_MULTIPLE_CTA", tr(
            lang, "Use one primary call to action per newsletter.", "Použijte v newsletteru jednu hlavní výzvu k akci."), _short(" / ".join(buttons))))
    if not _has_unsubscribe(body):
        issues.append(Issue("error", "NEWSLETTER_NO_UNSUBSCRIBE", tr(
            lang, "The footer has no unsubscribe reminder; every marketing email must offer an easy opt-out.",
            "V zápatí chybí upozornění na odhlášení; každý marketingový e-mail musí nabízet snadné odhlášení.")))
    n_sections = sum(1 for lv, _ in parse_headings(body) if lv in (2, 3))
    if n_sections < 3:
        issues.append(Issue("warn", "NEWSLETTER_STRUCTURE", tr(
            lang, "Expected one main story and two quick hits.", "Očekává se jeden hlavní příběh a dva krátké tipy.")))
    return issues


# -- email sequence ----------------------------------------------------------------------
_SEQ_GOALS: dict[str, tuple[str, str, str, tuple[int, int]]] = {
    "welcome": ("Welcome", "Uvítání", "Thank the reader for joining, set expectations (what you will send and how often) and deliver "
                "the first promised value. No hard sell.", (90, 140)),
    "value": ("Value", "Užitečný obsah", "Teach one useful thing the reader can apply today, drawn from the brand's own experience "
              "or supplied facts.", (150, 220)),
    "proof": ("Proof", "Důkazy", "Show proof: a first-party result, case or cited source supplied by the brand. Never invent "
              "customers, quotes or numbers.", (120, 180)),
    "offer": ("Offer", "Nabídka", "Present the offer clearly: who it is for, what is included and one clear next step. Real terms only.",
              (120, 180)),
    "last_call": ("Last call", "Poslední výzva", "A short, honest reminder of the offer. Mention a deadline only if one exists in the "
                  "supplied facts; no fake urgency.", (60, 110)),
}
_SEQ_ORDER = {3: ("welcome", "value", "offer"), 4: ("welcome", "value", "proof", "offer"),
              5: ("welcome", "value", "proof", "offer", "last_call")}
_SEQ_DAYS = (0, 2, 4, 7, 9)
_EMAIL_HEAD_RE = re.compile(r"^##[ \t]+(?:Email|E-mail)[ \t]+(\d+)\b[^\n]*$", re.M)


def build_email_sequence(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Email sequence of 3 to 5 emails (welcome, value, proof, offer, last call) with day offsets 0, 2, 4, 7, 9.

    options: emails (3..5, default 4), cta_url (default "#cta"). Each email has subject, preheader, body and one CTA.
    """
    opts = dict(options or {})
    lang = norm_lang(brief.lang)
    n = _clamp(opts.get("emails"), 3, 5, 4)
    cta_url = str(opts.get("cta_url") or "#cta")
    cta = brief.cta.strip() if brief.cta and brief.cta.strip() else None
    order = _SEQ_ORDER[n]
    slots: list[Slot] = []
    lines: list[str] = []
    timing: list[dict[str, Any]] = []
    for i, goal in enumerate(order, 1):
        label_en, label_cs, instr, (lo, hi) = _SEQ_GOALS[goal]
        day = _SEQ_DAYS[i - 1]
        timing.append({"n": i, "goal": goal, "day": day})
        slots += [
            Slot(f"e{i}_subject", f"Email {i} ({label_en}) subject line, at most 50 characters. Honest and specific; no RE:/FWD: tricks, no fake urgency.",
                 max_chars=50, kind="title"),
            Slot(f"e{i}_preheader", f"Email {i} preheader of 40-90 characters that adds to the subject.", max_chars=100, kind="line"),
            Slot(f"e{i}_body", f"Email {i} body of {lo}-{hi} words for {brief.audience}. Goal: {instr}", max_words=hi + 20, min_chars=lo * 5),
            Slot(f"e{i}_cta", f"Email {i}: the single call to action as button text, max 40 characters.", max_chars=40, kind="line", default=cta),
        ]
        head = tr(lang, f"## Email {i}: {label_en} (day {day})", f"## E-mail {i}: {label_cs} (den {day})")
        lines += [head, "", f"{tr(lang, 'Subject', 'Předmět')}: {_ph(f'e{i}_subject')}", f"Preheader: {_ph(f'e{i}_preheader')}", "",
                  _ph(f"e{i}_body"), "", f"**[{_ph(f'e{i}_cta')}]({cta_url})**", "", _footer_text(lang, brief.brand), "",
                  _ph("footer_identity"), "", "---", ""]
    slots.append(Slot("footer_identity", "Sender identity for every footer: legal name and postal address. Real details only.", kind="line"))
    return Skeleton(
        format="email_sequence", lang=lang, template="\n".join(lines).rstrip("-\n "), slots=slots, hook_slot="e1_subject",
        notes=[tr(lang, "One CTA per email. Last call only mentions a deadline that exists in your facts; no fake urgency.",
                  "Jedna výzva v každém e-mailu. Poslední výzva zmiňuje jen termín, který skutečně existuje; žádný vymyšlený spěch.")],
        fixed={"timing": timing, "emails": n, "cta_url": cta_url},
        meta={"goal": brief.goal, "cta": brief.cta, "sponsored": brief.sponsored, "keyword": brief.primary_keyword,
              "lang": lang, "brand": brief.brand, "topic": brief.topic, "emails": n},
    )


def validate_email_sequence(draft: Draft) -> list[Issue]:
    lang = _lang_of(draft)
    body = draft.body
    heads = list(_EMAIL_HEAD_RE.finditer(body))
    issues: list[Issue] = []
    if not 3 <= len(heads) <= 5:
        issues.append(Issue("warn", "SEQUENCE_LENGTH", tr(
            lang, f"The sequence has {len(heads)} emails; use 3 to 5.", f"Sekvence má {len(heads)} e-mailů; použijte 3 až 5.")))
    for k, m in enumerate(heads):
        chunk = body[m.end(): heads[k + 1].start() if k + 1 < len(heads) else len(body)]
        where = f"email {m.group(1)}"
        sm = _SUBJECT_RE.search(chunk)
        subject = _real(sm.group(1)) if sm else ""
        if subject:
            issues += [Issue(i.severity, i.code, f"[{where}] {i.message}", i.where) for i in _check_subject(subject, lang, where)]
        elif not sm:
            issues.append(Issue("error", "EMAIL_SUBJECT_MISSING", tr(lang, f"[{where}] No subject line.", f"[{where}] Chybí předmět."), where))
        pm = _PREHEADER_RE.search(chunk)
        if pm and _real(pm.group(1)):
            issues += [Issue(i.severity, i.code, f"[{where}] {i.message}", i.where) for i in _check_preheader(_real(pm.group(1)), subject, lang)]
        buttons = _cta_buttons(chunk)
        if not buttons:
            issues.append(Issue("warn", "EMAIL_NO_CTA", tr(lang, f"[{where}] No call to action.", f"[{where}] Chybí výzva k akci."), where))
        elif len(buttons) > 1:
            issues.append(Issue("warn", "EMAIL_MULTIPLE_CTA", tr(
                lang, f"[{where}] More than one call to action; use exactly one per email.",
                f"[{where}] Více než jedna výzva k akci; použijte v každém e-mailu právě jednu."), where))
        if not _has_unsubscribe(chunk):
            issues.append(Issue("error", "EMAIL_NO_UNSUBSCRIBE", tr(
                lang, f"[{where}] No unsubscribe line; every marketing email must offer an easy opt-out.",
                f"[{where}] Chybí řádek o odhlášení; každý marketingový e-mail musí nabízet snadné odhlášení."), where))
    days = [t.get("day") for t in draft.parts.get("timing") or [] if isinstance(t, dict)]
    if days and (days[0] != 0 or any(b <= a for a, b in zip(days, days[1:]))):
        issues.append(Issue("warn", "SEQUENCE_TIMING", tr(
            lang, "Send days should start at day 0 and increase (for example 0, 2, 4, 7).",
            "Dny odeslání mají začínat dnem 0 a růst (například 0, 2, 4, 7).")))
    return issues


FORMAT_SPECS: list[FormatSpec] = [
    FormatSpec(
        id="press_release", name_en="Press release", name_cs="Tisková zpráva", family="article", platform="newsroom",
        build=build_press_release, validate=validate_press_release, limits={"headline_max": 100, "lead_words": 60, "quotes": 1},
        description_en="Inverted pyramid press release with a 5W lead, real quotes only, boilerplate, media contact and end mark.",
        description_cs="Tisková zpráva v obrácené pyramidě s perexem na otázky kdo, co, kdy, kde, proč, jen skutečnými citacemi, medailonkem a kontaktem.",
    ),
    FormatSpec(
        id="landing_page", name_en="Landing page", name_cs="Landing page", family="article", platform="web",
        build=build_landing_page, validate=validate_landing_page, limits={"headline_words": 12, "benefits": 3, "meta_title_max": 60},
        description_en="Hero, problem, solution, three benefits, proof that is never invented, objection FAQ and one repeated CTA.",
        description_cs="Hlavní blok, problém, řešení, tři přínosy, nikdy nevymyšlené důkazy, FAQ s námitkami a jedna opakovaná výzva k akci.",
    ),
    FormatSpec(
        id="newsletter", name_en="Newsletter", name_cs="Newsletter", family="email", platform="email",
        build=build_newsletter, validate=validate_newsletter, limits={"subject_max": 50, "preheader_max": 100, "sections": 3},
        description_en="One main story, two quick hits, one CTA and a footer with the unsubscribe reminder.",
        description_cs="Jeden hlavní příběh, dva krátké tipy, jedna výzva k akci a zápatí s upozorněním na odhlášení.",
    ),
    FormatSpec(
        id="email_sequence", name_en="Email sequence", name_cs="E-mailová sekvence", family="email", platform="email",
        build=build_email_sequence, validate=validate_email_sequence,
        limits={"emails": (3, 5), "days": list(_SEQ_DAYS), "subject_max": 50},
        description_en="Welcome, value, proof, offer and last call emails with timing, one CTA each and an unsubscribe line.",
        description_cs="E-maily uvítání, užitečný obsah, důkazy, nabídka a poslední výzva s časováním, jednou výzvou a řádkem o odhlášení.",
    ),
]
