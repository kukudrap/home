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
