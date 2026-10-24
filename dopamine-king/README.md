# Dopamine King: hra o skutečném trhu MITO LIGHT

Dopamine King je hra v prohlížeči, která učí číst trh značky MITO LIGHT na skutečných datech. Souboje, soupeři a karty vycházejí z uložených hledání na webu, z registru ověřených studií a ze souboru o značce. U každé položky je vidět zdroj a datum a většina odkazuje na skutečnou stránku.

Hra je jeden soubor: [web/dist/dopamine-king.html](web/dist/dopamine-king.html). Otevřete ho dvojklikem a nic se nikam neodesílá. Stejná hra je publikovaná jako artefakt v aplikaci Claude.

## Co ve hře najdete

- Aréna má tři druhy soubojů. U pořadí hádáte, který ze dvou výsledků jednoho hledání byl výš. U výskytu hádáte, který web se objevil ve víc hledáních. U tvrzení hádáte, který ze dvou skutečných titulků by kontrola tvrzení zastavila. Po odpovědi uvidíte, jak to dopadlo, a odkaz na skutečnou stránku.
- Boss je skutečný titulek konkurenta nebo média z uložených hledání. Napíšete vlastní hook ke stejnému tématu a hra živě ukáže Dopamine Score, riziko clickbaitu a kontrolu tvrzení.
- Trh shrnuje, co hledání ukázala: sedm zjištění s číslem a zdrojem, šest úkolů, všech 88 uložených hledání s odkazy, kdo zaplňuje výsledky, co tvrdí trh a jak data vznikla.
- Laboratoř nabízí skutečný A/B test. Naplánujete vzorek, zapíšete skutečná čísla a hra je vyhodnotí. K tomu patří dvě výukové simulace.
- Trezor drží karty, 73 studií s odkazy (ověřené i neověřené), mapu tvrzení a hru Mýtus, nebo fakt.
- Claimy je banka 106 emočních vět, které prošly kontrolou tvrzení.
- Kovárna a Guru ukazují devět návrhů textů pro značku a plán obsahu.

XP dostanete za souboje, bosse a testy. Splněný úkol z Trhu vyplatí 50 XP jednou a každý třetí úkol otevře truhlu. Úkoly odškrtáváte sami, hra je nemůže ověřit.

## Odkud jsou data

- 88 skutečných hledání na webu ze dne 23. 10. 2026. Každé spustil nástroj Claude Code s jediným povoleným nástrojem, vyhledáváním. Uložené odkazy jsou přesně to, co nástroj vrátil (složka [radar/snapshots/2026-10-23](radar/snapshots/2026-10-23)). Hledání se uloží jen tehdy, když opravdu proběhlo s požadovaným dotazem.
- Z těchto hledání Python spočítá souboje, soupeře a karty ([src/dopamine_king/radar/realbundle.py](src/dopamine_king/radar/realbundle.py)). Testy hlídají, že počty, pořadí a verdikty kontroly tvrzení sedí s uloženými daty.
- Studie jsou z registru oboru: 39 ze 41 je ověřeno veřejnými zdroji. Fakta o značce jsou z veřejných popisů a značka je zatím nepotvrdila.
- Pět hledání bylo zopakováno přímo nástrojem pro vyhledávání a porovnáno s uloženými (shodné odkazy: 9 z 9, 9 z 10, 9 z 9, 8 z 9, 9 z 9).

## Co hra neumí

- Dopamine Score čte slova. Na skutečných dvojicích v Aréně vybral výše umístěný výsledek v 50,3 % případů, kdy dokázal dvojici rozlišit (74 ze 147). Hod mincí by dal 50 %. Hra to říká, pořadí skóre nepředpovídá.
- Hledání běžela z USA, takže nejde o Google.cz ani Seznam. Nástroj ukazuje názvy a adresy stránek, ne jejich obsah, a souhrny, které přidává, píše stroj.
- Zařazení webů a témat do skupin je úsudek podle názvů a adres.
- Dvě minihry v Laboratoři (Nenahlížejte, Zahrada banditů) jsou simulace s vymyšlenými daty a říkají to.
- Kontrola tvrzení čte slova, ne smysl. Každý text před zveřejněním musí přečíst člověk.

## Sestavení hry

```bash
export PYTHONPATH=src
python3 -m dopamine_king build-web              # hra se skutečnými daty z nejnovějšího snímku
python3 -m dopamine_king build-web --synthetic  # starší demo se simulovanými daty (pro testy a ukázku)
```

Nová data získáte tak, že napíšete Claudovi (v Claude Code na webu nebo v aplikaci): "obnov radar". Provede tři příkazy z následující části a potom sestaví i hru příkazem `build-web`. Spotřebuje jen vaše předplatné Claude, žádný API klíč.

## Radar jako samostatná stránka

Stejná data jsou i na jedné stránce, [web/dist/mito-light-radar.html](web/dist/mito-light-radar.html): zjištění, úkoly na tento týden, viditelnost značky, konkurence, záměna názvu s Mito Red Light, témata úspěšných značek, mapa tvrzení, emoční claimy, návrhy textů, studie a to, co chybí. Podrobnosti jsou v [docs/09-radar.md](docs/09-radar.md).

```bash
export PYTHONPATH=src
python3 -m dopamine_king radar collect --snapshot radar/snapshots/DATUM     # hledání na webu (asi 8 minut)
python3 -m dopamine_king radar drafts --out radar/drafts/DATUM              # návrhy textů pro Claude účet
python3 -m dopamine_king radar build --snapshot radar/snapshots/DATUM --drafts radar/drafts/DATUM
```

Plán hledání, seznam webů a témat jsou obyčejné soubory ve složce [radar](radar): `plan.json`, `domains.json`, `themes.json`, `outcome_words.json`, `drafts.json`. Co se má hledat, změníte tam, ne v kódu. Emoční claimy jsou v souboru [radar/claims_emotional.json](radar/claims_emotional.json). Větu přidáte nebo přepíšete tam a test `tests/test_radar_emotion.py` ověří, že prošla kontrolou tvrzení a opírá se jen o fakta ze souboru o značce.

## Co je potřeba od značky

- Potvrdit, že MITO LIGHT a Mito Red Light jsou dvě různé značky a že mitolight.com a mitolight.co.uk jsou její weby.
- Export ze Search Console a ze Seznam Webmaster. Radar hledá z USA, skutečné pozice zná jen značka.
- Zapnout internet pro prostředí, ve kterém radar běží (nastavení prostředí, Network access). Zatím vidí jen názvy stránek. S internetem může zkontrolovat celé texty webu a konkurence a stáhnout abstrakty studií.
- Vzdálenost a způsob měření ozáření u každého modelu.
- Rozhodnout o názvu Červená hodina (zda ho lze používat jako značku) a projít věty se štítkem Potvrdit v části Claimy.

## Starší části projektu

Dopamine King vznikl jako stroj na obsah zabalený do hry. Generátor obsahu ve 28 formátech, kontrola tvrzení (Trust Shield) a mapa tvrzení jsou součástí hry i radaru. Starší demo se simulovanými daty zůstává pro testy a pro ukázku jako `build-web --synthetic`.

> **English TL;DR.** Dopamine King is a single-file browser game for the Czech brand MITO LIGHT, built on real data only: 88 web searches run through Claude Code with the WebSearch tool as its only tool (links stored exactly as returned), a verified study ledger and a brand file. The Arena has three kinds of duel (which result ranked higher, which site appeared in more searches, which real page title the claims check would stop), the Boss is a real rival title, the Market view holds the findings, the stored searches and six tasks, and the Lab runs a real A/B test next to two teaching simulations that say they are simulated. The Dopamine Score picked the better placed result in 50.3 % of the pairs it could tell apart, which is a coin toss, and the game says so. Underneath is a Python core without third-party dependencies, 28 content formats and a Trust Shield claims profile for non-medical wellness devices. The same data also come as a one-page report, and 106 emotional, experience-based claims pass the Trust Shield without any error or warning.

## Rychlý start

Potřebujete Python 3.11 a (pro testy hry) Node 22. Žádné `pip install`.

```bash
cd dopamine-king
export PYTHONPATH=src

python3 -m dopamine_king demo              # celý řetězec na syntetických datech, offline, pár vteřin
python3 -m dopamine_king build-web         # postaví web/dist/dopamine-king.html (jeden soubor, skutečná data)
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
| Hra (aréna, boss, trh, laboratoř, trezor, claimy) | Hotovo a postavená na skutečných datech z uložených hledání. JS skóre je shodné s Pythonem (110 "golden" případů). |
| 28 formátů obsahu, Trust Shield, SEO a GEO skóre | Hotovo; offline režim nevymýšlí prózu |
| Psaní prózy modelem Claude | Napsáno podle dokumentace a **otestováno proti atrapě**; živé API zde nebylo možné vyzkoušet (bez klíče) |
| Šetrný sběr, import analytik | Hotovo, otestováno offline i proti lokálnímu HTTP serveru; **živý sběr vyžaduje síť** (prostředí, kde kód vznikl, povolilo ze 111 značek jen jednu) |
| Ledger studií | 32 záznamů; **23 potvrzeno** veřejnými zdroji (název, časopis, rok, DOI), zbytek má u sebe poznámku, jak daleko ověření došlo. `evidence verify` ověří přes Crossref. |
| Edice MITO LIGHT: profil wellness, mapa tvrzení, hra | Hotovo a otestováno na příkladech správných i nesprávných formulací a na 238 "golden" případech, které musí dát v Pythonu i v JavaScriptu stejný výsledek. **Pravidla je třeba nechat zkontrolovat regulatorním poradcem.** |
| Registr důkazů PBM | 41 záznamů: 39 ověřených veřejnými zdroji (14 z nich radarem 2026-10-23: název, časopis a rok v PubMed, PubMed Central nebo u vydavatele), 2 neověřené s poznámkou proč. Závěry jsou čtené z abstraktů a shrnutí, ne z plných textů. |
| Fakta o MITO LIGHT | Z veřejných zdrojů (výsledky vyhledávání, ne z otevřených stránek), **k potvrzení značkou**; čísla a parametry si značka musí schválit. |
| MITO LIGHT Radar 2.0 | **Skutečná data**: 88 hledání na webu ze dne 2026-10-23, nic simulovaného. Vidí názvy a adresy stránek, ne jejich obsah (prostředí nemá přístup na web). |
| Výkonnostní čísla značek | Nejsou veřejná, proto nejsou v repozitáři. Hra pracuje s tím, co je vidět ve výsledcích hledání: titulky, pořadím a adresami. Demo se simulovanými čísly zůstává jako `build-web --synthetic`. |

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
node web/tests/smoke.playwright.mjs     # sestaví demo i skutečnou edici a projde všechny pohledy v cs i en, světlém i tmavém režimu a na mobilu
                                        # (potřebuje balíček playwright; když je nainstalovaný globálně, nastavte NODE_PATH na jeho složku)
node web/tests/smoke.playwright.mjs --real-only    # jen skutečná edice: tři druhy soubojů, Trh, úkoly, skutečný A/B test
```

## Poctivost a limity

- **Dopamine Score je heuristika**, ne měření mozku ani záruka výkonu. Na skutečných dvojicích v Aréně předpovídá pořadí stejně spolehlivě jako hod mincí a hra to říká.
- **Čísla ve hře jsou z uložených hledání.** Jen dvě minihry v Laboratoři jsou simulace a hlásí to. Demo edice (`build-web --synthetic`) označuje všechna čísla jako simulovaná.
- **Žádné automatické publikování.** Výstup je koncept pro člověka; quality gate blokuje články bez vlastní zkušenosti.
- **Právo:** sběr respektuje `robots.txt` a rezervaci práv TDM, ukládá jen metadata a krátký výňatek. Není to právní poradenství, viz [docs/05-scraping-a-pravo.md](docs/05-scraping-a-pravo.md).
- **Edice MITO LIGHT hlídá slova, ne záměr.** Pravidla poznají zakázané formulace, ne obrázky, hashtagy ani celkový dojem; schválení textu před zveřejněním zůstává na člověku. Číslo studie v mapě tvrzení neznamená, že se týká právě vašeho přístroje.
- Licence zatím není určena: rozhodnutí je na majiteli repozitáře.
