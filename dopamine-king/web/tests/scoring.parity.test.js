"use strict";
// Parity of the JavaScript scorer with the Python engine: replays every golden case.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const scoring = require("../src/scoring.js");

const ROOT = path.resolve(__dirname, "..", "..");
const spec = JSON.parse(fs.readFileSync(path.join(ROOT, "src", "dopamine_king", "data", "scoring_spec.json"), "utf8"));
const golden = JSON.parse(fs.readFileSync(path.join(__dirname, "golden.json"), "utf8"));

const REL_TOL = 1e-9;
// Discrete values (counts, flags, token and character positions) must match exactly.
const DISCRETE = /^(hits\.|features\.(n_words|has_number|starts_with_number|is_question|open_loop|exclaim|\w+_hits)$|spans\[\d+\]\.(tok_start|tok_end|start|end)$)/;
const hasAstral = (s) => /[\u{10000}-\u{10FFFF}]/u.test(s);

function closeTo(actual, expected, where, label) {
  const msg = `${label} ${where}`;
  if (typeof expected !== "number") return assert.strictEqual(actual, expected, msg);
  assert.equal(typeof actual, "number", `${msg}: expected a number`);
  if (DISCRETE.test(where)) return assert.strictEqual(actual, expected, msg);
  const tol = REL_TOL * Math.max(1, Math.abs(expected));
  assert.ok(Math.abs(actual - expected) <= tol, `${msg}: ${actual} vs ${expected} (tol ${tol})`);
}

// where is the path inside the result ("spans[0].start"), label names the golden case.
function compare(actual, expected, where, skipOffsets, label) {
  if (Array.isArray(expected)) {
    assert.ok(Array.isArray(actual), `${label} ${where}: expected an array`);
    assert.equal(actual.length, expected.length, `${label} ${where}: length`);
    expected.forEach((e, i) => compare(actual[i], e, `${where}[${i}]`, skipOffsets, label));
  } else if (expected !== null && typeof expected === "object") {
    assert.ok(actual && typeof actual === "object", `${label} ${where}: expected an object`);
    assert.deepEqual(Object.keys(actual).sort(), Object.keys(expected).sort(), `${label} ${where}: keys`);
    for (const k of Object.keys(expected)) {
      const w = where ? `${where}.${k}` : k;
      if (skipOffsets && /^spans\[\d+\]\.(start|end)$/.test(w)) continue;
      compare(actual[k], expected[k], w, skipOffsets, label);
    }
  } else {
    closeTo(actual, expected, where, label);
  }
}

test("golden file has the expected shape", () => {
  assert.ok(Array.isArray(golden));
  assert.ok(golden.length >= 100, `only ${golden.length} golden cases`);
});

test("all golden cases match the Python scorer", () => {
  let checked = 0;
  golden.forEach((c, idx) => {
    const got = scoring.scoreHook(c.text, c.body || "", { lang: c.lang || undefined, weights: c.weights || undefined, spec });
    // Offsets are UTF-16 units in JavaScript and code points in Python: compare them for BMP-only text.
    compare(got, c.expected, "", hasAstral(c.text), `case${idx}(${JSON.stringify(c.text).slice(0, 40)})`);
    checked += 1;
  });
  assert.equal(checked, golden.length);
});

test("every golden case individually (names in the report)", async (t) => {
  for (const [idx, c] of golden.entries()) {
    await t.test(`#${idx} ${JSON.stringify(c.text).slice(0, 48)}`, () => {
      const got = scoring.scoreHook(c.text, c.body || "", { lang: c.lang || undefined, weights: c.weights || undefined, spec });
      compare(got, c.expected, "", hasAstral(c.text), `#${idx}`);
    });
  }
});

test("default spec registration works like passing the spec", () => {
  scoring.setDefaultSpec(spec);
  const a = scoring.scoreHook("Why most marketing dashboards lie to you");
  const b = scoring.scoreHook("Why most marketing dashboards lie to you", "", { spec });
  assert.deepEqual(a, b);
  scoring.setDefaultSpec(null);
  assert.throws(() => scoring.scoreHook("hello"), /spec not loaded/);
});

test("result carries the same keys as HookScore.to_dict", () => {
  const r = scoring.scoreHook("7 mistakes every beginner runner makes", "", { spec });
  assert.deepEqual(Object.keys(r).sort(), ["clickbait_risk", "features", "hits", "lang", "parts", "raw", "spans", "text", "tips", "total"]);
  assert.deepEqual(Object.keys(r.parts), ["curiosity", "surprise", "emotion", "relevance", "utility", "fluency"]);
  assert.deepEqual(Object.keys(r.features), scoring.FEATURE_NAMES);
});
