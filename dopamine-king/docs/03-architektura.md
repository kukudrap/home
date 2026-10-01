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
| `research/` | Klienti OpenAlex, Crossref, arXiv, hodnocení studií, taxonomie taktik, ledger a jeho ověřování |
| `generate/` | `hooks`, `formats` (registr), `social`, `video`, `ads`, `seo`, `geo`, `longform`, `guard` (Trust Shield), `visibility`, `providers`, `packs` |
| `guru/` | Čtyřtýdenní plán: pilíře, kanály, kalendář, experimenty, GEO úkoly |
| `webdata.py`, `web/`, `scripts/build_web.py` | Datový balík pro hru a samotná hra jako jeden HTML soubor |
| `server.py`, `cli.py` | Lokální API a příkaz `kingctl` |
| `synth.py` | Syntetický korpus fiktivních značek se **zasazenými efekty** |

## Klíčová rozhodnutí

1. **Skeleton a Writer.** Každý formát je builder, který z `Brief` vytvoří `Skeleton`: deterministickou strukturu a pojmenované `Slot`y pro prózu (s limity znaků a slov). `Writer` sloty vyplní. `OfflineWriter` používá jen výchozí hodnoty a **nikdy nevymýšlí text**, nevyplněné sloty zůstanou jako `[[ADD: ...]]`. `AnthropicWriter` zavolá Claude jednou pro všechny sloty a nechá vrátit JSON podle schématu, zkontroluje limity a případně slot opraví. Struktura, limity a kontroly jsou tedy stejné bez modelu i s ním, a testují se bez sítě.
2. **Jedna specifikace skóre pro Python i JavaScript.** Algoritmus je záměrně jednoduchý (tokeny, slovníky, saturační funkce). Python je referenční implementace, JS port musí projít 104 "golden" případů z `web/tests/golden.json`.
3. **Syntetický korpus se zasazenými efekty.** Reálné výkonové údaje značek nejsou veřejné a plné texty nelze distribuovat, proto je demo postavené na fiktivních značkách. Protože známe skutečné efekty, **testujeme, zda je analytika dokáže zpětně najít** (a najde).
4. **Vyměnitelný `Fetcher`.** Veškerá síť jde přes jedno rozhraní. Testy dosazují `FakeFetcher`, produkce `HttpFetcher` s opakováním, limity a cache, obalený `PoliteFetcher` s robots.txt a TDM.
5. **Žádné automatické publikování.** Výstup je koncept. Trust Shield a quality gate záměrně blokují články bez vlastní zkušenosti.
6. **Poctivost čísel.** Každé skóre má vysvětlení (zásahy, tipy), každý výsledek ze simulace nese štítek `simulated`, každá studie stav ověření.

## Jak rozšířit

- **Nový formát:** napište `build_<id>(brief, *, hook=None, options=None) -> Skeleton` a `validate(draft)`, přidejte `FormatSpec` do `FORMAT_SPECS` modulu. Registr ho najde sám.
- **Nový jazyk:** doplňte blok v `scoring_spec.json` (stopslova, slovníky, zahájení otázek); JS port ho načte beze změny kódu.
- **Nový zdroj signálů:** funkce `dict[str, float]` pro URL (viz `ingest/signals.py`); název signálu a váha v `analysis/success.py`.
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
