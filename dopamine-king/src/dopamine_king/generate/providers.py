"""Writers: fill the slots of a skeleton.

``OfflineWriter`` (in types.py) only uses deterministic defaults and never invents prose.
``AnthropicWriter`` asks Claude for one JSON object with a string per slot, checks the slot
constraints, and runs a short repair loop for violations. It uses the official SDK, structured
outputs (``output_config.format``), an explicit effort level, handles ``refusal`` before reading
content and opts into server-side fallbacks by default.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..config import anthropic_model
from .types import Brief, OfflineWriter, Skeleton, Slot, Writer

_EM = chr(0x2014)
_EN = chr(0x2013)
_SPACED_EN = re.compile(r"\s+" + re.escape(_EN) + r"\s+")
_EM_RE = re.compile(r"\s*" + re.escape(_EM) + r"\s*")

FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """You are the copy engine inside Dopamine King, an evidence-driven marketing platform. You fill the named slots of a content skeleton for a brand. Write like a senior copywriter and editor: specific, concrete, useful to the reader, with a distinct voice, never padded.

Hard rules:
1. Use ONLY facts, numbers, quotes and claims that appear in the brief (facts, sources, offer). Never invent statistics, studies, customers, testimonials, awards, prices or quotes. If a slot needs a fact the brief does not contain, write the slot without it instead of making one up.
2. Cite only sources listed in the brief, with the marker [[cite:<id>]] right after the claim it supports.
3. No clickbait, no fake scarcity or urgency, no guilt-tripping, no engagement bait, no unverifiable superlatives. A hook must deliver what it promises.
4. Write in the language of the brief (cs means Czech with correct diacritics and natural grammar, en means English) and match the requested tone.
5. Respect every slot constraint (max_chars, max_words, min_chars, must_include). Use plain text or Markdown as the template implies. Never use the long dash characters (em dash or en dash); use commas, colons, parentheses or a plain hyphen.
6. Return a JSON object with one string value per requested slot id and nothing else."""


class WriterError(RuntimeError):
    """The writer could not produce slot text."""


class WriterRefused(WriterError):
    def __init__(self, category: str | None, explanation: str | None = None) -> None:
        super().__init__(f"The model declined this request (category: {category or 'unknown'}). {explanation or ''}".strip())
        self.category = category


def normalize_dashes(text: str) -> str:
    """Project rule: no em dash or en dash in generated text."""
    text = _SPACED_EN.sub(" - ", text)
    text = text.replace(_EN, "-")
    return _EM_RE.sub(" - ", text)


def slot_violations(slot: Slot, text: str) -> list[str]:
    """Constraint problems of one filled slot (empty list when fine)."""
    problems = []
    if slot.max_chars is not None and len(text) > slot.max_chars:
        problems.append(f"{len(text)} characters, maximum is {slot.max_chars}")
    if slot.min_chars is not None and len(text) < slot.min_chars:
        problems.append(f"{len(text)} characters, minimum is {slot.min_chars}")
    words = len(text.split())
    if slot.max_words is not None and words > slot.max_words:
        problems.append(f"{words} words, maximum is {slot.max_words}")
    low = text.lower()
    for needed in slot.must_include:
        if needed.lower() not in low:
            problems.append(f"must include '{needed}'")
    return problems


def all_violations(skeleton: Skeleton, fills: dict[str, str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for slot in skeleton.slots:
        text = fills.get(slot.id)
        if text:
            problems = slot_violations(slot, text)
            if problems:
                out[slot.id] = problems
    return out


def slots_schema(slot_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {sid: {"type": "string"} for sid in slot_ids},
        "required": list(slot_ids),
        "additionalProperties": False,
    }


def _describe_slot(slot: Slot, current: str | None = None) -> str:
    limits = []
    if slot.max_chars is not None:
        limits.append(f"max {slot.max_chars} chars")
    if slot.min_chars is not None:
        limits.append(f"min {slot.min_chars} chars")
    if slot.max_words is not None:
        limits.append(f"max {slot.max_words} words")
    if slot.must_include:
        limits.append("must include: " + ", ".join(f'"{m}"' for m in slot.must_include))
    head = f"- {slot.id} ({slot.kind}{', ' + '; '.join(limits) if limits else ''}): {slot.instruction}"
    if current:
        head += f"\n  current draft: {current}"
    return head


def profile_block(brief: Brief) -> list[str]:
    """Regulatory profile for the prompt: the vertical's rules and what the claim map allows."""
    from . import claims
    from ..verticals import load_vertical

    profile = claims.profile_for(brief)
    if profile is None:
        return []
    vertical = load_vertical(brief.vertical or "pbm")
    lines = [f"Regulatory profile: {profile.profile} (non-medical product). Follow these rules strictly:"]
    lines += [f"  {n}. {rule}" for n, rule in enumerate(vertical.writer_rules("en"), 1)]
    blocked = [t.name_en for t in profile.topics if t.klass in ("medical", "avoid")]
    careful = [f"{t.name_en} (evidence: {t.label})" for t in profile.topics if t.klass in ("wellness", "cosmetic")]
    if blocked:
        lines.append("  Never write about: " + "; ".join(blocked) + ".")
    if careful:
        lines.append("  Only with hedged wording and a cited source: " + "; ".join(careful) + ".")
    return lines


def brief_block(brief: Brief) -> str:
    lines = [
        f"Brand: {brief.brand}", f"Topic: {brief.topic}", f"Audience: {brief.audience}", f"Goal: {brief.goal}",
        f"Language: {brief.lang}", f"Tone: {brief.tone}",
    ]
    if brief.keyword:
        lines.append(f"Primary keyword: {brief.keyword}")
    if brief.secondary_keywords:
        lines.append("Secondary keywords: " + ", ".join(brief.secondary_keywords))
    if brief.offer:
        lines.append(f"Offer: {brief.offer}")
    if brief.cta:
        lines.append(f"Call to action: {brief.cta}")
    if brief.voice_notes:
        lines.append(f"Voice notes: {brief.voice_notes}")
    if brief.avoid:
        lines.append("Avoid: " + ", ".join(brief.avoid))
    if brief.sponsored:
        lines.append("This content is sponsored and must carry a clear disclosure.")
    lines.extend(profile_block(brief))
    lines.append("Facts you may use (first party, verified by the brand):")
    lines.extend(f"  * {f}" for f in brief.facts) if brief.facts else lines.append("  (none provided: do not invent any)")
    lines.append("Sources you may cite with [[cite:<id>]]:")
    if brief.sources:
        for s in brief.sources:
            lines.append(f"  * id={s.get('id')} | {s.get('title', '')} | {s.get('claim', '')} | {s.get('url', '')}")
    else:
        lines.append("  (none provided: do not cite)")
    return "\n".join(lines)


def build_user_prompt(skeleton: Skeleton, brief: Brief, slots: Sequence[Slot], current: dict[str, str] | None = None,
                      feedback: dict[str, list[str]] | None = None) -> str:
    parts = [f"FORMAT: {skeleton.format}", "", "BRIEF", brief_block(brief), "", "TEMPLATE (slots are marked {{slot_id}})",
             skeleton.template, "", "SLOTS TO WRITE"]
    for slot in slots:
        parts.append(_describe_slot(slot, (current or {}).get(slot.id) or slot.default))
        if feedback and feedback.get(slot.id):
            parts.append("  problems to fix: " + "; ".join(feedback[slot.id]))
    if skeleton.notes:
        parts += ["", "BUILDER NOTES"] + [f"- {n}" for n in skeleton.notes]
    return "\n".join(parts)


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0

    def add(self, usage: Any) -> None:
        self.calls += 1
        self.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
        self.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
        self.cache_read_input_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)


class AnthropicWriter:
    """Fills skeleton slots with Claude. See the module docstring for the API choices."""

    name = "anthropic"

    def __init__(
        self,
        model: str | None = None,
        *,
        tier: str = "balanced",
        effort: str | None = None,
        client: Any = None,
        use_fallbacks: bool = True,
        max_tokens: int = 16000,
        max_repairs: int = 2,
    ) -> None:
        self.model = model or anthropic_model(tier)
        self.effort = effort or os.environ.get("KING_EFFORT", "medium")
        self.use_fallbacks = use_fallbacks
        self.max_tokens = max_tokens
        self.max_repairs = max_repairs
        self.usage = Usage()
        self._client = client

    # -- plumbing -------------------------------------------------------------------
    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as err:  # pragma: no cover - depends on the environment
                raise WriterError("The anthropic package is not installed. Run: pip install anthropic") from err
            try:
                self._client = anthropic.Anthropic()
            except Exception as err:  # missing credentials
                raise WriterError(
                    "No Anthropic credentials found. Set ANTHROPIC_API_KEY (or run `ant auth login`), "
                    "or use the offline writer."
                ) from err
        return self._client

    def _request(self, system: str, user: str, schema: dict[str, Any]) -> Any:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
        }
        if self.use_fallbacks:
            try:
                return self.client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **kwargs)
            except TypeError:
                # Older SDK without the typed parameter: send it in the raw body.
                return self.client.beta.messages.create(
                    betas=[FALLBACK_BETA], extra_body={"fallbacks": "default"}, **kwargs
                )
            except Exception as err:
                if getattr(err, "status_code", None) == 400:
                    return self.client.messages.create(**kwargs)   # platform without the fallback beta
                raise
        return self.client.messages.create(**kwargs)

    def _complete_json(self, user: str, slot_ids: Sequence[str]) -> dict[str, str]:
        response = self._request(SYSTEM_PROMPT, user, slots_schema(slot_ids))
        self.usage.add(getattr(response, "usage", None))
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            raise WriterRefused(getattr(details, "category", None), getattr(details, "explanation", None))
        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise WriterError("The response hit max_tokens before the JSON was complete; raise max_tokens.")
        try:
            data = json.loads(text)
        except ValueError as err:
            raise WriterError(f"The model did not return valid JSON: {text[:120]!r}") from err
        return {k: normalize_dashes(str(v)) for k, v in data.items() if k in slot_ids}

    # -- Writer protocol ------------------------------------------------------------
    def fill(self, skeleton: Skeleton, brief: Brief) -> dict[str, str]:
        slots = skeleton.slots
        if not slots:
            return {}
        fills = self._complete_json(build_user_prompt(skeleton, brief, slots), [s.id for s in slots])
        for s in slots:                                   # keep deterministic defaults for anything missing
            if not fills.get(s.id) and s.default:
                fills[s.id] = s.default
        return self._repair(skeleton, brief, fills)

    def revise(self, skeleton: Skeleton, brief: Brief, fills: dict[str, str], feedback: dict[str, list[str]]) -> dict[str, str]:
        """Rewrite only the slots named in ``feedback`` (validator, guard or scoring remarks)."""
        targets = [s for s in skeleton.slots if feedback.get(s.id)]
        if not targets:
            return fills
        prompt = build_user_prompt(skeleton, brief, targets, fills, feedback)
        updated = self._complete_json(prompt, [s.id for s in targets])
        merged = {**fills, **{k: v for k, v in updated.items() if v.strip()}}
        return self._repair(skeleton, brief, merged)

    def _repair(self, skeleton: Skeleton, brief: Brief, fills: dict[str, str]) -> dict[str, str]:
        for _ in range(self.max_repairs):
            bad = all_violations(skeleton, fills)
            if not bad:
                break
            targets = [s for s in skeleton.slots if s.id in bad]
            prompt = build_user_prompt(skeleton, brief, targets, fills, bad)
            fixed = self._complete_json(prompt, [s.id for s in targets])
            fills = {**fills, **{k: v for k, v in fixed.items() if v.strip()}}
        return fills


def offline_revise(skeleton: Skeleton, brief: Brief, fills: dict[str, str], feedback: dict[str, list[str]]) -> dict[str, str]:
    return fills


def select_writer(name: str | None = "auto", **kwargs: Any) -> Writer:
    """``offline``, ``anthropic`` or ``auto`` (Claude when credentials exist, otherwise offline)."""
    name = (name or "auto").lower()
    if name == "offline":
        return OfflineWriter()
    if name == "anthropic":
        return AnthropicWriter(**kwargs)
    if name == "auto":
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return AnthropicWriter(**kwargs)
        return OfflineWriter()
    raise ValueError(f"unknown writer {name!r} (use offline, anthropic or auto)")
