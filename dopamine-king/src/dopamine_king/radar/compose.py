"""The sentences of the report: findings and actions in plain Czech, every number taken from the analysis.

Nothing here is typed in by hand as a result. A sentence is only produced when the data supports it, so a new snapshot gives a new report.
"""
from __future__ import annotations

from typing import Any

NBSP = " "
TYPE_ORDER = ("pharmacy", "media", "forum", "ecommerce", "foreign_shop", "maker", "service", "foreign_media", "reviews", "authority", "science")


def plural(n: int, one: str, few: str, many: str) -> str:
    return one if n == 1 else few if 2 <= n <= 4 else many


def count(n: int, one: str, few: str, many: str) -> str:
    return f"{n}{NBSP}{plural(n, one, few, many)}"


def pct(part: int, whole: int) -> int:
    return round(100 * part / whole) if whole else 0


def names(items: list[str]) -> str:
    return ", ".join(items[:-1]) + " a " + items[-1] if len(items) > 1 else (items[0] if items else "")


def findings(d: dict[str, Any]) -> list[dict[str, Any]]:
    """Seven findings, each with the number that carries it, a sentence, a caveat and the searches it rests on."""
    out: list[dict[str, Any]] = []
    vis, ident, land, themes, own, audit, titles, sci = d["visibility"], d["identity"], d["landscape"], d["brandsites"], d["own"], d["claims_audit"], d["own_titles"], d["science"]
    q_all, q_own = vis["all"]["queries"], vis["all"]["own"]
    out.append({
        "id": "viditelnost", "number": f"{q_own}{NBSP}z{NBSP}{q_all}",
        "title": "Váš web se v otevřených hledáních neukázal" if q_own == 0 else "Váš web se v otevřených hledáních ukázal jen občas",
        "text": (f"Hledali jsme název značky, kategorii, témata šesti cílových skupin i konkurenty ({q_all} hledání). "
                 + ("Mitolight.cz se mezi výsledky neobjevil ani jednou. " if q_own == 0 else f"Mitolight.cz se objevil v {q_own} z nich. ")
                 + f"Když jsme hledání omezili jen na váš web, vyhledávač zná {count(len(own['pages']), 'stránku', 'stránky', 'stránek')}. Obsah tedy existuje."),
        "caveat": "Nástroj hledá z USA a není to Google.cz ani Seznam. Skutečné pozice ukážou Search Console a Seznam Webmaster.",
        "evidence": ["brand-02", "own-01", "own-02", "own-03"]})
    if ident["counted_links"]:
        share = pct(ident["lookalike_links"], ident["counted_links"])
        worst = ident["worst"]
        quote = next((q for q in ident["quotes"] if q["id"].startswith("direct")), None)
        out.append({
            "id": "identita", "number": f"{share}{NBSP}%",
            "title": "Při hledání vašeho názvu vede třetina odkazů jinam" if 25 <= share <= 45 else "Při hledání vašeho názvu vedou odkazy na Mito Red Light",
            "text": (f"Mezi výsledky pro dotazy s názvem MITO LIGHT je {ident['lookalike_links']} z {ident['counted_links']} odkazů na americkou Mito Red Light. "
                     + (f"U dotazu „{worst['query']}“ je to {worst['lookalike']} z {worst['links']}. " if worst and worst['lookalike'] >= 3 else "")
                     + (f"Strojové shrnutí vyhledávače v jednom případě napsalo: „{quote['text']}“" if quote else "")),
            "caveat": "Shrnutí píše stroj, ne stránky. Potvrďte prosím, že jde o dvě různé značky, a text opravte u zdroje.",
            "evidence": ["brand-01", "brand-03", "brand-07"] + ([quote["id"]] if quote else [])})
    market_n = d["visibility"]["market"]["queries"]
    top = land["domains"][:5]
    top_text = names([x["name"] + " (" + str(x["queries"]) + "×)" for x in top])
    cz_makers = [x for x in land["domains"] if x["type"] == "maker" and x["host"].endswith((".cz", ".sk"))]
    sellers = [x["name"] for x in land["domains"] if x["type"] == "ecommerce" and x["host"].endswith(".cz")][:3]
    if top:
        out.append({
            "id": "trh", "number": f"{top[0]['name']} {top[0]['queries']}{NBSP}z{NBSP}{market_n}",
            "title": "České výsledky zaplňuje pár zdrojů",
            "text": (f"V {market_n} českých hledáních se nejčastěji objevují {top_text}. "
                     + ("Žádný specializovaný český výrobce panelů mezi výsledky nebyl. " if not cz_makers else "")
                     + (f"Prodejci ({names(sellers)}) tu mají hlavně návody k panelům ke stažení." if sellers else "")),
            "caveat": "Zařazení webů do skupin je úsudek podle názvů a adres, ne měření.",
            "evidence": ["cat-01", "cat-03", "cat-10", "cat-12"]})
    howto = next((t for t in themes["themes"] if t["id"] == "howto"), None)
    if howto:
        n_howto = howto["maker"]["pages"] + howto["media"]["pages"]
        out.append({
            "id": "navod", "number": f"{n_howto}{NBSP}z{NBSP}{themes['pages']}",
            "title": "Návod a bezpečnost se mezi stránkami značek skoro neobjevil",
            "text": (f"Ze {themes['pages']} stránek {themes['sites_with_pages']} webů značek a recenzních webů se jen {n_howto} týkají návodu a bezpečného používání. "
                     f"České dotazy na bezpečnost, kontraindikace a délku sezení přitom ve výsledcích zodpovídá hlavně lékárna, média a návody prodejců. "
                     f"Váš web má takových stránek {own['themes'].get('howto', 0)} (časté otázky)."),
            "caveat": "Témata se přiřazují podle slov v názvu a adrese stránky. Dotazy na weby značek mířily na přínosy a panely, takže návody mohly zůstat mimo výsledky.",
            "evidence": ["cat-10", "cat-11", "cat-12", "cat-13"]})
    if titles:
        topics = names(sorted({t["topic"].lower() for t in titles}))
        out.append({
            "id": "vlastni-nazvy", "number": f"{len(titles)}{NBSP}z{NBSP}{len(own['pages'])}",
            "title": f"{count(len(titles), 'název vaší stránky slibuje', 'názvy vašich stránek slibují', 'názvů vašich stránek slibuje')} výsledek",
            "text": (f"Jde o témata: {topics}. U vlasů nesmí nezdravotnický přístroj tvrdit nic, u spánku a výkonu se důkazy rozcházejí, u pleti jsou možné jen "
                     "opatrné formulace se zdrojem."),
            "caveat": "Kontrola čte jen názvy stránek. Plné texty zkontroluje Trust Shield, jakmile bude mít prostředí přístup na web.",
            "evidence": ["own-01", "own-02", "own-03"]})
    if audit["scanned"]:
        out.append({
            "id": "trh-tvrzeni", "number": f"{audit['flagged']}{NBSP}z{NBSP}{audit['scanned']}",
            "title": "Část trhu slibuje to, co vy nesmíte",
            "text": (f"Z {audit['scanned']} názvů stránek prodejců, výrobců a médií v oboru jich {audit['flagged']} obsahuje tvrzení, které váš profil blokuje: "
                     + names([f"{rule} ({n}×)" for rule, n in audit["by_rule"].items()]) + ". Poctivá formulace je vaše výhoda, ne důvod konkurenci napodobit."),
            "caveat": "Zkoumají se jen krátké názvy stránek, takže skutečný podíl bude vyšší.",
            "evidence": ["site-joovv", "site-omnilux", "site-leredd", "site-rltexpert"]})
    out.append({
        "id": "studie", "number": f"{sci['verified']}{NBSP}z{NBSP}{sci['total']}",
        "title": "Důkazy: skoro všechny studie v registru jsou ověřené",
        "text": (f"K {d['meta']['date_cs']} jsme proti PubMed, PubMed Central a webům vydavatelů ověřili dalších {sci['verified_now']} studií. "
                 f"{count(sci['pending'], 'zůstává', 'zůstávají', 'zůstává')} neověřených. Síla důkazů v mapě tvrzení se počítá jen z ověřených studií."),
        "caveat": "Závěry studií jsou čtené z abstraktů a shrnutí ve výsledcích, plné texty ne.",
        "evidence": ["study-pbm-wunsch2014", "study2-barolet2009", "study2-jackson2009"]})
    return out


def actions(d: dict[str, Any]) -> list[dict[str, Any]]:
    """What to do this week, in order, each with its first step and the finding it comes from."""
    titles = d["own_titles"]
    return [
        {"id": "a1", "title": "Vysvětlete rozdíl mezi MITO LIGHT a Mito Red Light", "finding": "identita",
         "why": "Třetina odkazů při hledání vašeho názvu vede na jinou značku a strojové shrnutí vás s ní spojuje.",
         "steps": ["Potvrďte mi, že jde o dvě různé značky (a že mitolight.com a mitolight.co.uk jsou vaše weby).",
                   "Zveřejněte stránku s vysvětlením (návrh „identita“ níže) a odkaz na ni v patičce.",
                   "Doplňte do webu údaje o firmě a odkazy na Heureku, Trustpilot a Trusted Shops.",
                   "Zkontrolujte, zda se weby mitolight.cz, mitolight.com a mitolight.co.uk odkazují navzájem."]},
        {"id": "a2", "title": f"Přečtěte {count(len(titles), 'stránku', 'stránky', 'stránek')}, jejichž název slibuje výsledek", "finding": "vlastni-nazvy",
         "why": "Název stránky je první, co čte vyhledávač, lidé i úřad.",
         "steps": ["Otevřete stránky ze seznamu níže a porovnejte jejich text s tabulkou „Co smíte tvrdit“.",
                   "Vlasy: nezdravotnický přístroj o nich nesmí tvrdit nic.",
                   "Spánek, výkon a regeneraci formulujte jen opatrně a se zdrojem, nebo je neuvádějte.",
                   "Pro schválení použijte věty z tabulky, ne vlastní."]},
        {"id": "a3", "title": "Pošlete mi export z Search Console a Seznam Webmaster", "finding": "viditelnost",
         "why": "Tento radar hledá z USA. Vaše skutečné pozice v Google.cz a na Seznamu znáte jen vy.",
         "steps": ["V Search Console otevřete Výkon a exportujte dotazy a stránky za posledních 3 měsíce.",
                   "Totéž z Seznam Webmaster.",
                   "Export mi pošlete a radar nahradí odhady skutečnými čísly."]},
        {"id": "a4", "title": "Zveřejněte stránku o bezpečném používání panelu", "finding": "navod",
         "why": "České dotazy na bezpečnost a délku sezení dnes zodpovídají lékárna a média, světové značky o tom skoro nepíší.",
         "steps": ["Projděte návrh „Jak dlouho a jak často používat panel“ níže.",
                   "Ověřte časy a vzdálenosti proti návodu ke každému modelu.",
                   "Doplňte autora a zveřejněte."]},
        {"id": "a5", "title": "Napište, jak měříte ozáření", "finding": "navod",
         "why": "Technicky založení zákazníci porovnávají panely podle mW/cm2. U vás chybí u většiny modelů vzdálenost a přístroj.",
         "steps": ["Pošlete mi z technických listů vzdálenost a způsob měření u každého modelu.",
                   "Projděte návrh „Ozáření v mW/cm2“ níže.",
                   "Zvažte kalkulátor dávky: stránka s kalkulátorem se ve výsledcích pro dotaz na mW/cm2 objevila u konkurence."]},
        {"id": "a6", "title": "Naplánujte šest příspěvků, po jednom pro každou cílovou skupinu", "finding": "trh",
         "why": "Každý příspěvek prošel kontrolou tvrzení a drží se vykání.",
         "steps": ["Vyberte z návrhů níže, upravte hlas a doplňte obrázek.",
                   "Příspěvky se zdroji [n] doplňte o seznam zdrojů, nebo čísla vypusťte."]},
    ]


def open_items(d: dict[str, Any]) -> list[dict[str, str]]:
    """What the radar could not see, and what it would need."""
    return [
        {"what": "Plné texty stránek", "why": "Prostředí, ve kterém radar běží, nemá přístup na web. Vidí jen názvy stránek z vyhledávání, ne jejich obsah.",
         "need": "Zapnout síť pro prostředí (Network access). Pak zkontroluji celé texty vašeho webu a konkurence Trust Shieldem a stáhnu abstrakty studií."},
        {"what": "Skutečné pozice v Google.cz a na Seznamu", "why": "Radar hledá přes nástroj z USA.", "need": "Export ze Search Console a Seznam Webmaster."},
        {"what": "Vztah k Mito Red Light a ke stránkám mitolight.com a mitolight.co.uk", "why": "Strojové shrnutí vás spojuje s jinou firmou.", "need": "Vaše potvrzení."},
        {"what": "Měřené ozáření u každého modelu", "why": "U většiny modelů je uvedeno jen číslo bez vzdálenosti a přístroje.", "need": "Technické listy nebo měření."},
        {"what": "Stanovisko ministerstva pro generace 4.0 a 5.0", "why": "Dostupný dokument se týká generace 3.0.", "need": "Dopis od ministerstva nebo od vašeho poradce."},
        {"what": "Sociální sítě", "why": "Oficiální profily se ve výsledcích neobjevily.", "need": "Odkazy na profily a ideálně export příspěvků."},
        {"what": "Prodeje a návštěvnost", "why": "Bez nich nelze říct, které téma se vyplatí.", "need": "Export z e-shopu a z analytiky."},
    ]
