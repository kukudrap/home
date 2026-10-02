# Architektura

Jádro je v Pythonu 3.11 **bez třetích knihoven** (jen standardní knihovna), hra je jeden HTML soubor bez frameworků. Jediná volitelná závislost je `anthropic` pro psaní prózy modelem Claude.

## Tok dat

```
 zdroje veřejného obsahu                       vaše analytika (CSV)
 (feedy, sitemapy, API)                                |
        |                                              |
        v                                              v
 ingest/  robots + TDM + limity ------------>  store.py (SQLite)  <--- synth.py (demo)
        |                                              |
        |                                              v
        |                              analysis/  Success Index -> benchmark -> vzory -> kalibrace
        |                                              |
 research/  OpenAlex, Crossref, arXiv -> ledger        |      scoring.py + data/scoring_spec.json
        |        (taktiky <-> studie, grade A-D)       |             |  (sdílená specifikace)
        v                                              v             v
 +--------------------- generate/ ----------------------------------------------+
 | Brief -> builder -> Skeleton (sloty) -> Writer (offline | Claude) -> Draft    |
 |       -> validátor formátu + Trust Shield + SEO/GEO skóre -> Pack            |
 +-----------------------------------------------------------------------------+
        |                       |                              |
        v                       v                              v
 guru/ plán (4 týdny)    lab/ A/B, bandité, simulátor     webdata.py -> web/ (hra)
                                                                |
                                  server.py (lokální JSON API) <-+
```

## Moduly

| Balíček nebo soubor | Odpovědnost |
|---|---|
| `models.py`, `store.py`, `net.py`, `config.py` | Datové třídy, SQLite úložiště, HTTP vrstva (opakování, limity, cache) s vyměnitelným `Fetcher` |
| `scoring.py` + `data/scoring_spec.json` | Dopamine Score; slovníky cs a en jsou **sdílené** s JavaScriptovým portem |
| `ingest/` | Šetrný sběr: `robots.py`, `polite.py` (TDM), `feeds.py`, `sitemaps.py`, `extract.py` (JSON-LD, OG), `registry.py`, `pipeline.py`, `signals.py` (HN, import CSV) |
| `analysis/` | Success Index, benchmark, pattern mining, kalibrace, porovnání hooků, lineární algebra v čistém Pythonu |
| `lab/` | A/B testy, Bayes, velikost vzorku, nahlížení, bandité, simulátor publika |
| `research/` | Klienti OpenAlex, Crossref, arXiv a PubMed, hodnocení studií, taxonomie taktik, ledger a jeho ověřování |
| `generate/` | `hooks`, `formats` (registr), `social`, `video`, `ads`, `seo`, `geo`, `longform`, `guard` (Trust Shield), `claims` (profil tvrzení oboru), `visibility`, `providers`, `packs` |
| `verticals/` + `data/verticals/<id>/` | **Obor jako data** (první je `pbm`, edice MITO LIGHT): kohorty, profil tvrzení a mapa tvrzení, registr značek a studií, vzorová zadání, strategie, obsah hry. Načítá je `load_vertical(id)`. |
| `guru/` | Čtyřtýdenní plán: pilíře, kanály, kalendář, experimenty, GEO úkoly |
| `webdata.py`, `web/`, `scripts/build_web.py` | Datový balík pro hru a samotná hra jako jeden HTML soubor |
| `server.py`, `cli.py` | Lokální API a příkaz `kingctl` |
| `synth.py` | Syntetický korpus fiktivních značek se **zasazenými efekty** |

## Klíčová rozhodnutí

1. **Skeleton a Writer.** Každý formát je builder, který z `Brief` vytvoří `Skeleton`: deterministickou strukturu a pojmenované `Slot`y pro prózu (s limity znaků a slov). `Writer` sloty vyplní. `OfflineWriter` používá jen výchozí hodnoty a **nikdy nevymýšlí text**, nevyplněné sloty zůstanou jako `[[ADD: ...]]`. `FileWriter` bere texty slotů z JSON souboru (`--writer file --fills`; šablonu s pokyny a limity napíše `--emit-slots`), takže prózu může napsat člověk nebo jakýkoli jiný model a validátory ji kontrolují stejně. `AnthropicWriter` zavolá Claude jednou pro všechny sloty a nechá vrátit JSON podle schématu, zkontroluje limity a případně slot opraví. Struktura, limity a kontroly jsou tedy stejné bez modelu i s ním, a testují se bez sítě.
2. **Jedna specifikace skóre pro Python i JavaScript.** Algoritmus je záměrně jednoduchý (tokeny, slovníky, saturační funkce). Python je referenční implementace, JS port musí projít 110 "golden" případů z `web/tests/golden.json`.
3. **Syntetický korpus se zasazenými efekty.** Reálné výkonové údaje značek nejsou veřejné a plné texty nelze distribuovat, proto je demo postavené na fiktivních značkách. Protože známe skutečné efekty, **testujeme, zda je analytika dokáže zpětně najít** (a najde).
4. **Vyměnitelný `Fetcher`.** Veškerá síť jde přes jedno rozhraní. Testy dosazují `FakeFetcher`, produkce `HttpFetcher` s opakováním, limity a cache, obalený `PoliteFetcher` s robots.txt a TDM.
5. **Žádné automatické publikování.** Výstup je koncept. Trust Shield a quality gate záměrně blokují články bez vlastní zkušenosti.
6. **Poctivost čísel.** Každé skóre má vysvětlení (zásahy, tipy), každý výsledek ze simulace nese štítek `simulated`, každá studie stav ověření.
7. **Obor jako data, ne jako kód.** Zaměření na konkrétní obor (fotobiomodulace, MITO LIGHT) je soubor JSON v `data/verticals/<id>/`: kohorty, témata tvrzení, seznamy zakázaných výrazů, registr studií a značek, zadání. Obecný stroj se nemění, další obor je další složka. Python načítá data při spuštění, hra dostane stejná data v datovém balíku.
8. **Profil tvrzení (`claims_profile`).** Zadání (`Brief`) nese `claims_profile`: `general` (výchozí) nebo `wellness` (nezdravotnický přístroj). Profil wellness přidává pravidla Trust Shieldu (`CLAIM_MEDICAL`, `DISEASE_MENTION`, `STATUS_CLAIM` a další), patičku s bezpečnostním upozorněním a filtr hooků. Stejný kontrolor běží v Pythonu (`generate/claims.py`) i v JavaScriptu (`web/src/claims.js`) a shodu hlídá 187 "golden" případů v `web/tests/claims.golden.json`. Pravidla hlídají **slova a jejich vzdálenost**, ne význam.

## Jak rozšířit

- **Nový formát:** napište `build_<id>(brief, *, hook=None, options=None) -> Skeleton` a `validate(draft)`, přidejte `FormatSpec` do `FORMAT_SPECS` modulu. Registr ho najde sám.
- **Nový jazyk:** doplňte blok v `scoring_spec.json` (stopslova, slovníky, zahájení otázek); JS port ho načte beze změny kódu.
- **Nový zdroj signálů:** funkce `dict[str, float]` pro URL (viz `ingest/signals.py`); název signálu a váha v `analysis/success.py`.
- **Nový obor:** zkopírujte složku `data/verticals/pbm/`, upravte `vertical.json`, `claims.json`, `guard.json`, `ledger.json`, `briefs.json` a další; registr (`list_verticals`) ji najde sám. Testy v `tests/test_verticals.py` ověřují strukturu i obsah (například že studie bez ověření nezvedne štítek síly důkazů).
- **Jiný model:** třída s metodou `fill(skeleton, brief) -> dict[str, str]` (a volitelně `revise`).

## Konfigurace (prostředí)

| Proměnná | Význam |
|---|---|
| `KING_HOME` | Pracovní adresář (výchozí `.king`) |
| `KING_DB`, `KING_CACHE` | Databáze a HTTP cache |
| `KING_CONTACT`, `KING_USER_AGENT` | Identita sběrače (kontakt do User-Agent) |
| `ANTHROPIC_API_KEY` | Klíč pro psaní prózy modelem Claude |
| `KING_MODEL`, `KING_EFFORT` | Přepsání výchozího modelu (`claude-opus-5-5`) a úrovně effortu (`medium`) |

## Testy

`make test` spustí Python (`unittest`) i JavaScript (`node --test`). Pokrývají logiku, kontrakty a okrajové případy offline; **neověřují živé API Anthropic ani živé weby**, proto je provider testován proti atrapě podle dokumentace.
