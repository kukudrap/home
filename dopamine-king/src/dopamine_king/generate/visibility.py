"""AI answer visibility analytics: how often and how favourably answer engines mention and cite a brand.

Pure functions over answers you collected yourself (for example from a manual test of ChatGPT, Perplexity,
Gemini or Claude with the buyer questions from ``suggest_queries``). Nothing here calls an engine or the
network. Matching is case and diacritics insensitive with word boundaries; Czech declension is not guessed,
so pass inflected brand forms through ``aliases``.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Sequence
from urllib.parse import urlsplit

from ..models import Serializable
from ..scoring import detect_lang, fold
from .seo import norm_lang, split_sentences
from .types import Brief


@dataclass
class AnswerRecord(Serializable):
    query: str
    engine: str
    text: str
    cited_urls: list[str] = field(default_factory=list)


@dataclass
class VisibilityReport(Serializable):
    brand: str
    n_answers: int
    mention_rate: float                           # share of answers that name the brand
    citation_rate: float                          # share of answers that cite one of the brand domains
    avg_first_mention_position: float | None      # 0 = start of the answer, 1 = end; None when never mentioned
    share_of_voice: dict[str, float]              # brand and competitors, mentions normalised to sum 1
    sentiment: float                              # -1..1, only sentences that mention the brand
    per_engine: dict[str, dict[str, Any]]
    per_query: list[dict[str, Any]]
    gaps: list[str]                               # queries where competitors appear and the brand does not


# -- matching ---------------------------------------------------------------------------
def _norm(text: str) -> str:
    return fold(unicodedata.normalize("NFC", text or "").lower()).replace("’", "'")


def _name_pattern(names: Sequence[str]) -> re.Pattern[str]:
    parts = []
    for name in names:
        words = [re.escape(w) for w in re.split(r"[\s\-]+", _norm(name).strip()) if w]
        if words:
            parts.append(r"[\s\-]+".join(words))
    if not parts:
        return re.compile(r"(?!x)x")
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?![a-z0-9])")


def _host(url: str) -> str:
    u = (url or "").strip()
    if "://" not in u:
        u = "//" + u
    try:
        host = (urlsplit(u).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _cites_domain(urls: Sequence[str], domains: set[str]) -> bool:
    for url in urls:
        host = _host(url)
        if host and any(host == d or host.endswith("." + d) for d in domains):
            return True
    return False


# -- sentiment lexicon (folded, "*" = prefix) -------------------------------------------------------
_LEXICON: dict[str, dict[str, tuple[str, ...]]] = {
    "en": {
        "pos": ("good", "great", "excellent", "best", "love", "loved", "recommend", "recommended", "reliable", "comfortable",
                "affordable", "popular", "trusted", "quality", "durable", "fast", "easy", "helpful", "impressive", "favorite",
                "favourite", "top", "solid", "praised", "outstanding", "innovative", "worth", "perfect", "superior", "effective",
                "strong", "satisfied", "happy", "leading", "lightweight", "stable", "positive", "well-regarded"),
        "neg": ("bad", "poor", "worst", "hate", "avoid", "unreliable", "uncomfortable", "expensive", "overpriced", "slow",
                "difficult", "disappointing", "disappointed", "issues", "problem", "problems", "complaints", "complaint",
                "criticized", "criticised", "flawed", "fragile", "weak", "negative", "scam", "lacking", "limited", "mediocre",
                "outdated", "buggy", "risky", "concerns", "unhappy", "defective", "fail", "fails", "failed", "worse", "inferior",
                "drawback", "drawbacks", "downside", "downsides"),
        "negation": ("not", "no", "never", "isn't", "aren't", "don't", "doesn't", "didn't", "won't", "wasn't", "hardly", "without",
                     "cannot", "can't", "n't"),
    },
    "cs": {
        "pos": ("dobr*", "skvel*", "vyborn*", "nejlepsi", "doporuc*", "spolehliv*", "pohodln*", "dostupn*", "oblibe*", "kvalitn*",
                "odoln*", "rychl*", "snadn*", "uzitecn*", "ohromuj*", "spokojen*", "perfektn*", "efektivn*", "stabiln*", "lehk*",
                "vyhodn*", "osvedcen*", "pochval*", "ceneny", "ceneni", "pozitivn*", "premiov*", "lepsi"),
        "neg": ("spatn*", "nejhorsi", "pochybn*", "nespolehliv*", "nepohodln*", "drah*", "pomal*", "slozit*", "zklaman*", "zklam*",
                "problem*", "stiznost*", "kritiz*", "nekvalitn*", "krehk*", "slab*", "negativn*", "podvod*", "omezen*", "zastaral*",
                "rizik*", "obav*", "nespokojen*", "vadn*", "selh*", "horsi", "nevyhodn*", "nevyhod*", "nedostat*"),
        "negation": ("ne", "neni", "nikdy", "bez", "nejsou", "nema", "nemaji", "nebyl", "nebyla", "nebylo", "nelze", "ani"),
    },
}
_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?|n't")


def _lex_hit(token: str, entries: Sequence[str]) -> bool:
    for e in entries:
        if e.endswith("*"):
            if token.startswith(e[:-1]):
                return True
        elif token == e:
            return True
    return False


def _sentence_sentiment(folded_sentence: str, lang: str) -> float | None:
    lex = _LEXICON[lang]
    toks = _TOKEN.findall(folded_sentence)
    pos = neg = 0
    for i, tok in enumerate(toks):
        polarity = 1 if _lex_hit(tok, lex["pos"]) else -1 if _lex_hit(tok, lex["neg"]) else 0
        if not polarity:
            continue
        if any(t in lex["negation"] or t.endswith("n't") for t in toks[max(0, i - 3):i]):
            polarity = -polarity
        pos += polarity > 0
        neg += polarity < 0
    return (pos - neg) / (pos + neg) if pos + neg else None


# -- analysis ---------------------------------------------------------------------------
def analyze_answers(records: Sequence[AnswerRecord], brand: str, competitors: Sequence[str] | None = None, *,
                    brand_domains: Sequence[str] | None = None, lang: str = "en",
                    aliases: dict[str, Sequence[str]] | None = None) -> VisibilityReport:
    """Mention rate, citation rate, position, share of voice, sentiment and gaps over collected answers.

    ``lang`` selects the sentiment lexicon ("en" or "cs"; anything else detects it per answer).
    ``aliases`` maps a brand or competitor name to extra spellings (for example Czech inflected forms).
    """
    aliases = aliases or {}
    names = [brand] + [c for c in (competitors or []) if _norm(c) != _norm(brand)]
    patterns = {n: _name_pattern([n, *aliases.get(n, ())]) for n in names}
    domains = {d for d in (_host(x) for x in (brand_domains or [])) if d}

    mentioned = cited = 0
    positions: list[float] = []
    counts = {n: 0 for n in names}
    sentiments: list[float] = []
    engines: dict[str, dict[str, Any]] = {}
    queries: dict[str, dict[str, Any]] = {}

    for rec in records:
        folded = _norm(rec.text)
        per_name = {n: len(p.findall(folded)) for n, p in patterns.items()}
        for n, c in per_name.items():
            counts[n] += c
        is_mention = per_name[brand] > 0
        is_cited = bool(domains) and _cites_domain(rec.cited_urls or [], domains)
        first = patterns[brand].search(folded)
        pos = first.start() / len(folded) if (first and folded) else None
        mentioned += is_mention
        cited += is_cited
        if pos is not None:
            positions.append(pos)
        answer_sent: list[float] = []
        if is_mention:
            code = lang if lang in _LEXICON else detect_lang(rec.text)
            for sentence in split_sentences(rec.text):
                f = _norm(sentence)
                if patterns[brand].search(f):
                    s = _sentence_sentiment(f, code)
                    if s is not None:
                        answer_sent.append(s)
        sentiments += answer_sent

        eng = engines.setdefault(rec.engine, {"n_answers": 0, "mentions": 0, "citations": 0, "positions": [], "sent": []})
        eng["n_answers"] += 1
        eng["mentions"] += is_mention
        eng["citations"] += is_cited
        eng["positions"] += [pos] if pos is not None else []
        eng["sent"] += answer_sent
        key = re.sub(r"\s+", " ", rec.query).strip().lower()
        q = queries.setdefault(key, {"query": rec.query.strip(), "n_answers": 0, "mentions": 0, "citations": 0, "engines": [],
                                     "competitors": {n: 0 for n in names[1:]}, "positions": []})
        q["n_answers"] += 1
        q["mentions"] += is_mention
        q["citations"] += is_cited
        if rec.engine not in q["engines"]:
            q["engines"].append(rec.engine)
        for n in names[1:]:
            q["competitors"][n] += per_name[n] > 0
        if pos is not None:
            q["positions"].append(pos)

    n_answers = len(records)
    total_mentions = sum(counts.values())
    share = {n: (counts[n] / total_mentions if total_mentions else 0.0) for n in names}

    def avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 4) if values else None

    per_engine = {
        e: {"n_answers": v["n_answers"], "mention_rate": round(v["mentions"] / v["n_answers"], 4),
            "citation_rate": round(v["citations"] / v["n_answers"], 4), "avg_first_mention_position": avg(v["positions"]),
            "sentiment": round(sum(v["sent"]) / len(v["sent"]), 4) if v["sent"] else 0.0}
        for e, v in engines.items()
    }
    per_query = []
    gaps = []
    for q in queries.values():
        rivals = {n: c for n, c in q["competitors"].items() if c}
        per_query.append({
            "query": q["query"], "n_answers": q["n_answers"], "engines": q["engines"],
            "mentioned": q["mentions"], "mention_rate": round(q["mentions"] / q["n_answers"], 4),
            "cited": q["citations"], "citation_rate": round(q["citations"] / q["n_answers"], 4),
            "competitors_named": rivals, "avg_first_mention_position": avg(q["positions"]),
        })
        if rivals and q["mentions"] == 0:
            gaps.append(q["query"])
    return VisibilityReport(
        brand=brand, n_answers=n_answers, mention_rate=round(mentioned / n_answers, 4) if n_answers else 0.0,
        citation_rate=round(cited / n_answers, 4) if n_answers else 0.0, avg_first_mention_position=avg(positions),
        share_of_voice={n: round(v, 4) for n, v in share.items()}, sentiment=round(sum(sentiments) / len(sentiments), 4) if sentiments else 0.0,
        per_engine=per_engine, per_query=per_query, gaps=gaps,
    )


# -- buyer questions --------------------------------------------------------------------
# English templates avoid number agreement ("What is running shoes?"); Czech queries are keyword style, so
# they read naturally with a nominative topic whatever its number or gender.
_QUERIES = {
    "en": ["What should I know about {topic}?", "Best {topic} for {audience}", "How do I choose {topic}?",
           "{brand} vs alternatives", "How much should I pay for {topic}?", "{brand} reviews", "Is {brand} worth it?",
           "What are the alternatives to {brand}?", "Is it worth investing in {topic}?", "What are the pros and cons of {topic}?",
           "What should I look for in {topic}?", "Which {topic} do experts recommend?", "What mistakes do people make with {topic}?",
           "How do I get started with {topic}?", "Who should use {topic}?", "{brand} pricing", "Is {brand} trustworthy?",
           "{topic} buying guide", "{topic} for beginners vs experts", "Best {topic} under a tight budget"],
    "cs": ["{topic} co to je", "nejlepší {topic}", "{topic} jak vybrat", "{brand} vs alternativy", "{topic} cena", "{brand} recenze",
           "{brand} zkušenosti", "alternativy k {brand}", "vyplatí se {topic}", "{topic} výhody a nevýhody",
           "{topic} na co si dát pozor", "{topic} srovnání", "{topic} test", "{topic} pro koho se hodí", "{topic} jak začít",
           "{topic} doporučení odborníků", "{brand} ceník", "{brand} hodnocení", "{topic} nejčastější chyby",
           "{topic} levně a kvalitně"],
}
_QUERIES_CS_FORMS = {"acc": "jak vybrat {acc}", "gen": "výhody a nevýhody {gen}"}


def suggest_queries(brief: Brief, n: int = 15) -> list[str]:
    """Questions buyers ask answer engines about the topic, in the brief language (most useful first)."""
    lang = norm_lang(brief.lang)
    ctx = {"topic": brief.topic.strip(), "brand": brief.brand.strip(), "audience": brief.audience.strip()}
    out: list[str] = []
    for template in _QUERIES[lang]:
        out.append(template.format(**ctx))
    if lang == "cs":                                      # real case forms make the Czech phrasing natural
        if brief.topic_forms.get("acc"):
            out[2] = _QUERIES_CS_FORMS["acc"].format(acc=brief.topic_forms["acc"])
        if brief.topic_forms.get("gen"):
            out[9] = _QUERIES_CS_FORMS["gen"].format(gen=brief.topic_forms["gen"])
    kw = (brief.keyword or "").strip()
    if kw and kw.lower() != brief.topic.strip().lower():
        extra = [f"Best {kw}", f"{kw} price", f"How to choose {kw}"] if lang == "en" else [f"nejlepší {kw}", f"{kw} cena", f"{kw} jak vybrat"]
        out[3:3] = extra[:1]
        out += extra[1:]
    seen: set[str] = set()
    unique = []
    for q in out:
        if q.lower() not in seen:
            seen.add(q.lower())
            unique.append(q)
    return unique[: max(0, n)]
