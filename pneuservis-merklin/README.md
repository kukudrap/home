# Pneuservis Merklín · Roman Oberreiter

Web pro přezouvání pneumatik, Merklín 7, 362 34 Merklín. HTML, CSS a JavaScript bez sestavování. Animace dělá GSAP, plynulé kolečko myši Lenis; obě knihovny jsou přímo ve složce `vendor/`, takže web nezávisí na cizím CDN.

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
| Telefon v odkazech | 9 míst | `tel:+420XXXXXXXXX` |
| Telefon v textu | 2 místa | `+420 XXX XXX XXX` |
| Ceny služeb | sekce Služby | `od XXX Kč` |
| IČO | patička | `IČO XXXXXXXX` |
| Fotka Romana | sekce Kdo vás přezuje | návod je v komentáři přímo v kódu |
| Fotky z dílny | galerie Z dílny | místo kreseb, návod v komentáři |

Nejrychlejší je hromadné nahrazení: `+420XXXXXXXXX` a `+420 XXX XXX XXX` za skutečné číslo. Formulář na SMS bere číslo automaticky z prvního odkazu `tel:`.

Projděte i texty: seznam služeb (přezutí, přemontování, vyvážení, oprava defektu, kontrola) a věta o tom, že kola přezouvá Roman osobně, jsou odhad. Co nesedí, stačí upravit nebo smazat.

## Co web umí

**Animace (GSAP + Lenis)**

- Nadpis v úvodu se při načtení "vylije" písmeno po písmenu (SplitText). Při přepnutí sezóny slovo "zimu." vyteče a "léto." se vylije.
- Služby jsou vějíř karet, který se při scrollu rozevře; ikony se mezitím kreslí linkou (DrawSVG). Na mobilu se karty "rozdají" pod sebe.
- Nadpisy sekcí vyjíždějí slovo po slovu, ostatní obsah zespodu.
- Galerie "Z dílny" se na počítači při scrollu posouvá do strany a kresby dezénů, vyvážení nebo utahování do hvězdy se kreslí linkou. Na mobilu se karty posouvají prstem.
- Lenis vyhlazuje jen kolečko myši, dotyk na mobilu zůstává nativní.
- Světlo pod kurzorem na kartách je efekt SpotlightCard z React Bits přepsaný do čistého JavaScriptu.
- Kdo má v systému vypnuté animace, nebo kdyby se knihovny nenačetly, uvidí celý obsah bez pohybu.

**Obsah a funkce**

- **Menu**: na počítači pět jasných položek, aktuální sekce se zvýrazní. Na mobilu a tabletu tlačítko menu, které otevře celoobrazovkový přehled s telefonem. Sekce mají stejná čísla jako v menu (01 až 05).
- **Mobilní lišta**: po úvodu se dole objeví "Zavolat" a "Objednat přes SMS", u kontaktu se schová.
- **Prodejní texty podle sezóny**: příběh "Je půl sedmé a venku je poprvé bílo..." (v létě cesta k moři), výzva "Nečekejte na první sníh / vedro" a úvodní text se mění se sezónou.
- **Objednání z ceníku**: tlačítko "Objednat" u služby předvyplní službu ve formuláři.
- **Časté otázky**: šest odpovědí, které zákazníkovi ušetří telefonát (objednání, pneu bez disků, kdy přezout, co vzít s sebou, klíč k bezpečnostním šroubům).

- Přepínač **Zima / Léto**: přebarví celý web (modrá / oranžová), změní nadpis a rady. Výchozí sezóna se nastaví podle data (říjen až březen zima).
- Odpočet do 1. listopadu, od listopadu do konce března zbývající dny zimního období.
- Kolo v úvodu se při načtení přivalí a točí se se scrollem. Brzdový třmen stojí, jako na skutečném autě.
- Sekce "Jak to probíhá" se při scrollu připne a v posledním kroku nakreslí hvězdu, ve které se utahují šrouby.
- Poradna: rozklíčování nápisu na boku pneumatiky a posuvník hloubky dezénu s verdiktem podle sezóny.
- SMS formulář, který připraví zprávu a otevře ji v telefonu. Žádný server není potřeba.
- Mapa, odkazy na navigaci (Mapy.cz, Google Maps), strukturovaná data pro Google (`TireShop`).
- Respektuje nastavení "omezit pohyb" v systému, funguje od 360 px po velké monitory.

## Zveřejnění na Cloudflare

Web je statický, nic se nesestavuje. Soubor `_headers` nastaví Cloudflare bezpečnostní hlavičky a cache pro knihovny.

**Nejjednodušší (bez příkazové řádky):**

1. Zabalte obsah složky do ZIPu tak, aby `index.html` byl hned v kořeni (README do něj patřit nemusí).
2. Cloudflare → Workers & Pages → Vytvořit → Pages → Nahrát soubory (Upload assets).
3. Zadejte název projektu, přetáhněte ZIP a dejte Nasadit. Web poběží na `nazev-projektu.pages.dev`.
4. Vlastní doménu přidáte v projektu v záložce Vlastní domény (Custom domains).

**Z příkazové řádky:**

```bash
npx wrangler pages deploy pneuservis-merklin --project-name pneuservis-merklin
```

**Napojení na GitHub:** v Cloudflare Pages zvolte tento repozitář, build command nechte prázdný a jako výstupní složku (build output directory) zadejte `pneuservis-merklin`.

## Fakta použitá v textech

- Zimní pneumatiky: povinné od 1. 11. do 31. 3., pokud je na silnici sníh, led nebo námraza, nebo se dají čekat.
- Minimální dezén: zimní pneu u osobních aut 4 mm, letní 1,6 mm.
- 7 °C: běžně doporučovaná hranice pro přezutí.
