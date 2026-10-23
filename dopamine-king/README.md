# MITO LIGHT Radar 2.0

Radar zjistí ze **skutečného vyhledávání na webu**, jak si vede značka MITO LIGHT na českém trhu, co z toho plyne a co napsat jako první. Výsledek je **jedna stránka**: [web/dist/mito-light-radar.html](web/dist/mito-light-radar.html). Stejnou stránku najdete jako artefakt v aplikaci Claude.

## Co na stránce je (čísla platí pro snímek z 23. 10. 2026)

1. **Sedm zjištění** s číslem, větou, upozorněním a odkazem na hledání, ze kterého vychází.
2. **Šest úkolů na tento týden**, které se dají odškrtávat.
3. **Kde jste vidět**: 47 hledání (značka, kategorie, šest cílových skupin, konkurenti) a co se objevilo na prvním místě.
4. **Kdo je kolem vás**: weby, které se ve výsledcích opakují (lékárna, média, e-shopy, diskuze).
5. **Jak vás vidí vyhledávače a AI**: kolik odkazů při hledání vašeho názvu vede na jinou značku (Mito Red Light) a kdo o vás píše.
6. **Co zveřejňují úspěšné značky**: 127 stránek z 15 webů rozdělených podle témat, vedle vašeho webu.
7. **Co smíte tvrdit**: mapa tvrzení (19 témat), titulky vašich stránek, které slibují výsledek, a tvrzení konkurence.
8. **Emoční claimy**: 106 hotových vět (slogany, nadpisy, příspěvky, texty v aplikaci, příběh značky) postavených na těšení, rituálu, překvapení, příběhu, pocitu, příslušnosti a volbě. Každá prošla kontrolou tvrzení bez chyby i varování a žádná netvrdí účinek na tělo, náladu ani hormony. Stránka vysvětluje, proč tam není slovo dopamin.
9. **Devět návrhů textů** (tři stránky a šest příspěvků, po jednom na cílovou skupinu). Každý prošel kontrolou tvrzení.
10. **Studie**: 39 ze 41 je ověřeno veřejnými zdroji.
11. **Co chybí a co potřebuji od vás.**

## Odkud jsou data

- **88 skutečných hledání na webu** ze dne 23. 10. 2026. Každé spustil nástroj Claude Code s jediným povoleným nástrojem, vyhledáváním. Uložené odkazy jsou přesně to, co nástroj vrátil (složka [radar/snapshots/2026-10-23](radar/snapshots/2026-10-23)). Hledání se uloží jen tehdy, když opravdu proběhlo s požadovaným dotazem.
- **Žádná simulovaná data.** Co se nepodařilo zjistit, je na stránce v části "Co chybí".
- **Kontrola:** pět hledání jsme zopakovali přímo nástrojem pro vyhledávání a porovnali s uloženými (shodné odkazy: 9 z 9, 9 z 10, 9 z 9, 8 z 9, 9 z 9). Šesté přímé hledání zachytilo větu strojového shrnutí o vztahu k Mito Red Light.
- **Limity:** vyhledávač hledá z USA, takže to není Google.cz ani Seznam. Vidíme názvy a adresy stránek, ne jejich obsah. Souhrny, které nástroj přidává, píše stroj. Zařazení webů do skupin a témat je úsudek podle názvů a adres.

## Jak radar obnovit

Napište Claudovi (v Claude Code na webu nebo v aplikaci): **"obnov radar"**. Provede tři příkazy a stránku znovu postaví. Spotřebuje jen vaše předplatné Claude, žádný API klíč.

```bash
export PYTHONPATH=src
python3 -m dopamine_king radar collect --snapshot radar/snapshots/DATUM     # hledání na webu (asi 8 minut)
python3 -m dopamine_king radar drafts --out radar/drafts/DATUM              # návrhy textů pro Claude účet
python3 -m dopamine_king radar build --snapshot radar/snapshots/DATUM --drafts radar/drafts/DATUM
```

Plán hledání, seznam webů a témat jsou obyčejné soubory ve složce [radar](radar): `plan.json`, `domains.json`, `themes.json`, `outcome_words.json`, `drafts.json`. Co se má hledat, změníte tam, ne v kódu. Podrobnosti jsou v [docs/09-radar.md](docs/09-radar.md).

Emoční claimy jsou v souboru [radar/claims_emotional.json](radar/claims_emotional.json). Větu přidáte nebo přepíšete tam. Test `tests/test_radar_emotion.py` pak ověří, že prošla kontrolou tvrzení a opírá se jen o fakta ze souboru o značce. Stránku znovu postaví třetí příkaz výše.

## Co potřebuji od vás

- Potvrdit, že MITO LIGHT a Mito Red Light jsou dvě různé značky a že mitolight.com a mitolight.co.uk jsou vaše weby.
- Export ze Search Console a ze Seznam Webmaster. Radar hledá z USA, vaše skutečné pozice znáte jen vy.
- **Zapnout internet pro prostředí**, ve kterém radar běží (nastavení prostředí, Network access). Zatím vidí jen názvy stránek, ne jejich text. S internetem zkontroluji celé texty vašeho webu a konkurence a stáhnu abstrakty studií.
- Vzdálenost a způsob měření ozáření u každého modelu.
- Rozhodnout o názvu **Červená hodina** (zda ho lze používat jako značku) a projít věty se štítkem Potvrdit v části "Než něco zveřejníte" na stránce.

## Starší části projektu

Dopamine King vznikl jako stroj na obsah zabalený do hry (verze 1). Hra, generátor obsahu ve 28 formátech, kontrola tvrzení (Trust Shield) a mapa tvrzení fungují dál a radar je používá. Hra pracuje se **simulovanými čísly** a na každém odhalení to říká. Radar na ní nezávisí.

> **English TL;DR.** MITO LIGHT Radar 2.0 builds a market picture of the Czech brand MITO LIGHT from real web search results only: 88 searches run through the logged-in Claude Code with only the WebSearch tool, links stored exactly as returned, nothing simulated. It reports search visibility, who surrounds the brand, brand-name confusion with Mito Red Light, what top brands publish, a claims check of real page titles, nine reviewed drafts and the study ledger (39 of 41 verified). Underneath is the older Dopamine King engine: a Python core without third-party dependencies, 28 content formats, a Trust Shield claims profile for non-medical wellness devices and a single-file game. The page also holds 106 emotional, experience-based claims built on anticipation, ritual, surprise, story, feeling, belonging and choice; each passes the Trust Shield with no error or warning, none claims an effect on body, mood or hormones, and the page explains why the word dopamine is not used (it would be a health claim and rests on a myth).

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

# s modelem Claude přes API (potřebuje ANTHROPIC_API_KEY a `pip install anthropic`, účtuje se zvlášť od předplatného)
python3 -m dopamine_king forge ... --writer anthropic --formats seo_article,linkedin_post,short_video_script
python3 -m dopamine_king formats                  # všech 28 formátů

# přes váš Claude účet (Max, Pro) bez API klíče: píše lokální Claude Code, `claude` musí být nainstalovaný a přihlášený
python3 -m dopamine_king forge --brand Zorvia --topic "běžecké boty" --audience "začínající běžci" --lang cs \
    --formats instagram_caption,seo_article --writer claude-code --tier balanced --out out/zorvia

# bez API klíče a bez Claude Code: vlastní pisatel (vy nebo libovolný jazykový model) vyplní sloty a štít je zkontroluje
python3 -m dopamine_king forge --brand Zorvia --topic "běžecké boty" --audience "začínající běžci" --lang cs \
    --formats instagram_caption,seo_article --emit-slots sloty.json      # šablona: každý slot má zadání a limity
python3 -m dopamine_king forge --brand Zorvia --topic "běžecké boty" --audience "začínající běžci" --lang cs \
    --formats instagram_caption,seo_article --writer file --fills sloty.json --out out/zorvia
python3 -m dopamine_king guru plan --brand Zorvia --topic "běžecké boty" --audience "začínající běžci"
```

### Edice MITO LIGHT (fotobiomodulace)

Obecný stroj má první **obor** (vertical): fotobiomodulaci (PBM, červené a blízké infračervené světlo) pro značku **MITO LIGHT**. Obor je soubor dat v `src/dopamine_king/data/verticals/pbm/`, obecný stroj se nemění. Přidává:

- profil tvrzení **wellness** pro nezdravotnický přístroj: Trust Shield blokuje diagnostiku, léčbu, prevenci a zmírnění nemocí, stavové fráze ("schváleno", "klinicky prokázáno"), absolutní bezpečnost a nahrazování lékaře, a upozorní na přínosy bez opatrné formulace, sliby výsledků, dávky mimo návod a chybějící bezpečnostní upozornění,
- **mapu tvrzení** (19 témat, pět tříd) se silou důkazů počítanou jen z ověřených studií,
- registr 41 záznamů o studiích (39 ověřených, 2 označené jako neověřené s vysvětlením), registr 26 značek a organizací oboru, vzorová zadání MITO LIGHT česky (vykání) a anglicky, šest cílových skupin se zvláštní péčí o zranitelné a obsah hry (Boss s kontrolou tvrzení, Mýtus nebo fakt, mapa tvrzení v Trezoru).

```bash
python3 -m dopamine_king demo --vertical pbm                        # prohlídka edice na simulovaných datech
python3 -m dopamine_king evidence claims --vertical pbm             # co smím říct a s jakou silou důkazů
python3 -m dopamine_king forge --vertical pbm --sample mito-light-cs --writer offline --out out/mito-cs
python3 -m dopamine_king guru plan --vertical pbm --sample mito-light-cs
python3 -m dopamine_king forge --vertical pbm --sample mito-light-seniors-cs --writer offline --out out/seniors   # cílové skupiny: fitness, biohacker, beauty, everyday, tech, seniors
python3 -m dopamine_king audit stranka.txt                          # kontrola existujícího textu, kód 1 při chybě
python3 -m dopamine_king evidence search "photobiomodulation sleep" --sources pubmed   # nové studie (síť)
```

Hotová ukázka textů pro MITO LIGHT (pět formátů, napsal Claude, Štít důvěry: 0 chyb): [examples/mito-light-cs](examples/mito-light-cs/README.md). Podrobnosti v [docs/07-fotobiomodulace.md](docs/07-fotobiomodulace.md), regulace a zdroje v [docs/08-regulace-pbm.md](docs/08-regulace-pbm.md). **Pravidla nejsou právní poradenství.** Zjištění o stavu přístroje (nezdravotnický prostředek) vychází z jediného nepotvrzeného zdroje, viz docs/08.

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
| Hra (arena, boss, laboratoř, vault) | Hotovo; JS skóre je shodné s Pythonem (110 "golden" případů) |
| 28 formátů obsahu, Trust Shield, SEO a GEO skóre | Hotovo; offline režim nevymýšlí prózu |
| Psaní prózy modelem Claude | Napsáno podle dokumentace a **otestováno proti atrapě**; živé API zde nebylo možné vyzkoušet (bez klíče) |
| Šetrný sběr, import analytik | Hotovo, otestováno offline i proti lokálnímu HTTP serveru; **živý sběr vyžaduje síť** (prostředí, kde kód vznikl, povolilo ze 111 značek jen jednu) |
| Ledger studií | 32 záznamů; **23 potvrzeno** veřejnými zdroji (název, časopis, rok, DOI), zbytek má u sebe poznámku, jak daleko ověření došlo. `evidence verify` ověří přes Crossref. |
| Edice MITO LIGHT: profil wellness, mapa tvrzení, hra | Hotovo a otestováno na příkladech správných i nesprávných formulací a na 238 "golden" případech, které musí dát v Pythonu i v JavaScriptu stejný výsledek. **Pravidla je třeba nechat zkontrolovat regulatorním poradcem.** |
| Registr důkazů PBM | 41 záznamů: 39 ověřených veřejnými zdroji (14 z nich radarem 2026-10-23: název, časopis a rok v PubMed, PubMed Central nebo u vydavatele), 2 neověřené s poznámkou proč. Závěry jsou čtené z abstraktů a shrnutí, ne z plných textů. |
| Fakta o MITO LIGHT | Z veřejných zdrojů (výsledky vyhledávání, ne z otevřených stránek), **k potvrzení značkou**; čísla a parametry si značka musí schválit. |
| MITO LIGHT Radar 2.0 | **Skutečná data**: 88 hledání na webu ze dne 2026-10-23, nic simulovaného. Vidí názvy a adresy stránek, ne jejich obsah (prostředí nemá přístup na web). |
| Reálná data značek ve hře | Nejsou v repozitáři (autorská práva a výkonnostní čísla nejsou veřejná). Hra používá **fiktivní značky a simulovaná čísla**. |

## Struktura

```
radar/               plán hledání, seznamy webů a témat, uložená hledání (snapshots) a návrhy textů (drafts)
src/dopamine_king/   scoring, ingest, research, analysis, lab, generate, guru, radar, server, cli
web/                 hra (zdroje, testy), web/dist = sestavené jednosouborové stránky (hra a radar)
docs/                vize, hra, architektura, metodika, sběr dat a právo, roadmapa, edice MITO LIGHT, regulace (česky)
examples/            hotová ukázka textů pro MITO LIGHT (fills.json a výsledek v out/)
tests/               Python (unittest), web/tests = JavaScript (node --test)
```

Dokumentace: [vize](docs/01-vize.md), [herní design](docs/02-hra.md), [architektura](docs/03-architektura.md), [metodika](docs/04-metodika.md), [sběr dat a právo](docs/05-scraping-a-pravo.md), [roadmapa](docs/06-roadmapa.md), [edice MITO LIGHT](docs/07-fotobiomodulace.md), [regulace reklamy](docs/08-regulace-pbm.md), [radar](docs/09-radar.md).

## Testy

```bash
make test        # Python (unittest) + JavaScript (node --test)
make lint-dash   # projektové pravidlo: žádná dlouhá pomlčka v žádném souboru
```

Prohlížečový test celé hry (Playwright + Chromium, mimo CI, protože potřebuje prohlížeč):

```bash
python3 -m dopamine_king build-web
node web/tests/smoke.playwright.mjs     # projde všechny pohledy v cs i en, světlém i tmavém režimu a na mobilu, včetně kontroly tvrzení
                                        # (potřebuje balíček playwright; když je nainstalovaný globálně, nastavte NODE_PATH na jeho složku)
```

## Poctivost a limity

- **Dopamine Score je heuristika**, ne měření mozku ani záruka výkonu. Smysl má jako pořadí a vůči korpusu.
- **Demo čísla jsou simulovaná**; hra to na každém odhalení říká.
- **Žádné automatické publikování.** Výstup je koncept pro člověka; quality gate blokuje články bez vlastní zkušenosti.
- **Právo:** sběr respektuje `robots.txt` a rezervaci práv TDM, ukládá jen metadata a krátký výňatek. Není to právní poradenství, viz [docs/05-scraping-a-pravo.md](docs/05-scraping-a-pravo.md).
- **Edice MITO LIGHT hlídá slova, ne záměr.** Pravidla poznají zakázané formulace, ne obrázky, hashtagy ani celkový dojem; schválení textu před zveřejněním zůstává na člověku. Číslo studie v mapě tvrzení neznamená, že se týká právě vašeho přístroje.
- Licence zatím není určena: rozhodnutí je na majiteli repozitáře.
