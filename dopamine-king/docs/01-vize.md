# Vize: Dopamine King

## Jedna věta

Dopamine King je marketingový stroj, který nejdřív zjistí, co skutečně funguje (hledání na webu, benchmarky, vědecké studie, vlastní experimenty), a teprve potom vygeneruje obsah ve všech formátech: SEO a GEO články, příspěvky, video scénáře, reklamy. Je zabalený do hry, ve které si uživatel na skutečných datech trénuje úsudek a učí se experimentovat.

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

1. Hra pro uživatele. Souboje o pořadí, výskyt a tvrzení ze skutečných hledání, souboje s bossy (napište hook, který obstojí vedle skutečného titulku), přehled trhu s úkoly, laboratoř se skutečným A/B testem a dvěma simulacemi, Trezor s kartami a studiemi. Postup, série dnů a sběratelské karty se zveřejněnými šancemi a pojistkou.
2. **Hra o pozornost.** Samotný obsah, který systém generuje, je skórován stejným modelem a poměřován s korpusem.

## Co je opravdu hotové a co potřebuje vaše vstupy

| Část | Stav v tomto repozitáři |
|---|---|
| Scoring, benchmark, pattern mining, kalibrace, laboratoř | Hotovo, testováno na syntetickém korpusu se zasazenými efekty |
| Hra (single-file HTML) na skutečných datech z uložených hledání, lokální API server | Hotovo |
| Generátory (články, SEO, GEO, sociální sítě, video, reklamy), Trust Shield | Hotovo; offline režim nevymýšlí prózu, zapisuje `[[ADD: ...]]`; psaní prózy zajišťuje Claude (`--writer anthropic`) |
| Šetrný sběr (robots.txt, TDM, feedy, sitemapy), import vlastních analytik | Hotovo a testováno offline; **živý sběr vyžaduje síť** |
| Hledání studií (OpenAlex, Crossref, arXiv) | Hotovo a testováno offline; **živé hledání vyžaduje síť** |
| Seed ledger studií | 32 záznamů, z toho **23 potvrzeno** veřejnými zdroji (název, časopis, rok, DOI); ostatní nesou poznámku, jak daleko ověření došlo. `kingctl evidence verify` je znovu ověří přes Crossref (potřebuje síť). |
| Skutečná data o trhu | 88 uložených hledání ze dne 23. 10. 2026 jsou v repozitáři (jen titulky, adresy a pořadí). Výkonnostní čísla značek nejsou veřejná, proto v repozitáři nejsou. Starší demo má fiktivní značky a simulovaná čísla a zůstává jako `build-web --synthetic`. |

## Edice pro obor: MITO LIGHT (fotobiomodulace)

Obecný stroj se přizpůsobuje oboru **daty, ne kódem**. První edice je pro fotobiomodulaci (červené a blízké infračervené světlo) a značku MITO LIGHT. Protože podle veřejných zdrojů jde o nezdravotnický přístroj, edice přidává profil tvrzení **wellness**: žádná diagnostika, léčba ani prevence nemocí, přínosy jen opatrně a se zdrojem. Silné stránky oboru jsou pod kontrolou důkazů (mapa tvrzení počítá sílu důkazů jen z ověřených studií); to, co se nesmí říkat, hlídá Trust Shield. Podrobnosti v [07-fotobiomodulace.md](07-fotobiomodulace.md), regulace v [08-regulace-pbm.md](08-regulace-pbm.md).

Podrobnosti v `03-architektura.md`, metodika v `04-metodika.md`, pravidla sběru dat v `05-scraping-a-pravo.md`.
