"""Deterministic, explainable evidence grading.

The study design dominates the grade (a meta-analysis outranks an observational study however
often the latter is cited). Citations per year, peer review and retraction only adjust it.
Every step is reported in a list of human readable reasons.
"""
from __future__ import annotations

import datetime
import math
import re

from .models import Study

DESIGN_SCORES: dict[str, float] = {
    "meta-analysis": 1.0,
    "systematic-review": 1.0,
    "rct": 0.85,
    "field-experiment": 0.85,
    "lab-experiment": 0.7,
    "observational": 0.55,
    "survey": 0.5,
    "theory": 0.4,
    "preprint": 0.4,
    "qualitative": 0.35,
    "book": 0.3,
    "guideline": 0.3,
    "unknown": 0.25,
}
MAX_CITATION_BONUS = 0.1
CITATIONS_PER_YEAR_FOR_MAX = 100.0   # log scaled: 100 citations per year earns the full bonus
PEER_REVIEW_BONUS = 0.05
PREPRINT_CAP = 0.79                  # keeps unreviewed work at letter B at best
THRESHOLDS = (("A", 0.8), ("B", 0.6), ("C", 0.4))

# --- design classification --------------------------------------------------------------


def _re(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.I)


_PREPRINT_VENUE = _re(r"arxiv|ssrn|biorxiv|medrxiv|psyarxiv|socarxiv|osf preprints|research square|preprints\.org")
_META = r"meta[- ]?analy(?:sis|ses|tic|tical)\b"
_SYSTEMATIC = r"systematic(?:ally)?[- ](?:literature[- ])?(?:review|mapping|map)\b|scoping review|umbrella review"
_RCT = r"randomi[sz]ed[- ]controlled|randomi[sz]ed (?:clinical )?trials?|\brcts?\b"
_FIELD = r"field experiments?|natural experiments?|randomi[sz]ed (?:field |online )?experiments?|online controlled experiments?"
_AB_RUN = (
    r"(?:ran|run|conducted?|performed?|deployed|launched|carried out|reports?|reported)\b[^.]{0,60}?"
    r"(?:a/b[- ]?tests?|a/b[- ]?testing|split[- ]tests?)"
)
_LAB_TITLE = r"experimental (?:evidence|study|studies|investigation)|laboratory experiments?|lab experiments?"
_NUM = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten|several|multiple|a series of|a number of)"
_LAB_ABSTRACT = (
    r"participants (?:were )?randomly assigned|randomly assigned (?:to|participants)|"
    r"between[- ]subjects? (?:design|experiment)|within[- ]subjects? (?:design|experiment)|"
    r"laboratory (?:experiment|study)|lab (?:experiment|study)|"
    r"\bwe (?:\w+ ){0,2}(?:conduct|conducted|ran|run|report|reported|present|presented|perform|performed|"
    r"carried out) (?:\w+ ){0,2}?" + _NUM + r" (?:\w+[- ]){0,2}experiments?"
)
_OBSERVATIONAL = (
    r"observational (?:study|studies|data|analysis)|cohort stud|cross[- ]sectional|longitudinal (?:study|analysis)|"
    r"retrospective (?:study|analysis)|case[- ]control|panel data|archival data"
)
_SURVEY = r"\bsurvey\b|\bquestionnaire\b"
_QUALITATIVE = r"case stud(?:y|ies)|\binterviews?\b|ethnograph|grounded theory|focus groups?|thematic analysis|\bqualitative\b"
_GUIDELINE = r"\bguidelines?\b|\bbest[- ]practices?\b|\bpractical guide\b|\bwhite ?paper\b|\bplaybook\b"
_THEORY = r"\btheor(?:y|ies|etical)\b|\bframework\b|\bconceptual\b"

# (design, pattern applied to the title, pattern applied to abstract sentences that claim the design)
_RULES: tuple[tuple[str, re.Pattern[str] | None, re.Pattern[str] | None], ...] = (
    ("meta-analysis", _re(_META), _re(_META)),
    ("systematic-review", _re(_SYSTEMATIC), _re(_SYSTEMATIC)),
    ("rct", _re(_RCT), _re(_RCT)),
    ("field-experiment", _re(_FIELD), _re(_FIELD + "|" + _AB_RUN)),
    ("lab-experiment", _re(_LAB_TITLE), _re(_LAB_ABSTRACT)),
    ("observational", _re(_OBSERVATIONAL), _re(_OBSERVATIONAL)),
    ("survey", _re(_SURVEY), _re(r"\bwe survey(?:ed)?\b|\bsurvey of \d|\bquestionnaires?\b")),
    ("qualitative", _re(_QUALITATIVE), _re(_QUALITATIVE)),
    ("guideline", _re(_GUIDELINE), None),
    ("theory", _re(_THEORY), _re(_THEORY)),
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_SELF_REF = re.compile(r"\b(?:this|our|we|here|present|current|authors?|participants|respondents)\b", re.I)
_PRIOR_WORK = re.compile(r"\b(?:previous|prior|earlier|recent|existing|published|several|many|other|past)\b[^.]{0,30}$", re.I)
_BOOK_TYPES = frozenset({"book", "monograph", "edited-book", "reference-book"})
_PREPRINT_TYPES = frozenset({"preprint", "posted-content"})


def _claimed_in_abstract(pattern: re.Pattern[str], abstract: str) -> bool:
    """True when a sentence of the abstract claims the design for the paper itself.

    A mention of "previous meta-analyses" must not turn an ordinary study into a meta-analysis.
    """
    for sentence in _SENTENCE_SPLIT.split(abstract):
        match = pattern.search(sentence)
        if not match or not _SELF_REF.search(sentence):
            continue
        if _PRIOR_WORK.search(sentence[: match.start()]):
            continue
        return True
    return False


def classify_design(
    title: str,
    abstract: str | None = None,
    venue: str | None = None,
    *,
    work_type: str | None = None,
) -> str:
    """Guess the study design from public metadata. Conservative: "unknown" when unsure.

    ``work_type`` is the record type reported by the API (OpenAlex ``type``, Crossref ``type``).
    Title keywords are decisive; abstract keywords only count when the sentence claims the design
    for the paper itself.
    """
    wtype = (work_type or "").strip().lower()
    if wtype in _PREPRINT_TYPES or (venue and _PREPRINT_VENUE.search(venue)):
        return "preprint"
    if wtype in _BOOK_TYPES:
        return "book"
    text_title = title or ""
    text_abstract = abstract or ""
    for design, title_pattern, abstract_pattern in _RULES:
        if title_pattern and title_pattern.search(text_title):
            return design
        if abstract_pattern and text_abstract and _claimed_in_abstract(abstract_pattern, text_abstract):
            return design
    return "unknown"


# --- grading ------------------------------------------------------------------------------


def _letter(score: float) -> str:
    for letter, threshold in THRESHOLDS:
        if score >= threshold:
            return letter
    return "D"


def _citation_bonus(study: Study, today_year: int) -> tuple[float, str]:
    if study.cited_by is None or study.year is None:
        return 0.0, "citations: no citation data, no bonus"
    cited = max(0, study.cited_by)
    age = max(1, today_year - study.year + 1)
    per_year = cited / age
    bonus = MAX_CITATION_BONUS * min(1.0, math.log10(1 + per_year) / math.log10(1 + CITATIONS_PER_YEAR_FOR_MAX))
    return bonus, f"citations: {cited} in {age} year(s), {per_year:.1f} per year, bonus +{bonus:.3f}"


def grade_study(study: Study, *, today_year: int | None = None) -> tuple[str, float, list[str]]:
    """Return ``(letter, score, reasons)`` for one study. Pure function of the study and the year."""
    year_now = today_year if today_year is not None else datetime.date.today().year
    reasons: list[str] = []

    design = study.design if study.design in DESIGN_SCORES else "unknown"
    score = DESIGN_SCORES[design]
    reasons.append(f"design: {design} (base {score:.2f})")

    bonus, why = _citation_bonus(study, year_now)
    score += bonus
    reasons.append(why)

    if study.peer_reviewed is True:
        score += PEER_REVIEW_BONUS
        reasons.append(f"peer reviewed: +{PEER_REVIEW_BONUS:.2f}")
    elif study.peer_reviewed is False:
        reasons.append("not peer reviewed: no bonus")
    else:
        reasons.append("peer review status unknown: no bonus")

    score = min(1.0, score)
    if (study.design == "preprint" or study.peer_reviewed is False) and score > PREPRINT_CAP:
        score = PREPRINT_CAP
        reasons.append("capped at letter B: unreviewed work cannot reach A")

    if study.retracted:
        reasons.append("retracted: forced to D, the paper does not count as evidence")
        return "D", 0.0, reasons

    score = round(score, 3)
    return _letter(score), score, reasons


def apply_grade(study: Study, **kw) -> Study:
    """Fill ``grade`` and ``grade_score`` in place and return the same study."""
    letter, score, _ = grade_study(study, **kw)
    study.grade = letter
    study.grade_score = score
    return study
