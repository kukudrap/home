"use strict";
// The rules added for the real edition: duel kinds, tasks that pay once, real A/B tests, and the achievements that follow.
// The numbers come from the shipped bundle (web/dev/bundle.json), the real edition computed from the stored searches.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const game = require("../src/game.js");
const { mulberry32 } = require("../src/labstats.js");

const bundle = JSON.parse(fs.readFileSync(path.resolve(__dirname, "..", "dev", "bundle.json"), "utf8"));

const ctxAt = (iso = "2026-10-01T12:00:00", seed = 1) => ({ now: () => new Date(iso), rng: mulberry32(seed) });
const fresh = () => game.defaultProfile({ lang: "cs", today: "2026-10-01" });
/** A profile whose quests cannot be finished by the actions under test, so XP assertions stay exact. */
const quiet = () => {
  const p = fresh();
  p.quests = { date: "2026-10-01", ids: ["boss_win", "lab_run", "vault_open"], progress: {}, done: {}, bonusGranted: false };
  return p;
};
const withQuests = (ids) => {
  const p = fresh();
  p.quests = { date: "2026-10-01", ids, progress: {}, done: {}, bonusGranted: false };
  return p;
};
const firstOf = (kind) => bundle.arena.find((d) => d.kind === kind);
const wrongPick = (d) => (d.winner === "a" ? "b" : "a");

// -- duel kinds ---------------------------------------------------------------------------------
test("the duel kinds of the game are the three real ones and the old hook duel", () => {
  assert.deepEqual(game.DUEL_KINDS, ["hook", "rank", "reach", "claim"]);
  for (const d of bundle.arena) assert.ok(game.DUEL_KINDS.includes(d.kind), d.id);
});

test("pickDuel can be limited to one kind, and a duel without a kind counts as a hook duel", () => {
  for (const kind of ["rank", "reach", "claim"]) {
    for (let i = 0; i < 15; i++) assert.equal(game.pickDuel(bundle.arena, { kind, rng: mulberry32(i) }).duel.kind, kind);
  }
  assert.equal(game.pickDuel(bundle.arena, { kind: "hook", rng: mulberry32(1) }).duel, null, "the real edition has no simulated hook duels");
  const legacy = [{ id: "h1", difficulty: "easy", winner: "a", lang: "en" }];
  assert.equal(game.pickDuel(legacy, { kind: "hook" }).duel.id, "h1");
  assert.equal(game.pickDuel(legacy, { kind: "rank" }).duel, null);
  assert.ok(game.pickDuel(bundle.arena, { kind: "all", rng: mulberry32(2) }).duel);
  const hard = game.pickDuel(bundle.arena, { kind: "claim", difficulty: "hard", rng: mulberry32(3) }).duel;
  assert.deepEqual([hard.kind, hard.difficulty], ["claim", "hard"], "both filters apply together");
});

test("every answer is counted in its kind, right or wrong", () => {
  const rank = firstOf("rank");
  const right = game.answerDuel(quiet(), { duel: rank, pick: rank.winner }, ctxAt());
  assert.equal(right.kind, "rank");
  assert.deepEqual(right.profile.kinds.rank, { played: 1, correct: 1 });
  const wrong = game.answerDuel(right.profile, { duel: rank, pick: wrongPick(rank) }, ctxAt());
  assert.deepEqual(wrong.profile.kinds.rank, { played: 2, correct: 1 });
  assert.equal(wrong.profile.kinds.claim, undefined, "other kinds stay untouched");
  const old = game.answerDuel(quiet(), { duel: { id: "h", difficulty: "easy", winner: "a", upset: false, lang: "en" }, pick: "a" }, ctxAt());
  assert.equal(old.kind, "hook");
  assert.deepEqual(old.profile.kinds.hook, { played: 1, correct: 1 });
});

test("three claims duels called right finish the claims quest, a wrong call does not move it", () => {
  let p = withQuests(["claim_duels", "boss_win", "lab_run"]);
  const claims = bundle.arena.filter((d) => d.kind === "claim").slice(0, 4);
  const miss = game.answerDuel(p, { duel: claims[0], pick: wrongPick(claims[0]) }, ctxAt());
  assert.equal(miss.profile.quests.progress.claim_duels, undefined);
  p = miss.profile;
  let paid = 0;
  for (const d of claims.slice(1, 4)) {
    const r = game.answerDuel(p, { duel: d, pick: d.winner }, ctxAt());
    p = r.profile;
    paid += r.events.filter((e) => e.type === "quest").length;
  }
  assert.equal(p.quests.progress.claim_duels, 3);
  assert.equal(p.quests.done.claim_duels, true);
  assert.equal(paid, 1, "the quest pays once");
  const other = game.answerDuel(withQuests(["claim_duels", "boss_win", "lab_run"]), { duel: firstOf("rank"), pick: firstOf("rank").winner }, ctxAt());
  assert.equal(other.profile.quests.progress.claim_duels, undefined, "a position duel is not a claims duel");
});

// -- tasks --------------------------------------------------------------------------------------
test("the XP of real work is published in one place", () => {
  assert.equal(game.XP.taskDone, 50);
  assert.equal(game.XP.tasksPerChest, 3);
  assert.equal(game.XP.labPlan, 10);
  assert.equal(game.XP.labResult, 40);
  assert.equal(bundle.meta.real.task_xp, game.XP.taskDone, "the data builder and the game agree on what a task pays");
  for (const t of bundle.tasks) assert.equal(t.xp, game.XP.taskDone, t.id);
});

test("a task pays XP the first time it is ticked, ticking off takes nothing away and ticking on again pays nothing", () => {
  const on = game.toggleTask(quiet(), { id: "a1", done: true }, ctxAt());
  assert.deepEqual([on.xp, on.firstTime, on.chest], [50, true, false]);
  assert.equal(on.profile.tasks.a1, "2026-10-01");
  assert.equal(on.profile.stats.tasksDone, 1);
  assert.equal(on.profile.xp, 50);
  const off = game.toggleTask(on.profile, { id: "a1", done: false }, ctxAt("2026-10-02T09:00:00"));
  assert.equal(off.profile.tasks.a1, undefined);
  assert.equal(off.profile.xp, 50, "the XP stays");
  assert.deepEqual(off.profile.tasksPaid, ["a1"]);
  const again = game.toggleTask(off.profile, { id: "a1", done: true }, ctxAt("2026-10-03T09:00:00"));
  assert.deepEqual([again.xp, again.firstTime], [0, false]);
  assert.equal(again.profile.xp, 50);
  assert.equal(again.profile.stats.tasksDone, 1, "one task counts once");
  assert.equal(again.profile.tasks.a1, "2026-10-03", "the date of the latest tick is kept");
  const custom = game.toggleTask(quiet(), { id: "x", done: true, xp: 20 }, ctxAt());
  assert.equal(custom.xp, 20);
  const untouched = game.toggleTask(quiet(), { id: "never", done: false }, ctxAt());
  assert.equal(untouched.profile.xp, 0);
});

test("every third finished task opens a chest", () => {
  let p = quiet();
  const before = p.chestsReady;
  const chests = [];
  for (const id of ["a1", "a2", "a3", "a4", "a5", "a6"]) {
    const r = game.toggleTask(p, { id, done: true }, ctxAt());
    p = r.profile;
    chests.push(r.chest);
    if (r.chest) assert.ok(r.events.some((e) => e.type === "taskChest"));
  }
  assert.deepEqual(chests, [false, false, true, false, false, true]);
  assert.equal(p.chestsReady, before + 2);
  assert.equal(p.stats.tasksDone, 6);
});

test("finishing a task moves the task quest, and three tasks unlock the achievement", () => {
  let p = withQuests(["task_done", "boss_win", "lab_run"]);
  const r = game.toggleTask(p, { id: "a1", done: true }, ctxAt());
  assert.ok(r.events.some((e) => e.type === "quest" && e.id === "task_done"));
  p = r.profile;
  assert.equal(game.achievementById("real_work").test(p), false);
  p = game.toggleTask(game.toggleTask(p, { id: "a2", done: true }, ctxAt()).profile, { id: "a3", done: true }, ctxAt()).profile;
  assert.equal(game.achievementById("real_work").test(p), true);
  assert.ok(p.achievements.includes("real_work"));
});

// -- real A/B tests -----------------------------------------------------------------------------
test("planning a real test pays once, correcting the plan pays nothing", () => {
  const plan = game.planLabTest(quiet(), { id: "t1", baseline: 0.05, lift: 0.2, nPerArm: 8000 }, ctxAt());
  assert.deepEqual([plan.xp, plan.firstTime], [10, true]);
  assert.deepEqual(plan.profile.labTests.t1, { plan: { baseline: 0.05, lift: 0.2, nPerArm: 8000 }, result: null });
  const again = game.planLabTest(plan.profile, { id: "t1", baseline: 0.04, lift: 0.25, nPerArm: 6000 }, ctxAt());
  assert.deepEqual([again.xp, again.firstTime], [0, false]);
  assert.equal(again.profile.labTests.t1.plan.nPerArm, 6000);
  assert.equal(again.profile.xp, 10);
});

test("the real numbers of a test pay once, are kept with their date and unlock the achievement", () => {
  const planned = game.planLabTest(quiet(), { id: "t1", baseline: 0.05, lift: 0.2, nPerArm: 8000 }, ctxAt()).profile;
  assert.equal(game.achievementById("real_test").test(planned), false);
  const res = game.recordLabResult(planned, { id: "t1", nA: 5000, xA: 250, nB: 5000, xB: 300 }, ctxAt("2026-10-05T10:00:00"));
  assert.deepEqual([res.xp, res.firstTime], [40, true]);
  assert.deepEqual(res.profile.labTests.t1.result, { nA: 5000, xA: 250, nB: 5000, xB: 300, date: "2026-10-05" });
  assert.deepEqual(res.profile.labTests.t1.plan, planned.labTests.t1.plan, "the plan stays");
  assert.equal(res.profile.stats.labResults, 1);
  assert.ok(res.events.some((e) => e.type === "achievement" && e.id === "real_test"));
  const fix = game.recordLabResult(res.profile, { id: "t1", nA: 5000, xA: 251, nB: 5000, xB: 300 }, ctxAt("2026-10-06T10:00:00"));
  assert.deepEqual([fix.xp, fix.firstTime], [0, false]);
  assert.equal(fix.profile.labTests.t1.result.xA, 251);
  assert.equal(fix.profile.stats.labResults, 1, "one test counts once");
  const direct = game.recordLabResult(quiet(), { id: "t2", nA: 100, xA: 5, nB: 100, xB: 9 }, ctxAt());
  assert.equal(direct.profile.labTests.t2.plan, null, "a result can be entered without a plan");
});

// -- achievements -------------------------------------------------------------------------------
test("the achievements of the real edition follow the counts they promise", () => {
  const p = fresh();
  const at = (patch) => Object.assign(game.clone(p), patch);
  const claim = (correct) => at({ kinds: { claim: { played: correct + 2, correct } } });
  assert.equal(game.achievementById("rule_reader").test(claim(9)), false);
  assert.equal(game.achievementById("rule_reader").test(claim(10)), true);
  const market = (rank, reach) => at({ kinds: { rank: { played: 20, correct: rank }, reach: { played: 20, correct: reach } } });
  assert.equal(game.achievementById("market_scout").test(market(6, 3)), false);
  assert.equal(game.achievementById("market_scout").test(market(6, 4)), true, "position and appearance duels add up");
  assert.equal(game.achievementById("market_scout").test(at({ kinds: { claim: { played: 30, correct: 30 } } })), false, "claims duels do not count here");
});

// -- profile ------------------------------------------------------------------------------------
test("the profile keeps tasks, tests and kinds in a clean shape when it is loaded", () => {
  const raw = JSON.parse(JSON.stringify(fresh()));
  raw.tasks = { a1: "2026-10-01", a2: "yesterday", a3: 5 };
  raw.tasksPaid = ["a1", 3, "a2"];
  raw.labTests = {
    t1: { plan: { baseline: 0.05, lift: 0.2, nPerArm: 100 }, result: { nA: 10, xA: 99, nB: 10, xB: 2, date: "later" } },
    t2: "nonsense",
    t3: { plan: { baseline: -1, lift: 0, nPerArm: 0 }, result: null },
    t4: { plan: null, result: { nA: 0, xA: 1, nB: 5, xB: 1 } }
  };
  raw.kinds = { claim: { played: 4, correct: 9 }, rank: { played: 0, correct: 0 }, bogus: { played: 1, correct: 1 } };
  raw.stats = Object.assign({}, raw.stats, { tasksDone: 2.7, labResults: -4 });
  const p = game.normalizeProfile(raw);
  assert.deepEqual(Object.keys(p.tasks), ["a1"]);
  assert.deepEqual(p.tasksPaid, ["a1", "a2"].filter((x) => p.tasksPaid.includes(x)), "only text ids survive");
  assert.ok(!p.tasksPaid.includes(3));
  assert.deepEqual(Object.keys(p.labTests), ["t1"]);
  assert.deepEqual(p.labTests.t1.result, { nA: 10, xA: 10, nB: 10, xB: 2, date: null }, "conversions are capped at the visitors, a bad date is dropped");
  assert.deepEqual(p.kinds, { claim: { played: 4, correct: 4 } });
  assert.equal(p.stats.tasksDone, 2);
  assert.equal(p.stats.labResults, 0);
  const empty = game.normalizeProfile({});
  assert.deepEqual([empty.tasks, empty.tasksPaid, empty.labTests, empty.kinds], [{}, [], {}, {}]);
});
