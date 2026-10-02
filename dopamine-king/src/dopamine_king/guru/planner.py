"""Guru: a 4 week content plan built from rules, evidence and the hook library.

No hype and no invented numbers. Targets are relative to the brand's own baseline, proof slots
that need first-party material are marked, and every experiment carries the sample size the Lab
says it needs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from ..generate.types import Brief
from ..lab.ab import sample_size_per_arm

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri")
B2B_COHORTS = {"b2b-saas", "finance", "tech"}
B2B_WORDS = ("team", "manager", "founder", "compan", "business", "b2b", "enterprise", "saas", "firm", "firem", "podnik", "zakladatel")

PILLARS = {
    "educate": {"name_en": "Educate", "name_cs": "Vzdělávej",
                "angles_en": ["How-to with a concrete result", "Common mistakes and how to avoid them", "Myth versus fact", "Checklist or template"],
                "angles_cs": ["Návod s konkrétním výsledkem", "Časté chyby a jak se jim vyhnout", "Mýtus versus fakt", "Checklist nebo šablona"]},
    "prove": {"name_en": "Prove", "name_cs": "Dokaž",
              "angles_en": ["A first-party number and what it means", "Before and after with real data", "Behind the scenes of how it is made", "Customer outcome (with permission)"],
              "angles_cs": ["Vlastní číslo a co znamená", "Před a po se skutečnými daty", "Zákulisí výroby", "Výsledek zákazníka (se svolením)"]},
    "story": {"name_en": "Story", "name_cs": "Příběh",
              "angles_en": ["Origin or turning point", "A day in the life of the audience", "Lesson learned the hard way", "Community spotlight"],
              "angles_cs": ["Počátek nebo zlom", "Den v životě publika", "Lekce, která stála zkušenost", "Spotlight na komunitu"]},
    "convert": {"name_en": "Convert", "name_cs": "Prodej",
                "angles_en": ["One clear offer with an honest deadline (only if real)", "Objection handling", "Comparison with the old way", "How to get started in three steps"],
                "angles_cs": ["Jedna jasná nabídka s férovým termínem (jen pokud je reálný)", "Řešení námitek", "Srovnání se starým způsobem", "Jak začít ve třech krocích"]},
}
PILLAR_SHARE = {
    "awareness": {"educate": 0.35, "story": 0.30, "prove": 0.20, "convert": 0.15},
    "consideration": {"educate": 0.30, "prove": 0.35, "story": 0.15, "convert": 0.20},
    "conversion": {"convert": 0.35, "prove": 0.35, "educate": 0.20, "story": 0.10},
    "retention": {"educate": 0.35, "story": 0.25, "prove": 0.20, "convert": 0.20},
    "community": {"story": 0.40, "educate": 0.30, "prove": 0.15, "convert": 0.15},
}

CHANNELS = {
    "linkedin": {"formats": ["linkedin_post", "linkedin_carousel"], "kpi": "saves and comments",
                 "why_en": "Professional audience, text and carousel formats reward expertise.", "why_cs": "Profesionální publikum, texty a karusely odměňují odbornost."},
    "blog": {"formats": ["seo_article", "geo_answer_page"], "kpi": "organic visits and AI citations",
             "why_en": "Compounding search and answer-engine visibility; the home of your evidence.", "why_cs": "Kumulativní viditelnost ve vyhledávání a v AI odpovědích; domov vašich důkazů."},
    "email": {"formats": ["newsletter", "email_sequence"], "kpi": "open and click rate",
              "why_en": "The one channel you own; best place to convert attention.", "why_cs": "Jediný kanál, který vlastníte; nejlepší místo pro přeměnu pozornosti."},
    "youtube": {"formats": ["youtube_script"], "kpi": "average view duration",
                "why_en": "Search plus recommendation; long form builds trust.", "why_cs": "Vyhledávání plus doporučování; dlouhá forma buduje důvěru."},
    "short_video": {"formats": ["short_video_script"], "kpi": "completion rate",
                    "why_en": "Cheapest reach; the first three seconds decide everything.", "why_cs": "Nejlevnější dosah; o všem rozhodují první tři vteřiny."},
    "instagram": {"formats": ["instagram_carousel", "instagram_caption"], "kpi": "saves and shares",
                  "why_en": "Visual discovery for consumer topics; saves signal real value.", "why_cs": "Vizuální objevování spotřebitelských témat; uložení signalizuje skutečnou hodnotu."},
    "x": {"formats": ["x_post", "x_thread"], "kpi": "reposts and profile clicks",
          "why_en": "Fast feedback on messages and hooks.", "why_cs": "Rychlá zpětná vazba na sdělení a hooky."},
    "facebook": {"formats": ["facebook_post"], "kpi": "shares and comments",
                 "why_en": "Strong with local and community audiences.", "why_cs": "Silný u lokálních a komunitních publik."},
    "pinterest": {"formats": ["pinterest_pin"], "kpi": "outbound clicks",
                  "why_en": "Evergreen search-like discovery for home, food, fashion and travel.", "why_cs": "Trvalé objevování podobné vyhledávání pro bydlení, jídlo, módu a cestování."},
    "google_business": {"formats": ["google_business_post"], "kpi": "calls and direction requests",
                        "why_en": "Local intent at the moment of decision.", "why_cs": "Lokální záměr v okamžiku rozhodování."},
}
B2B_WEIGHTS = {"linkedin": 3, "blog": 3, "email": 2, "youtube": 1, "x": 1}
B2C_WEIGHTS = {"short_video": 3, "instagram": 3, "blog": 2, "email": 2, "youtube": 1}
VISUAL_COHORTS = {"home-living", "food-beverage", "fashion-beauty", "travel"}

HYPOTHESES = [
    ("Number-led hooks beat curiosity-led hooks", "Hooky s číslem porazí hooky založené na zvědavosti", "CTR"),
    ("A question beats a statement as the opening line", "Otázka porazí tvrzení jako úvodní řádek", "CTR"),
    ("Speaking to the reader (you) beats talking about us", "Oslovení čtenáře (vy) porazí mluvení o nás", "saves rate"),
    ("Hooks under 8 words beat hooks over 12 words", "Hooky pod 8 slov porazí hooky nad 12 slov", "CTR"),
    ("Showing the payoff first beats building suspense", "Ukázat výsledek hned porazí budování napětí", "completion rate"),
]

KPI_BY_GOAL = {
    "awareness": ("Reach and completion rate", "Dosah a dokoukanost"),
    "consideration": ("Click-through rate and saves", "Míra prokliku a uložení"),
    "conversion": ("Conversion rate and cost per conversion", "Konverzní poměr a cena konverze"),
    "retention": ("Open rate and repeat visits", "Otevření a opakované návštěvy"),
    "community": ("Comments, replies and shares", "Komentáře, odpovědi a sdílení"),
}


@dataclass
class Plan:
    brief: dict[str, Any]
    positioning: str
    pillars: list[dict[str, Any]]
    channels: list[dict[str, Any]]
    calendar: list[dict[str, Any]]
    experiments: list[dict[str, Any]]
    kpis: list[dict[str, Any]]
    geo: dict[str, Any]
    guardrails_en: list[str]
    guardrails_cs: list[str]
    needs_input: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "brief": self.brief, "positioning": self.positioning, "pillars": self.pillars, "channels": self.channels,
            "calendar": self.calendar, "experiments": self.experiments, "kpis": self.kpis, "geo": self.geo,
            "guardrails_en": self.guardrails_en, "guardrails_cs": self.guardrails_cs, "needs_input": self.needs_input,
        }

    def to_markdown(self, lang: str = "en") -> str:
        cs = lang == "cs"
        out = [f"# {'Obsahový plán' if cs else 'Content plan'}: {self.brief['brand']}", "", f"**{'Pozicování' if cs else 'Positioning'}:** {self.positioning}", ""]
        out.append(f"## {'Pilíře' if cs else 'Pillars'}")
        for p in self.pillars:
            out.append(f"- **{p['name_cs' if cs else 'name_en']}** ({p['share']:.0%}): " + "; ".join(p["angles_cs" if cs else "angles_en"][:2]))
        out += ["", f"## {'Kanály' if cs else 'Channels'}"]
        for c in self.channels:
            out.append(f"- **{c['id']}**: {c['posts_per_week']}x / {'týden' if cs else 'week'}, " + ", ".join(c["formats"]) + f". {c['why_cs' if cs else 'why_en']}")
        out += ["", f"## {'Kalendář' if cs else 'Calendar'}", "", f"| {'Týden' if cs else 'Week'} | {'Den' if cs else 'Day'} | {'Kanál' if cs else 'Channel'} | Format | {'Pilíř' if cs else 'Pillar'} | Hook |", "|---|---|---|---|---|---|"]
        for e in self.calendar:
            mark = " (A/B)" if e.get("experiment") else ""
            out.append(f"| {e['week']} | {e['day']} | {e['channel']} | {e['format']} | {e['pillar']} | {e['hook']}{mark} |")
        out += ["", f"## {'Experimenty' if cs else 'Experiments'}"]
        for x in self.experiments:
            out.append(f"- {x['hypothesis_cs' if cs else 'hypothesis_en']} ({x['metric']}, n/{'rameno' if cs else 'arm'} = {x['n_per_arm']})")
        out += ["", f"## {'Pojistky' if cs else 'Guardrails'}"] + [f"- {g}" for g in (self.guardrails_cs if cs else self.guardrails_en)]
        if self.needs_input:
            out += ["", f"## {'Chybí vstup od vás' if cs else 'Needs your input'}"] + [f"- {n}" for n in self.needs_input]
        return "\n".join(out)


def _is_b2b(brief: Brief) -> bool:
    if brief.cohort in B2B_COHORTS:
        return True
    text = f"{brief.audience} {brief.topic}".lower()
    return any(w in text for w in B2B_WORDS)


def _largest_remainder(shares: dict[str, float], total: int) -> dict[str, int]:
    raw = {k: v * total for k, v in shares.items()}
    out = {k: int(math.floor(v)) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - out[k], reverse=True)[: total - sum(out.values())]:
        out[k] += 1
    return out


def _fallback_hooks(brief: Brief, n: int) -> list[str]:
    base = brief.topic
    if brief.lang == "cs":
        pool = [f"{base}: co dělají lepší týmy jinak", f"Chyby, které brzdí {base}", f"{base}: jednoduchý návod", f"Mýty o tématu {base}", f"{base} v číslech", f"{base}: zkuste to takhle"]
    else:
        pool = [f"What better teams do differently with {base}", f"Mistakes that slow down {base}", f"{base}: a simple guide", f"Myths about {base}", f"{base} in numbers", f"Try {base} this way"]
    return [pool[i % len(pool)] + ("" if i < len(pool) else f" ({i // len(pool) + 1})") for i in range(n)]


def _strategy_for(brief: Brief) -> dict[str, Any]:
    """The strategy file of the brief's vertical (pillar wording, hypotheses, queries), or nothing."""
    if not brief.vertical:
        return {}
    try:
        from ..verticals import load_vertical
        return load_vertical(brief.vertical).strategy()
    except Exception:
        return {}


def _hooks(brief: Brief, n: int) -> list[str]:
    try:
        from ..generate.guard import TrustShield
        from ..generate.hooks import generate_hooks
        from ..generate.packs import safe_candidates
        found = [h.text for h in safe_candidates(generate_hooks(brief, n=n * 2), brief, TrustShield())]
    except Exception:
        found = []
    if len(found) < n:
        found += [h for h in _fallback_hooks(brief, n) if h not in found]
    return found[:n]


def _queries(brief: Brief, n: int = 10) -> list[str]:
    try:
        from ..generate.visibility import suggest_queries
        return suggest_queries(brief, n)
    except Exception:
        t = brief.primary_keyword
        return ([f"co je {t}", f"nejlepší {t} pro {brief.audience}", f"{t} alternativy", f"jak vybrat {t}"]
                if brief.lang == "cs" else
                [f"what is {t}", f"best {t} for {brief.audience}", f"{t} alternatives", f"how to choose {t}"])[:n]


def build_plan(
    brief: Brief, *, weeks: int = 4, posts_per_week: int = 5, channels: list[str] | None = None,
    baseline_ctr: float = 0.03, mde_rel: float = 0.2, strategy: dict[str, Any] | None = None,
) -> Plan:
    cs = brief.lang == "cs"
    b2b = _is_b2b(brief)
    needs: list[str] = []
    strategy = strategy if strategy is not None else _strategy_for(brief)
    pillar_defs = {pid: {**PILLARS[pid], **strategy.get("pillars", {}).get(pid, {})} for pid in PILLARS}
    hypotheses = [(h["en"], h["cs"], h["metric"]) for h in strategy.get("hypotheses", [])] or HYPOTHESES

    base_weights = strategy.get("channel_weights") or (B2B_WEIGHTS if b2b else B2C_WEIGHTS)
    weights = {c: 1 for c in channels} if channels else dict(base_weights)
    if not channels:
        if brief.cohort in VISUAL_COHORTS:
            weights["pinterest"] = 1
        if brief.cohort == "cz-local" or brief.lang == "cs":
            weights["facebook"] = 1
    weights = {c: w for c, w in weights.items() if c in CHANNELS}
    slots_total = weeks * posts_per_week
    per_channel = _largest_remainder({c: w / sum(weights.values()) for c, w in weights.items()}, slots_total)
    channel_rows = [
        {"id": c, "formats": CHANNELS[c]["formats"], "posts_per_week": round(per_channel[c] / weeks, 2), "kpi": CHANNELS[c]["kpi"],
         "why_en": CHANNELS[c]["why_en"], "why_cs": CHANNELS[c]["why_cs"]}
        for c in sorted(per_channel, key=lambda c: -per_channel[c]) if per_channel[c] > 0
    ]

    shares = PILLAR_SHARE.get(brief.goal, PILLAR_SHARE["awareness"])
    pillar_counts = _largest_remainder(shares, slots_total)
    pillars = [{"id": pid, "name_en": pillar_defs[pid]["name_en"], "name_cs": pillar_defs[pid]["name_cs"], "share": shares[pid],
                "angles": pillar_defs[pid]["angles_cs" if cs else "angles_en"], "angles_en": pillar_defs[pid]["angles_en"],
                "angles_cs": pillar_defs[pid]["angles_cs"]} for pid in shares]
    if not brief.facts:
        if strategy.get("needs_facts"):
            needs.append(strategy["needs_facts"]["cs" if cs else "en"])
        else:
            needs.append("Add 3 first-party facts (numbers, results, customer outcomes) so the Prove pillar has real material." if not cs
                         else "Přidejte 3 vlastní fakta (čísla, výsledky, výsledky zákazníků), aby měl pilíř Dokaž skutečný materiál.")
    if not brief.sources:
        needs.append("Add 2 to 3 vetted sources (studies, standards) for citations in articles." if not cs
                     else "Přidejte 2 až 3 prověřené zdroje (studie, normy) pro citace v článcích.")
    if not brief.offer:
        needs.append("Describe the offer so the Convert pillar can be specific." if not cs else "Popište nabídku, aby pilíř Prodej mohl být konkrétní.")

    # Interleave channels so a day never repeats the same channel twice in a row where avoidable.
    order: list[str] = []
    remaining = dict(per_channel)
    while sum(remaining.values()) > 0:
        for c in sorted(remaining, key=lambda c: -remaining[c]):
            if remaining[c] > 0:
                order.append(c)
                remaining[c] -= 1
    pillar_order: list[str] = []
    pc = dict(pillar_counts)
    while sum(pc.values()) > 0:
        for p in sorted(pc, key=lambda p: -pc[p]):
            if pc[p] > 0:
                pillar_order.append(p)
                pc[p] -= 1

    hooks = _hooks(brief, slots_total + weeks)
    calendar: list[dict[str, Any]] = []
    fmt_cursor: dict[str, int] = {}
    for i in range(slots_total):
        week, day_idx = divmod(i, posts_per_week)
        channel = order[i]
        formats = CHANNELS[channel]["formats"]
        fmt = formats[fmt_cursor.get(channel, 0) % len(formats)]
        fmt_cursor[channel] = fmt_cursor.get(channel, 0) + 1
        calendar.append({
            "week": week + 1, "day": DAYS[day_idx % len(DAYS)], "channel": channel, "format": fmt,
            "pillar": pillar_order[i], "hook": hooks[i], "experiment": None, "kpi": CHANNELS[channel]["kpi"],
        })

    experiments: list[dict[str, Any]] = []
    n_arm = sample_size_per_arm(baseline_ctr, mde_rel)
    for w in range(weeks):
        first = next(e for e in calendar if e["week"] == w + 1)
        h_en, h_cs, metric = hypotheses[w % len(hypotheses)]
        first["experiment"] = {"hypothesis": h_cs if cs else h_en, "variant_b": hooks[slots_total + w], "metric": metric}
    for idx, (h_en, h_cs, metric) in enumerate(hypotheses):
        experiments.append({
            "id": f"e{idx + 1}", "hypothesis_en": h_en, "hypothesis_cs": h_cs, "metric": metric,
            "baseline": baseline_ctr, "mde_rel": mde_rel, "n_per_arm": n_arm,
            "note_en": "Replace the baseline with your own measured rate before running.",
            "note_cs": "Před spuštěním nahraďte základní hodnotu vlastním naměřeným číslem.",
        })

    kpis = [{"goal": g, "metric_en": KPI_BY_GOAL[g][0], "metric_cs": KPI_BY_GOAL[g][1],
             "target_rule_en": "Improve by 10 percent against your own previous 4 week baseline, then re-baseline.",
             "target_rule_cs": "Zlepšit o 10 procent proti vlastnímu předchozímu čtyřtýdennímu základu, potom základ přepočítat.",
             "primary": g == brief.goal} for g in KPI_BY_GOAL]

    queries = list(strategy.get("queries", {}).get(brief.lang, [])) or _queries(brief)
    geo = {
        "queries": queries,
        "tasks_en": [
            "Publish one answer-first page per query cluster (format geo_answer_page) with a 40 to 60 word direct answer.",
            "Add at least 3 vetted sources, 1 quotation from a named expert and 3 first-party statistics per page.",
            "Add Article, FAQPage and Organization JSON-LD; show author, role and a visible updated date.",
            "Decide your policy for AI crawlers in robots.txt (search allowed, training your choice) and optionally publish llms.txt.",
            "Every week paste the answers of 2 to 3 answer engines for these queries into `kingctl visibility` and track mention and citation rate.",
        ],
        "tasks_cs": [
            "Publikujte pro každý okruh dotazů jednu stránku s odpovědí na začátku (formát geo_answer_page) s přímou odpovědí na 40 až 60 slov.",
            "Přidejte nejméně 3 prověřené zdroje, 1 citát jmenovaného experta a 3 vlastní statistiky na stránku.",
            "Přidejte JSON-LD Article, FAQPage a Organization; ukažte autora, jeho roli a viditelné datum aktualizace.",
            "Rozhodněte o politice pro AI crawlery v robots.txt (vyhledávání povolit, trénink dle vašeho rozhodnutí) a volitelně publikujte llms.txt.",
            "Každý týden vložte odpovědi 2 až 3 odpovědních enginů na tyto dotazy do `kingctl visibility` a sledujte míru zmínek a citací.",
        ],
    }
    guardrails_en = [
        "Every piece passes the Trust Shield before publishing: no invented numbers, no fake scarcity, citations only from vetted sources.",
        "A human reviews and adds first-party experience to every article; mass-produced low-value content is a spam-policy risk.",
        "Label sponsored content and follow platform and EU rules on AI-generated or synthetic media; this is not legal advice.",
        "Verify platform limits and policies before publishing; they change.",
    ]
    guardrails_cs = [
        "Každý kus projde před publikací Trust Shieldem: žádná vymyšlená čísla, žádný falešný nedostatek, citace jen z prověřených zdrojů.",
        "Člověk každý článek zkontroluje a doplní o vlastní zkušenost; hromadně vyráběný obsah s nízkou hodnotou je riziko pro spamové zásady.",
        "Označte sponzorovaný obsah a dodržujte pravidla platforem a EU pro obsah vytvořený AI nebo syntetická média; nejde o právní radu.",
        "Před publikací ověřte limity a pravidla platforem; mění se.",
    ]
    guardrails_en = strategy.get("guardrails_en", []) + guardrails_en
    guardrails_cs = strategy.get("guardrails_cs", []) + guardrails_cs
    positioning = (
        f"{brief.brand} | {'Publikum' if cs else 'Audience'}: {brief.audience} | {'Téma' if cs else 'Topic'}: {brief.topic} | "
        f"{'Slib' if cs else 'Promise'}: {brief.offer or ('[[DOPLŇTE jednu větu slibu]]' if cs else '[[ADD one sentence promise]]')} | "
        f"{'Důkaz' if cs else 'Proof'}: {'; '.join(brief.facts[:2]) if brief.facts else ('[[DOPLŇTE vlastní fakt]]' if cs else '[[ADD a first-party fact]]')} | "
        f"{'Tón' if cs else 'Tone'}: {brief.tone}"
    )
    return Plan(brief.to_dict(), positioning, pillars, channel_rows, calendar, experiments, kpis, geo, guardrails_en, guardrails_cs, needs)
