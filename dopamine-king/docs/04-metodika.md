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
- **Ověření:** `kingctl evidence verify` porovná každou studii s Crossref (shoda názvu a roku). Do té doby je záznam označen jako neověřený.

## 6. SEO, GEO, Trust Shield (`generate/`)
- **SEO skóre:** délka titulku a meta popisu, klíčové slovo v titulku, H1 a prvních 100 slovech, hustota 0,5 až 2,5 procenta, délka vět, FAQ, zdroje, délka textu. **Quality gate** odmítne článek bez vlastní zkušenosti nebo faktů jako nepublikovatelný (hromadně vyráběný obsah s nízkou hodnotou je podle zásad vyhledávačů riziko).
- **GEO skóre:** kontrolní seznam vážený podle výzkumu GEO (Aggarwal a kol., 2024: citace, citáty a statistiky pomáhaly nejvíc, nacpání klíčových slov nepomáhalo): zdroje, statistiky se zdrojem, citáty jmenovaných osob, odpověď na začátku, struktura, FAQ, srozumitelnost entity, aktuálnost, autor, schema, čitelnost. Výsledky pocházejí z jednoho benchmarku, na komerčních enginech se mohou lišit.
- **Trust Shield:** pravidla pro nepodložená tvrzení a statistiky, absolutní sliby, zdravotní a finanční sliby, falešný nedostatek a naléhavost, confirmshaming, engagement bait, skryté prompty pro AI, chybějící označení reklamy, osobní údaje, nenalezené citace.
