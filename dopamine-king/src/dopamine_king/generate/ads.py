"""Ad and email builders and validators: Google responsive search ads, Meta ads, LinkedIn ads and email
subject lines with preheaders.

Slot defaults only restate the brief (keyword, brand, topic, offer, CTA, secondary keywords, hooks from the
hook library). Persuasive copy, proof and benefits have no default, so the offline draft shows placeholders.
Validators measure real content and ignore ``[[ADD: ...]]`` placeholders.
"""
from __future__ import annotations

import re
from typing import Any

from ..scoring import fold
from .formats import (
    brief_meta, caps_words, emoji_count, fit, keyword_in, lang_of, pick, record_replaced_hook, slot_text,
    standard_notes, strip_placeholders,
)
from .hooks import cached_score, generate_hooks
from .types import Brief, Draft, FormatSpec, Issue, Skeleton, Slot

# platform limits checked 2026-10, verify before publishing
RSA_HEADLINES = 15
RSA_HEADLINE_CHARS = 30
RSA_DESCRIPTIONS = 4
RSA_DESCRIPTION_CHARS = 90
RSA_MIN_HEADLINES = 3
RSA_MIN_DESCRIPTIONS = 2
RSA_MAX_EXCLAMATION_HEADLINES = 2
RSA_KEYWORD_HEADLINES = 2         # headlines that should carry the keyword
META_VARIANTS = 3
META_PRIMARY_VISIBLE = 125
META_PRIMARY_MAX = 500
META_HEADLINE_MAX = 40
META_DESCRIPTION_MAX = 30
LINKEDIN_INTRO_RECOMMENDED = 150
LINKEDIN_INTRO_MAX = 600
LINKEDIN_HEADLINE_RECOMMENDED = 70
LINKEDIN_HEADLINE_MAX = 200
LINKEDIN_CTA_BUTTONS = ("Apply", "Download", "View quote", "Learn more", "Sign up", "Subscribe", "Register", "Join",
                        "Attend", "Request demo")
EMAIL_SUBJECTS = 10
EMAIL_SUBJECT_MAX = 50
EMAIL_PREHEADER = (40, 100)
CLICKBAIT_RISK_MAX = 0.35

HEADLINE_MIX: dict[str, list[str]] = {
    "keyword": ["h01", "h02", "h03", "h04"],
    "benefit": ["h05", "h06", "h07", "h08"],
    "proof": ["h09", "h10", "h11"],
    "cta": ["h12", "h13"],
    "brand": ["h14", "h15"],
}
_NO_NOTE = {"", "n/a", "na", "none", "no", "ne", "zadne", "zadna", "-"}

# Superlatives and absolute claims that need a substantiation note. Matched on lower-cased text without diacritics.
_CLAIM_RE = re.compile("|".join((
    r"\bbest\b(?! practices?\b)", r"(?<!\w)#\s?1\b", r"\bno\.? ?1\b", r"\bnumber (?:one|1)\b", r"\bguarantee[sd]?\b",
    r"\bleading (?:brand|provider|company|platform|manufacturer|maker|supplier|retailer|expert|authority|source|name|choice)\b",
    r"\btop[- ]rated\b", r"\bcheapest\b", r"\blowest price\b", r"\bfastest\b", r"\bunbeatable\b", r"\brisk[- ]free\b",
    r"\bproven\b", r"\bmiracle\b", r"\b100\s?% (?:satisfaction|guarantee\w*|safe|effective|success\w*|secure|accurate|results?)\b",
    r"\bworld'?s (?:best|first|leading)\b",
    r"\bcislo (?:1|jedna)\b", r"\bc\. ?1\b", r"\bgarantovan\w*", r"\bgarantujeme\b", r"\bgarance\b", r"\bzarucen\w*",
    r"\bnejlepsi\b", r"\bnejlevnejsi\b", r"\bnejrychlejsi\b", r"\bnejvyhodnejsi\b", r"\bnejkvalitnejsi\b",
    r"\bnejvetsi\b", r"\bnejoblibenejsi\b", r"\bnejlepe\b", r"\bjediny\b", r"\bbez rizika\b",
    r"\bvedouci (?:dodavatel|vyrobce|znacka|firma|poskytovatel|pozice|postaveni|specialista|expert)\b",
    r"\bosvedcen\w*", r"\bzazracn\w*", r"\bstoprocentn\w*",
    r"\b100\s?% (?:spokojenost|garance|bezpecn\w*|ucinn\w*|uspesn\w*)",
)))


def claim_hits(text: str) -> list[str]:
    """Superlative, ranking or guarantee claims in the text (English and Czech)."""
    t = fold(strip_placeholders(text)).lower()
    return [m.group(0) for m in _CLAIM_RE.finditer(t)]


def _has_substantiation(draft: Draft) -> bool:
    note = slot_text(draft, "substantiation").strip().lower().rstrip(".")
    return note not in _NO_NOTE


def claim_issues(draft: Draft, texts: dict[str, str]) -> list[Issue]:
    """UNSUBSTANTIATED_CLAIM warnings for every text with a claim, unless a substantiation note is given."""
    if _has_substantiation(draft):
        return []
    out = []
    for where, text in texts.items():
        hits = claim_hits(text)
        if hits:
            out.append(Issue("warn", "UNSUBSTANTIATED_CLAIM",
                             f"Claim without substantiation ({', '.join(sorted(set(hits)))}): add a proof source in the substantiation note or reword.",
                             where))
    return out


def _substantiation_slot() -> Slot:
    return Slot("substantiation", "Substantiation note: the source for any superlative, ranking or guarantee used above "
                                  "(study, award, date). Write 'n/a' when no such claim is used.", max_chars=300, kind="line")


def _cap(text: str) -> str:
    """Capitalise the first letter unless the first word is mixed case (iPhone, eBay)."""
    words = text.split()
    return text[:1].upper() + text[1:] if words and words[0].islower() else text


def _cap_fit(text: str | None, max_chars: int) -> str | None:
    """Brief text capitalised for display when it fits the limit, else None."""
    t = fit(text, max_chars=max_chars)
    return _cap(t) if t else None


def _numbered(prefix: str, count: int, width: int = 2) -> list[str]:
    return [f"{prefix}{i:0{width}d}" if width else f"{prefix}{i}" for i in range(1, count + 1)]


def check_limit(issues: list[Issue], text: str, limit: int, where: str, *, code: str = "CHAR_LIMIT", severity: str = "error") -> None:
    if len(text) > limit:
        issues.append(Issue(severity, code, f"{len(text)} characters, the limit is {limit}.", where))


# -- Google responsive search ad ---------------------------------------------------------------------
def rsa_headline_defaults(brief: Brief, hook: str | None) -> dict[str, str]:
    """Defaults restating only brief fields that fit 30 characters, without duplicates."""
    out: dict[str, str] = {}
    seen: set[str] = set()

    def distinct(text: str | None) -> str | None:
        t = fit(text, max_chars=RSA_HEADLINE_CHARS)
        if not t or fold(t).lower() in seen:
            return None
        seen.add(fold(t).lower())
        return _cap(t)

    keyword_texts = [distinct(t) for t in (hook, brief.primary_keyword, brief.topic, *brief.secondary_keywords)]
    for sid, text in zip(HEADLINE_MIX["keyword"], [t for t in keyword_texts if t]):
        out[sid] = text
    for sid, text in (("h12", brief.cta), ("h13", brief.offer), ("h14", brief.brand), ("h15", f"{brief.brand}: {brief.topic}")):
        t = distinct(text)
        if t:
            out[sid] = t
    return out


def build_google_rsa(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Responsive search ad: 15 headlines (30 chars) and 4 descriptions (90 chars)."""
    kw = brief.primary_keyword
    defaults = rsa_headline_defaults(brief, hook)
    kind_of = {sid: kind for kind, ids in HEADLINE_MIX.items() for sid in ids}
    what = {
        "keyword": f"keyword type: contain or closely match '{kw}'.",
        "benefit": f"benefit type: one concrete benefit for {brief.audience}; no superlatives without proof.",
        "proof": "proof type: a verifiable fact from the brief (number, certification, years in business). Leave open if none.",
        "cta": "call to action type: one clear next step.",
        "brand": "brand type: the brand name or a brand line.",
    }
    slots: list[Slot] = []
    for sid in _numbered("h", RSA_HEADLINES):
        kind = kind_of[sid]
        slots.append(Slot(sid, f"Headline, max {RSA_HEADLINE_CHARS} chars, {what[kind]}", max_chars=RSA_HEADLINE_CHARS,
                          kind="title", default=defaults.get(sid)))
    d_what = {1: f"states the main benefit for {brief.audience} and includes the keyword '{kw}'", 2: "answers the biggest objection or risk",
              3: "adds a verifiable proof point from the brief", 4: "ends with a clear call to action"}
    for i in range(1, RSA_DESCRIPTIONS + 1):
        slots.append(Slot(f"d{i}", f"Description {i}, max {RSA_DESCRIPTION_CHARS} chars: {d_what[i]}.", max_chars=RSA_DESCRIPTION_CHARS,
                          kind="line", default=fit(brief.cta, max_chars=RSA_DESCRIPTION_CHARS) if i == 4 else None))
    slots.append(_substantiation_slot())
    head = pick(lang_of(brief), ("Headlines", "Descriptions"), ("Nadpisy", "Popisy"))
    parts = [f"## {head[0]} ({RSA_HEADLINE_CHARS})\n\n" + "\n".join(f"{i}. " + "{{h%02d}}" % i for i in range(1, RSA_HEADLINES + 1)),
             f"## {head[1]} ({RSA_DESCRIPTION_CHARS})\n\n" + "\n".join(f"{i}. " + "{{d%d}}" % i for i in range(1, RSA_DESCRIPTIONS + 1)),
             "**" + pick(lang_of(brief), "Substantiation", "Doložení tvrzení") + ":** {{substantiation}}"]

    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        return {"headlines": [values[s] for s in _numbered("h", RSA_HEADLINES)],
                "descriptions": [values[f"d{i}"] for i in range(1, RSA_DESCRIPTIONS + 1)]}

    return record_replaced_hook(Skeleton(
        format="google_rsa", lang=lang_of(brief), template="\n\n".join(parts), slots=slots,
        fixed={"headline_mix": HEADLINE_MIX, "headline_chars": RSA_HEADLINE_CHARS, "description_chars": RSA_DESCRIPTION_CHARS},
        meta=brief_meta(brief), hook_slot="h01", assemble=assemble,
        notes=standard_notes(brief, "Mix: keyword, benefit, proof, CTA and brand headlines. Include the keyword in at least two headlines "
                                    "and one description. Headlines must be unique and must not be pinned unless required."),
    ), hook)


def validate_google_rsa(draft: Draft) -> list[Issue]:
    issues: list[Issue] = []
    heads = {s: slot_text(draft, s) for s in _numbered("h", RSA_HEADLINES) if s in draft.parts.get("slots", {})}
    descs = {s: slot_text(draft, s) for s in (f"d{i}" for i in range(1, RSA_DESCRIPTIONS + 1)) if s in draft.parts.get("slots", {})}
    for s, t in heads.items():
        check_limit(issues, t, RSA_HEADLINE_CHARS, s)
    for s, t in descs.items():
        check_limit(issues, t, RSA_DESCRIPTION_CHARS, s)
    for group, label in ((heads, "headline"), (descs, "description")):
        seen: dict[str, str] = {}
        for s, t in group.items():
            key = fold(t).lower().strip(" .!?")
            if not key:
                continue
            if key in seen:
                issues.append(Issue("error", "DUPLICATE_ASSET", f"Duplicate {label}: same as {seen[key]}.", s))
            seen.setdefault(key, s)
    filled_h = [t for t in heads.values() if t]
    filled_d = [t for t in descs.values() if t]
    if not draft.slots_open:
        if len(filled_h) < RSA_MIN_HEADLINES:
            issues.append(Issue("error", "TOO_FEW_ASSETS", f"Google needs at least {RSA_MIN_HEADLINES} headlines."))
        if len(filled_d) < RSA_MIN_DESCRIPTIONS:
            issues.append(Issue("error", "TOO_FEW_ASSETS", f"Google needs at least {RSA_MIN_DESCRIPTIONS} descriptions."))
    kw = draft.meta.get("primary_keyword")
    if kw and not any(s in draft.slots_open for s in heads):
        hits = sum(1 for t in filled_h if keyword_in(t, kw, draft.lang))
        if hits < RSA_KEYWORD_HEADLINES:
            issues.append(Issue("warn", "KEYWORD_COVERAGE", f"Only {hits} headline(s) contain the keyword '{kw}', aim for {RSA_KEYWORD_HEADLINES} or more."))
    if kw and filled_d and not any(s in draft.slots_open for s in descs) and not any(keyword_in(t, kw, draft.lang) for t in filled_d):
        issues.append(Issue("warn", "KEYWORD_COVERAGE", f"No description contains the keyword '{kw}'."))
    # Google Ads editorial policy may disallow exclamation marks in headlines; verify before publishing.
    bangs = [s for s, t in heads.items() if "!" in t]
    if len(bangs) > RSA_MAX_EXCLAMATION_HEADLINES:
        issues.append(Issue("warn", "EXCLAMATION_LIMIT", f"{len(bangs)} headlines use an exclamation mark, keep it to {RSA_MAX_EXCLAMATION_HEADLINES} at most."))
    for s, t in {**heads, **descs}.items():
        if len(caps_words(t)) >= 1 and len(caps_words(t)) >= len(t.split()) / 2:
            issues.append(Issue("warn", "ALL_CAPS", "Avoid words in all capitals.", s))
    issues += claim_issues(draft, {**heads, **descs})
    return issues


# -- Meta ad -------------------------------------------------------------------------------------------
def _hook_variants(brief: Brief, hook: str | None, n: int, max_chars: int) -> list[str]:
    """Up to n distinct hooks within max_chars; a caller supplied hook goes first."""
    out: list[str] = []
    if fit(hook, max_chars=max_chars):
        out.append(hook.strip())
    for c in generate_hooks(brief, n=n + 2, max_chars=max_chars):
        if len(out) >= n:
            break
        if c.text not in out:
            out.append(c.text)
    return out[:n]


def build_meta_ad(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Meta (Facebook and Instagram) ad with three variants of primary text, headline and description."""
    lang = lang_of(brief)
    hooks = _hook_variants(brief, hook, META_VARIANTS, META_PRIMARY_VISIBLE)
    head_defaults = [_cap_fit(t, META_HEADLINE_MAX) for t in (brief.offer, brief.cta, brief.primary_keyword)]
    slots: list[Slot] = []
    blocks: list[str] = []
    for i in range(1, META_VARIANTS + 1):
        slots.append(Slot(f"primary_{i}", f"Primary text for variant {i}, max {META_PRIMARY_MAX} chars; the first {META_PRIMARY_VISIBLE} "
                                          f"are all that shows before 'See more', so put the hook and the point there.",
                          max_chars=META_PRIMARY_MAX, kind="text", default=hooks[i - 1] if i <= len(hooks) else None))
        slots.append(Slot(f"headline_{i}", f"Headline for variant {i}, max {META_HEADLINE_MAX} chars: the offer or the benefit.",
                          max_chars=META_HEADLINE_MAX, kind="title", default=head_defaults[i - 1]))
        slots.append(Slot(f"description_{i}", f"Description for variant {i}, max {META_DESCRIPTION_MAX} chars (often hidden).",
                          max_chars=META_DESCRIPTION_MAX, kind="line"))
        blocks.append(f"## {pick(lang, 'Variant', 'Varianta')} {i}\n\n" + "- **" + pick(lang, "Primary text", "Primární text") + ":** {{primary_%d}}\n" % i
                      + "- **" + pick(lang, "Headline", "Nadpis") + ":** {{headline_%d}}\n" % i
                      + "- **" + pick(lang, "Description", "Popis") + ":** {{description_%d}}" % i)
    slots.append(_substantiation_slot())
    blocks.append("**" + pick(lang, "Substantiation", "Doložení tvrzení") + ":** {{substantiation}}")

    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        return {"variants": [{"n": i, "primary_text": values[f"primary_{i}"], "headline": values[f"headline_{i}"],
                              "description": values[f"description_{i}"]} for i in range(1, META_VARIANTS + 1)]}

    return record_replaced_hook(Skeleton(
        format="meta_ad", lang=lang, template="\n\n".join(blocks), slots=slots,
        fixed={"visible_chars": META_PRIMARY_VISIBLE, "primary_chars": META_PRIMARY_MAX, "headline_chars": META_HEADLINE_MAX,
               "description_chars": META_DESCRIPTION_MAX, "variants": META_VARIANTS},
        meta=brief_meta(brief), hook_slot="primary_1", assemble=assemble,
        notes=standard_notes(brief, "Test the three variants against each other: change one thing at a time (hook, offer or format)."),
    ), hook)


def validate_meta_ad(draft: Draft) -> list[Issue]:
    issues: list[Issue] = []
    texts: dict[str, str] = {}
    for i in range(1, META_VARIANTS + 1):
        for key, limit in ((f"primary_{i}", META_PRIMARY_MAX), (f"headline_{i}", META_HEADLINE_MAX), (f"description_{i}", META_DESCRIPTION_MAX)):
            if key not in draft.parts.get("slots", {}):
                continue
            t = slot_text(draft, key)
            texts[key] = t
            check_limit(issues, t, limit, key)
        p = texts.get(f"primary_{i}", "")
        if len(p) > META_PRIMARY_VISIBLE and len(p) <= META_PRIMARY_MAX:
            issues.append(Issue("info", "VISIBLE_TEXT_CUT", f"Only the first {META_PRIMARY_VISIBLE} characters show before 'See more'; "
                                                           "keep the hook and the point inside them.", f"primary_{i}"))
    present = [t.lower() for t in texts.values() if t]
    if len(set(present)) != len(present):
        issues.append(Issue("warn", "DUPLICATE_ASSET", "Two variants share identical text."))
    issues += claim_issues(draft, texts)
    return issues


# -- LinkedIn ad ----------------------------------------------------------------------------------------
_LI_BUTTON_HINTS = (
    ("Request demo", ("demo",)), ("Download", ("download", "stahn", "e-book", "ebook", "whitepaper")),
    ("Register", ("register", "registr")), ("Sign up", ("sign up", "prihlas", "zaregistruj")),
    ("Subscribe", ("subscribe", "odebira", "newsletter")), ("Join", ("join", "pridej", "pridejte")),
    ("Apply", ("apply", "prihlask")), ("Attend", ("attend", "ucast")),
)


def linkedin_default_button(brief: Brief) -> str:
    cta = fold(brief.cta or "").lower()
    for label, hints in _LI_BUTTON_HINTS:
        if any(h in cta for h in hints):
            return label
    return "Learn more"


def build_linkedin_ad(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """LinkedIn single image ad. options: variants 1..3 (default 1)."""
    try:
        n = max(1, min(3, int((options or {}).get("variants", 1))))
    except (TypeError, ValueError):
        n = 1
    lang = lang_of(brief)
    hooks = _hook_variants(brief, hook, n, LINKEDIN_INTRO_RECOMMENDED)
    slots: list[Slot] = []
    blocks = []
    for i in range(1, n + 1):
        sfx = "" if i == 1 else f"_{i}"
        slots.append(Slot(f"intro_text{sfx}", f"Intro text{'' if n == 1 else f' for variant {i}'}: recommended max {LINKEDIN_INTRO_RECOMMENDED} chars "
                                              f"(hard max {LINKEDIN_INTRO_MAX}); lead with the hook, speak to {brief.audience}.",
                          max_chars=LINKEDIN_INTRO_MAX, kind="text", default=hooks[i - 1] if i <= len(hooks) else None))
        slots.append(Slot(f"headline{sfx}", f"Headline{'' if n == 1 else f' for variant {i}'}: recommended max {LINKEDIN_HEADLINE_RECOMMENDED} chars, "
                                            "the offer or the clearest benefit.", max_chars=LINKEDIN_HEADLINE_MAX, kind="title",
                          default=_cap_fit(brief.offer, LINKEDIN_HEADLINE_RECOMMENDED) if i == 1 else None))
        label = f"## {pick(lang, 'Variant', 'Varianta')} {i}\n\n" if n > 1 else ""
        blocks.append(label + "- **" + pick(lang, "Intro text", "Úvodní text") + ":** " + "{{intro_text%s}}\n" % sfx
                      + "- **" + pick(lang, "Headline", "Nadpis") + ":** " + "{{headline%s}}" % sfx)
    slots.append(Slot("cta_button", "Call to action button, exactly one of: " + ", ".join(LINKEDIN_CTA_BUTTONS) + ".",
                      max_chars=20, kind="line", default=linkedin_default_button(brief)))
    slots.append(_substantiation_slot())
    blocks.append("**" + pick(lang, "Button", "Tlačítko") + ":** {{cta_button}}")
    blocks.append("**" + pick(lang, "Substantiation", "Doložení tvrzení") + ":** {{substantiation}}")
    return record_replaced_hook(Skeleton(
        format="linkedin_ad", lang=lang, template="\n\n".join(blocks), slots=slots,
        fixed={"intro_recommended": LINKEDIN_INTRO_RECOMMENDED, "intro_max": LINKEDIN_INTRO_MAX,
               "headline_recommended": LINKEDIN_HEADLINE_RECOMMENDED, "headline_max": LINKEDIN_HEADLINE_MAX,
               "cta_buttons": list(LINKEDIN_CTA_BUTTONS), "variants": n},
        meta=brief_meta(brief), hook_slot="intro_text",
        notes=standard_notes(brief, "Intro text over 150 characters is cut on mobile: put the hook and the point first."),
    ), hook)


def validate_linkedin_ad(draft: Draft) -> list[Issue]:
    issues: list[Issue] = []
    texts: dict[str, str] = {}
    for key in draft.parts.get("slots", {}):
        if key.startswith("intro_text"):
            t = slot_text(draft, key)
            texts[key] = t
            check_limit(issues, t, LINKEDIN_INTRO_MAX, key)
            if LINKEDIN_INTRO_RECOMMENDED < len(t) <= LINKEDIN_INTRO_MAX:
                issues.append(Issue("warn", "LENGTH_RECOMMENDED", f"{len(t)} characters, {LINKEDIN_INTRO_RECOMMENDED} or fewer is recommended.", key))
        elif key.startswith("headline"):
            t = slot_text(draft, key)
            texts[key] = t
            check_limit(issues, t, LINKEDIN_HEADLINE_MAX, key)
            if LINKEDIN_HEADLINE_RECOMMENDED < len(t) <= LINKEDIN_HEADLINE_MAX:
                issues.append(Issue("warn", "LENGTH_RECOMMENDED", f"{len(t)} characters, {LINKEDIN_HEADLINE_RECOMMENDED} or fewer is recommended.", key))
    button = slot_text(draft, "cta_button")
    if button and button not in LINKEDIN_CTA_BUTTONS:
        issues.append(Issue("error", "INVALID_CTA_BUTTON", f"'{button}' is not one of: {', '.join(LINKEDIN_CTA_BUTTONS)}."))
    issues += claim_issues(draft, texts)
    return issues


# -- email subject set -----------------------------------------------------------------------------------
_DECEPTIVE_PREFIX_RE = re.compile(r"^\s*(?:re|fwd?|aw|odp|pf)\s*:", re.I)
_SPAM_WORDS_RE = re.compile("|".join((
    r"\bact now\b", r"\blimited time\b", r"\bclick here\b", r"\bbuy now\b", r"\bwinner\b", r"\bcongratulations\b", r"\bcash\b",
    r"\$\$+", r"\b100% free\b", r"\burgent\b", r"\blast chance\b", r"\bno obligation\b", r"\bearn money\b", r"\bmake money\b",
    r"\border now\b", r"\bdear friend\b", r"\bakce pouze dnes\b", r"\bvyhrajte\b", r"\bgratulujeme\b", r"\bposledni sance\b",
    r"\bvydelejte\b", r"\bklikn\w* zde\b", r"\bkupte ted\b", r"\bnaposledy\b",
)))


def subject_problems(subject: str) -> list[str]:
    """Deceptive or spammy patterns in a subject line (RE:/FWD: tricks, shouting, repeated punctuation)."""
    s = strip_placeholders(subject).strip()
    out = []
    if _DECEPTIVE_PREFIX_RE.match(s):
        out.append("fake reply or forward prefix")
    if s.count("!") >= 2 or re.search(r"[!?]{2,}", s):
        out.append("repeated exclamation or question marks")
    if any(len(w) >= 4 for w in caps_words(s)) or len(caps_words(s)) >= 2:
        out.append("words in ALL CAPS")
    return out


def build_email_subject_set(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Ten subject lines (at most 50 characters) ranked by Dopamine Score with preheader slots (40 to 100).

    A supplied ``hook`` is pinned to subject_01 (the hook slot); the other nine stay ranked by score.
    """
    lang = lang_of(brief)
    rows = [{"text": c.text, "style": c.style, "score": c.score, "risk": c.clickbait_risk}
            for c in generate_hooks(brief, n=EMAIL_SUBJECTS, max_chars=EMAIL_SUBJECT_MAX)]
    if fit(hook, max_chars=EMAIL_SUBJECT_MAX):      # a supplied hook that fits is pinned to the first slot, the rest stay ranked
        total, risk = cached_score(hook.strip(), lang)
        rows = ([{"text": hook.strip(), "style": "provided", "score": round(total, 2), "risk": round(risk, 4)}]
                + [r for r in rows if r["text"] != hook.strip()])[:EMAIL_SUBJECTS]
    slots: list[Slot] = []
    lines = []
    for i in range(1, EMAIL_SUBJECTS + 1):
        row = rows[i - 1] if i <= len(rows) else None
        slots.append(Slot(f"subject_{i:02d}", f"Subject line {i}, max {EMAIL_SUBJECT_MAX} chars: specific, honest, no ALL CAPS, "
                                              "one exclamation mark at most, never RE: or FWD:.",
                          max_chars=EMAIL_SUBJECT_MAX, kind="title", default=row["text"] if row else None))
        slots.append(Slot(f"preheader_{i:02d}", f"Preheader for subject {i}, {EMAIL_PREHEADER[0]} to {EMAIL_PREHEADER[1]} chars: "
                                                "continue the subject, do not repeat it.", min_chars=EMAIL_PREHEADER[0],
                          max_chars=EMAIL_PREHEADER[1], kind="line"))
        lines.append(f"{i}. **" + pick(lang, "Subject", "Předmět") + ":** " + "{{subject_%02d}}\n" % i
                     + "   **" + pick(lang, "Preheader", "Preheader") + ":** " + "{{preheader_%02d}}" % i)
    template = f"# {pick(lang, 'Email subject lines', 'Předměty e-mailu')}: {brief.topic}\n\n" + "\n".join(lines)

    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        return {"pairs": [{"n": i, "subject": values[f"subject_{i:02d}"], "preheader": values[f"preheader_{i:02d}"]}
                          for i in range(1, EMAIL_SUBJECTS + 1)]}

    return record_replaced_hook(Skeleton(
        format="email_subject_set", lang=lang, template=template, slots=slots,
        fixed={"subjects": rows, "subject_chars": EMAIL_SUBJECT_MAX, "preheader_chars": list(EMAIL_PREHEADER)},
        meta=brief_meta(brief), hook_slot="subject_01", assemble=assemble,
        notes=standard_notes(brief, "Subjects are ranked by the Dopamine Score. A/B test two or three; a subject must match what the email delivers."),
    ), hook)


def validate_email_subject_set(draft: Draft) -> list[Issue]:
    issues: list[Issue] = []
    slots = draft.parts.get("slots", {})
    seen: dict[str, str] = {}
    for key in sorted(k for k in slots if k.startswith("subject_")):
        t = slot_text(draft, key)
        check_limit(issues, t, EMAIL_SUBJECT_MAX, key)
        if not t:
            continue
        for problem in subject_problems(t):
            issues.append(Issue("error", "DECEPTIVE_SUBJECT", f"Deceptive or spammy subject: {problem}.", key))
        if _SPAM_WORDS_RE.search(fold(t).lower()):
            issues.append(Issue("warn", "SPAM_WORDS", "Contains words that trigger spam filters.", key))
        if cached_score(t, draft.lang if draft.lang in ("en", "cs") else "en")[1] > CLICKBAIT_RISK_MAX:
            issues.append(Issue("warn", "CLICKBAIT_RISK", "This subject reads as clickbait.", key))
        if emoji_count(t) > 1:
            issues.append(Issue("warn", "EMOJI_OVERUSE", "More than one emoji in a subject line.", key))
        k = fold(t).lower()
        if k in seen:
            issues.append(Issue("warn", "DUPLICATE_ASSET", f"Same subject as {seen[k]}.", key))
        seen.setdefault(k, key)
    for key in sorted(k for k in slots if k.startswith("preheader_")):
        t = slot_text(draft, key)
        if not t:
            continue
        lo, hi = EMAIL_PREHEADER
        check_limit(issues, t, hi, key)
        if len(t) < lo:
            issues.append(Issue("warn", "PREHEADER_SHORT", f"{len(t)} characters, use at least {lo} so the inbox does not fill the gap with body text.", key))
        subj = slot_text(draft, "subject_" + key.split("_", 1)[1])
        if subj and fold(subj).lower() in fold(t).lower():
            issues.append(Issue("info", "PREHEADER_REPEATS", "The preheader repeats the subject; continue the thought instead.", key))
    return issues


# -- registry ---------------------------------------------------------------------------------------------
FORMAT_SPECS: list[FormatSpec] = [
    FormatSpec(
        id="google_rsa", name_en="Google responsive search ad", name_cs="Responzivní vyhledávací reklama Google", family="ad",
        platform="google", build=build_google_rsa, validate=validate_google_rsa,
        limits={"headlines": RSA_HEADLINES, "headline_chars": RSA_HEADLINE_CHARS, "descriptions": RSA_DESCRIPTIONS,
                "description_chars": RSA_DESCRIPTION_CHARS},
        description_en="15 headlines of 30 characters and 4 descriptions of 90 characters with a keyword, benefit, proof, CTA and brand mix.",
        description_cs="15 nadpisů do 30 znaků a 4 popisy do 90 znaků se směsí klíčového slova, přínosu, důkazu, výzvy a značky."),
    FormatSpec(
        id="meta_ad", name_en="Meta ad", name_cs="Reklama na Meta", family="ad", platform="meta",
        build=build_meta_ad, validate=validate_meta_ad,
        limits={"variants": META_VARIANTS, "primary_visible": META_PRIMARY_VISIBLE, "primary_max": META_PRIMARY_MAX,
                "headline_max": META_HEADLINE_MAX, "description_max": META_DESCRIPTION_MAX},
        description_en="Three variants of primary text, headline and description for Facebook and Instagram ads.",
        description_cs="Tři varianty primárního textu, nadpisu a popisu pro reklamy na Facebooku a Instagramu."),
    FormatSpec(
        id="linkedin_ad", name_en="LinkedIn ad", name_cs="Reklama na LinkedIn", family="ad", platform="linkedin",
        build=build_linkedin_ad, validate=validate_linkedin_ad,
        limits={"intro_recommended": LINKEDIN_INTRO_RECOMMENDED, "intro_max": LINKEDIN_INTRO_MAX,
                "headline_recommended": LINKEDIN_HEADLINE_RECOMMENDED, "headline_max": LINKEDIN_HEADLINE_MAX,
                "cta_buttons": list(LINKEDIN_CTA_BUTTONS)},
        description_en="Single image ad with intro text, headline and call to action button.",
        description_cs="Reklama s jedním obrázkem, úvodním textem, nadpisem a tlačítkem výzvy k akci."),
    FormatSpec(
        id="email_subject_set", name_en="Email subject lines", name_cs="Předměty e-mailu", family="email", platform="email",
        build=build_email_subject_set, validate=validate_email_subject_set,
        limits={"subjects": EMAIL_SUBJECTS, "subject_chars": EMAIL_SUBJECT_MAX, "preheader_chars": list(EMAIL_PREHEADER)},
        description_en="Ten ranked subject lines of at most 50 characters with matching preheaders.",
        description_cs="Deset seřazených předmětů do 50 znaků s odpovídajícími preheadery."),
]
