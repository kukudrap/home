# Herní design

Hra je tréninkový nástroj. Cílem není strávit v ní co nejvíc času, ale **zlepšit odhad toho, co funguje**, a odnést si z ní poznatky o experimentování a důkazech.

## Smyčka (Trigger, Action, Reward, Investment)

Model vychází z populárního rámce Hooked (Eyal, 2014; praktická kniha, ne recenzovaná studie) a upravuje ho eticky.

| Fáze | Co se děje | Eticky |
|---|---|---|
| **Trigger** | Denní kvesty (3 denně), upozornění na sérii | Žádné tlačení: bez notifikací, bez odpočtů |
| **Action** | Duel hooků, souboj s bossem, laboratorní experiment, kvíz Mýtus nebo fakt | Každá akce trvá 30 až 120 sekund |
| **Variable reward** | Truhla s kartou, odhalení "upsetu" (model se spletl a hráč měl pravdu) | Šance jsou **vždy viditelné**, funguje pity timer, žádné platby |
| **Investment** | Sbírka karet, Oracle rating (kalibrace), úspěchy | Odměňuje se pokrok a mistrovství, ne pouhá aktivita |

## Režimy

- **Arena (duel hooků).** Dva hooky, hráč tipne vítěze a volitelně nastaví jistotu 50 až 100 procent. Po odhalení uvidí skutečné (v demu simulované) percentily úspěchu, odhad modelu a vysvětlení. Z jistoty se počítá **Brierovo skóre** a z něj **Oracle rating**: odměňuje se dobrá kalibrace, ne štěstí.
- **Boss Battle.** Hráč napíše hook k zadání. Živě se přepočítává Dopamine Score, šest pák, riziko clickbaitu (Trust Shield) a percentil v kohortě. Boss je poražen, když percentil dosáhne cíle **a** riziko clickbaitu zůstane pod 0,35. Clickbait se tedy nevyplácí.
- **Laboratoř.** (1) Duel A/B s hlídáním velikosti vzorku, (2) "Nenahlížej": simulace ukáže, že zastavit test při první hodnotě p pod 0,05 po desetinásobném nahlédnutí dává kolem 17 až 25 procent falešně pozitivních výsledků místo 5, (3) Bandit Garden: Thompson sampling proti rovnoměrnému dělení provozu.
- **Vault.** Karty taktik a studií (s hodnocením A až D, výhradami a stavem ověření), kvíz Mýtus nebo fakt.

## Progres

- **Úrovně:** kumulativně `round(100 * (n - 1)^1.5)` XP; deset pojmenovaných úrovní (od Rookie po King).
- **Arena XP:** správně 10, +5 střední, +10 těžký duel, +10 za zachycený upset; špatně 2 (účast, nikdy trest); násobič série správných odpovědí až x3.
- **Boss:** XP bosse při první výhře dne, opakované výhry 20 procent.
- **Série dnů:** kdo vynechá den, spotřebuje "zmrazení" (získá se po každém sedmém dni, nejvýš 2). Žádné výčitky v textech.

## Etika dopaminového designu

1. **Publikované šance.** Panel "Drop rates" ukazuje: běžná 60 %, vzácná 28 %, epická 10 %, legendární 2 %. Po 8 truhlách bez vzácné nebo lepší karty je další zaručená vzácná.
2. **Žádné peníze ve hře.** Žádné loot boxy za skutečné peníze, žádná virtuální měna, kterou by šlo koupit.
3. **Žádné vynucené návyky.** Po nastavené době hraní (výchozí 20 minut) přijde vlídná, odmítnutelná karta "dejte si pauzu". Zvuk je ve výchozím stavu vypnutý, respektuje se `prefers-reduced-motion`.
4. **Poctivost dat.** Každé odhalení v demu nese štítek **SIMULOVANÁ DATA**; hra říká, že Dopamine Score je heuristika.
5. **Přesah do obsahu.** Totéž platí pro generovaný obsah: žádný falešný nedostatek, žádné výčitky ("confirmshaming"), žádné slibované a nesplněné.

## Proč Brierovo skóre

Kdybychom odměňovali jen "trefil jsem vítěze", hráč by se naučil sázet na jistotu. Brierovo skóre `(jistota - výsledek)^2` odměňuje **poctivě odhadnutou nejistotu**. Oracle rating = `100 * (1 - Brier / 0,25)` (0,25 je skóre hráče, který vždy tipuje 50 procent), zobrazuje se po deseti odpovědích.
