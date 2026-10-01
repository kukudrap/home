# Dopamine King

> **English TL;DR.** Evidence-driven content intelligence wrapped in a game. It scrapes public brand content politely (robots.txt, TDM reservations, feeds), turns it into cohort-fair benchmarks, tests and compares hooks with real statistics, keeps a graded ledger of the studies behind every tactic, and generates SEO, GEO, social and video content in 28 formats through a trust guard that blocks invented numbers and dark patterns. The Python core has no third-party dependencies; the game is one HTML file; prose is written by Claude (`--writer anthropic`) or left as explicit `[[ADD: ...]]` slots (`--writer offline`). Demo data is synthetic and labelled as such.

Marketingový stroj, který **nejdřív zjistí, co skutečně funguje**, a teprve potom **generuje obsah**: SEO a GEO články, příspěvky, video scénáře, reklamy. Celé je to zabalené do hry, ve které si trénujete cit pro silné hooky, porážíte "bossy" benchmarků a učíte se experimentovat.

Dopamin v názvu bereme vážně a poctivě: není to hormon slasti, ale souvisí s očekáváním a chybou predikce. **Dobrý hook vytvoří očekávání a splní ho.** Clickbait se proto ve skóre i ve hře trestá. Podrobněji v [docs/01-vize.md](docs/01-vize.md).

## Rychlý start

Potřebujete Python 3.11 a (pro testy hry) Node 22. Žádné `pip install`.

```bash
cd dopamine-king
export PYTHONPATH=src

python3 -m dopamine_king demo              # celý řetězec na syntetických datech, offline, pár vteřin
python3 -m dopamine_king build-web         # postaví web/dist/dopamine-king.html (jeden soubor)
python3 -m dopamine_king serve             # hra + lokální API na http://127.0.0.1:8765
```

Hru lze otevřít i dvojklikem na `web/dist/dopamine-king.html`; živé generování a plán přes API potřebují `serve`.

### Generování obsahu

```bash
# struktura bez modelu: nic nevymýšlí, chybějící prózu zapíše jako [[ADD: ...]]
python3 -m dopamine_king forge --brand Zorvia --topic "běžecké boty" --audience "začínající běžci" \
    --lang cs --keyword "běžecké boty pro začátečníky" --fact "Aero 2 váží 210 g." \
    --cta "Vyzkoušejte Aero 2 na 30 dní" --writer offline --out out/zorvia

# s modelem Claude (potřebuje ANTHROPIC_API_KEY a `pip install anthropic`)
python3 -m dopamine_king forge ... --writer anthropic --formats seo_article,linkedin_post,short_video_script
python3 -m dopamine_king formats                  # všech 28 formátů
python3 -m dopamine_king guru plan --brand Zorvia --topic "běžecké boty" --audience "začínající běžci"
```

### Živý sběr a studie (potřebují síť)

```bash
python3 -m dopamine_king sources verify --save .king/sources.json   # ověří adresy značek
python3 -m dopamine_king scrape --cohort sport --per-brand 30        # šetrný sběr
python3 -m dopamine_king import-csv moje-analytika.csv moje-znacka   # vaše vlastní data (cs/en hlavičky)
python3 -m dopamine_king analyze                                      # benchmarky, vzory, kalibrace
python3 -m dopamine_king evidence search "curiosity gap headlines"   # hledání studií
python3 -m dopamine_king evidence verify --save .king/ledger.json    # ověření ledgeru přes Crossref
```

## Co je hotové a co potřebuje vaše vstupy

| Část | Stav |
|---|---|
| Dopamine Score, benchmark, pattern mining, kalibrace, laboratoř (A/B, bandité) | Hotovo, otestováno na syntetickém korpusu se **zasazenými efekty** (analytika je dokáže zpětně najít) |
| Hra (arena, boss, laboratoř, vault) | Hotovo; JS skóre je shodné s Pythonem (104 "golden" případů) |
| 28 formátů obsahu, Trust Shield, SEO a GEO skóre | Hotovo; offline režim nevymýšlí prózu |
| Psaní prózy modelem Claude | Napsáno podle dokumentace a **otestováno proti atrapě**; živé API zde nebylo možné vyzkoušet (bez klíče) |
| Šetrný sběr, import analytik | Hotovo, otestováno offline i proti lokálnímu HTTP serveru; **živý sběr vyžaduje síť** (prostředí, kde kód vznikl, povolilo ze 111 značek jen jednu) |
| Ledger studií | 32 záznamů; **23 potvrzeno** veřejnými zdroji (název, časopis, rok, DOI), zbytek má u sebe poznámku, jak daleko ověření došlo. `evidence verify` ověří přes Crossref. |
| Reálná data značek | Nejsou v repozitáři (autorská práva a výkonnostní čísla nejsou veřejná). Demo používá **fiktivní značky a simulovaná čísla**. |

## Struktura

```
src/dopamine_king/   scoring, ingest, research, analysis, lab, generate, guru, server, cli
web/                 hra (zdroje, testy), web/dist = sestavený jediný HTML soubor
docs/                vize, hra, architektura, metodika, sběr dat a právo, roadmapa (česky)
tests/               Python (unittest), web/tests = JavaScript (node --test)
```

Dokumentace: [vize](docs/01-vize.md), [herní design](docs/02-hra.md), [architektura](docs/03-architektura.md), [metodika](docs/04-metodika.md), [sběr dat a právo](docs/05-scraping-a-pravo.md), [roadmapa](docs/06-roadmapa.md).

## Testy

```bash
make test        # Python (unittest) + JavaScript (node --test)
make lint-dash   # projektové pravidlo: žádná dlouhá pomlčka v žádném souboru
```

## Poctivost a limity

- **Dopamine Score je heuristika**, ne měření mozku ani záruka výkonu. Smysl má jako pořadí a vůči korpusu.
- **Demo čísla jsou simulovaná**; hra to na každém odhalení říká.
- **Žádné automatické publikování.** Výstup je koncept pro člověka; quality gate blokuje články bez vlastní zkušenosti.
- **Právo:** sběr respektuje `robots.txt` a rezervaci práv TDM, ukládá jen metadata a krátký výňatek. Není to právní poradenství, viz [docs/05-scraping-a-pravo.md](docs/05-scraping-a-pravo.md).
- Licence zatím není určena: rozhodnutí je na majiteli repozitáře.
