"""Format registry and dispatcher, plus small helpers shared by the builders and validators.

Each content module (hooks, social, video, ads, seo, geo, longform) exposes a module level
``FORMAT_SPECS`` list. ``all_formats`` collects them lazily so a module that does not exist yet is
skipped, while a module that exists but fails to import raises its real error.
"""
from __future__ import annotations

import importlib
import re
from typing import Any

from ..scoring import fold
from .types import Brief, Draft, FormatSpec, Issue, Skeleton

BUILTIN_MODULES = ("hooks", "social", "video", "ads", "seo", "geo", "longform")
EM_DASH = "—"                      # forbidden in this project's output
PLACEHOLDER_RE = re.compile(r"\[\[ADD:.*?\]\]", re.S)
LANG_NAMES = {"en": "English", "cs": "Czech"}
_SEVERITY_RANK = {"error": 0, "warn": 1, "info": 2}


# -- registry ------------------------------------------------------------------------
def _collect() -> tuple[dict[str, FormatSpec], dict[str, list[str]]]:
    specs: dict[str, FormatSpec] = {}
    owner: dict[str, str] = {}
    by_module: dict[str, list[str]] = {}
    for name in BUILTIN_MODULES:
        full = f"{__package__}.{name}"
        try:
            module = importlib.import_module(full)
        except ModuleNotFoundError as exc:
            if exc.name == full:        # the module itself does not exist yet: skip it
                continue
            raise
        by_module[name] = []
        for spec in getattr(module, "FORMAT_SPECS", []):
            if spec.id in specs:
                raise ValueError(f"duplicate format id {spec.id!r} (modules {owner[spec.id]} and {name})")
            specs[spec.id] = spec
            owner[spec.id] = name
            by_module[name].append(spec.id)
    return specs, by_module


def all_formats() -> dict[str, FormatSpec]:
    """Every registered format by id, in module then declaration order. Raises on duplicate ids."""
    return _collect()[0]


def formats_by_module() -> dict[str, list[str]]:
    """Registered format ids grouped by the module that defines them."""
    return _collect()[1]


def get_format(format_id: str) -> FormatSpec:
    specs = all_formats()
    if format_id not in specs:
        raise KeyError(f"unknown format {format_id!r}; valid ids: {', '.join(specs)}")
    return specs[format_id]


def list_formats(family: str | None = None) -> list[FormatSpec]:
    return [s for s in all_formats().values() if family is None or s.family == family]


def build_skeleton(format_id: str, brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    return get_format(format_id).build(brief, hook=hook, options=options)


# -- validation ----------------------------------------------------------------------
def generic_checks(draft: Draft) -> list[Issue]:
    """Checks every format shares: open slots, leftover placeholders, whitespace, forbidden characters."""
    issues: list[Issue] = []
    if draft.slots_open:
        issues.append(Issue("warn", "SLOTS_OPEN",
                            f"{len(draft.slots_open)} slot(s) still open: {', '.join(draft.slots_open)}"))
    if not draft.body.strip():
        issues.append(Issue("error", "EMPTY_DRAFT", "The draft body is empty."))
    if "{{" in draft.body:
        at = draft.body.index("{{")
        issues.append(Issue("error", "UNRESOLVED_PLACEHOLDER",
                            f"Unresolved template placeholder near: {draft.body[at:at + 40]!r}"))
    lines = draft.body.split("\n")
    if any(line != line.rstrip() for line in lines) or draft.body != draft.body.rstrip():
        issues.append(Issue("info", "WHITESPACE", "Trailing whitespace found."))
    if "\n\n\n" in draft.body:
        issues.append(Issue("info", "WHITESPACE", "More than one consecutive blank line found."))
    if EM_DASH in draft.body or EM_DASH in draft.hook:
        issues.append(Issue("warn", "EM_DASH", "The long dash character is never used in this project; use a hyphen, comma or colon."))
    return issues


def validate_draft(draft: Draft) -> list[Issue]:
    """Run the validator of the draft's format plus the generic checks. Errors come first."""
    try:
        issues = list(get_format(draft.format).validate(draft))
    except KeyError as exc:
        issues = [Issue("error", "UNKNOWN_FORMAT", str(exc.args[0]))]
    own = {i.code for i in issues}
    for g in generic_checks(draft):
        if g.code == "SLOTS_OPEN" and "SLOTS_OPEN" in own:
            continue                    # the format validator already reports it (with its own severity)
        issues.append(g)
    return sorted(issues, key=lambda i: _SEVERITY_RANK.get(i.severity, 3))


# -- brief and skeleton helpers --------------------------------------------------------
def lang_of(brief: Brief) -> str:
    return brief.lang if brief.lang in LANG_NAMES else "en"


def pick(lang: str, en: Any, cs: Any) -> Any:
    """Choose the English or Czech variant of a label."""
    return cs if lang == "cs" else en


def brief_meta(brief: Brief, **extra: Any) -> dict[str, Any]:
    """Skeleton meta: the brief fields validators need (they only see the Draft)."""
    meta: dict[str, Any] = {
        "goal": brief.goal, "cta": brief.cta, "sponsored": brief.sponsored, "keyword": brief.keyword,
        "primary_keyword": brief.primary_keyword, "brand": brief.brand, "topic": brief.topic,
        "audience": brief.audience,
    }
    meta.update(extra)
    return meta


def standard_notes(brief: Brief, *extra: str) -> list[str]:
    """Writer guidance every skeleton carries: language, tone, allowed facts, things to avoid."""
    notes = [f"Write all prose in {LANG_NAMES[lang_of(brief)]}.", f"Tone: {brief.tone}."]
    if brief.voice_notes.strip():
        notes.append(f"Voice notes: {brief.voice_notes.strip()}")
    if brief.avoid:
        notes.append("Avoid: " + ", ".join(brief.avoid) + ".")
    if brief.facts:
        notes.append("Use only these first-party facts and never invent others: " + " | ".join(brief.facts))
    else:
        notes.append("No first-party facts were given: do not add statistics, quotes, customer names or claims.")
    return notes + list(extra)


def fit(text: str | None, *, max_chars: int | None = None, max_words: int | None = None) -> str | None:
    """The text when it respects the limits, else None (defaults are never truncated mid-sentence)."""
    t = " ".join((text or "").split())
    if not t:
        return None
    if max_chars is not None and len(t) > max_chars:
        return None
    if max_words is not None and len(t.split()) > max_words:
        return None
    return t


def to_hashtag(phrase: str) -> str | None:
    parts = re.findall(r"[^\W_]+", phrase or "")
    if not parts or len(parts) > 3:
        return None
    tag = "".join(p[:1].upper() + p[1:] for p in parts)
    if tag.isdigit() or len(tag) > 30:
        return None
    return "#" + tag


def topic_hashtags(brief: Brief, limit: int) -> list[str]:
    """Hashtags derived only from brief fields (topic, keyword, audience, brand, secondary keywords)."""
    out: list[str] = []
    seen: set[str] = set()
    for phrase in (brief.topic, brief.keyword, brief.audience, brief.brand, *brief.secondary_keywords):
        tag = to_hashtag(phrase or "")
        if tag and tag.lower() not in seen:
            seen.add(tag.lower())
            out.append(tag)
    return out[:max(limit, 0)]


# -- text helpers for validators ------------------------------------------------------
_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*")
_HASHTAG_RE = re.compile(r"(?<![\w#&])#([^\W\d_]\w*)")
_URL_RE = re.compile(r"(?:https?://|www\.)[^\s)>\]]+", re.I)


def strip_placeholders(text: str) -> str:
    """Text without [[ADD: ...]] placeholders (limits are measured on real content only)."""
    return PLACEHOLDER_RE.sub("", text or "")


def has_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE.search(text or ""))


def words(text: str) -> list[str]:
    return _WORD_RE.findall(strip_placeholders(text))


def word_count(text: str) -> int:
    return len(words(text))


def hashtags_in(text: str) -> list[str]:
    return ["#" + m.group(1) for m in _HASHTAG_RE.finditer(strip_placeholders(text))]


def urls_in(text: str) -> list[str]:
    return _URL_RE.findall(strip_placeholders(text))


def emoji_count(text: str) -> int:
    n = 0
    for ch in text:
        o = ord(ch)
        if (0x1F300 <= o <= 0x1FAFF or 0x1F000 <= o <= 0x1F2FF or 0x2600 <= o <= 0x27BF
                or o in (0x2B50, 0x2B55, 0x231A, 0x231B, 0x23F0, 0x23F3)):
            n += 1
    return n


_ACRONYMS = frozenset({
    "SEO", "CRM", "ROI", "KPI", "CTA", "UGC", "API", "FAQ", "USA", "AI", "EU", "UK", "B2B", "B2C", "SaaS",
    "PDF", "CEO", "HR", "IT", "PR", "GEO", "RSA", "USP", "ADD", "TV", "VAT", "DPH",
})


def caps_words(text: str) -> list[str]:
    """Words of three or more letters written in capitals (known acronyms and hashtags excluded)."""
    t = _HASHTAG_RE.sub(" ", _URL_RE.sub(" ", strip_placeholders(text)))
    return [w for w in _WORD_RE.findall(t)
            if len(w) >= 3 and w.isalpha() and w == w.upper() and w.upper() not in _ACRONYMS]


def caps_ratio(text: str) -> float:
    ws = [w for w in words(text) if w.isalpha()]
    return len(caps_words(text)) / len(ws) if ws else 0.0


def keyword_in(text: str, keyword: str | None, lang: str = "en") -> bool:
    """Case and diacritics insensitive containment check."""
    if not keyword:
        return False
    return fold(keyword.lower().strip()) in fold(strip_placeholders(text).lower())


def slot_values(draft: Draft) -> dict[str, str]:
    return dict(draft.parts.get("slots", {}))


def slot_text(draft: Draft, slot_id: str) -> str:
    """Slot value without placeholders; empty while the slot is still open."""
    return strip_placeholders(draft.parts.get("slots", {}).get(slot_id, "")).strip()


# -- disclosure, engagement bait, calls to action -----------------------------------------
DISCLOSURE_TAG = {"en": "#ad", "cs": "#reklama"}
_DISCLOSURE_RE = re.compile(
    r"(?<![\w#])#(?:ad|advert|advertisement|sponsored|paidpartnership|reklama|spoluprace|sponzorovano)(?!\w)"
    r"|\bpaid partnership\b|\bsponsored\b|\badvertisement\b"
    r"|\breklam(?:a|u|ni|ou|y|e)\b|\bspolupr(?:ace|aci|acuj\w*)\b|\bsponzorovan(?:o|y|a|e)\b"
)


def has_disclosure(text: str) -> bool:
    """True when the text carries a paid or sponsored content disclosure (English or Czech)."""
    return bool(_DISCLOSURE_RE.search(fold(strip_placeholders(text)).lower()))


_BAIT_PATTERNS = [re.compile(p) for p in (
    # English
    r"\b(?:like|share|tag|follow|comment|repost|retweet)\b[^.!?\n]{0,60}\bto (?:win|enter|be entered|get entered)\b",
    r"\btag (?:a |an |your |some |two |three |\d+ )?(?:friend|friends|mate|mates|buddy|colleague|colleagues|someone|somebody)\b",
    r"\b(?:comment|type)\s+[\"']?(?:yes|amen|me|1|interested|ready|done)\b",
    r"\b(?:like|double[ -]?tap|tap the heart)\b[^.!?\n]{0,25}\bif you\b",
    r"\bsmash (?:that|the) like\b",
    r"\b(?:like|share)\s+(?:and|&|or)\s+(?:share|like|follow|comment|subscribe)\b",
    r"\bshare (?:this )?(?:post )?with \d+ (?:friends|people)\b",
    r"\bshare (?:this )?(?:post )?(?:to|if)\b[^.!?\n]{0,30}\b(?:win|agree|enter)\b",
    # Czech (matched on text without diacritics)
    r"\boznac(?:te|it)?\b[^.!?\n]{0,25}\b(?:kamarad\w*|pritel\w*|kolegu|kolegy|nekoho|kamosku|kamose)\b",
    r"\b(?:dej|dejte|pridej|pridejte)\s+(?:nam\s+)?(?:like|lajk|srdicko|palec)\b",
    r"\blajk(?:ni|nete|ujte|uj)\b",
    r"\b(?:sdilej\w*|lajk\w*|komentuj\w*|oznac\w*)\b[^.!?\n]{0,50}\b(?:vyhr\w+|o vyhru|do slosovani|ke slosovani)\b",
    r"\b(?:komentuj|komentujte|napis|napiste|odpovez|odpovezte)\s+[\"']?(?:ano|ne|1|ja|chci|hotovo|amen)\b",
    r"\b(?:like|lajk)\s+(?:a|nebo)\s+(?:sdilej|sdilejte|komentuj|komentujte|sleduj|sledujte)\b",
    r"\bsdilej\w*[^.!?\n]{0,15}\b\d+\s+(?:kamarad\w*|pratel\w*)",
)]


def engagement_bait(text: str) -> list[str]:
    """Matched engagement bait phrases (like or share to win, tag a friend, comment YES), English and Czech."""
    t = fold(strip_placeholders(text)).lower()
    found: list[str] = []
    for pat in _BAIT_PATTERNS:
        m = pat.search(t)
        if m:
            found.append(m.group(0).strip())
    return found


_CTA_RE = re.compile(
    r"\b(?:learn more|read more|read on|download|sign up|subscribe|join|try|start|book|get started|get your|"
    r"get the|check out|see how|find out|discover|shop|order|buy|register|contact|call|visit|follow|comment|"
    r"share|tell us|let us know|reply|message|save|bookmark|"
    r"zjistete|zjisti|prectete|stahnete|zaregistrujte|zaregistruj|prihlaste|prihlas|pridejte|vyzkousejte|"
    r"vyzkousej|zacnete|zacni|rezervujte|objednejte|kupte|ziskejte|napiste|napis|sdilejte|sdilej|sledujte|"
    r"sleduj|dejte vedet|zeptejte|zeptej|odpovezte|odpovez|navstivte|kontaktujte|volejte|ulozte|uloz|"
    r"podivejte|mrknete|zkuste|zkus|kliknete|klikni)\b"
)


def has_cta(text: str, cta: str | None = None) -> bool:
    """True when the text contains the brief's CTA or a call to action verb (English or Czech)."""
    t = fold(strip_placeholders(text)).lower()
    if cta and fold(cta.lower().strip()) in t:
        return True
    return bool(_CTA_RE.search(t))
