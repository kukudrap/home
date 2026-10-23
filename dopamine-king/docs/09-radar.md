# MITO LIGHT Radar 2.0

Radar je druhá verze projektu. První verze (hra a generátor) fungovala na simulovaných číslech a pro uživatele byla těžko srozumitelná. Radar dělá jednu věc: ze skutečných dat o vyhledávání ukáže, kde je značka MITO LIGHT na českém trhu a co napsat jako první. Výsledek je jedna stránka v češtině, [web/dist/mito-light-radar.html](../web/dist/mito-light-radar.html).

## Jak to funguje

```
plán hledání (radar/plan.json)
   -> sběr: každé hledání spustí Claude Code s jediným povoleným nástrojem, vyhledáváním na webu
   -> uložení: odkazy přesně tak, jak je nástroj vrátil (radar/snapshots/DATUM/raw/*.json)
   -> analýza: čísla ze seznamů odkazů a ručně sestavených seznamů webů a témat
   -> věty: česká zjištění a úkoly, každé číslo z analýzy
   -> stránka: web/dist/mito-light-radar.html
návrhy textů (radar/drafts.json) -> stejný pisatel a stejný Trust Shield jako ostatní obsah
```

Kód je v `src/dopamine_king/radar/` (`collect.py`, `analyze.py`, `compose.py`, `report.py`, `drafts.py`), příkazy jsou `kingctl radar collect`, `radar drafts` a `radar build`.

## Co je skutečné a co ne

| Co | Odkud |
|---|---|
| Odkazy a jejich pořadí | Skutečný výsledek vyhledávání, uložený beze změny (jen dlouhé pomlčky se nahrazují spojovníkem). |
| Souhrn pod odkazy | Text, který k výsledkům napsal stroj. Může se mýlit a míchat značky. Na stránce je vždy označený a nepoužívá se jako údaj o stránkách. |
| Zařazení webů (lékárna, médium, e-shop) a témat | Úsudek podle názvů a adres, v souborech `domains.json` a `themes.json`, u každého webu s poznámkou. |
| Mapa tvrzení a studie | Registr studií oboru. Síla důkazů se počítá jen z ověřených studií. |
| Návrhy textů | Napsal je Claude z faktů v `drafts.json`. Jsou to koncepty ke kontrole člověkem. |

Hledání se uloží jen tehdy, když nástroj opravdu proběhl s požadovaným dotazem a filtrem domény a hlásí aspoň jedno hledání. Jinak se zahodí a ohlásí. Nic se nedopisuje ani nezaokrouhluje.

## Kontrola proti přímému hledání

Pět uložených hledání jsme zopakovali přímo nástrojem pro vyhledávání a porovnali odkazy (soubory `radar/snapshots/2026-10-23/direct`). Shoda byla 9 z 9, 9 z 10, 9 z 9, 8 z 9 a 9 z 9 odkazů. Test `tests/test_radar_snapshot.py` hlídá, že shoda zůstane nad 80 procenty.

## Limity, které je nutné znát

- Vyhledávač hledá z USA a není to Google.cz ani Seznam. Pořadí a výběr se od českých výsledků mohou lišit. Skutečné pozice ukáže Search Console.
- Jde o jeden snímek. Při dalším hledání se výsledky mírně změní.
- Radar vidí názvy a adresy stránek, ne jejich obsah, protože prostředí, ve kterém běží, nemá přístup na web. Kontrola tvrzení v názvech stránek proto najde míň než kontrola celých textů.
- Filtr domény v hledání je nespolehlivý, když dotaz neobsahuje název značky: vrátí i cizí stránky. Proto dotazy na weby značek název obsahují.
- Některé výsledky nesouvisejí s oborem (součástky, laboratorní činidlo). Seznam `domains.json` je označuje jako nerelevantní a počítají se zvlášť.

## Studie

Čtrnáct záznamů registru bylo ověřeno proti stránkám PubMed, PubMed Central, vydavatelů a repozitářů, které se objevily ve výsledcích. Ověřená studie znamená, že se název, časopis a rok objevily ve veřejném zdroji. Neznamená to, že byl přečten celý text. U každého záznamu je v poznámce, ze kterého hledání (například `study2-barolet2009`) a ze kterého zdroje to plyne. Dva záznamy zůstaly neověřené a poznámka říká proč.

## Kontrola názvů vlastních stránek

Kontrola tvrzení (Trust Shield) hledá slovesa vedle témat. Skutečné názvy stránek mitolight.cz, například "Zvýšení kvality a množství vlasů" nebo "Červené světlo proti vráskám", slovesa nemají, a proto jí unikly. Radar proto používá druhou, jednodušší kontrolu: název se označí, když obsahuje téma z mapy tvrzení a slovo, které slibuje výsledek (seznam v `outcome_words.json`). Označení neříká, že je název špatně. Ukazuje, které stránky má přečíst člověk. Při práci vznikla i oprava pravidel: téma "Růst vlasů" nově zná i vyjádření "množství vlasů" a "kvalita vlasů".

## Jak ho obnovit

```bash
export PYTHONPATH=src
python3 -m dopamine_king radar collect --snapshot radar/snapshots/DATUM      # asi 8 minut, 88 hledání, 4 najednou
python3 -m dopamine_king radar drafts --out radar/drafts/DATUM               # návrhy textů (tři stránky, šest příspěvků)
python3 -m dopamine_king radar build --snapshot radar/snapshots/DATUM --drafts radar/drafts/DATUM
```

Potřebuje nainstalovaný a přihlášený Claude Code (`claude`). Používá váš účet, žádný API klíč se nepředává. Hledání běží s nejlevnějším modelem (`--model haiku`). Přerušený sběr lze spustit znovu, uložená hledání přeskočí. Stránka pro hostitele, který si ji obalí sám (artefakt v aplikaci Claude), se staví přepínačem `--fragment`.

## Jak změnit, co se hledá

Plán je obyčejný soubor `radar/plan.json`: každé hledání má `id`, skupinu, dotaz, případně `domains` (jen tyto weby) a `persona`. Nový dotaz stačí přidat a spustit `radar collect`. Nové weby a témata se zařazují v `domains.json` a `themes.json`.

## Testy

`tests/test_radar_collect.py` (čtení skutečného záznamu nástroje, odmítnutí hledání, které neproběhlo jak mělo), `tests/test_radar_analyze.py`, `tests/test_radar_snapshot.py` (uložená data: každé hledání z plánu je uložené, shoduje se s plánem a s přímým hledáním, žádná dlouhá pomlčka) a `tests/test_radar_report.py` (stránka, věty a návrhy textů; uložená stránka je přesně to, co sestaví kód).
