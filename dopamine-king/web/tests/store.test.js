"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");

const game = require("../src/game.js");
const { createStore, memoryStorage, parseExport } = require("../src/store.js");

const NOW = () => new Date("2026-10-01T12:00:00");
const duel = { id: "p1", difficulty: "easy", winner: "a", upset: false };

function fakeStorage(initial = {}) {
  const data = Object.assign({}, initial);
  return {
    data,
    getItem: (k) => (k in data ? data[k] : null),
    setItem: (k, v) => { data[k] = String(v); },
    removeItem: (k) => { delete data[k]; }
  };
}

const throwing = () => ({
  getItem() { throw new Error("SecurityError: storage is blocked"); },
  setItem() { throw new Error("QuotaExceededError"); },
  removeItem() { throw new Error("blocked"); }
});

test("profile is persisted under dk.profile.v1", () => {
  const storage = fakeStorage();
  const store = createStore({ storage, now: NOW, lang: "cs" });
  assert.equal(game.PROFILE_KEY, "dk.profile.v1");
  assert.equal(store.get().settings.lang, "cs");
  store.update((p) => game.answerDuel(p, { duel, pick: "a" }, { now: NOW }));
  assert.ok(storage.data["dk.profile.v1"], "written under the documented key");
  assert.equal(JSON.parse(storage.data["dk.profile.v1"]).xp >= 10, true);
  const reopened = createStore({ storage, now: NOW });
  assert.equal(reopened.get().xp, store.get().xp);
  assert.equal(reopened.get().stats.arenaCorrect, 1);
  assert.equal(reopened.usingFallback(), false);
});

test("works with an in-memory fallback when storage throws", () => {
  const store = createStore({ storage: throwing(), now: NOW });
  assert.equal(store.usingFallback(), true);
  assert.ok(store.get().xp === 0);
  store.update((p) => game.answerDuel(p, { duel, pick: "a" }, { now: NOW }));
  assert.ok(store.get().xp >= 10, "progress is kept in memory");
  store.update((p) => Object.assign({}, p, { name: "Ada" }));
  assert.equal(store.get().name, "Ada");
});

test("works when storage is missing entirely", () => {
  const store = createStore({ storage: null, now: NOW });
  assert.equal(store.usingFallback(), true);
  store.set(Object.assign({}, store.get(), { xp: 120 }));
  assert.equal(store.get().xp, 120);
  assert.equal(store.get().level, 2);
});

test("a write error later switches to memory without losing the profile", () => {
  let fail = false;
  const inner = fakeStorage();
  const storage = {
    getItem: (k) => inner.getItem(k),
    setItem: (k, v) => { if (fail) throw new Error("QuotaExceededError"); inner.setItem(k, v); },
    removeItem: (k) => inner.removeItem(k)
  };
  const store = createStore({ storage, now: NOW });
  store.update((p) => Object.assign({}, p, { xp: 50 }));
  assert.equal(store.usingFallback(), false);
  fail = true;
  store.update((p) => Object.assign({}, p, { xp: 75 }));
  assert.equal(store.usingFallback(), true);
  assert.equal(store.get().xp, 75);
});

test("corrupt stored data falls back to a fresh profile", () => {
  for (const bad of ["{not json", "[]", "42", "null", "\"x\""]) {
    const store = createStore({ storage: fakeStorage({ "dk.profile.v1": bad }), now: NOW });
    assert.equal(store.get().xp, 0, bad);
    assert.equal(store.get().version, game.PROFILE_VERSION);
  }
});

test("stored values are repaired on load", () => {
  const storage = fakeStorage({ "dk.profile.v1": JSON.stringify({ xp: 305, freezeTokens: 7, settings: { sessionMinutes: 30 } }) });
  const store = createStore({ storage, now: NOW });
  assert.equal(store.get().level, 3);
  assert.equal(store.get().freezeTokens, 2);
  assert.equal(store.get().settings.sessionMinutes, 30);
});

test("subscribers are notified and can unsubscribe", () => {
  const store = createStore({ storage: memoryStorage(), now: NOW });
  const seen = [];
  const off = store.subscribe((p) => seen.push(p.xp));
  store.update((p) => Object.assign({}, p, { xp: 10 }));
  store.update((p) => Object.assign({}, p, { xp: 20 }));
  off();
  store.update((p) => Object.assign({}, p, { xp: 30 }));
  assert.deepEqual(seen, [10, 20]);
  store.subscribe(() => { throw new Error("bad listener"); });
  store.update((p) => Object.assign({}, p, { xp: 40 }));
  assert.equal(store.get().xp, 40, "a failing listener does not break the store");
});

test("silent updates persist without notifying (play time ticks)", () => {
  const storage = fakeStorage();
  const store = createStore({ storage, now: NOW });
  let calls = 0;
  store.subscribe(() => { calls += 1; });
  store.update((p) => game.addPlayTime(p, 30, "2026-10-01"), { silent: true });
  assert.equal(calls, 0);
  assert.equal(JSON.parse(storage.data["dk.profile.v1"]).playTime.seconds, 30);
  store.update((p) => p);
  assert.equal(calls, 1);
});

test("export and import round trip as JSON", () => {
  const a = createStore({ storage: memoryStorage(), now: NOW });
  a.update((p) => game.answerDuel(p, { duel, pick: "a", confidence: 90 }, { now: NOW }));
  a.update((p) => Object.assign({}, p, { name: "Eliska" }));
  const text = a.exportJSON();
  const parsed = JSON.parse(text);
  assert.equal(parsed.app, "dopamine-king");
  assert.equal(parsed.profile.name, "Eliska");
  const b = createStore({ storage: memoryStorage(), now: NOW });
  b.importJSON(text);
  assert.deepEqual(b.get(), a.get());
  // a bare profile object is accepted too
  const c = createStore({ storage: memoryStorage(), now: NOW });
  c.importJSON(JSON.stringify(a.get()));
  assert.equal(c.get().xp, a.get().xp);
});

test("import validates its input", () => {
  const code = (text) => { try { parseExport(text); return "ok"; } catch (e) { return e.code; } };
  assert.equal(code(""), "empty");
  assert.equal(code("   "), "empty");
  assert.equal(code("{oops"), "invalid_json");
  assert.equal(code("[1,2]"), "invalid_profile");
  assert.equal(code(JSON.stringify({ app: "other-app", profile: { xp: 1 } })), "wrong_app");
  assert.equal(code(JSON.stringify({ app: "dopamine-king", profile: { nope: 1 } })), "invalid_profile");
  assert.equal(code("x".repeat(1000001)), "too_large");
  assert.equal(code(JSON.stringify({ app: "dopamine-king", profile: { xp: 10 } })), "ok");
  const store = createStore({ storage: memoryStorage(), now: NOW });
  assert.throws(() => store.importJSON("{oops"), (e) => e.name === "ImportError" && e.code === "invalid_json");
  assert.equal(store.get().xp, 0, "a failed import leaves the profile alone");
  const hostile = JSON.stringify({ app: "dopamine-king", profile: { xp: -5, level: 99, stats: { arenaPlayed: -3 }, evil: "<script>" } });
  store.importJSON(hostile);
  assert.equal(store.get().xp, 0);
  assert.equal(store.get().stats.arenaPlayed, 0);
  assert.equal("evil" in store.get(), false);
});

test("reset starts over but keeps the settings", () => {
  const store = createStore({ storage: memoryStorage(), now: NOW });
  store.update((p) => Object.assign({}, p, { xp: 500, settings: Object.assign({}, p.settings, { lang: "cs", theme: "light" }) }));
  const after = store.reset();
  assert.equal(after.xp, 0);
  assert.equal(after.settings.lang, "cs");
  assert.equal(after.settings.theme, "light");
});
