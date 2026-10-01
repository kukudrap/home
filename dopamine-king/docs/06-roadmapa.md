# Roadmapa

Verze 0.1 (tento repozitář) je **svislý řez**: celý řetězec od sběru po hru běží a je otestovaný, ale na syntetických datech. Další kroky mění demo na produkt.

## Známá omezení verze 0.1
- Zástupné texty `[[ADD: ...]]` v offline režimu nesou **anglické** zadání pro pisatele i v českých balíčcích (je to totéž zadání, které dostává model). Lokalizace zadání do češtiny je malá, ale pracná úprava všech 28 builderů.
- Skóre hooku má slovníky pro češtinu a angličtinu; u jiných jazyků se použije anglický slovník, takže smysl mají jen signály nezávislé na jazyce (čísla, interpunkce, délka).
- Živý sběr běží jen proti hostům, které síť prostředí povolí (viz otevřené otázky).

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

## v1.0: služba
Fakturace, správa dat a souhlasů, dokumentace pro audit (GDPR, bezpečnost).

## Otevřené otázky na vás
1. **Co přesně znamená "PBM" v zadání?** Zkratku jsem nedokázal jednoznačně rozluštit, proto je sběr obsahu nezávislý na oboru (kohorty se nastavují v `models.py` a v registru značek). Stačí napsat, jaký obor nebo typ obsahu myslíte, a upravím kohorty i seznam značek.
2. **Síť.** Prostředí, ve kterém vznikl tento kód, blokuje živé zdroje (OpenAlex, Crossref, arXiv, weby značek). Pro živý sběr a hledání studií povolte tyto hosty v nastavení sítě prostředí, nebo spusťte `kingctl` lokálně.
3. **Klíč Anthropic** (volitelné): bez něj generátor v režimu `offline` zapisuje jen strukturu a `[[ADD: ...]]`; s klíčem (`ANTHROPIC_API_KEY`) píše prózu Claude.
4. **Vlastní analytika (CSV)** aspoň jedné značky pro první skutečnou kalibraci modelu.
5. **Konkurenti a klíčové dotazy** pro měření viditelnosti v AI odpovědích.
