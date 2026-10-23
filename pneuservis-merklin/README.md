# Pneuservis Merklín · Roman Oberreiter

Web pro přezouvání pneumatik, Merklín 7, 362 34 Merklín. Čisté HTML, CSS a JavaScript bez knihoven a bez sestavování.

## Jak si to prohlédnout

Otevřete `index.html` v prohlížeči. Nebo spusťte jednoduchý server:

```bash
cd pneuservis-merklin
python3 -m http.server 8000
# a pak http://localhost:8000
```

## Co je potřeba doplnit

V souboru `index.html` hledejte `XXX`:

| Co | Kde | Jak to vypadá teď |
| --- | --- | --- |
| Telefon v odkazech | 3 místa | `tel:+420XXXXXXXXX` |
| Telefon v textu | 2 místa | `+420 XXX XXX XXX` |
| Ceny služeb | sekce Služby | `od XXX Kč` |
| IČO | patička | `IČO XXXXXXXX` |
| Fotka Romana | sekce Kdo vás přezuje | návod je v komentáři přímo v kódu |

Formulář na SMS bere číslo automaticky z prvního odkazu `tel:`, takže stačí přepsat telefon.

Projděte i texty: seznam služeb (přezutí, přemontování, vyvážení, oprava defektu, kontrola) a věta o tom, že kola přezouvá Roman osobně, jsou odhad. Co nesedí, stačí upravit nebo smazat.

## Co web umí

- Přepínač **Zima / Léto**: přebarví celý web (modrá / oranžová), změní nadpis a rady. Výchozí sezóna se nastaví podle data (říjen až březen zima).
- Odpočet do 1. listopadu, od listopadu do konce března zbývající dny zimního období.
- Kolo v úvodu se při načtení přivalí a točí se se scrollem. Brzdový třmen stojí, jako na skutečném autě.
- Sekce "Jak to probíhá" se při scrollu připne a v posledním kroku nakreslí hvězdu, ve které se utahují šrouby.
- Poradna: rozklíčování nápisu na boku pneumatiky a posuvník hloubky dezénu s verdiktem podle sezóny.
- SMS formulář, který připraví zprávu a otevře ji v telefonu. Žádný server není potřeba.
- Mapa, odkazy na navigaci (Mapy.cz, Google Maps), strukturovaná data pro Google (`TireShop`).
- Respektuje nastavení "omezit pohyb" v systému, funguje od 360 px po velké monitory.

## Zveřejnění

Stačí nahrát čtyři soubory (`index.html`, `styles.css`, `app.js`, `favicon.svg`) na libovolný hosting. Nejrychleji zdarma: přetáhnout složku na Netlify Drop, nebo zapnout GitHub Pages. Pro vlastní doménu (třeba pneuservis-merklin.cz) se doména jen nasměruje na hosting.

## Fakta použitá v textech

- Zimní pneumatiky: povinné od 1. 11. do 31. 3., pokud je na silnici sníh, led nebo námraza, nebo se dají čekat.
- Minimální dezén: zimní pneu u osobních aut 4 mm, letní 1,6 mm.
- 7 °C: běžně doporučovaná hranice pro přezutí.
