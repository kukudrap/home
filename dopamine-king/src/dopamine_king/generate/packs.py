"""Content packs: one brief, many formats, every draft validated, guarded and scored.

Flow per format: pick a hook that fits the format, build the skeleton, let the writer fill the
slots, render, run the format validator, the Trust Shield and (for articles) the SEO quality gate,
then let the writer revise the slots that drew remarks, up to ``improve_rounds`` times.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from ..scoring import score_hook
from .providers import slot_violations
from .types import Brief, Draft, Issue, OfflineWriter, Skeleton, Writer

DEFAULT_FORMATS = (
    "hook_set", "linkedin_post", "x_thread", "instagram_carousel", "short_video_script", "youtube_title_set",
    "seo_article", "geo_answer_page", "newsletter", "google_rsa", "email_subject_set",
)
ARTICLE_FORMATS = ("seo_article", "geo_answer_page")
# Menus of alternatives repeat the topic on purpose, so keyword density does not apply to them.
OPTION_LIST_FORMATS = ("hook_set", "youtube_title_set", "email_subject_set", "google_rsa")
# Formats with no natural place for a sponsorship label: the platform's ad label or the message body carries it.
NO_INLINE_DISCLOSURE = OPTION_LIST_FORMATS + ("meta_ad", "linkedin_ad")


@dataclass
class PackItem:
    format: str
    name_en: str
    name_cs: str
    family: str
    hook: str
    body: str
    hook_score: dict[str, Any]
    issues: list[dict[str, Any]]
    verdict: str
    scores: dict[str, float | None]
    alt_hooks: list[dict[str, Any]]
    parts: dict[str, Any]
    slots_open: list[str]
    rounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Pack:
    brief: dict[str, Any]
    writer: str
    created: str
    items: list[PackItem]
    summary: dict[str, Any]
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"brief": self.brief, "writer": self.writer, "created": self.created,
                "items": [i.to_dict() for i in self.items], "summary": self.summary, "errors": self.errors}

    def to_markdown(self, lang: str | None = None) -> str:
        cs = (lang or self.brief.get("lang", "en")) == "cs"
        s = self.summary
        out = [f"# {'Balíček obsahu' if cs else 'Content pack'}: {self.brief['brand']} / {self.brief['topic']}", "",
               f"{'Autor textu' if cs else 'Writer'}: {self.writer} | {s['n_items']} {'formátů' if cs else 'formats'} | "
               f"{'průměrné skóre hooku' if cs else 'average hook score'} {s['avg_dopamine']} | "
               f"{s['errors']} {'chyb' if cs else 'errors'}, {s['warnings']} {'varování' if cs else 'warnings'}, "
               f"{s['open_slots']} {'otevřených slotů' if cs else 'open slots'}", ""]
        for item in self.items:
            out += [f"## {item.name_cs if cs else item.name_en} ({item.format})", "",
                    f"**Hook:** {item.hook}  ", f"**{'Skóre' if cs else 'Score'}:** dopamine {item.scores.get('dopamine')}"
                    + (f", SEO {item.scores['seo']}" if item.scores.get("seo") is not None else "")
                    + (f", GEO {item.scores['geo']}" if item.scores.get("geo") is not None else "")
                    + f" | {'verdikt' if cs else 'verdict'}: **{item.verdict}**", "", item.body, ""]
            if item.issues:
                out.append(f"**{'Poznámky' if cs else 'Remarks'}:**")
                out += [f"- [{i['severity']}] {i['code']}: {i['message']}" for i in item.issues]
                out.append("")
        if self.errors:
            out += [f"## {'Nedostupné formáty' if cs else 'Unavailable formats'}"] + [f"- {e}" for e in self.errors]
        return "\n".join(out)

    def save(self, directory: str | Path) -> list[Path]:
        """Write pack.json, report.md, one file per item plus SRT and JSON-LD side files."""
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        written = []
        for name, text in (("pack.json", json.dumps(self.to_dict(), ensure_ascii=False, indent=1)),
                           ("report.md", self.to_markdown())):
            (root / name).write_text(text, "utf-8")
            written.append(root / name)
        for i, item in enumerate(self.items, 1):
            base = f"{i:02d}-{item.format}"
            (root / f"{base}.md").write_text(f"# {item.hook}\n\n{item.body}\n", "utf-8")
            written.append(root / f"{base}.md")
            if item.parts.get("srt"):
                (root / f"{base}.srt").write_text(item.parts["srt"], "utf-8")
                written.append(root / f"{base}.srt")
            if item.parts.get("json_ld"):
                (root / f"{base}.jsonld").write_text(json.dumps(item.parts["json_ld"], ensure_ascii=False, indent=1), "utf-8")
                written.append(root / f"{base}.jsonld")
        return written


def _verdict(issues: Sequence[Issue]) -> str:
    if any(i.severity == "error" for i in issues):
        return "blocked"
    if any(i.severity == "warn" for i in issues):
        return "review"
    return "ok"


def _dedupe(issues: Sequence[Issue]) -> list[Issue]:
    seen, out = set(), []
    for i in issues:
        key = (i.code, i.where, i.message)
        if key not in seen:
            seen.add(key)
            out.append(i)
    return out


def finalize_draft(draft: Draft, brief: Brief) -> Draft:
    """Claims profile: long-form drafts about using a light device end with a safety note.

    The brand's own text (``brief.safety_note``) is judged like any other copy; the vertical's template
    footer is pre-approved and marked exempt, because its job is to say what the device is not.
    """
    from . import claims

    profile = claims.profile_for(brief)
    if profile is None or draft.format not in profile.long_form or draft.parts.get("safety_note"):
        return draft
    own = (brief.safety_note or "").strip()
    footer = own or str(profile.footer.get(brief.lang) or profile.footer.get("en") or "").strip()
    if not footer:
        return draft
    draft.body = draft.body.rstrip() + "\n\n" + footer
    draft.parts["safety_note"] = footer
    if not own:
        draft.parts["guard_exempt"] = [*draft.parts.get("guard_exempt", []), footer]
    return draft


def safe_candidates(candidates: Sequence[Any], brief: Brief, shield: Any) -> list[Any]:
    """Drop hook candidates that the claims profile would block (a hook must pass before it is offered)."""
    from . import claims

    if claims.profile_for(brief) is None:
        return list(candidates)
    return [c for c in candidates if not any(i.severity == "error" for i in shield.check(c.text, brief))]


def check_draft(draft: Draft, brief: Brief, *, shield: Any = None, ledger: Any = None) -> list[Issue]:
    """Format validator + Trust Shield (+ SEO quality gate for articles)."""
    from . import formats as registry
    from .guard import TrustShield

    issues = list(registry.validate_draft(draft))
    issues += (shield or TrustShield(ledger)).check(draft, brief)
    if draft.format == "seo_article":
        try:
            from .seo import quality_gate
            issues += quality_gate(draft, brief)
        except ImportError:
            pass
    issues = _dedupe(issues)
    if draft.format in OPTION_LIST_FORMATS:
        issues = [i for i in issues if i.code != "KEYWORD_STUFFING"]
    if draft.format in NO_INLINE_DISCLOSURE:
        # Not blocking: the label belongs to the ad placement or the finished message, not to this copy set.
        issues = [Issue("warn", i.code, i.message + (" Label it in the ad placement or the final message." if brief.lang != "cs"
                                                      else " Označte to v reklamním umístění nebo ve finální zprávě."), i.where)
                  if i.code == "DISCLOSURE_MISSING" else i for i in issues]
    if any(i.code == "PLACEHOLDER_OPEN" for i in issues):
        issues = [i for i in issues if i.code != "SLOTS_OPEN"]
    return issues


def _feedback(skeleton: Skeleton, draft: Draft, issues: Sequence[Issue], brief: Brief) -> dict[str, list[str]]:
    """Map remarks to the slots they concern, so the writer rewrites only those."""
    values = draft.parts.get("slots", {})
    feedback: dict[str, list[str]] = {}
    for issue in issues:
        if issue.severity == "info" or not issue.where or issue.code == "SLOTS_OPEN":
            continue
        if issue.where in values:                       # builders report a slot id or a location label
            feedback.setdefault(issue.where, []).append(f"{issue.code}: {issue.message}")
            continue
        needle = issue.where.strip("[]. ")[:40]         # the guard reports a short excerpt of the text
        for slot_id, text in values.items():
            if needle and needle in text:
                feedback.setdefault(slot_id, []).append(f"{issue.code}: {issue.message}")
                break
    hook = score_hook(draft.hook, lang=brief.lang)
    if skeleton.hook_slot in values and (hook.clickbait_risk > 0.35 or hook.total < 40):
        tips = [t["en"] for t in hook.tips] or ["Make the hook more concrete and more specific to the audience."]
        feedback.setdefault(skeleton.hook_slot, []).append("HOOK_WEAK: " + " ".join(tips))
    return feedback


def _build_with_fitting_hook(spec: Any, brief: Brief, candidates: Sequence[Any], options: dict | None) -> Skeleton:
    if spec.family == "hooks":
        return spec.build(brief, hook=None, options=options)
    first = None
    for cand in list(candidates)[:8] or [None]:
        sk = spec.build(brief, hook=cand.text if cand else None, options=options)
        first = first or sk
        try:
            slot = sk.slot(sk.hook_slot)
        except KeyError:
            return sk
        if not slot_violations(slot, slot.default or ""):
            return sk
    return first  # type: ignore[return-value]


def slot_template(
    brief: Brief,
    formats: Sequence[str] | None = None,
    *,
    ledger: Any = None,
    options: dict[str, dict[str, Any]] | None = None,
    n_hooks: int = 12,
) -> dict[str, Any]:
    """Every slot of the chosen formats with its instruction and limits, to be filled by a person or another model.

    The shape is what ``FileWriter`` reads: ``{format_id: {slot_id: {"text": "", ...}}}``. Leave ``text`` empty to keep the default.
    """
    from . import formats as registry
    from .guard import TrustShield
    from .hooks import generate_hooks

    candidates = safe_candidates(generate_hooks(brief, n=n_hooks), brief, TrustShield(ledger))
    out: dict[str, Any] = {"_help": (
        "Fill the text fields (plain text or Markdown, language of the brief, no long dashes), leave a text empty to keep the "
        "default, delete the formats you do not need, then run: kingctl forge ... --writer file --fills THIS_FILE. "
        "The Trust Shield checks everything you write, so facts and sources must come from the brief.")}
    for fid in (formats or DEFAULT_FORMATS):
        try:
            spec = registry.get_format(fid)
        except KeyError:
            continue
        skeleton = _build_with_fitting_hook(spec, brief, candidates, (options or {}).get(fid))
        slots: dict[str, Any] = {}
        for s in skeleton.slots:
            limits = {k: v for k, v in (("max_chars", s.max_chars), ("min_chars", s.min_chars), ("max_words", s.max_words)) if v is not None}
            if s.must_include:
                limits["must_include"] = list(s.must_include)
            slots[s.id] = {"kind": s.kind, "instruction": s.instruction, "limits": limits, "default": s.default or "", "text": ""}
        out[fid] = slots
    return out


def build_pack(
    brief: Brief,
    formats: Sequence[str] | None = None,
    *,
    writer: Writer | None = None,
    ledger: Any = None,
    options: dict[str, dict[str, Any]] | None = None,
    improve_rounds: int = 1,
    n_hooks: int = 12,
) -> Pack:
    from . import formats as registry
    from .guard import TrustShield
    from .hooks import generate_hooks

    writer = writer or OfflineWriter()
    shield = TrustShield(ledger)
    candidates = safe_candidates(generate_hooks(brief, n=n_hooks), brief, shield)
    items: list[PackItem] = []
    errors: list[str] = []
    for fid in (formats or DEFAULT_FORMATS):
        try:
            spec = registry.get_format(fid)
        except KeyError as err:
            errors.append(str(err))
            continue
        skeleton = _build_with_fitting_hook(spec, brief, candidates, (options or {}).get(fid))
        fills = writer.fill(skeleton, brief)
        draft = finalize_draft(skeleton.render(fills), brief)
        issues = check_draft(draft, brief, shield=shield)
        rounds = 0
        reviser = getattr(writer, "revise", None)
        while reviser and rounds < improve_rounds:
            feedback = _feedback(skeleton, draft, issues, brief)
            if not feedback:
                break
            fills = reviser(skeleton, brief, fills, feedback)
            draft = finalize_draft(skeleton.render(fills), brief)
            issues = check_draft(draft, brief, shield=shield)
            rounds += 1
        hs = score_hook(draft.hook, lang=brief.lang)
        scores: dict[str, float | None] = {"dopamine": round(hs.total, 1), "seo": None, "geo": None}
        if draft.format == "seo_article":
            try:
                from .seo import seo_score
                scores["seo"] = round(seo_score(draft, brief).score, 1)
            except ImportError:
                pass
        if draft.format in ARTICLE_FORMATS:
            try:
                from .geo import geo_score
                scores["geo"] = round(geo_score(draft, brief).score, 1)
            except ImportError:
                pass
        alts = [{"text": c.text, "score": round(c.score, 1), "style": c.style} for c in candidates if c.text != draft.hook][:3]
        items.append(PackItem(
            format=fid, name_en=spec.name_en, name_cs=spec.name_cs, family=spec.family, hook=draft.hook, body=draft.body,
            hook_score=hs.to_dict(), issues=[i.to_dict() for i in issues], verdict=_verdict(issues), scores=scores,
            alt_hooks=alts, parts=_json_safe(draft.parts), slots_open=draft.slots_open, rounds=rounds,
        ))
    dopamine = [i.scores["dopamine"] for i in items if i.scores.get("dopamine") is not None]
    summary = {
        "n_items": len(items),
        "avg_dopamine": round(sum(dopamine) / len(dopamine), 1) if dopamine else 0.0,
        "errors": sum(1 for i in items for x in i.issues if x["severity"] == "error"),
        "warnings": sum(1 for i in items for x in i.issues if x["severity"] == "warn"),
        "open_slots": sum(len(i.slots_open) for i in items),
        "verdicts": {v: sum(1 for i in items if i.verdict == v) for v in ("ok", "review", "blocked")},
        "claims_profile": brief.claims_profile,
    }
    return Pack(brief.to_dict(), getattr(writer, "name", "custom"), datetime.now(timezone.utc).isoformat(timespec="seconds"),
                items, summary, errors)


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return json.loads(json.dumps(value, default=str))
