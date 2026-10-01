"""Hook library: parametrised English and Czech hook templates scored with the Dopamine Score.

Every template is plain text with ``{field}`` placeholders (topic, audience, keyword, brand, n, fact
and the Czech case forms ``topic_gen``, ``topic_acc`` ...). A template is skipped when one of its
fields is unavailable, so a brief without a keyword, without Czech case forms or without a numeric fact
simply yields fewer candidates. Nothing here invents facts: list counts are structural promises (5 or 7
unless the brief names a list size), and proof templates quote a numeric fact from ``brief.facts``
verbatim and are skipped when there is none.

Conventions: ``audience`` is a plural noun phrase in the nominative (``beginner runners``), and ``topic``
is never the grammatical subject of a verb, so templates stay correct for singular and plural topics.
Czech templates use colon constructions and address forms so they read naturally with a nominative
topic; templates that need a case form are only used when ``brief.topic_forms`` provides it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Sequence

from ..models import Serializable
from ..scoring import fold, score_hook
from .types import Brief, FormatSpec, Issue, Skeleton

HOOK_STYLES = (
    "curiosity_gap", "contrarian", "number_list", "how_to", "warning", "story",
    "question", "identity", "proof", "challenge", "before_after", "myth_bust",
)
STYLE_CAP = 3                    # max candidates per style when no style filter is given
DEFAULT_LIST_COUNTS = (7, 5)     # structural list sizes used when the brief names none
HOOK_PLAIN = "plain"             # style of the last-resort fallback hook


@dataclass
class HookCandidate(Serializable):
    text: str
    style: str
    score: float
    clickbait_risk: float
    lang: str


# -- English templates ---------------------------------------------------------------
# Order matters: it breaks score ties. Fields: topic audience keyword brand n fact.
TEMPLATES_EN: dict[str, tuple[str, ...]] = {
    "curiosity_gap": (
        "What nobody tells you about {topic}",
        "The truth about {topic}",
        "{topic}: the part nobody talks about",
        "The real reason {audience} get stuck with {topic}",
        "Here's what to know about {topic} before you decide",
        "The one thing about {topic} you may not know",
        "What really matters when it comes to {topic}",
        "Turns out, there is more to {topic} than you think",
        "Inside {topic}: what {audience} rarely see",
        "{keyword}: what to know before you start",
    ),
    "contrarian": (
        "Stop overthinking {topic}",
        "Forget what you think you know about {topic}",
        "An unpopular opinion about {topic}",
        "Don't follow the usual advice on {topic}",
        "Ditch the old rules of {topic}",
        "Stop wasting time on the wrong {topic} advice",
        "Why you should ignore some {topic} advice",
        "{audience}: quit chasing every new {topic} trend",
        "Less is more: a simpler way to approach {topic}",
    ),
    "number_list": (
        "{n} mistakes {audience} make with {topic}",
        "{n} ways to get more from your {topic}",
        "{n} questions to ask before you choose {topic}",
        "{n} lessons about {topic} for {audience}",
        "{n} simple rules for {topic}",
        "{n} things to check before you start with {topic}",
        "{n} tips on {topic} for {audience}",
        "{n} signs it is time to rethink your {topic}",
        "{keyword}: {n} things to know",
    ),
    "how_to": (
        "How to get started with {topic}",
        "How to choose {topic} with confidence",
        "How {audience} can get started with {topic}",
        "A step by step guide to {topic} for {audience}",
        "{topic}: a simple checklist before you begin",
        "How to keep {topic} simple",
        "How to avoid costly mistakes with {topic}",
        "A quick guide to {topic}",
        "{keyword}: how to start, step by step",
    ),
    "warning": (
        "Before you start with {topic}, read this",
        "Avoid these {n} mistakes with {topic}",
        "Think twice before you commit to {topic}",
        "A word of warning about {topic}",
        "Don't make this mistake with {topic}",
        "Red flags to watch for in {topic}",
        "The trap {audience} fall into with {topic}",
        "Don't decide on {topic} until you read this",
        "{keyword}: {n} red flags to check first",
    ),
    "story": (
        "The story behind {topic}",
        "Behind the scenes of {topic}",
        "What we learned about {topic}",
        "A real story about {topic} that {audience} will recognise",
        "How {brand} looks at {topic}, from the inside",
        "The one thing we would tell {audience} about {topic}",
        "From the first idea to the final result: {topic}",
        "{topic}: a story {audience} will recognise",
    ),
    "question": (
        "Are you making these mistakes with {topic}?",
        "Do you really need {topic}?",
        "What do {audience} get wrong about {topic}?",
        "What would you change about {topic}?",
        "Is it time to rethink {topic}?",
        "Should you start with {topic}? Here is how to decide",
        "What is the one thing you would ask about {topic}?",
        "What does good look like for {topic}?",
        "{keyword}: what should you look for?",
    ),
    "identity": (
        "For {audience} who want to get {topic} right",
        "Calling all {audience}: a {topic} guide made for you",
        "{audience}: this guide is for you",
        "Written for {audience}: {topic} without the jargon",
        "{audience}, here is your guide to {topic}",
        "A note for {audience} who are new to {topic}",
        "{audience}, this is your sign to rethink {topic}",
        "Made for {audience}: {topic}, explained",
    ),
    "proof": (
        "Proof, not promises: {fact}",
        "By the numbers: {fact}",
        "{fact}: what it means for {audience}",
        "The numbers on {topic}: {fact}",
        "What the data says: {fact}",
        "Real numbers, no spin: {fact}",
        "{fact}. Here is what that means for you",
        "Our numbers on {topic}: {fact}",
        "See the proof: {fact}",
    ),
    "challenge": (
        "Try this for {n} days: {topic}",
        "The {n}-day {topic} challenge for {audience}",
        "Can you do this for {n} days? A {topic} challenge",
        "Take the {topic} challenge: {n} days, one small step a day",
        "Your {n}-day {topic} challenge starts here",
        "One week, one change: a {topic} experiment for {audience}",
        "Ready for a {topic} challenge? Start with {n} days",
        "Join the {topic} challenge",
    ),
    "before_after": (
        "Before and after: {topic} done right",
        "Before vs after: {n} small changes to your {topic}",
        "Same {topic}, different result: what to change",
        "From stuck to steady: {topic} for {audience}",
        "What changes when you rethink {topic}",
        "Your {topic} before and after {n} simple changes",
        "Not what it used to be: a new way to look at {topic}",
        "{topic}: before and after you fix the basics",
    ),
    "myth_bust": (
        "{n} myths about {topic} that {audience} still believe",
        "Myth vs reality: {topic}",
        "Stop believing these {n} {topic} myths",
        "The biggest myth about {topic}",
        "Is it true? {n} popular claims about {topic}, checked",
        "Think you know {topic}? Check these {n} myths",
        "Fact or myth? {topic} edition",
        "{topic}: myths, facts and what to do instead",
    ),
}


# -- Czech templates -----------------------------------------------------------------
# Nominative-safe: the topic only appears as a label before a colon, the audience only as an address
# or as the subject of a plural verb, and {n} is always 5 or more (genitive plural after the number).
TEMPLATES_CS: dict[str, tuple[str, ...]] = {
    "curiosity_gap": (
        "{topic}: o čem se nemluví",
        "{topic}: celá pravda",
        "{topic}: skutečný důvod, proč {audience} tápou",
        "{topic}: tady je, co byste měli vědět dřív, než se rozhodnete",
        "Zákulisí: {topic}",
        "{topic}: skryté souvislosti, které {audience} přehlížejí",
        "{topic}: tajemství, o kterém {audience} nevědí",
        "{topic}: překvapivé souvislosti, které se vyplatí znát",
        "{keyword}: co vědět, než se rozhodnete",
    ),
    "contrarian": (
        "{topic}: přestaňte to komplikovat",
        "{topic}: zapomeňte na zažité rady",
        "Nepopulární názor: {topic}",
        "{topic}: nedělejte to jako všichni",
        "{topic}: místo dalších rad zkuste tohle",
        "{topic}: přestaňte plýtvat časem a začněte jednoduše",
        "{audience}, nenechte si namluvit složité rady: {topic}",
        "{topic}: opak toho, co jste slyšeli",
        "Zapomeňte na staré zvyky: {topic}",
    ),
    "number_list": (
        "{topic}: {n} chyb, kterých se dopouštějí {audience}",
        "{topic}: {n} otázek, které si položte před rozhodnutím",
        "{topic}: {n} věcí, které se vyplatí zkontrolovat",
        "{topic}: {n} pravidel, která usnadní začátek",
        "{topic}: {n} kroků, jak začít",
        "{topic}: {n} tipů, které {audience} ocení",
        "{topic}: {n} varovných signálů, že je čas na změnu",
        "{topic}: {n} lekcí pro začátek",
        "{keyword}: {n} věcí, které byste měli vědět",
    ),
    "how_to": (
        "{topic}: jak začít krok za krokem",
        "{topic}: jednoduchý návod, který se vyplatí znát",
        "{topic}: jak se rozhodnout a nelitovat",
        "{audience}, tady je návod: {topic}",
        "{topic}: praktický průvodce krok za krokem",
        "Jak na to: {topic}",
        "{topic}: checklist, který si projdete za pár minut",
        "{topic}: co dělat jako první",
        "{keyword}: jak začít a čeho se vyvarovat",
    ),
    "warning": (
        "{topic}: než začnete, přečtěte si tohle",
        "{topic}: pozor na tyto chyby",
        "{topic}: nedělejte tuto chybu",
        "Varování: {topic}, než se rozhodnete",
        "{topic}: {n} varovných signálů, kterých si všimněte",
        "{topic}: zastavte se, než začnete",
        "{topic}: pozor na pasti, do kterých {audience} padají",
        "{audience}, pozor: {topic}",
        "{keyword}: čeho si všimnout dřív, než začnete",
    ),
    "story": (
        "Příběh za značkou {brand}: {topic}",
        "Zákulisí: {topic} očima značky {brand}",
        "{topic}: co jsme zjistili",
        "Skutečný příběh: {topic}",
        "{topic}: pohled zevnitř",
        "{topic}: příběh, který {audience} dobře znají",
        "Za oponou: {topic}",
        "{topic}: jedna věc, kterou bychom řekli hned na začátku",
    ),
    "question": (
        "{topic}: děláte to správně?",
        "{topic}: opravdu to potřebujete?",
        "{topic}: co dělají {audience} špatně?",
        "{topic}: víte, na co si dát pozor?",
        "{topic}: je čas změnit přístup?",
        "{topic}: víte, co vlastně potřebujete?",
        "{topic}: na co se ptát, než se rozhodnete?",
        "{topic}: co byste se rádi dozvěděli?",
        "{keyword}: na co se zeptat, než začnete?",
    ),
    "identity": (
        "{audience}, tohle je pro vás: {topic}",
        "{audience}, čtěte dál: {topic}",
        "{audience}, máme pro vás téma: {topic}",
        "{audience}, pojďme na to: {topic}",
        "{audience}, zbystřete: {topic}",
        "{audience}, tady je něco pro vás: {topic}",
        "{topic}: {audience}, tohle si nenechte ujít",
    ),
    "proof": (
        "Čísla místo slibů: {fact}",
        "{topic} v číslech: {fact}",
        "Důkaz, ne tvrzení: {fact}",
        "Co říkají data: {fact}",
        "{fact}: co to znamená pro vás?",
        "Fakta bez příkras: {fact}",
        "Podívejte se na čísla: {fact}",
        "{topic}: {fact}",
        "Naše čísla: {fact}",
    ),
    "challenge": (
        "Výzva na {n} dní: {topic}",
        "{topic}: zvládnete to na {n} dní?",
        "Přidejte se k výzvě: {topic}",
        "{topic}: {n} dní, jeden malý krok denně",
        "{topic}: tady je výzva pro vás",
        "Vyzkoušejte si to na {n} dní: {topic}",
        "Jste připraveni na výzvu? {topic}",
        "{audience}, výzva pro vás: {topic}",
    ),
    "before_after": (
        "{topic}: před a po",
        "{topic}: {n} malých změn, které dělají rozdíl",
        "Před a po: {topic} bez zbytečných komplikací",
        "{topic}: co se změní, když začnete jinak",
        "Stejné téma, jiný výsledek: {topic}",
        "{topic}: od zmatku k jasnému plánu",
        "{topic}: {n} změn, po kterých to půjde lépe",
        "{topic}: před a po {n} malých změnách",
    ),
    "myth_bust": (
        "{topic}: {n} mýtů, kterým {audience} stále věří",
        "Mýtus, nebo pravda? {topic}",
        "{topic}: přestaňte věřit těmto mýtům",
        "{topic}: častý mýtus a jak je to doopravdy",
        "Mýty a fakta: {topic}",
        "{topic}: co je pravda a co mýtus",
        "{topic}: {n} tvrzení, která si zaslouží ověření",
        "Věříte tomu? {topic}: {n} mýtů pod lupou",
    ),
}

# Czech templates that need a grammatical case of the topic. Used only when brief.topic_forms has it.
TEMPLATES_CS_CASES: dict[str, tuple[str, ...]] = {
    "curiosity_gap": (
        "Pravda o {topic_loc}",
        "Nikdo vám neřekne celou pravdu o {topic_loc}",
        "Co se o {topic_loc} nemluví",
    ),
    "contrarian": (
        "Přestaňte řešit {topic_acc} podle starých pouček",
        "Zapomeňte na zažité rady o {topic_loc}",
        "Nepopulární názor na {topic_acc}",
    ),
    "number_list": (
        "{n} chyb při výběru {topic_gen}",
        "{n} věcí, které byste měli vědět o {topic_loc}",
        "{n} způsobů, jak vylepšit {topic_acc}",
    ),
    "how_to": (
        "Jak vybrat {topic_acc} a nelitovat",
        "Jak se zorientovat v {topic_loc}",
        "Průvodce výběrem {topic_gen} krok za krokem",
    ),
    "warning": (
        "Než se rozhodnete pro {topic_acc}: přečtěte si tohle",
        "Nedělejte tyto chyby při výběru {topic_gen}",
        "Pozor na pasti u {topic_gen}",
    ),
    "story": (
        "Příběh o {topic_loc}",
        "Co jsme se naučili o {topic_loc}",
    ),
    "question": (
        "Víte, jak je to s {topic_ins}?",
        "Opravdu potřebujete {topic_acc}?",
        "Co byste rádi věděli o {topic_loc}?",
    ),
    "identity": (
        "{audience}, tohle potřebujete vědět o {topic_loc}",
        "{audience}, ptáte se na {topic_acc}? Tady je odpověď",
    ),
    "proof": (
        "Čísla o {topic_loc}: {fact}",
    ),
    "challenge": (
        "Výzva: {n} dní s {topic_ins}",
        "Zvládnete {n} dní s {topic_ins}?",
    ),
    "before_after": (
        "Před a po: {n} změn u {topic_gen}",
        "Před a po: jak změnit přístup k {topic_dat}",
    ),
    "myth_bust": (
        "{n} mýtů o {topic_loc}",
        "Mýty o {topic_loc}: co je pravda?",
    ),
}


def templates_for(lang: str, style: str) -> tuple[str, ...]:
    """All templates of a style in tie-break order: base templates first, then case form templates."""
    if lang == "cs":
        return TEMPLATES_CS[style] + TEMPLATES_CS_CASES.get(style, ())
    return TEMPLATES_EN[style]


def all_templates() -> list[tuple[str, str, str]]:
    """Every template as (lang, style, text), for tests and tooling."""
    return [(lang, style, t) for lang in ("en", "cs") for style in HOOK_STYLES for t in templates_for(lang, style)]


# -- context and rendering -----------------------------------------------------------
_FIELD_RE = re.compile(r"\{([a-z_]+)\}")
_NUM_RE = re.compile(r"\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)*")
_SENTENCE_START_RE = re.compile(r"([.?!]\s+)(\w)")
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_CASES = ("gen", "dat", "acc", "loc", "ins")
# A number followed by one of these nouns is a list size ("7 tips"), not a statistic.
_LIST_NOUN_RE = re.compile(
    r"\b(\d{1,2})\s+(?:tips?|ways?|steps?|mistakes?|rules?|lessons?|tools?|ideas?|habits?|myths?|signs?|"
    r"questions?|things?|tricks?|reasons?|principles?|"
    r"tip\w*|krok\w*|chyb\w*|pravidel|lekc\w*|n[aá]stroj\w*|n[aá]pad\w*|zvyk\w*|m[yý]t\w*|"
    r"znamen\w*|ot[aá]zk\w*|v[eě]c\w*|trik\w*|d[uů]vod\w*|z[aá]sad\w*|zp[uů]sob\w*)",
    re.I,
)
MAX_FACT_CHARS = 80


@lru_cache(maxsize=16384)
def cached_score(text: str, lang: str) -> tuple[float, float]:
    """(Dopamine Score total, clickbait risk) of a hook. Scoring is deterministic, so results are cached."""
    s = score_hook(text, lang=lang)
    return s.total, s.clickbait_risk


def norm_key(text: str, lang: str) -> str:
    """Normalised text used to detect near duplicates."""
    t = unicodedata.normalize("NFC", text).lower()
    if lang == "cs":
        t = fold(t)
    return " ".join(re.sub(r"[\W_]+", " ", t).split())


def proof_facts(brief: Brief) -> list[str]:
    """Short facts that carry a real number (year-only facts do not count), trailing punctuation removed."""
    out: list[str] = []
    for raw in brief.facts:
        fact = " ".join(str(raw).split()).rstrip(".;:!")
        if not fact or len(fact) > MAX_FACT_CHARS:
            continue
        if any(not _YEAR_RE.fullmatch(m.group()) for m in _NUM_RE.finditer(fact)):
            out.append(fact)
    return out


def list_counts(brief: Brief, lang: str) -> list[int]:
    """List sizes for number hooks: a list size named in the facts, else the fixed defaults."""
    found: list[int] = []
    low = 5 if lang == "cs" else 3   # Czech nouns after 2-4 need another plural form
    for fact in brief.facts:
        for m in _LIST_NOUN_RE.finditer(str(fact)):
            n = int(m.group(1))
            if low <= n <= 12 and n not in found:
                found.append(n)
    return found[:1] or list(DEFAULT_LIST_COUNTS)


def build_context(brief: Brief) -> dict[str, str]:
    """Template fields available for a brief. Missing or empty fields are left out."""
    topic = " ".join(brief.topic.split())
    lang = resolve_lang(brief.lang)
    ctx: dict[str, str] = {"topic": topic}
    if brief.audience.strip():
        ctx["audience"] = " ".join(brief.audience.split())
    if brief.brand.strip():
        ctx["brand"] = brief.brand.strip()
    kw = " ".join((brief.keyword or "").split())
    if kw and norm_key(kw, lang) != norm_key(topic, lang):
        ctx["keyword"] = kw
    for case in _CASES:
        form = " ".join((brief.topic_forms.get(case) or "").split())
        if form:
            ctx[f"topic_{case}"] = form
    return {k: v for k, v in ctx.items() if v}


def resolve_lang(lang: str) -> str:
    return lang if lang in ("en", "cs") else "en"


def render_template(template: str, ctx: dict[str, str]) -> str | None:
    """Fill a template; None when a field is missing. The first letter is capitalised."""
    fields = _FIELD_RE.findall(template)
    if any(not ctx.get(f) for f in fields):
        return None
    text = _FIELD_RE.sub(lambda m: str(ctx[m.group(1)]), template)
    text = " ".join(text.split())
    text = _SENTENCE_START_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    if text and not template.startswith("{brand}"):
        text = text[0].upper() + text[1:]
    return text


def _candidate_texts(brief: Brief, lang: str, style: str) -> list[str]:
    """Rendered texts of one style in template order (duplicates and unavailable templates removed)."""
    ctx = build_context(brief)
    counts = list_counts(brief, lang)
    facts = proof_facts(brief)
    out: list[str] = []
    for i, template in enumerate(templates_for(lang, style)):
        c = dict(ctx)
        c["n"] = str(counts[i % len(counts)])
        if "{fact}" in template:
            if not facts:
                continue     # never fake a statistic: proof needs a real numeric fact
            c["fact"] = facts[i % len(facts)]
        text = render_template(template, c)
        if text:
            out.append(text)
    return out


# -- generation ----------------------------------------------------------------------
def generate_hooks(
    brief: Brief,
    *,
    n: int = 12,
    styles: Sequence[str] | None = None,
    max_chars: int | None = None,
    max_risk: float = 0.35,
    max_words: int | None = None,
) -> list[HookCandidate]:
    """Best hooks for a brief, highest Dopamine Score first.

    Deterministic: ties are broken by template order. Candidates above ``max_risk`` clickbait risk,
    over ``max_chars`` or ``max_words`` and near duplicates are dropped. Without a ``styles`` filter at
    most ``STYLE_CAP`` hooks per style are returned so the list stays diverse.
    """
    if isinstance(styles, str):
        styles = [styles]
    if styles is not None:
        unknown = [s for s in styles if s not in HOOK_STYLES]
        if unknown:
            raise ValueError(f"unknown hook style(s) {unknown}; valid styles: {', '.join(HOOK_STYLES)}")
    wanted = [s for s in HOOK_STYLES if styles is None or s in styles]
    lang = resolve_lang(brief.lang)
    pool: list[tuple[float, int, HookCandidate]] = []
    seen: set[str] = set()
    order = 0
    for style in wanted:
        for text in _candidate_texts(brief, lang, style):
            order += 1
            key = norm_key(text, lang)
            if key in seen:
                continue
            if max_chars is not None and len(text) > max_chars:
                continue
            if max_words is not None and len(text.split()) > max_words:
                continue
            total, risk = cached_score(text, lang)
            if risk > max_risk:
                continue
            seen.add(key)
            cand = HookCandidate(text, style, round(total, 2), round(risk, 4), lang)
            pool.append((cand.score, order, cand))
    pool.sort(key=lambda row: (-row[0], row[1]))
    chosen: list[HookCandidate] = []
    per_style: dict[str, int] = {}
    for _, _, cand in pool:
        if len(chosen) >= n:
            break
        if styles is None and per_style.get(cand.style, 0) >= STYLE_CAP:
            continue
        per_style[cand.style] = per_style.get(cand.style, 0) + 1
        chosen.append(cand)
    return chosen


def _fallback_hook(brief: Brief, max_chars: int | None, max_words: int | None) -> HookCandidate:
    """Last resort when every template was filtered out: the topic itself, trimmed to the limits."""
    lang = resolve_lang(brief.lang)
    words = brief.topic.split()
    if max_words is not None:
        words = words[:max(1, max_words)]
    text = " ".join(words)
    if max_chars is not None and len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0] or text[:max_chars]
    text = (text[:1].upper() + text[1:]) if text else ""
    total, risk = cached_score(text, lang)
    return HookCandidate(text, HOOK_PLAIN, round(total, 2), round(risk, 4), lang)


def best_hook(brief: Brief, **kw: Any) -> HookCandidate:
    """The top hook for a brief. Accepts the same limits as ``generate_hooks``.

    If the limits filter everything out the risk filter is relaxed once, then a plain topic line
    (style ``plain``) is returned, so builders always get a hook.
    """
    kw = dict(kw)
    kw["n"] = 1
    found = generate_hooks(brief, **kw)
    if not found:
        found = generate_hooks(brief, **{**kw, "max_risk": 1.0})
    return found[0] if found else _fallback_hook(brief, kw.get("max_chars"), kw.get("max_words"))


def hook_fits(text: str, max_chars: int | None = None, max_words: int | None = None) -> bool:
    return (max_chars is None or len(text) <= max_chars) and (max_words is None or len(text.split()) <= max_words)


def choose_hook(
    brief: Brief,
    hook: str | None = None,
    *,
    max_chars: int | None = None,
    max_words: int | None = None,
    prefer: str | None = None,
) -> str:
    """The hook text a builder should use as a slot default.

    A caller supplied hook wins when it respects the slot limits; one that does not fit (a 10 word hook for a
    3 second video beat, say) is replaced by the best library hook that does, so a skeleton never ships a
    default that breaks its own limits. ``prefer`` favours the best hook that contains the given phrase
    (for example the SEO keyword).
    """
    if hook and hook.strip() and hook_fits(hook.strip(), max_chars, max_words):
        return hook.strip()
    if prefer:
        needle = fold(prefer.lower().strip())
        for cand in generate_hooks(brief, n=36, max_chars=max_chars, max_words=max_words):
            if needle and needle in fold(cand.text.lower()):
                return cand.text
    return best_hook(brief, max_chars=max_chars, max_words=max_words).text


# -- hook_set format -----------------------------------------------------------------
HOOK_FEED_WINDOW = 140          # characters a feed shows before truncating
MAX_RISK_DEFAULT = 0.35


def build_hook_set(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """A ranked list of hooks. No slots: everything comes from the library and the scorer.

    options: n (default 12, max 36), styles, max_chars, max_words, max_risk. A ``hook`` argument is scored
    and ranked with the others (style ``provided``) even when it is above the risk limit.
    """
    from .formats import brief_meta, standard_notes   # late import: formats imports this module lazily

    opts = options or {}
    lang = resolve_lang(brief.lang)
    n = max(1, min(int(opts.get("n", 12)), 36))
    given_text = (hook or "").strip()
    cands = generate_hooks(
        brief, n=n - 1 if given_text and n > 1 else n, styles=opts.get("styles"), max_chars=opts.get("max_chars"),
        max_risk=float(opts.get("max_risk", MAX_RISK_DEFAULT)), max_words=opts.get("max_words"),
    )
    if given_text:
        total, risk = cached_score(given_text, lang)
        given = HookCandidate(given_text, "provided", round(total, 2), round(risk, 4), lang)
        cands = sorted([given] + cands, key=lambda c: -c.score)[:n]
    rows = [{"text": c.text, "style": c.style, "score": c.score, "risk": c.clickbait_risk} for c in cands]
    cs = lang == "cs"
    lines = [
        f"# {'Sada hooků' if cs else 'Hook set'}: {brief.topic}",
        "",
        ("Řazeno podle Dopamine Score (heuristika 0 až 100). Riziko je signál clickbaitu (0 až 1, nižší je lepší)."
         if cs else
         "Ranked by Dopamine Score (a heuristic from 0 to 100). Risk is the clickbait signal (0 to 1, lower is better)."),
        "",
    ]
    if not rows:
        lines.append("Žádný hook neprošel filtry." if cs else "No hook passed the filters.")
    for i, r in enumerate(rows, 1):
        lines.append(f"{i}. **{r['text']}**")
        lines.append(f"   {'Styl' if cs else 'Style'}: {r['style']} | {'Skóre' if cs else 'Score'}: "
                     f"{r['score']:.1f} | {'Riziko' if cs else 'Risk'}: {r['risk']:.2f}")
    return Skeleton(
        format="hook_set", lang=lang, template="\n".join(lines), slots=[],
        fixed={"hooks": rows, "hook": rows[0]["text"] if rows else ""},
        meta=brief_meta(brief, n=len(rows)),
        notes=standard_notes(brief, "Pick two or three hooks and A/B test them before committing."),
    )


def validate_hook_set(draft) -> list[Issue]:
    rows = draft.parts.get("hooks") or []
    if not rows:
        return [Issue("error", "HOOKS_EMPTY", "No hook passed the filters.")]
    issues: list[Issue] = []
    seen: set[str] = set()
    for i, row in enumerate(rows, 1):
        where = f"hooks[{i}]"
        text = str(row.get("text", "")).strip()
        if not text:
            issues.append(Issue("error", "HOOK_EMPTY", "Empty hook text.", where))
            continue
        key = norm_key(text, draft.lang)
        if key in seen:
            issues.append(Issue("warn", "HOOK_DUPLICATE", f"Duplicate hook: {text}", where))
        seen.add(key)
        if float(row.get("risk", 0.0)) > MAX_RISK_DEFAULT:
            issues.append(Issue("warn", "HOOK_RISK", f"Clickbait risk above {MAX_RISK_DEFAULT}: {text}", where))
        if len(text) > HOOK_FEED_WINDOW:
            issues.append(Issue("warn", "HOOK_LONG", f"Longer than the {HOOK_FEED_WINDOW} character feed window.", where))
    scores = [float(r.get("score", 0.0)) for r in rows]
    if scores != sorted(scores, reverse=True):
        issues.append(Issue("warn", "HOOKS_UNSORTED", "Hooks are not sorted by score."))
    return issues


FORMAT_SPECS: list[FormatSpec] = [
    FormatSpec(
        id="hook_set", name_en="Hook set", name_cs="Sada hooků", family="hooks", platform="any",
        build=build_hook_set, validate=validate_hook_set,
        limits={"max_hooks": 36, "style_cap": STYLE_CAP, "max_risk": MAX_RISK_DEFAULT, "feed_window": HOOK_FEED_WINDOW},
        description_en="Ranked opening lines in twelve styles, scored with the Dopamine Score and filtered for clickbait.",
        description_cs="Seřazené úvodní věty ve dvanácti stylech, ohodnocené Dopamine Score a očištěné od clickbaitu.",
    ),
]
