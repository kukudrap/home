# Ukázka: texty pro MITO LIGHT (návrh)

Hotová ukázka toho, co nástroj vyrobí: pět formátů (příspěvek na Instagram, krátké video, SEO článek, GEO stránka s odpověďmi, newsletter) pro zadání `mito-light-cs`. Texty napsal Claude do šablony slotů (`fills.json`), Dopamine King je zkontroloval Štítem důvěry v profilu **wellness**: **0 chyb**.

Zbývá 6 varování a jsou záměrná. Údaje, které nejsou ve faktech zadání a které si nikdo nesmí vymyslet, zůstávají jako `[[ADD: ...]]`: autor textu, datum aktualizace, citace jmenovaného odborníka a identita odesílatele newsletteru. Dokud je nedoplní člověk, kus zůstává ve stavu "ke kontrole".

**Je to návrh, ne hotová kampaň.**

- Fakta o značce (původ, test výkonu, parametry panelu Mitohacker 4.0, řada modelů) pocházejí z veřejných zdrojů a **musí je potvrdit MITO LIGHT**. Doby sezení, vzdálenosti a dávky v textech záměrně nejsou: patří do návodu výrobce.
- Studie jsou jen ty, které registr oboru eviduje jako ověřené (šest přehledů a metaanalýz o světle kolem cvičení u zdravých lidí). Výsledky jsou smíšené a texty to říkají: žádné sliby, malé efekty, rozdíly mezi skupinami. To je záměr, odpovídá to nezdravotnickému určení přístroje.
- Kontrola Štítem důvěry hlídá slova, ne celkový dojem. Schválení odpovědnou osobou (podle potřeby i regulatorním poradcem) zůstává nutné, viz [docs/08-regulace-pbm.md](../../docs/08-regulace-pbm.md).

## Soubory

| Soubor | Co to je |
|---|---|
| `fills.json` | Texty slotů (šablonu vyrábí `forge --emit-slots`) |
| `out/` | Výsledek: jeden soubor na formát, titulky `.srt`, strukturovaná data `.jsonld`, `report.md` s kontrolami a bodováním |

## Jak to vzniklo a jak to zopakovat

```bash
cd dopamine-king && export PYTHONPATH=src
python3 -m dopamine_king forge --vertical pbm --sample mito-light-cs \
    --formats instagram_caption,short_video_script,seo_article,geo_answer_page,newsletter \
    --writer file --fills examples/mito-light-cs/fills.json --out examples/mito-light-cs/out
```

Test `tests/test_examples.py` hlídá, že ukázka dál prochází bez chyb a že soubory v `out/` odpovídají tomu, co příkaz vyrobí. Když změníte pravidla nebo formáty, spusťte příkaz znovu a výsledek commitněte (soubor `pack.json` se do repozitáře nedává).
