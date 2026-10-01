# Vize: Dopamine King

## Jedna věta

Dopamine King je marketingový stroj, který **nejdřív zjistí, co skutečně funguje** (sběr veřejného obsahu úspěšných značek, benchmarky, vědecké studie, vlastní experimenty), a teprve potom **vygeneruje obsah ve všech formátech**: SEO a GEO články, příspěvky, video scénáře, reklamy. Celé je to zabalené do hry, ve které si uživatel trénuje cit pro silné hooky a učí se experimentovat.

## Proč to není další AI generátor textů

Běžný generátor dostane prompt a vyrobí text ve vzduchoprázdnu. Dopamine King má čtyři vrstvy, které v prompt-only nástrojích chybí:

| Vrstva | Co dělá | Proč je to důležité |
|---|---|---|
| **Korpus** | Etický sběr veřejného obsahu úspěšných značek, výkon normalizovaný podle kohorty a platformy (Success Index) | Neporovnáváte B2B changelog s videem Red Bullu. Učíte se z toho, co funguje ve vašem oboru. |
| **Důkazy** | Ledger studií: každá taktika je propojena se studiemi, které ji podporují nebo vyvracejí, s hodnocením kvality (A až D) a výhradami | Obsah netvrdí "studie ukazují", pokud k tomu nemá zdroj. Mýty (například "dopamin je hormon slasti") se vyvracejí. |
| **Laboratoř** | A/B testy (frekventistické i bayesovské), výpočet velikosti vzorku, bandité, ochrana před "nahlížením" | Generované varianty končí v experimentu, ne v dojmu. Systém se učí z vašich čísel. |
| **Trust Shield** | Hlídá vymyšlená čísla, falešný nedostatek, zdravotní a finanční sliby, skryté prompty pro AI, chybějící označení reklamy | Důvěra je dlouhodobě silnější než clickbait a chrání vás před regulací i před spamovými zásadami vyhledávačů. |

## Co znamená "dopamine" (poctivě)

Dopamin **není** "hormon štěstí" ani látka slasti. Souvisí hlavně s *chtěním*, očekáváním a chybou predikce odměny (Schultz a kol., 1997; Berridge a Robinson, 1998). Pro obsah z toho plyne jednoduchý princip: **dobrý hook vytvoří očekávání a pak ho splní**. Proto Dopamine Score měří šest pákových bodů pozornosti (zvědavost, překvapení, emoce, oslovení, užitek, srozumitelnost) a **trestá clickbait**, tedy slib, který se nesplní. Skóre je heuristika, ne měření mozku.

## Dvě hry v jedné

1. **Hra pro uživatele.** Duely hooků (hádáte, který fungoval lépe), souboje s "bossy" (napište hook, který překoná benchmark oboru), laboratoř (naučte se nenahlížet do testů), Vault (karty se studiemi). Postup, série dnů, sběratelské karty s **zveřejněnými šancemi** a pity timerem.
2. **Hra o pozornost.** Samotný obsah, který systém generuje, je skórován stejným modelem a poměřován s korpusem.

## Co je opravdu hotové a co potřebuje vaše vstupy

| Část | Stav v tomto repozitáři |
|---|---|
| Scoring, benchmark, pattern mining, kalibrace, laboratoř | Hotovo, testováno na syntetickém korpusu se zasazenými efekty |
| Hra (single-file HTML), lokální API server | Hotovo |
| Generátory (články, SEO, GEO, sociální sítě, video, reklamy), Trust Shield | Hotovo; offline režim nevymýšlí prózu, zapisuje `[[ADD: ...]]`; psaní prózy zajišťuje Claude (`--writer anthropic`) |
| Šetrný sběr (robots.txt, TDM, feedy, sitemapy), import vlastních analytik | Hotovo a testováno offline; **živý sběr vyžaduje síť** |
| Hledání studií (OpenAlex, Crossref, arXiv) | Hotovo a testováno offline; **živé hledání vyžaduje síť** |
| Seed ledger studií | Sepsáno z paměti autora; do ověření přes Crossref (`kingctl evidence verify`) je označeno jako **neověřené** |
| Skutečná data značek | Nejsou součástí repozitáře (autorská práva, výkonnostní čísla nejsou veřejná). Demo používá fiktivní značky a **simulovaná** čísla. |

Podrobnosti v `03-architektura.md`, metodika v `04-metodika.md`, pravidla sběru dat v `05-scraping-a-pravo.md`.
