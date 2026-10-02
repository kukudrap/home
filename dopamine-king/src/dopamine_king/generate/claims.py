"""Claims profile: stricter, evidence-aware rules for regulated wellness copy.

The first profile is "wellness": copy for a NON-MEDICAL light device (photobiomodulation panels). Such
copy may speak about regeneration, routines and how the technology works, with hedged and sourced
wording, but never about diagnosis, treatment, prevention or relief of a disease, condition or symptom.

Everything is data driven. A vertical ships ``claims.json`` (claim topics: class, outcome words, safe and
unsafe wording, evidence label) and ``guard.json`` (term lists for verbs, diseases, regulated status,
absolute safety words, hedges, safety terms). This module compiles them and finds hits; ``guard.py`` turns
hits into issues. The rules are a heuristic reviewer, not a lawyer.

Matching works on the folded text (lower case, no diacritics), which the Trust Shield already builds, so
Czech typed without diacritics is caught too. Term lists are plain words WITH diacritics; a trailing
asterisk is a stem wildcard (``lecb*``). The JavaScript game ships the same lists and the same compiler.
"""
from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from ..scoring import fold

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "verticals"
CLASS_RANK = {"context": 0, "wellness": 1, "cosmetic": 2, "medical": 3, "avoid": 4}
WINDOW = 5                                       # words allowed between a verb and an outcome word
SEP = r"[^\w.!?;\n]+"                            # separator that never crosses a sentence boundary

# severity, English message, Czech message (format fields in braces)
RULES: dict[str, tuple[str, str, str]] = {
    "CLAIM_MEDICAL": ("error",
        "Medical claim ({topic}): it speaks about treating, relieving or preventing a condition or symptom. Not "
        "allowed for a non-medical wellness device. Evidence label for this topic: {label}. Safer: {safe}",
        "Zdravotní tvrzení ({topic}): mluví o léčbě, zmírnění nebo prevenci stavu či příznaku. Pro nezdravotnický "
        "wellness přístroj není dovoleno. Síla důkazů pro toto téma: {label}. Bezpečněji: {safe}"),
    "CLAIM_AVOID": ("error",
        "Unsupported or risky claim ({topic}). Remove it. Evidence label for this topic: {label}. Safer: {safe}",
        "Nepodložené nebo rizikové tvrzení ({topic}). Odstraňte ho. Síla důkazů pro toto téma: {label}. Bezpečněji: {safe}"),
    "CLAIM_UNHEDGED": ("warn",
        "Benefit stated as a fact ({topic}). Hedge it (may, some studies) or cite a vetted source, and keep it to "
        "healthy people. Evidence label for this topic: {label}. Safer: {safe}",
        "Přínos uvedený jako fakt ({topic}). Zmírněte ho (může, některé studie) nebo citujte ověřený zdroj a držte se "
        "zdravých lidí. Síla důkazů pro toto téma: {label}. Bezpečněji: {safe}"),
    "DISEASE_MENTION": ("error",
        "A disease, condition or symptom appears next to a treatment or benefit word. Descriptions of a "
        "non-medical device must not mention diagnosis, treatment or prevention of disease.",
        "Nemoc, stav nebo příznak je vedle slova o léčbě či přínosu. Popis nezdravotnického přístroje nesmí "
        "zmiňovat diagnostiku, léčbu ani prevenci nemocí."),
    "STATUS_CLAIM": ("error",
        "Regulatory or quality status claim that the brief facts do not back (medical device, FDA, medical grade, "
        "doctor recommended). Remove it or add the verified fact to the brief.",
        "Tvrzení o regulačním nebo kvalitativním statusu, které fakta zadání nepodporují (zdravotnický prostředek, "
        "FDA, lékařská kvalita, doporučeno lékaři). Odstraňte ho nebo přidejte ověřený fakt do zadání."),
    "SAFETY_ABSOLUTE": ("error",
        "Absolute safety claim (no side effects, safe for everyone, no risk). Light devices have cautions; say how to "
        "use the device safely instead.",
        "Absolutní tvrzení o bezpečnosti (bez vedlejších účinků, bezpečné pro každého, bez rizika). Světelné přístroje "
        "mají upozornění; raději popište, jak je používat bezpečně."),
    "OUTCOME_PROMISE": ("warn",
        "Outcome promised within a time frame. Results differ between people; describe a routine instead of a "
        "guaranteed result.",
        "Slib výsledku v určité době. Výsledky se u lidí liší; popište raději rutinu než zaručený výsledek."),
    "DOSE_NOT_FROM_MANUAL": ("warn",
        "A time, distance or dose is given that the brief facts do not contain. Usage figures must come from the "
        "manufacturer's manual: add them to the brief facts or remove them.",
        "Je uvedena doba, vzdálenost nebo dávka, kterou fakta zadání neobsahují. Údaje o používání musí pocházet z "
        "návodu výrobce: přidejte je do faktů zadání nebo je odstraňte."),
    "SAFETY_NOTE_MISSING": ("warn",
        "Long-form content about using a light device needs a safety note (eyes, doctor if pregnant or on "
        "light-sensitising medicine, follow the manual).",
        "Delší obsah o používání světelného přístroje potřebuje bezpečnostní upozornění (oči, lékař při těhotenství "
        "nebo lécích zvyšujících citlivost na světlo, řídit se návodem)."),
    "THERAPY_WORD": ("info",
        "The word 'therapy' can suggest medical treatment. For a non-medical device consider 'session', "
        "'light routine' or 'photobiomodulation'. Check the wording with your regulatory adviser.",
        "Slovo 'terapie' může naznačovat léčbu. U nezdravotnického přístroje zvažte 'sezení', 'světelná rutina' nebo "
        "'fotobiomodulace'. Formulaci si ověřte u svého regulatorního poradce."),
}


# -- term compiler (the JavaScript port in web/src/claims.js mirrors this exactly) -------------------------
def term_regex(term: str) -> str:
    """Regex for one plain term: folded, words joined by space or hyphen, a trailing ``*`` on a word is a stem wildcard."""
    words = []
    for word in fold(term.strip().lower()).split():
        star = word.endswith("*")
        word = word.rstrip("*")
        if word:
            words.append(re.escape(word) + (r"\w*" if star else ""))
    return r"[\s-]+".join(words)


def terms_regex(terms: Iterable[str]) -> str:
    """One alternation for many terms, longest first, with word boundaries."""
    parts = sorted({term_regex(t) for t in terms if t and term_regex(t)}, key=len, reverse=True)
    return r"\b(?:" + "|".join(parts) + r")\b" if parts else r"(?!x)x"


def _both(table: dict[str, list[str]] | None) -> list[str]:
    table = table or {}
    return list(table.get("en", [])) + list(table.get("cs", []))


def proximity(first: str, second: str, window: int = WINDOW) -> str:
    """``first`` and ``second`` within ``window`` words in either order, never across a sentence end."""
    gap = rf"(?:{SEP}\w+){{0,{window}}}{SEP}"
    return rf"(?:{first}{gap}{second}|{second}{gap}{first})"


@dataclass
class ClaimTopic:
    id: str
    klass: str
    name_en: str
    name_cs: str
    nouns: list[str]
    safe_en: list[str] = field(default_factory=list)
    safe_cs: list[str] = field(default_factory=list)
    label: str = "none"
    regex: re.Pattern[str] | None = None
    patterns: list[re.Pattern[str]] = field(default_factory=list)

    def name(self, lang: str) -> str:
        return self.name_cs if lang == "cs" else self.name_en

    def safe(self, lang: str) -> str:
        options = self.safe_cs if lang == "cs" else self.safe_en
        return options[0] if options else ("neuvádějte toto tvrzení" if lang == "cs" else "do not make this claim")


@dataclass
class Hit:
    code: str
    start: int
    end: int
    topic: ClaimTopic | None = None
    fmt: dict[str, Any] = field(default_factory=dict)


class ClaimsProfile:
    """Compiled claim topics and term lists of one vertical, ready to scan folded text."""

    def __init__(self, claims: dict[str, Any], guard: dict[str, Any], profile: str = "wellness") -> None:
        self.profile = profile
        self.guard = guard
        verbs_all = _both(guard.get("treatment_verbs")) + _both(guard.get("benefit_verbs"))
        self.verb_re = terms_regex(verbs_all)
        self.disease_re = terms_regex(_both(guard.get("disease_terms")))
        self.device_re = terms_regex(_both(guard.get("device_words")))
        self.prep_re = terms_regex(_both(guard.get("indication_prepositions")))
        self.status_re = re.compile(terms_regex(_both(guard.get("regulated_status"))))
        self.safety_abs_re = re.compile(terms_regex(_both(guard.get("safety_absolute"))))
        self.therapy_re = re.compile(terms_regex(_both(guard.get("therapy_words"))))
        self.hedge_re = re.compile(terms_regex(_both(guard.get("hedge_words"))))
        self.safety_terms_re = re.compile(terms_regex(_both(guard.get("safety_terms"))))
        negation = [re.escape(fold(w.lower())) for w in _both(guard.get("negation_words"))]
        self.neg_re = re.compile(r"\b(?:" + "|".join(negation) + r")\b[^.!?;\n]{0,40}$") if negation else re.compile(r"(?!x)x")
        stems = guard.get("negated_verb_stems") or []
        self.neg_verb_re = re.compile(r"\bne(?:" + "|".join(stems) + r")\w*\b") if stems else re.compile(r"(?!x)x")
        self.timeline = [re.compile(p) for p in (guard.get("timeline_patterns", {}).get("en", []) + guard.get("timeline_patterns", {}).get("cs", []))]
        self.dose = [re.compile(p) for p in (guard.get("dose_patterns", {}).get("en", []) + guard.get("dose_patterns", {}).get("cs", []))]
        self.dose_ctx = re.compile(terms_regex(_both(guard.get("dose_context"))))
        self.long_form = tuple(guard.get("long_form_formats", ()))
        self.footer = guard.get("safety_footer", {})
        self.topics: list[ClaimTopic] = []
        indication = rf"(?:{self.device_re}{SEP}(?:{self.prep_re}{SEP})(?:\w+{SEP}){{0,3}}?)"
        for t in claims.get("topics", []):
            nouns = list(t.get("nouns_en", [])) + list(t.get("nouns_cs", []))
            topic = ClaimTopic(
                id=t["id"], klass=t["class"], name_en=t["name_en"], name_cs=t["name_cs"], nouns=nouns,
                safe_en=list(t.get("safe_en", [])), safe_cs=list(t.get("safe_cs", [])), label=t.get("label_cap", "none"),
            )
            if nouns:
                noun_re = terms_regex(nouns)
                topic.regex = re.compile(proximity(self.verb_re, noun_re))
                if topic.klass in ("medical", "avoid"):
                    topic.patterns.append(re.compile(rf"{indication}{noun_re}"))
            topic.patterns += [re.compile(p) for p in t.get("patterns", [])]
            self.topics.append(topic)
        self.disease_regex = re.compile(proximity(self.verb_re, self.disease_re))
        self.disease_indication = re.compile(rf"{indication}{self.disease_re}")

    # -- helpers ---------------------------------------------------------------------------------------
    @staticmethod
    def _sentence_of(spans: list[tuple[int, int]], pos: int) -> tuple[int, int]:
        for a, b in spans:
            if a <= pos < b or pos < a:
                return a, b
        return spans[-1] if spans else (0, 0)

    def negated(self, low: str, start: int, end: int, spans: list[tuple[int, int]]) -> bool:
        """The hit sits in a negated clause ("does not treat", "neslouží k léčbě", "bez rizika")."""
        a, _ = self._sentence_of(spans, start)
        before = low[max(a, start - 60):start]
        if self.neg_re.search(before):
            return True
        return bool(self.neg_verb_re.search(low[max(a, start - 40):end]))

    def hedged(self, low: str, start: int, spans: list[tuple[int, int]]) -> bool:
        a, b = self._sentence_of(spans, start)
        return bool(self.hedge_re.search(low[a:b]))

    # -- scanning --------------------------------------------------------------------------------------
    def scan(self, text: str, low: str, *, spans: list[tuple[int, int]], skip: Callable[[int, int], bool],
             backed: Callable[[str], bool], cited_near: Callable[[int], bool], is_question: Callable[[int], bool],
             format_id: str | None = None) -> list[Hit]:
        hits: list[Hit] = []

        def usable(a: int, b: int) -> bool:
            return not skip(a, b) and not self.negated(low, a, b, spans)

        candidates: list[Hit] = []
        for topic in self.topics:
            for rx in ([topic.regex] if topic.regex else []) + topic.patterns:
                for m in rx.finditer(low):
                    a, b = m.span()
                    if not usable(a, b) or is_question(b):
                        continue
                    if topic.klass == "medical":
                        code = "CLAIM_MEDICAL"
                    elif topic.klass == "avoid":
                        code = "CLAIM_AVOID"
                    elif self.hedged(low, a, spans) or cited_near(a) or backed(m.group()):
                        continue
                    else:
                        code = "CLAIM_UNHEDGED"
                    candidates.append(Hit(code, a, b, topic))
        # the strictest class wins where hits of several topics overlap
        candidates.sort(key=lambda h: (-CLASS_RANK[h.topic.klass], h.start))  # type: ignore[union-attr]
        for h in candidates:
            if not any(k.start < h.end and h.start < k.end for k in hits):
                hits.append(h)
        hits.sort(key=lambda h: h.start)
        taken = [(h.start, h.end) for h in hits]

        def free(a: int, b: int) -> bool:
            return not any(x < b and a < y for x, y in taken)

        for rx in (self.disease_regex, self.disease_indication):
            for m in rx.finditer(low):
                a, b = m.span()
                if usable(a, b) and free(a, b) and not is_question(b):
                    hits.append(Hit("DISEASE_MENTION", a, b))
                    taken.append((a, b))
        for m in self.status_re.finditer(low):
            a, b = m.span()
            if usable(a, b) and not backed(m.group()):
                hits.append(Hit("STATUS_CLAIM", a, b))
        for m in self.safety_abs_re.finditer(low):
            a, b = m.span()
            if usable(a, b):
                hits.append(Hit("SAFETY_ABSOLUTE", a, b))
        for rx in self.timeline:
            for m in rx.finditer(low):
                a, b = m.span()
                if usable(a, b) and not is_question(b):
                    hits.append(Hit("OUTCOME_PROMISE", a, b))
        seen_dose: set[str] = set()
        for rx in self.dose:
            for m in rx.finditer(low):
                a, b = m.span()
                key = m.group()
                sa, sb = self._sentence_of(spans, a)
                if key in seen_dose or skip(a, b) or backed(key) or not self.dose_ctx.search(low[sa:sb]):
                    continue
                seen_dose.add(key)
                hits.append(Hit("DOSE_NOT_FROM_MANUAL", a, b))
        m = self.therapy_re.search(low)
        if m and not skip(*m.span()) and not self.negated(low, *m.span(), spans):
            hits.append(Hit("THERAPY_WORD", *m.span()))
        if format_id in self.long_form and not self.safety_terms_re.search(low):
            hits.append(Hit("SAFETY_NOTE_MISSING", 0, 0))
        return hits


# -- loading -----------------------------------------------------------------------------------------------
def _read(vertical: str, name: str) -> dict[str, Any]:
    path = DATA_DIR / vertical / name
    return json.loads(path.read_text("utf-8"))


@functools.lru_cache(maxsize=8)
def load_profile(vertical: str = "pbm", profile: str = "wellness") -> ClaimsProfile:
    """Compile the claims profile of a vertical (cached)."""
    return ClaimsProfile(_read(vertical, "claims.json"), _read(vertical, "guard.json"), profile)


def profile_for(brief: Any) -> ClaimsProfile | None:
    """The profile a brief asks for, or None for the general profile."""
    name = getattr(brief, "claims_profile", "general") if brief is not None else "general"
    if not name or name == "general":
        return None
    vertical = getattr(brief, "vertical", None) or "pbm"
    try:
        return load_profile(vertical, name)
    except FileNotFoundError:
        return None
