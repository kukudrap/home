"use strict";
// Edge cases and display helpers of the scorer that the golden file does not name: the year rule, numbers with
// decimals, hostile input, and the pieces the highlight layer is built from.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const scoring = require("../src/scoring.js");
const { mulberry32 } = require("../src/labstats.js");

const spec = JSON.parse(fs.readFileSync(path.resolve(__dirname, "..", "..", "src", "dopamine_king", "data", "scoring_spec.json"), "utf8"));
const score = (text, lang, body) => scoring.scoreHook(text, body || "", { lang, spec });

test("year-like tokens are not payoff numbers, decimals are numbers but never years", () => {
  assert.equal(score("Best of 2024 for runners", "en").features.has_number, 0, "2024 reads as a year");
  assert.equal(score("2024 trends in running", "en").features.starts_with_number, 0);
  assert.equal(score("5 tips for 2024", "en").features.has_number, 1);
  assert.equal(score("1899 was a long time ago", "en").features.has_number, 1, "outside 1900 to 2100 it is a number");
  assert.equal(score("Back in 2101 we will see", "en").features.has_number, 1);
  assert.equal(score("Now 9.99 only", "en").features.has_number, 1, "a decimal price is a number");
  assert.equal(score("Version 2026.5 is out", "en").features.has_number, 1, "2026.5 is a number, not a year");
  assert.equal(score("Version 1900.0 is out", "en").features.has_number, 1);
  assert.equal(score("Rok 2025 v číslech", "cs").features.has_number, 0);
  assert.equal(score("Cena 12,5 Kč", "cs").features.has_number, 1, "a decimal comma is a number");
});

test("empty, blank and hostile input never throws and stays in range", () => {
  for (const text of ["", "   ", "\n\n", "!!!", "?", "...", "\u0000", "a".repeat(5000), "word ".repeat(2000), "\u{1F600}".repeat(50), "ÁÉÍ ĚŠČ", "<script>alert(1)</script>", "\ud800", "x\u200by"]) {
    const r = score(text);
    for (const k of ["total", "raw", "clickbait_risk"]) assert.ok(Number.isFinite(r[k]), `${JSON.stringify(text).slice(0, 20)} ${k}`);
    assert.ok(r.total >= 0 && r.total <= 100, `total ${r.total}`);
    assert.ok(r.clickbait_risk >= 0 && r.clickbait_risk <= 1, `risk ${r.clickbait_risk}`);
    Object.values(r.parts).forEach((p) => assert.ok(p >= 0 && p <= 100));
  }
  assert.equal(score("").total, 0);
  assert.ok(score("word ".repeat(2000)).features.n_words <= spec.params.max_tokens, "long text is capped");
});

test("random text never breaks the scorer and the score is deterministic", () => {
  const rnd = mulberry32(2026);
  const alphabet = "abcdefghijklmnopqrstuvwxyz ABC 0123456789 .,!?:'\u2019- ěščřžýáíé\n";
  for (let i = 0; i < 400; i++) {
    let text = "";
    const n = Math.floor(rnd() * 120);
    for (let k = 0; k < n; k++) text += alphabet[Math.floor(rnd() * alphabet.length)];
    const a = score(text), b = score(text);
    assert.deepEqual(a, b);
    assert.ok(a.total >= 0 && a.total <= 100 && Number.isFinite(a.total));
    // The pieces the highlight layer draws must tile the text exactly.
    const segs = scoring.segments(a.text, a.spans);
    assert.equal(segs.map((s) => s.text).join(""), a.text, "segments rebuild the text");
    let at = 0;
    for (const s of segs) { assert.equal(s.start, at); at = s.end; assert.ok(s.end > s.start || a.text === ""); }
  }
});

test("language detection and its override", () => {
  assert.equal(score("Proč většina firem ztrácí zákazníky").lang, "cs");
  assert.equal(score("Why most companies lose customers").lang, "en");
  assert.equal(score("Why most companies lose customers", "cs").lang, "cs", "an explicit language wins");
  assert.equal(scoring.detectLang("Jak na to? Návod krok za krokem", spec), "cs");
  assert.equal(scoring.detectLang("", spec), "en");
});

test("a better hook scores higher than a flat one, and clickbait is penalised", () => {
  const flat = score("Our new product update", "en");
  const strong = score("7 mistakes that cost you customers (and how to fix them)", "en");
  assert.ok(strong.total > flat.total + 10, `${strong.total} vs ${flat.total}`);
  assert.ok(strong.parts.utility > flat.parts.utility && strong.parts.curiosity >= flat.parts.curiosity);
  const honest = score("How to cut onboarding time in half: a 3 step checklist", "en");
  const bait = score("You won't believe this SHOCKING secret!!! Doctors hate it!!!", "en");
  assert.ok(bait.clickbait_risk > 0.35 && honest.clickbait_risk < 0.2, `${bait.clickbait_risk} / ${honest.clickbait_risk}`);
  assert.ok(bait.total < bait.raw * 0 + 100 && scoring.shieldState(bait.clickbait_risk) === "broken");
  assert.equal(scoring.shieldState(honest.clickbait_risk), "intact");
  assert.equal(honest.tips.length > 0, true);
  assert.ok(bait.tips.some((t) => t.key === "reduce_clickbait"), "clickbait gets the matching tip");
});

test("the Trust Shield thresholds are 0.2 and 0.35", () => {
  assert.equal(scoring.shieldState(0), "intact");
  assert.equal(scoring.shieldState(0.1999), "intact");
  assert.equal(scoring.shieldState(0.2), "cracked");
  assert.equal(scoring.shieldState(0.3499), "cracked");
  assert.equal(scoring.shieldState(0.35), "broken");
  assert.equal(scoring.shieldState(1), "broken");
});

test("custom weights change the blend and are normalised", () => {
  const text = "Why most dashboards lie to you";
  const base = scoring.scoreHook(text, "", { spec, lang: "en" });
  const onlyCuriosity = scoring.scoreHook(text, "", { spec, lang: "en", weights: { curiosity: 1, surprise: 0, emotion: 0, relevance: 0, utility: 0 } });
  const scaled = scoring.scoreHook(text, "", { spec, lang: "en", weights: { curiosity: 5, surprise: 0, emotion: 0, relevance: 0, utility: 0 } });
  assert.notEqual(base.total, onlyCuriosity.total);
  assert.ok(Math.abs(onlyCuriosity.total - scaled.total) < 1e-9, "only the ratio of the weights matters");
});

test("rankHooks sorts best first and keeps input order for ties", () => {
  const ranked = scoring.rankHooks(["Update", "7 ways to save an hour a day", "Update"], { spec, lang: "en" });
  assert.equal(ranked[0][0], "7 ways to save an hour a day");
  assert.equal(ranked[1][0], "Update");
  assert.equal(ranked.length, 3);
  assert.deepEqual(scoring.rankHooks([], { spec }), []);
});

test("segments carry the category groups the overlay draws", () => {
  const r = score("Why you should stop doing this: 3 proven steps", "en");
  const segs = scoring.segments(r.text, r.spans);
  assert.equal(segs.map((s) => s.text).join(""), r.text);
  const cats = new Set(segs.flatMap((s) => s.cats));
  assert.ok(cats.size >= 2, `expected several categories, got ${[...cats]}`);
  for (const s of segs) if (s.cats.length) assert.ok(s.primary, "a highlighted piece has a primary category");
  assert.equal(scoring.primaryCategory([]), null);
  assert.equal(scoring.primaryCategory(["positive", "clickbait"]), "clickbait", "clickbait outranks the others");
  assert.deepEqual(scoring.segments("", []), []);
  assert.deepEqual(scoring.segments("plain", []).map((s) => [s.text, s.cats.length]), [["plain", 0]]);
});

test("tokenizer keeps decimals, apostrophes and Czech words whole", () => {
  const t = (s) => scoring.tokenize(s).map((x) => x.text);
  assert.deepEqual(t("It's 9.99 now"), ["It's", "9.99", "now"]);
  assert.deepEqual(t("cena 1,5 Kč"), ["cena", "1,5", "Kč"]);
  assert.deepEqual(t("Příliš žluťoučký kůň"), ["Příliš", "žluťoučký", "kůň"]);
  assert.deepEqual(t("  ...  "), []);
  const toks = scoring.tokenize("ab cd");
  assert.deepEqual(toks.map((x) => [x.start, x.end]), [[0, 2], [3, 5]]);
});
