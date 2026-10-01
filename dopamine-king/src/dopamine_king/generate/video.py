"""Video, YouTube and podcast script builders with a real timing model.

A script is a list of beats. ``plan_beats`` divides the requested duration into whole seconds (the beats
add up to the duration exactly), gives every beat a word budget (duration times speaking rate), plans a
visual change at least every 4 seconds and marks beats that open with a pattern interrupt. Every beat has
three slots: ``vo_<id>`` (voiceover), ``text_<id>`` (on-screen text, at most 6 words) and ``visual_<id>``
(shot or b-roll). ``assemble`` turns the filled slots into ``beats``, a Markdown ``timeline_md`` table and
SubRip ``srt`` captions. Defaults only restate the brief (hook from the hook library, CTA, disclosure);
voiceover, proof and visuals have no default so the offline draft shows explicit placeholders.
"""
from __future__ import annotations

import math
import re
from typing import Any, Callable

from .formats import (
    DISCLOSURE_TAG, PLACEHOLDER_RE, brief_meta, fit, has_disclosure, has_placeholder, keyword_in, lang_of,
    pick, slot_text, standard_notes, strip_placeholders, topic_hashtags, word_count,
)
from .hooks import cached_score, choose_hook, generate_hooks
from .types import Brief, Draft, FormatSpec, Issue, Skeleton, Slot

SPEECH_RATE = {"en": 2.6, "cs": 2.4}          # words per second of natural narration
SHORT_DURATIONS = (15, 30, 45, 60, 90)
SHORT_STYLES = ("talking_head", "voiceover_broll", "screen_demo", "ugc")
PLAN_STYLES = SHORT_STYLES + ("pas",)          # "pas" is the problem-agitate-solution plan of ugc_ad_script
HOOK_MAX_S = 3                                 # the hook beat of a short never exceeds 3 seconds
CUT_EVERY_S = 4                                # a visual change at least this often
DISCLOSURE_S = 3
ON_SCREEN_MAX_WORDS = 6
WORDS_WARN = 1.10                              # voiceover over 110 percent of the budget warns
WORDS_ERROR = 1.40                             # over 140 percent is an error
SRT_CHUNK_WORDS = 7
SRT_MAX_LINES = 2
SRT_LINE_CHARS = 38
MIN_BEAT_S = 3
TITLE_MAX_CHARS = 70
THUMB_MAX_WORDS = 4
PATTERN_INTERRUPT_GAP_S = 6                    # flag an interrupt when this long passed since the last one


# -- timing model ----------------------------------------------------------------------
def speech_rate(lang: str) -> float:
    """Narration speed in words per second (English 2.6, Czech 2.4)."""
    return SPEECH_RATE.get(lang, SPEECH_RATE["en"])


def estimate_duration(text: str, lang: str) -> float:
    """Seconds needed to speak the text (placeholders ignored)."""
    return word_count(text) / speech_rate(lang)


def fmt_time(seconds: int | float) -> str:
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def split_seconds(total: int, weights: list[float], minimum: int = MIN_BEAT_S) -> list[int]:
    """Split ``total`` whole seconds proportionally to ``weights``; every part gets at least ``minimum``."""
    n = len(weights)
    rest = total - minimum * n
    if rest < 0:
        raise ValueError(f"{total} s is too short for {n} beats of at least {minimum} s")
    wsum = sum(weights)
    raw = [rest * w / wsum for w in weights]
    parts = [int(x) for x in raw]
    left = rest - sum(parts)
    for i in sorted(range(n), key=lambda i: (-(raw[i] - parts[i]), i))[:left]:
        parts[i] += 1
    return [minimum + p for p in parts]


# beat structure of a short by duration row: the middle beats between hook and CTA
_MIDDLE = {
    15: ["point_1", "point_2"],
    30: ["problem", "point_1", "point_2", "proof"],
    45: ["problem", "point_1", "point_2", "point_3", "recap"],
    60: ["problem", "point_1", "point_2", "point_3", "proof", "recap"],
    90: ["problem", "point_1", "point_2", "point_3", "point_4", "point_5", "proof", "recap"],
}
_PAS_MIDDLE = ["problem", "agitate", "solution", "proof"]
_CTA_S = {15: 3, 30: 4, 45: 5, 60: 6, 90: 7}
_WEIGHTS = {"problem": 1.0, "agitate": 1.0, "solution": 1.3, "point": 1.3, "proof": 1.0, "recap": 0.8}
_LABELS = {
    "en": {"hook": "Hook", "disclosure": "Disclosure", "problem": "Problem", "agitate": "Agitate", "solution": "Solution",
           "point": "Point {n}", "proof": "Proof", "recap": "Recap", "cta": "Call to action",
           "setup": "Setup", "step": "Step {n}", "result": "Result"},
    "cs": {"hook": "Hook", "disclosure": "Označení spolupráce", "problem": "Problém", "agitate": "Vyostření",
           "solution": "Řešení", "point": "Bod {n}", "proof": "Důkaz", "recap": "Shrnutí", "cta": "Výzva k akci",
           "setup": "Příprava", "step": "Krok {n}", "result": "Výsledek"},
}
_SCREEN_DEMO_KIND = {"problem": "setup", "point": "step", "proof": "result"}


def beat_kind(beat_id: str) -> str:
    return beat_id.rsplit("_", 1)[0] if re.search(r"_\d+$", beat_id) else beat_id


def beat_label(beat_id: str, style: str, lang: str) -> str:
    kind = beat_kind(beat_id)
    if style == "screen_demo":
        kind = _SCREEN_DEMO_KIND.get(kind, kind)
    num = beat_id.rsplit("_", 1)[1] if re.search(r"_\d+$", beat_id) else ""
    return _LABELS.get(lang, _LABELS["en"])[kind].format(n=num)


def _row(duration_s: int) -> int:
    for limit, row in ((20, 15), (37, 30), (52, 45), (75, 60)):
        if duration_s <= limit:
            return row
    return 90


def plan_beats(duration_s: int, style: str = "talking_head", lang: str = "en", *, disclosure: bool = False) -> list[dict]:
    """Beat plan for a short video of ``duration_s`` seconds (at least 15).

    Each beat: id, label, start, end (whole seconds, contiguous, summing to the duration exactly),
    max_words (duration times speaking rate), pattern_interrupt (the beat opens with a deliberate
    interrupt such as a zoom, sound hit, text pop or angle change), cuts and visual_changes (planned
    visual change times in seconds, never more than 4 seconds apart across the whole video). The hook
    beat is 3 seconds, the CTA beat is last. With
    ``disclosure`` a 3 second paid partnership beat follows the hook.
    """
    if style not in PLAN_STYLES:
        raise ValueError(f"unknown video style {style!r}; valid styles: {', '.join(PLAN_STYLES)}")
    if duration_s < 15:
        raise ValueError("a short video needs at least 15 seconds")
    row = _row(duration_s)
    middle = list(_PAS_MIDDLE if style == "pas" else _MIDDLE[row])
    disc_s = DISCLOSURE_S if disclosure else 0
    rest = duration_s - HOOK_MAX_S - _CTA_S[row] - disc_s
    lengths = split_seconds(rest, [_WEIGHTS[beat_kind(i)] for i in middle])
    ids = ["hook"] + (["disclosure"] if disclosure else []) + middle + ["cta"]
    secs = [HOOK_MAX_S] + ([disc_s] if disclosure else []) + lengths + [_CTA_S[row]]
    rate = speech_rate(lang)
    beats: list[dict] = []
    t = 0
    last_flag = None
    for bid, d in zip(ids, secs):
        flag = bid == "hook" or beat_kind(bid) == "proof" or (last_flag is not None and t - last_flag >= PATTERN_INTERRUPT_GAP_S)
        if bid == "cta":
            flag = False
        if flag:
            last_flag = t
        cuts = max(1, math.ceil(d / CUT_EVERY_S))
        beats.append({
            "id": bid, "label": beat_label(bid, style, lang), "start": t, "end": t + d,
            "max_words": int(d * rate), "pattern_interrupt": flag, "cuts": cuts,
            "visual_changes": [round(t + i * d / cuts, 2) for i in range(cuts)],
        })
        t += d
    return beats


# -- captions ---------------------------------------------------------------------------
def _chunk_words(ws: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = []
    cur: list[str] = []
    for w in ws:
        cur.append(w)
        if len(cur) >= SRT_CHUNK_WORDS or w.endswith((".", "!", "?")) or (w.endswith((",", ";", ":")) and len(cur) >= 4):
            chunks.append(cur)
            cur = []
    if cur:
        chunks.append(cur)
    if len(chunks) >= 2 and len(chunks[-1]) == 1 and len(chunks[-2]) < SRT_CHUNK_WORDS \
            and not chunks[-2][-1].endswith((".", "!", "?")):
        chunks[-2].extend(chunks.pop())
    return chunks


def _wrap(chunk: list[str]) -> str:
    text = " ".join(chunk)
    if len(text) <= SRT_LINE_CHARS or len(chunk) < 2:
        return text
    best = min(range(1, len(chunk)), key=lambda i: abs(len(" ".join(chunk[:i])) - len(" ".join(chunk[i:]))))
    return " ".join(chunk[:best]) + "\n" + " ".join(chunk[best:])


def _ts(ms: int) -> str:
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(beats: list[dict], lang: str) -> str:
    """SubRip captions from beat voiceovers.

    Chunks of at most 7 words and 2 lines, timed proportionally to their words inside the beat window,
    contiguous inside a beat, never overlapping and never past the beat end. Beats whose voiceover is
    still an [[ADD ...]] placeholder are skipped.
    """
    blocks: list[str] = []
    for beat in beats:
        text = strip_placeholders(beat.get("voiceover", "")).strip()
        if not text:
            continue
        chunks = _chunk_words(text.split())
        total = sum(len(c) for c in chunks)
        start_ms, end_ms = round(beat["start"] * 1000), round(beat["end"] * 1000)
        span = end_ms - start_ms
        done = 0
        for chunk in chunks:
            t0 = start_ms + round(span * done / total)
            done += len(chunk)
            t1 = start_ms + round(span * done / total)
            if t1 > t0:
                blocks.append(f"{len(blocks) + 1}\n{_ts(t0)} --> {_ts(t1)}\n{_wrap(chunk)}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


_SRT_TIME_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3}) --> (\d{2}):(\d{2}):(\d{2}),(\d{3})$")


def parse_srt(srt: str) -> list[dict]:
    """Parse SubRip text into cues; raises ValueError when it is malformed."""
    cues: list[dict] = []
    for block in [b for b in srt.strip().split("\n\n") if b.strip()]:
        lines = block.split("\n")
        if len(lines) < 3 or not lines[0].isdigit():
            raise ValueError(f"bad cue block: {block[:40]!r}")
        m = _SRT_TIME_RE.match(lines[1])
        if not m:
            raise ValueError(f"bad timing line: {lines[1]!r}")
        g = [int(x) for x in m.groups()]
        cues.append({"index": int(lines[0]), "start": ((g[0] * 60 + g[1]) * 60 + g[2]) * 1000 + g[3],
                     "end": ((g[4] * 60 + g[5]) * 60 + g[6]) * 1000 + g[7], "lines": lines[2:]})
    return cues


def _cell(text: str, lang: str) -> str:
    t = PLACEHOLDER_RE.sub(pick(lang, "(open)", "(doplnit)"), text or "")
    return " ".join(t.replace("|", "/").split())


def timeline_md(beats: list[dict], lang: str = "en") -> str:
    """Markdown table of the beats. Beats that open with a pattern interrupt carry an asterisk."""
    head = pick(lang, ("Time", "Beat", "Voiceover", "On-screen text", "Visual"),
                ("Čas", "Část", "Voiceover", "Text na obrazovce", "Obraz"))
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for b in beats:
        label = b["label"] + (" *" if b.get("pattern_interrupt") else "")
        lines.append(f"| {fmt_time(b['start'])}-{fmt_time(b['end'])} | {label} | {_cell(b['voiceover'], lang)} | "
                     f"{_cell(b['on_screen_text'], lang)} | {_cell(b['visual'], lang)} |")
    lines.append("")
    lines.append(pick(lang, "* pattern interrupt: zoom, sound hit, text pop or angle change",
                      "* pattern interrupt: přiblížení, zvuk, text nebo změna úhlu"))
    return "\n".join(lines)


# -- beat based skeletons ------------------------------------------------------------------
_VISUAL_HINT = {
    "talking_head": "Face to camera: describe framing and gesture.",
    "voiceover_broll": "B-roll shot list that illustrates the voiceover.",
    "screen_demo": "Screen recording: what is on screen and what is clicked or highlighted.",
    "ugc": "Handheld, natural light, product in use or selfie angle.",
    "pas": "Handheld, natural light, product in use or selfie angle.",
}


def _vo_instruction(beat: dict, brief: Brief, style: str) -> str:
    kind, mw, aud = beat_kind(beat["id"]), beat["max_words"], brief.audience
    n = beat["id"].rsplit("_", 1)[1] if re.search(r"_\d+$", beat["id"]) else ""
    if style == "screen_demo" and kind in _SCREEN_DEMO_KIND:
        text = {
            "problem": f"Setup: what the viewer sees at the start and what they want to achieve (max {mw} words).",
            "point": f"Step {n}: say what you do and why (max {mw} words).",
            "proof": f"Result: show the real outcome on screen. Never invent numbers (max {mw} words).",
        }[kind]
        return text
    return {
        "hook": f"Hook, spoken in {beat['end'] - beat['start']} s (max {mw} words): promise one specific payoff for {aud}. No clickbait.",
        "disclosure": f"Spoken disclosure of the paid partnership with {brief.brand} (max {mw} words).",
        "problem": f"The problem {aud} feel, in their own words (max {mw} words).",
        "agitate": f"Make the cost of the problem concrete without exaggeration (max {mw} words).",
        "solution": f"Introduce the solution and how it works in plain words (max {mw} words).",
        "point": f"Point {n}: one idea with one concrete example (max {mw} words).",
        "proof": f"Real proof only: a fact from the brief, a documented result or a live demo. Never invent numbers or testimonials (max {mw} words).",
        "recap": f"Recap the takeaway in one sentence (max {mw} words).",
        "cta": f"One clear call to action (max {mw} words).",
    }[kind]


def _beat_slots(brief: Brief, plan: list[dict], style: str, hook: str | None) -> list[Slot]:
    lang = lang_of(brief)
    slots: list[Slot] = []
    for b in plan:
        bid, kind = b["id"], beat_kind(b["id"])
        d = b["end"] - b["start"]
        vo = tx = vis = None
        if kind == "hook":
            vo = choose_hook(brief, hook, max_words=b["max_words"])
            tx = fit(vo, max_words=ON_SCREEN_MAX_WORDS)
        elif kind == "disclosure":
            vo = fit(pick(lang, f"Paid partnership with {brief.brand}.", f"Reklamní spolupráce se značkou {brief.brand}."),
                     max_words=b["max_words"])
            tx = DISCLOSURE_TAG[lang]
            vis = pick(lang, "Show the paid partnership label on screen.", "Zobrazte na obrazovce označení reklamní spolupráce.")
        elif kind == "cta":
            vo = fit(brief.cta, max_words=b["max_words"])
            tx = fit(brief.cta, max_words=ON_SCREEN_MAX_WORDS)
        slots.append(Slot(f"vo_{bid}", _vo_instruction(b, brief, style), max_words=b["max_words"], kind="text", default=vo))
        slots.append(Slot(f"text_{bid}", f"On-screen text, at most {ON_SCREEN_MAX_WORDS} words: the key phrase of this beat.",
                          max_words=ON_SCREEN_MAX_WORDS, kind="line", default=tx))
        spacing = round(d / b["cuts"], 1)
        slots.append(Slot(f"visual_{bid}", f"{_VISUAL_HINT[style]} Plan {b['cuts']} shot(s), a visual change every {spacing} s or less.",
                          kind="text", default=vis))
    return slots


def _beat_template(plan: list[dict], lang: str) -> list[str]:
    vo, tx, vis = pick(lang, ("Voiceover", "On-screen text", "Visual"), ("Voiceover", "Text na obrazovce", "Obraz"))
    out = []
    for b in plan:
        i = b["id"]
        out.append(f"### {fmt_time(b['start'])}-{fmt_time(b['end'])} {b['label']}\n\n"
                   f"- **{vo}:** " + "{{vo_%s}}\n" % i + f"- **{tx}:** " + "{{text_%s}}\n" % i + f"- **{vis}:** " + "{{visual_%s}}" % i)
    return out


def _assemble_beats(plan: list[dict], lang: str, extra: Callable[[list[dict], dict[str, str]], dict[str, Any]] | None = None):
    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        beats = []
        for b in plan:
            i = b["id"]
            voiceover = values[f"vo_{i}"] + (" " + values[f"loop_{i}"] if f"loop_{i}" in values else "")
            beats.append({
                "id": i, "label": b["label"], "start": b["start"], "end": b["end"], "voiceover": voiceover,
                "on_screen_text": values[f"text_{i}"], "visual": values[f"visual_{i}"],
                "pattern_interrupt": b["pattern_interrupt"], "max_words": b["max_words"], "cuts": b["cuts"],
                "visual_changes": b["visual_changes"],
            })
        out: dict[str, Any] = {"beats": beats, "timeline_md": timeline_md(beats, lang), "srt": to_srt(beats, lang)}
        if extra:
            out.update(extra(beats, values))
        return out
    return assemble


def _post_slots(brief: Brief) -> tuple[list[Slot], list[str]]:
    """Caption, hashtags and (when sponsored) disclosure slots that follow the script."""
    lang = lang_of(brief)
    slots = [
        Slot("caption", "Post caption, at most 150 characters, carrying the hook idea. No engagement bait.", max_chars=150, kind="line"),
        Slot("hashtags", "Three relevant hashtags on one line.", max_chars=100, kind="line",
             default=" ".join(topic_hashtags(brief, 3)) or None),
    ]
    parts = [pick(lang, "**Caption:** ", "**Popisek:** ") + "{{caption}}", "**Hashtags:** {{hashtags}}"]
    if brief.sponsored:
        slots.append(Slot("disclosure", "Paid partnership disclosure for the caption (for example #ad).", max_chars=40,
                          kind="line", default=DISCLOSURE_TAG[lang]))
        parts.append(pick(lang, "**Disclosure:** ", "**Označení:** ") + "{{disclosure}}")
    return slots, parts


def _opt_choice(options: dict | None, key: str, default: Any, valid: tuple) -> Any:
    value = (options or {}).get(key, default)
    if value not in valid:
        raise ValueError(f"option {key}={value!r} is not valid; use one of {', '.join(str(v) for v in valid)}")
    return value


def build_short_video_script(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Short video script (TikTok, Reels, Shorts). options: duration in 15/30/45/60/90, style."""
    duration = _opt_choice(options, "duration", 30, SHORT_DURATIONS)
    style = _opt_choice(options, "style", "talking_head", SHORT_STYLES)
    lang = lang_of(brief)
    plan = plan_beats(duration, style, lang, disclosure=brief.sponsored)
    post_slots, post_parts = _post_slots(brief)
    title = pick(lang, "Short video script", "Scénář krátkého videa")
    parts = [f"# {title}: {brief.topic} ({duration} s, {style})"] + _beat_template(plan, lang) + post_parts
    return Skeleton(
        format="short_video_script", lang=lang, template="\n\n".join(parts), slots=_beat_slots(brief, plan, style, hook) + post_slots,
        fixed={"duration": duration, "style": style, "plan": plan, "speech_rate": speech_rate(lang),
               "hook_max_s": HOOK_MAX_S, "cut_every_s": CUT_EVERY_S},
        meta=brief_meta(brief, duration_s=duration, style=style, hook_max_s=HOOK_MAX_S, short=True),
        hook_slot="vo_hook", assemble=_assemble_beats(plan, lang),
        notes=standard_notes(brief, f"Budget: {speech_rate(lang)} words per second. Hook within {HOOK_MAX_S} s, a visual change at least every {CUT_EVERY_S} s."),
    )


def build_ugc_ad_script(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """UGC style ad, Problem-Agitate-Solution with a proof beat. options: duration in 30/45/60 (default 30)."""
    duration = _opt_choice(options, "duration", 30, (30, 45, 60))
    lang = lang_of(brief)
    plan = plan_beats(duration, "pas", lang, disclosure=brief.sponsored)
    post_slots, post_parts = _post_slots(brief)
    title = pick(lang, "UGC ad script", "Scénář UGC reklamy")
    parts = [f"# {title}: {brief.topic} ({duration} s, PAS)"] + _beat_template(plan, lang) + post_parts
    notes = ["Proof must be real: a documented fact, a result you can show or a live demo. Never invent testimonials or numbers.",
             f"Hook within {HOOK_MAX_S} s, a visual change at least every {CUT_EVERY_S} s."]
    if brief.sponsored:
        notes.append("Paid partnership: the disclosure beat must stay in the video and the label in the caption.")
    else:
        notes.append("If the creator is paid or receives free product, add a disclosure before publishing.")
    return Skeleton(
        format="ugc_ad_script", lang=lang, template="\n\n".join(parts), slots=_beat_slots(brief, plan, "pas", hook) + post_slots,
        fixed={"duration": duration, "style": "pas", "plan": plan, "speech_rate": speech_rate(lang),
               "hook_max_s": HOOK_MAX_S, "cut_every_s": CUT_EVERY_S},
        meta=brief_meta(brief, duration_s=duration, style="pas", hook_max_s=HOOK_MAX_S, short=True),
        hook_slot="vo_hook", assemble=_assemble_beats(plan, lang), notes=standard_notes(brief, *notes),
    )


# -- beat validators --------------------------------------------------------------------------
def check_srt(draft: Draft) -> list[Issue]:
    srt = draft.parts.get("srt", "")
    if not srt.strip():
        return []
    try:
        cues = parse_srt(srt)
    except ValueError as exc:
        return [Issue("error", "SRT_MALFORMED", str(exc))]
    issues: list[Issue] = []
    beats = draft.parts.get("beats") or []
    prev_end = 0
    for n, cue in enumerate(cues, 1):
        where = f"cue {cue['index']}"
        if cue["index"] != n:
            issues.append(Issue("error", "SRT_MALFORMED", f"Cue numbering is not sequential at {n}.", where))
        if cue["end"] <= cue["start"]:
            issues.append(Issue("error", "SRT_MALFORMED", "Cue ends before it starts.", where))
        if cue["start"] < prev_end:
            issues.append(Issue("error", "SRT_MALFORMED", "Cue overlaps the previous cue.", where))
        prev_end = max(prev_end, cue["end"])
        if len(cue["lines"]) > SRT_MAX_LINES or sum(len(l.split()) for l in cue["lines"]) > SRT_CHUNK_WORDS:
            issues.append(Issue("error", "SRT_MALFORMED", f"Cue is longer than {SRT_CHUNK_WORDS} words or {SRT_MAX_LINES} lines.", where))
        if beats and not any(b["start"] * 1000 <= cue["start"] and cue["end"] <= b["end"] * 1000 for b in beats):
            issues.append(Issue("error", "SRT_MALFORMED", "Cue runs outside its beat window.", where))
    return issues


def check_beats(draft: Draft) -> list[Issue]:
    """Timing, budget, caption and disclosure checks shared by the beat based scripts."""
    beats = draft.parts.get("beats") or []
    issues: list[Issue] = []
    if not beats:
        return [Issue("error", "NO_BEATS", "The script has no beats.")]
    ids = [b["id"] for b in beats]
    if "cta" not in ids:
        issues.append(Issue("error", "CTA_BEAT_MISSING", "The script needs a call to action beat."))
    elif ids[-1] != "cta":
        issues.append(Issue("error", "CTA_BEAT_NOT_LAST", "The call to action beat must be the last beat."))
    t = 0
    for b in beats:
        if b["start"] != t or b["end"] <= b["start"]:
            issues.append(Issue("error", "TIMELINE_BROKEN", f"Beat {b['id']} does not follow the previous beat.", b["id"]))
        t = b["end"]
    total = draft.meta.get("duration_s")
    if total and t != total:
        issues.append(Issue("error", "DURATION_MISMATCH", f"Beats add up to {t} s, expected {total} s."))
    hook_max = draft.meta.get("hook_max_s")
    if hook_max and beats[0]["id"] == "hook" and beats[0]["end"] - beats[0]["start"] > hook_max:
        issues.append(Issue("error", "HOOK_BEAT_LONG", f"The hook beat is longer than {hook_max} s.", "hook"))
    for b in beats:
        n, budget = word_count(b["voiceover"]), b.get("max_words") or 0
        if budget and n > budget * WORDS_ERROR:
            issues.append(Issue("error", "WORDS_OVER_BUDGET", f"{n} words, the beat fits {budget} (over 140 percent).", b["id"]))
        elif budget and n > budget * WORDS_WARN:
            issues.append(Issue("warn", "WORDS_OVER_BUDGET", f"{n} words, the beat fits {budget} (over 110 percent).", b["id"]))
        if word_count(b["on_screen_text"]) > ON_SCREEN_MAX_WORDS:
            issues.append(Issue("warn", "ONSCREEN_TEXT_LONG", f"On-screen text is longer than {ON_SCREEN_MAX_WORDS} words.", b["id"]))
    if draft.meta.get("short"):
        changes = sorted(c for b in beats for c in b.get("visual_changes", []))
        points = changes + [t]
        if changes and (changes[0] > 0 or any(b - a > CUT_EVERY_S for a, b in zip(points, points[1:]))):
            issues.append(Issue("warn", "VISUAL_CADENCE", f"A visual change is needed at least every {CUT_EVERY_S} s."))
        if not beats[0].get("pattern_interrupt"):
            issues.append(Issue("warn", "PATTERN_INTERRUPT_MISSING", "Open with a pattern interrupt in the hook beat.", "hook"))
    issues += check_srt(draft)
    if draft.meta.get("sponsored"):
        text = " ".join(b["voiceover"] + " " + b["on_screen_text"] for b in beats) + " " + " ".join(slot_text(draft, k) for k in ("caption", "disclosure", "description"))
        if not has_disclosure(text):
            issues.append(Issue("error", "DISCLOSURE_MISSING", "Sponsored video needs a spoken or on-screen disclosure and a caption label."))
    if draft.slots_open:
        issues.append(Issue("info", "SLOTS_OPEN", f"{len(draft.slots_open)} slot(s) are still open (a human fills them when shooting)."))
    return issues


def validate_short_video_script(draft: Draft) -> list[Issue]:
    return check_beats(draft)


def validate_ugc_ad_script(draft: Draft) -> list[Issue]:
    issues = check_beats(draft)
    if not draft.meta.get("sponsored"):
        issues.append(Issue("info", "DISCLOSURE_REMINDER", "UGC style ads need a disclosure when the creator is paid or gets free product."))
    return issues


# -- YouTube script ------------------------------------------------------------------------------
YT_HOOK_S = 30                    # cold open window (0:00-0:30)
YT_CRED_S = 15
YT_CTA_S = 30
YT_LOOP_WORDS = 25
YT_CUT_EVERY_S = 10
YT_CHAPTER_TITLE_CHARS = 60
YT_DESCRIPTION_CHARS = 1500
YT_MINUTES = (5, 15)
_YT_LABELS = {
    "en": {"hook": "Cold open", "cred": "Credibility", "recap": "Mid-video recap", "cta": "Call to action", "ch": "Chapter {n}",
           "intro": "Intro", "wrap": "Wrap-up"},
    "cs": {"hook": "Úvodní hook", "cred": "Důvěryhodnost", "recap": "Shrnutí v polovině", "cta": "Výzva k akci",
           "ch": "Kapitola {n}", "intro": "Úvod", "wrap": "Závěr"},
}


def plan_youtube(minutes: int, lang: str = "en") -> list[dict]:
    """Beat plan of a YouTube script: cold open, credibility, 3-5 chapters, mid-video recap, CTA."""
    minutes = max(YT_MINUTES[0], min(YT_MINUTES[1], int(minutes)))
    total = minutes * 60
    k = 3 if minutes <= 6 else 4 if minutes <= 10 else 5
    recap_s = 45 if minutes >= 7 else 30
    chapters = split_seconds(total - YT_HOOK_S - YT_CRED_S - recap_s - YT_CTA_S, [1.0] * k, minimum=30)
    rate = speech_rate(lang)
    labels = _YT_LABELS.get(lang, _YT_LABELS["en"])
    order = [("hook", YT_HOOK_S, True), ("cred", YT_CRED_S, False)]
    for i, d in enumerate(chapters, 1):
        order.append((f"ch{i}", d, True))
        if i == math.ceil(k / 2):
            order.append(("recap", recap_s, True))
    order.append(("cta", YT_CTA_S, False))
    beats, t = [], 0
    for bid, d, flag in order:
        cuts = max(1, math.ceil(d / YT_CUT_EVERY_S))
        label = labels["ch"].format(n=bid[2:]) if bid.startswith("ch") else labels[bid]
        beats.append({"id": bid, "label": label, "start": t, "end": t + d, "max_words": int(d * rate),
                      "pattern_interrupt": flag, "cuts": cuts,
                      "visual_changes": [round(t + i * d / cuts, 2) for i in range(cuts)]})
        t += d
    return beats


def _yt_vo_instruction(b: dict, brief: Brief) -> str:
    mw, kind = b["max_words"], b["id"]
    if kind == "hook":
        return (f"Cold open (0:00-0:30, max {mw} words): start with the hook, then preview exactly what the viewer gets by the end. "
                "Promise only what the video delivers.")
    if kind == "cred":
        return f"One or two lines that earn trust: why you can speak on this. Only true facts from the brief (max {mw} words)."
    if kind == "recap":
        return f"Mid-video recap of what was covered and what is still coming (max {mw} words)."
    if kind == "cta":
        return f"One clear call to action and a pointer to the next video (max {mw} words)."
    return f"Chapter {kind[2:]} script for {brief.audience}: concrete, with one example (max {mw - YT_LOOP_WORDS} words)."


def build_youtube_script(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """YouTube script. options: minutes 5..15 (default 8)."""
    try:
        minutes = int((options or {}).get("minutes", 8))
    except (TypeError, ValueError):
        minutes = 8
    minutes = max(YT_MINUTES[0], min(YT_MINUTES[1], minutes))
    lang = lang_of(brief)
    plan = plan_youtube(minutes, lang)
    labels = _YT_LABELS[lang]
    kw = brief.primary_keyword
    title_default = choose_hook(brief, hook, max_chars=TITLE_MAX_CHARS, prefer=kw)
    slots: list[Slot] = [Slot("title", f"Video title (max {TITLE_MAX_CHARS} chars) with the keyword near the start and an honest promise.",
                              max_chars=TITLE_MAX_CHARS, kind="title", default=title_default)]
    blocks: list[str] = []
    chapters: list[dict] = [{"id": "intro", "start": 0, "timestamp": "0:00", "title": labels["intro"]}]
    n_ch = sum(1 for b in plan if b["id"].startswith("ch"))
    for b in plan:
        bid, d = b["id"], b["end"] - b["start"]
        is_ch = bid.startswith("ch")
        vo = tx = None
        if bid == "hook":
            vo = fit(title_default, max_words=b["max_words"])
            tx = fit(vo, max_words=ON_SCREEN_MAX_WORDS)
        elif bid == "cta":
            vo = fit(brief.cta, max_words=b["max_words"])
            tx = fit(brief.cta, max_words=ON_SCREEN_MAX_WORDS)
        slots.append(Slot(f"vo_{bid}", _yt_vo_instruction(b, brief), max_words=b["max_words"] - (YT_LOOP_WORDS if is_ch else 0),
                          kind="text", default=vo))
        head = f"### {fmt_time(b['start'])}-{fmt_time(b['end'])} {b['label']}"
        body = "- **Voiceover:** " + "{{vo_%s}}\n" % bid
        if is_ch:
            num = int(bid[2:])
            nxt = "the next chapter" if num < n_ch else "the recap and next step"
            slots.append(Slot(f"title_{bid}", f"Chapter {num} title for the chapter list (max {YT_CHAPTER_TITLE_CHARS} chars, keyword if natural).",
                              max_chars=YT_CHAPTER_TITLE_CHARS, kind="title"))
            slots.append(Slot(f"loop_{bid}", f"Closing line that opens a loop into {nxt}: a question or teaser the next part answers (max {YT_LOOP_WORDS} words).",
                              max_words=YT_LOOP_WORDS, kind="line"))
            head += ": " + "{{title_%s}}" % bid
            body += pick(lang, "- **Open loop:** ", "- **Otevřená smyčka:** ") + "{{loop_%s}}\n" % bid
            chapters.append({"id": bid, "start": b["start"], "timestamp": fmt_time(b["start"]), "title": None})
        elif bid == "recap":
            chapters.append({"id": bid, "start": b["start"], "timestamp": fmt_time(b["start"]), "title": labels["recap"]})
        elif bid == "cta":
            chapters.append({"id": bid, "start": b["start"], "timestamp": fmt_time(b["start"]), "title": labels["wrap"]})
        slots.append(Slot(f"text_{bid}", f"On-screen text or chapter card, at most {ON_SCREEN_MAX_WORDS} words.",
                          max_words=ON_SCREEN_MAX_WORDS, kind="line", default=tx))
        slots.append(Slot(f"visual_{bid}", f"Shots, b-roll or screen capture for this part; change the visual about every {YT_CUT_EVERY_S} s.",
                          kind="text"))
        body += pick(lang, "- **On-screen text:** ", "- **Text na obrazovce:** ") + "{{text_%s}}\n" % bid
        body += pick(lang, "- **Visual:** ", "- **Obraz:** ") + "{{visual_%s}}" % bid
        blocks.append(head + "\n\n" + body)
    slots.append(Slot("description", f"Video description (max {YT_DESCRIPTION_CHARS} chars): the first 150 characters carry the keyword "
                                     "and the promise, then context. No keyword stuffing, no invented claims.",
                      max_chars=YT_DESCRIPTION_CHARS, kind="text", must_include=[kw]))
    if brief.sponsored:
        slots.append(Slot("disclosure", "Paid promotion disclosure for the description (and tick the paid promotion setting).",
                          max_chars=80, kind="line", default=DISCLOSURE_TAG[lang]))
    chapter_lines = []
    for c in chapters:
        title = c["title"] if c["title"] else "{{title_%s}}" % c["id"]
        chapter_lines.append(f"{c['timestamp']} {title}")
    desc_block = ("## " + pick(lang, "Description", "Popis") + "\n\n" + ("{{disclosure}}\n\n" if brief.sponsored else "")
                  + "{{description}}\n\n" + pick(lang, "Chapters:", "Kapitoly:") + "\n" + "\n".join(chapter_lines))
    template = "\n\n".join([f"# {pick(lang, 'YouTube script', 'Scénář pro YouTube')}: " + "{{title}}"] + blocks + [desc_block])

    def extra(beats: list[dict], values: dict[str, str]) -> dict[str, Any]:
        out = []
        for c in chapters:
            title = c["title"] or values[f"title_{c['id']}"]
            out.append({"id": c["id"], "start": c["start"], "timestamp": c["timestamp"], "title": title})
        return {"chapters": out, "chapters_text": "\n".join(f"{c['timestamp']} {c['title']}" for c in out)}

    return Skeleton(
        format="youtube_script", lang=lang, template=template, slots=slots,
        fixed={"minutes": minutes, "plan": plan, "speech_rate": speech_rate(lang), "chapter_count": n_ch,
               "chapter_times": [{k: c[k] for k in ("id", "start", "timestamp")} for c in chapters],
               "hook_max_s": YT_HOOK_S},
        meta=brief_meta(brief, duration_s=minutes * 60, style="youtube", hook_max_s=YT_HOOK_S, short=False),
        hook_slot="vo_hook", assemble=_assemble_beats(plan, lang, extra),
        notes=standard_notes(brief, f"Budget: {speech_rate(lang)} words per second. Every chapter ends with an open loop into the next part."),
    )


_TS_RE = re.compile(r"^\d{1,2}:\d{2}$")


def validate_youtube_script(draft: Draft) -> list[Issue]:
    issues = check_beats(draft)
    chapters = draft.parts.get("chapters") or []
    if len(chapters) < 3:
        issues.append(Issue("error", "CHAPTERS", "YouTube needs at least three chapters."))
    if chapters and chapters[0]["start"] != 0:
        issues.append(Issue("error", "CHAPTERS", "The first chapter must start at 0:00."))
    for a, b in zip(chapters, chapters[1:]):
        if b["start"] <= a["start"]:
            issues.append(Issue("error", "CHAPTERS", "Chapter timestamps must increase.", b["id"]))
        elif b["start"] - a["start"] < 10:
            issues.append(Issue("error", "CHAPTERS", "Chapters must be at least 10 seconds long.", a["id"]))
    for c in chapters:
        if not _TS_RE.match(c["timestamp"]):
            issues.append(Issue("error", "CHAPTERS", f"Bad timestamp {c['timestamp']!r}.", c["id"]))
        t = strip_placeholders(c["title"]).strip()
        if len(t) > YT_CHAPTER_TITLE_CHARS:
            issues.append(Issue("warn", "CHAPTER_TITLE_LONG", f"Chapter title is {len(t)} characters, keep it under {YT_CHAPTER_TITLE_CHARS}.", c["id"]))
    title = slot_text(draft, "title")
    if len(title) > 100:
        issues.append(Issue("error", "CHAR_LIMIT", f"Title is {len(title)} characters, YouTube allows 100.", "title"))
    elif len(title) > TITLE_MAX_CHARS:
        issues.append(Issue("warn", "TITLE_LONG", f"Title is {len(title)} characters; search results cut it near {TITLE_MAX_CHARS}.", "title"))
    desc = slot_text(draft, "description")
    kw = draft.meta.get("primary_keyword")
    if len(desc) > YT_DESCRIPTION_CHARS:
        issues.append(Issue("error", "CHAR_LIMIT", f"Description is {len(desc)} characters, the limit is {YT_DESCRIPTION_CHARS}.", "description"))
    if desc and kw and not keyword_in(desc, kw, draft.lang):
        issues.append(Issue("warn", "KEYWORD_MISSING", f"The description does not contain the keyword '{kw}'."))
    return issues


# -- YouTube title set -----------------------------------------------------------------------------
YT_TITLES = 10
YT_THUMBS = 4
_THUMB_EN = ("{n} mistakes", "Stop doing this", "The truth", "Start here", "Read this first", "Avoid this",
             "Do this instead", "Before you start", "Quick guide", "Myth or fact?", "Is it worth it?")
_THUMB_CS = ("{n} chyb", "Přestaňte s tím", "Celá pravda", "Začněte tady", "Přečtěte si to", "Tomu se vyhněte",
             "Dělejte to jinak", "Než začnete", "Rychlý návod", "Mýtus, nebo fakt?", "Vyplatí se to?")


def thumbnail_texts(brief: Brief, n: int = YT_THUMBS) -> list[tuple[str, float]]:
    """Neutral thumbnail phrases of at most four words, ranked by Dopamine Score (best first)."""
    lang = lang_of(brief)
    scored = []
    for i, tpl in enumerate(_THUMB_CS if lang == "cs" else _THUMB_EN):
        text = tpl.format(n=7)
        total, risk = cached_score(text, lang)
        if len(text.split()) <= THUMB_MAX_WORDS and risk <= 0.35:
            scored.append((-total, i, text, total))
    scored.sort()
    return [(t, round(total, 2)) for _, _, t, total in scored[:n]]


def build_youtube_title_set(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Ten title options (at most 70 characters) ranked by Dopamine Score, four thumbnail texts, a concept slot.

    A supplied ``hook`` is pinned to title_01 (the hook slot); the other nine stay ranked by score.
    """
    lang = lang_of(brief)
    cands = generate_hooks(brief, n=YT_TITLES, max_chars=TITLE_MAX_CHARS)
    rows = [{"text": c.text, "style": c.style, "score": c.score, "risk": c.clickbait_risk} for c in cands]
    if hook and hook.strip():      # a supplied hook is pinned to the first slot, the rest stay ranked
        total, risk = cached_score(hook.strip(), lang)
        rows = ([{"text": hook.strip(), "style": "provided", "score": round(total, 2), "risk": round(risk, 4)}]
                + [r for r in rows if r["text"] != hook.strip()])[:YT_TITLES]
    thumbs = thumbnail_texts(brief)
    slots: list[Slot] = []
    for i in range(1, YT_TITLES + 1):
        row = rows[i - 1] if i <= len(rows) else None
        slots.append(Slot(f"title_{i:02d}", f"Title option {i}, at most {TITLE_MAX_CHARS} characters, keyword early, honest promise.",
                          max_chars=TITLE_MAX_CHARS, kind="title", default=row["text"] if row else None))
    for i in range(1, YT_THUMBS + 1):
        slots.append(Slot(f"thumb_{i}", f"Thumbnail text option {i}, at most {THUMB_MAX_WORDS} words, adds to the title instead of repeating it.",
                          max_words=THUMB_MAX_WORDS, kind="line", default=thumbs[i - 1][0] if i <= len(thumbs) else None))
    slots.append(Slot("thumbnail_concept", "Thumbnail concept: one clear focal subject, high contrast, at most four words of text, "
                                           "and a promise that matches the title.", kind="text"))
    head = pick(lang, ("YouTube titles", "Titles (ranked by Dopamine Score)", "Thumbnail text (at most 4 words)", "Thumbnail concept"),
                ("Názvy videí na YouTube", "Názvy (seřazené podle Dopamine Score)", "Text na náhledu (nejvýše 4 slova)", "Koncept náhledu"))
    parts = [f"# {head[0]}: {brief.topic}", f"## {head[1]}\n\n" + "\n".join(f"{i}. " + "{{title_%02d}}" % i for i in range(1, YT_TITLES + 1)),
             f"## {head[2]}\n\n" + "\n".join(f"{i}. " + "{{thumb_%d}}" % i for i in range(1, YT_THUMBS + 1)),
             f"## {head[3]}\n\n" + "{{thumbnail_concept}}"]
    return Skeleton(
        format="youtube_title_set", lang=lang, template="\n\n".join(parts), slots=slots,
        fixed={"titles": rows, "thumbnail_texts": [{"text": t, "score": sc} for t, sc in thumbs], "hook": rows[0]["text"] if rows else ""},
        meta=brief_meta(brief), hook_slot="title_01",
        notes=standard_notes(brief, "Titles are ranked by the Dopamine Score; test two or three, and make sure the video delivers the promise."),
    )


def validate_youtube_title_set(draft: Draft) -> list[Issue]:
    issues: list[Issue] = []
    titles = [(k, slot_text(draft, k)) for k in sorted(draft.parts.get("slots", {})) if k.startswith("title_")]
    seen: set[str] = set()
    for k, t in titles:
        if len(t) > TITLE_MAX_CHARS:
            issues.append(Issue("error", "CHAR_LIMIT", f"{len(t)} characters, the limit is {TITLE_MAX_CHARS}.", k))
        if t and t.lower() in seen:
            issues.append(Issue("warn", "TITLE_DUPLICATE", "Duplicate title option.", k))
        seen.add(t.lower())
        if t and cached_score(t, draft.lang if draft.lang in ("en", "cs") else "en")[1] > 0.35:
            issues.append(Issue("warn", "CLICKBAIT_RISK", "This title reads as clickbait.", k))
    for k in sorted(draft.parts.get("slots", {})):
        if k.startswith("thumb_") and word_count(slot_text(draft, k)) > THUMB_MAX_WORDS:
            issues.append(Issue("error", "THUMB_TEXT_LONG", f"Thumbnail text is longer than {THUMB_MAX_WORDS} words.", k))
    if sum(1 for _, t in titles if t) < YT_TITLES and "title_" not in "".join(draft.slots_open):
        issues.append(Issue("warn", "TITLE_COUNT", f"Fewer than {YT_TITLES} title options."))
    return issues


# -- podcast outline -----------------------------------------------------------------------------------
POD_COLD_S = 60
POD_INTRO_S = 120
POD_OUTRO_S = 120
POD_QUESTIONS = 5
POD_SEGMENTS = (3, 4)
POD_MINUTES = (15, 90)
POD_SHOW_NOTES_CHARS = 1500


def plan_podcast(minutes: int, segments: int) -> list[dict]:
    total = max(POD_MINUTES[0], min(POD_MINUTES[1], int(minutes))) * 60
    k = max(POD_SEGMENTS[0], min(POD_SEGMENTS[1], int(segments)))
    seg = split_seconds(total - POD_COLD_S - POD_INTRO_S - POD_OUTRO_S, [1.0] * k, minimum=60)
    order = [("cold_open", POD_COLD_S), ("intro", POD_INTRO_S)] + [(f"seg{i}", d) for i, d in enumerate(seg, 1)] + [("outro", POD_OUTRO_S)]
    out, t = [], 0
    for bid, d in order:
        out.append({"id": bid, "start": t, "end": t + d, "timestamp": fmt_time(t)})
        t += d
    return out


def build_podcast_outline(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    """Podcast outline. options: minutes 15..90 (default 30), segments 3 or 4 (default 3)."""
    opts = options or {}
    try:
        minutes, segs = int(opts.get("minutes", 30)), int(opts.get("segments", 3))
    except (TypeError, ValueError):
        minutes, segs = 30, 3
    minutes = max(POD_MINUTES[0], min(POD_MINUTES[1], minutes))
    segs = max(POD_SEGMENTS[0], min(POD_SEGMENTS[1], segs))
    lang = lang_of(brief)
    plan = plan_podcast(minutes, segs)
    rate = speech_rate(lang)
    kw = brief.primary_keyword
    cold_words = int((POD_COLD_S) * rate)
    slots: list[Slot] = [
        Slot("vo_hook", f"Cold open (max {cold_words} words): a teaser of the most interesting moment or question of the episode.",
             max_words=cold_words, kind="text", default=choose_hook(brief, hook, max_words=cold_words)),
        Slot("vo_intro", f"Intro (max {int(POD_INTRO_S * rate)} words): who the guest or topic is and why {brief.audience} should listen.",
             max_words=int(POD_INTRO_S * rate), kind="text"),
    ]
    title_h, q_h, notes_h = pick(lang, ("Podcast outline", "Questions", "Show notes"), ("Osnova podcastu", "Otázky", "Poznámky k epizodě"))
    seg_label = pick(lang, "Segment", "Část")
    blocks = [f"# {title_h}: {brief.topic}"]
    for b in plan:
        bid = b["id"]
        head = f"## {b['timestamp']}-{fmt_time(b['end'])} "
        if bid == "cold_open":
            blocks.append(head + pick(lang, "Cold open", "Úvodní hook") + "\n\n{{vo_hook}}")
        elif bid == "intro":
            blocks.append(head + pick(lang, "Intro", "Úvod") + "\n\n{{vo_intro}}")
        elif bid == "outro":
            blocks.append(head + pick(lang, "Outro and call to action", "Závěr a výzva k akci") + "\n\n{{cta}}")
        else:
            n = bid[3:]
            slots.append(Slot(f"seg_{n}_title", "Segment title, at most 60 characters.", max_chars=60, kind="title"))
            slots.append(Slot(f"seg_{n}_points", "Two to four talking points as '- ' bullets. Only content you can back up.",
                              max_chars=600, kind="list"))
            blocks.append(head + f"{seg_label} {n}: " + "{{seg_%s_title}}\n\n{{seg_%s_points}}" % (n, n))
    slots.append(Slot("cta", "Closing call to action (max 150 chars).", max_chars=150, kind="line", default=fit(brief.cta, max_chars=150)))
    for i in range(1, POD_QUESTIONS + 1):
        slots.append(Slot(f"q_{i}", f"Open-ended interview or discussion question {i}, at most 25 words, ending with a question mark.",
                          max_words=25, kind="line"))
    slots.append(Slot("show_notes", f"Show notes (max {POD_SHOW_NOTES_CHARS} chars): a short summary with the keyword and a list of "
                                    "topics. Leave link and guest details to the human.", max_chars=POD_SHOW_NOTES_CHARS,
                      kind="text", must_include=[kw]))
    if brief.sponsored:
        slots.append(Slot("disclosure", "Spoken and written sponsorship disclosure.", max_chars=100, kind="line",
                          default=pick(lang, f"Sponsored by {brief.brand}.", f"Sponzorováno značkou {brief.brand}.")))
    blocks.append(f"## {q_h}\n\n" + "\n".join(f"{i}. " + "{{q_%d}}" % i for i in range(1, POD_QUESTIONS + 1)))
    blocks.append(f"## {notes_h}\n\n" + ("{{disclosure}}\n\n" if brief.sponsored else "") + "{{show_notes}}")

    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        segments = [{"id": b["id"], "start": b["start"], "end": b["end"], "timestamp": b["timestamp"],
                     "title": values[f"seg_{b['id'][3:]}_title"], "points": values[f"seg_{b['id'][3:]}_points"]}
                    for b in plan if b["id"].startswith("seg")]
        return {"segments": segments, "questions": [values[f"q_{i}"] for i in range(1, POD_QUESTIONS + 1)]}

    return Skeleton(
        format="podcast_outline", lang=lang, template="\n\n".join(blocks), slots=slots,
        fixed={"minutes": minutes, "plan": plan, "segment_count": segs, "speech_rate": rate},
        meta=brief_meta(brief, duration_s=minutes * 60), hook_slot="vo_hook", assemble=assemble,
        notes=standard_notes(brief, "Timings are a plan: adjust to the guest. Questions must be open-ended, not yes or no."),
    )


def validate_podcast_outline(draft: Draft) -> list[Issue]:
    issues: list[Issue] = []
    segs = draft.parts.get("segments") or []
    lo, hi = POD_SEGMENTS
    if not lo <= len(segs) <= hi:
        issues.append(Issue("error", "SEGMENT_COUNT", f"{len(segs)} segments, use {lo} or {hi}."))
    plan = draft.parts.get("plan") or []
    t = 0
    for b in plan:
        if b["start"] != t or b["end"] <= b["start"]:
            issues.append(Issue("error", "TIMELINE_BROKEN", f"Segment {b['id']} does not follow the previous one.", b["id"]))
        t = b["end"]
    total = draft.meta.get("duration_s")
    if plan and total and t != total:
        issues.append(Issue("error", "DURATION_MISMATCH", f"Timings add up to {t} s, expected {total} s."))
    questions = [strip_placeholders(q).strip() for q in draft.parts.get("questions") or []]
    filled = [q for q in questions if q]
    if len(questions) != POD_QUESTIONS:
        issues.append(Issue("warn", "QUESTION_COUNT", f"{len(questions)} questions, plan {POD_QUESTIONS}."))
    for i, q in enumerate(questions, 1):
        if q and not q.endswith("?"):
            issues.append(Issue("warn", "QUESTION_FORM", "A question should end with a question mark.", f"q_{i}"))
        if q and word_count(q) > 25:
            issues.append(Issue("warn", "QUESTION_LONG", "Keep questions to 25 words.", f"q_{i}"))
    if len(set(q.lower() for q in filled)) != len(filled):
        issues.append(Issue("warn", "QUESTION_DUPLICATE", "Duplicate questions."))
    notes = slot_text(draft, "show_notes")
    kw = draft.meta.get("primary_keyword")
    if len(notes) > POD_SHOW_NOTES_CHARS:
        issues.append(Issue("error", "CHAR_LIMIT", f"Show notes are {len(notes)} characters, the limit is {POD_SHOW_NOTES_CHARS}.", "show_notes"))
    if notes and kw and not keyword_in(notes, kw, draft.lang):
        issues.append(Issue("warn", "KEYWORD_MISSING", f"The show notes do not contain the keyword '{kw}'."))
    hook_words = word_count(slot_text(draft, "vo_hook"))
    budget = int(POD_COLD_S * speech_rate(draft.lang))
    if hook_words > budget * WORDS_ERROR:
        issues.append(Issue("error", "WORDS_OVER_BUDGET", f"{hook_words} words, the cold open fits {budget} (over 140 percent).", "vo_hook"))
    elif hook_words > budget * WORDS_WARN:
        issues.append(Issue("warn", "WORDS_OVER_BUDGET", f"{hook_words} words, the cold open fits {budget} (over 110 percent).", "vo_hook"))
    if draft.meta.get("sponsored"):
        text = " ".join(slot_text(draft, k) for k in ("vo_intro", "show_notes", "disclosure", "cta"))
        if not has_disclosure(text):
            issues.append(Issue("error", "DISCLOSURE_MISSING", "A sponsored episode needs a spoken and written disclosure."))
    if draft.slots_open:
        issues.append(Issue("info", "SLOTS_OPEN", f"{len(draft.slots_open)} slot(s) are still open (a human records the episode)."))
    return issues


# -- registry --------------------------------------------------------------------------------------------
FORMAT_SPECS: list[FormatSpec] = [
    FormatSpec(
        id="short_video_script", name_en="Short video script", name_cs="Scénář krátkého videa", family="video", platform="tiktok",
        build=build_short_video_script, validate=validate_short_video_script,
        limits={"durations": list(SHORT_DURATIONS), "styles": list(SHORT_STYLES), "hook_max_s": HOOK_MAX_S,
                "cut_every_s": CUT_EVERY_S, "on_screen_max_words": ON_SCREEN_MAX_WORDS, "speech_rate": SPEECH_RATE},
        description_en="Beat by beat script with timings, word budgets, on-screen text, visuals and SRT captions.",
        description_cs="Scénář po částech s časováním, limity slov, texty na obrazovce, záběry a titulky SRT."),
    FormatSpec(
        id="youtube_script", name_en="YouTube script", name_cs="Scénář pro YouTube", family="video", platform="youtube",
        build=build_youtube_script, validate=validate_youtube_script,
        limits={"minutes": list(YT_MINUTES), "hook_window_s": YT_HOOK_S, "title_chars": TITLE_MAX_CHARS,
                "chapter_title_chars": YT_CHAPTER_TITLE_CHARS, "description_chars": YT_DESCRIPTION_CHARS},
        description_en="Cold open with payoff preview, credibility line, 3 to 5 chapters with open loops, recap, CTA and chapter timestamps.",
        description_cs="Úvodní hook s příslibem přínosu, řádek důvěryhodnosti, 3 až 5 kapitol s otevřenými smyčkami, shrnutí, výzva a časové značky."),
    FormatSpec(
        id="ugc_ad_script", name_en="UGC ad script", name_cs="Scénář UGC reklamy", family="video", platform="tiktok",
        build=build_ugc_ad_script, validate=validate_ugc_ad_script,
        limits={"durations": [30, 45, 60], "hook_max_s": HOOK_MAX_S, "cut_every_s": CUT_EVERY_S},
        description_en="Problem, agitate, solution ad in a user generated style with a real proof beat and a disclosure beat when sponsored.",
        description_cs="Reklama ve stylu uživatelského obsahu: problém, vyostření, řešení, skutečný důkaz a označení spolupráce u placeného obsahu."),
    FormatSpec(
        id="youtube_title_set", name_en="YouTube title set", name_cs="Sada názvů pro YouTube", family="video", platform="youtube",
        build=build_youtube_title_set, validate=validate_youtube_title_set,
        limits={"titles": YT_TITLES, "title_chars": TITLE_MAX_CHARS, "thumbnail_texts": YT_THUMBS, "thumbnail_words": THUMB_MAX_WORDS},
        description_en="Ten ranked title options, four thumbnail texts and a thumbnail concept.",
        description_cs="Deset seřazených názvů, čtyři texty na náhled a koncept náhledu."),
    FormatSpec(
        id="podcast_outline", name_en="Podcast outline", name_cs="Osnova podcastu", family="audio", platform="podcast",
        build=build_podcast_outline, validate=validate_podcast_outline,
        limits={"minutes": list(POD_MINUTES), "segments": list(POD_SEGMENTS), "questions": POD_QUESTIONS,
                "show_notes_chars": POD_SHOW_NOTES_CHARS},
        description_en="Cold open, three or four timed segments, five questions and show notes.",
        description_cs="Úvodní hook, tři nebo čtyři časované části, pět otázek a poznámky k epizodě."),
]
