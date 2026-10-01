# Sběr dat: pravidla, zdroje a právo

> Tento dokument není právní poradenství. Před komerčním nasazením si pravidla ověřte u právníka a v aktuálních podmínkách každého zdroje.

## Zásada

**Nesbíráme víc, než potřebujeme, a nic, co nám majitel zakázal.** "Mega scrape" znamená široký a **šetrný** sběr veřejných dat, ne hrubou sílu.

## Co sběrač dělá (a co nikdy)

| Pravidlo | Provedení |
|---|---|
| Respektuje `robots.txt` (RFC 9309) | 4xx na robots.txt = povoleno, 5xx nebo nedostupné = zakázáno pro tento běh; skupina pro token `DopamineKing` má přednost před `*`; dodržuje `Crawl-delay` |
| Respektuje rezervaci práv pro text a data mining | Hlavička HTTP `tdm-reservation: 1`, `<meta name="tdm-reservation">`; takový obsah se **neukládá** |
| Preferuje feedy a sitemapy před procházením HTML | Nejvýše 3 hádané adresy feedů na značku, jinak jen to, co web sám nabízí |
| Je zdvořilý | Limit požadavků na hostitele, opakování s exponenciální prodlevou, podmíněné GET (ETag), identifikovatelný User-Agent s kontaktem (`KING_CONTACT`) |
| Ukládá minimum | Metadata, **krátký výňatek (nejvýše 300 znaků)**, odvozená čísla (délky, počty nadpisů, schema typy). **Nikdy ne celý text.** |
| Minimalizuje osobní údaje | Jméno autora se neukládá, jen příznak `has_byline` |
| Nesbírá sociální sítě procházením HTML | Instagram, TikTok, LinkedIn a X to ve svých podmínkách zakazují; použijte oficiální API nebo **export vlastních analytik** (`kingctl import-csv`) |

## Zdroje podle spolehlivosti signálu

1. **Vlastní analytika (CSV export)**: nejlepší pravda o výkonu, vaše data, žádný právní problém. Hlavičky v češtině i angličtině.
2. **Oficiální API** (YouTube Data API, Reddit API a podobně): vyžadují klíč a dodržení kvót; konektory jsou na roadmapě.
3. **Veřejné signály** (komentáře v RSS, body a komentáře na Hacker News přes veřejné API): slabší a zkreslené (technické publikum), proto mají nižší váhu.
4. **Feedy a sitemapy značek**: tituly, data, výňatky; bez výkonových čísel.
5. **Hromadné veřejné datasety** (Common Crawl, GDELT, Wayback CDX): preferujte stažení hotového datasetu před vlastním procházením.
6. **Ocenění a výběry** (veřejné seznamy oceněných kampaní): kurátorský signál úspěchu.

## Právní rámec ve stručnosti (EU a Česko)

- **Autorské právo.** Plný text článků je chráněné dílo; krátké metadata a odvozené statistiky jsou nízkorizikové. Směrnice o autorském právu na jednotném digitálním trhu (2019/790) zná výjimky pro text a data mining (čl. 3 pro výzkumné organizace, čl. 4 pro libovolný účel), ale držitel práv si může využití **vyhradit strojově čitelně** (robots.txt, hlavička TDM). Proto sběrač vyhrazení respektuje.
- **Podmínky služeb.** I veřejně dostupná data mohou mít zakázané automatické stahování. Porušení smluvních podmínek je samostatné riziko.
- **GDPR.** Jména autorů, komentátorů a profilů jsou osobní údaje. Neukládáme je; pokud sbíráte vlastní data, mějte právní titul a minimalizujte.
- **Nekalé obchodní praktiky** (směrnice 2005/29/ES, zákon o ochraně spotřebitele). Falešný nedostatek ("zbývají 2 kusy"), skrytá reklama a zavádějící tvrzení jsou zakázané. Proto je ve Trust Shieldu kontrolujeme.
- **AI-generovaný obsah.** Nařízení o umělé inteligenci (čl. 50, povinnosti transparentnosti) a pravidla platforem vyžadují za určitých podmínek označení. Ověřte aktuální termíny a výjimky.
- **Vyhledávače.** Zásady Google proti "scaled content abuse" míří na hromadně vyráběný obsah s nízkou hodnotou bez ohledu na to, jak vznikl. Generátor proto zapisuje `[[ADD: ...]]` a quality gate vyžaduje vlastní zkušenost.

## Co nikdy nedělat

- Nepřihlašovat se, neobcházet přihlášení, CAPTCHA, ani technická omezení.
- Neukládat a nepublikovat cizí text jako vlastní. Dopamine King učí **vzory** (struktura, délka, typ hooku), ne kopíruje věty.
- Nesbírat osobní profily ani komentáře jednotlivců.
- Nepoužívat vzorek značek jako "důkaz" o výkonu bez uvedení zdroje a zkreslení.
