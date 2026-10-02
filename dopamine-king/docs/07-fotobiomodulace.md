# Edice MITO LIGHT: fotobiomodulace

Tato edice mění obecný stroj Dopamine King v nástroj pro obsahový marketing v oboru **fotobiomodulace** (PBM, červené a blízké infračervené světlo) a pro značku **MITO LIGHT**. Všechno z obecné části zůstává (skóre hooků, laboratoř, generátor, hra). Obor k tomu přidává:

| Část | Co dělá |
|---|---|
| **Profil tvrzení "wellness"** | Štít důvěry navíc hlídá, co smí říkat nezdravotnický přístroj: žádná diagnostika, léčba, prevence ani zmírnění nemoci či příznaku, přínosy jen opatrně a se zdrojem. |
| **Mapa tvrzení** | 19 témat (například regenerace po cvičení, vzhled pleti, spánek, bolest, zánět) s třídou, silou důkazů a vzorovými formulacemi, co říct a co ne. |
| **Registr důkazů** | 41 záznamů o studiích propojených s tématy. Síla důkazů se počítá jen z ověřených záznamů. |
| **Registr značek oboru** | 26 značek a organizací (domácí panely, LED masky, klinické přístroje, odborné společnosti, média, MITO LIGHT) pro šetrný sběr. |
| **Vzorová zadání MITO LIGHT** | Česky a anglicky, s fakty z veřejných zdrojů (k potvrzení značkou) a s ověřenými zdroji. |
| **Obsah hry** | Souboje (Boss) s kontrolou tvrzení, Mýtus nebo fakt o červeném světle, simulované duely, mapa tvrzení v Trezoru. |
| **Příkazy** | `kingctl audit` (kontrola existujících textů), `kingctl evidence claims`, `--vertical pbm` u ostatních příkazů, hledání v PubMed. |

## Výchozí bod: nezdravotnický přístroj

Podle veřejných zdrojů není MITO LIGHT zdravotnický prostředek, je určen jako pomůcka k podpoře regenerace zdravého organismu a popis jeho účinků nemá zmiňovat diagnostiku, léčbu ani prevenci nemocí. Zjištění vychází z odpovědi Ministerstva zdravotnictví, kterou vyhledávače uvádějí u modelu MITO LIGHT 3.0. Dokument jsem **neotevřel** (síť prostředí ho blokuje), proto je zdroj veden jako jediný a nepotvrzený. Edice podle něj nastavuje profil **wellness**. Podrobnosti a zdroje jsou v [08-regulace-pbm.md](08-regulace-pbm.md). **Není to právní poradenství**: formulace si ověřte u svého regulatorního poradce.

## Co profil wellness hlídá

| Kód | Úroveň | Příklad |
|---|---|---|
| `CLAIM_MEDICAL` | chyba | "Červené světlo zmírňuje bolest kloubů." "Heals your body with light." "Léčebné účinky světla." |
| `CLAIM_AVOID` | chyba | "Zvyšuje testosteron." "Detoxikuje tělo." |
| `DISEASE_MENTION` | chyba | "Pomáhá při artritidě." "Trpíte migrénou? Vyzkoušejte panel." |
| `MEDICATION_ADVICE` | chyba | "Nahraďte léky světlem." "Lepší než prášky." "Say goodbye to your painkillers." |
| `STATUS_CLAIM` | chyba | "Zdravotnický prostředek schválený FDA." "Lékařsky doporučeno." "Léčebný panel pro domácí použití." |
| `SAFETY_ABSOLUTE` | chyba | "Bez vedlejších účinků, bezpečné pro každého." |
| `CLAIM_UNHEDGED` | varování | "Zlepšuje spánek." (bez "může", bez zdroje) |
| `OUTCOME_PROMISE` | varování | "Za 4 týdny uvidíte méně vrásek." "Zaručeně zlepší spánek." "Zázračné světlo." |
| `DOSE_NOT_FROM_MANUAL` | varování | "Sezení trvá 10 minut z 15 cm." (údaj není ve faktech zadání) |
| `SAFETY_NOTE_MISSING` | varování | Delší text o používání bez upozornění na oči, návod a lékaře |
| `THERAPY_WORD` | poznámka | Slovo "terapie" může naznačovat léčbu |

Důležité vlastnosti pravidel:

- **Slova s léčebným významem jsou zdravotní tvrzení sama o sobě** ("léčí", "vyléčí", "heals", "cures", "léčebné účinky", "ochrana před nemocemi"): zvednou i téma wellness či vzhled na chybu a opatrné slovo ("může léčit") nepomůže. Podobně "alternativa k lékům", "lepší než prášky" nebo "rozlučte se s prášky" jsou rada nahradit léky.
- **Odmítnutí a výhrady se nepenalizují.** "Přístroj neslouží k léčbě nemocí" ani "Není zdravotnický prostředek" projde. Pravidla hledají nejbližší zápor a končí u nové věty nebo nové klauzule ("Ochrana očí není nutná, je to naprosto neškodné" zápor neplatí).
- **Standardní formulace se maskují**: "Vyzkoušejte bez rizika", "bezpečná platba", "lidé s epilepsií se mají poradit s lékařem".
- **Otázky nejsou tvrzení** ("Může červené světlo podpořit regeneraci?"), kromě oslovení lidí s nemocí ("Trpíte artritidou?").
- **Jazyk**: čeština (i bez diakritiky) a angličtina. U jiných jazyků pravidla nefungují.
- **Vlastní schválená věta značky** ve faktech zadání (například "pomůcka k podpoře regenerace zdravého organismu") projde bez varování.

Pravidla jsou **data**, ne kód: `src/dopamine_king/data/verticals/pbm/guard.json` a `claims.json`. Přidat zakázaný výraz je úprava seznamu. Příklady správných a nesprávných formulací, na kterých se pravidla testují, jsou v `examples.json`.

## Mapa tvrzení a jak číst štítky

Pět tříd: **wellness** (smí se opatrně a se zdrojem), **vzhled** (totéž pro vzhled pleti a těla), **souvislosti** (mechanismus, dávka, parametry, bezpečnost), **zdravotní** a **zakázáno** (nesmí se vůbec). Štítek síly důkazů vzniká takto:

1. počítají se **jen ověřené studie** (neověřený záznam štítek nikdy nezvedne),
2. štítek **nikdy nepřekročí ruční strop** tématu (heterogenní protokoly, malé studie a vlastnosti klinických přístrojů, které se na domácí panely nepřenáší),
3. při rozporu kvalitních studií je štítek **sporný**.

Stav ke dni sestavení:

| Téma | Třída | Štítek | Ověřené studie | Čeká na ověření |
|---|---|---|---|---|
| Regenerace svalů po cvičení | wellness | omezené | 4 | 1 |
| Sportovní výkon | wellness | sporné | 5 | 0 |
| Kvalita spánku | wellness | sporné | 3 | 0 |
| Energie a pohoda | wellness | omezené | 1 | 0 |
| Vzhled pleti | vzhled | žádné | 0 | 5 |
| Tvar postavy | vzhled | žádné | 0 | 2 |
| Jak to funguje (buněčný mechanismus) | souvislosti | omezené | 3 | 1 |
| Záleží na dávce a vlnové délce | souvislosti | omezené | 4 | 1 |
| Zařízení se liší výkonem | souvislosti | omezené | 2 | 2 |
| Bezpečnost očí | souvislosti | omezené | 1 | 0 |
| Obecná bezpečnost a upozornění | souvislosti | omezené | 1 | 0 |
| Růst vlasů | zdravotní (blokováno) | žádné | 0 | 2 |
| Bolest a klouby | zdravotní (blokováno) | omezené | 2 | 0 |
| Zánět | zdravotní (blokováno) | omezené | 1 | 0 |
| Hojení ran | zdravotní (blokováno) | žádné | 0 | 2 |
| Nálada a funkce mozku | zdravotní (blokováno) | omezené | 3 | 0 |
| Zrak a sítnice | zdravotní (blokováno) | omezené | 2 | 1 |
| Hormony a plodnost | zakázáno | žádné | 0 | 1 |
| Detox a imunita | zakázáno | žádné | 1 | 0 |

Medicínská a zakázaná témata zůstávají blokovaná, ať je štítek jakýkoli. Mapa je v hře v Trezoru, v terminálu `kingctl evidence claims --vertical pbm`.

## Důkazy: co je ověřeno a co ne

- **41 záznamů, z toho 25 ověřených** webovým vyhledáváním dne 2026-10-02 (název, časopis, rok, DOI nebo PubMed). U ověřených záznamů jsou závěry z abstraktů a shrnutí ve výsledcích, plné texty nebyly čteny.
- **16 záznamů je "výzkumných podnětů" z paměti autora** (kůže, tvarování těla, vlasy a několik přehledů). Mají poznámku, že nejsou ověřeny, nic o jejich závěrech se neříká a do štítku se nepočítají. Ověříte je příkazem `kingctl evidence verify --vertical pbm --save .king/pbm-ledger.json` (potřebuje síť, využívá Crossref).
- Rešerše narazila na **limit 200 webových vyhledávání na jednu relaci**. Proto chybí ověřené studie k vzhledu pleti, tvarování těla a vlasům, nejsou nezávislá měření spotřebitelských panelů ani přehled nežádoucích účinků. U sportu jsou záměrně vidět i nulové a smíšené výsledky (například celotělové panely).
- Hledání dalších studií: `kingctl evidence search "photobiomodulation skin" --sources pubmed,crossref` (PubMed je pro tento obor nejúplnější zdroj; potřebuje síť).

## Postup práce

```bash
cd dopamine-king && export PYTHONPATH=src

python3 -m dopamine_king demo --vertical pbm                 # celý řetězec, offline
python3 -m dopamine_king build-web                           # hra v edici MITO LIGHT (výchozí)
python3 -m dopamine_king evidence claims --vertical pbm      # mapa tvrzení

# koncepty obsahu z ukázkového zadání (česky a anglicky)
python3 -m dopamine_king forge --vertical pbm --sample mito-light-cs --writer offline --out out/mito-cs
python3 -m dopamine_king guru plan --vertical pbm --sample mito-light-cs

# bez klíče k AI: vyplníte sloty sami nebo je necháte napsat jiným modelem a štít je zkontroluje
python3 -m dopamine_king forge --vertical pbm --sample mito-light-cs --formats instagram_caption,seo_article --emit-slots sloty.json
python3 -m dopamine_king forge --vertical pbm --sample mito-light-cs --formats instagram_caption,seo_article --writer file --fills sloty.json --out out/mito-cs

# vlastní zadání (profil wellness se zapne sám)
python3 -m dopamine_king forge --vertical pbm --brand "MITO LIGHT" --topic "regenerace po tréninku" --audience "sportovci" --lang cs \
    --fact "Doporučená doba sezení je podle návodu 10 minut." --formats instagram_caption,seo_article --writer offline

# kontrola textu, který už existuje (web, newsletter, příspěvek)
python3 -m dopamine_king audit stranka.txt          # návratový kód 1 při chybě
```

1. **Zadání.** Značka, téma, publikum a **jen pravdivá fakta**. Doby používání, vzdálenosti a dávky patří do faktů zadání z návodu výrobce, jinak je štít označí.
2. **Generování.** Bez klíče k AI generátor nic nevymýšlí a míst, která vyžadují vaši zkušenost, se drží jako `[[ADD: ...]]` (u českých balíčků je zadání u těchto míst anglicky). S klíčem `--writer anthropic` píše prózu Claude a pravidla profilu dostává přímo v zadání. Živé volání API jsem zde nemohl vyzkoušet. Třetí cesta bez klíče je `--emit-slots` a `--writer file`: do šablony (každý slot má zadání a limity) napíšete text sami nebo ho dodá jiný jazykový model a Štít důvěry ho zkontroluje stejně jako text od Claude.
3. **Kontrola.** Každý kus projde Štítem důvěry. Delší texty dostanou bezpečnostní upozornění (oči, návod výrobce, lékař při těhotenství nebo lécích zvyšujících citlivost na světlo). Šablona upozornění je předschválená; pokud máte vlastní text z návodu, předejte ho přes `--safety-note`.
4. **Člověk.** Výstup je koncept. Nic se nepublikuje samo.

## Co víme o MITO LIGHT z veřejných zdrojů

Soubor `mito_light.json` obsahuje **31 sourcovaných faktů** a **15 otevřených otázek**. Vše pochází z výsledků vyhledávání, ne z otevření webu značky, a značka to musí potvrdit nebo opravit. Hlavní body: česká značka (mitolight.cz), zařízení vyvíjená a navrhovaná v Česku, výroba u dlouhodobého partnera v Číně, řada panelů a žárovek, šest vlnových délek 630 až 850 nm, na webu praktické FAQ k dávkování a očím. **Pozor na záměnu:** americká značka Mito Red Light je jiná firma, tvrzení se mezi nimi nesmí přenášet.

**Důležité pozorování.** Výsledky vyhledávání ukazují, že část textů na webu značky jde za rámec "podpůrná pomůcka": zmiňuje vlasy, jizvy, zánět a obsahuje superlativy. Podle zdrojů, které jsme našli, to s uvedeným stanoviskem ministerstva nemusí souhlasit. Doporučení: nechte stránky projít příkazem `kingctl audit` a nález probrat s regulatorním poradcem.

Otevřené otázky pro značku (výběr): kdo je právním provozovatelem v jednotlivých zemích, tykání nebo vykání, schválená slovní zásoba ("terapie" nebo "světelná rutina"), aktuální stanovisko pro generace 4.0 a 5.0 (nalezený dokument se týká generace 3.0), certifikace a měření ozáření, trhy mimo CZ, DE a UK, sociální sítě a persony.

## Omezení

- Štít tvrzení je **heuristický kontrolor, ne právník**. Může přehlédnout nebo označit zbytečně; seznamy jsou záměrně konzervativní.
- Fakta o MITO LIGHT, počet studií a registr značek odpovídají tomu, co šlo zjistit z vyhledávání v prostředí s omezeným rozpočtem a blokovanou sítí (viz výše).
- Pravidla znají češtinu a angličtinu. Slovenština a němčina jsou v roadmapě.
- Čísla v duelech a benchmarcích hry jsou **simulovaná** (fiktivní značky). Skutečná data konkurence získáte šetrným sběrem po povolení sítě a vlastní analytikou.
