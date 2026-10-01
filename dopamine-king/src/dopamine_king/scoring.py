"""Dopamine Score: an explainable, heuristic model of attention triggers in a hook.

The score is NOT a neuroscience measurement. It rates how many well documented attention
triggers a headline or opening line carries (curiosity gap, surprise, emotional arousal,
relevance to the reader, concrete utility) and how easy it is to process, then subtracts a
penalty for clickbait and overclaiming. Lexicons and parameters live in
``data/scoring_spec.json`` and are shared with the JavaScript port used by the game UI;
golden tests keep both implementations identical.

Matching rules (must stay identical in JS): NFC normalise, tokenise on letter/digit runs
(apostrophes allowed inside a word, digit groups like 1,000 or 3.5 stay one token), lower-case, for Czech additionally strip diacritics so
text typed without hacek and carka still matches. Lexicon entries are 1..n tokens, a trailing
``*`` on a token means prefix match. Per category the scan is left to right, longest match first,
non overlapping.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

SPEC_PATH = Path(__file__).with_name("data") / "scoring_spec.json"

WEIGHTED_DRIVERS = ("curiosity", "surprise", "emotion", "relevance", "utility")
ALL_PARTS = WEIGHTED_DRIVERS + ("fluency",)
LEX_CATEGORIES = (
    "curiosity", "contrast", "emotion", "practical", "social", "second_person",
    "clickbait", "overclaim", "positive", "negative",
)
FEATURE_NAMES = (
    "n_words", "has_number", "starts_with_number", "is_question", "open_loop", "exclaim",
    "caps_ratio", "avg_word_len", "promise_gap",
    "curiosity_hits", "contrast_hits", "emotion_hits", "practical_hits", "social_hits",
    "second_person_hits", "clickbait_hits", "overclaim_hits", "positive_hits", "negative_hits",
)

_TOKEN_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)+|[^\W_]+(?:['’][^\W_]+)*")
_NUM_RE = re.compile(r"[0-9]+(?:[.,][0-9]+)*")
_INT_RE = re.compile(r"[0-9]+")
_LIST_LINE_RE = re.compile(r"^[ \t]*(?:[-*•]|[0-9]{1,2}[.)])[ \t]+\S", re.M)
_HEADING_RE = re.compile(r"^[ \t]*#{2,3}[ \t]+\S", re.M)
_CS_CHARS = frozenset("ěščřžůďťň")

_SPEC_CACHE: dict[str, dict[str, Any]] = {}
_COMPILED_CACHE: dict[tuple[int, str], dict[str, Any]] = {}


@dataclass(frozen=True)
class Token:
    text: str   # original case
    norm: str   # lower-cased, apostrophes unified
    start: int
    end: int


@dataclass
class Span:
    category: str
    tok_start: int
    tok_end: int      # exclusive
    start: int        # character offsets in the normalised text
    end: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "tok_start": self.tok_start, "tok_end": self.tok_end,
                "start": self.start, "end": self.end, "text": self.text}


@dataclass
class HookScore:
    total: float                      # 0..100 after the clickbait penalty
    raw: float                        # 0..1 weighted driver mean before display transform
    parts: dict[str, float]           # curiosity, surprise, emotion, relevance, utility, fluency (0..100)
    clickbait_risk: float             # 0..1
    lang: str
    features: dict[str, float]
    hits: dict[str, int]
    spans: list[Span] = field(default_factory=list)
    tips: list[dict[str, str]] = field(default_factory=list)   # {"key", "en", "cs"}
    text: str = ""

    def to_dict(self, ndigits: int | None = 2) -> dict[str, Any]:
        """Display friendly dict. ``ndigits=None`` keeps full precision (used by parity tests)."""

        def r(x: float, digits: int | None = None) -> float:
            if ndigits is None:
                return x
            return round(x, ndigits if digits is None else digits)

        return {
            "total": r(self.total),
            "raw": r(self.raw, 4),
            "parts": {k: r(v) for k, v in self.parts.items()},
            "clickbait_risk": r(self.clickbait_risk, 4),
            "lang": self.lang,
            "features": {k: r(v, 4) for k, v in self.features.items()},
            "hits": dict(self.hits),
            "spans": [s.to_dict() for s in self.spans],
            "tips": list(self.tips),
            "text": self.text,
        }


# -- spec loading -------------------------------------------------------------------
def load_spec(path: str | Path | None = None) -> dict[str, Any]:
    key = str(path or SPEC_PATH)
    if key not in _SPEC_CACHE:
        _SPEC_CACHE[key] = json.loads(Path(key).read_text("utf-8"))
    return _SPEC_CACHE[key]


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def fold(text: str) -> str:
    """Strip diacritics (used for Czech matching so ASCII-typed text still scores)."""
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def tokenize(text: str) -> list[Token]:
    """Tokenise already NFC-normalised text."""
    return [
        Token(m.group(), m.group().lower().replace("’", "'"), m.start(), m.end())
        for m in _TOKEN_RE.finditer(text)
    ]


def _compile_entries(entries: Sequence[str], fold_on: bool) -> list[tuple[tuple[str, ...], tuple[bool, ...]]]:
    out = []
    for entry in entries:
        parts = entry.lower().split()
        if fold_on:
            parts = [fold(p) for p in parts]
        out.append((tuple(p.rstrip("*") for p in parts), tuple(p.endswith("*") for p in parts)))
    return out


def _tables(lang: str, spec: dict[str, Any]) -> dict[str, Any]:
    key = (id(spec), lang)
    if key not in _COMPILED_CACHE:
        block = spec["langs"][lang]
        fold_on = lang == "cs"
        _COMPILED_CACHE[key] = {
            "lex": {cat: _compile_entries(block["lexicons"].get(cat, []), fold_on) for cat in LEX_CATEGORIES},
            "starters": _compile_entries(block["question_starters"], fold_on),
            "fold": fold_on,
        }
    return _COMPILED_CACHE[key]


def find_matches(norms: Sequence[str], compiled: Sequence[tuple[tuple[str, ...], tuple[bool, ...]]]) -> list[tuple[int, int]]:
    """Left to right, longest entry first, non overlapping. Returns [(start, end_exclusive)]."""
    out: list[tuple[int, int]] = []
    n = len(norms)
    i = 0
    while i < n:
        best = 0
        for toks, wild in compiled:
            size = len(toks)
            if size <= best or i + size > n:
                continue
            ok = True
            for j in range(size):
                t = norms[i + j]
                if wild[j]:
                    if not t.startswith(toks[j]):
                        ok = False
                        break
                elif t != toks[j]:
                    ok = False
                    break
            if ok:
                best = size
        if best:
            out.append((i, i + best))
            i += best
        else:
            i += 1
    return out


def detect_lang(text: str, spec: dict[str, Any] | None = None) -> str:
    spec = spec or load_spec()
    low = normalize(text).lower()
    if any(c in _CS_CHARS for c in low):
        return "cs"
    cs_stop = {fold(w) for w in spec["langs"]["cs"]["stopwords"]}
    en_stop = set(spec["langs"]["en"]["stopwords"])
    toks = [t.norm for t in tokenize(low)]
    cs = sum(1 for t in toks if fold(t) in cs_stop)
    en = sum(1 for t in toks if t in en_stop)
    return "cs" if cs > en else "en"


# -- scoring ------------------------------------------------------------------------
def _sat(x: float, k: float) -> float:
    return 1.0 - math.exp(-x / k)


def _brevity(n: int) -> float:
    if n == 0:
        return 0.0
    if n < 3:
        return 0.4
    if n < 6:
        return 0.4 + 0.6 * (n - 3) / 3
    if n <= 12:
        return 1.0
    if n <= 25:
        return 1.0 - 0.7 * (n - 12) / 13
    return 0.3


def _promise_gap(tokens: Sequence[Token], starts_with_number: bool, body: str) -> float:
    if not body or not starts_with_number or not tokens:
        return 0.0
    if not _INT_RE.fullmatch(tokens[0].norm):
        return 0.0
    promised = int(tokens[0].norm)
    if promised < 2 or promised > 60:
        return 0.0
    found = max(len(_LIST_LINE_RE.findall(body)), len(_HEADING_RE.findall(body)))
    return max(0.0, (promised - found) / promised)


def score_hook(
    text: str,
    body: str = "",
    *,
    lang: str | None = None,
    weights: dict[str, float] | None = None,
    spec: dict[str, Any] | None = None,
) -> HookScore:
    spec = spec or load_spec()
    p = spec["params"]
    text = normalize(text or "").strip()
    lang = lang if lang in spec["langs"] else detect_lang(text, spec)
    tables = _tables(lang, spec)

    tokens = tokenize(text)[: p["max_tokens"]]
    n = len(tokens)
    norms = [fold(t.norm) if tables["fold"] else t.norm for t in tokens]

    hits: dict[str, int] = {}
    spans: list[Span] = []
    for cat in LEX_CATEGORIES:
        matches = find_matches(norms, tables["lex"][cat])
        hits[cat] = len(matches)
        for a, b in matches:
            spans.append(Span(cat, a, b, tokens[a].start, tokens[b - 1].end, text[tokens[a].start:tokens[b - 1].end]))

    is_num = [bool(_NUM_RE.fullmatch(t.norm)) for t in tokens]
    year_like = [is_num[i] and len(tokens[i].norm) == 4 and 1900 <= int(tokens[i].norm) <= 2100 for i in range(n)]
    has_number = any(is_num[i] and not year_like[i] for i in range(n))
    starts_with_number = bool(n and is_num[0] and not year_like[0])

    is_question = text.endswith("?") or text.endswith("？") or bool(n and find_matches(norms[:1], tables["starters"]))
    open_loop = (":" in text) or ("..." in text) or ("…" in text)
    exclaim = text.count("!")
    caps = sum(
        1 for t in tokens
        if t.text.isalpha() and len(t.text) >= p["caps_min_len"] and t.text == t.text.upper() and t.text != t.text.lower()
    )
    caps_ratio = caps / max(n, 1)
    alpha_lengths = [len(t.norm) for t in tokens if t.norm.isalpha()]
    avg_word_len = sum(alpha_lengths) / len(alpha_lengths) if alpha_lengths else 0.0
    promise_gap = _promise_gap(tokens, starts_with_number, body or "")

    sc = p["scales"]
    d01 = {
        "curiosity": _sat(1.0 * min(hits["curiosity"], 3) + 0.6 * is_question + 0.35 * open_loop, sc["curiosity"]),
        "surprise": _sat(1.0 * min(hits["contrast"], 3)
                         + 0.4 * (1 if (has_number and hits["negative"] > 0) else 0), sc["surprise"]),
        "emotion": _sat(1.0 * min(hits["emotion"], 3) + 0.3 * min(exclaim, 2)
                        + 0.25 * min(hits["positive"], 2) + 0.35 * min(hits["negative"], 2), sc["emotion"]),
        "relevance": _sat(1.0 * min(hits["second_person"], 2) + 0.6 * min(hits["social"], 2), sc["relevance"]),
        "utility": _sat(1.0 * min(hits["practical"], 3) + 0.35 * has_number + 0.65 * starts_with_number, sc["utility"]),
    }
    ref = p["avg_len_ref"][lang]
    ease = min(1.0, max(0.0, 1.0 - (avg_word_len - ref) / 3.0)) if avg_word_len > 0 else 0.5
    fluency = 0.6 * _brevity(n) + 0.4 * ease

    w = weights or p["weights"]
    wsum = sum(w.get(d, 0.0) for d in WEIGHTED_DRIVERS) or 1.0
    raw5 = sum(w.get(d, 0.0) * d01[d] for d in WEIGHTED_DRIVERS) / wsum
    modulator = p["fluency_floor"] + (1.0 - p["fluency_floor"]) * fluency
    raw = raw5 * modulator
    display = 100.0 * (1.0 - math.exp(-raw / p["display_tau"]))

    risk_raw = (1.0 * min(hits["clickbait"], 3) + 0.5 * min(hits["overclaim"], 3)
                + 0.35 * max(exclaim - 1, 0) + 2.0 * max(caps_ratio - p["caps_threshold"], 0.0)
                + 0.6 * promise_gap)
    risk = _sat(risk_raw, sc["risk"])
    total = display * (1.0 - p["risk_penalty"] * risk)

    features: dict[str, float] = {
        "n_words": float(n), "has_number": float(has_number), "starts_with_number": float(starts_with_number),
        "is_question": float(is_question), "open_loop": float(open_loop), "exclaim": float(exclaim),
        "caps_ratio": caps_ratio, "avg_word_len": avg_word_len, "promise_gap": promise_gap,
        "curiosity_hits": float(hits["curiosity"]), "contrast_hits": float(hits["contrast"]),
        "emotion_hits": float(hits["emotion"]), "practical_hits": float(hits["practical"]),
        "social_hits": float(hits["social"]), "second_person_hits": float(hits["second_person"]),
        "clickbait_hits": float(hits["clickbait"]), "overclaim_hits": float(hits["overclaim"]),
        "positive_hits": float(hits["positive"]), "negative_hits": float(hits["negative"]),
    }
    parts = {d: 100.0 * d01[d] for d in WEIGHTED_DRIVERS}
    parts["fluency"] = 100.0 * fluency

    tips = _tips(spec, d01, fluency, risk, promise_gap, n, avg_word_len, ref, w, wsum, total)
    return HookScore(total, raw, parts, risk, lang, features, hits, spans, tips, text)


_TIP_FOR_DRIVER = {
    "curiosity": "open_loop", "utility": "add_utility", "relevance": "address_reader",
    "emotion": "add_emotion", "surprise": "add_contrast",
}


def _tips(spec, d01, fluency, risk, promise_gap, n, avg_len, ref, w, wsum, total) -> list[dict[str, str]]:
    cands: list[tuple[float, str]] = []
    if risk > 0.35:
        cands.append((1.0 + risk, "reduce_clickbait"))
    if promise_gap > 0.2:
        cands.append((0.9 + promise_gap, "keep_promise"))
    for d, key in _TIP_FOR_DRIVER.items():
        if d01[d] < 0.35:
            cands.append((w.get(d, 0.0) / wsum * (0.6 - d01[d]), key))
    if fluency < 0.65:
        if n > 12:
            cands.append(((1.0 - fluency) * 0.6, "shorten"))
        elif avg_len > ref + 0.8:
            cands.append(((1.0 - fluency) * 0.6, "simplify"))
    cands.sort(key=lambda c: (-c[0], c[1]))
    keys = [k for _, k in cands[:3]]
    if not keys and total >= 70 and risk < 0.2:
        keys = ["ship_it"]
    return [{"key": k, "en": spec["messages"][k]["en"], "cs": spec["messages"][k]["cs"]} for k in keys]


def feature_vector(score: HookScore) -> list[float]:
    return [score.features[name] for name in FEATURE_NAMES]


def rank_hooks(candidates: Sequence[str], *, lang: str | None = None, body: str = "") -> list[tuple[str, HookScore]]:
    """Score and sort candidates best first (ties keep input order)."""
    scored = [(c, score_hook(c, body, lang=lang)) for c in candidates]
    return sorted(scored, key=lambda cs: -cs[1].total)
