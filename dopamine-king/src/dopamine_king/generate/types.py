"""Shared contracts for the content generators.

Every builder turns a ``Brief`` into a ``Skeleton``: deterministic structure plus named ``Slot``s for
the prose that needs a writer. A ``Writer`` fills the slots (offline: defaults only, no invented
prose; LLM: model written), ``Skeleton.render`` produces a ``Draft`` and validators/guards inspect it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..models import Serializable

SLOT_RE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
GOALS = ("awareness", "consideration", "conversion", "retention", "community")


@dataclass
class Brief(Serializable):
    brand: str
    topic: str                                   # nominative form, e.g. "marketing automation"
    audience: str                                # e.g. "beginner runners"
    goal: str = "awareness"                      # one of GOALS
    lang: str = "en"                             # "en" | "cs"
    tone: str = "friendly, direct, no hype"
    keyword: str | None = None                   # primary SEO keyword
    secondary_keywords: list[str] = field(default_factory=list)
    offer: str | None = None                     # product or offer being promoted
    cta: str | None = None
    facts: list[str] = field(default_factory=list)            # first-party facts the writer may use
    sources: list[dict[str, Any]] = field(default_factory=list)   # vetted: {"id","title","url","claim"}
    voice_notes: str = ""
    cohort: str | None = None
    avoid: list[str] = field(default_factory=list)            # words or claims to avoid
    # Czech grammar helper: {"gen": ..., "dat": ..., "acc": ..., "loc": ..., "ins": ...} forms of topic.
    topic_forms: dict[str, str] = field(default_factory=dict)
    sponsored: bool = False                      # paid or affiliate content needs a disclosure
    # Regulated verticals: "general" applies the standard Trust Shield; "wellness" adds the claims profile of the
    # vertical (non-medical device: no disease, treatment or prevention claims, hedged and sourced benefits).
    vertical: str | None = None
    claims_profile: str = "general"
    safety_note: str | None = None               # the manufacturer's own safety text; replaces the vertical's template

    def topic_in(self, case: str) -> str:
        """Topic in a grammatical case when known, else the nominative form."""
        return self.topic_forms.get(case) or self.topic

    @property
    def primary_keyword(self) -> str:
        return (self.keyword or self.topic).strip()


@dataclass
class Slot:
    id: str                                      # [a-z0-9_]+
    instruction: str                             # English instruction for the writer
    max_chars: int | None = None
    min_chars: int | None = None
    max_words: int | None = None
    must_include: list[str] = field(default_factory=list)
    kind: str = "text"                           # text | title | line | list
    default: str | None = None                   # deterministic text used by the offline writer


@dataclass
class Draft(Serializable):
    format: str
    lang: str
    hook: str
    body: str                                    # rendered text (Markdown or plain)
    parts: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)
    slots_open: list[str] = field(default_factory=list)   # slots still holding [[ADD: ...]] placeholders
    notes: list[str] = field(default_factory=list)


@dataclass
class Skeleton:
    format: str
    lang: str
    template: str                                # text containing {{slot_id}} placeholders
    slots: list[Slot]
    fixed: dict[str, Any] = field(default_factory=dict)       # structured data that needs no writer
    meta: dict[str, Any] = field(default_factory=dict)
    hook_slot: str = "hook"
    notes: list[str] = field(default_factory=list)
    # Optional hook for builders that need structured output derived from the filled slots
    # (for example video beats with timings). Receives (skeleton, filled values) and returns parts.
    assemble: Callable[["Skeleton", dict[str, str]], dict[str, Any]] | None = field(
        default=None, repr=False, compare=False
    )

    def slot(self, slot_id: str) -> Slot:
        for s in self.slots:
            if s.id == slot_id:
                return s
        raise KeyError(slot_id)

    def render(self, fills: dict[str, str] | None = None) -> Draft:
        fills = fills or {}
        values: dict[str, str] = {}
        open_slots: list[str] = []
        for s in self.slots:
            v = fills.get(s.id)
            if v is None or not str(v).strip():
                v = s.default
            if v is None or not str(v).strip():
                v = f"[[ADD: {s.instruction}]]"
                open_slots.append(s.id)
            values[s.id] = str(v).strip()
        body = SLOT_RE.sub(lambda m: values.get(m.group(1), m.group(0)), self.template)
        hook = values.get(self.hook_slot) or str(self.fixed.get(self.hook_slot, ""))
        parts: dict[str, Any] = dict(self.fixed)
        if self.assemble:
            parts.update(self.assemble(self, values))
        parts["slots"] = values
        return Draft(
            format=self.format, lang=self.lang, hook=hook, body=body, parts=parts,
            meta=dict(self.meta), slots_open=open_slots, notes=list(self.notes),
        )


@dataclass
class Issue(Serializable):
    severity: str                                # "error" | "warn" | "info"
    code: str                                    # UPPER_SNAKE
    message: str
    where: str | None = None


class Writer(Protocol):
    name: str

    def fill(self, skeleton: Skeleton, brief: Brief) -> dict[str, str]: ...


class OfflineWriter:
    """Deterministic writer: uses slot defaults only and never invents prose."""

    name = "offline"

    def fill(self, skeleton: Skeleton, brief: Brief) -> dict[str, str]:
        return {s.id: s.default for s in skeleton.slots if s.default}


@dataclass
class FormatSpec:
    id: str                                      # e.g. "linkedin_post"
    name_en: str
    name_cs: str
    family: str                                  # article | social | video | ad | email | audio | hooks
    platform: str                                # blog | linkedin | x | instagram | tiktok | youtube | google | meta | email | ...
    build: Callable[..., Skeleton]               # build(brief, *, hook=None, options=None) -> Skeleton
    validate: Callable[[Draft], list[Issue]]
    limits: dict[str, Any] = field(default_factory=dict)
    description_en: str = ""
    description_cs: str = ""
