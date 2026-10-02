"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const game = require("../src/game.js");
const { mulberry32 } = require("../src/labstats.js");

const bundle = JSON.parse(fs.readFileSync(path.resolve(__dirname, "..", "dev", "bundle.json"), "utf8"));

const ctxAt = (iso = "2026-10-01T12:00:00", seed = 1) => ({ now: () => new Date(iso), rng: mulberry32(seed) });
const duel = (over = {}) => Object.assign({ id: "p1", difficulty: "easy", winner: "a", upset: false, lang: "en" }, over);
const fresh = () => game.defaultProfile({ lang: "en", today: "2026-10-01" });
// A profile whose quests cannot be completed by arena answers, so XP assertions stay exact.
const quiet = () => {
  const p = fresh();
  p.quests = { date: "2026-10-01", ids: ["boss_win", "lab_run", "vault_open"], progress: {}, done: {}, bonusGranted: false };
  return p;
};
const near = (a, b, tol, msg) => assert.ok(Math.abs(a - b) <= tol, `${msg || ""} ${a} vs ${b}`);

// -- levels -------------------------------------------------------------------------------------
test("level thresholds follow round(100 * (n - 1) ^ 1.5)", () => {
  assert.equal(game.xpForLevel(1), 0);
  assert.equal(game.xpForLevel(2), 100);
  assert.equal(game.xpForLevel(3), 283);
  assert.equal(game.xpForLevel(4), 520);
  assert.equal(game.xpForLevel(5), 800);
  assert.equal(game.xpForLevel(10), 2700);
  for (let n = 1; n <= 30; n++) assert.equal(game.xpForLevel(n), n <= 1 ? 0 : Math.round(100 * Math.pow(n - 1, 1.5)));
  assert.equal(game.levelForXp(0), 1);
  assert.equal(game.levelForXp(99), 1);
  assert.equal(game.levelForXp(100), 2);
  assert.equal(game.levelForXp(282), 2);
  assert.equal(game.levelForXp(283), 3);
  assert.equal(game.levelForXp(2700), 10);
  assert.equal(game.levelForXp(1e6) > 10, true);
});

test("ten named levels in English and Czech, the last title is kept above 10", () => {
  assert.equal(game.LEVELS.length, 10);
  game.LEVELS.forEach((l) => { assert.ok(l.en && l.cs); assert.ok(/\S/.test(l.en + l.cs)); });
  assert.equal(game.levelTitle(1, "en"), "Rookie");
  assert.equal(game.levelTitle(10, "en"), "King");
  assert.equal(game.levelTitle(25, "en"), "King");
  assert.equal(game.levelTitle(25, "cs"), "Král");
  assert.equal(new Set(game.LEVELS.map((l) => l.en)).size, 10);
  const p = game.levelProgress(150);
  assert.equal(p.level, 2);
  assert.equal(p.into, 50);
  assert.equal(p.span, 183);
  near(p.pct, 50 / 183, 1e-12);
});

// -- profile ------------------------------------------------------------------------------------
test("default profile has the documented shape", () => {
  const p = fresh();
  for (const k of ["name", "xp", "level", "streak", "bestStreak", "lastPlayDate", "freezeTokens", "pity", "deck", "stats", "brier", "achievements", "bossWinsByDay", "quests", "settings"]) assert.ok(k in p, k);
  for (const k of ["arenaPlayed", "arenaCorrect", "upsetsCaught", "bossWins", "labRuns", "mythsCorrect", "mythsPlayed", "chests"]) assert.equal(p.stats[k], 0, k);
  assert.deepEqual(p.brier, { sum: 0, n: 0 });
  assert.equal(p.settings.sessionMinutes, 20);
  assert.equal(p.settings.sound, false, "sound is off by default");
  assert.equal(p.settings.lang, "en");
  assert.equal(game.defaultProfile({ lang: "cs" }).settings.lang, "cs");
});

test("normalizeProfile repairs garbage and clamps values", () => {
  assert.deepEqual(game.normalizeProfile(null).stats, fresh().stats);
  const p = game.normalizeProfile({
    xp: -50, streak: "x", freezeTokens: 9, deck: ["a", "a", 3, "b"], settings: { lang: "de", sessionMinutes: 9999, sound: "yes" },
    brier: { sum: -1, n: 2.7 }, bossWinsByDay: { "2026-10-01": { b: 2 }, nonsense: { b: 1 } }, lastPlayDate: "yesterday", level: 99
  });
  assert.equal(p.xp, 0);
  assert.equal(p.level, 1);
  assert.equal(p.streak, 0);
  assert.equal(p.freezeTokens, 2);
  assert.deepEqual(p.deck, ["a", "b"]);
  assert.equal(p.settings.lang, "en");
  assert.equal(p.settings.sessionMinutes, 240);
  assert.equal(p.settings.sound, false);
  assert.deepEqual(p.brier, { sum: 0, n: 2 });
  assert.deepEqual(Object.keys(p.bossWinsByDay), ["2026-10-01"]);
  assert.equal(p.lastPlayDate, null);
  const round = game.normalizeProfile(JSON.parse(JSON.stringify(game.answerDuel(fresh(), { duel: duel(), pick: "a" }, ctxAt()).profile)));
  assert.equal(round.xp, 10);
});

// -- arena --------------------------------------------------------------------------------------
test("arena XP: base 10, +5 medium, +10 hard, +10 upset called", () => {
  const cases = [
    [{ difficulty: "easy" }, 10], [{ difficulty: "medium" }, 15], [{ difficulty: "hard" }, 20],
    [{ difficulty: "easy", upset: true }, 20], [{ difficulty: "medium", upset: true }, 25], [{ difficulty: "hard", upset: true }, 30]
  ];
  for (const [over, expected] of cases) {
    const r = game.answerDuel(quiet(), { duel: duel(over), pick: "a" }, ctxAt());
    assert.equal(r.correct, true);
    assert.equal(r.xp.total, expected, JSON.stringify(over));
    assert.equal(r.profile.xp, expected);
  }
});

test("a wrong answer gives 2 XP, never negative, and resets the combo", () => {
  let p = quiet();
  for (let i = 0; i < 3; i++) p = game.answerDuel(p, { duel: duel({ id: "c" + i }), pick: "a" }, ctxAt()).profile;
  assert.equal(p.combo, 3);
  const before = p.xp;
  const r = game.answerDuel(p, { duel: duel({ id: "w", upset: true }), pick: "b" }, ctxAt());
  assert.equal(r.correct, false);
  assert.equal(r.upsetCaught, false);
  assert.equal(r.xp.total, 2);
  assert.equal(r.profile.xp, before + 2);
  assert.equal(r.profile.combo, 0);
  assert.equal(r.profile.stats.arenaPlayed, 4);
  assert.equal(r.profile.stats.arenaCorrect, 3);
});

test("combo multiplier is floor(consecutive / 5) + 1 capped at x3", () => {
  assert.deepEqual([0, 1, 4, 5, 9, 10, 14, 15, 40].map(game.comboMultiplier), [1, 1, 1, 2, 2, 3, 3, 3, 3]);
  let p = quiet();
  const gains = [];
  for (let i = 1; i <= 12; i++) {
    const r = game.answerDuel(p, { duel: duel({ id: "d" + i }), pick: "a" }, ctxAt());
    gains.push(r.xp.total);
    p = r.profile;
  }
  assert.deepEqual(gains, [10, 10, 10, 10, 20, 20, 20, 20, 20, 30, 30, 30]);
  assert.equal(p.stats.bestCombo, 12);
});

test("confidence: +3 XP when correct with confidence >= 80, Brier and Oracle rating", () => {
  const at80 = game.answerDuel(fresh(), { duel: duel(), pick: "a", confidence: 80 }, ctxAt());
  assert.equal(at80.xp.confidence, 3);
  assert.equal(at80.xp.total, 13);
  const at79 = game.answerDuel(fresh(), { duel: duel(), pick: "a", confidence: 79 }, ctxAt());
  assert.equal(at79.xp.confidence, 0);
  const wrong90 = game.answerDuel(fresh(), { duel: duel(), pick: "b", confidence: 90 }, ctxAt());
  assert.equal(wrong90.xp.total, 2);
  near(wrong90.profile.brier.sum, 0.81, 1e-12);
  near(at80.profile.brier.sum, 0.04, 1e-12);
  const none = game.answerDuel(fresh(), { duel: duel(), pick: "a" }, ctxAt());
  assert.deepEqual(none.profile.brier, { sum: 0, n: 0 }, "no confidence, no Brier entry");
  // confidence is clamped to 50..100
  const odd = game.answerDuel(fresh(), { duel: duel(), pick: "a", confidence: 150 }, ctxAt());
  near(odd.profile.brier.sum, 0, 1e-12);
});

test("Oracle rating = clamp(100 * (1 - brier / 0.25)) shown after at least 10 answers", () => {
  assert.equal(game.oracleRating({ sum: 0, n: 9 }), null);
  assert.equal(game.oracleRating({ sum: 0, n: 10 }), 100);
  assert.equal(game.oracleRating({ sum: 2.5, n: 10 }), 0, "a coin flip forecaster scores 0");
  near(game.oracleRating({ sum: 1.25, n: 10 }), 50, 1e-9);
  assert.equal(game.oracleRating({ sum: 9, n: 10 }), 0, "clamped at 0");
  near(game.brierScore({ sum: 1, n: 4 }), 0.25, 1e-12);
  assert.equal(game.brierScore({ sum: 0, n: 0 }), null);
  let p = fresh();
  for (let i = 0; i < 10; i++) p = game.answerDuel(p, { duel: duel({ id: "o" + i }), pick: "a", confidence: 100 }, ctxAt()).profile;
  assert.equal(game.oracleRating(p.brier), 100);
});

test("upset calls are counted and quests, achievements fire", () => {
  let p = fresh();
  const ev = [];
  for (let i = 0; i < 5; i++) {
    const r = game.answerDuel(p, { duel: duel({ id: "u" + i, upset: true, difficulty: "hard" }), pick: "a" }, ctxAt());
    p = r.profile;
    ev.push(...r.events);
  }
  assert.equal(p.stats.upsetsCaught, 5);
  assert.ok(ev.some((e) => e.type === "achievement" && e.id === "first_blood"));
  assert.ok(ev.some((e) => e.type === "achievement" && e.id === "upset_hunter"));
  assert.ok(p.achievements.includes("upset_hunter"));
});

test("pickDuel prefers unseen duels in the UI language and respects filters", () => {
  const arena = bundle.arena;
  const rng = mulberry32(3);
  for (let i = 0; i < 30; i++) {
    const { duel: d } = game.pickDuel(arena, { lang: "cs", seen: [], rng });
    assert.equal(d.lang, "cs");
  }
  const seenCs = arena.filter((d) => d.lang === "cs").map((d) => d.id);
  const { duel: other } = game.pickDuel(arena, { lang: "cs", seen: seenCs, rng });
  assert.equal(other.lang, "en", "falls back to the other language once the preferred ones are seen");
  const { duel: any } = game.pickDuel(arena, { lang: "cs", preferLang: false, seen: [], rng: mulberry32(1) });
  assert.ok(any);
  const hard = game.pickDuel(arena, { difficulty: "hard", seen: [], rng });
  assert.equal(hard.duel.difficulty, "hard");
  const allSeen = game.pickDuel(arena, { seen: arena.map((d) => d.id), rng });
  assert.equal(allSeen.cycled, true);
  assert.ok(allSeen.duel);
  const avoid = game.pickDuel(arena.slice(0, 2), { seen: [], avoid: arena[0].id, rng });
  assert.equal(avoid.duel.id, arena[1].id);
  assert.equal(game.pickDuel([], { rng }).duel, null);
});

test("win probability helper", () => {
  near(game.winProbability(50, 50), 0.5, 1e-12);
  near(game.winProbability(60, 40, 12), 1 / (1 + Math.exp(-20 / 12)), 1e-12);
  assert.ok(game.winProbability(40, 60) < 0.5);
  // The bundle was computed with the calibrated logit scale; the stored probabilities must agree.
  const k = bundle.calibration.logit_scale;
  for (const d of bundle.arena) near(game.winProbability(d.a.score, d.b.score, k), d.model_p_a, 0.002, d.id);
});

// -- boss ---------------------------------------------------------------------------------------
test("percentile uses interpolation and mid rank for ties", () => {
  const q = Array.from({ length: 101 }, (_, i) => i); // score == percentile
  assert.equal(game.percentileOf(-1, q), 0);
  assert.equal(game.percentileOf(0, q), 0);
  assert.equal(game.percentileOf(50, q), 50);
  assert.equal(game.percentileOf(100, q), 100);
  assert.equal(game.percentileOf(250, q), 100);
  near(game.percentileOf(37.5, q), 37.5, 1e-12);
  const tied = [0, 0, 0, 0, 10, 20];
  assert.equal(game.percentileOf(0, tied), 1.5, "mid rank of a run of ties");
  const real = bundle.benchmarks.all.quantiles;
  let prev = -1;
  for (let s = 0; s <= 100; s += 0.5) {
    const v = game.percentileOf(s, real);
    assert.ok(v >= prev - 1e-12, `monotone at ${s}`);
    assert.ok(v >= 0 && v <= 100);
    prev = v;
  }
  assert.equal(game.percentileOf(real[100] + 1, real), 100);
});

test("thresholdScore inverts the percentile", () => {
  const real = bundle.benchmarks.all.quantiles;
  for (const p of [60, 75, 90]) {
    const s = game.thresholdScore(p, real);
    assert.ok(game.percentileOf(s, real) >= p, `score ${s} reaches p${p}`);
    assert.ok(game.percentileOf(s - 0.2, real) < p, `score ${s - 0.2} stays below p${p}`);
  }
});

const boss = bundle.bosses[0];
const score = (total, risk) => ({ total, clickbait_risk: risk, lang: "en" });

test("boss win needs the percentile AND a clickbait risk of at most 0.35", () => {
  const need = game.thresholdScore(boss.percentile, bundle.benchmarks[boss.cohort].quantiles);
  const win = game.resolveBoss(boss, score(need + 5, 0.1), bundle.benchmarks);
  assert.equal(win.won, true);
  assert.ok(win.percentile >= boss.percentile);
  const weak = game.resolveBoss(boss, score(need - 5, 0.1), bundle.benchmarks);
  assert.equal(weak.won, false);
  assert.equal(weak.pctOk, false);
  assert.equal(weak.riskOk, true);
  const risky = game.resolveBoss(boss, score(need + 20, 0.5), bundle.benchmarks);
  assert.equal(risky.won, false);
  assert.equal(risky.pctOk, true);
  assert.equal(risky.riskOk, false);
  assert.equal(game.resolveBoss(boss, score(need + 20, 0.35), bundle.benchmarks).won, true, "0.35 is still allowed");
  assert.equal(game.resolveBoss(boss, score(need + 20, 0.36), bundle.benchmarks).won, false);
  assert.equal(game.resolveBoss(boss, score(need + 5, 0.05), bundle.benchmarks).honest, true);
  assert.equal(game.resolveBoss(boss, score(need + 5, 0.15), bundle.benchmarks).honest, false);
  const none = game.resolveBoss(boss, score(99, 0), {});
  assert.equal(none.won, false);
  assert.equal(none.hasBenchmark, false);
  const viaAll = game.resolveBoss(Object.assign({}, boss, { cohort: "unknown-cohort" }), score(99, 0), bundle.benchmarks);
  assert.equal(viaAll.hasBenchmark, true, "falls back to the all-corpus benchmark");
});

test("every bundled boss is beatable by an honest strong hook", () => {
  for (const b of bundle.bosses) {
    const q = bundle.benchmarks[b.cohort].quantiles;
    assert.ok(game.thresholdScore(b.percentile, q) < 70, `${b.id} needs ${game.thresholdScore(b.percentile, q)}`);
  }
});

test("boss XP: full on the first win of the day, 20 percent after, one chest per first win", () => {
  const res = { won: true, risk: 0.2, percentile: 80 };
  const a = game.applyBoss(fresh(), { boss, resolution: res, lang: "en" }, ctxAt());
  assert.equal(a.firstWin, true);
  assert.equal(a.xp, boss.xp);
  assert.equal(a.chestGranted, true);
  assert.equal(a.profile.chestsReady, fresh().chestsReady + 1);
  const b = game.applyBoss(a.profile, { boss, resolution: res, lang: "en" }, ctxAt());
  assert.equal(b.firstWin, false);
  assert.equal(b.xp, Math.round(boss.xp * 0.2));
  assert.equal(b.chestGranted, false);
  assert.equal(b.profile.stats.bossWins, 2);
  const nextDay = game.applyBoss(b.profile, { boss, resolution: res, lang: "en" }, ctxAt("2026-10-02T09:00:00"));
  assert.equal(nextDay.firstWin, true, "first win of the new day");
  assert.equal(nextDay.xp, boss.xp);
  const otherBoss = game.applyBoss(nextDay.profile, { boss: bundle.bosses[1], resolution: res, lang: "en" }, ctxAt("2026-10-02T10:00:00"));
  assert.equal(otherBoss.xp, bundle.bosses[1].xp, "another boss starts fresh the same day");
  const lost = game.applyBoss(fresh(), { boss, resolution: { won: false, risk: 0.2 }, lang: "en" }, ctxAt());
  assert.equal(lost.xp, 0);
  assert.equal(lost.profile.xp, 0);
  assert.equal(lost.profile.stats.bossWins, 0);
});

test("boss achievements: Honest Hook, Boss Slayer, Polyglot", () => {
  let p = fresh();
  const honest = game.applyBoss(p, { boss: bundle.bosses[0], resolution: { won: true, risk: 0.05 }, lang: "en" }, ctxAt());
  assert.ok(honest.events.some((e) => e.type === "achievement" && e.id === "honest_hook"));
  p = honest.profile;
  p = game.applyBoss(p, { boss: bundle.bosses[1], resolution: { won: true, risk: 0.2 }, lang: "en" }, ctxAt()).profile;
  const third = game.applyBoss(p, { boss: bundle.bosses[2], resolution: { won: true, risk: 0.2 }, lang: "en" }, ctxAt());
  assert.ok(third.events.some((e) => e.id === "boss_slayer"));
  assert.ok(!third.profile.achievements.includes("polyglot"));
  const cs = game.applyBoss(third.profile, { boss: bundle.bosses.find((b) => b.lang === "cs"), resolution: { won: true, risk: 0.2 }, lang: "cs" }, ctxAt());
  assert.ok(cs.events.some((e) => e.id === "polyglot"));
});

// -- lab, myths ---------------------------------------------------------------------------------
test("Lab XP: +25 for a correct decision, +5 otherwise; myths +8 / +2", () => {
  assert.equal(game.applyLabDecision(fresh(), { correct: true }, ctxAt()).xp, 25);
  const wrong = game.applyLabDecision(fresh(), { correct: false }, ctxAt());
  assert.equal(wrong.xp, 5);
  assert.equal(wrong.profile.xp, 5);
  const myth = bundle.myths[0];
  const right = game.answerMyth(fresh(), { myth, answer: myth.answer }, ctxAt());
  assert.equal(right.correct, true);
  assert.equal(right.xp, 8);
  const flip = game.answerMyth(fresh(), { myth, answer: myth.answer === "myth" ? "fact" : "myth" }, ctxAt());
  assert.equal(flip.xp, 2);
  assert.equal(flip.profile.stats.mythsPlayed, 1);
  assert.equal(flip.profile.stats.mythsCorrect, 0);
  assert.deepEqual(flip.profile.mythsSeen, [myth.id]);
});

test("Lab runs count, the peeking demo unlocks Don't Peek", () => {
  const r = game.applyLabRun(fresh(), { kind: "peek" }, ctxAt());
  assert.equal(r.profile.stats.labRuns, 1);
  assert.equal(r.profile.peekDone, true);
  assert.ok(r.events.some((e) => e.type === "achievement" && e.id === "dont_peek"));
  assert.equal(game.applyLabRun(fresh(), { kind: "duel" }, ctxAt()).profile.peekDone, false);
  assert.equal(game.applyLabRun(fresh(), { kind: "bandit" }, ctxAt()).profile.banditDone, true);
});

test("Lab truth is drawn with the published odds from the scenario lift", () => {
  const sc = bundle.lab.scenarios[0];
  const rng = mulberry32(12);
  const counts = { better: 0, none: 0, worse: 0 };
  const n = 20000;
  for (let i = 0; i < n; i++) {
    const t = game.drawLabTruth(sc, rng);
    counts[t.kind] += 1;
    assert.equal(t.rateA, sc.baseline);
    if (t.kind === "better") near(t.rateB, sc.baseline * (1 + sc.lift_rel), 1e-12);
    if (t.kind === "none") assert.equal(t.rateB, sc.baseline);
    if (t.kind === "worse") assert.ok(t.rateB < sc.baseline);
  }
  for (const k of Object.keys(counts)) near(counts[k] / n, game.LAB_TRUTH_ODDS[k], 0.015, k);
  near(game.LAB_TRUTH_ODDS.better + game.LAB_TRUTH_ODDS.none + game.LAB_TRUTH_ODDS.worse, 1, 1e-12);
});

test("Lab decisions are judged against the hidden truth", () => {
  const better = { kind: "better" }, none = { kind: "none" }, worse = { kind: "worse" };
  const sigB = { pValue: 0.01, alpha: 0.05, diff: 0.01 }, sigA = { pValue: 0.01, alpha: 0.05, diff: -0.01 }, weak = { pValue: 0.4, alpha: 0.05, diff: 0.002 };
  assert.equal(game.judgeLabDecision("ship_b", better, sigB).correct, true);
  assert.equal(game.judgeLabDecision("ship_b", none, sigB).correct, false, "fooled by a false positive");
  assert.equal(game.judgeLabDecision("ship_b", worse, weak).correct, false);
  assert.equal(game.judgeLabDecision("ship_a", better, sigB).correct, false);
  assert.equal(game.judgeLabDecision("ship_a", none, weak).correct, true);
  assert.equal(game.judgeLabDecision("ship_a", worse, sigA).correct, true);
  assert.equal(game.judgeLabDecision("keep_testing", better, weak).correct, true, "inconclusive evidence: keep testing is right");
  assert.equal(game.judgeLabDecision("keep_testing", better, sigB).correct, false, "conclusive and right: waiting wastes traffic");
  assert.equal(game.judgeLabDecision("keep_testing", worse, sigA).correct, false, "conclusive and right about B being worse");
  assert.equal(game.judgeLabDecision("keep_testing", none, sigB).correct, true, "a false alarm: confirming first is wise");
  assert.equal(game.judgeLabDecision("keep_testing", better, sigA).correct, true, "evidence pointing the wrong way");
  assert.equal(game.judgeLabDecision("keep_testing", none, weak).correct, true);
  assert.equal(game.judgeLabDecision("ship_b", better, sigB).evidenceSays, "b");
  assert.equal(game.judgeLabDecision("ship_b", better, weak).evidenceSays, "none");
  assert.equal(game.judgeLabDecision("ship_b", better, sigA).conclusive, true);
});

// -- streaks ------------------------------------------------------------------------------------
test("streak rules", () => {
  const S = (o) => Object.assign({ streak: 0, bestStreak: 0, lastPlayDate: null, freezeTokens: 0 }, o);
  let r = game.advanceStreak(S({}), "2026-10-01");
  assert.equal(r.state.streak, 1);
  assert.equal(r.state.lastPlayDate, "2026-10-01");
  r = game.advanceStreak(r.state, "2026-10-01");
  assert.equal(r.state.streak, 1);
  assert.equal(r.info.changed, false, "same day: no change");
  r = game.advanceStreak(r.state, "2026-10-02");
  assert.equal(r.state.streak, 2, "yesterday: +1");
  assert.equal(r.state.bestStreak, 2);
  // a gap without freezes restarts at 1, best streak is kept
  const gap = game.advanceStreak(S({ streak: 5, bestStreak: 5, lastPlayDate: "2026-10-01" }), "2026-10-04");
  assert.equal(gap.state.streak, 1);
  assert.equal(gap.state.bestStreak, 5);
  assert.equal(gap.info.restarted, true);
  // a freeze per missed day when available
  const frozen = game.advanceStreak(S({ streak: 5, bestStreak: 5, lastPlayDate: "2026-10-01", freezeTokens: 2 }), "2026-10-04");
  assert.equal(frozen.state.streak, 6);
  assert.equal(frozen.state.freezeTokens, 0);
  assert.equal(frozen.info.freezeUsed, 2);
  const oneMissed = game.advanceStreak(S({ streak: 5, bestStreak: 5, lastPlayDate: "2026-10-01", freezeTokens: 1 }), "2026-10-03");
  assert.equal(oneMissed.state.streak, 6);
  assert.equal(oneMissed.state.freezeTokens, 0);
  // not enough freezes: streak restarts and the freeze is kept
  const short = game.advanceStreak(S({ streak: 5, bestStreak: 5, lastPlayDate: "2026-10-01", freezeTokens: 1 }), "2026-10-05");
  assert.equal(short.state.streak, 1);
  assert.equal(short.state.freezeTokens, 1);
  // a freeze is earned at every multiple of 7, at most 2 held
  const seven = game.advanceStreak(S({ streak: 6, bestStreak: 6, lastPlayDate: "2026-10-01", freezeTokens: 0 }), "2026-10-02");
  assert.equal(seven.state.streak, 7);
  assert.equal(seven.state.freezeTokens, 1);
  assert.equal(seven.info.freezeEarned, true);
  const capped = game.advanceStreak(S({ streak: 13, bestStreak: 13, lastPlayDate: "2026-10-01", freezeTokens: 2 }), "2026-10-02");
  assert.equal(capped.state.streak, 14);
  assert.equal(capped.state.freezeTokens, 2);
  // clock going backwards changes nothing
  const back = game.advanceStreak(S({ streak: 3, bestStreak: 3, lastPlayDate: "2026-10-05" }), "2026-10-01");
  assert.equal(back.state.streak, 3);
  // month and year boundaries, daylight saving independent
  assert.equal(game.advanceStreak(S({ streak: 1, lastPlayDate: "2026-12-31" }), "2027-01-01").state.streak, 2);
  assert.equal(game.daysBetween("2026-03-28", "2026-03-30"), 2);
  assert.equal(game.daysBetween("2026-10-24", "2026-10-26"), 2);
});

test("playing on consecutive days builds the streak through the actions", () => {
  let p = fresh();
  for (let day = 1; day <= 8; day++) {
    p = game.answerDuel(p, { duel: duel({ id: "s" + day }), pick: "a" }, ctxAt(`2026-10-${String(day).padStart(2, "0")}T20:00:00`)).profile;
  }
  assert.equal(p.streak, 8);
  assert.equal(p.freezeTokens, 1);
  assert.ok(p.achievements.includes("streak_7"));
  // two missed days use up the earned freeze first, then the streak restarts
  const back = game.answerDuel(p, { duel: duel({ id: "late" }), pick: "a" }, ctxAt("2026-10-10T08:00:00"));
  assert.equal(back.profile.streak, 9, "one freeze covers the single missed day");
  assert.ok(back.events.some((e) => e.type === "freezeUsed"));
  const restart = game.answerDuel(back.profile, { duel: duel({ id: "later" }), pick: "a" }, ctxAt("2026-10-20T08:00:00"));
  assert.equal(restart.profile.streak, 1);
  assert.equal(restart.profile.bestStreak, 9);
});

// -- quests -------------------------------------------------------------------------------------
test("quests are chosen deterministically from the date", () => {
  const ids = game.questIdsForDate("2026-10-01", 3);
  assert.equal(ids.length, 3);
  assert.equal(new Set(ids).size, 3);
  assert.deepEqual(ids, game.questIdsForDate("2026-10-01", 3));
  const pool = game.QUEST_POOL.map((q) => q.id);
  ids.forEach((id) => assert.ok(pool.includes(id)));
  const variants = new Set();
  for (let d = 1; d <= 28; d++) variants.add(game.questIdsForDate(`2026-10-${String(d).padStart(2, "0")}`, 3).join());
  assert.ok(variants.size > 10, "different days give different quests");
  assert.equal(game.QUEST_POOL.length, 8);
  const events = new Set(game.QUEST_POOL.map((q) => q.event));
  assert.equal(events.size, 8);
});

function forceQuests(p, ids) {
  const q = game.clone(p);
  q.quests = { date: "2026-10-01", ids, progress: {}, done: {}, bonusGranted: false };
  return q;
}

test("each quest pays 30 XP and all three open a bonus chest", () => {
  let p = forceQuests(fresh(), ["arena_wins", "hard_duel", "upset_call"]);
  const chests = p.chestsReady;
  let totalQuestXp = 0, bonus = 0, done = 0;
  for (let i = 0; i < 6; i++) {
    const r = game.answerDuel(p, { duel: duel({ id: "q" + i, difficulty: "hard", upset: true }), pick: "a" }, ctxAt());
    p = r.profile;
    r.events.forEach((e) => { if (e.type === "quest") { totalQuestXp += e.xp; done += 1; } if (e.type === "bonusChest") bonus += 1; });
  }
  assert.equal(done, 3);
  assert.equal(totalQuestXp, 90);
  assert.equal(bonus, 1, "the bonus chest is granted exactly once");
  assert.equal(p.chestsReady, chests + 1);
  assert.equal(p.quests.bonusGranted, true);
  const view = game.questView(p, "2026-10-01");
  assert.ok(view.every((q) => q.done && q.progress === q.target));
});

test("quest events: boss, clean win, lab, myths, vault", () => {
  let p = forceQuests(fresh(), ["boss_win", "clean_win", "lab_run"]);
  const b = game.applyBoss(p, { boss, resolution: { won: true, risk: 0.05 }, lang: "en" }, ctxAt());
  assert.deepEqual(b.events.filter((e) => e.type === "quest").map((e) => e.id).sort(), ["boss_win", "clean_win"]);
  const l = game.applyLabRun(b.profile, { kind: "duel" }, ctxAt());
  assert.ok(l.events.some((e) => e.type === "bonusChest"));

  p = forceQuests(fresh(), ["myths_5", "vault_open", "arena_wins"]);
  const myth = bundle.myths[0];
  for (let i = 0; i < 4; i++) p = game.answerMyth(p, { myth, answer: "fact" }, ctxAt()).profile;
  assert.equal(game.questView(p, "2026-10-01").find((q) => q.id === "myths_5").progress, 4);
  const fifth = game.answerMyth(p, { myth, answer: "fact" }, ctxAt());
  assert.ok(fifth.events.some((e) => e.type === "quest" && e.id === "myths_5"), "answering counts, right or wrong");
  const v = game.applyVaultOpen(fifth.profile, null, ctxAt());
  assert.ok(v.events.some((e) => e.type === "quest" && e.id === "vault_open"));
});

test("opening the game does not count as activity for the streak", () => {
  const p = game.rollover(Object.assign(fresh(), { streak: 4, bestStreak: 4, lastPlayDate: "2026-09-29" }), ctxAt()).profile;
  assert.equal(p.streak, 4);
  assert.equal(p.lastPlayDate, "2026-09-29");
  assert.equal(p.quests.date, "2026-10-01");
});

test("displayed streak: alive today or yesterday, bridged by freezes, otherwise 0 without any blame", () => {
  const P = (o) => Object.assign(fresh(), o);
  assert.deepEqual(game.streakStatus(fresh(), "2026-10-01"), { streak: 0, alive: false, playedToday: false, freezesNeeded: 0 });
  assert.equal(game.streakStatus(P({ streak: 4, lastPlayDate: "2026-10-01" }), "2026-10-01").playedToday, true);
  assert.equal(game.streakStatus(P({ streak: 4, lastPlayDate: "2026-09-30" }), "2026-10-01").streak, 4);
  assert.equal(game.streakStatus(P({ streak: 4, lastPlayDate: "2026-09-28" }), "2026-10-01").streak, 0);
  const bridged = game.streakStatus(P({ streak: 4, lastPlayDate: "2026-09-28", freezeTokens: 2 }), "2026-10-01");
  assert.equal(bridged.streak, 4);
  assert.equal(bridged.freezesNeeded, 2);
});

test("quests re-roll on a new day", () => {
  const a = game.rollover(fresh(), ctxAt("2026-10-01T08:00:00")).profile;
  assert.equal(a.quests.date, "2026-10-01");
  const b = game.rollover(a, ctxAt("2026-10-02T08:00:00")).profile;
  assert.equal(b.quests.date, "2026-10-02");
  assert.deepEqual(b.quests.progress, {});
  assert.equal(b.quests.bonusGranted, false);
  assert.equal(game.questView(b, "2026-10-02").length, 3);
});

// -- loot ---------------------------------------------------------------------------------------
const RATES = { common: 0.6, rare: 0.28, epic: 0.1, legendary: 0.02 };
const fullPool = () => {
  const cards = [];
  for (const r of Object.keys(RATES)) for (let i = 0; i < 12; i++) cards.push({ id: `${r}-${i}`, rarity: r, kind: "tip" });
  return cards;
};

test("20000 chests match the published drop rates within 1.5 points", () => {
  const rng = mulberry32(2026);
  const cards = fullPool();
  const counts = { common: 0, rare: 0, epic: 0, legendary: 0 };
  let pity = 0;
  const n = 20000;
  for (let i = 0; i < n; i++) {
    const res = game.drawChest({ cards, rates: RATES, pityAfter: 8, owned: [], pity }, rng);
    counts[res.rarity] += 1;
    pity = res.pity;
  }
  for (const r of Object.keys(RATES)) near(counts[r] / n, RATES[r], 0.015, `${r} rate`);
});

test("pity timer: never more than 8 chests in a row without a rare or better", () => {
  for (const seed of [1, 2, 3, 4, 5]) {
    const rng = mulberry32(seed);
    const cards = fullPool();
    let pity = 0, run = 0, longest = 0, forced = 0;
    for (let i = 0; i < 20000; i++) {
      const res = game.drawChest({ cards, rates: RATES, pityAfter: 8, owned: [], pity }, rng);
      if (res.guaranteed) { forced += 1; assert.notEqual(res.rarity, "common", "a guaranteed chest is rare or better"); assert.equal(res.pityBefore, 8); }
      run = res.rarity === "common" ? run + 1 : 0;
      longest = Math.max(longest, run);
      pity = res.pity;
    }
    assert.ok(longest <= 8, `seed ${seed}: ${longest} commons in a row`);
    assert.ok(forced > 0, "the guarantee does trigger now and then");
  }
});

test("pity guarantee holds even with the unluckiest random source", () => {
  const cards = fullPool();
  let pity = 0;
  const seq = [];
  for (let i = 0; i < 27; i++) {
    const res = game.drawChest({ cards, rates: RATES, pityAfter: 8, owned: [], pity }, () => 0);
    seq.push(res.rarity);
    pity = res.pity;
  }
  assert.deepEqual(seq.slice(0, 9), ["common", "common", "common", "common", "common", "common", "common", "common", "rare"]);
  assert.deepEqual(seq.slice(9, 18), seq.slice(0, 9));
  const highRng = game.drawChest({ cards, rates: RATES, pityAfter: 8, owned: [], pity: 8 }, () => 0.999999);
  assert.equal(highRng.rarity, "legendary");
  assert.equal(highRng.pity, 0);
});

test("chests prefer cards you do not own yet, duplicates become 5 XP dust", () => {
  const cards = fullPool().filter((c) => c.rarity === "common");
  const rng = mulberry32(8);
  const owned = [];
  let pity = 0;
  for (let i = 0; i < 12; i++) {
    const res = game.drawChest({ cards, rates: { common: 1 }, pityAfter: 8, owned, pity }, rng);
    assert.equal(res.duplicate, false, `draw ${i} should be new`);
    assert.ok(!owned.includes(res.card.id));
    owned.push(res.card.id);
    pity = res.pity;
  }
  const dup = game.drawChest({ cards, rates: { common: 1 }, pityAfter: 8, owned, pity }, rng);
  assert.equal(dup.duplicate, true);
  assert.equal(dup.dust, 5);
});

test("an edition without epic or legendary cards still always yields a card", () => {
  const cards = bundle.loot.cards.filter((c) => c.rarity === "common" || c.rarity === "rare");
  assert.ok(cards.some((c) => c.rarity === "common") && cards.some((c) => c.rarity === "rare"));
  const rng = mulberry32(4);
  let pity = 0, longest = 0, run = 0;
  const seen = new Set();
  for (let i = 0; i < 3000; i++) {
    const res = game.drawChest({ cards, rates: bundle.loot.rates, pityAfter: bundle.loot.pity_after, owned: [], pity }, rng);
    assert.ok(res && res.card);
    seen.add(res.rarity);
    run = res.rarity === "common" ? run + 1 : 0;
    longest = Math.max(longest, run);
    pity = res.pity;
  }
  assert.deepEqual([...seen].sort(), ["common", "rare"]);
  assert.ok(longest <= bundle.loot.pity_after);
  assert.equal(game.drawChest({ cards: [], rates: RATES, pityAfter: 8, owned: [], pity: 0 }, rng), null);
});

test("the shipped edition yields every rarity it has cards for, and the pity timer still holds", () => {
  const cards = bundle.loot.cards;
  const rng = mulberry32(11);
  const seen = new Set();
  let pity = 0, run = 0, longest = 0;
  for (let i = 0; i < 4000; i++) {
    const res = game.drawChest({ cards, rates: bundle.loot.rates, pityAfter: bundle.loot.pity_after, owned: [], pity }, rng);
    seen.add(res.rarity);
    run = res.rarity === "common" ? run + 1 : 0;
    longest = Math.max(longest, run);
    pity = res.pity;
  }
  assert.deepEqual([...seen].sort(), [...new Set(cards.map((c) => c.rarity))].sort());
  assert.ok(longest <= bundle.loot.pity_after, `${longest} commons in a row, pity after ${bundle.loot.pity_after}`);
});

test("openChest updates the profile: inventory, deck, pity, dust XP", () => {
  const loot = { cards: fullPool(), rates: RATES, pity_after: 8 };
  let p = fresh();
  assert.equal(p.chestsReady, 1);
  const r = game.openChest(p, loot, ctxAt("2026-10-01T12:00:00", 5));
  assert.equal(r.ok, true);
  assert.equal(r.profile.chestsReady, 0);
  assert.equal(r.profile.stats.chests, 1);
  assert.equal(r.profile.deck.length, 1);
  assert.equal(r.profile.deck[0], r.card.id);
  assert.equal(r.profile.pity, r.rarity === "common" ? 1 : 0);
  const none = game.openChest(r.profile, loot, ctxAt());
  assert.equal(none.ok, false);
  assert.equal(none.reason, "no_chest");
  assert.equal(game.openChest(fresh(), { cards: [], rates: RATES }, ctxAt()).reason, "no_cards");
  // determinism with the same injected random source
  const again = game.openChest(fresh(), loot, ctxAt("2026-10-01T12:00:00", 5));
  assert.equal(again.card.id, r.card.id);
  // duplicates give dust
  const only = { cards: [{ id: "x", rarity: "common" }], rates: { common: 1 }, pity_after: 8 };
  let q = game.openChest(Object.assign(fresh(), { chestsReady: 3 }), only, ctxAt());
  assert.equal(q.duplicate, false);
  q = game.openChest(q.profile, only, ctxAt());
  assert.equal(q.duplicate, true);
  assert.equal(q.profile.xp, 5);
  assert.equal(q.profile.deck.length, 1);
});

test("ten cards unlock Scientist", () => {
  const cards = fullPool();
  let p = Object.assign(fresh(), { chestsReady: 20 });
  const rng = mulberry32(31);
  let unlocked = false;
  for (let i = 0; i < 12; i++) {
    const r = game.openChest(p, { cards, rates: RATES, pity_after: 8 }, { now: () => new Date("2026-10-01T10:00:00"), rng });
    p = r.profile;
    if (r.events.some((e) => e.id === "scientist")) unlocked = true;
  }
  assert.equal(unlocked, true);
});

// -- achievements -------------------------------------------------------------------------------
test("12 achievements with English and Czech names and descriptions", () => {
  assert.equal(game.ACHIEVEMENTS.length, 12);
  const ids = game.ACHIEVEMENTS.map((a) => a.id);
  assert.equal(new Set(ids).size, 12);
  for (const id of ["first_blood", "calibrated", "upset_hunter", "honest_hook", "boss_slayer", "scientist", "streak_7", "dont_peek", "myth_buster", "polyglot", "level_5", "level_10"]) assert.ok(ids.includes(id), id);
  game.ACHIEVEMENTS.forEach((a) => {
    for (const lang of ["en", "cs"]) { assert.ok(a.name[lang] && a.name[lang].trim(), `${a.id} name ${lang}`); assert.ok(a.desc[lang] && a.desc[lang].trim(), `${a.id} desc ${lang}`); }
    assert.equal(typeof a.test, "function");
  });
  assert.equal(game.achievementById("polyglot").id, "polyglot");
  assert.equal(game.achievementById("nope"), null);
});

test("achievement conditions", () => {
  const A = (id) => game.achievementById(id).test;
  const p = fresh();
  assert.equal(A("first_blood")(p), false);
  assert.equal(A("first_blood")(Object.assign(game.clone(p), { stats: Object.assign({}, p.stats, { arenaCorrect: 1 }) })), true);
  const cal = (n, sum) => Object.assign(game.clone(p), { brier: { n, sum } });
  assert.equal(A("calibrated")(cal(19, 0)), false, "needs 20 answers");
  assert.equal(A("calibrated")(cal(20, 0)), true);
  assert.equal(A("calibrated")(cal(20, 20 * 0.0749)), true, "oracle just above 70");
  assert.equal(A("calibrated")(cal(20, 20 * 0.0751)), false, "oracle just below 70");
  assert.equal(A("level_5")(Object.assign(game.clone(p), { level: 5 })), true);
  assert.equal(A("level_10")(Object.assign(game.clone(p), { level: 9 })), false);
  assert.equal(A("myth_buster")(Object.assign(game.clone(p), { stats: Object.assign({}, p.stats, { mythsCorrect: 10 }) })), true);
  assert.equal(A("streak_7")(Object.assign(game.clone(p), { bestStreak: 7 })), true);
});

test("reaching level 5 through XP unlocks the achievement and reports the level up", () => {
  const p = Object.assign(fresh(), { xp: 790, level: 4 });
  const r = game.answerDuel(p, { duel: duel(), pick: "a" }, ctxAt());
  assert.equal(r.profile.level, 5);
  assert.ok(r.events.some((e) => e.type === "levelUp" && e.from === 4 && e.to === 5));
  assert.ok(r.events.some((e) => e.type === "achievement" && e.id === "level_5"));
});

// -- wellbeing ----------------------------------------------------------------------------------
test("session break card appears once after the configured minutes", () => {
  assert.equal(game.shouldShowBreak({ activeSeconds: 19 * 60, limitMinutes: 20, alreadyShown: false }), false);
  assert.equal(game.shouldShowBreak({ activeSeconds: 20 * 60, limitMinutes: 20, alreadyShown: false }), true);
  assert.equal(game.shouldShowBreak({ activeSeconds: 60 * 60, limitMinutes: 20, alreadyShown: true }), false, "once per session");
  assert.equal(game.shouldShowBreak({ activeSeconds: 60 * 60, limitMinutes: 0, alreadyShown: false }), false, "0 disables it");
  assert.equal(game.shouldShowBreak({ activeSeconds: 20 * 60, alreadyShown: false }), true, "default is 20 minutes");
  let p = game.addPlayTime(fresh(), 90, "2026-10-01");
  p = game.addPlayTime(p, 45, "2026-10-01");
  assert.equal(game.playMinutesToday(p, "2026-10-01"), 2);
  assert.equal(game.playMinutesToday(p, "2026-10-02"), 0);
  p = game.addPlayTime(p, 30, "2026-10-02");
  assert.equal(p.playTime.seconds, 30);
});

test("next best action", () => {
  const p = fresh();
  assert.equal(game.nextBestAction(p, "2026-10-01").key, "chest", "the welcome chest comes first");
  const open = Object.assign(game.clone(p), { chestsReady: 0 });
  assert.equal(game.nextBestAction(open, "2026-10-01").key, "quest");
  const allDone = forceQuests(open, ["arena_wins", "hard_duel", "upset_call"]);
  allDone.quests.done = { arena_wins: true, hard_duel: true, upset_call: true };
  assert.equal(game.nextBestAction(allDone, "2026-10-01").key, "oracle");
  allDone.brier = { sum: 0, n: 12 };
  assert.equal(game.nextBestAction(allDone, "2026-10-01").key, "boss");
});

test("actions never mutate their input profile", () => {
  const p = fresh();
  const snapshot = JSON.stringify(p);
  game.answerDuel(p, { duel: duel(), pick: "a", confidence: 90 }, ctxAt());
  game.applyBoss(p, { boss, resolution: { won: true, risk: 0 }, lang: "en" }, ctxAt());
  game.applyLabDecision(p, { correct: true }, ctxAt());
  game.openChest(p, { cards: fullPool(), rates: RATES }, ctxAt());
  assert.equal(JSON.stringify(p), snapshot);
});

test("system random source stays in [0, 1)", () => {
  const rng = game.systemRng();
  for (let i = 0; i < 1000; i++) { const x = rng(); assert.ok(x >= 0 && x < 1); }
});
