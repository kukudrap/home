"""Data models of the research package: studies, tactics and the links between them.

Integrity rule: a field that cannot be stated with certainty stays ``None``. These records are
shown to users as evidence, so a missing reference is always better than a wrong one.
"""
from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field

from ..models import Serializable

DESIGNS = (
    "meta-analysis", "systematic-review", "rct", "field-experiment", "lab-experiment",
    "observational", "survey", "theory", "qualitative", "book", "preprint", "guideline", "unknown",
)
SOURCES = ("seed", "openalex", "crossref", "arxiv", "pubmed")
DIRECTIONS = ("supports", "mixed", "contradicts", "context")
DRIVERS = (
    "curiosity", "surprise", "emotion", "relevance", "utility", "fluency",
    "integrity", "game", "geo", "testing", "structure", "claim",
)
CONFIDENCES = ("low", "medium", "high")
GRADES = ("A", "B", "C", "D")


@dataclass
class Study(Serializable):
    id: str                          # doi:<lowercase doi> | arxiv:<id> | oa:<openalex id> | seed:<slug>
    title: str
    authors: list[str] = field(default_factory=list)   # "Surname, I."
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    abstract: str | None = None
    cited_by: int | None = None
    design: str = "unknown"          # one of DESIGNS
    source: str = "seed"             # one of SOURCES
    verified: bool = False           # resolved against Crossref by Ledger.verify()
    verification_note: str = ""
    retracted: bool = False
    peer_reviewed: bool | None = None
    confidence: str = "medium"       # confidence in the bibliographic record itself
    grade: str = ""                  # "A".."D", filled by grading.apply_grade
    grade_score: float = 0.0


@dataclass
class EvidenceLink(Serializable):
    tactic_id: str
    study_id: str
    direction: str                   # one of DIRECTIONS
    note_en: str
    note_cs: str
    caveat_en: str = ""
    caveat_cs: str = ""


@dataclass
class Tactic(Serializable):
    id: str
    name_en: str
    name_cs: str
    summary_en: str
    summary_cs: str
    driver: str                      # one of DRIVERS
    ethics_en: str = ""
    ethics_cs: str = ""


# --- shared helpers used by the API clients and the ledger -------------------------------------

class ResearchApiError(Exception):
    """A scholarly API answered with an unusable status or payload (network errors are FetchError)."""


DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.I)
_BLOCK_TAGS = re.compile(r"</?(?:jats:)?(?:p|title|sec|br|li|ul|ol|abstract)\b[^>]*>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_SURNAME_PARTICLES = frozenset(
    {"van", "von", "de", "der", "den", "di", "da", "del", "della", "du", "la", "le", "dos", "das",
     "ter", "ten", "bin", "ibn", "al", "el"}
)
_NAME_SUFFIXES = frozenset({"jr", "jr.", "sr", "sr.", "ii", "iii", "iv"})


def normalize_doi(raw: str | None) -> str | None:
    """Lower-cased bare DOI, or None when ``raw`` is empty or not a well formed DOI."""
    if not raw or not isinstance(raw, str):
        return None
    value = _DOI_PREFIX.sub("", raw.strip()).strip().lower()
    return value if DOI_RE.match(value) else None


def clean_text(raw: str | None) -> str:
    """Strip markup (HTML, JATS), unescape entities and collapse whitespace."""
    if not raw:
        return ""
    text = _ANY_TAG.sub("", _BLOCK_TAGS.sub(" ", raw))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _initials(given: str) -> str:
    out: list[str] = []
    for token in given.split():
        if "-" in token:
            pieces = [p for p in token.split("-") if p]
            out.append("-".join(f"{p.strip('.')[0].upper()}." for p in pieces if p.strip(".")))
        elif token.isalpha() and token.isupper() and len(token) <= 3:
            out.extend(f"{c}." for c in token)           # "JP" -> "J. P."
        else:
            out.extend(f"{p[0].upper()}." for p in token.split(".") if p)
    return " ".join(x for x in out if x)


def format_author_parts(given: str | None, family: str | None) -> str | None:
    """"Surname, I. J." from separate given and family names (Crossref style)."""
    family = clean_text(family)
    given = clean_text(given)
    if not family:
        return clean_text(given) or None
    initials = _initials(given)
    return f"{family}, {initials}" if initials else family


def format_author(name: str | None) -> str | None:
    """"Surname, I." from a display name such as "Jonah Berger" or "Berger, Jonah"."""
    name = clean_text(name)
    if not name:
        return None
    if "," in name:
        family, _, given = name.partition(",")
        return format_author_parts(given.strip(), family.strip())
    tokens = name.split()
    if len(tokens) == 1:
        return name
    suffix = tokens.pop() if tokens[-1].lower() in _NAME_SUFFIXES and len(tokens) > 2 else None
    family_tokens = [tokens.pop()]
    while len(tokens) > 1 and tokens[-1].lower() in _SURNAME_PARTICLES:
        family_tokens.insert(0, tokens.pop())
    family = " ".join(family_tokens) + (f" {suffix}" if suffix else "")
    return format_author_parts(" ".join(tokens), family)


def make_study_id(
    *, doi: str | None = None, arxiv_id: str | None = None,
    openalex_id: str | None = None, pmid: str | None = None, slug: str | None = None,
) -> str:
    """Stable id with the documented priority: doi, arxiv, openalex, pubmed id, seed slug."""
    if doi:
        return f"doi:{doi.lower()}"
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    if openalex_id:
        return f"oa:{openalex_id}"
    if pmid:
        return f"pmid:{pmid}"
    if slug:
        return f"seed:{slug}"
    raise ValueError("a study id needs a doi, arxiv id, openalex id, pubmed id or slug")


def fold(text: str | None) -> str:
    """Case and diacritics insensitive form of ``text`` for tolerant matching ("Žluťoučký" -> "zlutoucky")."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def normalize_title(title: str | None) -> str:
    """Folded title reduced to words, so punctuation and markup never block a match."""
    return " ".join(re.findall(r"\w+", fold(clean_text(title))))
