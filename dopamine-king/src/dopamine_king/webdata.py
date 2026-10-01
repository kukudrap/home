"""Data bundle for the game UI.

Everything the static game needs, precomputed by the Python engine: the shared scoring spec (so the
JavaScript scorer is identical), Arena duels, Boss Battle scenarios, per-cohort score distributions,
mined patterns, the evidence vault and a loot table with published drop rates. In demo mode all
engagement numbers come from the synthetic corpus and the UI labels them SIMULATED.
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from typing import Any

from .analysis import Benchmark, ItemAnalysis, analyze_items, calibrate_weights, compare_hooks, mine_patterns, win_probability
from .analysis.linalg import quantile
from .models import COHORT_LABELS
from .scoring import load_spec
from .synth import generate_corpus

BUNDLE_VERSION = 1

BOSSES = [
    {"id": "boss-goblin", "cohort": "sport", "lang": "en", "name": "The Scroll Goblin", "tier": 1, "percentile": 60, "xp": 60,
     "brief_en": "Launch post for a lightweight running shoe aimed at beginners.",
     "brief_cs": "Příspěvek k uvedení lehké běžecké boty pro začátečníky.",
     "taunt_en": "Nobody reads launch posts. Prove me wrong.", "taunt_cs": "Launch příspěvky nikdo nečte. Dokaž opak."},
    {"id": "boss-cliche", "cohort": "b2b-saas", "lang": "en", "name": "Captain Cliche", "tier": 2, "percentile": 75, "xp": 100,
     "brief_en": "Webinar invitation: cut churn with better onboarding emails.",
     "brief_cs": "Pozvánka na webinář: snižte odchody zákazníků lepším onboardingem.",
     "taunt_en": "Unlock your potential and leverage synergies!", "taunt_cs": "Odemkněte svůj potenciál a využijte synergie!"},
    {"id": "boss-meh", "cohort": "food-beverage", "lang": "en", "name": "Mr. Meh", "tier": 1, "percentile": 60, "xp": 60,
     "brief_en": "Teaser for a new cold brew flavour.",
     "brief_cs": "Upoutávka na novou příchuť cold brew.",
     "taunt_en": "It is just coffee.", "taunt_cs": "Je to jen káva."},
    {"id": "boss-hydra", "cohort": "finance", "lang": "en", "name": "The Algorithm Hydra", "tier": 3, "percentile": 90, "xp": 180,
     "brief_en": "Savings account: an emergency fund challenge for people who never save.",
     "brief_cs": "Spořicí účet: výzva k nouzové rezervě pro lidi, kteří nikdy nešetří.",
     "taunt_en": "Cut off one hook, two more appear.", "taunt_cs": "Utneš jeden hook, narostou dva."},
    {"id": "boss-nomad", "cohort": "travel", "lang": "en", "name": "The Tab Nomad", "tier": 2, "percentile": 75, "xp": 100,
     "brief_en": "Weekend city break deal for first-time visitors.",
     "brief_cs": "Nabídka víkendového pobytu ve městě pro první návštěvníky.",
     "taunt_en": "Fifty open tabs and not one booking.", "taunt_cs": "Padesát otevřených panelů a žádná rezervace."},
    {"id": "boss-lagbot", "cohort": "gaming", "lang": "en", "name": "Lagbot 3000", "tier": 2, "percentile": 75, "xp": 100,
     "brief_en": "Headline for a co-op update trailer.",
     "brief_cs": "Titulek k traileru kooperativní aktualizace.",
     "taunt_en": "Skip trailer. Skip trailer. Skip.", "taunt_cs": "Přeskočit trailer. Přeskočit. Přeskočit."},
    {"id": "boss-kafe", "cohort": "cz-local", "lang": "cs", "name": "Pan Nuda", "tier": 1, "percentile": 60, "xp": 60,
     "brief_en": "Czech roastery: promote home coffee for people who only drink instant.",
     "brief_cs": "Česká pražírna: propagujte domácí kávu lidem, kteří pijí jen instantní.",
     "taunt_en": "Instant is fine.", "taunt_cs": "Instantní je v pohodě."},
    {"id": "boss-chytry", "cohort": "cz-local", "lang": "cs", "name": "Lord Průměr", "tier": 3, "percentile": 90, "xp": 180,
     "brief_en": "Czech smart home brand: spring promotion for flat owners.",
     "brief_cs": "Česká značka chytré domácnosti: jarní akce pro majitele bytů.",
     "taunt_en": "Average is safe.", "taunt_cs": "Průměr je bezpečný."},
]

MYTHS = [
    {"id": "m-dopamine", "answer": "myth", "ref": "Berridge and Robinson, 1998; Schultz et al., 1997",
     "en": "Dopamine is the brain's pleasure chemical.", "cs": "Dopamin je mozková látka slasti.",
     "why_en": "Dopamine is better tied to wanting, anticipation and prediction errors than to enjoyment itself. That is why a good hook creates anticipation and then delivers.",
     "why_cs": "Dopamin souvisí spíš s chtěním, očekáváním a chybou predikce než s požitkem samotným. Proto dobrý hook vytvoří očekávání a pak ho splní."},
    {"id": "m-peeking", "answer": "myth", "ref": "Johari et al., 2017",
     "en": "Checking an A/B test every hour and stopping at the first p below 0.05 is fine.", "cs": "Kontrolovat A/B test každou hodinu a zastavit ho při první hodnotě p pod 0,05 je v pořádku.",
     "why_en": "Continuous peeking inflates false positives far above the nominal 5 percent. Fix the sample size in advance or use a sequential method.",
     "why_cs": "Neustálé nahlížení nafukuje falešně pozitivní výsledky daleko nad nominálních 5 procent. Určete velikost vzorku předem nebo použijte sekvenční metodu."},
    {"id": "m-stuffing", "answer": "myth", "ref": "Aggarwal et al., 2024",
     "en": "Stuffing keywords makes your content more visible to AI answer engines.", "cs": "Nacpání klíčových slov zvýší viditelnost obsahu v AI odpovědních enginech.",
     "why_en": "In the GEO benchmark, keyword stuffing did not help, while citations, quotations and statistics did. Caveat: one benchmark and engine setup.",
     "why_cs": "V benchmarku GEO nacpání klíčových slov nepomohlo, zatímco citace, citáty a statistiky ano. Pozor: jde o jeden benchmark a nastavení enginu."},
    {"id": "m-arousal", "answer": "fact", "ref": "Berger and Milkman, 2012",
     "en": "High-arousal emotions such as awe or anger make content more likely to be shared than low-arousal sadness.", "cs": "Emoce s vysokou intenzitou, jako úžas nebo hněv, zvyšují šanci na sdílení víc než smutek s nízkou intenzitou.",
     "why_en": "Observational data on thousands of articles supports this. It shows association, not proof of cause, and it is no licence to manufacture outrage.",
     "why_cs": "Podporují to observační data z tisíců článků. Ukazuje to souvislost, ne důkaz příčiny, a není to licence vyrábět pobouření."},
    {"id": "m-points", "answer": "myth", "ref": "Deci, Koestner and Ryan, 1999",
     "en": "Rewarding people with points always increases their intrinsic motivation.", "cs": "Odměňování body vždy zvyšuje vnitřní motivaci.",
     "why_en": "A meta-analysis found that expected tangible rewards can undermine intrinsic motivation. Reward progress and mastery, not mere activity.",
     "why_cs": "Metaanalýza zjistila, že očekávané hmatatelné odměny mohou vnitřní motivaci podkopat. Odměňujte pokrok a mistrovství, ne pouhou aktivitu."},
    {"id": "m-gamification", "answer": "fact", "ref": "Sailer and Homner, 2020; Hamari et al., 2014",
     "en": "Gamification tends to give small to medium positive effects, and context matters.", "cs": "Gamifikace obvykle přináší malé až střední pozitivní efekty a záleží na kontextu.",
     "why_en": "Reviews and a meta-analysis point that way, mostly in learning settings. It is not magic and it can fail.",
     "why_cs": "Přehledové studie a metaanalýza to naznačují, hlavně ve vzdělávání. Není to kouzlo a může to selhat."},
    {"id": "m-scaled", "answer": "myth", "ref": "Google Search Central spam policies",
     "en": "Mass-produced AI articles are safe for SEO as long as they read well.", "cs": "Hromadně vyráběné AI články jsou pro SEO bezpečné, pokud se dobře čtou.",
     "why_en": "Mass-produced low-value content can violate spam policy however it is made. Add first-party experience and review every piece.",
     "why_cs": "Hromadně vyráběný obsah s nízkou hodnotou může porušovat spamové zásady bez ohledu na to, jak vznikl. Přidejte vlastní zkušenost a každý kus zkontrolujte."},
    {"id": "m-loss", "answer": "fact", "ref": "Kahneman and Tversky, 1979",
     "en": "Losses tend to feel larger than equal gains.", "cs": "Ztráty bývají vnímány silněji než stejně velké zisky.",
     "why_en": "This is the core of prospect theory. How strongly it shows up in marketing varies, so test it and never fake scarcity.",
     "why_cs": "To je jádro teorie vyhlídek. Jak silně se projeví v marketingu, se liší, takže to testujte a nikdy nepředstírejte nedostatek."},
    {"id": "m-curiosity", "answer": "fact", "ref": "Gruber, Gelman and Ranganath, 2014",
     "en": "Curiosity can improve learning and memory.", "cs": "Zvědavost může zlepšit učení a paměť.",
     "why_en": "A lab study linked curiosity states to better memory and activity in reward circuitry. Small lab samples, so treat it as supportive, not final.",
     "why_cs": "Laboratorní studie spojila stavy zvědavosti s lepší pamětí a aktivitou v okruzích odměny. Malé laboratorní vzorky, berte to jako podpůrné, ne konečné."},
    {"id": "m-rats", "answer": "myth", "ref": "Ferster and Skinner, 1957",
     "en": "Variable-reward experiments on animals prove that slot-machine mechanics are the best way to market products.", "cs": "Pokusy s proměnlivou odměnou na zvířatech dokazují, že mechanika hracích automatů je nejlepší způsob marketingu.",
     "why_en": "Reinforcement schedules were studied in animals. Generalising to marketing is weak, and manipulative mechanics erode trust. Variable rewards belong in learning, with published odds.",
     "why_cs": "Plány posilování se zkoumaly na zvířatech. Zobecnění na marketing je slabé a manipulativní mechaniky ničí důvěru. Proměnlivé odměny patří do učení, s uvedenými šancemi."},
    {"id": "m-geo-cite", "answer": "fact", "ref": "Aggarwal et al., 2024",
     "en": "Citing sources, adding quotations from named people and adding statistics can help generative engines surface your content.", "cs": "Citace zdrojů, citáty jmenovaných osob a statistiky mohou pomoci generativním enginům zobrazit váš obsah.",
     "why_en": "These were the strongest tactics in the GEO benchmark. Use real, verifiable sources only.",
     "why_cs": "Byly to nejsilnější taktiky v benchmarku GEO. Používejte jen skutečné, ověřitelné zdroje."},
    {"id": "m-fluency", "answer": "fact", "ref": "Alter and Oppenheimer, 2009",
     "en": "Text that is easy to process shapes how people judge it.", "cs": "To, jak snadno se text zpracovává, ovlivňuje, jak ho lidé hodnotí.",
     "why_en": "Processing fluency influences judgements. Short words and clear structure are not decoration, they are persuasion hygiene.",
     "why_cs": "Plynulost zpracování ovlivňuje soudy. Krátká slova a jasná struktura nejsou ozdoba, ale hygiena přesvědčování.",
     },
]

LAB_SCENARIOS = [
    {"id": "lab-subject", "title_en": "Newsletter subject line", "title_cs": "Předmět newsletteru",
     "baseline": 0.04, "lift_rel": 0.25, "visitors_hint": 6000},
    {"id": "lab-cta", "title_en": "Landing page button", "title_cs": "Tlačítko na landing page",
     "baseline": 0.08, "lift_rel": 0.15, "visitors_hint": 12000},
    {"id": "lab-thumb", "title_en": "Video thumbnail", "title_cs": "Náhled videa",
     "baseline": 0.03, "lift_rel": 0.40, "visitors_hint": 3000},
]

DROP_RATES = {"common": 0.60, "rare": 0.28, "epic": 0.10, "legendary": 0.02}
PITY_AFTER = 8


def _quantiles(values: list[float]) -> list[float]:
    s = sorted(values)
    return [round(quantile(s, i / 100), 3) for i in range(101)]


DIFFICULTY_BANDS = {"easy": (30.0, 101.0), "medium": (15.0, 30.0), "hard": (6.0, 15.0)}
DIFFICULTY_SHARE = {"easy": 0.30, "medium": 0.40, "hard": 0.30}


def build_arena(analyses: list[ItemAnalysis], titles: dict[str, str], brands: dict[str, str], *, n_pairs: int = 120, seed: int = 11,
                logit_scale: float = 12.0) -> list[dict[str, Any]]:
    """Duels with a known winner by real (here: simulated) success. Difficulty is the success gap."""
    rng = random.Random(seed)
    groups: dict[tuple, list[ItemAnalysis]] = {}
    for a in analyses:
        if a.success is not None:
            groups.setdefault((a.cohort, a.platform, a.lang), []).append(a)
    pools = [(k, v) for k, v in sorted(groups.items()) if len(v) >= 24]
    quota = {d: round(n_pairs * share) for d, share in DIFFICULTY_SHARE.items()}
    pairs: list[dict[str, Any]] = []
    used: dict[str, int] = {}
    attempts = 0
    while pools and any(quota.values()) and attempts < n_pairs * 400:
        attempts += 1
        difficulty = rng.choice([d for d, q in quota.items() if q > 0])
        gap_lo, gap_hi = DIFFICULTY_BANDS[difficulty]
        key, pool = rng.choice(pools)
        x = rng.choice(pool)
        near = [y for y in pool if y.item_id != x.item_id and gap_lo <= abs((y.success or 0) - (x.success or 0)) < gap_hi]
        if not near:
            continue
        y = rng.choice(near)
        hi, lo = (x, y) if (x.success or 0) > (y.success or 0) else (y, x)
        if titles[lo.item_id].lower() == titles[hi.item_id].lower():
            continue
        if used.get(lo.item_id, 0) >= 2 or used.get(hi.item_id, 0) >= 2:
            continue
        used[lo.item_id] = used.get(lo.item_id, 0) + 1
        used[hi.item_id] = used.get(hi.item_id, 0) + 1
        quota[difficulty] -= 1
        winner_is_a = rng.random() < 0.5
        a_item, b_item = (hi, lo) if winner_is_a else (lo, hi)
        cmp = compare_hooks(titles[a_item.item_id], titles[b_item.item_id], lang=key[2], logit_scale=logit_scale)
        model_pick_a = cmp.p_a_wins >= 0.5
        pairs.append({
            "id": f"p{len(pairs) + 1:03d}", "difficulty": difficulty, "cohort": key[0], "platform": key[1], "lang": key[2],
            "a": {"text": titles[a_item.item_id], "brand": brands[a_item.item_id], "success": round(a_item.success or 0, 1),
                  "score": round(a_item.score.total, 1)},
            "b": {"text": titles[b_item.item_id], "brand": brands[b_item.item_id], "success": round(b_item.success or 0, 1),
                  "score": round(b_item.score.total, 1)},
            "winner": "a" if winner_is_a else "b", "model_p_a": round(cmp.p_a_wins, 3),
            "upset": model_pick_a != winner_is_a and cmp.winner != "tie",
            "reasons_en": cmp.reasons_en, "reasons_cs": cmp.reasons_cs,
        })
    rng.shuffle(pairs)
    for i, pair in enumerate(pairs, 1):
        pair["id"] = f"p{i:03d}"
    return pairs


def build_benchmarks(analyses: list[ItemAnalysis]) -> dict[str, Any]:
    bench = Benchmark(analyses)
    out: dict[str, Any] = {}
    for cohort in [None] + bench.cohorts():
        pool = [a.score.total for a in analyses if cohort is None or a.cohort == cohort]
        out["all" if cohort is None else cohort] = {"quantiles": _quantiles(pool), "stats": {k: round(v, 2) for k, v in bench.stats(cohort).items()}}
    return out


def build_loot(patterns: list[dict[str, Any]], ledger_cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for i, p in enumerate(patterns[:14]):
        if not p["significant"] or abs(p["adj_effect"]) < 1.0:
            continue
        direction_en = "higher" if p["adj_effect"] > 0 else "lower"
        direction_cs = "vyšší" if p["adj_effect"] > 0 else "nižší"
        rarity = "rare" if abs(p["adj_effect"]) >= 5 else "common"
        cards.append({
            "id": f"pat-{p['feature']}", "kind": "pattern", "rarity": rarity, "demo": True,
            "title_en": p["label_en"], "title_cs": p["label_cs"],
            "body_en": f"In the demo corpus, this signal goes with {direction_en} success ({p['adj_effect']:+.1f} index points per standard deviation, other features held constant). Demo data: simulated.",
            "body_cs": f"V demo korpusu tento signál souvisí s {direction_cs} úspěchem ({p['adj_effect']:+.1f} bodu indexu na směrodatnou odchylku, ostatní vlastnosti konstantní). Demo data: simulace.",
        })
    cards.extend(ledger_cards)
    spec = load_spec()
    for key, msg in spec["messages"].items():
        if key in ("ship_it", "keep_promise"):
            continue
        cards.append({"id": f"tip-{key}", "kind": "tip", "rarity": "common", "demo": False,
                      "title_en": "Hook hygiene", "title_cs": "Hygiena hooku", "body_en": msg["en"], "body_cs": msg["cs"]})
    return cards


def build_bundle(*, seed: int = 7, ledger: Any = None, forge_samples: list[dict[str, Any]] | None = None,
                 guru_sample: dict[str, Any] | None = None) -> dict[str, Any]:
    brands, items = generate_corpus(seed=seed)
    cohort_by_brand = {b.id: b.cohort for b in brands}
    brand_name = {b.id: b.name for b in brands}
    analyses = analyze_items(items, cohort_by_brand)
    titles = {i.id: i.title for i in items}
    brands_by_item = {i.id: brand_name[i.brand_id] for i in items}
    cal = calibrate_weights(analyses)
    patterns = [p.to_dict() for p in mine_patterns(analyses, titles, n_boot=60)]

    ledger_cards: list[dict[str, Any]] = []
    vault: dict[str, Any] = {"tactics": [], "studies": [], "links": []}
    if ledger is not None:
        vault, ledger_cards = _vault_from_ledger(ledger)

    return {
        "meta": {"version": BUNDLE_VERSION, "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "synthetic": True, "corpus": {"brands": len(brands), "items": len(items)},
                 "note": "All engagement data in this bundle is SIMULATED. Brands are fictional."},
        "spec": load_spec(),
        "calibration": cal.to_dict(),
        "cohort_labels": COHORT_LABELS,
        "benchmarks": build_benchmarks(analyses),
        "arena": build_arena(analyses, titles, brands_by_item, logit_scale=cal.logit_scale),
        "bosses": BOSSES,
        "patterns": patterns,
        "myths": MYTHS,
        "lab": {"scenarios": LAB_SCENARIOS},
        "vault": vault,
        "loot": {"cards": build_loot(patterns, ledger_cards), "rates": DROP_RATES, "pity_after": PITY_AFTER},
        "forge_samples": forge_samples or [],
        "guru_sample": guru_sample,
    }


_GRADE_RARITY = {"A": "epic", "B": "rare", "C": "common", "D": "common"}


def _vault_from_ledger(ledger: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Convert the research ledger (duck typed) to UI data and loot cards."""
    from .research.tactics import TACTICS

    studies = [s.to_dict() for s in ledger.studies.values()] if isinstance(getattr(ledger, "studies", None), dict) \
        else [s.to_dict() for s in getattr(ledger, "studies", [])]
    links = [l.to_dict() for l in getattr(ledger, "links", [])]
    tactics = []
    cards: list[dict[str, Any]] = []
    for t in TACTICS.values():
        summary = ledger.summary(t.id)
        # Show the best grade among studies that SUPPORT the tactic, so a mixed or contradicting
        # high-grade study cannot make weak support look strong.
        supporters = [study.grade or "D" for study, link in ledger.evidence_for(t.id) if link.direction == "supports"]
        tactics.append({**t.to_dict(), "evidence": {
            "label": summary.label, "grade": min(supporters, default=""), "n_studies": summary.n_studies,
            "headline_en": summary.headline_en, "headline_cs": summary.headline_cs,
            "caveats_en": summary.caveats_en, "caveats_cs": summary.caveats_cs,
        }})
    for study in studies:
        rarity = _GRADE_RARITY.get(study.get("grade") or "C", "common")
        if study.get("design") in ("meta-analysis", "systematic-review"):
            rarity = "legendary" if study.get("grade") == "A" else "epic"
        authors = study.get("authors") or []
        first = authors[0].split(",")[0] if authors else "Unknown"
        cards.append({
            "id": f"study-{study['id']}", "kind": "study", "rarity": rarity, "demo": False,
            "title_en": f"{first} ({study.get('year')})", "title_cs": f"{first} ({study.get('year')})",
            "body_en": f"{study['title']}. Design: {study.get('design')}. Grade {study.get('grade')}. Not yet verified against Crossref: run `kingctl evidence verify`." if not study.get("verified") else f"{study['title']}. Design: {study.get('design')}. Grade {study.get('grade')}. Verified.",
            "body_cs": f"{study['title']}. Typ studie: {study.get('design')}. Hodnocení {study.get('grade')}. Zatím neověřeno přes Crossref: spusťte `kingctl evidence verify`." if not study.get("verified") else f"{study['title']}. Typ studie: {study.get('design')}. Hodnocení {study.get('grade')}. Ověřeno.",
        })
    stats = ledger.stats() if hasattr(ledger, "stats") else {}
    return {"tactics": tactics, "studies": studies, "links": links, "stats": stats}, cards


def bundle_json(bundle: dict[str, Any], *, indent: int | None = None) -> str:
    return json.dumps(bundle, ensure_ascii=False, indent=indent, separators=None if indent else (",", ":"))
