# MITO LIGHT Radar 2.0

Radar zjišťuje ze skutečných dat o vyhledávání, kde je značka MITO LIGHT na českém trhu a co napsat jako první. Výsledek je jedna stránka v češtině, [web/dist/mito-light-radar.html](../web/dist/mito-light-radar.html). Stejná data pohánějí i hru [web/dist/dopamine-king.html](../web/dist/dopamine-king.html).

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

Kód je v `src/dopamine_king/radar/` (`collect.py`, `analyze.py`, `compose.py`, `report.py`, `drafts.py`, `emotion.py`, `realbundle.py`), příkazy jsou `kingctl radar collect`, `radar drafts` a `radar build`.

## Jak data použije hra

`realbundle.py` vezme nejnovější snímek, stejné analýzy jako stránka radaru a registr studií a postaví z nich datový balíček hry. Je deterministický (stejný snímek dá stejný balíček), nic v něm není simulované a každý souboj nese svůj zdroj.

- Souboje o pořadí: dvojice výsledků jednoho hledání od dvou různých webů. Vítěz je ten, kdo byl výš. Odhad Dopamine Score se počítá ze skutečných titulků a překvapení je souboj, ve kterém si model byl jistý (rozdíl skóre aspoň 8 bodů) a spletl se.
- Souboje o výskyt: dvojice webů, které se objevily v různém počtu z 47 hledání na českém trhu. Počty se dají zpětně spočítat z uložených hledání.
- Souboje o tvrzení: skutečný titulek, který kontrola tvrzení zastaví, proti titulku bez jediné připomínky. Verdikt počítá stejná kontrola jako v Boss souboji.
- Bossové jsou nejlépe umístěné titulky konkurentů a médií. Měřítkem je skóre skutečných titulků.
- Úkoly a zjištění v Trhu jsou věty z `compose.py`, tedy stejné jako na stránce radaru.
- Skutečný A/B test v Laboratoři používá dvojice vět z banky emočních claimů.

Přesnost Dopamine Score se měří na všech dvojicích, ne jen na odehraných: ze 201 dvojic dokázalo skóre rozlišit 147 a vybralo výše umístěný výsledek v 74 případech (50,3 %). Hra tento údaj ukazuje u každého souboje o pořadí.

## Co je skutečné a co ne

| Co | Odkud |
|---|---|
| Odkazy a jejich pořadí | Skutečný výsledek vyhledávání, uložený beze změny (jen dlouhé pomlčky se nahrazují spojovníkem). |
| Souhrn pod odkazy | Text, který k výsledkům napsal stroj. Může se mýlit a míchat značky. Na stránce je vždy označený a nepoužívá se jako údaj o stránkách. |
| Zařazení webů (lékárna, médium, e-shop) a témat | Úsudek podle názvů a adres, v souborech `domains.json` a `themes.json`, u každého webu s poznámkou. |
| Mapa tvrzení a studie | Registr studií oboru. Síla důkazů se počítá jen z ověřených studií. |
| Návrhy textů | Napsal je Claude z faktů v `drafts.json`. Jsou to koncepty ke kontrole člověkem. |
| Emoční claimy | Napsal je Claude do souboru `claims_emotional.json`. Každá věta prošla kontrolou tvrzení a opírá se jen o fakta ze souboru o značce. Jsou to hypotézy k testu, ne výsledky. |

Hledání se uloží jen tehdy, když nástroj opravdu proběhl s požadovaným dotazem a filtrem domény a hlásí aspoň jedno hledání. Jinak se zahodí a ohlásí. Nic se nedopisuje ani nezaokrouhluje.

## Kontrola proti přímému hledání

Pět uložených hledání bylo zopakováno přímo nástrojem pro vyhledávání a odkazy byly porovnány (soubory `radar/snapshots/2026-10-23/direct`). Shoda byla 9 z 9, 9 z 10, 9 z 9, 8 z 9 a 9 z 9 odkazů. Test `tests/test_radar_snapshot.py` hlídá, že shoda zůstane nad 80 procenty.

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

## Emoční claimy

Radar obsahuje i banku pozitivních, zážitkových vět pro značku: [radar/claims_emotional.json](../radar/claims_emotional.json). Na stránce je sekce "Emoční claimy" a v ní:

- **106 hotových vět** (slogany, nadpisy, úvodní věty, popisky, mikrotexty do aplikace a e-mailů, výzvy zákazníkům), z toho deset doporučených k prvnímu použití.
- **Sedm pák**, na kterých věty stojí: těšení, rituál, překvapení, příběh, pocit, příslušnost a volba. U každé je síla důkazů z registru studií a seznam ověřených studií. Síla platí pro obecnou páku, ne pro konkrétní větu ani pro produkt. Páka je tak silná, jak je silná její nejslabší taktika.
- **Šest cílových skupin** po čtyřech větách (u citlivých skupin s upozorněním), **příběh značky** ve třech délkách (jen skutečný začátek v posilovně) a **jména** pro rituál a funkce (Červená hodina, Rozbřesk, Soumrak, Moje světlo).
- **Co říkat místo čeho**: osm formulací, které kontrola tvrzení zachytí, a věta, kterou je nahradit.
- **Pravidla hry** (žádný pocit viny, upozornění na požádání, jen pravdivý nedostatek, jen skutečný příběh, citlivé skupiny), **čtyři dvojice pro A/B test** a seznam toho, co musí značka potvrdit před zveřejněním.

### Proč v nich není slovo dopamin
Věta typu "zvyšuje dopamin" tvrdí účinek přístroje na tělo, a je tedy zdravotním tvrzením. Opírá se navíc o zjednodušení: dopamin není látka potěšení, souvisí s toužením, očekáváním a překvapením (v registru taktika `dopamine-myth` se studiemi Salimpoor 2011, Gruber 2014 a Berridge a Robinson 1998). Věty proto využívají to, co za dopaminem v běžném životě stojí, a mluví o tom lidsky. Kontrola tvrzení u vět o dopaminu, serotoninu, endorfinech a dalších hormonech navíc hlásí chybu.

### Jak je zajištěno, že věty neslibují víc, než smějí
- Každá věta prochází stejnou kontrolou tvrzení jako ostatní texty a musí projít bez chyby i varování. Test to hlídá.
- Věta, která se opírá o fakt (šest vlnových délek, začátek v posilovně), uvádí který, a fakt musí být doslova v souboru o značce.
- Věta s číslem je buď opřená o fakt, nebo označená jako koncept: nápad, který zatím nic netvrdí o přístroji (kampaň, předmět e-mailu, upozornění v aplikaci, které aplikace dnes nemá doložené).
- Ani jedna věta nenese slova o těle, náladě, hormonech ani nejvyšším postavení na trhu.
- Kontrola čte slova, ne smysl, proto každou větu před zveřejněním přečte člověk. Skutečnou sílu věty ukáže až test na lidech.
- Slovo "zázrak" je na seznamu slov, kterým se značka vyhýbá. Věta "Žádné zázraky. Jen světlo, které si zvolíte." ho má jen v záporu a stránka u ní žádá potvrzení.

### Jak ji upravit
Věta se přidá do `radar/claims_emotional.json` s `id`, pákou (`lever`), použitím (`use`) a textem. Pokud se opírá o fakt, přidá se `support` s klíčem faktu a fakt musí být doslova v souboru o značce. Test `tests/test_radar_emotion.py` ověří kontrolu tvrzení, čísla i zakázaná slova. Stránku znovu postaví `radar build`.

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

`tests/test_radar_collect.py` (čtení skutečného záznamu nástroje, odmítnutí hledání, které neproběhlo jak mělo), `tests/test_radar_analyze.py`, `tests/test_radar_snapshot.py` (uložená data: každé hledání z plánu je uložené, shoduje se s plánem a s přímým hledáním, žádná dlouhá pomlčka) `tests/test_radar_emotion.py` (banka emočních vět: kontrola tvrzení, fakta, čísla, zakázaná slova, síla důkazů pák) a `tests/test_radar_report.py` (stránka, věty, návrhy textů a sekce emočních claimů; uložená stránka je přesně to, co sestaví kód).
