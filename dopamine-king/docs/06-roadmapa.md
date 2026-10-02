# Roadmapa

Verze 0.1 (tento repozitář) je **svislý řez**: celý řetězec od sběru po hru běží a je otestovaný, ale na syntetických datech. Další kroky mění demo na produkt.

## Známá omezení verze 0.1
- Zástupné texty `[[ADD: ...]]` v offline režimu nesou **anglické** zadání pro pisatele i v českých balíčcích (je to totéž zadání, které dostává model). Lokalizace zadání do češtiny je malá, ale pracná úprava všech 28 builderů.
- Skóre hooku má slovníky pro češtinu a angličtinu; u jiných jazyků se použije anglický slovník, takže smysl mají jen signály nezávislé na jazyce (čísla, interpunkce, délka).
- Živý sběr běží jen proti hostům, které síť prostředí povolí (viz otevřené otázky).
- Kontrola tvrzení (profil `wellness`) čte češtinu a angličtinu a hlídá slova a jejich vzdálenost, ne význam; obrázky, hashtagy ani jiné jazyky nehlídá.

## v0.2: skutečná data
- Konektory: YouTube Data API, Reddit API, hromadný import z GDELT a Common Crawl, historie přes Wayback CDX (vše s klíči, kvótami a dodržením podmínek).
- Rozšíření a ověření registru značek (stovky značek, automatické objevování feedů), plánovač sběru a inkrementální běhy.
- Import vlastních analytik (GA4, Meta Business Suite, LinkedIn Analytics): mapování na signály Success Indexu.
- Success Index v2: oddělení placeného a organického dosahu, sezónnost a kampaně.

## v0.3: lepší model
- Doplnit slovníky o klasifikátor hooků nad vlastním korpusem při zachování vysvětlitelnosti (které části textu skóre zvedly).
- Další jazyky (slovenština, němčina, polština), slovníky učené z korpusu.
- Kauzální vrstva: uplift z vlastních A/B experimentů, sekvenční testy (mSPRT), předregistrace hypotéz.

## v0.4: viditelnost v AI odpovědích (GEO)
- Živé měření: pravidelné dotazy na odpovědní enginy přes jejich API, uložení odpovědí, trend míry zmínek a citací, share of voice, upozornění na pokles.
- Experimenty GEO: před a po na úrovni stránek s kontrolními skupinami.
- Kontrola schema.org, `robots.txt` pro AI crawlery a `llms.txt` v produkci.

## v0.5: tým a provoz
- Více uživatelů, role, workflow schvalování ("člověk ve smyčce"), verze textů, audit log Trust Shieldu.
- Postgres, fronta úloh, Docker, autentizace, API klíče na workspace.
- Publikace přes API (WordPress, LinkedIn, plánovače) **až po schválení člověkem**; automatické publikování bez kontroly se nepřipravuje záměrně.

## Edice PBM (MITO LIGHT): další kroky
Edice je hotový svislý řez (viz [07-fotobiomodulace.md](07-fotobiomodulace.md)). Co je třeba udělat, aby z ní byl provozní nástroj:

1. **Ověřit zbylých 16 záznamů studií** (`kingctl evidence verify --vertical pbm --save ...` a `evidence search --sources pubmed` pro každé téma). Teprve ověřené záznamy zvedají sílu důkazů v mapě tvrzení. Kvůli omezení vyhledávání v prostředí, kde edice vznikla, se to nepovedlo.
2. **Živý sběr registru 26 značek oboru** (potřebuje síť) a rozšíření registru na stovky značek, včetně srovnání českého a slovenského trhu.
3. **Kontrola pravidel regulatorním poradcem** a doplnění o to, co řekne: seznamy výrazů a témata jsou data, úprava nevyžaduje změnu kódu. Prověřit zejména dopis Ministerstva zdravotnictví o MITO LIGHT 3.0 (zatím jediný nepotvrzený zdroj, viz [08-regulace-pbm.md](08-regulace-pbm.md)).
4. **Další pravidlové profily:** zdravotnický prostředek (pro klinické přístroje nebo pokud se status změní) a lokalizace (slovenština, němčina včetně německého zákona o reklamě na léčivé prostředky, angličtina pro USA a Velkou Británii).
5. **Soubor důkazů ke každému tvrzení** (claim file: zdroj, datum, populace, dávka) vytvářený automaticky z mapy tvrzení, aby bylo možné prokázat věcnou přesnost na požádání dozorového orgánu.
6. **Schvalovací workflow:** koncept, kontrola Štítem důvěry, schválení odpovědnou osobou, archiv schválených verzí, smlouvy a kontrolní seznam pro influencery a prodejce.
7. **Kontrola obrázků a videa** (před a po, bílé pláště, nápisy ve videu), protože textová pravidla je nevidí, a kontrola proti aktuálním pravidlům reklamních platforem.
8. **Měření a vlastní analytika značky** (import CSV z Meta, Google, e-shopu), aby se nahradila simulovaná demo čísla a kalibrovalo se na skutečném výkonu.

## v1.0: služba
Fakturace, správa dat a souhlasů, dokumentace pro audit (GDPR, bezpečnost).

## Otevřené otázky na vás
1. **PBM je fotobiomodulace a nástroj má sloužit značce MITO LIGHT.** Tím je první otázka vyřešená; edice je v [07-fotobiomodulace.md](07-fotobiomodulace.md). Zbývá potvrdit u značky věci, které z veřejných zdrojů nejsou jisté (tykání nebo vykání, aktivní kanály, cílové trhy a persony, certifikace, ozáření měřené v mW/cm2, zda další generace mají vlastní stanovisko ministerstva); úplný seznam je v dokumentaci edice.
2. **Síť.** Prostředí, ve kterém vznikl tento kód, blokuje živé zdroje (OpenAlex, Crossref, arXiv, weby značek). Pro živý sběr a hledání studií povolte tyto hosty v nastavení sítě prostředí, nebo spusťte `kingctl` lokálně.
3. **Klíč Anthropic** (volitelné): bez něj generátor v režimu `offline` zapisuje jen strukturu a `[[ADD: ...]]`; s klíčem (`ANTHROPIC_API_KEY`) píše prózu Claude.
4. **Vlastní analytika (CSV)** aspoň jedné značky pro první skutečnou kalibraci modelu.
5. **Konkurenti a klíčové dotazy** pro měření viditelnosti v AI odpovědích.
