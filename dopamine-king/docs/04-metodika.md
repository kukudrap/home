# Metodika

Tento dokument popisuje, **jak se počítá každé číslo**, aby šlo výsledkům věřit, nebo je zpochybnit. Všechny vzorce jsou v kódu (odkazy v závorkách).

## 1. Dopamine Score (`scoring.py`, `data/scoring_spec.json`)

Skóre hodnotí **hook** (titulek nebo první řádek) podle toho, kolik zdokumentovaných pák pozornosti obsahuje, a odečítá penalizaci za clickbait. **Není to měření mozku ani předpověď výkonu** konkrétního příspěvku, je to vysvětlitelná heuristika.

### Tokenizace a slovníky
Text se normalizuje (NFC), rozdělí na slova a čísla (`1,000` a `3.5` zůstávají jedním tokenem), převede na malá písmena. U češtiny se navíc odstraňují diakritická znaménka, aby fungoval i text psaný bez háčků a čárek. Slovníky (angličtina a čeština) mají 10 kategorií; položka může být víceslovná a hvězdička na konci znamená předponu (`tajn*` pokryje "tajný", "tajemství"). Hledá se zleva doprava, nejdelší shoda první, bez překryvů.

### Šest složek
| Složka | Čím se měří | Poznámka |
|---|---|---|
| Zvědavost | fráze informační mezery, otázka, otevřená smyčka (dvojtečka, tři tečky) | Loewenstein, 1994 |
| Překvapení | kontrast a vyvracení mýtů ("přestaň", "mýtus", "naopak"), číslo spolu s negativním rámcem | chyba predikce, Schultz a kol., 1997 |
| Emoce | slova s vysokou intenzitou, vykřičníky (omezeně), pozitivní a negativní rámování | Berger a Milkman, 2012 |
| Oslovení | "ty/vy/váš", slova sociální měny | relevance pro čtenáře |
| Užitek | slova praktického užitku ("jak", "návod"), číslo, číslo na začátku | konkrétní výplata |
| Srozumitelnost | délka (optimum 6 až 12 slov), průměrná délka slova | plynulost zpracování, Alter a Oppenheimer, 2009 |

Každá z prvních pěti složek je saturační funkce `1 - exp(-x / k)` váženého počtu zásahů (počty jsou zastropované, aby jedno slovo nepřebilo ostatní). Srozumitelnost **moduluje** výsledek: `0,55 + 0,45 * srozumitelnost`.

### Souhrn
```
raw      = (vážený průměr pěti složek) * modulátor srozumitelnosti          # 0..1
display  = 100 * (1 - exp(-raw / 0,35))
risk     = 1 - exp(-(clickbait + 0,5*přehnané sliby + 0,35*(vykřičníky-1)
                     + 2*(podíl VELKÝCH PÍSMEN - 0,25) + 0,6*mezera slibu))
total    = display * (1 - 0,65 * risk)
```
Výchozí váhy: zvědavost 0,25, užitek 0,25, emoce 0,18, oslovení 0,17, překvapení 0,15. **Mezera slibu**: titulek začíná číslem (například "7 způsobů"), ale text obsahuje méně položek.

### Limity (co skóre neumí)
Neví nic o významu: ironii, kontextu, kvalitě nabídky ani vizuálu. Slovníky pokrývají češtinu a angličtinu. Dá se obejít (někdo může slova do hooku nacpat), proto je tu penalizace clickbaitu, ale ne dokonalá. Skóre je smysluplné **jako pořadí** a vůči korpusu (percentil), ne jako absolutní číslo.

## 2. Success Index (`analysis/success.py`)
Výkon obsahu se **normalizuje**, aby nevyhrávaly velké účty: engagement se převede na míry (lajky na zhlédnutí, komentáře na zhlédnutí, sdílení, uložení, CTR, dokoukanost), každá míra se zařadí jako percentil v rámci **kohorty a platformy** (skupina minimálně 15 položek, jinak širší skupina) a index je vážený průměr dostupných percentil (sdílení a uložení mají váhu 1,3, lajky 1,0). Zdroj každého signálu zůstává u položky (provenance).

## 3. Pattern mining a kalibrace (`analysis/patterns.py`, `calibrate.py`)
- **Vzory:** ridge regrese (λ = 5) na standardizovaných vlastnostech hooku proti Success Indexu; interval spolehlivosti **bootstrapem** (percentilový, výchozí 200 opakování); vzor je "signifikantní", pokud interval nezahrnuje nulu. U binárních vlastností navíc rozdíl průměrů s intervalem. **Korelace není příčina.**
- **Kalibrace vah:** nezáporné nejmenší čtverce (NNLS) na pěti složkách; porovnání proti výchozím vahám **mimo trénovací vzorek** (5násobná křížová validace, Spearmanova korelace). Pokud kalibrace výchozí váhy nepřekoná, zůstanou výchozí.
- **Pravděpodobnost výhry:** `P(A vyhraje) = 1 / (1 + exp(-(sA - sB) / k))`, měřítko `k` se odhadne maximální věrohodností na náhodných dvojicích.

## 4. Laboratoř (`lab/`)
- **Dvouvýběrový test podílů** (sdružený z-test) a interval pro rozdíl podle Newcombeho; Wilsonovy intervaly pro jednotlivá ramena.
- **Velikost vzorku:** `n = (z_{α/2} * sqrt(2 p̄ q̄) + z_β * sqrt(p1 q1 + p2 q2))^2 / (p2 - p1)^2`. Příklad: z 5 na 6 procent při α = 0,05 a síle 0,8 je 8158 návštěvníků na rameno.
- **Bayes:** Beta-binomický model, `P(B lepší)` a očekávaná ztráta metodou Monte Carlo (pevné seedy).
- **Vícenásobné porovnání:** Holm-Bonferroni.
- **Nahlížení:** simulace A/A testů ukazuje, že zastavení při první hodnotě p < 0,05 po deseti nahlédnutích dává řádově 17 a více procent falešně pozitivních výsledků (nominálně 5).
- **Bandité:** rovnoměrné dělení, epsilon-greedy, UCB1, Thompson sampling; měří se **regret** (ztracené konverze proti vždy nejlepší variantě).
- **Simulátor publika** (`lab/sim.py`) slouží jen jako hřiště: každý výsledek nese štítek `simulated`.

## 5. Důkazy (`research/`)
- **Hodnocení studie:** hierarchie designu (metaanalýza a systematický přehled 1,0; RCT a polní experiment 0,85; laboratorní experiment 0,7; observační studie 0,55; průzkum 0,5; teorie 0,4; kvalitativní 0,35; preprint 0,4; kniha 0,3; neznámé 0,25), malý bonus za citace za rok, preprint nemůže přesáhnout B, stažená práce je vždy D. Práh: A od 0,8, B od 0,6, C od 0,4.
- **Souhrn taktiky:** `strong` (aspoň dvě podporující studie A nebo B a žádná protichůdná A nebo B), `contested`, `moderate`, `limited`, `none`.
- **Ověření:** `kingctl evidence verify` porovná každou studii s Crossref (shoda názvu a roku). Seed ledger je z větší části už ověřen přes veřejné zdroje (23 z 32); ostatní záznamy zůstávají označené jako neověřené, dokud ověření neproběhne. Ledger oboru PBM má 41 záznamů, z toho 25 ověřených; 16 je označeno jako neověřené podněty a do síly důkazů se nepočítají. Hledání nových studií umí i PubMed (`evidence search --sources pubmed`).

## 6. SEO, GEO, Trust Shield (`generate/`)
- **SEO skóre:** délka titulku a meta popisu, klíčové slovo v titulku, H1 a prvních 100 slovech, hustota 0,5 až 2,5 procenta, délka vět, FAQ, zdroje, délka textu. **Quality gate** odmítne článek bez vlastní zkušenosti nebo faktů jako nepublikovatelný (hromadně vyráběný obsah s nízkou hodnotou je podle zásad vyhledávačů riziko).
- **GEO skóre:** kontrolní seznam vážený podle výzkumu GEO (Aggarwal a kol., 2024: citace, citáty a statistiky pomáhaly nejvíc, nacpání klíčových slov nepomáhalo): zdroje, statistiky se zdrojem, citáty jmenovaných osob, odpověď na začátku, struktura, FAQ, srozumitelnost entity, aktuálnost, autor, schema, čitelnost. Výsledky pocházejí z jednoho benchmarku, na komerčních enginech se mohou lišit.
- **Profil tvrzení wellness:** viz část 7.
- **Další pravidla Štítu:** poznámka pro redaktora v hranatých závorkách (`PLACEHOLDER_NOTE`, například "[Doplňte jméno autora]") a tykání v českém textu značky, která vyká (`INFORMAL_ADDRESS`, zadání s `address: vy`).
- **Trust Shield:** pravidla pro nepodložená tvrzení a statistiky, absolutní sliby, zdravotní a finanční sliby, falešný nedostatek a naléhavost, confirmshaming, engagement bait, skryté prompty pro AI, chybějící označení reklamy, osobní údaje, nenalezené citace.

## 7. Profil tvrzení wellness a mapa tvrzení (`generate/claims.py`, `verticals/`)

Obor PBM (edice MITO LIGHT) přidává pravidla pro nezdravotnický přístroj. Údaje (témata, seznamy výrazů, vzorce) jsou v `data/verticals/pbm/claims.json` a `guard.json`, algoritmus je obecný.

### Jak kontrolor čte text
1. Text se převede na malá písmena a zbaví diakritiky (čeština s háčky i bez nich funguje stejně), poloha znaků se zachová, aby šlo označit konkrétní místo.
2. Každý výraz ze seznamu se přeloží na regulární výraz; hvězdička na konci slova znamená kmen (`léč*`). Výraz o více slovech se hledá celý.
3. **Blízkost.** Pravidla se ptají na dvojice (sloveso nebo podstatné jméno léčby, téma nebo nemoc) v okně 5 slov (u oslovování nemocných 8). Okno nikdy nepřekročí konec věty (tečka, otazník, vykřičník, středník, nový řádek).
4. **Zápor.** Hledá se **nejbližší** zápor před výrazem (do 60 znaků a s mezerou nejvýš 40 znaků); nová klauzule ("..., je to naprosto neškodné") zápor ruší. Díky tomu projde "Přístroj neslouží k léčbě nemocí", ale neprojde "Ochrana očí není nutná, je to naprosto neškodné".
5. **Maskování.** Standardní věty (odmítnutí zdravotního určení, "vyzkoušejte bez rizika", "bezpečná platba") se nehodnotí.
6. **Otázky** nejsou tvrzení, kromě oslovení lidí s problémem a rady o lécích. **Oslovení lidí s problémem je tvrzení:** "máte problémy s", "trpíte", "trápí vás" vedle nemoci nebo vedle podstatného jména kteréhokoli tématu kromě souvislostí (spánek, únava, bolest) je chyba i jako otázka, stejně jako "pomůže vám s problémy".
7. **Opatrné slovo a zdroj.** Přínos v třídě wellness s "může", "u zdravých lidí" nebo s odkazem na zdroj je v pořádku. Bez toho je varování `CLAIM_UNHEDGED`. U zdravotních témat opatrné slovo nepomáhá.
8. Při překrytí vyhrává přísnější třída (souvislosti, wellness, vzhled, zdravotní, zakázáno).
9. **Slova s léčebným významem** (léčí, vyléčí, hojí, cures, heals, "léčebné účinky", ochrana před nemocemi) jsou zdravotní tvrzení bez ohledu na to, k čemu se vztahují: zvednou i téma wellness či vzhled na zdravotní tvrzení (opatrné slovo nepomůže) a samotná tvoří téma `generic-cure`. Seznam je v `guard.json` pod klíčem `strong_claims`.
10. **Schválený název kategorie.** Výrazy v `approved_terms` (u MITO LIGHT "terapie červeným světlem") přeskočí jen poznámku o slově terapie; všechna ostatní pravidla je čtou dál, takže "terapie červeným světlem léčí bolest zad" zůstává chybou.

### Mapa tvrzení: štítek síly důkazů
Pro každé téma se spočítá štítek (`none`, `limited`, `moderate`, `strong`, `contested`) z ledgeru takto: (1) počítají se **jen ověřené studie**, neověřené jsou vidět jako "čeká na ověření", ale štítek nezvedou, (2) štítek **nepřekročí ruční strop** tématu (`label_cap`), který kurátor odůvodní (malé studie, různé protokoly, klinické přístroje, které se na domácí panely nepřenáší), (3) při rozporu kvalitních studií zůstává `contested`. Mapa **neříká, že tvrzení je dovolené**: třída tématu určuje, zda a s jakou formulací se smí vůbec zmínit.

### Jak byla pravidla ověřena a co to znamená
- Jednotkové testy na stovkách vět v češtině, češtině bez diakritiky a angličtině (správné i nesprávné formulace).
- **Sada 50 příkladů psaných odděleně od pravidel** (například svědectví se slovesy "zmizela" či "vymizelo", nahrazení léků, schválení ministerstvem). Při prvním použití odhalila mezery, které jsem doplnil; teprve potom prošla 50 z 50. Sada tedy pomohla pravidla opravit a už není zcela nezávislá. Je to ověření, že pravidla nejsou naučená nazpaměť, ne důkaz, že jsou úplná; novou nezávislou sadu je třeba sestavit při každém větším rozšíření pravidel.
- **Druhé kolo: asi 100 nových vět** (60 s předem určeným očekáváním, 47 jen k prohlédnutí). Našlo další mezery (například "Heals your body with light", "lepší než prášky", "alternativa k lékům", "léčebný panel", "redukuje úzkost", "zaručeně", "zázračné světlo"), které jsou opravené a mají testy. Na 30 běžných, správných větách (doprava, záruka, návod, opatrné wellness formulace) nebyl žádný falešný poplach.
- 187 "golden" případů shodných v Pythonu a JavaScriptu.

### Limity (co kontrolor neumí)
Čte slova, ne význam: obrázky, hashtagy, ironii, tvrzení rozložená do více vět a zvláštní slovní obraty (například nový slang) nezachytí a zdravé věty může označit omylem. Jazyky mimo češtinu a angličtinu nehlídá. Známé mezery, které dnes projdou nebo skončí jen varováním a člověk by je zastavil: "Less pain, more energy" (méně bolesti), "Trusted by thousands of doctors", "Relieves muscle soreness" (anglicky jen varování, česky "zmírňuje svalovou bolest" chyba), kosmetické sliby typu "odstraňuje vrásky" (varování, v regulaci jde o rizikovou oblast a patří k právníkovi). Je to **pomůcka pro člověka**, ne právní posudek ani schvalovací orgán.

