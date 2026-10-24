"""The real edition of the game: one data bundle built only from stored web searches, the evidence ledger and the brand file.

Nothing in it is simulated. What the player guesses in the Arena is an outcome that was measured or computed from real material: the
position of a link in a stored search, how many of the market searches showed a site, or what the claims check says about a real page
title. The Boss Battle rivals are real page titles, the benchmark is the Dopamine Score of real titles, the cards are the verified
studies of the ledger and what the searches showed. The game code reads the same keys as before (``arena``, ``bosses``, ``benchmarks``,
``loot``...), plus ``real``, ``market``, ``claimbank``, ``tasks`` and ``lab.tests`` for the new views.

Everything is deterministic: the same snapshot gives the same bundle.
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from statistics import median
from typing import Any, Sequence

from ..analysis import compare_hooks, win_probability
from ..analysis.linalg import percentile_rank, quantile
from ..generate.claims import load_profile
from ..generate.guard import severity_of
from ..models import COHORT_LABELS
from ..scoring import detect_lang, fold, load_spec, score_hook
from ..verticals import load_vertical
from ..webdata import DROP_RATES, GENERIC_MYTH_IDS, MYTHS, PITY_AFTER, _vault_from_ledger
from . import analyze as A
from . import emotion
from . import report as R
from .collect import load_plan, load_records

REAL_VERSION = 2
SEED = 23
MARKET_GROUPS = ("brand", "category", "persona", "competitor")      # searches a Czech buyer could make
SITE_GROUP = "brandsite"                                             # searches limited to the site of one brand
RELEVANT_TYPES = {"maker", "media", "pharmacy", "ecommerce", "service", "forum", "foreign_media", "foreign_shop", "science", "reviews", "authority"}
MIN_WORDS, MIN_CHARS, MAX_CHARS = 3, 18, 110
GAP_BANDS = (("easy", 5), ("medium", 3), ("hard", 2))                # a rank gap of at least this many places (next door results are a coin toss)
REACH_BANDS = (("easy", 8), ("medium", 4), ("hard", 2))              # a difference of at least this many searches (one search is a coin toss)
QUOTAS = {"easy": 0.30, "medium": 0.40, "hard": 0.30}
UPSET_MIN_GAP = 8.0                                                   # Dopamine Score points the model must be ahead to count as confident
SCORE_TIE = 2.0
MAX_USES = 3                                                          # one title or site appears in at most this many duels
LOGIT_SCALE = 12.0
TASK_XP = 50
COHORTS = {
    "real-market": {"en": "Results of the Czech market searches", "cs": "Výsledky hledání na českém trhu"},
    "real-brands": {"en": "Pages of leading red light brands", "cs": "Stránky předních značek červeného světla"},
}
CLAIM_DIFFICULTY = {"CLAIM_MEDICAL": "easy", "DISEASE_MENTION": "easy", "STATUS_CLAIM": "hard"}
STOP = frozenset("a an the for of and or to in on is are how what why with your you do does vs v s na pro ve se je jak co".split())


# -- titles ------------------------------------------------------------------------------------------------------------------
def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text.lower()))


def norm_title(text: str) -> str:
    return " ".join(tokens(text))


def derived_from_address(title: str, url: str) -> bool:
    """True when the "title" is just the words of the address (the search tool had no page title): such a text is not a hook."""
    t, s = tokens(title), tokens(A.slug_label(url))
    if not t or not s:
        return False
    t, s = (t[1:] if t[0].isdigit() else t), (s[1:] if s[0].isdigit() else s)
    return t == s or (len(t) >= 4 and t == s[:len(t)]) or (len(s) >= 4 and s == t[:len(s)])


def looks_like_code(title: str) -> bool:
    words = re.findall(r"[A-Za-z0-9]+", title)
    if not words:
        return True
    hexish = [w for w in words if re.fullmatch(r"[0-9a-f]{4,}", w.lower()) and re.search(r"\d", w)]
    digits = [w for w in words if re.search(r"\d", w)]
    return len(hexish) >= 2 or (len(digits) >= 3 and len(digits) >= len(words) / 2)


def host_kind(link: dict[str, Any], cfg: dict[str, Any]) -> dict[str, Any]:
    return A.domain_info(A.host_of(link["url"]), cfg["domains"])


def readable(link: dict[str, Any], cfg: dict[str, Any]) -> bool:
    """A search result worth showing to a player: a page title, not a file name, a code or an unrelated site."""
    title = link["title"].strip()
    if A.title_is_junk(title, link["url"]) or looks_like_code(title):
        return False
    kind = host_kind(link, cfg).get("type")
    if kind == "noise":
        return False
    if not (len(title.split()) >= MIN_WORDS and MIN_CHARS <= len(title) <= MAX_CHARS):
        return False
    return kind in RELEVANT_TYPES or A.is_light_related(title)


def usable_hook(link: dict[str, Any], cfg: dict[str, Any]) -> bool:
    """A readable result whose title the page really has (not words cut from its address): fit for scoring as a hook."""
    return readable(link, cfg) and not derived_from_address(link["title"], link["url"])


@dataclass
class RealTitle:
    record: str
    group: str
    persona: str
    query: str
    retrieved_at: str
    rank: int
    of: int
    title: str
    url: str
    host: str
    host_name: str
    host_type: str
    lang: str
    score: float
    risk: float
    parts: dict[str, float]
    findings: list[dict[str, str]] = field(default_factory=list)
    derived: bool = False

    @property
    def key(self) -> str:
        return f"{self.record}:{self.rank}"

    @property
    def errors(self) -> list[dict[str, str]]:
        return [f for f in self.findings if f["severity"] == "error"]

    def side(self) -> dict[str, Any]:
        """What a duel shows about this result."""
        return {"text": self.title, "brand": self.host_name or self.host, "host": self.host, "host_type": self.host_type, "url": self.url,
                "rank": self.rank, "of": self.of, "query": self.query, "record": self.record, "lang": self.lang, "score": round(self.score, 1),
                "derived": self.derived}


def collect_titles(records: Sequence[dict[str, Any]], cfg: dict[str, Any], profile: Any, spec: dict[str, Any], *, groups: Sequence[str],
                   hooks_only: bool = True, own_site: bool = False) -> list[RealTitle]:
    """The readable results of the given search groups in the order the search returned them.

    An open search gives one result per site. A search limited to one site (``own_site``) keeps the pages of that site only, because the
    filter of the search lets other sites through now and then, and a page title only counts when it belongs to the brand it stands for.
    """
    out: list[RealTitle] = []
    for rec in records:
        if rec["group"] not in groups:
            continue
        allowed = rec.get("allowed_domains") or []
        seen_hosts: set[str] = set()
        seen_titles: set[str] = set()
        for link in rec["links"]:
            ok = usable_hook(link, cfg) if hooks_only else readable(link, cfg)
            host = A.host_of(link["url"])
            norm = norm_title(link["title"])
            if not ok or norm in seen_titles or (own_site and allowed and not A.host_matches(host, allowed)) or (not own_site and host in seen_hosts):
                continue
            seen_hosts.add(host)
            seen_titles.add(norm)
            info = A.domain_info(host, cfg["domains"])
            lang = detect_lang(link["title"], spec)
            sc = score_hook(link["title"], lang=lang, spec=spec)
            hits = profile.scan_text(link["title"])
            findings = [{"code": h.code, "severity": severity_of(h.code), "phrase": link["title"][h.start:h.end]} for h in hits]
            out.append(RealTitle(
                record=rec["id"], group=rec["group"], persona=rec.get("persona", ""), query=rec["query"], retrieved_at=rec["retrieved_at"], rank=link["rank"],
                of=len(rec["links"]), title=link["title"].strip(), url=link["url"], host=host, host_name=info.get("name", host), host_type=info.get("type", ""),
                lang=lang, score=sc.total, risk=sc.clickbait_risk, parts=dict(sc.parts), findings=findings,
                derived=derived_from_address(link["title"], link["url"])))
    return out


def unique_titles(titles: Sequence[RealTitle]) -> list[RealTitle]:
    seen: set[str] = set()
    out = []
    for t in titles:
        key = norm_title(t.title)
        if key not in seen:
            seen.add(key)
            out.append(t)
    return out


# -- benchmarks ------------------------------------------------------------------------------------------------------------
def quantiles(values: Sequence[float]) -> list[float]:
    s = sorted(values)
    return [round(quantile(s, i / 100), 3) for i in range(101)]


def benchmark_of(values: Sequence[float]) -> dict[str, Any]:
    s = sorted(values)
    stats = {"n": float(len(s)), "mean": sum(s) / len(s), "p25": quantile(s, 0.25), "p50": quantile(s, 0.5), "p75": quantile(s, 0.75), "p90": quantile(s, 0.9)}
    return {"quantiles": quantiles(s), "stats": {k: round(v, 2) for k, v in stats.items()}}


def build_benchmarks(market: Sequence[RealTitle], brands: Sequence[RealTitle]) -> dict[str, Any]:
    pools = {"real-market": [t.score for t in unique_titles(market)], "real-brands": [t.score for t in unique_titles(brands)]}
    pools["all"] = pools["real-market"] + pools["real-brands"]
    return {k: benchmark_of(v) for k, v in pools.items()}


# -- rank duels -----------------------------------------------------------------------------------------------------------------
def band(value: float, bands: Sequence[tuple[str, int]]) -> str:
    for name, least in bands:
        if value >= least:
            return name
    return bands[-1][0]


def pick_by_quota(pool: list[Any], difficulty_of: Any, n_total: int, rng: random.Random, uses_of: Any) -> list[Any]:
    """Draw from the shuffled pool until each difficulty has its share; an item may be used MAX_USES times."""
    quota = {d: round(n_total * share) for d, share in QUOTAS.items()}
    used: Counter[str] = Counter()
    chosen = []
    pool = pool[:]
    rng.shuffle(pool)
    for cand in pool:
        d = difficulty_of(cand)
        keys = uses_of(cand)
        if quota.get(d, 0) <= 0 or any(used[k] >= MAX_USES for k in keys):
            continue
        quota[d] -= 1
        for k in keys:
            used[k] += 1
        chosen.append(cand)
    return chosen


def rank_pairs(results: Sequence[RealTitle]) -> list[tuple[RealTitle, RealTitle]]:
    """Every pair of results of one search from two different sites, the better placed one first."""
    by_record: dict[str, list[RealTitle]] = defaultdict(list)
    for t in results:
        by_record[t.record].append(t)
    pairs = []
    for rows in by_record.values():
        rows.sort(key=lambda t: t.rank)
        pairs.extend((hi, lo) for hi, lo in combinations(rows, 2) if lo.rank - hi.rank >= GAP_BANDS[-1][1] and hi.host != lo.host)
    return pairs


def position_score(rank: int, of: int) -> float:
    """100 for first place, falling to about 100 / n for the last of n results."""
    return round(100.0 * (of - rank + 1) / max(of, 1), 1)


def model_accuracy(pairs: Sequence[tuple[RealTitle, RealTitle]]) -> dict[str, Any]:
    """How often the Dopamine Score of the two titles points to the better placed one, over every pair, not only the played ones."""
    decided = right = 0
    for hi, lo in pairs:
        if abs(hi.score - lo.score) < SCORE_TIE:
            continue
        decided += 1
        right += hi.score > lo.score
    return {"pairs": len(pairs), "decided": decided, "right": right, "pct": round(100.0 * right / decided, 1) if decided else None, "tie_below": SCORE_TIE}


def build_rank_duels(results: Sequence[RealTitle], rng: random.Random, *, n_pairs: int = 150) -> list[dict[str, Any]]:
    pairs = rank_pairs(results)
    chosen = pick_by_quota(pairs, lambda p: band(p[1].rank - p[0].rank, GAP_BANDS), n_pairs, rng, lambda p: [p[0].key, p[1].key])
    duels = []
    for hi, lo in chosen:
        winner_is_a = rng.random() < 0.5
        a, b = (hi, lo) if winner_is_a else (lo, hi)
        cmp = compare_hooks(a.title, b.title, lang=None, logit_scale=LOGIT_SCALE)
        p_a = win_probability(a.score, b.score, LOGIT_SCALE)
        model_pick_a = a.score > b.score
        confident = abs(a.score - b.score) >= UPSET_MIN_GAP
        a_side, b_side = a.side(), b.side()
        for t, s in ((a, a_side), (b, b_side)):
            s["success"] = position_score(t.rank, t.of)
        duels.append({
            "id": "", "kind": "rank", "difficulty": band(lo.rank - hi.rank, GAP_BANDS), "cohort": "real-market" if hi.group in MARKET_GROUPS else "real-brands",
            "platform": "web", "lang": detect_lang(hi.query), "query": hi.query, "record": hi.record, "retrieved_at": hi.retrieved_at,
            "a": a_side, "b": b_side, "winner": "a" if winner_is_a else "b", "model_p_a": round(p_a, 3),
            "upset": confident and model_pick_a != winner_is_a,
            "reasons_en": cmp.reasons_en, "reasons_cs": cmp.reasons_cs})
    return duels


# -- reach duels ----------------------------------------------------------------------------------------------------------------
@dataclass
class SiteReach:
    host: str
    name: str
    kind: str
    searches: list[str]
    first_url: str
    best_title: str = ""          # a real page title of this site (not words cut from the address), when the searches had one
    best_url: str = ""

    @property
    def count(self) -> int:
        return len(self.searches)


def site_reach(records: Sequence[dict[str, Any]], cfg: dict[str, Any]) -> list[SiteReach]:
    """In how many of the market searches each site appeared (the same site twice in one search counts once)."""
    found: dict[str, dict[str, Any]] = {}
    for rec in records:
        if rec["group"] not in MARKET_GROUPS:
            continue
        for link in rec["links"]:
            host = A.host_of(link["url"])
            info = A.domain_info(host, cfg["domains"])
            if info.get("type") in (None, "noise"):
                continue
            row = found.setdefault(host, {"name": info.get("name", host), "kind": info["type"], "searches": [], "first_url": link["url"], "title": "", "url": ""})
            if rec["id"] not in row["searches"]:
                row["searches"].append(rec["id"])
            if not row["title"] and usable_hook(link, cfg):
                row["title"], row["url"] = link["title"].strip(), link["url"]
    return sorted((SiteReach(h, r["name"], r["kind"], r["searches"], r["first_url"], r["title"], r["url"]) for h, r in found.items()),
                  key=lambda s: (-s.count, s.host))


def build_reach_duels(sites: Sequence[SiteReach], n_searches: int, rng: random.Random, *, n_pairs: int = 80) -> list[dict[str, Any]]:
    pool = [s for s in sites if s.count >= 2]                           # a site seen once says nothing about the market
    pairs = [(x, y) for x, y in combinations(pool, 2) if abs(x.count - y.count) >= REACH_BANDS[-1][1]]
    chosen = pick_by_quota(pairs, lambda p: band(abs(p[0].count - p[1].count), REACH_BANDS), n_pairs, rng, lambda p: [p[0].host, p[1].host])
    duels = []

    def side(s: SiteReach) -> dict[str, Any]:
        return {"text": s.name, "brand": s.host, "host": s.host, "host_type": s.kind, "example": s.best_title, "url": s.best_url or s.first_url, "count": s.count,
                "of": n_searches, "searches": s.searches, "success": round(100.0 * s.count / n_searches, 1)}
    for x, y in chosen:
        hi, lo = (x, y) if x.count > y.count else (y, x)
        winner_is_a = rng.random() < 0.5
        a, b = (hi, lo) if winner_is_a else (lo, hi)
        duels.append({"id": "", "kind": "reach", "difficulty": band(hi.count - lo.count, REACH_BANDS), "cohort": "real-market", "platform": "web", "lang": "cs",
                      "a": side(a), "b": side(b), "winner": "a" if winner_is_a else "b", "upset": False})
    return duels


# -- claim duels ----------------------------------------------------------------------------------------------------------------
def build_claim_duels(titles: Sequence[RealTitle], rng: random.Random, *, per_flagged: int = 3) -> list[dict[str, Any]]:
    """A real title the claims check stops against one it lets through without any remark."""
    pool = unique_titles(titles)
    flagged = [t for t in pool if t.errors]
    clean = [t for t in pool if not t.findings]
    duels = []
    used: Counter[str] = Counter()
    for f in flagged:
        near = [c for c in clean if c.lang == f.lang and c.host != f.host and used[c.key] < MAX_USES
                and abs(len(c.title) - len(f.title)) <= max(12, 0.4 * len(f.title))]
        rng.shuffle(near)
        for c in near[:per_flagged]:
            used[c.key] += 1
            flagged_is_a = rng.random() < 0.5
            a, b = (f, c) if flagged_is_a else (c, f)
            a_side, b_side = a.side(), b.side()
            a_side["findings"], b_side["findings"] = a.findings, b.findings
            a_side["flagged"], b_side["flagged"] = bool(a.errors), bool(b.errors)
            code = f.errors[0]["code"]
            duels.append({"id": "", "kind": "claim", "difficulty": CLAIM_DIFFICULTY.get(code, "medium"), "cohort": "real-brands" if f.group == SITE_GROUP else "real-market",
                          "platform": "web", "lang": f.lang, "a": a_side, "b": b_side, "winner": "a" if flagged_is_a else "b", "upset": False})
    return duels


def number_duels(duels: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    rng.shuffle(duels)
    for i, d in enumerate(duels, 1):
        d["id"] = f"{d['kind']}-{i:03d}"
    return duels


# -- bosses -----------------------------------------------------------------------------------------------------------------------
def tier_of(percentile: float) -> int:
    return 1 if percentile <= 60 else 2 if percentile <= 75 else 3


def boss_target(rival_percentile: float) -> int:
    """The percentile that beats the rival's title: its own percentile rounded up to the next 5, at least 55 and at most 90."""
    return int(min(90, max(55, 5 * -(-rival_percentile // 5))))


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", fold(text.lower()))).strip("-")


def boss_dict(rival: RealTitle, bench: dict[str, Any], *, cohort: str, name: str, brief_en: str, brief_cs: str, boss_id: str) -> dict[str, Any]:
    pct = percentile_rank(sorted(bench[cohort]["quantiles"]), rival.score)
    target = boss_target(pct)
    tier = tier_of(target)
    rival_dict = {k: v for k, v in rival.side().items() if k not in ("success",)}
    rival_dict.update(percentile=round(pct, 1), retrieved_at=rival.retrieved_at)
    return {"id": boss_id, "cohort": cohort, "lang": rival.lang, "name": name, "tier": tier, "percentile": target, "xp": {1: 60, 2: 100, 3: 180}[tier],
            "brief_en": brief_en, "brief_cs": brief_cs, "taunt_en": rival.title, "taunt_cs": rival.title, "rival": rival_dict}


def first_sentence(text: str) -> str:
    """A persona description can carry a working note after its first sentence; the boss brief shows the first sentence only."""
    return re.split(r"(?<=[.!?])\s+", text.strip())[0]


def build_bosses(market: Sequence[RealTitle], brands: Sequence[RealTitle], personas: Sequence[dict[str, Any]], bench: dict[str, Any]) -> list[dict[str, Any]]:
    bosses = []
    taken: set[str] = set()
    for p in personas:
        rows = sorted((t for t in market if t.persona == p["id"] and norm_title(t.title) not in taken), key=lambda t: (t.rank, t.record))
        if not rows:
            continue
        r = rows[0]
        taken.add(norm_title(r.title))
        topic = p["brief"]["topic"]
        bosses.append(boss_dict(
            r, bench, cohort="real-market", name=r.host_name or r.host, boss_id=f"boss-p-{p['id']}-{slug(r.host)}",
            brief_en=f"A page title on the theme \"{topic}\" for this audience: {first_sentence(p['who_en'])[0].lower() + first_sentence(p['who_en'])[1:]} The rival is the best placed real title of the search \"{r.query}\".",
            brief_cs=f"Titulek stránky na téma „{topic}“ pro tuto skupinu: {first_sentence(p['who_cs'])[0].lower() + first_sentence(p['who_cs'])[1:]} Soupeř je nejlépe umístěný skutečný titulek hledání „{r.query}“."))
    first_per_site: dict[str, RealTitle] = {}
    for t in sorted(brands, key=lambda t: (t.record, t.rank)):
        first_per_site.setdefault(t.record, t)
    for rec_id, r in first_per_site.items():
        name = r.host_name or r.host
        bosses.append(boss_dict(
            r, bench, cohort="real-brands", name=name, boss_id=f"boss-b-{slug(r.host)}",
            brief_en=f"A page title for MITO LIGHT that holds its own next to {name} on the search \"{r.query}\". The rival is that site's best placed page.",
            brief_cs=f"Titulek stránky MITO LIGHT, který obstojí vedle webu {name} u hledání „{r.query}“. Soupeř je nejlépe umístěná stránka tohoto webu."))
    return sorted(bosses, key=lambda b: (b["tier"], b["id"]))


# -- loot -------------------------------------------------------------------------------------------------------------------------
GRADE_RARITY = {"A": "epic", "B": "rare", "C": "common", "D": "common"}


DESIGN_LABELS = {
    "meta-analysis": ("meta-analysis", "metaanalýza"), "systematic-review": ("systematic review", "systematický přehled"), "rct": ("randomised trial", "randomizovaná studie"),
    "field-experiment": ("field experiment", "terénní experiment"), "lab-experiment": ("lab experiment", "laboratorní experiment"),
    "observational": ("observational study", "observační studie"), "survey": ("survey", "dotazníkové šetření"), "theory": ("theory", "teorie"),
    "qualitative": ("qualitative study", "kvalitativní studie"), "book": ("book", "kniha"), "preprint": ("preprint", "preprint"), "guideline": ("guideline", "doporučení"),
}


def study_cards(ledger: Any) -> list[dict[str, Any]]:
    """One card per study of the ledger. A study nobody has matched against a public record is never rarer than common."""
    cards = []
    for s in sorted(ledger.studies, key=lambda s: s.id):
        rarity = GRADE_RARITY.get(s.grade or "C", "common")
        if s.design in ("meta-analysis", "systematic-review"):
            rarity = "legendary" if s.grade == "A" else "epic"
        if not s.verified:
            rarity = "common"
        design_en, design_cs = DESIGN_LABELS.get(s.design, ("design unknown", "typ neznámý"))
        first = (s.authors[0].split(",")[0] if s.authors else "")
        label = f"{first} ({s.year})" if first and s.year else s.title[:60]
        where = ", ".join(x for x in (s.venue, str(s.year) if s.year else "") if x)
        state_en = "Verified: title, journal and year were found in a public source." if s.verified else "Not verified yet: no public source confirmed title, journal and year."
        state_cs = "Ověřeno: název, časopis a rok se našly ve veřejném zdroji." if s.verified else "Zatím neověřeno: žádný veřejný zdroj nepotvrdil název, časopis a rok."
        cards.append({"id": f"study-{s.id}", "kind": "study", "rarity": rarity, "demo": False, "url": s.url or (f"https://doi.org/{s.doi}" if s.doi else ""),
                      "verified": bool(s.verified),
                      "title_en": label, "title_cs": label,
                      "body_en": f"{s.title}. {where}. Design: {design_en}, grade {s.grade}. {state_en}",
                      "body_cs": f"{s.title}. {where}. Typ studie: {design_cs}, hodnocení {s.grade}. {state_cs}"})
    return cards


def market_cards(titles: Sequence[RealTitle], n_searches: int, reach: Sequence[SiteReach], findings: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the searches showed, as cards: the findings of the market view and a few counts anyone can check in the stored results."""
    def card(cid: str, rarity: str, title_en: str, title_cs: str, body_en: str, body_cs: str) -> dict[str, Any]:
        return {"id": cid, "kind": "market", "rarity": rarity, "demo": False, "url": "", "title_en": title_en, "title_cs": title_cs, "body_en": body_en, "body_cs": body_cs}

    rarity_of = {"viditelnost": "epic", "identita": "epic"}
    cards = [card(f"market-{f['id']}", rarity_of.get(f["id"], "rare"), f["title"], f["title"], f"{f['text']} Upozornění: {f['caveat']}", f"{f['text']} Upozornění: {f['caveat']}")
             for f in findings]
    if reach:
        top = reach[0]
        one = sum(1 for s in reach if s.count == 1)
        cards.append(card("market-top-site", "common", f"{top.name} shows up most often", f"Nejčastěji se objevuje {top.name}",
                          f"{top.name} appeared in {top.count} of {n_searches} market searches, more than any other site.",
                          f"{top.name} se objevil ve {top.count} z {n_searches} hledání na trhu, víc než kterýkoli jiný web."))
        cards.append(card("market-long-tail", "common", "Most sites show up once", "Většina webů se objeví jen jednou",
                          f"Of {len(reach)} sites in the market searches, {one} appeared in a single search only.",
                          f"V hledáních na trhu se objevilo {len(reach)} webů. {one} z nich se objevilo jen v jediném hledání."))
    if titles:
        words = [len(t.title.split()) for t in titles]
        questions = sum(1 for t in titles if t.title.rstrip().endswith("?"))
        numbers = sum(1 for t in titles if re.search(r"\d", t.title))
        cards.append(card("market-title-length", "common", "How long a page title is", "Jak dlouhý je titulek stránky",
                          f"The median real title has {int(median(words))} words ({len(words)} titles of the market searches).",
                          f"Typický skutečný titulek (medián) má {int(median(words))} slov. Počítáno ze {len(words)} titulků z hledání na trhu."))
        cards.append(card("market-questions-numbers", "rare", "Questions and numbers in titles", "Otázky a čísla v titulcích",
                          f"Of {len(titles)} real titles, {questions} are questions and {numbers} contain a digit.",
                          f"Z {len(titles)} skutečných titulků je {questions} otázek a {numbers} obsahuje číslici."))
    return cards


def tip_cards(spec: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for key, msg in spec["messages"].items():
        if key in ("ship_it", "keep_promise"):
            continue
        out.append({"id": f"tip-{key}", "kind": "tip", "rarity": "common", "demo": False, "title_en": "Hook hygiene", "title_cs": "Hygiena hooku",
                    "body_en": msg["en"], "body_cs": msg["cs"]})
    return out


# -- the rest -----------------------------------------------------------------------------------------------------------------------
def build_tasks(actions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": a["id"], "title": a["title"], "why": a["why"], "steps": list(a["steps"]), "finding": a.get("finding", ""), "xp": TASK_XP} for a in actions]


def build_lab_tests(tests: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": f"test-{i}", "a_id": t["a"], "b_id": t["b"], "a": t["a_text"], "b": t["b_text"], "hypothesis_cs": t["hypothesis_cs"]} for i, t in enumerate(tests, 1)]


def build_market(report: dict[str, Any]) -> dict[str, Any]:
    keep = ("brand", "meta", "findings", "visibility", "landscape", "identity", "brandsites", "own", "own_titles", "claims_audit", "science", "open_items",
            "validation", "queries", "direct")
    return {k: report[k] for k in keep}


def draft_packs(drafts_dir: Path) -> list[dict[str, Any]]:
    """The reviewed drafts of the radar as Forge packs, each marked with what the radar says about it."""
    index = json.loads((drafts_dir / "index.json").read_text("utf-8"))
    packs = []
    for row in index:
        pack = json.loads((drafts_dir / row["id"] / "pack.json").read_text("utf-8"))
        pack["draft"] = {k: row[k] for k in ("id", "kind", "action", "title", "persona", "needs_approval", "verdict", "errors", "warnings", "open_slots")}
        packs.append(pack)
    return packs


def build_real_bundle(snapshot: str | Path, drafts: str | Path, plan_path: str | Path, *, vertical: str = "pbm") -> dict[str, Any]:
    from ..webdata import demo_samples

    snapshot, drafts, plan_path = Path(snapshot), Path(drafts), Path(plan_path)
    root = plan_path.resolve().parent
    plan = load_plan(plan_path)
    records = load_records(snapshot, plan)
    vert = load_vertical(vertical)
    ledger = vert.ledger()
    spec = load_spec()
    cfg = A.load_config(root, json.loads((vert.path / "brands.json").read_text("utf-8")))
    profile = load_profile(vertical, "wellness")
    personas = vert.personas()
    rng = random.Random(SEED)

    market = collect_titles(records, cfg, profile, spec, groups=MARKET_GROUPS)
    sites = collect_titles(records, cfg, profile, spec, groups=(SITE_GROUP,), own_site=True)
    results = collect_titles(records, cfg, profile, spec, groups=MARKET_GROUPS, hooks_only=False)
    bench = build_benchmarks(market, sites)
    pairs = rank_pairs(results)
    reach = site_reach(records, cfg)
    n_market_searches = sum(1 for r in records if r["group"] in MARKET_GROUPS)

    rank = build_rank_duels(results, rng)
    reach_duels = build_reach_duels(reach, n_market_searches, rng)
    claim = build_claim_duels(unique_titles(market + sites), rng)
    arena = number_duels(rank + reach_duels + claim, rng)

    report = R.report_data(snapshot, drafts, plan_path)
    claimbank = emotion.section_data(emotion.load(root / "claims_emotional.json"), vert, ledger, personas)
    vault, ledger_cards = _vault_from_ledger(ledger)
    del ledger_cards
    cards = study_cards(ledger) + market_cards(unique_titles(market), n_market_searches, reach, report["findings"]) + tip_cards(spec)
    manifest = json.loads((snapshot / "snapshot.json").read_text("utf-8"))
    forge = draft_packs(drafts)
    _, guru_samples = demo_samples(ledger, vert)

    real = {
        "snapshot": manifest["last_retrieved_at"][:10], "first": manifest["first_retrieved_at"], "last": manifest["last_retrieved_at"], "tool": R.tool_label(manifest["tool"]),
        "searches": len(records), "market_searches": n_market_searches, "links": sum(len(r["links"]) for r in records),
        "sites": len({A.host_of(l["url"]) for r in records for l in r["links"]}), "titles": {"market": len(unique_titles(market)), "brands": len(unique_titles(sites))},
        "duels": dict(Counter(d["kind"] for d in arena)), "model": model_accuracy(pairs), "task_xp": TASK_XP,
        "claim_titles": {"flagged": sum(1 for t in unique_titles(market + sites) if t.errors), "clean": sum(1 for t in unique_titles(market + sites) if not t.findings)},
    }
    weights = spec["params"]["weights"]
    return {
        "meta": {"version": REAL_VERSION, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "synthetic": False, "edition": "real", "vertical": vertical,
                 "default_lang": "cs",
                 "corpus": {"brands": real["sites"], "items": real["links"]}, "real": real,
                 "note": "Every number in this bundle comes from stored web searches, the verified evidence ledger or the brand file. Nothing is simulated."},
        "spec": spec,
        "calibration": {"weights": dict(weights), "logit_scale": LOGIT_SCALE, "fitted": False,
                        "note": "Not fitted: there is no engagement data. The weights are the ones of the scoring spec."},
        "vertical": vert.public_meta(),
        "claims": {"classes": vert.claims()["classes"], "topics": vert.claim_map(ledger)},
        "claim_rules": vert.claim_rules(),
        "cohort_labels": {**COHORT_LABELS, **COHORTS},
        "benchmarks": bench,
        "arena": arena,
        "bosses": build_bosses(market, sites, personas, bench),
        "patterns": [],
        "myths": vert.myths() + [m for m in MYTHS if m["id"] in GENERIC_MYTH_IDS],
        "lab": {"scenarios": [], "tests": build_lab_tests(claimbank["tests"])},
        "vault": vault,
        "loot": {"cards": cards, "rates": DROP_RATES, "pity_after": PITY_AFTER},
        "forge_samples": forge,
        "guru_sample": guru_samples[0] if guru_samples else None,
        "guru_samples": guru_samples,
        "tasks": build_tasks(report["actions"]),
        "market": build_market(report),
        "claimbank": claimbank,
    }
