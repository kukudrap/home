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
_FIELD_TITLE = r"field experiments?|natural experiments?|randomi[sz]ed (?:field |online )?experiments?|online controlled experiments?"
_FIELD_CLAIM = _FIELD_TITLE + r"|a/b[- ]?(?:tests?|testing)|split[- ]tests?"   # "A/B test" in a title is often a methods paper
_LAB_TITLE = r"experimental (?:evidence|study|studies|investigation)|laboratory experiments?|lab experiments?"
_NUM = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_LAB_ABSTRACT = (
    r"participants (?:were )?randomly assigned|randomly assigned (?:to|participants)|"
    r"between[- ]subjects? (?:design|experiment)|within[- ]subjects? (?:design|experiment)|"
    r"laboratory (?:experiment|study)|lab (?:experiment|study)|"
    r"\bin " + _NUM + r" (?:\w+[- ]){0,2}experiments?\b"
)
_OBSERVATIONAL = (
    r"observational (?:study|studies|data|analysis)|cohort stud|cross[- ]sectional|longitudinal (?:study|analysis)|"
    r"retrospective (?:study|analysis)|case[- ]control|panel data|archival data"
)
_SURVEY = r"\bsurvey\b|\bquestionnaire\b"
_QUALITATIVE = r"case stud(?:y|ies)|\binterview(?:s|ed)?\b|ethnograph|grounded theory|focus groups?|thematic analysis|\bqualitative\b"
_GUIDELINE = r"\bguidelines?\b|\bbest[- ]practices?\b|\bpractical guide\b|\bwhite ?paper\b|\bplaybook\b"
_THEORY = r"\btheor(?:y|ies|etical)\b|\bframework\b|\bconceptual\b"

# Wording in which the authors claim a design for their own paper: "we ran an A/B test", "this meta-analysis".
# Mentions such as "we review field experiments" or "unlike previous meta-analyses" do not match.
_CLAIM_VERBS = r"(?:conduct(?:ed)?|ran|run|perform(?:ed)?|carried out|carry out|report(?:ed)?|present(?:ed)?|undert(?:ook|ake))"
_FILLER_WORD = r"(?:(?!(?:study|studies|survey|review|analysis|paper|approach|method|methods|framework|literature)\b)[\w,/-]+\s+)"


def _claim(noun: str) -> str:
    return (
        rf"\bwe\s+(?:\w+\s+){{0,2}}{_CLAIM_VERBS}\s+{_FILLER_WORD}{{0,3}}?(?:{noun})"
        rf"|\b(?:this|the present|the current|our)\s+(?:[\w-]+\s+)?(?:{noun})"
    )


# (design, title pattern, abstract pattern, abstract needs the generic self-reference check, title guard)
_RULES: tuple[tuple[str, re.Pattern[str], re.Pattern[str] | None, bool, bool], ...] = (
    ("meta-analysis", _re(_META), _re(_claim(_META)), False, False),
    ("systematic-review", _re(_SYSTEMATIC), _re(_claim(_SYSTEMATIC)), False, False),
    ("rct", _re(_RCT), _re(_claim(_RCT)), False, True),
    ("field-experiment", _re(_FIELD_TITLE), _re(_claim(_FIELD_CLAIM)), False, True),
    ("lab-experiment", _re(_LAB_TITLE), _re(_LAB_ABSTRACT + "|" + _claim(r"experiments?")), False, True),
    ("observational", _re(_OBSERVATIONAL), _re(_OBSERVATIONAL), True, False),
    ("survey", _re(_SURVEY), _re(r"\bwe survey(?:ed)?\b|\bsurvey of \d|\bquestionnaires?\b"), True, False),
    ("qualitative", _re(_QUALITATIVE), _re(_QUALITATIVE), True, False),
    ("guideline", _re(_GUIDELINE), None, False, False),
    ("theory", _re(_THEORY), _re(_THEORY), True, False),
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_SELF_REF = re.compile(r"\b(?:this|our|we|here|present|current|authors?|participants|respondents)\b", re.I)
_PRIOR_WORK = re.compile(r"\b(?:previous|prior|earlier|recent|existing|published|several|many|other|past)\b[^.]{0,30}$", re.I)
_REVIEWISH_TITLE = _re(r"\b(?:reviews?|surveys?|overview|literature|meta|synthesis|commentary|critique)\b")
_BOOK_TYPES = frozenset({"book", "monograph", "edited-book", "reference-book"})
_PREPRINT_TYPES = frozenset({"preprint", "posted-content"})


def _claimed_in_abstract(pattern: re.Pattern[str], abstract: str) -> bool:
    """True when a sentence of the abstract claims the design for the paper itself.

    A mention of "previous studies of this kind" must not turn an ordinary paper into that design.
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
    Title keywords are decisive; abstract keywords only count when the authors claim the design for
    their own paper. A design guess is never a verdict: grading shows the reasoning.
    """
    wtype = (work_type or "").strip().lower()
    if wtype in _PREPRINT_TYPES or (venue and _PREPRINT_VENUE.search(venue)):
        return "preprint"
    if wtype in _BOOK_TYPES:
        return "book"
    text_title = title or ""
    text_abstract = abstract or ""
    for design, title_pattern, abstract_pattern, generic, guard in _RULES:
        if title_pattern.search(text_title) and not (guard and _REVIEWISH_TITLE.search(text_title)):
            return design
        if abstract_pattern and text_abstract:
            if generic and _claimed_in_abstract(abstract_pattern, text_abstract):
                return design
            if not generic and abstract_pattern.search(text_abstract):
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
