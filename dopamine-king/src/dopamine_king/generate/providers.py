"""Writers: fill the slots of a skeleton.

``OfflineWriter`` (in types.py) only uses deterministic defaults and never invents prose.
``FileWriter`` takes the slot texts from a JSON file a person (or any other model) wrote: bring your own writer.
``ClaudeCodeWriter`` asks Claude through the local Claude Code command (``claude -p``): it uses the Claude subscription the
person is logged in with (for example Max) instead of API credits.
``AnthropicWriter`` asks Claude for one JSON object with a string per slot, checks the slot
constraints, and runs a short repair loop for violations. It uses the official SDK, structured
outputs (``output_config.format``), an explicit effort level, handles ``refusal`` before reading
content and opts into server-side fallbacks by default.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Sequence

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
6. If a slot needs real information that the brief does not contain (an author's name and credentials, a date, a named person's quote, a postal address), return an empty string for it. Never write a placeholder, a bracketed note or an instruction to an editor in its place, and never mention the brief, the slots or these rules in the text.
7. Return a JSON object with one string value per requested slot id and nothing else."""


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


class _SlotJsonWriter:
    """Fills skeleton slots with a model that answers one JSON object per request; subclasses supply ``_complete_json``."""

    max_repairs = 2
    usage: Usage

    def _complete_json(self, user: str, slot_ids: Sequence[str]) -> dict[str, str]:  # pragma: no cover - interface
        raise NotImplementedError

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


class AnthropicWriter(_SlotJsonWriter):
    """Fills skeleton slots with Claude through the API. See the module docstring for the API choices."""

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


def offline_revise(skeleton: Skeleton, brief: Brief, fills: dict[str, str], feedback: dict[str, list[str]]) -> dict[str, str]:
    return fills


class FileWriter:
    """Fills slots from a JSON file written by a person or by another model ("bring your own writer").

    The file maps format ids to slot texts, ``{"seo_article": {"answer": "..."}}``; ``forge --emit-slots`` writes a template with
    every slot, its instruction and its limits. A flat ``{"slot_id": "text"}`` applies to every format that has the slot, a value may
    also be ``{"text": "..."}`` (the template's shape), and keys that start with an underscore are notes. Slots the file leaves
    empty keep their defaults (and stay ``[[ADD: ...]]`` when they have none). The text is checked against the slot limits; problems
    are collected in ``violations`` and the draft still goes through the validators and the Trust Shield like any other.
    """

    name = "file"

    def __init__(self, path: str | os.PathLike[str]) -> None:
        try:
            data = json.loads(Path(path).read_text("utf-8"))
        except OSError as err:
            raise WriterError(f"cannot read the fills file: {err}") from err
        except ValueError as err:
            raise WriterError(f"the fills file is not valid JSON: {err}") from err
        if not isinstance(data, dict):
            raise WriterError("the fills file must be a JSON object")
        self.by_format: dict[str, dict[str, str]] = {}
        self.flat: dict[str, str] = {}
        for key, value in data.items():
            if str(key).startswith("_"):
                continue
            if isinstance(value, dict) and not self._is_text_object(value):
                self.by_format[str(key)] = {str(k): text for k, v in value.items() if not str(k).startswith("_") and (text := self._text(v))}
            elif text := self._text(value):
                self.flat[str(key)] = text
        self.violations: dict[str, list[str]] = {}
        self.used: set[tuple[str, str]] = set()

    @staticmethod
    def _is_text_object(value: dict[str, Any]) -> bool:
        return isinstance(value.get("text"), str) and all(k == "text" or str(k).startswith("_") or k in ("kind", "limits", "instruction", "default") for k in value)

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, dict):
            value = value.get("text")
        return value.strip() if isinstance(value, str) else ""

    def fill(self, skeleton: Skeleton, brief: Brief) -> dict[str, str]:
        out: dict[str, str] = {}
        own = self.by_format.get(skeleton.format, {})
        for slot in skeleton.slots:
            text = own.get(slot.id) or self.flat.get(slot.id) or ""
            if text:
                text = normalize_dashes(text)
                self.used.add((skeleton.format, slot.id))
                problems = slot_violations(slot, text)
                if problems:
                    self.violations[f"{skeleton.format}.{slot.id}"] = problems
            else:
                text = slot.default or ""
            if text:
                out[slot.id] = text
        return out


_CLAUDE_CODE_MODELS = {"premium": "opus", "balanced": "sonnet", "economy": "haiku", "fast": "haiku"}


class ClaudeCodeWriter(_SlotJsonWriter):
    """Fills slots with Claude through the local Claude Code command in print mode (``claude -p``).

    The call runs under the Claude account the person is logged in with, so a subscription such as Max pays for it instead of
    API credits. ``ANTHROPIC_API_KEY`` is removed from the child's environment unless ``use_api_key`` is set, because Claude Code
    would otherwise bill that key. The prompt goes in on standard input, the answer is checked against a JSON schema by the
    command itself, no tools are enabled and no session is stored. Tiers map to the model aliases opus, sonnet and haiku
    (``--model``, ``KING_CLAUDE_MODEL``); the effort is ``low`` unless ``KING_EFFORT`` says otherwise; ``KING_CLAUDE_BIN`` names another executable.
    """

    name = "claude-code"

    def __init__(
        self,
        model: str | None = None,
        *,
        tier: str = "balanced",
        effort: str | None = None,
        executable: str | None = None,
        timeout: float = 600.0,
        max_repairs: int = 2,
        use_api_key: bool = False,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        self.model = model or os.environ.get("KING_CLAUDE_MODEL") or _CLAUDE_CODE_MODELS.get(tier, "sonnet")
        self.effort = effort or os.environ.get("KING_EFFORT") or "low"          # slot writing needs little thinking: low is much faster and cheaper on the limits
        self.executable = executable or os.environ.get("KING_CLAUDE_BIN") or "claude"
        self.timeout = timeout
        self.max_repairs = max_repairs
        self.use_api_key = use_api_key
        self.usage = Usage()
        self._runner = runner or subprocess.run

    def command(self, slot_ids: Sequence[str]) -> list[str]:
        cmd = [self.executable, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence",
               "--system-prompt", SYSTEM_PROMPT, "--json-schema", json.dumps(slots_schema(slot_ids)), "--model", self.model]
        if self.effort:
            cmd += ["--effort", self.effort]
        return cmd

    def _environment(self) -> dict[str, str]:
        env = dict(os.environ)
        if not self.use_api_key:
            env.pop("ANTHROPIC_API_KEY", None)
        return env

    def _complete_json(self, user: str, slot_ids: Sequence[str]) -> dict[str, str]:
        try:
            with tempfile.TemporaryDirectory() as workdir:            # no project files or instructions of the caller are read
                proc = self._runner(self.command(slot_ids), input=user, capture_output=True, text=True, timeout=self.timeout,
                                    env=self._environment(), cwd=workdir)
        except FileNotFoundError as err:
            raise WriterError(f"The command {self.executable!r} was not found. Install Claude Code and log in with your Claude "
                              "account (run claude, then /login), or use --writer file.") from err
        except subprocess.TimeoutExpired as err:
            raise WriterError(f"Claude Code did not answer within {self.timeout:.0f} seconds.") from err
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip()[-300:]
            raise WriterError(f"Claude Code failed (exit {proc.returncode}): {tail or 'no message'}")
        try:
            data = json.loads(proc.stdout)
        except ValueError as err:
            raise WriterError(f"Unexpected output from Claude Code: {proc.stdout[:120]!r}") from err
        if not isinstance(data, dict):
            raise WriterError("Unexpected output from Claude Code: not a JSON object")
        if data.get("is_error"):
            raise WriterError(f"Claude Code reported an error: {str(data.get('result') or data.get('subtype') or 'unknown')[:300]}")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        self.usage.add(SimpleNamespace(**{k: usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens")}))
        payload = data.get("structured_output")
        if not isinstance(payload, dict):
            text = str(data.get("result") or "").strip()
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
            try:
                payload = json.loads(text)
            except ValueError as err:
                raise WriterError(f"Claude Code did not return valid JSON: {text[:120]!r}") from err
            if not isinstance(payload, dict):
                raise WriterError("Claude Code did not return a JSON object")
        return {k: normalize_dashes(str(v)) for k, v in payload.items() if k in slot_ids}


def select_writer(name: str | None = "auto", **kwargs: Any) -> Writer:
    """``offline``, ``file`` (needs ``path=``), ``claude-code`` (the local Claude Code command), ``anthropic`` or ``auto`` (Claude through the API when credentials exist, otherwise offline)."""
    name = (name or "auto").lower()
    if name == "offline":
        return OfflineWriter()
    if name == "file":
        return FileWriter(kwargs["path"])
    if name == "claude-code":
        return ClaudeCodeWriter(tier=kwargs.get("tier", "balanced"))
    if name == "anthropic":
        return AnthropicWriter(**kwargs)
    if name == "auto":
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return AnthropicWriter(**kwargs)
        return OfflineWriter()
    raise ValueError(f"unknown writer {name!r} (use offline, file, claude-code, anthropic or auto)")
