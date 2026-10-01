/* Game rules for Dopamine King: levels, XP, streaks with freezes, daily quests, boss resolution,
 * loot chests with published odds and a pity timer, achievements and the digital wellbeing helpers.
 *
 * Everything here is a pure function. Actions take a profile and return a NEW profile plus details and a
 * list of events for the UI; the clock (ctx.now) and the random source (ctx.rng) are injected, so the
 * rules can be unit tested (web/tests/game.test.js).
 *
 * Ethics by design: variable rewards (chests) use published drop rates and a pity timer, nothing costs
 * real money, a missed day never produces guilt copy (streak freezes instead), and wrong answers still
 * earn a little XP.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(function (n) { return require("./" + n + ".js"); });
  else { root.DK = root.DK || {}; root.DK.game = factory(function (n) { return root.DK[n]; }); }
})(typeof self !== "undefined" ? self : this, function (dep) {
  "use strict";

  var labstats = dep("labstats");

  // -- constants ----------------------------------------------------------------------------
  var PROFILE_KEY = "dk.profile.v1";
  var PROFILE_VERSION = 1;

  var XP = {
    arenaBase: 10, arenaMedium: 5, arenaHard: 10, arenaUpset: 10, arenaWrong: 2,
    confidenceBonus: 3, confidenceThreshold: 80, comboStep: 5, comboMax: 3,
    bossRepeatShare: 0.2, labRight: 25, labWrong: 5, mythRight: 8, mythWrong: 2,
    quest: 30, dust: 5
  };
  var BOSS_MAX_RISK = 0.35;
  var HONEST_RISK = 0.10;
  var ORACLE_MIN_ANSWERS = 10;
  var BRIER_BASELINE = 0.25;
  var MAX_FREEZES = 2;
  var FREEZE_EVERY = 7;
  var DEFAULT_SESSION_MINUTES = 20;
  var RARITIES = ["common", "rare", "epic", "legendary"];
  var LAB_TRUTH_ODDS = { better: 0.5, none: 0.3, worse: 0.2 };

  var LEVELS = [
    { en: "Rookie", cs: "Nováček" },
    { en: "Hook Apprentice", cs: "Učeň hooků" },
    { en: "Curiosity Hunter", cs: "Lovec zvědavosti" },
    { en: "Signal Reader", cs: "Čtenář signálů" },
    { en: "Pattern Seeker", cs: "Hledač vzorců" },
    { en: "Growth Strategist", cs: "Stratég růstu" },
    { en: "Dopamine Architect", cs: "Architekt dopaminu" },
    { en: "Oracle", cs: "Orákulum" },
    { en: "Grandmaster", cs: "Velmistr" },
    { en: "King", cs: "Král" }
  ];

  // -- helpers ------------------------------------------------------------------------------
  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function clamp(x, lo, hi) { return Math.min(hi, Math.max(lo, x)); }
  function isObj(x) { return x !== null && typeof x === "object" && !Array.isArray(x); }
  function num(x, d) { return typeof x === "number" && isFinite(x) ? x : d; }
  function pad2(n) { return (n < 10 ? "0" : "") + n; }

  function nowDate(ctx) {
    var v = ctx && typeof ctx.now === "function" ? ctx.now() : Date.now();
    return v instanceof Date ? v : new Date(v);
  }
  /** Local calendar date as YYYY-MM-DD. */
  function localDate(d) { return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate()); }
  function dayNumber(s) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
    if (!m) return NaN;
    return Math.round(Date.UTC(+m[1], +m[2] - 1, +m[3]) / 86400000);
  }
  function daysBetween(a, b) { return dayNumber(b) - dayNumber(a); }

  /** Random source for chests and duels: crypto when available, else Math.random. */
  function systemRng() {
    var c = typeof globalThis !== "undefined" ? globalThis.crypto : null;
    if (c && typeof c.getRandomValues === "function") {
      var buf = new Uint32Array(1);
      return function () { c.getRandomValues(buf); return buf[0] / 4294967296; };
    }
    return Math.random;
  }

  // -- levels -------------------------------------------------------------------------------
  /** Cumulative XP needed to reach level n (level 1 starts at 0). */
  function xpForLevel(n) { return n <= 1 ? 0 : Math.round(100 * Math.pow(n - 1, 1.5)); }
  function levelForXp(xp) {
    var n = 1;
    while (xpForLevel(n + 1) <= xp) n += 1;
    return n;
  }
  function levelTitle(level, lang) {
    var entry = LEVELS[Math.min(Math.max(level, 1), LEVELS.length) - 1];
    return entry[lang] || entry.en;
  }
  function levelProgress(xp) {
    var level = levelForXp(xp);
    var base = xpForLevel(level), next = xpForLevel(level + 1);
    return { level: level, base: base, next: next, into: xp - base, span: next - base, pct: (xp - base) / (next - base) };
  }

  // -- profile ------------------------------------------------------------------------------
  function defaultProfile(opts) {
    opts = opts || {};
    return {
      version: PROFILE_VERSION, name: "", created: opts.today || null,
      xp: 0, level: 1, streak: 0, bestStreak: 0, lastPlayDate: null, freezeTokens: 0, pity: 0,
      chestsReady: 1, // a welcome chest, so the first visit can show how chests and odds work
      deck: [],
      stats: {
        arenaPlayed: 0, arenaCorrect: 0, upsetsCaught: 0, bossWins: 0, labRuns: 0, mythsCorrect: 0,
        mythsPlayed: 0, chests: 0, labPlayed: 0, labCorrect: 0, honestWins: 0, bestCombo: 0
      },
      brier: { sum: 0, n: 0 },
      achievements: [],
      bossWinsByDay: {},
      bossesBeaten: [],
      winLangs: [],
      combo: 0,
      arenaSeen: [], mythsSeen: [],
      peekDone: false, banditDone: false,
      quests: { date: null, ids: [], progress: {}, done: {}, bonusGranted: false },
      playTime: { date: null, seconds: 0 },
      settings: {
        lang: opts.lang === "cs" ? "cs" : "en", theme: "auto", sound: false, reducedMotion: false,
        sessionMinutes: DEFAULT_SESSION_MINUTES
      }
    };
  }

  function strList(x, max) {
    if (!Array.isArray(x)) return [];
    var out = [];
    x.forEach(function (v) { if (typeof v === "string" && v && out.indexOf(v) < 0) out.push(v); });
    return max ? out.slice(-max) : out;
  }

  /** Validate and repair a stored or imported profile: unknown keys are dropped, numbers clamped. */
  function normalizeProfile(raw, opts) {
    var d = defaultProfile(opts);
    if (!isObj(raw)) return d;
    var p = d;
    p.name = typeof raw.name === "string" ? raw.name.slice(0, 40) : "";
    p.created = typeof raw.created === "string" ? raw.created : d.created;
    p.xp = Math.max(0, Math.floor(num(raw.xp, 0)));
    p.level = levelForXp(p.xp);
    p.streak = Math.max(0, Math.floor(num(raw.streak, 0)));
    p.bestStreak = Math.max(p.streak, Math.floor(num(raw.bestStreak, 0)));
    p.lastPlayDate = isFinite(dayNumber(raw.lastPlayDate)) ? raw.lastPlayDate : null;
    p.freezeTokens = clamp(Math.floor(num(raw.freezeTokens, 0)), 0, MAX_FREEZES);
    p.pity = Math.max(0, Math.floor(num(raw.pity, 0)));
    p.chestsReady = Math.max(0, Math.floor(num(raw.chestsReady, d.chestsReady)));
    p.deck = strList(raw.deck);
    if (isObj(raw.stats)) Object.keys(d.stats).forEach(function (k) { p.stats[k] = Math.max(0, Math.floor(num(raw.stats[k], 0))); });
    if (isObj(raw.brier)) p.brier = { sum: Math.max(0, num(raw.brier.sum, 0)), n: Math.max(0, Math.floor(num(raw.brier.n, 0))) };
    p.achievements = strList(raw.achievements);
    if (isObj(raw.bossWinsByDay)) {
      Object.keys(raw.bossWinsByDay).forEach(function (day) {
        if (!isFinite(dayNumber(day)) || !isObj(raw.bossWinsByDay[day])) return;
        var counts = {};
        Object.keys(raw.bossWinsByDay[day]).forEach(function (id) { counts[id] = Math.max(0, Math.floor(num(raw.bossWinsByDay[day][id], 0))); });
        p.bossWinsByDay[day] = counts;
      });
    }
    p.bossesBeaten = strList(raw.bossesBeaten);
    p.winLangs = strList(raw.winLangs).filter(function (l) { return l === "en" || l === "cs"; });
    p.combo = Math.max(0, Math.floor(num(raw.combo, 0)));
    p.arenaSeen = strList(raw.arenaSeen, 400);
    p.mythsSeen = strList(raw.mythsSeen, 100);
    p.peekDone = raw.peekDone === true;
    p.banditDone = raw.banditDone === true;
    if (isObj(raw.quests)) {
      var q = raw.quests;
      p.quests = {
        date: isFinite(dayNumber(q.date)) ? q.date : null, ids: strList(q.ids, 3),
        progress: {}, done: {}, bonusGranted: q.bonusGranted === true
      };
      if (isObj(q.progress)) Object.keys(q.progress).forEach(function (k) { p.quests.progress[k] = Math.max(0, Math.floor(num(q.progress[k], 0))); });
      if (isObj(q.done)) Object.keys(q.done).forEach(function (k) { if (q.done[k] === true) p.quests.done[k] = true; });
    }
    if (isObj(raw.playTime)) {
      p.playTime = { date: isFinite(dayNumber(raw.playTime.date)) ? raw.playTime.date : null, seconds: Math.max(0, num(raw.playTime.seconds, 0)) };
    }
    if (isObj(raw.settings)) {
      var s = raw.settings;
      p.settings.lang = s.lang === "cs" || s.lang === "en" ? s.lang : d.settings.lang;
      p.settings.theme = s.theme === "dark" || s.theme === "light" ? s.theme : "auto";
      p.settings.sound = s.sound === true;
      p.settings.reducedMotion = s.reducedMotion === true;
      p.settings.sessionMinutes = clamp(Math.floor(num(s.sessionMinutes, DEFAULT_SESSION_MINUTES)), 0, 240);
    }
    return p;
  }

  // -- oracle (calibration) ------------------------------------------------------------------
  function brierScore(brier) { return brier && brier.n > 0 ? brier.sum / brier.n : null; }
  /** Oracle rating 0..100 (coin-flip forecasting is 0), shown after at least 10 answers with confidence. */
  function oracleRating(brier) {
    if (!brier || brier.n < ORACLE_MIN_ANSWERS) return null;
    return clamp(100 * (1 - brierScore(brier) / BRIER_BASELINE), 0, 100);
  }

  // -- streaks ------------------------------------------------------------------------------
  /**
   * Touching a day with activity. Same day: no change. Yesterday: +1. A longer gap spends one freeze per
   * missed day when enough freezes are held, otherwise the streak restarts at 1. A freeze is earned each
   * time the streak reaches a multiple of 7 (at most 2 held).
   */
  function advanceStreak(state, today) {
    var s = { streak: state.streak || 0, bestStreak: state.bestStreak || 0, lastPlayDate: state.lastPlayDate || null, freezeTokens: state.freezeTokens || 0 };
    var info = { changed: false, freezeUsed: 0, freezeEarned: false, restarted: false, incremented: false };
    if (!s.lastPlayDate) {
      s.streak = 1; info.incremented = true;
    } else {
      var diff = daysBetween(s.lastPlayDate, today);
      if (!(diff >= 1)) return { state: s, info: info };
      if (diff === 1) { s.streak += 1; info.incremented = true; }
      else {
        var missed = diff - 1;
        if (s.freezeTokens >= missed) { s.freezeTokens -= missed; s.streak += 1; info.freezeUsed = missed; info.incremented = true; }
        else { s.streak = 1; info.restarted = true; }
      }
    }
    s.lastPlayDate = today;
    info.changed = true;
    if (info.incremented && s.streak % FREEZE_EVERY === 0 && s.freezeTokens < MAX_FREEZES) { s.freezeTokens += 1; info.freezeEarned = true; }
    s.bestStreak = Math.max(s.bestStreak, s.streak);
    return { state: s, info: info };
  }

  // -- daily quests -------------------------------------------------------------------------
  var QUEST_POOL = [
    { id: "arena_wins", event: "arena_win", target: 5, route: "arena" },
    { id: "hard_duel", event: "hard_win", target: 1, route: "arena", params: { difficulty: "hard" } },
    { id: "upset_call", event: "upset", target: 1, route: "arena" },
    { id: "boss_win", event: "boss_win", target: 1, route: "boss" },
    { id: "lab_run", event: "lab_run", target: 1, route: "lab" },
    { id: "myths_5", event: "myth", target: 5, route: "vault", params: { tab: "myths" } },
    { id: "vault_open", event: "vault_open", target: 1, route: "vault" },
    { id: "clean_win", event: "clean_win", target: 1, route: "boss" }
  ];

  function questDef(id) {
    for (var i = 0; i < QUEST_POOL.length; i++) if (QUEST_POOL[i].id === id) return QUEST_POOL[i];
    return null;
  }

  /** Three distinct quest ids for a date, chosen by an RNG seeded with the date string. */
  function questIdsForDate(dateStr, count) {
    var rng = labstats.mulberry32(labstats.hashSeed("dk-quests:" + dateStr));
    var ids = QUEST_POOL.map(function (q) { return q.id; });
    for (var i = ids.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var tmp = ids[i]; ids[i] = ids[j]; ids[j] = tmp;
    }
    return ids.slice(0, count || 3);
  }

  /** Re-roll the quests when the day changed (mutates the given profile copy). */
  function ensureQuests(p, today) {
    if (p.quests.date !== today) {
      p.quests = { date: today, ids: questIdsForDate(today, 3), progress: {}, done: {}, bonusGranted: false };
    }
  }

  function questView(profile, today) {
    var q = profile.quests;
    var ids = q.date === today ? q.ids : questIdsForDate(today, 3);
    var fresh = q.date === today;
    return ids.map(function (id) {
      var def = questDef(id);
      var progress = fresh ? Math.min(q.progress[id] || 0, def.target) : 0;
      return { id: id, event: def.event, target: def.target, progress: progress, done: fresh && q.done[id] === true, xp: XP.quest, route: def.route, params: def.params || null };
    });
  }

  function bump(p, event, amount, events) {
    amount = amount === undefined ? 1 : amount;
    var q = p.quests;
    q.ids.forEach(function (id) {
      var def = questDef(id);
      if (!def || def.event !== event || q.done[id]) return;
      q.progress[id] = Math.min(def.target, (q.progress[id] || 0) + amount);
      if (q.progress[id] >= def.target) {
        q.done[id] = true;
        award(p, XP.quest, events);
        events.push({ type: "quest", id: id, xp: XP.quest });
      }
    });
    if (!q.bonusGranted && q.ids.length === 3 && q.ids.every(function (id) { return q.done[id]; })) {
      q.bonusGranted = true;
      p.chestsReady += 1;
      events.push({ type: "bonusChest" });
    }
  }

  // -- shared action plumbing ----------------------------------------------------------------
  function award(p, amount, events) {
    if (!amount) return;
    var before = p.level;
    p.xp += amount;
    p.level = levelForXp(p.xp);
    if (p.level > before) events.push({ type: "levelUp", from: before, to: p.level });
  }

  function touchDay(p, today, events) {
    var res = advanceStreak(p, today);
    if (res.info.changed) {
      p.streak = res.state.streak; p.bestStreak = res.state.bestStreak;
      p.lastPlayDate = res.state.lastPlayDate; p.freezeTokens = res.state.freezeTokens;
      if (res.info.freezeUsed) events.push({ type: "freezeUsed", n: res.info.freezeUsed });
      if (res.info.freezeEarned) events.push({ type: "freezeEarned" });
    }
  }

  function begin(profile, ctx) {
    var next = clone(profile);
    var events = [];
    var today = localDate(nowDate(ctx));
    ensureQuests(next, today);
    touchDay(next, today, events);
    if (!next.created) next.created = today;
    return { next: next, events: events, today: today };
  }

  function pruneDays(map, today) {
    var t = dayNumber(today);
    Object.keys(map).forEach(function (day) { if (t - dayNumber(day) > 30) delete map[day]; });
  }

  function finish(p, events) {
    ACHIEVEMENTS.forEach(function (a) {
      if (p.achievements.indexOf(a.id) < 0 && a.test(p)) { p.achievements.push(a.id); events.push({ type: "achievement", id: a.id }); }
    });
    return p;
  }

  /**
   * Start of day bookkeeping: new daily quests when the date changed. Opening the game is not activity, so
   * the streak is not touched here (only real play touches the day).
   */
  function rollover(profile, ctx) {
    var next = clone(profile);
    var today = localDate(nowDate(ctx));
    ensureQuests(next, today);
    return { profile: next, events: [], today: today };
  }

  /**
   * The streak as it should be displayed today: still alive when the last play was today or yesterday, or
   * when enough freezes cover the missed days; otherwise it shows 0 and a new streak starts with the next play.
   */
  function streakStatus(profile, today) {
    var last = profile.lastPlayDate;
    var base = { streak: 0, alive: false, playedToday: false, freezesNeeded: 0 };
    if (!last || !(profile.streak > 0)) return base;
    var diff = daysBetween(last, today);
    if (!(diff >= 1)) return { streak: profile.streak, alive: true, playedToday: diff === 0, freezesNeeded: 0 };
    if (diff === 1) return { streak: profile.streak, alive: true, playedToday: false, freezesNeeded: 0 };
    if (profile.freezeTokens >= diff - 1) return { streak: profile.streak, alive: true, playedToday: false, freezesNeeded: diff - 1 };
    return base;
  }

  // -- achievements ---------------------------------------------------------------------------
  var ACHIEVEMENTS = [
    { id: "first_blood", icon: "swords", name: { en: "First Blood", cs: "První krev" },
      desc: { en: "Call your first duel correctly in the Arena.", cs: "Poprvé správně rozhodni souboj v Aréně." },
      test: function (p) { return p.stats.arenaCorrect >= 1; } },
    { id: "calibrated", icon: "target", name: { en: "Calibrated", cs: "Kalibrovaný" },
      desc: { en: "Reach an Oracle rating of 70 or more after at least 20 answers with confidence.", cs: "Dosáhni hodnocení Orákula 70 a více po alespoň 20 odpovědích s jistotou." },
      test: function (p) { return p.brier.n >= 20 && oracleRating(p.brier) >= 70; } },
    { id: "upset_hunter", icon: "bolt", name: { en: "Upset Hunter", cs: "Lovec překvapení" },
      desc: { en: "Call 5 upsets, duels where the model favoured the loser.", cs: "Správně tipni 5 překvapivých duelů, ve kterých model fandil poraženému." },
      test: function (p) { return p.stats.upsetsCaught >= 5; } },
    { id: "honest_hook", icon: "shield", name: { en: "Honest Hook", cs: "Poctivý hook" },
      desc: { en: "Beat a boss with a clickbait risk below 10 percent.", cs: "Poraz bosse s rizikem clickbaitu pod 10 procent." },
      test: function (p) { return p.stats.honestWins >= 1; } },
    { id: "boss_slayer", icon: "crown", name: { en: "Boss Slayer", cs: "Zabiják bossů" },
      desc: { en: "Beat 3 different bosses.", cs: "Poraz 3 různé bossy." },
      test: function (p) { return p.bossesBeaten.length >= 3; } },
    { id: "scientist", icon: "flask", name: { en: "Scientist", cs: "Výzkumník" },
      desc: { en: "Collect 10 vault cards.", cs: "Sesbírej 10 karet do trezoru." },
      test: function (p) { return p.deck.length >= 10; } },
    { id: "streak_7", icon: "flame", name: { en: "Streak 7", cs: "Série 7" },
      desc: { en: "Play on 7 days in a row.", cs: "Hraj 7 dnů v řadě." },
      test: function (p) { return p.bestStreak >= 7; } },
    { id: "dont_peek", icon: "eye", name: { en: "Don't Peek", cs: "Nenahlížej" },
      desc: { en: "Complete the peeking demo in the Lab.", cs: "Dokonči ukázku nahlížení v Laboratoři." },
      test: function (p) { return p.peekDone === true; } },
    { id: "myth_buster", icon: "bulb", name: { en: "Myth Buster", cs: "Ničitel mýtů" },
      desc: { en: "Answer 10 Myth or Fact cards correctly.", cs: "Správně odpověz na 10 karet Mýtus, nebo fakt." },
      test: function (p) { return p.stats.mythsCorrect >= 10; } },
    { id: "polyglot", icon: "globe", name: { en: "Polyglot", cs: "Polyglot" },
      desc: { en: "Beat a boss in both English and Czech.", cs: "Poraz bosse v angličtině i v češtině." },
      test: function (p) { return p.winLangs.indexOf("en") >= 0 && p.winLangs.indexOf("cs") >= 0; } },
    { id: "level_5", icon: "star", name: { en: "Level 5", cs: "Úroveň 5" },
      desc: { en: "Reach level 5.", cs: "Dosáhni úrovně 5." },
      test: function (p) { return p.level >= 5; } },
    { id: "level_10", icon: "star", name: { en: "Level 10", cs: "Úroveň 10" },
      desc: { en: "Reach level 10.", cs: "Dosáhni úrovně 10." },
      test: function (p) { return p.level >= 10; } }
  ];

  function achievementById(id) {
    for (var i = 0; i < ACHIEVEMENTS.length; i++) if (ACHIEVEMENTS[i].id === id) return ACHIEVEMENTS[i];
    return null;
  }

  // -- arena --------------------------------------------------------------------------------
  function comboMultiplier(combo) { return Math.min(XP.comboMax, Math.floor(combo / XP.comboStep) + 1); }

  /** Choose the next duel: unseen first, the UI language first (when preferred), optional difficulty filter. */
  function pickDuel(arena, o) {
    o = o || {};
    var rng = o.rng || systemRng();
    var seen = o.seen || [];
    var pool = (arena || []).filter(function (d) { return !o.difficulty || o.difficulty === "all" || d.difficulty === o.difficulty; });
    if (!pool.length) return { duel: null, cycled: false };
    var fresh = pool.filter(function (d) { return seen.indexOf(d.id) < 0 && d.id !== o.avoid; });
    var cycled = false;
    if (!fresh.length) { cycled = true; fresh = pool.filter(function (d) { return d.id !== o.avoid; }); if (!fresh.length) fresh = pool; }
    if (o.preferLang !== false && o.lang) {
      var mine = fresh.filter(function (d) { return d.lang === o.lang; });
      if (mine.length) fresh = mine;
    }
    return { duel: fresh[Math.floor(rng() * fresh.length)], cycled: cycled };
  }

  /**
   * Resolve one Arena answer. args: {duel, pick: "a"|"b", confidence?: 50..100}.
   * XP: correct 10 (+5 medium, +10 hard, +10 for an upset called against the model), multiplied by the combo
   * multiplier (floor(combo / 5) + 1, at most x3, the combo counting this answer); +3 when confidence >= 80.
   * A wrong answer earns 2 XP and is never punished.
   */
  function answerDuel(profile, args, ctx) {
    var st = begin(profile, ctx), p = st.next, events = st.events;
    var duel = args.duel;
    var correct = args.pick === duel.winner;
    var upsetCaught = correct && duel.upset === true;
    var conf = typeof args.confidence === "number" ? clamp(args.confidence, 50, 100) : null;
    var xp = { base: 0, difficulty: 0, upset: 0, multiplier: 1, subtotal: 0, confidence: 0, total: 0, participation: 0 };

    p.stats.arenaPlayed += 1;
    if (correct) {
      p.stats.arenaCorrect += 1;
      p.combo += 1;
      p.stats.bestCombo = Math.max(p.stats.bestCombo, p.combo);
      xp.base = XP.arenaBase;
      xp.difficulty = duel.difficulty === "hard" ? XP.arenaHard : duel.difficulty === "medium" ? XP.arenaMedium : 0;
      xp.upset = upsetCaught ? XP.arenaUpset : 0;
      xp.multiplier = comboMultiplier(p.combo);
      xp.subtotal = (xp.base + xp.difficulty + xp.upset) * xp.multiplier;
      xp.confidence = conf !== null && conf >= XP.confidenceThreshold ? XP.confidenceBonus : 0;
      xp.total = xp.subtotal + xp.confidence;
      if (upsetCaught) p.stats.upsetsCaught += 1;
    } else {
      p.combo = 0;
      xp.participation = XP.arenaWrong;
      xp.total = XP.arenaWrong;
    }
    if (conf !== null) {
      var outcome = correct ? 1 : 0;
      p.brier.sum += Math.pow(conf / 100 - outcome, 2);
      p.brier.n += 1;
    }
    if (duel.id && p.arenaSeen.indexOf(duel.id) < 0) { p.arenaSeen.push(duel.id); if (p.arenaSeen.length > 400) p.arenaSeen.shift(); }
    award(p, xp.total, events);
    if (correct) {
      bump(p, "arena_win", 1, events);
      if (duel.difficulty === "hard") bump(p, "hard_win", 1, events);
      if (upsetCaught) bump(p, "upset", 1, events);
    }
    finish(p, events);
    return { profile: p, correct: correct, upsetCaught: upsetCaught, xp: xp, combo: p.combo, multiplier: xp.multiplier, oracle: oracleRating(p.brier), events: events };
  }

  /** P(A beats B) from two Dopamine Scores (calibrate.py win_probability). */
  function winProbability(scoreA, scoreB, logitScale) {
    return 1 / (1 + Math.exp(-(scoreA - scoreB) / (logitScale || 12)));
  }

  // -- boss ---------------------------------------------------------------------------------
  /**
   * Percentile of a score inside a distribution given as 101 quantiles (index = percentile).
   * Between two quantiles the position is interpolated; a run of equal quantiles (ties) takes its mid rank.
   */
  function percentileOf(score, quantiles) {
    var q = quantiles, n = q.length;
    if (!n) return null;
    if (score < q[0]) return 0;
    if (score > q[n - 1]) return n > 1 ? n - 1 : 100;
    var lo = 0;
    while (lo < n && q[lo] < score) lo += 1; // number of quantiles strictly below the score
    var eq = 0;
    while (lo + eq < n && q[lo + eq] === score) eq += 1;
    if (eq > 0) return lo + (eq - 1) / 2;
    return (lo - 1) + (score - q[lo - 1]) / (q[lo] - q[lo - 1]);
  }

  /** Smallest score (to 0.1) whose percentile reaches p inside the distribution. */
  function thresholdScore(p, quantiles) {
    var lo = 0, hi = 100;
    if (percentileOf(hi, quantiles) < p) return hi;
    for (var i = 0; i < 40; i++) {
      var mid = (lo + hi) / 2;
      if (percentileOf(mid, quantiles) >= p) hi = mid; else lo = mid;
    }
    return Math.ceil(hi * 10 - 1e-9) / 10;
  }

  function bossQuantiles(boss, benchmarks) {
    var b = benchmarks && (benchmarks[boss.cohort] || benchmarks.all);
    return b && Array.isArray(b.quantiles) && b.quantiles.length ? b.quantiles : null;
  }

  /** Win condition: percentile inside the boss cohort >= boss.percentile AND clickbait risk <= 0.35. */
  function resolveBoss(boss, score, benchmarks) {
    var q = bossQuantiles(boss, benchmarks);
    var pct = q ? percentileOf(score.total, q) : null;
    var risk = score.clickbait_risk;
    var pctOk = pct !== null && pct >= boss.percentile;
    var riskOk = risk <= BOSS_MAX_RISK;
    return {
      percentile: pct, needPercentile: boss.percentile, needScore: q ? thresholdScore(boss.percentile, q) : null,
      risk: risk, riskOk: riskOk, pctOk: pctOk, won: pctOk && riskOk, honest: risk < HONEST_RISK,
      hasBenchmark: !!q
    };
  }

  /** Apply a boss attack: XP = boss.xp on the first win of that boss per day, 20 percent for repeats. */
  function applyBoss(profile, args, ctx) {
    var st = begin(profile, ctx), p = st.next, events = st.events;
    var boss = args.boss, res = args.resolution;
    var out = { won: !!res.won, firstWin: false, xp: 0, chestGranted: false, honest: false };
    if (res.won) {
      var day = p.bossWinsByDay[st.today] = p.bossWinsByDay[st.today] || {};
      var count = day[boss.id] || 0;
      out.firstWin = count === 0;
      day[boss.id] = count + 1;
      out.xp = out.firstWin ? boss.xp : Math.round(boss.xp * XP.bossRepeatShare);
      p.stats.bossWins += 1;
      if (p.bossesBeaten.indexOf(boss.id) < 0) p.bossesBeaten.push(boss.id);
      var lang = args.lang === "cs" || args.lang === "en" ? args.lang : boss.lang;
      if ((lang === "cs" || lang === "en") && p.winLangs.indexOf(lang) < 0) p.winLangs.push(lang);
      out.honest = res.risk < HONEST_RISK;
      if (out.honest) p.stats.honestWins += 1;
      if (out.firstWin) { p.chestsReady += 1; out.chestGranted = true; }
      award(p, out.xp, events);
      bump(p, "boss_win", 1, events);
      if (out.honest) bump(p, "clean_win", 1, events);
      pruneDays(p.bossWinsByDay, st.today);
    }
    finish(p, events);
    out.profile = p; out.events = events;
    return out;
  }

  // -- lab ----------------------------------------------------------------------------------
  /** Hidden truth of a Lab duel round: B better by the scenario lift, no effect, or worse. */
  function drawLabTruth(scenario, rng) {
    var u = rng();
    var kind = u < LAB_TRUTH_ODDS.better ? "better" : u < LAB_TRUTH_ODDS.better + LAB_TRUTH_ODDS.none ? "none" : "worse";
    var lift = scenario.lift_rel;
    var rateA = scenario.baseline;
    var rateB = kind === "better" ? rateA * (1 + lift) : kind === "worse" ? rateA / (1 + lift) : rateA;
    return { kind: kind, rateA: rateA, rateB: rateB, trueLiftRel: rateB / rateA - 1 };
  }

  /**
   * Judge a Lab decision against the hidden truth. Shipping B is right only when B is truly better,
   * shipping A is right when it is not, and "keep testing" is right while the evidence is inconclusive.
   */
  function judgeLabDecision(decision, truth, test) {
    var alpha = test && test.alpha !== undefined ? test.alpha : 0.05;
    var conclusive = !!test && test.pValue < alpha;
    if (decision === "ship_b") return { correct: truth.kind === "better", conclusive: conclusive };
    if (decision === "ship_a") return { correct: truth.kind !== "better", conclusive: conclusive };
    return { correct: !conclusive, conclusive: conclusive };
  }

  function applyLabRun(profile, args, ctx) {
    var st = begin(profile, ctx), p = st.next, events = st.events;
    p.stats.labRuns += 1;
    if (args && args.kind === "peek") p.peekDone = true;
    if (args && args.kind === "bandit") p.banditDone = true;
    bump(p, "lab_run", 1, events);
    finish(p, events);
    return { profile: p, events: events };
  }

  function applyLabDecision(profile, args, ctx) {
    var st = begin(profile, ctx), p = st.next, events = st.events;
    var xp = args.correct ? XP.labRight : XP.labWrong;
    p.stats.labPlayed += 1;
    if (args.correct) p.stats.labCorrect += 1;
    award(p, xp, events);
    finish(p, events);
    return { profile: p, xp: xp, events: events };
  }

  // -- myth or fact -------------------------------------------------------------------------
  function answerMyth(profile, args, ctx) {
    var st = begin(profile, ctx), p = st.next, events = st.events;
    var correct = args.answer === args.myth.answer;
    var xp = correct ? XP.mythRight : XP.mythWrong;
    p.stats.mythsPlayed += 1;
    if (correct) p.stats.mythsCorrect += 1;
    if (args.myth.id && p.mythsSeen.indexOf(args.myth.id) < 0) { p.mythsSeen.push(args.myth.id); if (p.mythsSeen.length > 100) p.mythsSeen.shift(); }
    award(p, xp, events);
    bump(p, "myth", 1, events);
    finish(p, events);
    return { profile: p, correct: correct, xp: xp, events: events };
  }

  function pickMyth(myths, o) {
    o = o || {};
    var rng = o.rng || systemRng();
    var seen = o.seen || [];
    var pool = myths || [];
    if (!pool.length) return null;
    var fresh = pool.filter(function (m) { return seen.indexOf(m.id) < 0 && m.id !== o.avoid; });
    if (!fresh.length) fresh = pool.filter(function (m) { return m.id !== o.avoid; });
    if (!fresh.length) fresh = pool;
    return fresh[Math.floor(rng() * fresh.length)];
  }

  // -- loot ---------------------------------------------------------------------------------
  function rarityRank(r) { var i = RARITIES.indexOf(r); return i < 0 ? 0 : i; }

  /** Draw a rarity from the published rates; minRank restricts (and renormalises) to rare or better. */
  function drawRarity(rates, rng, minRank) {
    minRank = minRank || 0;
    var list = RARITIES.map(function (r, i) { return { r: r, i: i, w: Math.max(0, +(rates || {})[r] || 0) }; })
      .filter(function (x) { return x.i >= minRank && x.w > 0; });
    var total = list.reduce(function (a, x) { return a + x.w; }, 0);
    if (!list.length || total <= 0) return RARITIES[minRank];
    var u = rng() * total, acc = 0;
    for (var k = 0; k < list.length; k++) { acc += list[k].w; if (u < acc) return list[k].r; }
    return list[list.length - 1].r;
  }

  function nearestPool(byRarity, rarity, minRank) {
    var rank = rarityRank(rarity);
    var order = RARITIES.map(function (r, i) { return { r: r, i: i, d: Math.abs(i - rank) }; })
      .sort(function (a, b) { return a.d - b.d || a.i - b.i; });
    for (var pass = 0; pass < 2; pass++) {
      for (var k = 0; k < order.length; k++) {
        if (pass === 0 && order[k].i < minRank) continue;
        if (byRarity[order[k].r] && byRarity[order[k].r].length) return order[k].r;
      }
    }
    return null;
  }

  /**
   * One chest. opts: {cards, rates, pityAfter, owned, pity}. After pityAfter consecutive chests without a
   * rare or better card the next one is guaranteed rare or better. Unowned cards of the drawn rarity are
   * preferred; a duplicate turns into 5 XP of dust. When an edition has no cards of the drawn rarity the
   * nearest rarity with cards is used (the UI says so next to the published odds).
   */
  function drawChest(opts, rng) {
    var cards = opts.cards || [];
    if (!cards.length) return null;
    var pity = opts.pity || 0, pityAfter = opts.pityAfter || 8;
    var owned = opts.owned || [];
    var guaranteed = pity >= pityAfter;
    var minRank = guaranteed ? 1 : 0;
    var drawn = drawRarity(opts.rates, rng, minRank);
    var byRarity = {};
    cards.forEach(function (c) { var r = RARITIES.indexOf(c.rarity) < 0 ? "common" : c.rarity; (byRarity[r] = byRarity[r] || []).push(c); });
    var used = nearestPool(byRarity, drawn, minRank);
    var pool = byRarity[used];
    var unowned = pool.filter(function (c) { return owned.indexOf(c.id) < 0; });
    var duplicate = unowned.length === 0;
    var from = duplicate ? pool : unowned;
    var card = from[Math.floor(rng() * from.length)];
    var rank = rarityRank(card.rarity);
    return {
      card: card, rarity: RARITIES[rank], drawnRarity: drawn, duplicate: duplicate, dust: duplicate ? XP.dust : 0,
      guaranteed: guaranteed, pity: rank >= 1 ? 0 : pity + 1, pityBefore: pity
    };
  }

  /** Open one chest from the inventory. Returns {ok:false} when none is ready or the edition has no cards. */
  function openChest(profile, loot, ctx) {
    if (!(profile.chestsReady > 0)) return { ok: false, reason: "no_chest", profile: profile, events: [] };
    var cards = loot && loot.cards || [];
    if (!cards.length) return { ok: false, reason: "no_cards", profile: profile, events: [] };
    var st = begin(profile, ctx), p = st.next, events = st.events;
    var rng = ctx && ctx.rng || systemRng();
    var res = drawChest({ cards: cards, rates: loot.rates, pityAfter: loot.pity_after, owned: p.deck, pity: p.pity }, rng);
    p.chestsReady -= 1;
    p.stats.chests += 1;
    p.pity = res.pity;
    if (res.duplicate) award(p, res.dust, events); else p.deck.push(res.card.id);
    finish(p, events);
    res.ok = true; res.profile = p; res.events = events;
    return res;
  }

  /** Looking at a vault card counts for the daily quest. */
  function applyVaultOpen(profile, ctx) {
    var st = begin(profile, ctx), p = st.next, events = st.events;
    bump(p, "vault_open", 1, events);
    finish(p, events);
    return { profile: p, events: events };
  }

  // -- wellbeing ----------------------------------------------------------------------------
  /** True once per session after limitMinutes of active play (0 or less disables the reminder). */
  function shouldShowBreak(o) {
    if (!o || o.alreadyShown) return false;
    var limit = o.limitMinutes === undefined ? DEFAULT_SESSION_MINUTES : o.limitMinutes;
    return limit > 0 && o.activeSeconds >= limit * 60;
  }

  function addPlayTime(profile, seconds, today) {
    var p = clone(profile);
    if (p.playTime.date !== today) p.playTime = { date: today, seconds: 0 };
    p.playTime.seconds += Math.max(0, seconds);
    return p;
  }

  function playMinutesToday(profile, today) {
    return profile.playTime && profile.playTime.date === today ? Math.floor(profile.playTime.seconds / 60) : 0;
  }

  /** The suggested next action for the Home screen. */
  function nextBestAction(profile, today) {
    if (profile.chestsReady > 0) return { key: "chest", route: "vault", params: null };
    var open = questView(profile, today).filter(function (q) { return !q.done; })[0];
    if (open) return { key: "quest", route: open.route, params: open.params, quest: open.id };
    if (oracleRating(profile.brier) === null) return { key: "oracle", route: "arena", params: null };
    return { key: "boss", route: "boss", params: null };
  }

  return {
    PROFILE_KEY: PROFILE_KEY, PROFILE_VERSION: PROFILE_VERSION, XP: XP, LEVELS: LEVELS, RARITIES: RARITIES,
    QUEST_POOL: QUEST_POOL, ACHIEVEMENTS: ACHIEVEMENTS, LAB_TRUTH_ODDS: LAB_TRUTH_ODDS,
    BOSS_MAX_RISK: BOSS_MAX_RISK, HONEST_RISK: HONEST_RISK, ORACLE_MIN_ANSWERS: ORACLE_MIN_ANSWERS,
    MAX_FREEZES: MAX_FREEZES, DEFAULT_SESSION_MINUTES: DEFAULT_SESSION_MINUTES,
    clone: clone, localDate: localDate, dayNumber: dayNumber, daysBetween: daysBetween, systemRng: systemRng,
    xpForLevel: xpForLevel, levelForXp: levelForXp, levelTitle: levelTitle, levelProgress: levelProgress,
    defaultProfile: defaultProfile, normalizeProfile: normalizeProfile,
    brierScore: brierScore, oracleRating: oracleRating, advanceStreak: advanceStreak,
    questDef: questDef, questIdsForDate: questIdsForDate, questView: questView, rollover: rollover, streakStatus: streakStatus,
    achievementById: achievementById, comboMultiplier: comboMultiplier,
    pickDuel: pickDuel, answerDuel: answerDuel, winProbability: winProbability,
    percentileOf: percentileOf, thresholdScore: thresholdScore, resolveBoss: resolveBoss, applyBoss: applyBoss,
    drawLabTruth: drawLabTruth, judgeLabDecision: judgeLabDecision, applyLabRun: applyLabRun, applyLabDecision: applyLabDecision,
    answerMyth: answerMyth, pickMyth: pickMyth,
    drawRarity: drawRarity, drawChest: drawChest, openChest: openChest, applyVaultOpen: applyVaultOpen,
    shouldShowBreak: shouldShowBreak, addPlayTime: addPlayTime, playMinutesToday: playMinutesToday,
    nextBestAction: nextBestAction
  };
});
