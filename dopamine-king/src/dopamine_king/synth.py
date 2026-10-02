"""Synthetic demo corpus with PLANTED effects.

Real scraped data cannot be shipped in the repository (copyright, and engagement numbers are not
public), and we never attribute invented numbers to real brands. This generator builds a fully
synthetic corpus of fictional brands whose engagement depends on known, planted hook features.
That makes the analysis stack testable (can it recover the planted effects?) and gives the demo
and the game realistic material. Everything it creates is flagged ``synthetic=True``.
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import Any

from .models import Brand, ContentItem
from .store import Store

# Effect of each construction flag on content quality q (log scale).
PLANTED_EFFECTS: dict[str, float] = {
    "number": 0.30, "question": 0.10, "curiosity": 0.35, "contrast": 0.20, "emotion": 0.15,
    "second": 0.15, "practical": 0.22, "social": 0.05, "clickbait": -0.30, "boring": -0.40, "long": -0.30,
}

# (template, flags). {t} topic, {N} number; Czech also {a} accusative, {g} genitive, {l} locative.
EN_TEMPLATES: list[tuple[str, tuple[str, ...]]] = [
    ("{N} ways to get more out of {t}", ("number", "practical")),
    ("{N} tips for better {t}", ("number", "practical")),
    ("{N} {t} templates you can copy today", ("number", "practical", "second")),
    ("{N} {t} mistakes that quietly cost you results", ("number", "curiosity", "second")),
    ("{N} things top performers do differently with {t}", ("number", "social")),
    ("Is {t} worth the money?", ("question",)),
    ("Should you rethink {t} this year?", ("question", "second")),
    ("What nobody tells you about {t}", ("curiosity", "second")),
    ("The hidden truth about {t}", ("curiosity",)),
    ("Why most {t} advice falls flat", ("curiosity", "contrast")),
    ("Stop doing {t} the hard way", ("contrast",)),
    ("{t} myths we need to retire", ("contrast",)),
    ("Why {t} advice is usually wrong", ("contrast",)),
    ("The incredible story behind {t}", ("emotion",)),
    ("We are obsessed with {t}", ("emotion",)),
    ("{t} that people absolutely love", ("emotion",)),
    ("Your {t} questions, answered", ("second",)),
    ("Everything you need for {t}", ("second",)),
    ("How to start with {t}", ("practical",)),
    ("A beginner guide to {t}", ("practical",)),
    ("{t}: a practical playbook", ("practical",)),
    ("Why founders and experts choose {t}", ("social",)),
    ("Our Q3 {t} update", ("boring",)),
    ("Introducing our new {t} range", ("boring",)),
    ("{t} news and announcements", ("boring",)),
    ("Company update: {t}", ("boring",)),
    ("A message from our CEO on {t}", ("boring",)),
    ("You won't believe what happened with {t}!!!", ("clickbait",)),
    ("This one trick changes everything about {t}", ("clickbait",)),
    ("Shocking {t} secrets revealed!!!", ("clickbait", "curiosity")),
]
CS_TEMPLATES: list[tuple[str, tuple[str, ...]]] = [
    ("{N} tipů, jak vylepšit {a}", ("number", "practical")),
    ("{N} chyb, které děláte u {g}", ("number", "curiosity")),
    ("{N} věcí, které dělají špičky kolem {g}", ("number", "social")),
    ("Vyplatí se {t}?", ("question",)),
    ("Pravda o {l}", ("curiosity",)),
    ("Skrytá pravda o {l}", ("curiosity",)),
    ("Přestaňte dělat {a} špatně", ("contrast",)),
    ("Mýty o {l}, kterým nesmíte věřit", ("contrast",)),
    ("Neuvěřitelný příběh: {t}", ("emotion",)),
    ("Milujeme {a}", ("emotion",)),
    ("Váš průvodce: {t}", ("second", "practical")),
    ("Jak na {a}", ("practical",)),
    ("Průvodce pro začátečníky: {t}", ("practical",)),
    ("Naše novinky: {t} ve třetím čtvrtletí", ("boring",)),
    ("Představujeme naši novou nabídku: {t}", ("boring",)),
    ("Aktuality: {t}", ("boring",)),
    ("Šokující tajemství: {t}!!!", ("clickbait", "curiosity")),
]

TOPICS_EN: dict[str, list[str]] = {
    "sport": ["running shoes", "marathon training", "recovery", "strength training", "cycling", "yoga"],
    "food-beverage": ["cold brew", "meal prep", "plant-based dinners", "sourdough", "smoothies", "coffee at home"],
    "b2b-saas": ["CRM", "email automation", "customer onboarding", "sales forecasting", "churn", "product analytics"],
    "finance": ["saving", "budgeting", "index funds", "credit cards", "mortgage rates", "emergency funds"],
    "travel": ["weekend trips", "packing", "budget flights", "city breaks", "road trips", "hotel deals"],
    "gaming": ["co-op games", "speedrunning", "indie releases", "game settings", "controllers", "esports"],
    "home-living": ["small apartments", "smart lighting", "plants at home", "decluttering", "sleep setups", "home office"],
}
TOPICS_CS: list[dict[str, str]] = [
    {"t": "domácí káva", "g": "domácí kávy", "a": "domácí kávu", "l": "domácí kávě"},
    {"t": "běžecké boty", "g": "běžeckých bot", "a": "běžecké boty", "l": "běžeckých botách"},
    {"t": "online nakupování", "g": "online nakupování", "a": "online nakupování", "l": "online nakupování"},
    {"t": "cestování po Česku", "g": "cestování po Česku", "a": "cestování po Česku", "l": "cestování po Česku"},
    {"t": "chytrá domácnost", "g": "chytré domácnosti", "a": "chytrou domácnost", "l": "chytré domácnosti"},
    {"t": "osobní rozpočet", "g": "osobního rozpočtu", "a": "osobní rozpočet", "l": "osobním rozpočtu"},
]

BRANDS: dict[str, list[str]] = {
    "sport": ["Zorvia Running", "Peakline Cycling", "Kinetiq Gear"],
    "food-beverage": ["Kettle and Crumb", "Brewmoor Coffee", "Greenfork Meals"],
    "b2b-saas": ["Quillo CRM", "Mailorbit", "Onboardly"],
    "finance": ["Lumen Bank", "Penny Harbor", "Coinharbor"],
    "travel": ["Voyago", "Tripnest", "Skyhopper"],
    "gaming": ["Pixelforge Games", "Questloop", "Arcadium"],
    "home-living": ["Verdant Home", "Lumiline", "Nesta Living"],
    "cz-local": ["Hrnek a Hvězda", "Šlapka", "Domovník", "Spořílek"],
}
PLATFORMS_BY_COHORT: dict[str, list[tuple[str, str]]] = {
    "sport": [("instagram", "post"), ("youtube", "video")],
    "food-beverage": [("instagram", "post"), ("blog", "article")],
    "b2b-saas": [("linkedin", "post"), ("blog", "article")],
    "finance": [("linkedin", "post"), ("x", "post")],
    "travel": [("instagram", "post"), ("youtube", "video")],
    "gaming": [("youtube", "video"), ("x", "post")],
    "home-living": [("instagram", "post"), ("blog", "article")],
    "cz-local": [("instagram", "post"), ("blog", "article")],
}
LONG_TAIL = " in a way that works for teams of every size across every industry and every single region of the world"
LONG_TAIL_CS = " tak, aby to fungovalo pro týmy všech velikostí napříč všemi obory a ve všech regionech celého světa"


def _slug(name: str) -> str:
    import unicodedata
    folded = "".join(c for c in unicodedata.normalize("NFD", name) if not unicodedata.combining(c))
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in folded).strip("-").replace("--", "-")


def _poisson(rng: random.Random, lam: float) -> int:
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    limit, k, prod = math.exp(-lam), 0, 1.0
    while True:
        prod *= rng.random()
        if prod <= limit:
            return k
        k += 1


def _build_title(rng: random.Random, cohort: str, topics_en: dict[str, list[str]] | None = None,
                 topics_cs: list[dict[str, str]] | None = None, cs_cohorts: frozenset[str] = frozenset({"cz-local"}),
                 style: dict[str, Any] | None = None) -> tuple[str, tuple[str, ...], str]:
    style = style or {}
    czech = cohort in cs_cohorts
    templates = [(t, tuple(f)) for t, f in style.get("templates_cs", [])] or CS_TEMPLATES if czech \
        else [(t, tuple(f)) for t, f in style.get("templates_en", [])] or EN_TEMPLATES
    template, flags = rng.choice(templates)
    flags = tuple(flags)
    number = rng.choice([3, 4, 5, 6, 7, 8, 9, 10, 12, 15, 21])
    if czech:
        forms = rng.choice(topics_cs or TOPICS_CS)
        title = template.format(N=number, **forms)
    else:
        topic = rng.choice((topics_en or TOPICS_EN)[cohort])
        title = template.format(N=number, t=topic if not template.startswith("{t}") else topic.capitalize())
    if rng.random() < 0.12 and "clickbait" not in flags:
        title += style.get("long_tail_cs", LONG_TAIL_CS) if czech else style.get("long_tail_en", LONG_TAIL)
        flags = flags + ("long",)
    return title[0].upper() + title[1:], flags, "cs" if czech else "en"


def generate_corpus(
    seed: int = 7, items_per_brand: int = 40, today: str = "2026-09-01", config: dict[str, Any] | None = None,
) -> tuple[list[Brand], list[ContentItem]]:
    """The demo corpus. ``config`` (a vertical's ``synth.json``) swaps in its own fictional brands and topics."""
    rng = random.Random(seed)
    end = date.fromisoformat(today)
    brands: list[Brand] = []
    items: list[ContentItem] = []
    brand_names = config["brands"] if config else BRANDS
    platforms_by_cohort = {k: [tuple(p) for p in v] for k, v in config["platforms"].items()} if config else PLATFORMS_BY_COHORT
    topics_en = config["topics_en"] if config else None
    topics_cs = config["topics_cs"] if config else None
    cs_cohorts = frozenset(config.get("cs_cohorts", [])) if config else frozenset({"cz-local"})
    countries = config.get("country", {}) if config else {"cz-local": "CZ"}
    cohort_base = {c: rng.gauss(0, 0.4) for c in brand_names}
    counter = 0
    for cohort, names in brand_names.items():
        platforms = platforms_by_cohort[cohort]
        for name in names:
            brand = Brand(
                id=f"syn-{_slug(name)}", name=name, cohort=cohort, country=countries.get(cohort),
                homepage=None, verified=False, synthetic=True,
            )
            brands.append(brand)
            reach = rng.gauss(0, 0.8)
            quality_bias = rng.gauss(0, 0.2)
            for _ in range(items_per_brand):
                platform, fmt = rng.choice(platforms)
                title, flags, lang = _build_title(rng, cohort, topics_en, topics_cs, cs_cohorts, config)
                q = sum(PLANTED_EFFECTS[f] for f in flags) + quality_bias + rng.gauss(0, 0.30)
                exposure = math.exp(cohort_base[cohort] + reach + (0.4 if platform == "youtube" else 0.0))
                views = max(50.0, 800.0 * exposure * math.exp(0.5 * q + 0.3 * rng.gauss(0, 1)))
                signals: dict[str, float] = {}
                like_rate = 0.03 * math.exp(0.9 * q + 0.4 * rng.gauss(0, 1))
                comment_rate = 0.004 * math.exp(0.7 * q + 0.6 * rng.gauss(0, 1))
                share_rate = 0.006 * math.exp(1.1 * q + 0.6 * rng.gauss(0, 1))
                save_rate = 0.008 * math.exp(1.0 * q + 0.6 * rng.gauss(0, 1))
                denom_key = "impressions" if platform in ("linkedin", "x") else "views"
                signals[denom_key] = float(round(views))
                signals["likes"] = float(_poisson(rng, views * min(like_rate, 0.5)))
                signals["comments"] = float(_poisson(rng, views * min(comment_rate, 0.2)))
                if platform in ("linkedin", "x", "instagram"):
                    signals["shares"] = float(_poisson(rng, views * min(share_rate, 0.2)))
                if platform == "instagram":
                    signals["saves"] = float(_poisson(rng, views * min(save_rate, 0.2)))
                if platform == "youtube":
                    signals["watch_time"] = round(min(0.95, max(0.05, 0.38 * math.exp(0.35 * q + 0.2 * rng.gauss(0, 1)))), 4)
                counter += 1
                published = end - timedelta(days=rng.randrange(0, 365))
                items.append(ContentItem(
                    id=f"syn-{counter:05d}", brand_id=brand.id, platform=platform, format=fmt, title=title,
                    url=None, excerpt="", lang=lang, published_at=f"{published.isoformat()}T09:00:00+00:00",
                    word_count=None, signals=signals, synthetic=True,
                    meta={"planted_flags": list(flags), "planted_quality": round(q, 4), "source": "synthetic"},
                ))
    return brands, items


def populate_store(store: Store, **kwargs: Any) -> tuple[int, int]:
    """Create the synthetic corpus in a store. Returns (brands, items)."""
    brands, items = generate_corpus(**kwargs)
    for b in brands:
        store.upsert_brand(b)
    for it in items:
        store.upsert_item(it)
    return len(brands), len(items)
