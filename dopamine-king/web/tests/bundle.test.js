"use strict";
// The data the game ships with, checked against the JavaScript scorer and statistics, plus the pure helpers
// the Forge, Guru and About views are built on.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const scoring = require("../src/scoring.js");
const labstats = require("../src/labstats.js");
const game = require("../src/game.js");
const charts = require("../src/ui/charts.js");
const guru = require("../src/ui/guru.js");
const forge = require("../src/ui/forge.js");
const about = require("../src/ui/about.js");

const DEV = path.resolve(__dirname, "..", "dev");
const bundle = JSON.parse(fs.readFileSync(path.join(DEV, "bundle.json"), "utf8"));
const pack = JSON.parse(fs.readFileSync(path.join(DEV, "mock-forge.json"), "utf8"));
const plan = JSON.parse(fs.readFileSync(path.join(DEV, "mock-guru.json"), "utf8"));
const spec = bundle.spec;
const round1 = (x) => Math.round(x * 10) / 10;

// -- arena data ---------------------------------------------------------------------------------
test("the Python scores stored in the arena data equal what the JavaScript scorer computes", () => {
  assert.ok(bundle.arena.length >= 100);
  for (const d of bundle.arena) {
    for (const side of ["a", "b"]) {
      const s = scoring.scoreHook(d[side].text, "", { lang: d.lang, spec });
      assert.ok(Math.abs(round1(s.total) - d[side].score) <= 0.1 + 1e-9, `${d.id} ${side}: ${s.total} vs ${d[side].score}`);
    }
  }
});

test("arena duels are well formed", () => {
  const ids = new Set();
  for (const d of bundle.arena) {
    assert.ok(!ids.has(d.id), `duplicate ${d.id}`);
    ids.add(d.id);
    assert.ok(["easy", "medium", "hard"].includes(d.difficulty), d.id);
    assert.ok(["cs", "en"].includes(d.lang), d.id);
    assert.ok(["a", "b"].includes(d.winner), d.id);
    assert.equal(d.winner, d.a.success >= d.b.success ? "a" : "b", `${d.id}: winner must have the higher success`);
    assert.equal(typeof d.upset, "boolean");
    const disagree = (d.model_p_a >= 0.5) !== (d.winner === "a");
    if (d.upset) assert.ok(disagree, `${d.id}: an upset means the model favoured the loser`);
    else assert.ok(!disagree || Math.abs(d.model_p_a - 0.5) < 0.03, `${d.id}: a model miss that is not an upset must be a near tie`);
    assert.equal(d.reasons_en.length, d.reasons_cs.length, `${d.id}: both languages explain the same points (a close duel may have none)`);
  }
  for (const lang of ["cs", "en"]) for (const diff of ["easy", "medium", "hard"]) assert.ok(bundle.arena.some((d) => d.lang === lang && d.difficulty === diff), `${lang} ${diff}`);
});

test("shipped constants are consistent", () => {
  const rates = bundle.loot.rates;
  assert.ok(Math.abs(Object.values(rates).reduce((s, x) => s + x, 0) - 1) < 1e-9, "rates sum to 1");
  assert.ok(Number.isInteger(bundle.loot.pity_after) && bundle.loot.pity_after >= 1);
  const ids = bundle.loot.cards.map((c) => c.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const c of bundle.loot.cards) assert.ok(game.RARITIES.includes(c.rarity), c.id);
  assert.equal(new Set(bundle.bosses.map((b) => b.id)).size, bundle.bosses.length);
  for (const b of bundle.bosses) { assert.ok(b.percentile > 0 && b.percentile < 100, b.id); assert.ok(b.xp > 0); }
  for (const m of bundle.myths) assert.ok(["myth", "fact"].includes(m.answer), m.id);
  assert.deepEqual(Object.keys(bundle.calibration.weights).sort(), [...scoring.WEIGHTED_DRIVERS].sort());
  assert.deepEqual(Object.keys(spec.params.weights).sort(), [...scoring.WEIGHTED_DRIVERS].sort());
  for (const p of bundle.patterns) assert.ok(scoring.FEATURE_NAMES.includes(p.feature), `pattern feature ${p.feature}`);
  for (const [k, b] of Object.entries(bundle.benchmarks)) { assert.equal(b.quantiles.length, 101, k); assert.ok(b.quantiles.every((q, i, a) => i === 0 || q >= a[i - 1]), `${k} quantiles must not decrease`); }
});

// -- Forge sample -------------------------------------------------------------------------------
function checkPack(pack, { everyVerdict }) {
  const lang = pack.brief.lang;
  let sumDopamine = 0, n = 0;
  for (const it of pack.items) {
    const s = scoring.scoreHook(it.hook, "", { lang, spec });
    assert.ok(Math.abs(s.total - it.hook_score.total) < 0.0051, `${it.format}: ${s.total} vs ${it.hook_score.total} (the sample stores two decimals)`);
    assert.equal(round1(it.hook_score.total), it.scores.dopamine, it.format);
    assert.deepEqual(Object.keys(it.hook_score).sort(), Object.keys(s).sort(), "same result keys as the scorer");
    sumDopamine += it.scores.dopamine; n += 1;
    const sev = it.issues.map((i) => i.severity);
    assert.equal(it.verdict, sev.includes("error") ? "blocked" : sev.includes("warn") ? "review" : "ok", `${it.format} verdict`);
    assert.equal(/\[\[ADD/.test(it.body), it.slots_open.length > 0, `${it.format}: open slots match the body`);
    for (const a of it.alt_hooks) assert.ok(Math.abs(scoring.scoreHook(a.text, "", { lang, spec }).total - a.score) <= 0.06, `${it.format} alt ${a.text}`);
  }
  assert.equal(pack.summary.n_items, pack.items.length);
  assert.equal(pack.summary.avg_dopamine, round1(sumDopamine / n));
  assert.equal(pack.summary.errors, pack.items.flatMap((i) => i.issues).filter((i) => i.severity === "error").length);
  assert.equal(pack.summary.warnings, pack.items.flatMap((i) => i.issues).filter((i) => i.severity === "warn").length);
  assert.equal(pack.summary.open_slots, pack.items.reduce((s, i) => s + i.slots_open.length, 0));
  const counts = { ok: 0, review: 0, blocked: 0 };
  pack.items.forEach((i) => { counts[i.verdict] += 1; });
  assert.deepEqual(pack.summary.verdicts, counts);
  if (everyVerdict) assert.ok(pack.items.some((i) => i.verdict === "blocked") && pack.items.some((i) => i.verdict === "ok"), "the sample shows every verdict");
}

test("the development sample pack agrees with the JavaScript scorer and with its own summary", () => {
  checkPack(pack, { everyVerdict: true });
});

test("the sample packs shipped in the bundle (one per language) agree with the JavaScript scorer and their own summary", () => {
  assert.deepEqual(bundle.forge_samples.map((p) => p.brief.lang).sort(), ["cs", "en"]);
  for (const p of bundle.forge_samples) checkPack(p, { everyVerdict: false });
});

test("the shipped sample packs are written for the edition: vertical, claims profile and the claims check codes it can produce", () => {
  const known = new Set(["CLAIM_MEDICAL", "CLAIM_AVOID", "CLAIM_UNHEDGED", "DISEASE_MENTION", "STATUS_CLAIM", "SAFETY_ABSOLUTE", "OUTCOME_PROMISE", "DOSE_NOT_FROM_MANUAL", "SAFETY_NOTE_MISSING", "MEDICATION_ADVICE", "THERAPY_WORD"]);
  for (const p of bundle.forge_samples) {
    assert.equal(p.brief.vertical, bundle.vertical.id);
    assert.equal(p.brief.claims_profile, bundle.vertical.claims_profile);
    assert.equal(p.summary.claims_profile, bundle.vertical.claims_profile);
    assert.equal(p.brief.brand, "MITO LIGHT");
    assert.ok(p.brief.facts.length >= 3, "facts come from public descriptions and are listed in the brief");
    const codes = p.items.flatMap((i) => i.issues.map((x) => x.code)).filter((c) => known.has(c));
    assert.ok(codes.every((c) => bundle.claim_rules && require("../src/claims.js").CODES.includes(c)), "codes the UI can name");
  }
});

test("Forge helpers: briefToApi trims, drops empty fields and splits the facts", () => {
  const out = forge.briefToApi({ brand: " Acme ", topic: "shoes ", audience: " runners", goal: "conversion", lang: null, tone: " calm ", keyword: "  ", facts: "One.\n\n  Two.  \r\nThree.", offer: "", cta: " Go " });
  assert.deepEqual(out, { brand: "Acme", topic: "shoes", audience: "runners", goal: "conversion", lang: "en", tone: "calm", cta: "Go", facts: ["One.", "Two.", "Three."] });
  assert.equal(forge.briefToApi({ brand: "a", topic: "b", audience: "c", goal: "awareness", lang: "cs", tone: "", keyword: "", facts: "", offer: "", cta: "" }).lang, "cs");
});

// -- Guru sample --------------------------------------------------------------------------------
function checkPlan(plan, { needsInput } = {}) {
  assert.ok(Math.abs(plan.pillars.reduce((s, p) => s + p.share, 0) - 1) < 1e-9, "pillar shares sum to 1");
  assert.deepEqual([...new Set(plan.calendar.map((c) => c.week))].sort(), [1, 2, 3, 4]);
  const pillarIds = new Set(plan.pillars.map((p) => p.id)), channelIds = new Set(plan.channels.map((c) => c.id));
  for (const c of plan.calendar) {
    assert.ok(pillarIds.has(c.pillar), c.pillar);
    assert.ok(channelIds.has(c.channel), c.channel);
    assert.ok(c.hook && c.format && c.day);
  }
  const posts = plan.channels.reduce((s, c) => s + c.posts_per_week, 0) * 4;
  assert.ok(Math.abs(posts - plan.calendar.length) < 0.2, `channel rates imply ${posts} posts, the calendar has ${plan.calendar.length}`);
  for (const e of plan.experiments) assert.equal(e.n_per_arm, labstats.sampleSizePerArm(e.baseline, e.mde_rel), e.id);
  for (const c of plan.calendar.filter((x) => x.experiment)) {
    const e = guru.normExperiment(plan, c.experiment, (o, f) => o[f + "_en"]);
    assert.ok(e && e.def, `a calendar test must map to a backlog entry: ${c.experiment.hypothesis}`);
    assert.ok(e.variantB && e.metric);
  }
  assert.ok(plan.kpis.some((k) => k.primary) && plan.kpis.every((k) => k.target_rule_en && k.target_rule_cs));
  assert.ok(Array.isArray(plan.needs_input), "the plan lists what it still needs from the brand (possibly nothing)");
  if (needsInput) assert.ok(plan.needs_input.length >= 1, "the plan must say what it cannot know");
  assert.equal(plan.guardrails_en.length, plan.guardrails_cs.length);
}

test("the development sample plan is internally consistent and uses the Lab's sample size formula", () => {
  checkPlan(plan, { needsInput: true });
});

test("the sample plans shipped in the bundle (one per language) are consistent too", () => {
  assert.deepEqual(bundle.guru_samples.map((p) => p.brief.lang).sort(), ["cs", "en"]);
  for (const p of bundle.guru_samples) checkPlan(p);
});

test("Guru helpers: parsePositioning, groupWeeks and normExperiment", () => {
  const parts = guru.parsePositioning(plan.positioning);
  assert.equal(parts[0].label, null);
  assert.equal(parts[0].value, plan.brief.brand);
  assert.deepEqual(parts.slice(1).map((p) => p.label), ["Audience", "Topic", "Promise", "Proof", "Tone"]);
  assert.ok(!/[.!?];\s/.test(parts.map((p) => p.value).join(" ")), "joined facts do not leave a '.;' behind");
  assert.deepEqual(guru.parsePositioning("Just a sentence."), [{ label: null, value: "Just a sentence." }]);
  assert.deepEqual(guru.parsePositioning(""), [{ label: null, value: "" }]);
  const weeks = guru.groupWeeks([{ week: 2, day: "Mon" }, { week: 1, day: "Fri" }, { week: 1, day: "Mon" }, { week: "3" }, {}]);
  assert.deepEqual(weeks.map((w) => [w.n, w.items.length]), [[1, 3], [2, 1], [3, 1]]);
  assert.deepEqual(guru.groupWeeks(undefined), []);
  const pick = (o, f) => o[f + "_en"];
  assert.equal(guru.normExperiment(plan, null, pick), null);
  const byId = guru.normExperiment(plan, "e2", pick);
  assert.equal(byId.def.id, "e2");
  assert.equal(byId.hypothesis, plan.experiments[1].hypothesis_en);
  assert.equal(guru.normExperiment(plan, "nope", pick), null);
  const loose = guru.normExperiment({ experiments: [] }, { hypothesis: "H", variant_b: "B", metric: "M" }, pick);
  assert.deepEqual([loose.hypothesis, loose.variantB, loose.metric, loose.def], ["H", "B", "M", null]);
});

test("About helper: references are split, unique and sorted", () => {
  const refs = about.collectRefs([{ ref: "Zed, 2001; Alpha, 1999" }, { ref: "Alpha, 1999" }, { ref: "" }, {}, null, { ref: " Beta and Co, 2010 ;" }]);
  assert.deepEqual(refs, ["Alpha, 1999", "Beta and Co, 2010", "Zed, 2001"]);
  const real = about.collectRefs(bundle.myths);
  assert.ok(real.length >= 8 && real.every((r) => !/;/.test(r)));
});

// -- claims data of the edition ----------------------------------------------------------------------
test("the claims map in the bundle is consistent with the vault and the checker rules", () => {
  assert.ok(bundle.vertical && bundle.claims && bundle.claim_rules, "the development bundle is the MITO LIGHT edition");
  assert.equal(bundle.meta.vertical, bundle.vertical.id);
  const classes = Object.keys(bundle.claims.classes).sort();
  assert.deepEqual(classes, ["avoid", "context", "cosmetic", "medical", "wellness"]);
  for (const c of classes) assert.ok(bundle.claims.classes[c].en && bundle.claims.classes[c].cs, c);
  const studies = new Map(bundle.vault.studies.map((x) => [x.id, x]));
  const ruleIds = new Set(bundle.claim_rules.topics.map((t) => t.id));
  const labels = ["strong", "moderate", "limited", "contested", "none"];
  const ids = new Set();
  for (const t of bundle.claims.topics) {
    assert.ok(!ids.has(t.id), `duplicate topic ${t.id}`);
    ids.add(t.id);
    assert.ok(classes.includes(t.class), t.id);
    assert.ok(labels.includes(t.label) && labels.includes(t.computed_label), t.id);
    for (const f of ["name", "claim", "summary"]) assert.ok(t[f + "_en"] && t[f + "_cs"], `${t.id} ${f}`);
    assert.equal(t.safe_en.length > 0, t.safe_cs.length > 0, `${t.id}: safer wording in both languages`);
    assert.equal(t.avoid_en.length, t.avoid_cs.length, t.id);
    assert.equal(t.capped, t.label !== t.computed_label && t.computed_label !== "contested", `${t.id}: capped means the shown label is below the computed one`);
    if (t.capped) assert.ok(t.cap_reason_en && t.cap_reason_cs, `${t.id}: a cap is explained`);
    assert.ok(ruleIds.has(t.id), `${t.id}: the checker knows the topic`);
    const linked = t.study_ids.map((id) => studies.get(id));
    assert.ok(linked.every(Boolean), `${t.id}: every linked study is in the vault`);
    assert.ok(t.n_studies <= linked.filter((x) => x.verified === true).length, `${t.id}: only verified studies are counted`);
    assert.equal(t.n_pending, linked.filter((x) => x.verified !== true).length, `${t.id}: the others are pending`);
  }
  for (const link of bundle.vault.links) {
    const known = ids.has(link.tactic_id) || bundle.vault.tactics.some((x) => x.id === link.tactic_id);
    assert.ok(known, `link to ${link.tactic_id} resolves to a claim topic or a tactic`);
    assert.ok(studies.has(link.study_id), link.study_id);
    assert.ok(["supports", "mixed", "contradicts", "context"].includes(link.direction), link.direction);
  }
  assert.ok(bundle.vault.studies.some((x) => x.verified !== true), "research leads that are not verified yet ship in the bundle");
  assert.ok(bundle.vault.studies.some((x) => x.verified === true));
});

test("the vertical metadata has both languages, the glossary and the regulatory note", () => {
  const v = bundle.vertical;
  for (const f of ["name", "short", "tagline", "edition", "regulatory_note"]) assert.ok(v[f + "_en"] && v[f + "_cs"], f);
  assert.ok(v.glossary.length >= 5);
  for (const g of v.glossary) assert.ok(g.id && g.term_en && g.term_cs && g.def_en && g.def_cs, g.id);
  assert.match(v.regulatory_note_en, /not legal advice/i);
  assert.match(v.regulatory_note_cs, /nejde|ne právní poradenství/i);
  for (const [k, lab] of Object.entries(v.cohorts)) assert.ok(bundle.cohort_labels[k] && lab.en && lab.cs, k);
});

test("every boss of the edition has benchmark data to be judged against", () => {
  for (const b of bundle.bosses) {
    assert.ok(bundle.benchmarks[b.cohort] || bundle.benchmarks.all, b.id);
    assert.ok(bundle.cohort_labels[b.cohort], `${b.id}: the cohort has a name`);
    assert.ok(b.brief_en && b.brief_cs && b.taunt_en && b.taunt_cs, b.id);
  }
  assert.ok(bundle.bosses.some((b) => b.lang === "cs") && bundle.bosses.some((b) => b.lang === "en"));
});

// -- chart helpers ------------------------------------------------------------------------------
test("niceTicks returns round, evenly spaced ticks that cover the range", () => {
  assert.deepEqual(charts.niceTicks(0, 100, 5).ticks, [0, 20, 40, 60, 80, 100]);
  assert.deepEqual(charts.niceTicks(0, 1, 4).ticks, [0, 0.2, 0.4, 0.6, 0.8, 1]);
  assert.ok(charts.niceTicks(3, 3).ticks.length > 0, "a flat range still gets ticks");
  assert.equal(charts.niceTicks(0, 0.037, 4).niceMax >= 0.037, true);
  let seed = 12345;
  const rnd = () => { seed = (seed * 1664525 + 1013904223) % 4294967296; return seed / 4294967296; };
  for (let i = 0; i < 300; i++) {
    const min = (rnd() - 0.3) * 1000, span = Math.pow(10, rnd() * 6 - 3), max = min + span;
    const { ticks, step, niceMax } = charts.niceTicks(min, max, 5);
    assert.ok(ticks.length >= 2 && ticks.length <= 12, `${ticks.length} ticks for ${min}..${max}`);
    assert.ok(ticks[0] >= min - step * 1e-6 && ticks[ticks.length - 1] <= max + step * 1e-6, "ticks inside the range");
    assert.ok(niceMax >= max - step * 1e-6, "niceMax covers the maximum");
    for (let k = 1; k < ticks.length; k++) assert.ok(Math.abs(ticks[k] - ticks[k - 1] - step) < step * 1e-6, "even spacing");
    const mag = Math.pow(10, Math.floor(Math.log10(step)));
    assert.ok([1, 2, 5, 10].some((m) => Math.abs(step / mag - m) < 1e-6), `step ${step} is 1, 2 or 5 times a power of ten`);
  }
});

test("chart sample keeps the first and last point and never exceeds n", () => {
  const pts = Array.from({ length: 1000 }, (_, i) => [i, i * i]);
  const s = charts.sample(pts, 40);
  assert.equal(s.length, 40);
  assert.deepEqual(s[0], pts[0]);
  assert.deepEqual(s[39], pts[999]);
  assert.equal(charts.sample(pts.slice(0, 10), 40).length, 10);
});
