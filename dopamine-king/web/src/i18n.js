/* Strings for the whole UI in Czech and English.
 *
 * Every entry is written as a pair [english, czech], so both languages always have the same keys.
 * web/tests/i18n.test.js checks key sets, empty values and placeholders, and that every key used in
 * the sources exists. Data coming from the bundle uses name_en / name_cs style fields; use pick().
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else { root.DK = root.DK || {}; root.DK.i18n = factory(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var LANGS = ["cs", "en"];
  var T = {};

  /** Register a section: add("nav", {home: ["Home", "Domů"]}) defines the key "nav.home". */
  function add(section, table) {
    Object.keys(table).forEach(function (k) { T[section + "." + k] = table[k]; });
  }

  // ---- app shell ---------------------------------------------------------------------------
  add("app", {
    name: ["DOPAMINE KING", "DOPAMINE KING"],
    tagline: ["Train your feel for hooks that work", "Trénuj cit pro hooky, které fungují"],
    skip: ["Skip to content", "Přeskočit na obsah"],
    noscript: ["Dopamine King needs JavaScript. Everything runs in your browser and nothing is sent anywhere.", "Dopamine King potřebuje JavaScript. Vše běží ve tvém prohlížeči a nic se nikam neodesílá."],
    loading: ["Loading the game...", "Načítám hru..."],
    loadFailed: ["The game data could not be loaded.", "Data hry se nepodařilo načíst."],
    devHint: ["Development page: serve the web folder over http, for example", "Vývojová stránka: spusť složku web přes http, například"],
    retry: ["Try again", "Zkusit znovu"],
    stored: ["Progress is saved in this browser only.", "Postup se ukládá jen v tomto prohlížeči."],
    memoryOnly: ["Browser storage is blocked, so progress is kept only until you close this tab. You can export it from your profile.", "Úložiště prohlížeče je zablokované, takže se postup drží jen do zavření této karty. Můžeš ho exportovat z profilu."]
  });

  add("nav", {
    label: ["Main navigation", "Hlavní navigace"],
    home: ["Home", "Domů"],
    arena: ["Arena", "Aréna"],
    boss: ["Boss", "Boss"],
    lab: ["Lab", "Laboratoř"],
    vault: ["Vault", "Trezor"],
    forge: ["Forge", "Kovárna"],
    guru: ["Guru", "Guru"],
    about: ["About", "O hře"],
    more: ["More", "Další"],
    moreLabel: ["More sections", "Další sekce"]
  });

  add("top", {
    level: ["Level {n}", "Úroveň {n}"],
    levelAria: ["Level {n}, {title}. {into} of {span} XP towards the next level. Open your profile.", "Úroveň {n}, {title}. {into} z {span} XP do další úrovně. Otevřít profil."],
    xp: ["{n} XP", "{n} XP"],
    streak: ["Streak", "Série"],
    streakAria: ["Streak: {n} days in a row. Streak freezes held: {f}.", "Série: {n} dnů v řadě. Zmrazení série: {f}."],
    streakTitle: ["Daily streak. A streak freeze protects it when you miss a day.", "Denní série. Zmrazení série ji ochrání, když jeden den vynecháš."],
    freezes: ["{n} freeze", "{n} zmrazení"],
    lang: ["Language", "Jazyk"],
    langCs: ["Čeština", "Čeština"],
    langEn: ["English", "English"],
    theme: ["Colour theme", "Barevný motiv"],
    toLight: ["Switch to the light theme", "Přepnout na světlý motiv"],
    toDark: ["Switch to the dark theme", "Přepnout na tmavý motiv"],
    demo: ["Demo data", "Demo data"],
    demoReal: ["Your data", "Tvoje data"],
    demoTitle: ["All engagement numbers in this demo are SIMULATED and the brands are fictional.", "Všechna čísla o zapojení v tomto dema jsou SIMULOVANÁ a značky jsou smyšlené."],
    live: ["Live", "Živě"],
    liveTitle: ["Connected to kingctl serve: the Forge and Guru forms are active.", "Připojeno ke kingctl serve: formuláře Kovárny a Guru jsou aktivní."],
    profile: ["Profile and settings", "Profil a nastavení"],
    sound: ["Sound", "Zvuk"],
    soundOn: ["Sound is on", "Zvuk je zapnutý"],
    soundOff: ["Sound is off", "Zvuk je vypnutý"]
  });

  add("common", {
    close: ["Close", "Zavřít"],
    cancel: ["Cancel", "Zrušit"],
    ok: ["Got it", "Rozumím"],
    back: ["Back", "Zpět"],
    next: ["Next", "Další"],
    copy: ["Copy", "Kopírovat"],
    copied: ["Copied", "Zkopírováno"],
    copyFailed: ["Copy failed, select the text by hand.", "Kopírování selhalo, označ text ručně."],
    yes: ["Yes", "Ano"],
    no: ["No", "Ne"],
    on: ["On", "Zapnuto"],
    off: ["Off", "Vypnuto"],
    all: ["All", "Vše"],
    none: ["None", "Žádné"],
    free: ["free", "zdarma"],
    new: ["New", "Nové"],
    locked: ["Locked", "Zamčeno"],
    owned: ["Owned", "Vlastníš"],
    simulated: ["SIMULATED DATA", "SIMULOVANÁ DATA"],
    simulatedShort: ["Simulated", "Simulace"],
    heuristic: ["Heuristic score", "Heuristické skóre"],
    min: ["{n} min", "{n} min"],
    points: ["{n} pts", "{n} b."],
    percent: ["{n}%", "{n} %"],
    of: ["{a} of {b}", "{a} z {b}"],
    comingSoon: ["Coming soon", "Již brzy"],
    error: ["Something went wrong.", "Něco se nepovedlo."],
    unknown: ["Unknown", "Neznámé"],
    yesNo: ["{yes} / {no}", "{yes} / {no}"],
    key: ["Key", "Klávesa"],
    action: ["Action", "Akce"],
    rank: ["Rank", "Pořadí"]
  });

  add("demo", {
    title: ["About the demo data", "O demo datech"],
    p1: ["Every engagement number you see here is SIMULATED. The brands are fictional and the corpus is synthetic.", "Každé číslo o zapojení, které tu vidíš, je SIMULOVANÉ. Značky jsou smyšlené a korpus je syntetický."],
    p2: ["The Dopamine Score is a transparent heuristic, not a neuroscience measurement.", "Dopamine Score je průhledná heuristika, ne neurovědecké měření."],
    p3: ["Nothing is sent anywhere: your progress is stored locally in this browser.", "Nic se nikam neodesílá: tvůj postup se ukládá lokálně v tomto prohlížeči."],
    more: ["Read how it works in About", "Přečti si, jak to funguje, v části O hře"]
  });

  add("profile", {
    title: ["Your profile", "Tvůj profil"],
    name: ["Display name", "Zobrazované jméno"],
    namePlaceholder: ["Optional", "Volitelné"],
    xpTo: ["{xp} XP in total. Next level at {next} XP.", "Celkem {xp} XP. Další úroveň při {next} XP."],
    stats: ["Stats", "Statistiky"],
    statArena: ["Duels won", "Vyhrané souboje"],
    statUpsets: ["Upsets called", "Trefená překvapení"],
    statBoss: ["Boss wins", "Výhry nad bossy"],
    statLab: ["Lab runs", "Pokusy v laboratoři"],
    statMyths: ["Myths right", "Správné mýty"],
    statChests: ["Chests opened", "Otevřené truhly"],
    statBestStreak: ["Best streak", "Nejlepší série"],
    statOracle: ["Oracle rating", "Hodnocení Orákula"],
    achievements: ["Achievements", "Úspěchy"],
    unlocked: ["Unlocked", "Odemčeno"],
    settings: ["Settings", "Nastavení"],
    themeAuto: ["Auto", "Auto"],
    themeDark: ["Dark", "Tmavý"],
    themeLight: ["Light", "Světlý"],
    sound: ["Sound effects", "Zvukové efekty"],
    soundHint: ["Off by default. Short, quiet tones for answers, wins and chests.", "Ve výchozím stavu vypnuto. Krátké tiché tóny pro odpovědi, výhry a truhly."],
    reduceMotion: ["Reduce motion", "Omezit animace"],
    reduceMotionHint: ["Also follows your system setting. Turns off confetti and big animations.", "Řídí se i nastavením systému. Vypne konfety a velké animace."],
    session: ["Break reminder", "Připomínka přestávky"],
    sessionHint: ["A friendly card after this many minutes of play in one session.", "Přátelská karta po tolika minutách hraní v jedné relaci."],
    data: ["Your data", "Tvoje data"],
    export: ["Export progress", "Exportovat postup"],
    import: ["Import progress", "Importovat postup"],
    imported: ["Progress imported.", "Postup byl importován."],
    "importErr.empty": ["That file is empty.", "Soubor je prázdný."],
    "importErr.too_large": ["That file is too large.", "Soubor je příliš velký."],
    "importErr.invalid_json": ["That file is not valid JSON.", "Soubor není platný JSON."],
    "importErr.wrong_app": ["That file was not exported by Dopamine King.", "Soubor nebyl exportován z Dopamine King."],
    "importErr.invalid_profile": ["No progress was found in that file.", "V souboru není žádný postup."],
    "importErr.read": ["The file could not be read.", "Soubor se nepodařilo přečíst."],
    reset: ["Reset progress", "Smazat postup"],
    resetAsk: ["This erases XP, cards and achievements in this browser. Export first if you want a backup.", "Tím se v tomto prohlížeči smaže XP, karty i úspěchy. Chceš-li zálohu, nejdřív exportuj."],
    resetYes: ["Yes, reset everything", "Ano, vše smazat"]
  });

  add("toast", {
    achievement: ["Achievement unlocked", "Úspěch odemčen"],
    quest: ["Quest complete +{xp} XP", "Úkol splněn +{xp} XP"],
    bonusChest: ["Bonus chest unlocked", "Bonusová truhla odemčena"],
    bonusChestText: ["All three daily quests are done. Open it in the Vault.", "Všechny tři denní úkoly jsou hotové. Otevři ji v Trezoru."],
    freezeUsed: ["Streak freeze used", "Zmrazení série použito"],
    freezeUsedText: ["A freeze kept your streak alive while you were away. Welcome back!", "Zmrazení udrželo tvou sérii, když jsi byl pryč. Vítej zpátky!"],
    freezeEarned: ["You earned a streak freeze", "Získal jsi zmrazení série"],
    freezeEarnedText: ["Every 7 days of streak earns one (you can hold 2).", "Každých 7 dní série jedno získáš (můžeš držet 2)."],
    levelUp: ["Level {n}!", "Úroveň {n}!"]
  });

  add("break", {
    title: ["Time for a short break?", "Dáš si krátkou pauzu?"],
    text: ["You have been playing for about {n} minutes. A stretch, some water or a short walk can help. Your progress is saved.", "Hraješ už asi {n} minut. Protáhnout se, napít se nebo se krátce projít může pomoct. Tvůj postup je uložený."],
    note: ["You can change or turn off this reminder in your profile.", "Připomínku můžeš změnit nebo vypnout ve svém profilu."],
    keep: ["Keep playing", "Hrát dál"],
    settings: ["Reminder settings", "Nastavení připomínky"]
  });

  add("quest", {
    arena_wins: ["Win {n} Arena rounds", "Vyhraj {n} kol v Aréně"],
    hard_duel: ["Call a hard duel correctly", "Správně rozhodni těžký souboj"],
    upset_call: ["Call an upset against the model", "Správně tipni překvapení proti modelu"],
    boss_win: ["Beat a boss", "Poraz bosse"],
    lab_run: ["Run a Lab experiment", "Spusť experiment v laboratoři"],
    myths_5: ["Answer {n} Myth or Fact cards", "Odpověz na {n} karet Mýtus, nebo fakt"],
    vault_open: ["Open a Vault card", "Otevři kartu v Trezoru"],
    clean_win: ["Beat a boss with clickbait risk under 10%", "Poraz bosse s rizikem clickbaitu pod 10 %"]
  });

  add("home", {
    hello: ["Welcome", "Vítej"],
    helloName: ["Welcome back, {name}", "Vítej zpátky, {name}"],
    lead: ["Learn what makes a hook work: pick winning headlines, beat benchmark bosses, run honest experiments and collect evidence cards. All results here are simulated demo data.", "Zjisti, čím hook funguje: vybírej vítězné titulky, poraz bossy podle benchmarků, pouštěj férové experimenty a sbírej karty s důkazy. Všechny výsledky tu jsou simulovaná demo data."],
    xpLine: ["{xp} XP in total, {n} to level {level}", "Celkem {xp} XP, do úrovně {level} zbývá {n}"],
    "next.chest": ["Open your chest", "Otevři svou truhlu"],
    "next.quest": ["Next: {quest}", "Další krok: {quest}"],
    "next.oracle": ["Unlock your Oracle rating in the Arena", "Odemkni si hodnocení Orákula v Aréně"],
    "next.boss": ["Take on a boss", "Vyzvi bosse"],
    "quests.title": ["Daily quests", "Denní úkoly"],
    "quests.sub": ["Three new quests every day, +30 XP each. Finish all three for a bonus chest.", "Každý den tři nové úkoly, každý za +30 XP. Splň všechny tři a získáš bonusovou truhlu."],
    "quests.done": ["Done", "Hotovo"],
    "quests.go": ["Go", "Jdi na to"],
    "quests.bonus": ["Finish all three to open a bonus chest.", "Splň všechny tři a otevře se bonusová truhla."],
    "quests.allDone": ["All three done. Your bonus chest is ready in the Vault.", "Všechny tři hotové. Bonusová truhla čeká v Trezoru."],
    "chest.title": ["Chests", "Truhly"],
    "chest.ready.one": ["{n} chest ready to open", "{n} truhla připravena k otevření"],
    "chest.ready.few": ["{n} chests ready to open", "{n} truhly připraveny k otevření"],
    "chest.ready.other": ["{n} chests ready to open", "{n} truhel připraveno k otevření"],
    "chest.none": ["No chest ready. Win a boss or finish all daily quests to earn one.", "Žádná truhla není připravená. Poraz bosse nebo splň všechny denní úkoly a nějakou získáš."],
    "chest.pity": ["Pity timer: {n} of {max} chests without a rare or better card.", "Pojistka: {n} z {max} truhel bez vzácné nebo lepší karty."],
    "chest.open": ["Open in the Vault", "Otevřít v Trezoru"],
    "chest.odds": ["See the published drop rates", "Zobrazit zveřejněné šance"],
    "oracle.title": ["Oracle rating", "Hodnocení Orákula"],
    "oracle.locked": ["Answer {n} more duels with the confidence slider to reveal it.", "Odpověz ještě na {n} soubojů s posuvníkem jistoty a rating se odhalí."],
    "oracle.hint": ["How well your confidence matches reality. 0 is a coin flip, 100 is perfect calibration.", "Jak dobře tvoje jistota odpovídá realitě. 0 je hod mincí, 100 dokonalá kalibrace."],
    "time.title": ["Played today", "Dnes odehráno"],
    "time.hint": ["A reminder appears after {n} minutes in one session.", "Připomínka přestávky přijde po {n} minutách v jedné relaci."],
    "time.hintOff": ["Break reminders are off.", "Připomínky přestávek jsou vypnuté."],
    "streak.title": ["Streak", "Série"],
    "streak.days.one": ["{n} day", "{n} den"],
    "streak.days.few": ["{n} days", "{n} dny"],
    "streak.days.other": ["{n} days", "{n} dní"],
    "streak.best": ["Best: {n}", "Nejlepší: {n}"],
    "streak.freezes": ["Freezes: {n}", "Zmrazení: {n}"],
    "streak.hint": ["Freezes protect your streak if you skip a day. You earn one every 7 days of streak, up to 2.", "Zmrazení ochrání tvou sérii, když jeden den vynecháš. Získáš ho za každých 7 dní série, nejvýš 2."],
    "streak.fresh": ["A new streak starts with your next round.", "Nová série začne tvým dalším kolem."],
    "accuracy.title": ["Arena accuracy", "Úspěšnost v Aréně"],
    "accuracy.none": ["Play a duel to see it.", "Zahraj souboj a uvidíš ji."],
    "accuracy.hint": ["{a} of {b} duels called correctly", "{a} z {b} soubojů rozhodnuto správně"],
    "modes.title": ["Choose your game", "Vyber si hru"],
    "mode.arena": ["Pick which hook performed better.", "Vyber hook, který fungoval lépe."],
    "mode.boss": ["Write a hook and beat a benchmark.", "Napiš hook a poraz benchmark."],
    "mode.lab": ["Run honest A/B experiments.", "Pouštěj férové A/B experimenty."],
    "mode.vault": ["Evidence cards, studies and myths.", "Karty s důkazy, studie a mýty."],
    "mode.forge": ["Content packs from a brief.", "Balíčky obsahu ze zadání."],
    "mode.guru": ["A four week content plan.", "Čtyřtýdenní plán obsahu."],
    "xp.title": ["How XP works", "Jak funguje XP"],
    "xp.arena": ["Arena: {base} XP for a correct call, +{medium} on medium and +{hard} on hard duels.", "Aréna: {base} XP za správný tip, +{medium} u střední a +{hard} u těžké obtížnosti."],
    "xp.upset": ["+{n} XP when you call an upset against the model.", "+{n} XP, když trefíš překvapení proti modelu."],
    "xp.combo": ["Combo: every {step} correct answers in a row raise the multiplier, up to x{max}.", "Kombo: každých {step} správných odpovědí v řadě zvýší násobitel, nejvýš na x{max}."],
    "xp.confidence": ["+{n} XP for a correct call with confidence of {c} percent or more. Confidence also builds your Oracle rating.", "+{n} XP za správný tip s jistotou {c} procent a více. Jistota zároveň buduje hodnocení Orákula."],
    "xp.wrong": ["A wrong answer still earns {n} XP. Nothing is ever taken away.", "I špatná odpověď přinese {n} XP. Nic se ti nikdy neodebírá."],
    "xp.boss": ["Boss: the full XP reward for your first win over that boss each day, {share} percent for repeat wins.", "Boss: plná odměna za první výhru nad daným bossem každý den, za opakované výhry {share} procent."],
    "xp.lab": ["Lab: +{right} XP for a correct decision, +{wrong} for a wrong one.", "Laboratoř: +{right} XP za správné rozhodnutí, +{wrong} za špatné."],
    "xp.myth": ["Myth or Fact: +{right} XP when right, +{wrong} when wrong.", "Mýtus, nebo fakt: +{right} XP za správně, +{wrong} za špatně."],
    "xp.quest": ["Each daily quest is worth +{n} XP.", "Každý denní úkol má hodnotu +{n} XP."],
    "xp.dust": ["A duplicate card from a chest turns into {n} XP.", "Duplicitní karta z truhly se promění v {n} XP."],
    "xp.levels": ["Each level needs more XP than the last: level 2 starts at 100 XP, level 5 at 800, level 10 at 2,700.", "Každá úroveň potřebuje víc XP než předchozí: úroveň 2 začíná na 100 XP, úroveň 5 na 800, úroveň 10 na 2 700."],
    "xp.streak": ["Streak: play on consecutive days. A streak freeze (earned every 7 days, up to 2) covers a missed day. No guilt, ever.", "Série: hraj víc dní po sobě. Zmrazení série (za každých 7 dní, nejvýš 2) pokryje vynechaný den. Žádné výčitky."],
    "xp.ethics": ["Ethical by design: chest odds are published, a pity timer guarantees a rare or better card, nothing costs real money and sound is off by default.", "Etické už z návrhu: šance v truhlách jsou zveřejněné, pojistka zaručí vzácnou nebo lepší kartu, nic nestojí skutečné peníze a zvuk je ve výchozím stavu vypnutý."]
  });

  add("chart", {
    showTable: ["Show data as a table", "Zobrazit data jako tabulku"]
  });

  add("platform", {
    blog: ["Blog", "Blog"], newsroom: ["Newsroom", "Newsroom"], youtube: ["YouTube", "YouTube"], instagram: ["Instagram", "Instagram"],
    tiktok: ["TikTok", "TikTok"], x: ["X", "X"], linkedin: ["LinkedIn", "LinkedIn"], facebook: ["Facebook", "Facebook"],
    threads: ["Threads", "Threads"], reddit: ["Reddit", "Reddit"], email: ["Email", "E-mail"], ad: ["Ad", "Reklama"],
    podcast: ["Podcast", "Podcast"], web: ["Web", "Web"], other: ["Other", "Jiné"]
  });

  add("arena", {
    title: ["Hook Duel", "Souboj hooků"],
    lead: ["Two hooks, one winner. Pick the one that performed better in the simulated data, then see what the model thought.", "Dva hooky, jeden vítěz. Vyber ten, který v simulovaných datech fungoval lépe, a pak se podívej, co si myslel model."],
    prompt: ["Which hook performed better?", "Který hook fungoval lépe?"],
    keys: ["Keyboard: A or the left arrow picks the first hook, B or the right arrow the second, Enter moves on.", "Klávesnice: A nebo šipka doleva vybere první hook, B nebo šipka doprava druhý, Enter jde dál."],
    pick: ["Pick hook {side}", "Vybrat hook {side}"],
    controls: ["Duel settings", "Nastavení souboje"],
    stats: ["Your run", "Tvoje série"],
    difficulty: ["Difficulty", "Obtížnost"],
    easy: ["Easy", "Snadná"],
    medium: ["Medium", "Střední"],
    hard: ["Hard", "Těžká"],
    preferLang: ["Duels in my language first", "Nejdřív souboje v mém jazyce"],
    confidence: ["Rate my confidence", "Ohodnotit moji jistotu"],
    confShort: ["Optional: it builds your Oracle rating.", "Volitelné: buduje hodnocení Orákula."],
    confHint: ["50 percent is a coin flip. Right with 80 percent or more pays +3 XP; being sure and wrong costs rating, never XP.", "50 procent je hod mincí. Správný tip s jistotou 80 procent a více přidá +3 XP; jistota a omyl snižují rating, nikdy XP."],
    confValue: ["Confidence in my pick", "Jistota ve svém tipu"],
    combo: ["Combo", "Kombo"],
    comboRow: ["{n} in a row", "{n} v řadě"],
    comboNext: ["{n} more for x{m}", "ještě {n} pro x{m}"],
    comboMax: ["Maximum combo", "Maximální kombo"],
    round: ["Round {n}", "Kolo {n}"],
    session: ["Correct this session", "Správně v této relaci"],
    oracle: ["Oracle rating", "Hodnocení Orákula"],
    langCs: ["Czech", "Česky"],
    langEn: ["English", "Anglicky"],
    winner: ["Winner", "Vítěz"],
    yourPick: ["Your pick", "Tvůj tip"],
    modelPick: ["Model's pick", "Tip modelu"],
    success: ["Success index", "Index úspěchu"],
    score: ["Dopamine Score", "Dopamine Score"],
    result: ["Result of this duel", "Výsledek tohoto souboje"],
    details: ["Model details for this duel", "Podrobnosti modelu k tomuto souboji"],
    correct: ["Correct!", "Správně!"],
    wrong: ["Not this time", "Tentokrát ne"],
    upset: ["UPSET CALLED", "PŘEKVAPENÍ TREFENO"],
    upsetText: ["The model favoured the loser and you saw it coming.", "Model fandil poraženému a ty jsi to předvídal."],
    upsetMissed: ["This was an upset: the model favoured the loser.", "Tohle bylo překvapení: model fandil poraženému."],
    xpBase: ["Correct call +{n}", "Správný tip +{n}"],
    xpDifficulty: ["{level} duel +{n}", "Obtížnost {level} +{n}"],
    xpUpset: ["Upset +{n}", "Překvapení +{n}"],
    xpCombo: ["Combo x{n}", "Kombo x{n}"],
    xpConfidence: ["Confident +{n}", "Jistota +{n}"],
    xpParticipation: ["Participation +{n}", "Za účast +{n}"],
    modelProb: ["The model's win probability", "Pravděpodobnost výhry podle modelu"],
    modelAria: ["Model win probability: A {a} percent, B {b} percent. The model picked {pick}.", "Pravděpodobnost výhry podle modelu: A {a} procent, B {b} procent. Model tipoval {pick}."],
    scores: ["Dopamine Scores: A {a}, B {b}. The score is a heuristic, not a neuroscience measurement.", "Dopamine Score: A {a}, B {b}. Skóre je heuristika, ne neurovědecké měření."],
    why: ["Why the model leaned that way", "Proč se model přiklonil právě tak"],
    noReasons: ["The two hooks scored almost the same on every driver.", "Oba hooky měly téměř stejné skóre ve všech ohledech."],
    simNote: ["Simulated data: the success index comes from a synthetic corpus of fictional brands. Nothing here is a real campaign result.", "Simulovaná data: index úspěchu pochází ze syntetického korpusu smyšlených značek. Nic z toho není výsledek skutečné kampaně."],
    cycled: ["You have seen every duel for this filter, so they start over.", "Viděl jsi všechny souboje pro tento filtr, takže začínají znovu."],
    next: ["Next duel", "Další souboj"],
    announceCorrect: ["Correct. Hook {side} performed better. {xp} XP.", "Správně. Hook {side} fungoval lépe. {xp} XP."],
    announceWrong: ["Not this time. Hook {side} performed better. {xp} XP.", "Tentokrát ne. Hook {side} fungoval lépe. {xp} XP."],
    "empty.title": ["No duels in this edition", "V této edici nejsou žádné souboje"],
    "empty.text": ["The data bundle has no Arena duels yet. Rebuild it with the engine to play.", "Datový balíček zatím neobsahuje žádné souboje. Přegeneruj ho enginem a můžeš hrát."]
  });

  add("boss", {
    title: ["Boss Battle", "Souboj s bossem"],
    lead: ["Each boss sets a brief and a benchmark from its cohort. Write a hook, watch the live score and beat the boss without clickbait.", "Každý boss zadá téma a benchmark ze své kohorty. Napiš hook, sleduj živé skóre a poraz bosse bez clickbaitu."],
    tier1: ["Warm-up", "Rozcvička"],
    tier2: ["Tough", "Tvrdý"],
    tier3: ["Final boss", "Finální boss"],
    needs: ["Beat {p}% of hooks", "Překonej {p} % hooků"],
    wonToday: ["Won today", "Dnes vyhráno"],
    fight: ["Fight", "Bojovat"],
    fightAgain: ["Fight again", "Bojovat znovu"],
    "empty.title": ["No bosses in this edition", "V této edici nejsou žádní bossové"],
    "empty.text": ["The data bundle has no bosses yet.", "Datový balíček zatím neobsahuje žádné bossy."],
    benchNote: ["Benchmarks are percentiles of Dopamine Scores in the synthetic demo corpus of fictional brands. The score is a heuristic.", "Benchmarky jsou percentily Dopamine Score v syntetickém demo korpusu smyšlených značek. Skóre je heuristika."],
    notFound: ["Boss not found", "Boss nenalezen"],
    notFoundText: ["This boss is not in the current data bundle.", "Tento boss není v aktuálním datovém balíčku."],
    all: ["All bosses", "Všichni bossové"],
    inputLabel: ["Your hook", "Tvůj hook"],
    placeholder: ["Write a hook for the brief...", "Napiš hook k zadání..."],
    scoringLang: ["Scoring language", "Jazyk hodnocení"],
    langAuto: ["Auto", "Auto"],
    legend: ["Highlight legend", "Legenda zvýraznění"],
    "group.curiosity": ["Curiosity", "Zvědavost"],
    "group.surprise": ["Surprise", "Překvapení"],
    "group.emotion": ["Emotion", "Emoce"],
    "group.utility": ["Utility", "Užitek"],
    "group.relevance": ["Relevance", "Oslovení"],
    "group.risk": ["Risk", "Riziko"],
    "group.tone": ["Tone", "Tón"],
    noPhrases: ["No trigger phrases found yet. Try a question, a number or a \"how to\".", "Zatím žádné spouštěcí fráze. Zkus otázku, číslo nebo \"jak na to\"."],
    "cat.curiosity": ["curiosity", "zvědavost"],
    "cat.contrast": ["contrast", "kontrast"],
    "cat.emotion": ["emotion", "emoce"],
    "cat.practical": ["practical", "užitek"],
    "cat.social": ["social proof", "sociální oslovení"],
    "cat.second_person": ["speaks to you", "oslovení čtenáře"],
    "cat.clickbait": ["clickbait", "clickbait"],
    "cat.overclaim": ["overclaim", "přehnaný slib"],
    "cat.positive": ["positive tone", "pozitivní tón"],
    "cat.negative": ["negative tone", "negativní tón"],
    met: ["Condition met", "Podmínka splněna"],
    notMet: ["Condition not met yet", "Podmínka zatím není splněna"],
    meter: ["Dopamine Score meter", "Měřič Dopamine Score"],
    bossMarker: ["Boss {n}", "Boss {n}"],
    meterText: ["{n} out of 100", "{n} ze 100"],
    riskMeter: ["Clickbait risk meter", "Měřič rizika clickbaitu"],
    scoreTitle: ["Dopamine Score", "Dopamine Score"],
    noBench: ["No benchmark for this cohort in the data bundle, so the fight cannot be resolved.", "Pro tuto kohortu není v datovém balíčku benchmark, takže souboj nelze rozhodnout."],
    benchLine: ["Benchmark: {n} simulated hooks in {cohort} (demo data).", "Benchmark: {n} simulovaných hooků v kohortě {cohort} (demo data)."],
    driversTitle: ["Six drivers", "Šest faktorů"],
    driversNote: ["Each driver runs from 0 to 100. The score weighs the first five; fluency adjusts how easy the hook is to process.", "Každý faktor má 0 až 100. Skóre váží prvních pět; srozumitelnost upravuje, jak snadno se hook zpracuje."],
    shieldTitle: ["Trust Shield", "Štít důvěry"],
    shieldNote: ["Intact below 20% clickbait risk, cracked below 35%, broken above. A broken shield means no victory, however catchy the hook.", "Neporušený pod 20 % rizika clickbaitu, prasklý pod 35 %, rozbitý nad. Rozbitý štít znamená žádnou výhru, ať je hook sebelákavější."],
    tipsTitle: ["What to try next", "Co zkusit dál"],
    phrasesTitle: ["What the scorer saw", "Co scorer zachytil"],
    count: ["{c} / {max} characters, {w} words", "{c} / {max} znaků, {w} slov"],
    detected: ["Detected: {lang}", "Rozpoznáno: {lang}"],
    detectedNone: ["Detected: nothing yet", "Rozpoznáno: zatím nic"],
    pctLine: ["Better than about {p}% of the hooks in {cohort}.", "Lepší než asi {p} % hooků v kohortě {cohort}."],
    pctEmpty: ["Start typing and the meter moves.", "Začni psát a měřič se pohne."],
    condPct: ["Beat {p}% of hooks", "Překonej {p} % hooků"],
    condNow: ["now better than {p}%", "teď lepší než {p} %"],
    condScore: ["needs a score of {n}", "potřebuješ skóre {n}"],
    condWait: ["waiting for your hook", "čeká se na tvůj hook"],
    condRisk: ["Clickbait risk at most 35%", "Riziko clickbaitu nejvýš 35 %"],
    condNowRisk: ["now {n}%", "teď {n} %"],
    "shield.intact": ["Intact", "Neporušený"],
    "shield.cracked": ["Cracked", "Prasklý"],
    "shield.broken": ["Broken", "Rozbitý"],
    "shield.idle": ["Waiting", "Čeká"],
    "shieldRange.intact": ["under 20%", "pod 20 %"],
    "shieldRange.cracked": ["20% to 35%", "20 až 35 %"],
    "shieldRange.broken": ["35% and more", "35 % a víc"],
    riskPct: ["{n}% risk", "riziko {n} %"],
    tipEmpty: ["Write a few words. Tips from the scorer show up here.", "Napiš pár slov. Tady se objeví tipy od scorera."],
    liveStrip: ["Live result", "Živý výsledek"],
    attack: ["Attack", "Zaútočit"],
    stripScore: ["Score", "Skóre"],
    stripPct: ["Goal: {p}%", "Cíl: {p} %"],
    stripShield: ["Shield", "Štít"],
    resultRegion: ["Battle result", "Výsledek souboje"],
    writeFirst: ["Write a hook first.", "Nejdřív napiš hook."],
    announceWin: ["Victory! +{xp} XP.", "Vítězství! +{xp} XP."],
    announceLose: ["Not yet. See what to try next.", "Zatím ne. Podívej se, co zkusit dál."],
    victory: ["Victory!", "Vítězství!"],
    victoryText: ["{name} is down. Your hook beat the benchmark and kept its trust.", "{name} padl. Tvůj hook překonal benchmark a udržel si důvěru."],
    xpFirst: ["First win over this boss today: full reward.", "První výhra nad tímto bossem dnes: plná odměna."],
    xpRepeat: ["Repeat win: {n}% of the reward.", "Opakovaná výhra: {n} % odměny."],
    honestWin: ["Honest win: risk under 10%", "Poctivá výhra: riziko pod 10 %"],
    chestGained: ["Chest earned", "Získána truhla"],
    noChestRepeat: ["Chests come from the first win of the day", "Truhly se dávají za první výhru dne"],
    winPct: ["Better than {p}% of hooks", "Lepší než {p} % hooků"],
    openChest: ["Open the chest", "Otevřít truhlu"],
    keepEditing: ["Keep editing", "Pokračovat v úpravách"],
    lostPct: ["You beat about {p}% of hooks and the boss needs {need}%. About {gap} more points to go.", "Překonal jsi asi {p} % hooků a boss chce {need} %. Chybí asi {gap} bodu."],
    lostRisk: ["Clickbait risk is {n}%, above the 35% limit. Remove hype phrases and overclaims.", "Riziko clickbaitu je {n} %, nad limitem 35 %. Odstraň přehnané fráze a sliby."],
    notYet: ["Not yet", "Zatím ne"],
    notYetText: ["{name} holds on, but you can adjust and attack again. There is no penalty.", "{name} se drží, ale můžeš hook upravit a zaútočit znovu. Nic za to neplatíš."],
    tryThis: ["Try this", "Zkus tohle"],
    tryAgain: ["Edit and try again", "Upravit a zkusit znovu"],
    briefTitle: ["The brief", "Zadání"],
    winRule: ["To win, your hook must beat {p}% of the hooks in {cohort} and keep the clickbait risk at 35% or lower.", "K výhře musí tvůj hook překonat {p} % hooků v kohortě {cohort} a držet riziko clickbaitu na 35 % nebo níž."],
    langHint: ["This boss speaks {lang}. Write your hook in that language for the fairest score.", "Tento boss mluví {lang}. Napiš hook v tomto jazyce, skóre bude nejférovější."],
    "langName.cs": ["Czech", "česky"],
    "langName.en": ["English", "anglicky"],
    yourHook: ["Your hook", "Tvůj hook"],
    help: ["Ctrl+Enter attacks. Nothing is sent anywhere.", "Ctrl+Enter zaútočí. Nic se nikam neodesílá."],
    legendTitle: ["What gets highlighted", "Co se zvýrazňuje"]
  });

  add("lab", {
    title: ["Lab", "Laboratoř"],
    lead: ["Three mini games that teach honest experimentation: read the evidence, resist peeking and let the winners earn the traffic.", "Tři minihry, které učí férově experimentovat: čti důkazy, nenahlížej předčasně a nech vítěze, ať si traffic zaslouží."],
    simNote: ["Everything in the Lab is simulated in your browser with a seeded random generator. No real traffic, no real brands.", "Vše v laboratoři se simuluje ve tvém prohlížeči pomocí seedovaného generátoru náhody. Žádný skutečný traffic, žádné skutečné značky."],
    tabs: ["Lab games", "Hry v laboratoři"],
    "tab.duel": ["Duel", "Souboj"],
    "tab.peek": ["Don't Peek", "Nenahlížej"],
    "tab.bandit": ["Bandit Garden", "Zahrada banditů"],
    "empty.title": ["No scenarios in this edition", "V této edici nejsou žádné scénáře"],
    "empty.text": ["The data bundle has no Lab scenarios yet.", "Datový balíček zatím neobsahuje žádné laboratorní scénáře."],

    "duel.title": ["Duel: ship A, ship B or keep testing", "Souboj: nasadit A, nasadit B, nebo testovat dál"],
    "duel.intro": ["Scenario: {s}. Variant B changes it. Is B really better than A? Choose how many visitors to test, read the evidence, then decide. The truth stays hidden until you do.", "Scénář: {s}. Varianta B to mění. Je B opravdu lepší než A? Vyber, kolik návštěvníků otestovat, přečti si důkazy a rozhodni se. Pravda zůstane skrytá, dokud se nerozhodneš."],
    "duel.odds": ["Published odds for the hidden truth in each round: B really better {a}%, no real effect {b}%, B really worse {c}%. When B is better, the size of the lift comes from the scenario.", "Zveřejněné šance na skrytou pravdu v každém kole: B opravdu lepší {a} %, žádný skutečný efekt {b} %, B opravdu horší {c} %. Když je B lepší, velikost zlepšení určuje scénář."],
    "duel.scenario": ["Scenario", "Scénář"],
    "duel.baseline": ["Baseline conversion {p}", "Základní konverze {p}"],
    "duel.traffic": ["typical traffic: about {n} visitors per arm", "typický traffic: asi {n} návštěvníků na variantu"],
    "duel.visitors": ["Visitors per arm", "Návštěvníků na variantu"],
    "duel.days": ["about {d} days of traffic at this scenario's pace", "asi {d} dní provozu v tempu tohoto scénáře"],
    "duel.planning": ["Planning tip: to detect a {m}% relative lift on a {p} baseline you need about {n} visitors per arm. Smaller lifts need far more.", "Tip pro plánování: k odhalení relativního zlepšení o {m} % při základu {p} potřebuješ asi {n} návštěvníků na variantu. Menší zlepšení potřebují mnohem víc."],
    "duel.run": ["Run the test", "Spustit test"],
    "duel.runAgain": ["Collect another sample", "Nasbírat další vzorek"],
    "duel.runs": ["Samples collected: {k}", "Nasbíraných vzorků: {k}"],
    "duel.running": ["Collecting visitors...", "Sbírám návštěvníky..."],
    "duel.perArm": ["visitors per arm so far", "návštěvníků na variantu zatím"],
    "duel.resultsTitle": ["What the data says", "Co říkají data"],
    "duel.variantA": ["Variant A (control)", "Varianta A (kontrola)"],
    "duel.variantB": ["Variant B (change)", "Varianta B (změna)"],
    "duel.counts": ["{k} of {n} converted", "{k} z {n} konvertovalo"],
    "duel.diff": ["Difference B minus A", "Rozdíl B mínus A"],
    "duel.points": ["pts", "p. b."],
    "duel.rel": ["{r} relative to A", "{r} vůči A"],
    "duel.zTest": ["Two-proportion z test", "Z test dvou podílů"],
    "duel.verdict": ["Verdict at 5%", "Verdikt při 5 %"],
    "duel.sig": ["Significant", "Statisticky významné"],
    "duel.notSig": ["Not significant", "Nevýznamné"],
    "duel.sigB": ["The data favour B.", "Data nahrávají B."],
    "duel.sigA": ["The data favour A.", "Data nahrávají A."],
    "duel.notSigHint": ["Could be noise: the evidence is not strong enough yet.", "Může jít o šum: důkazy zatím nejsou dost silné."],
    "duel.ci": ["95% interval for the difference (Newcombe)", "95% interval pro rozdíl (Newcombe)"],
    "duel.zero": ["no difference", "žádný rozdíl"],
    "duel.ciAria": ["Difference B minus A is {d} points, 95 percent interval from {lo} to {hi}.", "Rozdíl B mínus A je {d} p. b., 95% interval od {lo} do {hi}."],
    "duel.ciHint": ["If the interval crosses zero, the data are compatible with no difference.", "Pokud interval protíná nulu, data jsou slučitelná s žádným rozdílem."],
    "duel.bayes": ["Bayesian view: chance that B is better", "Bayesovský pohled: šance, že B je lepší"],
    "duel.loss": ["Expected loss: shipping A costs about {a} points of conversion if B is better, shipping B about {b} points if A is better.", "Očekávaná ztráta: nasazení A stojí asi {a} p. b. konverze, pokud je lepší B, nasazení B asi {b} p. b., pokud je lepší A."],
    "duel.history": ["Your samples so far", "Tvoje dosavadní vzorky"],
    "duel.historyNote": ["Same truth, different samples: notice how much the results wobble.", "Stejná pravda, jiné vzorky: všimni si, jak moc výsledky kolísají."],
    "duel.colRun": ["Sample", "Vzorek"],
    "duel.colN": ["Visitors", "Návštěvníci"],
    "duel.decide": ["Your decision", "Tvoje rozhodnutí"],
    "duel.decideHint": ["Based on the latest sample. Shipping B is right only if B is truly better; keep testing is right while the evidence is inconclusive.", "Podle posledního vzorku. Nasadit B je správně jen tehdy, když je B skutečně lepší; testovat dál je správně, dokud jsou důkazy neprůkazné."],
    "duel.decideWait": ["Run the test at least once to unlock your decision.", "Spusť test alespoň jednou, odemkne se tím rozhodnutí."],
    "duel.shipA": ["Ship A", "Nasadit A"],
    "duel.shipB": ["Ship B", "Nasadit B"],
    "duel.keep": ["Keep testing", "Testovat dál"],
    "duel.right": ["Right call", "Správné rozhodnutí"],
    "duel.wrong": ["Not this time", "Tentokrát ne"],
    "duel.youChose": ["You chose: {c}", "Zvolil jsi: {c}"],
    "duel.truth": ["The hidden truth", "Skrytá pravda"],
    "duel.truth.better": ["B really was better: {b} against {a} (a {l}% lift).", "B skutečně bylo lepší: {b} oproti {a} (zlepšení o {l} %)."],
    "duel.truth.none": ["B had no real effect: both variants convert at {a}.", "B nemělo skutečný efekt: obě varianty konvertují na {a}."],
    "duel.truth.worse": ["B really was worse: {b} against {a} ({l}% lower).", "B skutečně bylo horší: {b} oproti {a} (o {l} % méně)."],
    "duel.truthOdds": ["Reminder: each round draws the truth with published odds (better {a}%, no effect {b}%, worse {c}%).", "Připomenutí: v každém kole se pravda losuje podle zveřejněných šancí (lepší {a} %, žádný efekt {b} %, horší {c} %)."],
    "duel.needMore": ["To reliably see a lift like this you would need about {n} visitors per arm.", "Aby bylo takové zlepšení spolehlivě vidět, potřeboval bys asi {n} návštěvníků na variantu."],
    "duel.next": ["Next round", "Další kolo"],
    "duel.announce": ["Sample {k} done. A converted {a}, B {b}. {p}. Chance that B is better: {pb} percent.", "Vzorek {k} hotov. A konvertovalo {a}, B {b}. {p}. Šance, že B je lepší: {pb} procent."],
    "duel.ex.better.b": ["B really was better, so shipping it was the right call.", "B skutečně bylo lepší, takže nasadit ho bylo správné rozhodnutí."],
    "duel.ex.better.a": ["You skipped a real win: B was truly {l}% better. More visitors would have made it visible.", "Přišel jsi o skutečnou výhru: B bylo opravdu o {l} % lepší. S více návštěvníky by to bylo vidět."],
    "duel.ex.better.keep.inconclusive": ["B really was better, but this sample could not show it yet. Asking for more data was the careful move.", "B skutečně bylo lepší, ale tento vzorek to zatím nedokázal ukázat. Chtít víc dat bylo rozumné."],
    "duel.ex.better.keep.wasted": ["The evidence already pointed the right way and B really was better. Waiting longer only burns traffic.", "Důkazy už mířily správným směrem a B bylo skutečně lepší. Další čekání jen spaluje traffic."],
    "duel.ex.better.keep.falseAlarm": ["This sample pointed the wrong way even though B was better. Collecting more data before deciding was wise.", "Tento vzorek ukázal opačně, i když B bylo lepší. Nasbírat víc dat před rozhodnutím bylo moudré."],
    "duel.ex.none.b": ["B had no real effect: chance made it look better. Even with p below 0.05 you get fooled about 1 time in 20 when there is nothing to find.", "B nemělo skutečný efekt: náhoda ho nechala vypadat lépe. I při p pod 0,05 tě to splete zhruba v 1 případě z 20, když není co najít."],
    "duel.ex.none.a": ["There was no real difference, so keeping A avoided a pointless change.", "Skutečný rozdíl nebyl, takže ponechání A ušetřilo zbytečnou změnu."],
    "duel.ex.none.keep.inconclusive": ["There is no real difference, and the data rightly did not show one. Waiting or keeping A are both reasonable.", "Skutečný rozdíl neexistuje a data ho právem neukázala. Čekat i ponechat A je rozumné."],
    "duel.ex.none.keep.falseAlarm": ["The sample looked significant, but there was no real effect: a false alarm. Confirming first was wise.", "Vzorek vypadal významně, ale skutečný efekt nebyl: falešný poplach. Nejdřív to potvrdit bylo moudré."],
    "duel.ex.worse.b": ["B was truly worse, so shipping it would have cost you conversions.", "B bylo skutečně horší, takže jeho nasazení by tě stálo konverze."],
    "duel.ex.worse.a": ["B was truly worse, so keeping A protected your conversions.", "B bylo skutečně horší, takže ponechání A ochránilo tvoje konverze."],
    "duel.ex.worse.keep.inconclusive": ["B was worse, but the sample was too small to show it. Waiting was the careful move.", "B bylo horší, ale vzorek byl příliš malý, aby to ukázal. Čekat bylo rozumné."],
    "duel.ex.worse.keep.wasted": ["The data already showed that B is worse. Keep A and move on instead of spending more traffic.", "Data už ukázala, že B je horší. Ponech A a jdi dál, místo abys utrácel další traffic."],
    "duel.ex.worse.keep.falseAlarm": ["The sample looked as if B were better, but it was truly worse: a false alarm. Waiting was wise.", "Vzorek vypadal, jako by B bylo lepší, ale ve skutečnosti bylo horší: falešný poplach. Počkat bylo moudré."],

    "calc.title": ["Sample size calculator", "Kalkulačka velikosti vzorku"],
    "calc.intro": ["How many visitors per arm do you need to reliably detect a lift? 80% power, 5% significance, two-sided.", "Kolik návštěvníků na variantu potřebuješ, abys spolehlivě odhalil zlepšení? Síla 80 %, hladina významnosti 5 %, oboustranně."],
    "calc.baseline": ["Baseline conversion rate (%)", "Základní míra konverze (%)"],
    "calc.lift": ["Relative lift to detect (%)", "Relativní zlepšení k odhalení (%)"],
    "calc.result": ["About {n} visitors per arm.", "Asi {n} návštěvníků na variantu."],
    "calc.invalid": ["Enter a baseline between 0 and 100 and a lift above 0.", "Zadej základ mezi 0 a 100 a zlepšení větší než 0."],

    "peek.title": ["Don't Peek: why checking early lies", "Nenahlížej: proč brzké kontrolování lže"],
    "peek.intro": ["Both groups in these tests are identical (an A/A test), so every winner is a false alarm. A fair test looks once, at the end: about 5% false alarms. Peeking after every batch and stopping at the first p below 0.05 makes false alarms explode.", "Obě skupiny v těchto testech jsou stejné (A/A test), takže každý vítěz je falešný poplach. Férový test se dívá jednou, na konci: asi 5 % falešných poplachů. Nahlížení po každé dávce a zastavení u prvního p pod 0,05 falešné poplachy vyžene nahoru."],
    "peek.setup": ["{t} simulated A/A tests, {n} visitors per arm in each look, a 5% conversion rate and a 5% significance level.", "{t} simulovaných A/A testů, {n} návštěvníků na variantu v každé dávce, 5% konverze a hladina významnosti 5 %."],
    "peek.looks": ["Number of looks", "Počet nahlédnutí"],
    "peek.run": ["Run {n} A/A tests", "Spustit {n} A/A testů"],
    "peek.running": ["Simulating...", "Simuluji..."],
    "peek.resultTitle": ["False alarm rates", "Míra falešných poplachů"],
    "peek.summary": ["Out of {t} tests with NO real difference, peeking declared {a} winners. A fixed horizon declared {b}.", "Z {t} testů BEZ skutečného rozdílu vyhlásilo nahlížení {a} vítězů. Pevný horizont jich vyhlásil {b}."],
    "peek.fixed": ["Fixed horizon (look once)", "Pevný horizont (jedno nahlédnutí)"],
    "peek.peeking": ["Peeking at {n} looks", "Nahlížení při {n} kontrolách"],
    "peek.nominal": ["Nominal 5%", "Nominálních 5 %"],
    "peek.barAria": ["Bar chart: fixed horizon {a} false alarms, peeking at {n} looks {b}, against the nominal 5 percent.", "Sloupcový graf: pevný horizont {a} falešných poplachů, nahlížení při {n} kontrolách {b}, proti nominálním 5 procentům."],
    "peek.barCaption": ["Share of A/A tests declared significant", "Podíl A/A testů vyhlášených za významné"],
    "peek.colMethod": ["Method", "Metoda"],
    "peek.colRate": ["False alarm rate", "Míra falešných poplachů"],
    "peek.barNote": ["Bars grow from zero; the thin line marks the 5% you were promised.", "Sloupce rostou od nuly; tenká čára značí 5 %, které ti byly slíbeny."],
    "peek.curveCaption": ["False alarms pile up with every look", "Falešné poplachy se s každým nahlédnutím hromadí"],
    "peek.curveAria": ["Line chart: share of A/A tests that had already crossed p below 0.05 after each look.", "Čárový graf: podíl A/A testů, které po každém nahlédnutí už překročily p pod 0,05."],
    "peek.xLabel": ["Looks so far", "Dosavadní nahlédnutí"],
    "peek.seriesPeek": ["Peeking: tests already flagged", "Nahlížení: už označené testy"],
    "peek.curveNote": ["Each extra look is another chance for noise to cross the line.", "Každé další nahlédnutí je další šance, aby šum překročil hranici."],
    "peek.lessonTitle": ["What to do instead", "Co dělat místo toho"],
    "peek.l1": ["Decide the sample size in advance (see the calculator in the Duel tab) and look once.", "Velikost vzorku urči předem (viz kalkulačka na kartě Souboj) a podívej se jednou."],
    "peek.l2": ["If you must look early, use a sequential method designed for it, not repeated p values.", "Pokud se musíš dívat dřív, použij sekvenční metodu k tomu určenou, ne opakovaná p."],
    "peek.l3": ["Report the interval, not just the winner, and say how many looks you took.", "Uváděj interval, ne jen vítěze, a řekni, kolikrát ses díval."],
    "peek.announce": ["Peeking gave {a} false alarms, a fixed horizon {b}.", "Nahlížení dalo {a} falešných poplachů, pevný horizont {b}."],

    "bandit.title": ["Bandit Garden: let winners earn the traffic", "Zahrada banditů: nech vítěze, ať si traffic zaslouží"],
    "bandit.intro": ["Four variants (plants) have hidden conversion rates. An even split waters them all equally. Thompson sampling gives more water to the plants that look best while still testing the others. Regret is the conversions you lose compared with always showing the best one.", "Čtyři varianty (rostlinky) mají skryté míry konverze. Rovnoměrné dělení zalévá všechny stejně. Thompsonovo vzorkování zalévá víc ty, které vypadají nejlépe, a přitom ostatní dál zkouší. Regret jsou konverze, o které přijdeš oproti tomu, kdybys vždy ukazoval tu nejlepší."],
    "bandit.rounds": ["Visitors in total", "Návštěvníků celkem"],
    "bandit.speed": ["Speed", "Rychlost"],
    "bandit.slow": ["Slow", "Pomalu"],
    "bandit.normal": ["Normal", "Normálně"],
    "bandit.fast": ["Fast", "Rychle"],
    "bandit.start": ["Start", "Spustit"],
    "bandit.pause": ["Pause", "Pozastavit"],
    "bandit.resume": ["Resume", "Pokračovat"],
    "bandit.newGarden": ["New garden", "Nová zahrada"],
    "bandit.ready": ["Ready. Press Start and the first visitors arrive.", "Připraveno. Stiskni Spustit a dorazí první návštěvníci."],
    "bandit.progress": ["{a} of {b} visitors", "{a} z {b} návštěvníků"],
    "bandit.paused": ["Paused", "Pozastaveno"],
    "bandit.done": ["Done. The best variant is revealed.", "Hotovo. Nejlepší varianta je odhalena."],
    "bandit.thompson": ["Thompson sampling", "Thompsonovo vzorkování"],
    "bandit.thompsonDesc": ["Sends more visitors to variants that look better, and keeps exploring.", "Posílá víc návštěvníků variantám, které vypadají lépe, a dál zkoumá."],
    "bandit.even": ["Even split", "Rovnoměrné dělení"],
    "bandit.evenDesc": ["Gives every variant the same share of visitors, whatever the results.", "Dává každé variantě stejný podíl návštěvníků bez ohledu na výsledky."],
    "bandit.visitors": ["visitors", "návštěvníků"],
    "bandit.best": ["Best variant", "Nejlepší varianta"],
    "bandit.true": ["true {p}", "skutečná {p}"],
    "bandit.regretTitle": ["Regret: conversions lost along the way", "Regret: konverze ztracené cestou"],
    "bandit.chartCaption": ["Cumulative regret: expected conversions lost versus always showing the best variant", "Kumulativní regret: očekávané ztracené konverze oproti tomu, kdybys vždy ukazoval nejlepší variantu"],
    "bandit.chartAria": ["Line chart of cumulative regret for Thompson sampling and an even split over the visitors.", "Čárový graf kumulativního regretu pro Thompsonovo vzorkování a rovnoměrné dělení v průběhu návštěvníků."],
    "bandit.xLabel": ["Visitors", "Návštěvníci"],
    "bandit.regretNote": ["Lower is better. The Thompson line flattens once it has found the winner; the even split keeps losing at a constant rate.", "Nižší je lepší. Čára Thompsona se vyrovná, jakmile najde vítěze; rovnoměrné dělení ztrácí pořád stejným tempem."],
    "bandit.resultTitle": ["Result", "Výsledek"],
    "bandit.summary": ["After {n} visitors the even split lost about {a} conversions to the best variant, Thompson sampling about {b}. That is {s} conversions saved.", "Po {n} návštěvnících přišlo rovnoměrné dělení asi o {a} konverzí oproti nejlepší variantě, Thompsonovo vzorkování asi o {b}. Ušetřeno: {s} konverzí."],
    "bandit.share": ["Share of visitors sent to the best variant ({k}): {x} with Thompson sampling, {y} with the even split.", "Podíl návštěvníků poslaných na nejlepší variantu ({k}): {x} u Thompsonova vzorkování, {y} u rovnoměrného dělení."],
    "bandit.caveat": ["One run is one story. Bandits shine when results during the test matter; a classic fixed test is better when you need a clean estimate of the effect.", "Jeden běh je jeden příběh. Bandité září, když záleží na výsledcích už během testu; klasický pevný test je lepší, když potřebuješ čistý odhad efektu."],
    "bandit.announce": ["Even split lost {a} conversions, Thompson sampling {b}.", "Rovnoměrné dělení ztratilo {a} konverzí, Thompsonovo vzorkování {b}."]
  });

  add("vault", {
    title: ["Vault", "Trezor"],
    lead: ["Collect evidence cards, read the studies behind the tactics and test your instincts on myths. Chest odds are published and nothing costs real money.", "Sbírej karty s důkazy, čti studie za jednotlivými taktikami a testuj svůj instinkt na mýtech. Šance v truhlách jsou zveřejněné a nic nestojí skutečné peníze."],
    tabs: ["Vault sections", "Sekce Trezoru"],
    "tab.cards": ["Cards", "Karty"],
    "tab.studies": ["Studies", "Studie"],
    "tab.myths": ["Myth or Fact", "Mýtus, nebo fakt"],
    chestTitle: ["Chests", "Truhly"],
    "chestsReady.one": ["{n} chest ready", "{n} truhla připravena"],
    "chestsReady.few": ["{n} chests ready", "{n} truhly připraveny"],
    "chestsReady.other": ["{n} chests ready", "{n} truhel připraveno"],
    chestHow: ["Win a boss or finish all three daily quests to earn a chest.", "Poraz bosse nebo splň všechny tři denní úkoly a získáš truhlu."],
    openChest: ["Open a chest", "Otevřít truhlu"],
    noChest: ["No chest to open right now", "Teď není žádná truhla k otevření"],
    opening: ["Opening the chest...", "Otevírám truhlu..."],
    pityLine: ["Pity timer: {n} of {max} chests without a rare or better card.", "Pojistka: {n} z {max} truhel bez vzácné nebo lepší karty."],
    pityGuaranteed: ["Pity timer reached: your next chest is guaranteed rare or better.", "Pojistka je naplněná: tvoje další truhla bude zaručeně vzácná nebo lepší."],
    pityAria: ["Pity timer: {n} of {max} chests without a rare or better card.", "Pojistka: {n} z {max} truhel bez vzácné nebo lepší karty."],
    pityUsed: ["The pity timer made this one rare or better. The counter starts over.", "Pojistka zařídila vzácnou nebo lepší kartu. Počítadlo začíná znovu."],
    pityNow: ["Pity timer: {n} of {max}.", "Pojistka: {n} z {max}."],
    pityReset: ["A rare or better card resets the pity timer to 0.", "Vzácná nebo lepší karta vynuluje pojistku."],
    dropTitle: ["Drop rates (published)", "Šance na výhru (zveřejněné)"],
    dropIntro: ["These are the real odds used by every chest. They are the same for everyone, and your history never changes them except through the pity timer below.", "Tohle jsou skutečné šance, které používá každá truhla. Jsou pro všechny stejné a tvoje historie je nemění, kromě pojistky níže."],
    colRarity: ["Rarity", "Vzácnost"],
    colRate: ["Drop rate", "Šance"],
    colCards: ["Cards here", "Karet tady"],
    colOwned: ["You own", "Vlastníš"],
    dropFallback: ["This edition has no cards of these rarities yet: {r}. Those drops become the nearest rarity that has cards.", "Tato edice zatím nemá žádné karty těchto vzácností: {r}. Takové výhry připadnou nejbližší vzácnosti, která karty má."],
    pityRule: ["Pity timer: after {n} chests in a row without a rare or better card, the next chest is guaranteed to be rare or better.", "Pojistka: po {n} truhlách v řadě bez vzácné nebo lepší karty je další truhla zaručeně vzácná nebo lepší."],
    noMoney: ["No real money is involved anywhere in this game, and a duplicate card turns into 5 XP.", "V celé hře nejde o skutečné peníze a duplicitní karta se promění v 5 XP."],
    "rarity.common": ["Common", "Běžná"],
    "rarity.rare": ["Rare", "Vzácná"],
    "rarity.epic": ["Epic", "Epická"],
    "rarity.legendary": ["Legendary", "Legendární"],
    "kind.pattern": ["Pattern", "Vzorec"],
    "kind.tip": ["Tip", "Tip"],
    "kind.study": ["Study", "Studie"],
    "kind.tactic": ["Tactic", "Taktika"],
    collection: ["Collection", "Sbírka"],
    collectionSub: ["Locked cards show only their rarity until you win them from a chest.", "Zamčené karty ukazují jen vzácnost, dokud je nezískáš z truhly."],
    locked: ["Locked", "Zamčeno"],
    lockedAria: ["Locked card, rarity {r}", "Zamčená karta, vzácnost {r}"],
    demoCard: ["This card describes a pattern in the simulated demo corpus. It is not a finding about real campaigns.", "Tahle karta popisuje vzorec v simulovaném demo korpusu. Není to zjištění o skutečných kampaních."],
    "noCards.title": ["No cards in this edition", "V této edici nejsou žádné karty"],
    "noCards.text": ["The data bundle has no loot cards yet.", "Datový balíček zatím neobsahuje žádné karty."],
    newCard: ["New card for your collection", "Nová karta do sbírky"],
    dupe: ["Duplicate: +{n} XP", "Duplikát: +{n} XP"],
    dupeChip: ["Duplicate +{n} XP", "Duplikát +{n} XP"],
    openAnother: ["Open another ({n} left)", "Otevřít další (zbývá {n})"],
    tactics: ["Evidence tactics", "Taktiky s důkazy"],
    tacticsSub: ["Each tactic shows how strong the evidence is, with caveats. Even strong evidence has limits.", "U každé taktiky vidíš, jak silné jsou důkazy, včetně výhrad. I silné důkazy mají meze."],
    "noTactics.title": ["No evidence tactics yet", "Zatím žádné taktiky s důkazy"],
    "noTactics.text": ["The evidence ledger is empty in this demo bundle. Tactics, studies and their grades appear here once the research ledger is exported into the bundle.", "Evidenční registr je v tomto demo balíčku prázdný. Taktiky, studie a jejich hodnocení se tu objeví, jakmile se výzkumný registr exportuje do balíčku."],
    tacticMore: ["Caveats and ethics", "Výhrady a etika"],
    caveats: ["Caveats", "Výhrady"],
    ethics: ["Ethics", "Etika"],
    "ev.strong": ["Strong evidence", "Silné důkazy"],
    "ev.moderate": ["Moderate evidence", "Střední důkazy"],
    "ev.limited": ["Limited evidence", "Omezené důkazy"],
    "ev.contested": ["Contested", "Sporné"],
    "ev.none": ["No evidence yet", "Zatím bez důkazů"],
    grade: ["Grade {g}", "Hodnocení {g}"],
    "nStudies.one": ["{n} study", "{n} studie"],
    "nStudies.few": ["{n} studies", "{n} studie"],
    "nStudies.other": ["{n} studies", "{n} studií"],
    honestyTitle: ["How to read this ledger", "Jak číst tento registr"],
    unverifiedNote: ["Seed entries are unverified until `kingctl evidence verify` was run. Verification checks that a record exists in Crossref; it does not say the study is right.", "Úvodní záznamy jsou neověřené, dokud nebyl spuštěn `kingctl evidence verify`. Ověření kontroluje, že záznam existuje v Crossrefu; neříká, že studie má pravdu."],
    gradeNote: ["Grades A to D come from the study design first (a meta-analysis outranks a single observational study), then small adjustments for citations and peer review.", "Hodnocení A až D vychází nejdřív z typu studie (metaanalýza převyšuje jednu observační studii), potom z drobných úprav za citace a recenzní řízení."],
    filter: ["Filter studies", "Filtrovat studie"],
    verified: ["Verified", "Ověřeno"],
    unverified: ["Unverified", "Neověřeno"],
    studyCount: ["{v} of {n} verified", "{v} z {n} ověřeno"],
    noMatch: ["No studies match this filter.", "Žádné studie neodpovídají filtru."],
    "noStudies.title": ["No studies yet", "Zatím žádné studie"],
    "noStudies.text": ["The ledger has no studies in this bundle. Seed entries appear after the research ledger is set up and stay marked unverified until checked.", "Registr v tomto balíčku neobsahuje žádné studie. Úvodní záznamy se objeví po zprovoznění výzkumného registru a zůstanou označené jako neověřené, dokud nebudou zkontrolovány."],
    unknownAuthors: ["Unknown authors", "Neznámí autoři"],
    etAl: ["et al.", "a kol."],
    cited: ["Cited {n} times", "Citováno {n}krát"],
    peer: ["Peer reviewed", "Recenzováno"],
    notPeer: ["Not peer reviewed", "Nerecenzováno"],
    retracted: ["Retracted", "Stažená studie"],
    usedBy: ["Supports:", "Podporuje:"],
    copyDoi: ["Copy DOI", "Kopírovat DOI"],
    gradeHelp: ["Evidence grade from A (strongest) to D", "Hodnocení důkazů od A (nejsilnější) po D"],
    "design.meta-analysis": ["Meta-analysis", "Metaanalýza"],
    "design.systematic-review": ["Systematic review", "Systematický přehled"],
    "design.rct": ["Randomised trial", "Randomizovaná studie"],
    "design.field-experiment": ["Field experiment", "Terénní experiment"],
    "design.lab-experiment": ["Lab experiment", "Laboratorní experiment"],
    "design.observational": ["Observational", "Observační studie"],
    "design.survey": ["Survey", "Dotazníkové šetření"],
    "design.theory": ["Theory", "Teorie"],
    "design.qualitative": ["Qualitative", "Kvalitativní studie"],
    "design.book": ["Book", "Kniha"],
    "design.preprint": ["Preprint", "Preprint"],
    "design.guideline": ["Guideline", "Doporučení"],
    "design.unknown": ["Design unknown", "Typ neznámý"],
    "myth.prompt": ["Myth or fact?", "Mýtus, nebo fakt?"],
    "myth.myth": ["Myth", "Mýtus"],
    "myth.fact": ["Fact", "Fakt"],
    "myth.isMyth": ["a myth", "mýtus"],
    "myth.isFact": ["a fact", "fakt"],
    "myth.right": ["Right", "Správně"],
    "myth.wrong": ["Not quite", "Ne tak docela"],
    "myth.answerWas": ["It is {a}.", "Je to {a}."],
    "myth.why": ["Why", "Proč"],
    "myth.ref": ["Reference:", "Zdroj:"],
    "myth.caveat": ["Check the original source before you rely on it. References here are not verified against Crossref unless the Studies tab says so.", "Než se na to spolehneš, zkontroluj původní zdroj. Zdroje tu nejsou ověřené proti Crossrefu, pokud to neříká karta Studie."],
    "myth.next": ["Next card", "Další karta"],
    "myth.progress": ["Seen {a} of {b}", "Zobrazeno {a} z {b}"],
    "myth.run": ["{n} right in a row", "{n} správně v řadě"],
    "myth.xpHint": ["+{r} XP when right, +{w} when wrong", "+{r} XP za správně, +{w} za špatně"],
    "myth.keys": ["Swipe the card left for Myth and right for Fact, or use the buttons. Keyboard: left or M for Myth, right or F for Fact, Enter for the next card.", "Posuň kartu doleva pro Mýtus a doprava pro Fakt, nebo použij tlačítka. Klávesnice: šipka doleva nebo M pro Mýtus, doprava nebo F pro Fakt, Enter pro další kartu."],
    "noMyths.title": ["No myth cards yet", "Zatím žádné karty mýtů"],
    "noMyths.text": ["The data bundle has no Myth or Fact cards.", "Datový balíček neobsahuje žádné karty Mýtus, nebo fakt."]
  });

  // @@SECTIONS-END@@ (new sections are inserted above this line)

  // ---- engine -----------------------------------------------------------------------------
  var dictionaries = { en: {}, cs: {} };
  Object.keys(T).forEach(function (k) { dictionaries.en[k] = T[k][0]; dictionaries.cs[k] = T[k][1]; });

  var current = "en";

  function setLang(l) { current = LANGS.indexOf(l) >= 0 ? l : "en"; return current; }
  function getLang() { return current; }
  /** Czech UI when the browser language starts with cs, otherwise English. */
  function detectLang(navigatorLanguage) {
    return /^cs\b/i.test(String(navigatorLanguage || "")) ? "cs" : "en";
  }

  function interpolate(s, params) {
    if (!params) return s;
    return s.replace(/\{(\w+)\}/g, function (m, k) { return params[k] === undefined || params[k] === null ? m : String(params[k]); });
  }

  /** Translate a key. Unknown keys return the key itself so a gap is visible, never a crash. */
  function t(key, params, lang) {
    var l = lang || current;
    var s = dictionaries[l] && dictionaries[l][key];
    if (s === undefined) s = dictionaries.en[key];
    if (s === undefined) return key;
    return interpolate(s, params);
  }

  /** Plural aware lookup: key.one / key.few / key.other (Czech has a "few" form for 2 to 4). */
  function tp(key, n, params, lang) {
    var l = lang || current;
    var form = n === 1 ? "one" : (l === "cs" && n >= 2 && n <= 4) ? "few" : "other";
    var p = Object.assign({ n: n }, params || {});
    var full = key + "." + form;
    return has(full) ? t(full, p, l) : t(key + ".other", p, l);
  }

  function has(key) { return Object.prototype.hasOwnProperty.call(dictionaries.en, key); }

  /** Field of a bundle object in the current language: pick(card, "title") reads title_cs or title_en. */
  function pick(obj, field, lang) {
    if (!obj) return "";
    var l = lang || current;
    var v = obj[field + "_" + l];
    if (v === undefined || v === null || v === "") v = obj[field + "_en"];
    if (v === undefined || v === null || v === "") v = obj[field];
    return v === undefined || v === null ? "" : v;
  }

  /** Number formatting in the UI language (decimal comma for Czech). */
  function fmt(n, digits, lang) {
    var l = lang || current;
    if (typeof n !== "number" || !isFinite(n)) return "-";
    try {
      return new Intl.NumberFormat(l === "cs" ? "cs-CZ" : "en-US", { minimumFractionDigits: digits || 0, maximumFractionDigits: digits || 0 }).format(n);
    } catch (e) { return n.toFixed(digits || 0); }
  }

  function keys(lang) { return Object.keys(dictionaries[lang]); }

  return {
    LANGS: LANGS, dictionaries: dictionaries, setLang: setLang, getLang: getLang, detectLang: detectLang,
    t: t, tp: tp, has: has, pick: pick, fmt: fmt, keys: keys, interpolate: interpolate
  };
});
