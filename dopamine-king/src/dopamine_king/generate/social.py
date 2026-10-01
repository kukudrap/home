"""Social post builders and validators (LinkedIn, X, Instagram, Facebook, Threads, Pinterest, YouTube
community, Reddit, Google Business Profile).

Builders return a ``Skeleton``: structure plus slots. Slot defaults only restate the brief (hook from the
hook library, CTA, hashtags derived from topic and audience, one fact) and never invent prose. Validators
only see the rendered ``Draft`` and measure real content: ``[[ADD: ...]]`` placeholders are ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from ..scoring import fold
from .formats import (
    DISCLOSURE_TAG, brief_meta, caps_ratio, caps_words, emoji_count, engagement_bait, fit, has_cta,
    has_disclosure, hashtags_in, keyword_in, lang_of, pick, slot_text, standard_notes, strip_placeholders,
    topic_hashtags, urls_in, word_count,
)
from .hooks import choose_hook
from .types import Brief, Draft, FormatSpec, Issue, Skeleton, Slot

# Platform limits checked 2026-10, verify before publishing.
LINKEDIN_POST_CHARS = 3000
LINKEDIN_HOOK_WINDOW = 140          # characters shown before "see more"
LINKEDIN_HASHTAGS = (0, 3)
LINKEDIN_SLIDES = (8, 12)
SLIDE_TITLE_WORDS = 8
LINKEDIN_SLIDE_BODY_WORDS = 30
X_POST_CHARS = 280
X_THREAD_POSTS = (5, 10)
X_THREAD_POST_CHARS = 270
X_URL_WEIGHT = 23                   # X counts every link as 23 characters
INSTAGRAM_CAPTION_CHARS = 2200
INSTAGRAM_HOOK_WINDOW = 125
INSTAGRAM_HASHTAGS = (3, 5)
INSTAGRAM_MAX_SLIDES = 10
INSTAGRAM_SLIDE_WORDS = 25
FACEBOOK_AIM_WORDS = 80
THREADS_POST_CHARS = 500
THREADS_MAX_TAGS = 1
PINTEREST_TITLE_CHARS = 100
PINTEREST_DESCRIPTION_CHARS = 500
PINTEREST_ALT_CHARS = 500
PINTEREST_ALT_AIM = 125
YOUTUBE_COMMUNITY_CHARS = 1000
YOUTUBE_POLL_OPTIONS = (2, 4)
YOUTUBE_POLL_OPTION_CHARS = 65
REDDIT_COMMENT_CHARS = 10000
REDDIT_LINK_WINDOW = 300
GBP_POST_CHARS = 1500
GBP_AIM_CHARS = (150, 300)
GBP_CTA_BUTTONS = {          # label -> Business Profile API enum
    "Book": "BOOK", "Order online": "ORDER", "Buy": "SHOP", "Learn more": "LEARN_MORE",
    "Sign up": "SIGN_UP", "Call now": "CALL",
}
FIRST_LINE_EMOJI_MAX = 3
CAPS_RATIO_WARN = 0.12


# -- builder helpers -------------------------------------------------------------------
def _hook_slot(brief: Brief, hook: str | None, *, max_chars: int, max_words: int | None = None,
               prefer: str | None = None, slot_id: str = "hook", what: str = "Opening line") -> Slot:
    text = choose_hook(brief, hook, max_chars=max_chars, max_words=max_words, prefer=prefer)
    limit = f"max {max_chars} chars" + (f", max {max_words} words" if max_words else "")
    return Slot(
        slot_id,
        f"{what} ({limit}). Promise one specific payoff for {brief.audience}; no clickbait, no unproven claims.",
        max_chars=max_chars, max_words=max_words, kind="line", default=text,
    )


def _cta_slot(brief: Brief, *, max_chars: int, max_words: int | None = None, slot_id: str = "cta",
              instruction: str | None = None) -> Slot:
    default = fit(brief.cta, max_chars=max_chars, max_words=max_words)
    return Slot(
        slot_id, instruction or f"Call to action (max {max_chars} chars): one clear next step for the reader.",
        max_chars=max_chars, max_words=max_words, kind="line", default=default,
    )


def _hashtag_slot(brief: Brief, lo: int, hi: int, *, slot_id: str = "hashtags", default_count: int | None = None) -> Slot:
    tags = topic_hashtags(brief, default_count if default_count is not None else hi)
    return Slot(
        slot_id, f"{lo} to {hi} relevant hashtags on one line, space separated. No spammy or banned tags.",
        max_chars=150, kind="line", default=" ".join(tags) or None,
    )


def _disclosure_slot(brief: Brief, max_chars: int = 40) -> Slot | None:
    """Disclosure line for sponsored briefs. Tight formats pass a small limit so the worst case still fits."""
    if not brief.sponsored:
        return None
    return Slot(
        "disclosure", "Paid partnership disclosure, clearly visible (for example #ad).",
        max_chars=max_chars, kind="line", default=DISCLOSURE_TAG[lang_of(brief)],
    )


def _skeleton(fmt: str, brief: Brief, parts: list[str], slots: list[Slot | None], *, hook_slot: str = "hook",
              fixed: dict[str, Any] | None = None, assemble: Callable | None = None,
              notes: tuple[str, ...] = (), meta: dict[str, Any] | None = None, sep: str = "\n\n") -> Skeleton:
    real = [s for s in slots if s is not None]
    return Skeleton(
        format=fmt, lang=lang_of(brief), template=sep.join(p for p in parts if p), slots=real,
        fixed=fixed or {}, meta=brief_meta(brief, **(meta or {})), hook_slot=hook_slot,
        notes=standard_notes(brief, *notes), assemble=assemble,
    )


def _opt_int(options: dict | None, key: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int((options or {}).get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value))


# -- validator core --------------------------------------------------------------------
@dataclass(frozen=True)
class Rule:
    """Limits and expectations of one text format."""
    max_chars: int | None = None
    counter: Callable[[str], int] = len
    hook_window: int | None = None
    hashtags: tuple[int, int] | None = None      # (min, max)
    cta: str = "if_given"                        # "required" | "if_given" | "off"
    aim_words: int | None = None
    check_hook: bool = True                      # False when the checked text does not contain the hook


def x_length(text: str) -> int:
    """X weighted length: every link counts 23, every emoji 2 (approximation, verify before publishing)."""
    t = re.sub(r"(?:https?://|www\.)\S+", "x" * X_URL_WEIGHT, text)
    return len(t) + emoji_count(t)


def first_line(text: str) -> str:
    for line in strip_placeholders(text).splitlines():
        if line.strip():
            return line.strip()
    return ""


def compose(draft: Draft, slot_ids: list[str]) -> str:
    """Text assembled from filled slots only (placeholders removed), paragraphs separated by blank lines."""
    return "\n\n".join(t for t in (slot_text(draft, i) for i in slot_ids) if t)


def _last_paragraph(text: str) -> str:
    for para in reversed([p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]):
        rest = para
        for tag in hashtags_in(para):
            rest = rest.replace(tag, "")
        if rest.strip() and not (has_disclosure(para) and len(rest.split()) <= 6):
            return rest.strip()
    return ""


def disclosure_issue(draft: Draft, text: str) -> list[Issue]:
    if draft.meta.get("sponsored") and not has_disclosure(text):
        return [Issue("error", "DISCLOSURE_MISSING",
                      "Sponsored content needs a visible disclosure (#ad, paid partnership; Czech: #reklama, spolupráce).")]
    return []


def check_social(draft: Draft, rule: Rule, text: str | None = None) -> list[Issue]:
    """Shared social checks on ``text`` (default: the whole body) with placeholders ignored."""
    clean = strip_placeholders(draft.body if text is None else text)
    issues: list[Issue] = []
    length = rule.counter(clean.strip())
    if rule.max_chars is not None and length > rule.max_chars:
        issues.append(Issue("error", "CHAR_LIMIT", f"{length} characters, the limit is {rule.max_chars}."))
    hook = strip_placeholders(draft.hook).strip() if rule.check_hook else ""
    if not rule.check_hook:
        pass
    elif hook:
        if rule.hook_window and len(hook) > rule.hook_window:
            issues.append(Issue("warn", "HOOK_TRUNCATED",
                                f"The hook is {len(hook)} characters; the feed shows about {rule.hook_window} before truncating."))
        if clean.find(hook) < 0 or clean.find(hook) > 40:
            issues.append(Issue("warn", "HOOK_MISSING", "The hook is not at the start of the post."))
    elif "hook" not in draft.slots_open and not draft.hook.strip():
        issues.append(Issue("warn", "HOOK_MISSING", "The post has no hook."))
    if rule.hashtags is not None:
        lo, hi = rule.hashtags
        n = len(hashtags_in(clean))
        if n > hi:
            issues.append(Issue("warn", "HASHTAG_COUNT", f"{n} hashtags, use at most {hi}."))
        elif n < lo and "hashtags" not in draft.slots_open:
            issues.append(Issue("warn", "HASHTAG_COUNT", f"{n} hashtags, use at least {lo}."))
    if emoji_count(first_line(clean)) > FIRST_LINE_EMOJI_MAX:
        issues.append(Issue("warn", "EMOJI_OVERUSE", f"More than {FIRST_LINE_EMOJI_MAX} emojis in the first line."))
    if len(caps_words(clean)) >= 2 and caps_ratio(clean) > CAPS_RATIO_WARN:
        issues.append(Issue("warn", "ALL_CAPS", "Many words are written in capitals: " + ", ".join(caps_words(clean)[:5])))
    bait = engagement_bait(clean)
    if bait:
        issues.append(Issue("warn", "ENGAGEMENT_BAIT", "Engagement bait phrasing: " + "; ".join(bait)))
    issues += disclosure_issue(draft, clean)
    if rule.aim_words is not None and word_count(clean) > rule.aim_words:
        issues.append(Issue("warn", "LENGTH_AIM", f"{word_count(clean)} words, aim for {rule.aim_words} or fewer."))
    if rule.cta != "off" and not ({"cta", "closing"} & set(draft.slots_open)) and clean.strip():
        cta = draft.meta.get("cta")
        if (rule.cta == "required" or cta) and not (has_cta(clean, cta) or _last_paragraph(clean).endswith("?")):
            issues.append(Issue("warn", "CTA_MISSING", "No clear call to action or closing question."))
    return issues


# -- LinkedIn post ---------------------------------------------------------------------
def build_linkedin_post(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    proof = fit(brief.facts[0], max_chars=300) if brief.facts else None
    slots = [
        _hook_slot(brief, hook, max_chars=LINKEDIN_HOOK_WINDOW, what="Opening line, the feed truncates after about 140 chars"),
        Slot("context", f"Two or three short lines on the situation or problem {brief.audience} recognise. One idea only.",
             max_chars=300, max_words=50),
        Slot("insight", "The main idea in short paragraphs of one or two sentences each. Concrete detail beats adjectives.",
             max_chars=800),
        Slot("proof", "One concrete fact or number that backs the idea. Use only facts from the brief.",
             max_chars=300, kind="line", default=proof),
        Slot("points", "Three to five bullet lines starting with '- ', at most 20 words each, with practical takeaways.",
             max_chars=700, kind="list"),
        Slot("closing", "Close with one specific question or call to action.", max_chars=200, kind="line",
             default=fit(brief.cta, max_chars=200)),
        _disclosure_slot(brief),
        _hashtag_slot(brief, *LINKEDIN_HASHTAGS, default_count=2),
    ]
    parts = ["{{hook}}", "{{context}}", "{{insight}}", "{{proof}}", "{{points}}", "{{closing}}",
             "{{disclosure}}" if brief.sponsored else "", "{{hashtags}}"]
    return _skeleton("linkedin_post", brief, parts, slots, notes=(
        "Short paragraphs of one or two lines. The first 140 characters must carry the hook.",
        "Zero to three hashtags at the end, nothing that asks for likes or tags.",
    ))


def validate_linkedin_post(draft: Draft) -> list[Issue]:
    issues = check_social(draft, Rule(max_chars=LINKEDIN_POST_CHARS, hook_window=LINKEDIN_HOOK_WINDOW,
                                      hashtags=LINKEDIN_HASHTAGS, cta="required"))
    for i, para in enumerate(re.split(r"\n\s*\n", strip_placeholders(draft.body)), 1):
        if len(para.strip()) > 400:
            issues.append(Issue("info", "PARAGRAPH_LONG", "Paragraph is longer than 400 characters; keep paragraphs short.", f"paragraph {i}"))
    return issues


# -- X post and thread -----------------------------------------------------------------
def build_x_post(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    slots = [
        _hook_slot(brief, hook, max_chars=100, what="First line"),
        Slot("point", "One sentence that delivers on the hook. Concrete, no filler.", max_chars=115, kind="line"),
        _cta_slot(brief, max_chars=40),
        Slot("disclosure", "Paid partnership disclosure (for example #ad).", max_chars=12, kind="line",
             default=DISCLOSURE_TAG[lang_of(brief)]) if brief.sponsored else None,
    ]
    parts = ["{{hook}}", "{{point}}", "{{cta}}", "{{disclosure}}" if brief.sponsored else ""]
    return _skeleton("x_post", brief, parts, slots, fixed={"max_chars": X_POST_CHARS}, notes=(
        "280 characters in total (links count 23, emoji 2). At most two hashtags.",
    ))


def validate_x_post(draft: Draft) -> list[Issue]:
    return check_social(draft, Rule(max_chars=X_POST_CHARS, counter=x_length, hashtags=(0, 2), cta="if_given"))


def build_x_thread(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    n = _opt_int(options, "posts", 7, X_THREAD_POSTS[0], X_THREAD_POSTS[1])
    slots: list[Slot | None] = [_hook_slot(brief, hook, max_chars=240, what="Post 1, the hook that promises the payoff of the thread")]
    for k in range(2, n):
        what = ("Set up the problem or context in plain words." if k == 2
                else f"Point {k - 2}: one practical idea or step, concrete and understandable on its own.")
        slots.append(Slot(f"post_{k:02d}", f"Post {k} of {n}. {what} One idea per post, max 260 chars.",
                          max_chars=260, kind="text"))
    slots.append(Slot("recap", "Recap the thread in one or two sentences (max 180 chars).", max_chars=180, kind="text"))
    slots.append(_cta_slot(brief, max_chars=70))
    slots.append(Slot("disclosure", "Paid partnership disclosure (for example #ad).", max_chars=12, kind="line",
                      default=DISCLOSURE_TAG[lang_of(brief)]) if brief.sponsored else None)
    posts = ["1/" + str(n) + " {{hook}}" + (" {{disclosure}}" if brief.sponsored else "")]
    posts += [f"{k}/{n} " + "{{post_%02d}}" % k for k in range(2, n)]
    posts.append(f"{n}/{n} " + "{{recap}}\n\n{{cta}}")

    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        texts = [f"1/{n} " + values["hook"] + (" " + values["disclosure"] if "disclosure" in values else "")]
        texts += [f"{k}/{n} " + values[f"post_{k:02d}"] for k in range(2, n)]
        texts.append(f"{n}/{n} " + values["recap"] + "\n\n" + values["cta"])
        return {"posts": [{"n": i, "text": t, "chars": x_length(strip_placeholders(t))} for i, t in enumerate(texts, 1)]}

    return _skeleton("x_thread", brief, posts, slots, sep="\n\n---\n\n", assemble=assemble,
                     fixed={"posts_count": n, "post_chars": X_THREAD_POST_CHARS}, notes=(
        "Post 1 promises the payoff and the thread delivers it. The last post recaps and carries the call to action.",
    ))


def validate_x_thread(draft: Draft) -> list[Issue]:
    posts = draft.parts.get("posts") or []
    issues: list[Issue] = []
    lo, hi = X_THREAD_POSTS
    if not lo <= len(posts) <= hi:
        issues.append(Issue("error", "POST_COUNT", f"{len(posts)} posts, a thread needs {lo} to {hi}."))
    for p in posts:
        chars = x_length(strip_placeholders(p["text"]).strip())
        if chars > X_THREAD_POST_CHARS:
            issues.append(Issue("error", "CHAR_LIMIT", f"{chars} characters, the limit is {X_THREAD_POST_CHARS}.", f"post {p['n']}"))
    issues += check_social(draft, Rule(hashtags=(0, 2), cta="off"))
    if posts and "cta" not in draft.slots_open:
        last = strip_placeholders(posts[-1]["text"])
        if last.strip() and not has_cta(last, draft.meta.get("cta")):
            issues.append(Issue("warn", "CTA_MISSING", "The last post should recap and carry the call to action.", f"post {posts[-1]['n']}"))
    return issues


# -- Instagram caption ----------------------------------------------------------------
def build_instagram_caption(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    slots = [
        _disclosure_slot(brief),
        _hook_slot(brief, hook, max_chars=INSTAGRAM_HOOK_WINDOW, what="First line, the feed truncates after about 125 chars"),
        Slot("body", f"Two to four short paragraphs that deliver value to {brief.audience}. Line breaks between ideas.",
             max_chars=1500, kind="text"),
        _cta_slot(brief, max_chars=150),
        _hashtag_slot(brief, *INSTAGRAM_HASHTAGS, default_count=4),
    ]
    parts = ["{{disclosure}}" if brief.sponsored else "", "{{hook}}", "{{body}}", "{{cta}}", "{{hashtags}}"]
    return _skeleton("instagram_caption", brief, parts, slots, notes=(
        "Three to five hashtags at the end. Put the paid partnership label at the very start when sponsored.",
    ))


def validate_instagram_caption(draft: Draft) -> list[Issue]:
    return check_social(draft, Rule(max_chars=INSTAGRAM_CAPTION_CHARS, hook_window=INSTAGRAM_HOOK_WINDOW,
                                    hashtags=INSTAGRAM_HASHTAGS, cta="required"))


# -- Facebook and Threads ---------------------------------------------------------------
def build_facebook_post(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    slots = [
        _hook_slot(brief, hook, max_chars=110, max_words=15, what="First line"),
        Slot("body", "One to three short sentences. Plain language, one idea.", max_words=45, kind="text"),
        _cta_slot(brief, max_chars=140, max_words=18),
        _disclosure_slot(brief),
    ]
    parts = ["{{hook}}", "{{body}}", "{{cta}}", "{{disclosure}}" if brief.sponsored else ""]
    return _skeleton("facebook_post", brief, parts, slots, fixed={"aim_words": FACEBOOK_AIM_WORDS},
                     notes=("Short is better: aim for 80 words or fewer.",))


def validate_facebook_post(draft: Draft) -> list[Issue]:
    return check_social(draft, Rule(aim_words=FACEBOOK_AIM_WORDS, hashtags=(0, 3), cta="required"))


def build_threads_post(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    slots = [
        _hook_slot(brief, hook, max_chars=120, what="First line"),
        Slot("body", "Conversational, one idea, written like a person not a brand (max 270 chars).", max_chars=270, kind="text"),
        _cta_slot(brief, max_chars=80),
        _disclosure_slot(brief, 12),
    ]
    parts = ["{{hook}}", "{{body}}", "{{cta}}", "{{disclosure}}" if brief.sponsored else ""]
    return _skeleton("threads_post", brief, parts, slots, fixed={"max_chars": THREADS_POST_CHARS},
                     notes=("Threads shows one topic tag per post; use at most one.",))


def validate_threads_post(draft: Draft) -> list[Issue]:
    return check_social(draft, Rule(max_chars=THREADS_POST_CHARS, hashtags=(0, THREADS_MAX_TAGS), cta="if_given"))


# -- carousels ---------------------------------------------------------------------------
def _slide_ids(k: int) -> tuple[str, str]:
    return ("hook", "subtitle") if k == 1 else (f"title_{k:02d}", f"body_{k:02d}")


def _slides_assemble(n: int, roles: list[str]) -> Callable[[Skeleton, dict[str, str]], dict[str, Any]]:
    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        out = []
        for k in range(1, n + 1):
            t, b = _slide_ids(k)
            out.append({"n": k, "role": roles[k - 1], "title": values[t], "body": values[b]})
        return {"slides": out}
    return assemble


def _carousel_roles(n: int) -> list[str]:
    return ["hook", "problem"] + [f"point_{k - 2}" for k in range(3, n - 1)] + ["recap", "cta"]


def build_linkedin_carousel(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    n = _opt_int(options, "slides", 10, LINKEDIN_SLIDES[0], LINKEDIN_SLIDES[1])
    lang = lang_of(brief)
    roles = _carousel_roles(n)
    slots: list[Slot | None] = [
        _hook_slot(brief, hook, max_chars=70, max_words=SLIDE_TITLE_WORDS, what="Slide 1 title, the hook"),
        Slot("subtitle", "Slide 1 subtitle: one short line saying who this is for (max 12 words).", max_words=12,
             kind="line", default=fit(pick(lang, f"For {brief.audience}", f"Téma: {brief.topic}"), max_words=12)),
        _disclosure_slot(brief),
    ]
    instr = {
        "problem": "Name the problem or the cost of the status quo from the reader's point of view.",
        "recap": "Recap the single most important takeaway in one line.",
    }
    for k in range(2, n):
        role = roles[k - 1]
        what = instr.get(role, f"Point {k - 2} of the argument: one idea, concrete and standalone.")
        slots.append(Slot(f"title_{k:02d}", f"Slide {k} title, at most {SLIDE_TITLE_WORDS} words. {what}",
                          max_words=SLIDE_TITLE_WORDS, kind="title"))
        slots.append(Slot(f"body_{k:02d}", f"Slide {k} body, at most {LINKEDIN_SLIDE_BODY_WORDS} words, no filler.",
                          max_words=LINKEDIN_SLIDE_BODY_WORDS, kind="text"))
    slots.append(Slot(f"title_{n:02d}", f"Final slide title, at most {SLIDE_TITLE_WORDS} words: the next step.",
                      max_words=SLIDE_TITLE_WORDS, kind="title", default=pick(lang, "Next step", "Další krok")))
    slots.append(Slot(f"body_{n:02d}", f"Final slide: one clear call to action, at most {LINKEDIN_SLIDE_BODY_WORDS} words.",
                      max_words=LINKEDIN_SLIDE_BODY_WORDS, kind="text",
                      default=fit(brief.cta, max_words=LINKEDIN_SLIDE_BODY_WORDS)))
    parts = ["## Slide 1\n\n**{{hook}}**\n\n{{subtitle}}" + ("\n\n{{disclosure}}" if brief.sponsored else "")]
    for k in range(2, n + 1):
        parts.append(f"## Slide {k}\n\n" + "**{{title_%02d}}**\n\n{{body_%02d}}" % (k, k))
    return _skeleton("linkedin_carousel", brief, parts, slots, assemble=_slides_assemble(n, roles),
                     fixed={"slides_count": n, "roles": roles}, notes=(
        "Slide 1 is the hook, the last slide is the call to action. One idea per slide.",
    ))


def validate_linkedin_carousel(draft: Draft) -> list[Issue]:
    slides = draft.parts.get("slides") or []
    issues: list[Issue] = []
    lo, hi = LINKEDIN_SLIDES
    if not lo <= len(slides) <= hi:
        issues.append(Issue("error", "SLIDE_COUNT", f"{len(slides)} slides, a carousel needs {lo} to {hi}."))
    for s in slides:
        where = f"slide {s['n']}"
        if word_count(s["title"]) > SLIDE_TITLE_WORDS:
            issues.append(Issue("warn", "SLIDE_TITLE_LONG", f"Title has {word_count(s['title'])} words, keep it to {SLIDE_TITLE_WORDS}.", where))
        if s["n"] > 1 and word_count(s["body"]) > LINKEDIN_SLIDE_BODY_WORDS:
            issues.append(Issue("warn", "SLIDE_BODY_LONG", f"Body has {word_count(s['body'])} words, keep it to {LINKEDIN_SLIDE_BODY_WORDS}.", where))
    if slides and not strip_placeholders(slides[0]["title"]).strip() and "hook" not in draft.slots_open:
        issues.append(Issue("warn", "HOOK_MISSING", "Slide 1 has no hook."))
    if slides and "title_%02d" % len(slides) not in draft.slots_open and "body_%02d" % len(slides) not in draft.slots_open:
        last = strip_placeholders(slides[-1]["title"] + " " + slides[-1]["body"])
        if not has_cta(last, draft.meta.get("cta")):
            issues.append(Issue("warn", "CTA_MISSING", "The last slide should carry the call to action.", f"slide {slides[-1]['n']}"))
    text = "\n".join(strip_placeholders(s["title"] + "\n" + s["body"]) for s in slides) + "\n" + slot_text(draft, "disclosure")
    issues += check_social(draft, Rule(cta="off", check_hook=False), text)
    return issues


def build_instagram_carousel(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    n = _opt_int(options, "slides", 7, 3, INSTAGRAM_MAX_SLIDES)
    roles = _carousel_roles(n) if n >= 4 else ["hook"] + ["point_%d" % k for k in range(1, n - 1)] + ["cta"]
    slots: list[Slot | None] = [
        _hook_slot(brief, hook, max_chars=90, max_words=12, what="Cover slide text, the hook"),
    ]
    for k in range(2, n):
        slots.append(Slot(f"slide_{k:02d}", f"Slide {k} text, at most {INSTAGRAM_SLIDE_WORDS} words: one idea, big and legible on a phone.",
                          max_words=INSTAGRAM_SLIDE_WORDS, kind="text"))
    slots.append(Slot(f"slide_{n:02d}", f"Final slide, at most {INSTAGRAM_SLIDE_WORDS} words: one clear call to action.",
                      max_words=INSTAGRAM_SLIDE_WORDS, kind="text", default=fit(brief.cta, max_words=INSTAGRAM_SLIDE_WORDS)))
    slots.append(Slot("caption", "Caption: the first 125 characters must carry the hook, then context and one call to action "
                                 f"(max {INSTAGRAM_CAPTION_CHARS} chars).", max_chars=1500, kind="text"))
    slots.append(_hashtag_slot(brief, *INSTAGRAM_HASHTAGS, default_count=4))
    slots.append(_disclosure_slot(brief))
    parts = ["## Slide 1\n\n{{hook}}"] + [f"## Slide {k}\n\n" + "{{slide_%02d}}" % k for k in range(2, n + 1)]
    parts.append("## Caption\n\n" + ("{{disclosure}}\n\n" if brief.sponsored else "") + "{{caption}}\n\n{{hashtags}}")

    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        slides = [{"n": 1, "role": roles[0], "text": values["hook"]}]
        slides += [{"n": k, "role": roles[k - 1], "text": values[f"slide_{k:02d}"]} for k in range(2, n + 1)]
        return {"slides": slides}

    return _skeleton("instagram_carousel", brief, parts, slots, assemble=assemble,
                     fixed={"slides_count": n, "roles": roles}, notes=(
        f"Up to {INSTAGRAM_MAX_SLIDES} slides. Slide 1 is the hook, the last slide is the call to action.",
    ))


def validate_instagram_carousel(draft: Draft) -> list[Issue]:
    slides = draft.parts.get("slides") or []
    issues: list[Issue] = []
    if not 2 <= len(slides) <= INSTAGRAM_MAX_SLIDES:
        issues.append(Issue("error", "SLIDE_COUNT", f"{len(slides)} slides, use 2 to {INSTAGRAM_MAX_SLIDES}."))
    for s in slides:
        if word_count(s["text"]) > INSTAGRAM_SLIDE_WORDS:
            issues.append(Issue("warn", "SLIDE_TEXT_LONG", f"{word_count(s['text'])} words, keep slides to {INSTAGRAM_SLIDE_WORDS}.", f"slide {s['n']}"))
    if slides and f"slide_{len(slides):02d}" not in draft.slots_open:
        last = strip_placeholders(slides[-1]["text"])
        if not has_cta(last, draft.meta.get("cta")):
            issues.append(Issue("warn", "CTA_MISSING", "The last slide should carry the call to action.", f"slide {slides[-1]['n']}"))
    caption = compose(draft, ["disclosure", "caption", "hashtags"])
    issues += check_social(draft, Rule(max_chars=INSTAGRAM_CAPTION_CHARS, hashtags=INSTAGRAM_HASHTAGS,
                                       cta="off", check_hook=False), caption)
    return issues


# -- Pinterest pin ------------------------------------------------------------------------
def build_pinterest_pin(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    kw = brief.primary_keyword
    slots = [
        _hook_slot(brief, hook, max_chars=PINTEREST_TITLE_CHARS, prefer=kw, slot_id="title", what="Pin title, keyword early"),
        Slot("description", f"Pin description (max {PINTEREST_DESCRIPTION_CHARS} chars): say what the pin gives the viewer, "
                            "use the keyword naturally and end with a soft call to action.",
             max_chars=PINTEREST_DESCRIPTION_CHARS, kind="text", must_include=[kw]),
        Slot("alt_text", f"Alt text: describe what is visible in the image literally, ideally under {PINTEREST_ALT_AIM} characters.",
             max_chars=PINTEREST_ALT_CHARS, kind="line"),
        _disclosure_slot(brief),
    ]
    parts = ["**Title:** {{title}}", "**Description:** {{description}}" + ("\n\n{{disclosure}}" if brief.sponsored else ""),
             "**Alt text:** {{alt_text}}"]
    return _skeleton("pinterest_pin", brief, parts, slots, hook_slot="title",
                     fixed={"title_chars": PINTEREST_TITLE_CHARS, "description_chars": PINTEREST_DESCRIPTION_CHARS},
                     notes=("Pinterest is a search engine: lead with the keyword and describe the pin plainly.",))


def validate_pinterest_pin(draft: Draft) -> list[Issue]:
    issues: list[Issue] = []
    for slot_id, limit in (("title", PINTEREST_TITLE_CHARS), ("description", PINTEREST_DESCRIPTION_CHARS), ("alt_text", PINTEREST_ALT_CHARS)):
        n = len(slot_text(draft, slot_id))
        if n > limit:
            issues.append(Issue("error", "CHAR_LIMIT", f"{n} characters, the limit is {limit}.", slot_id))
    alt = len(slot_text(draft, "alt_text"))
    if PINTEREST_ALT_AIM < alt <= PINTEREST_ALT_CHARS:
        issues.append(Issue("info", "ALT_TEXT_LONG", f"Alt text is {alt} characters; under {PINTEREST_ALT_AIM} reads better in screen readers.", "alt_text"))
    kw = draft.meta.get("primary_keyword")
    combined = slot_text(draft, "title") + " " + slot_text(draft, "description")
    if kw and combined.strip() and not keyword_in(combined, kw, draft.lang):
        issues.append(Issue("warn", "KEYWORD_MISSING", f"The keyword '{kw}' appears in neither title nor description."))
    issues += check_social(draft, Rule(cta="if_given", check_hook=False), compose(draft, ["title", "description", "disclosure"]))
    return issues


# -- YouTube community post ---------------------------------------------------------------
def build_youtube_community_post(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    raw = (options or {}).get("poll")
    texts: list[str | None] = []
    if isinstance(raw, (list, tuple)):
        texts = [(" ".join(str(t).split()) or None) for t in raw][:YOUTUBE_POLL_OPTIONS[1]]
    elif isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        texts = [None] * min(raw, YOUTUBE_POLL_OPTIONS[1])
    while texts and len(texts) < YOUTUBE_POLL_OPTIONS[0]:
        texts.append(None)
    k_opts = len(texts)
    slots: list[Slot | None] = [
        _hook_slot(brief, hook, max_chars=140, what="First line"),
        Slot("body", "Two or three short sentences that give the community a reason to respond (max 680 chars).",
             max_chars=680, kind="text"),
        _cta_slot(brief, max_chars=120),
        _disclosure_slot(brief, 12),
    ]
    parts = ["{{hook}}", "{{body}}", "{{cta}}", "{{disclosure}}" if brief.sponsored else ""]
    if k_opts:
        slots.append(Slot("poll_question", "Poll question, specific and answerable in one tap (max 100 chars).", max_chars=100, kind="line"))
        for i, t in enumerate(texts, 1):
            slots.append(Slot(f"poll_option_{i}", f"Poll option {i}, short and distinct (max {YOUTUBE_POLL_OPTION_CHARS} chars).",
                              max_chars=YOUTUBE_POLL_OPTION_CHARS, kind="line", default=t))
        parts.append("**Poll:** {{poll_question}}\n\n" + "\n".join("- {{poll_option_%d}}" % i for i in range(1, k_opts + 1)))

    def assemble(sk: Skeleton, values: dict[str, str]) -> dict[str, Any]:
        if not k_opts:
            return {"poll": None}
        return {"poll": {"question": values["poll_question"],
                         "options": [values[f"poll_option_{i}"] for i in range(1, k_opts + 1)]}}

    return _skeleton("youtube_community_post", brief, parts, slots, assemble=assemble,
                     fixed={"max_chars": YOUTUBE_COMMUNITY_CHARS, "poll_options": k_opts},
                     notes=("Optional poll: 2 to 4 options, passed as options['poll'] (a count or a list of option texts).",))


def validate_youtube_community_post(draft: Draft) -> list[Issue]:
    text = compose(draft, ["hook", "body", "cta", "disclosure"])
    issues = check_social(draft, Rule(max_chars=YOUTUBE_COMMUNITY_CHARS, hashtags=(0, 3), cta="if_given"), text)
    poll = draft.parts.get("poll")
    if poll:
        opts = [strip_placeholders(o).strip() for o in poll["options"]]
        lo, hi = YOUTUBE_POLL_OPTIONS
        if not lo <= len(opts) <= hi:
            issues.append(Issue("error", "POLL_OPTIONS", f"{len(opts)} poll options, use {lo} to {hi}."))
        for i, o in enumerate(opts, 1):
            if len(o) > YOUTUBE_POLL_OPTION_CHARS:
                issues.append(Issue("error", "CHAR_LIMIT", f"{len(o)} characters, the limit is {YOUTUBE_POLL_OPTION_CHARS}.", f"poll option {i}"))
        filled = [o.lower() for o in opts if o]
        if len(set(filled)) != len(filled):
            issues.append(Issue("warn", "POLL_DUPLICATE", "Poll options must be distinct."))
    return issues


# -- Reddit answer -------------------------------------------------------------------------
_AFFILIATION_MARKERS = (
    "i work", "i'm with", "i am with", "disclosure", "affiliat", "my employer", "i'm part of", "i am part of",
    "upozorneni", "pracuji", "jsem z", "zamestnanec", "spolupracuji", "jsem soucasti",
)
_BARE_DOMAIN_RE = re.compile(r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|cz|sk|io|co|net|org|eu|app|shop|store|de|uk|ai)\b")
_PROMO_RE = re.compile("|".join((
    r"check out our", r"visit our", r"our (?:product|platform|tool|app|shop|store|service)s?\b", r"we offer",
    r"use (?:the )?(?:code|coupon)", r"\bdiscount\b", r"\d+\s?% off", r"sign up", r"buy now", r"limited offer",
    r"link in (?:my )?bio", r"\bdm me\b", r"navstivte", r"nase (?:nabidka|produkty|sluzby|aplikace|eshop)",
    r"\bsleva\b", r"slevovy kod", r"\bkupte\b", r"objednejte",
)))


def _brand_slug(brand: str) -> str:
    return re.sub(r"[^a-z0-9]", "", fold(brand).lower())


def links_to_brand(text: str, brand: str) -> bool:
    """True when the text contains a URL or bare domain that carries the brand name."""
    slug = _brand_slug(brand)
    if len(slug) < 3:
        return False
    candidates = [fold(u).lower() for u in urls_in(text)] + _BARE_DOMAIN_RE.findall(fold(strip_placeholders(text)).lower())
    return any(slug in c for c in candidates)


def has_affiliation_disclosure(text: str, brand: str) -> bool:
    """A line that names the brand together with an affiliation marker, such as 'I work at Brand'."""
    b = fold(brand).lower().strip()
    return any(b in line and any(m in line for m in _AFFILIATION_MARKERS)
               for line in fold(strip_placeholders(text)).lower().splitlines())


def build_reddit_answer(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    lang = lang_of(brief)
    disclosure = pick(lang, f"Disclosure: I work at {brief.brand}.", f"Upozornění: pracuji pro {brief.brand}.")
    if brief.sponsored:
        disclosure += pick(lang, " This post is sponsored.", " Tento příspěvek je sponzorovaný.")
    sub = str((options or {}).get("subreddit") or "").strip()
    slots = [
        Slot("direct_answer", "Answer the question directly in one or two sentences. No promotion, no brand mention, no links.",
             max_chars=300, kind="text", default=hook.strip() if hook and hook.strip() else None),
        Slot("details", "Explain how and why with practical steps, trade-offs or examples. Be useful even if the reader never "
                        "buys anything. No brand mention, no links.", max_chars=2500, kind="text"),
        Slot("caveats", "Say when this advice does not apply and mention fair alternatives, including ones that are not ours.",
             max_chars=700, kind="text"),
        Slot("disclosure", "Affiliation disclosure naming the brand, for example 'Disclosure: I work at <brand>.'",
             max_chars=160, kind="line", default=disclosure, must_include=[brief.brand]),
    ]
    parts = ["{{direct_answer}}", "{{details}}", "{{caveats}}", "---", "{{disclosure}}"]
    notes = [
        "Never write sales copy here: the first answer is purely helpful, with no brand link in the first 300 characters.",
        "Check the subreddit rules on brand accounts and self-promotion before posting; many forbid it.",
    ]
    if sub:
        notes.append(f"Target subreddit: {sub}. Read its rules first.")
    return _skeleton("reddit_answer", brief, parts, slots, hook_slot="direct_answer",
                     fixed={"max_chars": REDDIT_COMMENT_CHARS, "brand_link_window": REDDIT_LINK_WINDOW, "subreddit": sub or None},
                     notes=tuple(notes))


def validate_reddit_answer(draft: Draft) -> list[Issue]:
    brand = str(draft.meta.get("brand") or "")
    full = strip_placeholders(draft.body)
    issues: list[Issue] = []
    if len(full) > REDDIT_COMMENT_CHARS:
        issues.append(Issue("error", "CHAR_LIMIT", f"{len(full)} characters, the limit is {REDDIT_COMMENT_CHARS}."))
    if brand and not has_affiliation_disclosure(full, brand):
        issues.append(Issue("error", "DISCLOSURE_MISSING", f"Disclose your affiliation with a line like 'I work at {brand}'."))
    if brand and links_to_brand(full[:REDDIT_LINK_WINDOW], brand):
        issues.append(Issue("error", "BRAND_LINK_EARLY", f"Link to the brand within the first {REDDIT_LINK_WINDOW} characters."))
    content = "\n".join(l for l in full.splitlines() if not (brand and has_affiliation_disclosure(l, brand)))
    if brand and fold(brand).lower() in fold(content).lower():
        issues.append(Issue("warn", "BRAND_PROMOTION", "The first answer should not mention the brand outside the disclosure."))
    if _PROMO_RE.search(fold(content).lower()):
        issues.append(Issue("warn", "PROMO_LANGUAGE", "Promotional wording found; a first answer must be purely helpful."))
    if "direct_answer" not in draft.slots_open and not slot_text(draft, "direct_answer"):
        issues.append(Issue("warn", "ANSWER_MISSING", "Answer the question directly first."))
    issues += [i for i in check_social(draft, Rule(cta="off", check_hook=False), content) if i.code != "DISCLOSURE_MISSING"]
    issues += disclosure_issue(draft, full)
    return issues


# -- Google Business Profile post --------------------------------------------------------------
_GBP_BUTTON_HINTS = (
    ("Call now", ("call", "zavolej", "zavolejte", "volej", "volejte")),
    ("Book", ("book", "reserve", "rezerv", "objednej se", "objednejte se")),
    ("Order online", ("order", "objedn")),
    ("Sign up", ("sign up", "register", "subscribe", "regist", "prihlas")),
    ("Buy", ("buy", "shop", "kup", "nakup")),
)


def gbp_default_button(brief: Brief) -> str:
    cta = fold(brief.cta or "").lower()
    for label, hints in _GBP_BUTTON_HINTS:
        if any(h in cta for h in hints):
            return label
    return "Learn more"


def build_google_business_post(brief: Brief, *, hook: str | None = None, options: dict | None = None) -> Skeleton:
    slots = [
        _hook_slot(brief, hook, max_chars=90, what="First sentence"),
        Slot("details", "One or two sentences with the specific news, offer or event: what, when, where (max 150 chars).",
             max_chars=150, kind="text"),
        _cta_slot(brief, max_chars=50),
        Slot("cta_button", "Button label, exactly one of: " + ", ".join(GBP_CTA_BUTTONS) + ".", max_chars=20, kind="line",
             default=gbp_default_button(brief)),
        _disclosure_slot(brief, 12),
    ]
    parts = ["{{hook}}", "{{details}}", "{{cta}}", "{{disclosure}}" if brief.sponsored else "", "**Button:** {{cta_button}}"]
    return _skeleton("google_business_post", brief, parts, slots,
                     fixed={"cta_buttons": dict(GBP_CTA_BUTTONS), "aim_chars": list(GBP_AIM_CHARS)},
                     notes=("Aim for 150 to 300 characters. Name the offer, date and place; avoid phone numbers and ALL CAPS.",))


def validate_google_business_post(draft: Draft) -> list[Issue]:
    text = compose(draft, ["hook", "details", "cta", "disclosure"])
    issues = check_social(draft, Rule(max_chars=GBP_POST_CHARS, cta="if_given"), text)
    n = len(text)
    if not ({"hook", "details", "cta"} & set(draft.slots_open)) and not GBP_AIM_CHARS[0] <= n <= GBP_AIM_CHARS[1]:
        issues.append(Issue("warn", "LENGTH_AIM", f"{n} characters, aim for {GBP_AIM_CHARS[0]} to {GBP_AIM_CHARS[1]}."))
    button = slot_text(draft, "cta_button")
    if button and button not in GBP_CTA_BUTTONS:
        issues.append(Issue("error", "INVALID_CTA_BUTTON", f"'{button}' is not one of: {', '.join(GBP_CTA_BUTTONS)}."))
    return issues


# -- registry -----------------------------------------------------------------------------------
def _spec(fid: str, en: str, cs: str, platform: str, build: Callable, validate: Callable, limits: dict[str, Any],
          d_en: str, d_cs: str) -> FormatSpec:
    return FormatSpec(id=fid, name_en=en, name_cs=cs, family="social", platform=platform, build=build,
                      validate=validate, limits=limits, description_en=d_en, description_cs=d_cs)


# Platform limits checked 2026-10, verify before publishing.
FORMAT_SPECS: list[FormatSpec] = [
    _spec("linkedin_post", "LinkedIn post", "LinkedIn příspěvek", "linkedin", build_linkedin_post, validate_linkedin_post,
          {"max_chars": LINKEDIN_POST_CHARS, "hook_window": LINKEDIN_HOOK_WINDOW, "hashtags": list(LINKEDIN_HASHTAGS)},
          "Feed post with the hook in the first 140 characters, short paragraphs and a closing question or call to action.",
          "Příspěvek do feedu s hookem v prvních 140 znacích, krátkými odstavci a závěrečnou otázkou nebo výzvou."),
    _spec("linkedin_carousel", "LinkedIn carousel", "LinkedIn karusel", "linkedin", build_linkedin_carousel,
          validate_linkedin_carousel,
          {"slides": list(LINKEDIN_SLIDES), "title_words": SLIDE_TITLE_WORDS, "body_words": LINKEDIN_SLIDE_BODY_WORDS},
          "Document carousel of 8 to 12 slides: hook first, one idea per slide, call to action last.",
          "Karusel o 8 až 12 slidech: nejdřív hook, jedna myšlenka na slide, nakonec výzva k akci."),
    _spec("x_post", "X post", "Příspěvek na X", "x", build_x_post, validate_x_post,
          {"max_chars": X_POST_CHARS, "url_weight": X_URL_WEIGHT},
          "Single post of at most 280 characters: hook, one point and a call to action.",
          "Jeden příspěvek do 280 znaků: hook, jedna myšlenka a výzva k akci."),
    _spec("x_thread", "X thread", "Vlákno na X", "x", build_x_thread, validate_x_thread,
          {"posts": list(X_THREAD_POSTS), "post_chars": X_THREAD_POST_CHARS},
          "Thread of 5 to 10 posts: post 1 promises the payoff, the last post recaps and asks.",
          "Vlákno o 5 až 10 příspěvcích: první slibuje přínos, poslední shrnuje a vyzývá k akci."),
    _spec("instagram_caption", "Instagram caption", "Popisek na Instagramu", "instagram", build_instagram_caption,
          validate_instagram_caption,
          {"max_chars": INSTAGRAM_CAPTION_CHARS, "hook_window": INSTAGRAM_HOOK_WINDOW, "hashtags": list(INSTAGRAM_HASHTAGS)},
          "Caption with the hook in the first 125 characters and three to five hashtags.",
          "Popisek s hookem v prvních 125 znacích a třemi až pěti hashtagy."),
    _spec("instagram_carousel", "Instagram carousel", "Instagramový karusel", "instagram", build_instagram_carousel,
          validate_instagram_carousel,
          {"max_slides": INSTAGRAM_MAX_SLIDES, "slide_words": INSTAGRAM_SLIDE_WORDS, "caption_chars": INSTAGRAM_CAPTION_CHARS},
          "Up to 10 slides of at most 25 words each, plus a caption.",
          "Až 10 slidů po nejvýše 25 slovech a popisek."),
    _spec("facebook_post", "Facebook post", "Příspěvek na Facebooku", "facebook", build_facebook_post,
          validate_facebook_post, {"aim_words": FACEBOOK_AIM_WORDS},
          "Short post, aim for 80 words or fewer, with a hook and one call to action.",
          "Krátký příspěvek do 80 slov s hookem a jednou výzvou k akci."),
    _spec("threads_post", "Threads post", "Příspěvek na Threads", "threads", build_threads_post, validate_threads_post,
          {"max_chars": THREADS_POST_CHARS, "max_tags": THREADS_MAX_TAGS},
          "Conversational post of at most 500 characters.", "Konverzační příspěvek do 500 znaků."),
    _spec("pinterest_pin", "Pinterest pin", "Pin na Pinterestu", "pinterest", build_pinterest_pin, validate_pinterest_pin,
          {"title_chars": PINTEREST_TITLE_CHARS, "description_chars": PINTEREST_DESCRIPTION_CHARS, "alt_chars": PINTEREST_ALT_CHARS},
          "Keyword-led title, description and alt text for a pin.",
          "Titulek s klíčovým slovem, popis a alternativní text pro pin."),
    _spec("youtube_community_post", "YouTube community post", "Komunitní příspěvek na YouTube", "youtube",
          build_youtube_community_post, validate_youtube_community_post,
          {"max_chars": YOUTUBE_COMMUNITY_CHARS, "poll_options": list(YOUTUBE_POLL_OPTIONS)},
          "Community tab post of at most 1000 characters with an optional poll of 2 to 4 options.",
          "Příspěvek v komunitě do 1000 znaků s volitelnou anketou o 2 až 4 možnostech."),
    _spec("reddit_answer", "Reddit answer", "Odpověď na Redditu", "reddit", build_reddit_answer, validate_reddit_answer,
          {"max_chars": REDDIT_COMMENT_CHARS, "brand_link_window": REDDIT_LINK_WINDOW},
          "Genuinely helpful answer with an affiliation disclosure and no promotion.",
          "Opravdu užitečná odpověď s uvedením vztahu ke značce a bez propagace."),
    _spec("google_business_post", "Google Business post", "Příspěvek ve Firmě na Googlu", "google",
          build_google_business_post, validate_google_business_post,
          {"max_chars": GBP_POST_CHARS, "aim_chars": list(GBP_AIM_CHARS), "cta_buttons": list(GBP_CTA_BUTTONS)},
          "Business Profile update of 150 to 300 characters with a call to action button.",
          "Aktualita pro Profil firmy o 150 až 300 znacích s tlačítkem výzvy k akci."),
]
