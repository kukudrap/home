# Herní design

Hra je tréninkový nástroj. Cílem není strávit v ní co nejvíc času, ale zlepšit odhad toho, co na trhu funguje, a odnést si z ní poznatky o experimentování a důkazech. Ve skutečné edici (výchozí sestavení) se všechna čísla berou z uložených hledání na webu, z ověřeného registru studií a ze souboru o značce. Starší demo se simulovanými daty zůstává jako `build-web --synthetic`.

## Smyčka (Trigger, Action, Reward, Investment)

Model vychází z rámce Hooked (Eyal, 2014; praktická kniha, ne recenzovaná studie) a upravuje ho eticky.

| Fáze | Co se děje | Eticky |
|---|---|---|
| Trigger | Denní úkoly (3 denně), série dnů | Žádné notifikace ani odpočty |
| Action | Souboj v Aréně, boss, skutečný úkol z Trhu, experiment v Laboratoři, Mýtus, nebo fakt | Každá akce trvá 30 až 120 sekund |
| Variable reward | Truhla s kartou, odhalení překvapení (model se spletl a hráč měl pravdu) | Šance jsou vždy viditelné, funguje pojistka a nic se neplatí |
| Investment | Sbírka karet, hodnocení Orákula (kalibrace), úspěchy | Odměňuje se pokrok a přesnost, ne samotná aktivita |

## Režimy

- Aréna. Má tři druhy soubojů z uložených hledání. U pořadí (147 soubojů) hráč hádá, který ze dvou výsledků stejného hledání byl výš. U výskytu (36) hádá, který web se objevil ve víc z 47 hledání na českém trhu. U tvrzení (36) hádá, který ze dvou skutečných titulků by kontrola tvrzení zastavila. Po odpovědi hra ukáže pořadí, počty, nálezy kontroly a odkaz na skutečnou stránku. U pořadí navíc ukáže odhad Dopamine Score a přizná, že na všech dvojicích skóre pořadí nepředpovídá (50,3 %, hod mincí je 50 %). Z jistoty, kterou hráč volitelně nastaví, se počítá Brierovo skóre a z něj hodnocení Orákula.
- Boss. Soupeř je skutečný titulek konkurenta nebo média (21 bossů). Hráč napíše hook ke stejnému tématu. Živě se přepočítává Dopamine Score, šest faktorů, riziko clickbaitu a percentil mezi skutečnými titulky. Boss je poražen, když percentil dosáhne cíle, riziko clickbaitu zůstane do 35 % a hook nemá žádný blokující problém s tvrzením.
- Trh. Sedm zjištění z hledání, každé s číslem, upozorněním a odkazem na hledání, ze kterého vychází. Šest úkolů, které z nich plynou. Všech 88 uložených hledání s odkazy, přehled konkurence, záměna názvu s Mito Red Light, tvrzení trhu a popis metody včetně toho, co chybí.
- Laboratoř. Skutečný A/B test: hráč vybere dvojici vět z banky claimů, hra spočítá velikost vzorku, hráč test spustí ve vlastním nástroji a zapíše skutečná čísla, hra je vyhodnotí. Dále dvě výukové simulace: Nenahlížejte (zastavit test při první hodnotě p pod 0,05 po opakovaném nahlížení dává mnohem víc falešných poplachů než 5 %) a Zahrada banditů (Thompsonovo vzorkování proti rovnoměrnému dělení provozu). Obě simulace jsou označené.
- Trezor. Karty (studie, čísla z hledání, tipy), 73 studií s odkazy a stavem ověření, mapa tvrzení s 19 tématy a hra Mýtus, nebo fakt.
- Claimy. Banka 106 vět pro slogany, nadpisy a příspěvky, které prošly kontrolou tvrzení.
- Kovárna a Guru. Devět návrhů textů pro značku (psal je Claude, každý prošel kontrolou tvrzení) a ukázkový plán obsahu.

## Skutečná data a jejich meze

- Každý souboj nese dotaz, pořadí, datum hledání a odkaz. Titulek, který nástroj nevrátil, hra označí jako vzniklý z adresy.
- Úkoly a čísla testů zapisuje hráč sám. Hra je neověřuje a říká to.
- Vyhledávač hledal z USA, takže pořadí se může lišit od Googlu a Seznamu.
- Kontrola tvrzení čte slova, ne smysl. Neověřené studie jsou vidět, ale sílu důkazů nikdy nezvedají.

## Progres

- Úrovně: kumulativně `round(100 * (n - 1)^1.5)` XP, deset pojmenovaných úrovní (od Nováčka po Krále).
- Aréna: správně 10 XP, +5 u střední a +10 u těžké obtížnosti, +10 za trefené překvapení proti modelu. Špatně 2 XP (účast, nikdy trest). Násobič série správných odpovědí je nejvýš x3.
- Boss: plná odměna za první výhru dne nad daným bossem, za opakované 20 %.
- Skutečná práce: splněný úkol z Trhu 50 XP jednou, každý třetí úkol otevře truhlu, naplánování skutečného testu 10 XP a zapsání jeho čísel 40 XP, vždy jednou za test. Odškrtnutí úkolu zpět XP neubere.
- Série dnů: kdo vynechá den, spotřebuje zmrazení (získá se po každém sedmém dni, nejvýš 2).
- Denní úkoly: tři z deseti, každý za 30 XP, všechny tři otevřou bonusovou truhlu.
- Šestnáct úspěchů, mezi nimi Čtenář pravidel (10 správných soubojů o tvrzeních), Průzkumník trhu (10 soubojů o pořadí a výskytu), Skutečná práce (3 úkoly) a Skutečný test.

## Etika dopaminového designu

1. Zveřejněné šance. Panel ukazuje: běžná 60 %, vzácná 28 %, epická 10 %, legendární 2 %. Po 8 truhlách bez vzácné nebo lepší karty je další zaručeně vzácná. Karta ze studie, kterou nikdo neověřil, je vždy jen běžná.
2. Žádné peníze ve hře. Žádné loot boxy za skutečné peníze a žádná virtuální měna, kterou by šlo koupit.
3. Žádné vynucené návyky. Po nastavené době hraní (výchozí je 20 minut) se ukáže připomínka přestávky, kterou lze odmítnout. Zvuk je ve výchozím stavu vypnutý a respektuje se `prefers-reduced-motion`.
4. Poctivost dat. Hra říká, odkud čísla jsou, a že Dopamine Score je heuristika. Simulace v Laboratoři a celé demo jsou označené.
5. Stejná pravidla pro generovaný obsah: žádný falešný nedostatek, žádné výčitky, žádné sliby, které by se nesplnily.

## Edice MITO LIGHT a kontrola tvrzení

Hra se sestavuje jako edice: stejná hra a stejný scorer, nastavené pro jeden výrobek (výchozí je fotobiomodulace a značka MITO LIGHT, viz [07-fotobiomodulace.md](07-fotobiomodulace.md)). Edice přidává kontrolu toho, co smí o nezdravotnickém světelném panelu zaznít.

- V souboji s bossem běží naživo kontrola tvrzení (profil wellness). Zdravotní tvrzení, nemoc vedle slova o léčbě, stavové fráze typu "schváleno", absolutní bezpečnost a rada nahradit léky jsou chyby a výhru blokují. Varování a poznámky ji neblokují. U každého nálezu hra ukáže kód, text, téma, označení síly důkazů a bezpečnější formulaci.
- Mapa tvrzení v Trezoru ukazuje 19 témat v pěti třídách se silou důkazů, propojenými studiemi a bezpečnějšími formulacemi. Pole Zkontrolujte vlastní text pustí stejný kontrolor na libovolný vložený text.
- Kontrola běží celá v prohlížeči (JavaScriptový port Python kontroloru, shodu hlídá 238 společných testovacích případů) a text se nikam neodesílá.

## Proč Brierovo skóre

Kdyby se odměňovalo jen trefení vítěze, hráč by se naučil sázet na jistotu. Brierovo skóre `(jistota - výsledek)^2` odměňuje poctivě odhadnutou nejistotu. Hodnocení Orákula je `100 * (1 - Brier / 0,25)`, kde 0,25 je skóre hráče, který vždy tipuje 50 %. Zobrazí se po deseti odpovědích s jistotou.
