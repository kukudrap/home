"use strict";
// The claims views: the pure models (claims map, findings, study links) and the rendered Boss claims panel, Vault claims
// map, Home banner, About cards and Forge pill, using the small DOM of ui-sandbox.js. The generic edition (a bundle
// without vertical, claims and claim_rules) must keep its old shape.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const claimsui = require("../src/ui/claimsui.js");
const forge = require("../src/ui/forge.js");
const game = require("../src/game.js");
const scoring = require("../src/scoring.js");
const { loadUi, sleep } = require("./ui-sandbox.js");

const bundle = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "dev", "bundle.json"), "utf8"));
const clone = (x) => JSON.parse(JSON.stringify(x));
/** The same data as the generic edition ships it: no vertical, no claims map, no rules. */
function generic() {
  const b = clone(bundle);
  delete b.vertical; delete b.claims; delete b.claim_rules;
  return b;
}
const GOOD_HOOK = "5 mistakes people make when choosing a red light panel";
const BAD_HOOK = "Red light cures joint pain";

// -- pure models ------------------------------------------------------------------------------------------
test("the claims engine exists only for an edition with rules, and is cached per bundle", () => {
  assert.equal(claimsui.engine(generic()), null);
  assert.equal(claimsui.engine(null), null);
  const e = claimsui.engine(bundle);
  assert.ok(e && e.compiled.topics.length >= 15 && e.compiled.errors.length === 0);
  assert.equal(claimsui.engine(bundle), e);
});

test("a check returns findings with the topic in the UI language, its evidence label and the first safer wording", () => {
  const e = claimsui.engine(bundle);
  const en = claimsui.check(e, BAD_HOOK, "en");
  assert.equal(en.errors, 1);
  const f = en.findings[0];
  assert.deepEqual([f.code, f.severity, f.phrase], ["CLAIM_MEDICAL", "error", "cures joint pain"]);
  const topic = bundle.claims.topics.find((t) => t.id === "pbm-pain-joints");
  assert.equal(f.topic.id, "pbm-pain-joints");
  assert.equal(f.topic.name, topic.name_en);
  assert.equal(f.topic.label, topic.label, "the label shown in the Claims map, not the cap");
  assert.equal(f.topic.safe, bundle.claim_rules.topics.find((t) => t.id === "pbm-pain-joints").safe_en[0]);
  assert.equal(f.topic.blocked, true);
  const cs = claimsui.check(e, "Červené světlo léčí bolest kloubů", "cs");
  assert.equal(cs.findings[0].topic.name, topic.name_cs);
  assert.equal(cs.findings[0].topic.safe, bundle.claim_rules.topics.find((t) => t.id === "pbm-pain-joints").safe_cs[0]);
  assert.ok(!JSON.stringify(cs).includes(String.fromCharCode(0x2014)) && !JSON.stringify(cs).includes(String.fromCharCode(0x2013)), "no long dashes in what the user sees");
});

test("findings are listed errors first, then warnings and notes, each with a severity", () => {
  const e = claimsui.engine(bundle);
  const r = claimsui.check(e, "Red light therapy. Results in 14 days. Red light cures joint pain.", "en");
  assert.deepEqual(r.findings.map((x) => x.severity), ["error", "warn", "info"]);
  assert.deepEqual(r.summary, { error: 1, warn: 1, info: 1, total: 3 });
  assert.equal(r.findings[0].start > r.findings[1].start, true, "errors come first even when they sit later in the text");
});

test("a text typed with combining accents is normalised before it is checked", () => {
  const e = claimsui.engine(bundle);
  const decomposed = "Cerveně svetlo leči bolest kloubů".normalize("NFD");
  const composed = "Červené světlo léčí bolest kloubů".normalize("NFD");
  assert.equal(claimsui.check(e, composed, "cs").errors, 1);
  assert.equal(claimsui.check(e, composed, "cs").text, composed.normalize("NFC"));
  assert.ok(claimsui.check(e, decomposed, "cs").text.length < decomposed.length + 1);
});

test("the status of a report: idle, clean, blocked or advice", () => {
  const e = claimsui.engine(bundle);
  assert.deepEqual(claimsui.statusOf(null), { kind: "idle", n: 0 });
  assert.deepEqual(claimsui.statusOf(claimsui.check(e, GOOD_HOOK, "en")), { kind: "clean", n: 0 });
  assert.deepEqual(claimsui.statusOf(claimsui.check(e, BAD_HOOK, "en")), { kind: "blocked", n: 1 });
  assert.deepEqual(claimsui.statusOf(claimsui.check(e, "Red light therapy", "en")), { kind: "advice", n: 1 });
  assert.deepEqual(claimsui.statusOf(claimsui.check(e, "Results in 14 days. Red light therapy.", "en")), { kind: "advice", n: 2 });
});

test("the claims map groups the topics by class in the fixed order and marks medical and avoid as blocked", () => {
  const m = claimsui.claimsMap(bundle, "en");
  assert.deepEqual(m.legend.map((g) => g.klass), ["wellness", "cosmetic", "context", "medical", "avoid"]);
  assert.ok(m.legend.every((g) => g.meaning.length > 20), "each class carries its meaning from the data");
  assert.deepEqual(m.groups.map((g) => g.klass), ["wellness", "cosmetic", "context", "medical", "avoid"]);
  assert.equal(m.total, bundle.claims.topics.length);
  assert.equal(m.groups.reduce((s, g) => s + g.topics.length, 0), m.total);
  for (const g of m.groups) {
    assert.equal(g.blocked, g.klass === "medical" || g.klass === "avoid");
    for (const t of g.topics) { assert.equal(t.klass, g.klass); assert.equal(t.blocked, g.blocked); }
  }
  assert.equal(m.blockedTotal, bundle.claims.topics.filter((t) => t.class === "medical" || t.class === "avoid").length);
  assert.equal(m.note, bundle.vertical.regulatory_note_en);
  assert.equal(claimsui.claimsMap(bundle, "cs").note, bundle.vertical.regulatory_note_cs);
  assert.equal(claimsui.claimsMap(generic(), "en"), null);
  assert.equal(claimsui.claimsMap({ claims: { classes: {}, topics: "no" } }, "en"), null);
});

test("a topic model has the name, claim, label, cap, counts, wording lists and linked studies in the UI language", () => {
  const raw = bundle.claims.topics.find((t) => t.id === "pbm-pain-joints");
  const en = claimsui.claimsMap(bundle, "en").groups.flatMap((g) => g.topics).find((t) => t.id === "pbm-pain-joints");
  const cs = claimsui.claimsMap(bundle, "cs").groups.flatMap((g) => g.topics).find((t) => t.id === "pbm-pain-joints");
  assert.equal(en.name, raw.name_en);
  assert.equal(cs.name, raw.name_cs);
  assert.equal(en.claim, raw.claim_en);
  assert.deepEqual(cs.safe, raw.safe_cs);
  assert.deepEqual(en.avoid, raw.avoid_en);
  assert.equal(en.capped, true);
  assert.equal(en.label, raw.label);
  assert.equal(en.computedLabel, raw.computed_label);
  assert.equal(en.capReason, raw.cap_reason_en);
  assert.equal(cs.capReason, raw.cap_reason_cs);
  assert.equal(en.nVerified, raw.n_studies);
  assert.equal(en.nPending, raw.n_pending);
  assert.deepEqual(en.studies.map((s) => s.id).sort(), [...raw.study_ids].sort());
  const flags = en.studies.map((s) => s.verified);
  assert.deepEqual(flags, [...flags].sort((a, b) => Number(b) - Number(a)), "verified studies first");
  const byId = Object.fromEntries(bundle.vault.studies.map((s) => [s.id, s]));
  for (const s of en.studies) assert.equal(s.verified, byId[s.id].verified === true, s.id);
});

test("every claim topic that has unverified studies says so, and nothing unverified is counted as verified", () => {
  const m = claimsui.claimsMap(bundle, "en");
  const byId = Object.fromEntries(bundle.vault.studies.map((s) => [s.id, s]));
  let withLeads = 0;
  for (const t of m.groups.flatMap((g) => g.topics)) {
    const pending = t.studies.filter((s) => !s.verified).length;
    assert.equal(pending, t.nPending, `${t.id}: pending studies listed equal the pending count`);
    if (pending) withLeads += 1;
    assert.ok(t.studies.every((s) => (byId[s.id] ? byId[s.id].verified === true : false) === s.verified));
  }
  assert.ok(withLeads >= 3, "the edition ships research leads that are not verified yet");
});

test("a link to a study that is missing from the bundle still shows, as not verified", () => {
  const b = clone(bundle);
  b.claims.topics[0].study_ids = b.claims.topics[0].study_ids.concat(["doi:missing"]);
  const t = claimsui.claimsMap(b, "en").groups.flatMap((g) => g.topics).find((x) => x.id === b.claims.topics[0].id);
  const stub = t.studies.find((s) => s.id === "doi:missing");
  assert.deepEqual([stub.title, stub.verified], ["doi:missing", false]);
});

test("study links resolve names of evidence tactics and of claim topics, with the direction of each link", () => {
  const names = claimsui.topicNames(bundle, "en");
  assert.equal(names["curiosity-gap"], "Curiosity gap");
  assert.equal(names["pbm-muscle-recovery"], bundle.claims.topics.find((t) => t.id === "pbm-muscle-recovery").name_en);
  assert.equal(claimsui.topicNames(bundle, "cs")["pbm-muscle-recovery"], bundle.claims.topics.find((t) => t.id === "pbm-muscle-recovery").name_cs);
  const link = bundle.vault.links.find((l) => /^pbm-/.test(l.tactic_id));
  const found = claimsui.studyLinks(bundle, link.study_id, "en");
  assert.ok(found.some((l) => l.id === link.tactic_id && l.name === names[link.tactic_id] && l.direction === link.direction));
  assert.ok(found.every((l) => claimsui.DIRECTIONS.includes(l.direction)));
  const unresolved = clone(bundle);
  unresolved.vault.links.push({ tactic_id: "no-such-topic", study_id: link.study_id, direction: "strange" });
  const odd = claimsui.studyLinks(unresolved, link.study_id, "en").find((l) => l.id === "no-such-topic");
  assert.deepEqual([odd.name, odd.direction], ["no-such-topic", "context"], "an id without a name stays readable, an unknown direction is background");
  assert.deepEqual(claimsui.studyLinks(bundle, "nope", "en"), []);
});

test("the example text of the Check your own text box shows both a blocked and an allowed sentence in both languages", () => {
  const i18n = require("../src/i18n.js");
  const e = claimsui.engine(bundle);
  for (const lang of ["en", "cs"]) {
    const text = i18n.t("vault.check.exampleText", null, lang);
    const r = claimsui.check(e, text, lang);
    assert.ok(r.summary.error >= 1 && r.summary.warn >= 1, `${lang}: ${JSON.stringify(r.summary)}`);
    const sentences = text.split(/(?<=\.)\s+/);
    const safe = sentences.filter((s) => claimsui.check(e, s, lang).summary.total === 0);
    assert.ok(safe.length >= 1, `${lang}: one sentence is fine`);
  }
});

// -- game: the claims condition of a boss win ----------------------------------------------------------------
test("a boss win also needs no claim error, and the old two-condition rule holds without the checker", () => {
  const boss = bundle.bosses.find((b) => b.lang === "en");
  const need = game.thresholdScore(boss.percentile, bundle.benchmarks[boss.cohort].quantiles);
  const strong = { total: need + 10, clickbait_risk: 0.05, lang: "en" };
  const plain = game.resolveBoss(boss, strong, bundle.benchmarks);
  assert.deepEqual([plain.won, plain.claimsChecked, plain.claimsOk, plain.claimErrors], [true, false, true, 0]);
  const clean = game.resolveBoss(boss, strong, bundle.benchmarks, { claimErrors: 0 });
  assert.deepEqual([clean.won, clean.claimsChecked, clean.claimsOk], [true, true, true]);
  const blocked = game.resolveBoss(boss, strong, bundle.benchmarks, { claimErrors: 2 });
  assert.deepEqual([blocked.won, blocked.pctOk, blocked.riskOk, blocked.claimsOk, blocked.claimErrors], [false, true, true, false, 2]);
  assert.equal(game.resolveBoss(boss, { total: need - 5, clickbait_risk: 0.05 }, bundle.benchmarks, { claimErrors: 0 }).won, false, "the percentile still counts");
  assert.equal(game.resolveBoss(boss, { total: need + 10, clickbait_risk: 0.5 }, bundle.benchmarks, { claimErrors: 0 }).won, false, "so does the risk");
  assert.equal(game.resolveBoss(boss, strong, bundle.benchmarks, {}).claimsChecked, false);
  assert.equal(game.resolveBoss(boss, strong, bundle.benchmarks, { claimErrors: -3 }).claimsOk, true);
  assert.equal(game.resolveBoss(boss, strong, bundle.benchmarks, { claimErrors: NaN }).claimsChecked, false);
});

test("the real hooks used below do what the tests expect: the good one wins the first English boss, the bad one is blocked", () => {
  const boss = bundle.bosses.find((b) => b.lang === "en");
  const e = claimsui.engine(bundle);
  const win = (text) => {
    const s = scoring.scoreHook(text, "", { lang: "en", spec: bundle.spec });
    return game.resolveBoss(boss, s, bundle.benchmarks, { claimErrors: claimsui.check(e, text, "en").errors });
  };
  assert.equal(win(GOOD_HOOK).won, true);
  const bad = win(BAD_HOOK);
  assert.equal(bad.claimsOk, false);
  assert.equal(bad.won, false);
});

// -- rendered views --------------------------------------------------------------------------------------
function makeCtx(env, b, lang = "en") {
  const { DK } = env;
  DK.i18n.setLang(lang);
  DK.scoring.setDefaultSpec(b.spec);
  const store = DK.store.createStore({ storage: null, lang });
  const now = () => new Date("2026-10-02T10:00:00");
  const ctx = {
    bundle: b, store, rng: DK.game.systemRng(), now, today: () => "2026-10-02",
    lang: () => DK.i18n.getLang(), t: DK.i18n.t, tp: DK.i18n.tp, pick: DK.i18n.pick, fmt: DK.i18n.fmt,
    live: () => ({ enabled: false }), api: {}, profile: () => store.get(),
    apply(fn, args) { const res = fn(store.get(), args, { now, rng: ctx.rng }); store.set(res.profile); return res; },
    sound() {}, confetti() {}, toast() {}, announce() {}, reducedMotion: () => true, effectiveTheme: () => "dark",
    openProfile() {}, exportProfile() {}, navigate() {}
  };
  return ctx;
}

async function type(env, el, text) {
  el.value = text;
  el.dispatchEvent({ type: "input", target: el });
  await sleep(220);
}

test("Boss: the claims panel runs live on the typed hook and shows severity, topic, label and safer wording", async () => {
  const env = loadUi(["ui/boss.js"]);
  const ctx = makeCtx(env, bundle);
  const boss = bundle.bosses.find((b) => b.lang === "en");
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  const view = env.DK.ui.boss.mount(host, ctx, { sub: boss.id });
  const panel = host.querySelector(".claims-card");
  assert.ok(panel, "the claims check panel is under the score");
  assert.equal(panel.querySelector("h2").textContent, "Claims check");
  assert.ok(host.querySelector(".live-strip.has-claims .strip-claims") === null, "nothing typed yet, no claims value");
  assert.match(host.querySelector(".claims-status").textContent, /Write a hook/);
  assert.equal(host.querySelectorAll(".cond").length, 3, "percentile, clickbait risk and claims");

  const input = host.querySelector("#hook-input");
  await type(env, input, "Red light cures joint pain");
  const status = host.querySelector(".claims-status");
  assert.ok(status.classList.contains("is-blocked"));
  assert.equal(status.textContent, "1 blocking problem");
  const items = host.querySelectorAll(".claims-card .finding");
  assert.equal(items.length, 1);
  const f = items[0];
  assert.equal(f.getAttribute("data-code"), "CLAIM_MEDICAL");
  assert.ok(f.classList.contains("sev-error"));
  const sev = f.querySelector(".sev-chip");
  assert.match(sev.textContent, /Error/, "severity is text as well as an icon");
  assert.ok(sev.querySelector("svg.icon-ban"), "and an icon");
  assert.match(f.querySelector(".finding-msg").textContent, /Medical claim/);
  assert.match(f.querySelector(".finding-phrase").textContent, /cures joint pain/);
  const topic = bundle.claims.topics.find((t) => t.id === "pbm-pain-joints");
  assert.ok(f.querySelector(".finding-topic").textContent.includes(topic.name_en));
  assert.ok(f.querySelector(".finding-topic .chip.ev-" + topic.label), "the evidence label chip");
  assert.ok(f.querySelector(".finding-safer").textContent.includes(bundle.claim_rules.topics.find((t) => t.id === topic.id).safe_en[0].slice(0, 40)));
  const conds = host.querySelectorAll(".cond");
  assert.ok(conds[2].classList.contains("is-no"), "the claims condition is not met");
  assert.match(conds[2].textContent, /No blocking claim problems/);
  assert.ok(host.querySelector(".strip-claims.is-blocked"), "the live strip carries it too");

  await type(env, input, GOOD_HOOK);
  assert.ok(host.querySelector(".claims-status").classList.contains("is-clean"));
  assert.equal(host.querySelector(".claims-status").textContent, "No claim problems");
  assert.equal(host.querySelectorAll(".claims-card .finding").length, 0);
  assert.ok(host.querySelector(".claims-clean"), "the green state says what was checked");
  assert.ok(host.querySelectorAll(".cond")[2].classList.contains("is-ok"));
  assert.ok(host.querySelector(".strip-claims.is-clean"));
  view.destroy();
});

test("Boss: the panel follows the UI language", async () => {
  const env = loadUi(["ui/boss.js"]);
  const ctx = makeCtx(env, bundle, "cs");
  const boss = bundle.bosses.find((b) => b.lang === "cs");
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.boss.mount(host, ctx, { sub: boss.id });
  assert.equal(host.querySelector(".claims-card h2").textContent, "Kontrola tvrzení");
  await type(env, host.querySelector("#hook-input"), "Červené světlo léčí bolest kloubů");
  assert.equal(host.querySelector(".claims-status").textContent, "1 blokující problém");
  const f = host.querySelector(".claims-card .finding");
  assert.match(f.querySelector(".sev-chip").textContent, /Chyba/);
  assert.match(f.querySelector(".finding-msg").textContent, /Zdravotní tvrzení/);
  const topic = bundle.claims.topics.find((t) => t.id === "pbm-pain-joints");
  assert.ok(f.querySelector(".finding-topic").textContent.includes(topic.name_cs));
  assert.ok(f.querySelector(".finding-safer").textContent.includes("Bezpečnější formulace"));
});

test("Boss: attacking with a claim error loses and says why; a clean strong hook wins", async () => {
  const env = loadUi(["ui/boss.js"]);
  const ctx = makeCtx(env, bundle);
  const boss = bundle.bosses.find((b) => b.lang === "en");
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.boss.mount(host, ctx, { sub: boss.id });
  const input = host.querySelector("#hook-input");
  input.value = "5 mistakes people make when choosing a red light panel. It cures joint pain.";
  host.querySelector(".attack-btn").click();
  const lose = host.querySelector(".fight-result.is-lose");
  assert.ok(lose, "a claim error means no victory");
  const reasons = lose.querySelectorAll(".reason-list li").map((li) => li.textContent);
  assert.ok(reasons.some((r) => /claims check found 1 blocking problem/.test(r)), reasons.join(" | "));
  assert.equal(lose.querySelectorAll(".result-claims .finding").length, 1, "the blocking finding is repeated on the result card");
  assert.equal(ctx.profile().stats.bossWins, 0);

  input.value = GOOD_HOOK;
  host.querySelector(".attack-btn").click();
  const win = host.querySelector(".fight-result.is-win");
  assert.ok(win, "a compliant hook with a strong score wins");
  assert.match(win.textContent, /Claims check passed/);
  assert.equal(ctx.profile().stats.bossWins, 1);
});

test("Boss: without a claims profile the screen is the old one", async () => {
  const env = loadUi(["ui/boss.js"]);
  const b = generic();
  const ctx = makeCtx(env, b);
  const boss = b.bosses.find((x) => x.lang === "en");
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.boss.mount(host, ctx, { sub: boss.id });
  assert.equal(host.querySelector(".claims-card"), null);
  assert.equal(host.querySelector(".live-strip.has-claims"), null);
  await type(env, host.querySelector("#hook-input"), "Red light cures joint pain");
  assert.equal(host.querySelectorAll(".cond").length, 2, "percentile and clickbait risk only");
  assert.equal(host.querySelectorAll(".finding").length, 0);
  assert.doesNotMatch(host.querySelector(".brief").textContent, /claims check/i);
});

test("Boss list: the lead mentions the claims check only in an edition that has one", () => {
  const env = loadUi(["ui/boss.js"]);
  for (const [b, expected] of [[bundle, true], [generic(), false]]) {
    const host = env.document.createElement("div");
    env.DK.ui.boss.mount(host, makeCtx(env, b), null);
    assert.equal(/claims check/.test(host.querySelector(".page-lead").textContent), expected);
  }
});

test("Vault: the Claims map tab, its legend, regulatory note, groups, badges and counts", () => {
  const env = loadUi(["ui/vault.js"]);
  const ctx = makeCtx(env, bundle);
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.vault.mount(host, ctx, { sub: "claims", params: {} });
  const tabs = host.querySelectorAll('[role="tab"]');
  assert.deepEqual(tabs.map((t) => t.querySelector(".tab-label").textContent), ["Cards", "Studies", "Claims map", "Myth or Fact"]);
  assert.deepEqual(tabs.map((t) => t.getAttribute("aria-selected")), ["false", "false", "true", "false"]);
  const legend = host.querySelectorAll(".class-legend > li");
  assert.equal(legend.length, 5);
  assert.deepEqual(legend.map((li) => li.querySelector("strong").textContent), ["Wellness", "Cosmetic", "Context", "Medical", "Unsupported"]);
  for (const li of legend) assert.ok(li.querySelector("svg"), "each class has an icon");
  const classes = bundle.claims.classes;
  assert.ok(legend[0].textContent.includes(classes.wellness.en), "and its meaning");
  const note = host.querySelector(".reg-note");
  assert.equal(note.getAttribute("role"), "note");
  assert.ok(note.textContent.includes(bundle.vertical.regulatory_note_en));
  assert.match(note.textContent, /Not legal advice/);
  const groups = host.querySelectorAll(".claim-group");
  assert.deepEqual(groups.map((g) => g.className.split(" ").find((c) => c.startsWith("klass-"))), ["klass-wellness", "klass-cosmetic", "klass-context", "klass-medical", "klass-avoid"]);
  const cards = host.querySelectorAll(".claim-card");
  assert.equal(cards.length, bundle.claims.topics.length);
  for (const t of bundle.claims.topics) {
    const card = host.querySelector('.claim-card[data-topic="' + t.id + '"]');
    assert.ok(card, t.id);
    assert.equal(card.querySelector(".claim-name").textContent, t.name_en);
    assert.ok(card.querySelector(".claim-sentence").textContent.includes(t.claim_en), `${t.id}: the claim sentence`);
    assert.ok(card.querySelector(".chip.ev-" + t.label), `${t.id}: evidence label chip`);
    const blocked = t.class === "medical" || t.class === "avoid";
    assert.equal(!!card.querySelector(".blocked-badge"), blocked, `${t.id}: blocked badge`);
    assert.equal(card.classList.contains("is-blocked"), blocked);
    if (blocked) assert.match(card.querySelector(".blocked-badge").textContent, /Blocked for this product/);
    assert.equal(!!card.querySelector(".cap-box"), t.capped, `${t.id}: capped explanation`);
    if (t.capped) assert.ok(card.querySelector(".cap-box").textContent.includes(t.cap_reason_en));
    const counts = card.querySelector(".claim-counts").textContent;
    assert.match(counts, new RegExp(t.n_studies + " verified stud"));
    assert.equal(/pending verification/.test(counts), t.n_pending > 0, `${t.id}: pending count`);
    assert.equal(card.querySelectorAll(".safe-list li").length, t.safe_en.length, `${t.id}: safer wording list`);
    assert.equal(card.querySelectorAll(".avoid-list li").length, t.avoid_en.length, `${t.id}: avoid list`);
    assert.equal(card.querySelectorAll(".claim-study").length, t.study_ids.length, `${t.id}: linked studies`);
    const pending = card.querySelectorAll(".claim-study.is-unverified");
    assert.equal(pending.length, t.study_ids.filter((id) => bundle.vault.studies.find((s) => s.id === id).verified !== true).length);
    for (const p of pending) assert.match(p.textContent, /Not verified yet/);
  }
  assert.ok(host.querySelector('.claim-card[data-topic="pbm-pain-joints"]').querySelector(".cap-box"), "a capped label is explained");

  // the legend jumps to a group and each group has a way back up (the page is long)
  assert.equal(host.querySelectorAll(".claim-group .to-legend").length, 5);
  host.querySelector(".class-legend .legend-class.class-medical").click();
  assert.equal(env.document.activeElement.id, "claims-group-medical", "focus follows the jump");
  host.querySelector(".claim-group.klass-medical .to-legend").click();
  assert.equal(env.document.activeElement.id, "claims-legend-h", "and the way back");
  assert.equal(host.querySelectorAll(".class-legend button.legend-class").length, 5, "every class has topics, so every legend item is a button");
});

test("Vault: the Claims map in Czech", () => {
  const env = loadUi(["ui/vault.js"]);
  const ctx = makeCtx(env, bundle, "cs");
  const host = env.document.createElement("div");
  env.DK.ui.vault.mount(host, ctx, { sub: "claims", params: {} });
  assert.deepEqual(host.querySelectorAll('[role="tab"] .tab-label').map((x) => x.textContent), ["Karty", "Studie", "Mapa tvrzení", "Mýtus, nebo fakt"]);
  const t = bundle.claims.topics.find((x) => x.id === "pbm-pain-joints");
  const card = host.querySelector('.claim-card[data-topic="pbm-pain-joints"]');
  assert.equal(card.querySelector(".claim-name").textContent, t.name_cs);
  assert.match(card.querySelector(".blocked-badge").textContent, /Pro tento výrobek zakázáno/);
  assert.ok(host.querySelector(".reg-note").textContent.includes(bundle.vertical.regulatory_note_cs));
  assert.match(card.querySelector(".claim-counts").textContent, /ověřen/);
});

test("Vault: Check your own text runs the same checker and lists severity, topic, label and safer wording", () => {
  const env = loadUi(["ui/vault.js"]);
  const ctx = makeCtx(env, bundle);
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.vault.mount(host, ctx, { sub: "claims", params: {} });
  const box = host.querySelector(".claims-check");
  assert.match(box.querySelector(".claims-empty").textContent, /Nothing checked yet/, "the empty state explains what it does");
  assert.match(box.textContent, /nothing is sent anywhere/);
  const input = box.querySelector("#claims-check-input");
  const [run, example, clear] = box.querySelectorAll(".claims-check-bar button");
  // empty text: a gentle message, no findings
  run.click();
  assert.match(box.querySelector(".claims-empty").textContent, /Paste some text first/);
  // pasted text
  input.value = "Red light relieves joint pain. Some studies suggest red light may support muscle recovery after exercise. Red light therapy.";
  run.click();
  const findings = box.querySelectorAll(".finding");
  assert.deepEqual(findings.map((f) => f.getAttribute("data-code")), ["CLAIM_MEDICAL", "THERAPY_WORD"]);
  assert.ok(box.querySelector(".claims-status").classList.contains("is-blocked"));
  const first = findings[0];
  assert.match(first.querySelector(".sev-chip").textContent, /Error/);
  assert.ok(first.querySelector(".finding-topic .chip.ev-limited, .finding-topic .chip.ev-strong, .finding-topic .chip.ev-moderate, .finding-topic .chip.ev-none, .finding-topic .chip.ev-contested"));
  assert.ok(first.querySelector(".finding-safer").textContent.length > 30);
  // an example fills the box and runs
  clear.click();
  assert.equal(input.value, "");
  assert.match(box.querySelector(".claims-empty").textContent, /Nothing checked yet/);
  example.click();
  assert.equal(input.value, env.DK.i18n.t("vault.check.exampleText"));
  assert.ok(box.querySelectorAll(".finding").length >= 2);
  // clean copy
  input.value = "Many people add a short evening session to their relaxation routine.";
  run.click();
  assert.ok(box.querySelector(".claims-status").classList.contains("is-clean"));
  assert.equal(box.querySelectorAll(".finding").length, 0);
});

test("Vault: an edition without claims has three tabs and ignores a claims deep link", () => {
  const env = loadUi(["ui/vault.js"]);
  const b = generic();
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.vault.mount(host, makeCtx(env, b), { sub: "claims", params: {} });
  assert.deepEqual(host.querySelectorAll('[role="tab"] .tab-label').map((x) => x.textContent), ["Cards", "Studies", "Myth or Fact"]);
  assert.equal(host.querySelector('[role="tab"][aria-selected="true"] .tab-label').textContent, "Cards");
  assert.equal(host.querySelector(".claim-card"), null);
});

test("Vault: the Studies tab resolves claim topic names, shows directions and marks studies that are not verified yet", () => {
  const env = loadUi(["ui/vault.js"]);
  const ctx = makeCtx(env, bundle);
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.vault.mount(host, ctx, { sub: "studies", params: {} });
  const cards = host.querySelectorAll(".study");
  assert.equal(cards.length, bundle.vault.studies.length);
  const unverified = bundle.vault.studies.filter((s) => s.verified !== true).length;
  assert.equal(cards.filter((c) => /Not verified yet/.test(c.textContent)).length, unverified);
  const claimLink = bundle.vault.links.find((l) => l.tactic_id === "pbm-muscle-recovery");
  const study = bundle.vault.studies.find((s) => s.id === claimLink.study_id);
  const card = cards.find((c) => c.textContent.includes(study.title));
  assert.ok(card, "the study card");
  const topicName = bundle.claims.topics.find((t) => t.id === "pbm-muscle-recovery").name_en;
  assert.ok(card.querySelector(".study-links").textContent.includes(topicName), "the claim topic is named, not shown as an id");
  assert.ok(!card.textContent.includes("pbm-muscle-recovery"));
  assert.match(card.querySelector(".study-links").textContent, new RegExp("\\((supports|mixed results|contradicts|background)\\)"));
  assert.match(host.querySelector(".note-card").textContent, /Not verified yet/);
});

test("Home: the edition banner names the edition and the generic edition has none", () => {
  const env = loadUi(["ui/shell.js", "ui/home.js"]);
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.home.mount(host, makeCtx(env, bundle));
  const banner = host.querySelector(".edition-banner");
  assert.ok(banner);
  assert.equal(banner.querySelector(".edition-name").textContent, bundle.vertical.edition_en);
  assert.equal(banner.querySelector(".edition-tagline").textContent, bundle.vertical.tagline_en);
  assert.deepEqual(banner.querySelectorAll("a.btn").map((a) => a.getAttribute("href")), ["#/vault/claims", "#/vault/claims?focus=check"]);
  assert.match(banner.textContent, /Non-medical wellness device/);
  assert.match(banner.textContent, /confirmed by the brand/);

  const cs = env.document.createElement("div");
  env.DK.ui.home.mount(cs, makeCtx(env, bundle, "cs"));
  assert.equal(cs.querySelector(".edition-name").textContent, bundle.vertical.edition_cs);
  assert.equal(cs.querySelector(".edition-tagline").textContent, bundle.vertical.tagline_cs);

  const plain = env.document.createElement("div");
  env.DK.ui.home.mount(plain, makeCtx(env, generic()));
  assert.equal(plain.querySelector(".edition-banner"), null);
  const page = plain.querySelector(".page.home");
  assert.deepEqual(page.children.map((c) => c.className.split(" ").slice(0, 2).join(" ")), ["card hero", "home-grid", "stat-grid-4", "", "card xp-panel"], "hero, quests and chest, four stats, modes, XP panel");
  assert.equal(host.querySelector(".page.home").children.length, 6, "the banner is the only addition");
});

test("About: the edition card, claims check, glossary and the regulatory note are marked as not legal advice; the generic page lacks them", () => {
  const env = loadUi(["ui/about.js"]);
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.about.mount(host, makeCtx(env, bundle));
  assert.ok(host.querySelector(".edition-card"));
  assert.equal(host.querySelector(".edition-card .edition-name").textContent, bundle.vertical.edition_en);
  const terms = host.querySelectorAll(".glossary-item dt").map((x) => x.textContent);
  assert.deepEqual(terms, bundle.vertical.glossary.map((g) => g.term_en));
  assert.ok(host.querySelector(".glossary-item dd").textContent.includes(bundle.vertical.glossary[0].def_en));
  const reg = host.querySelector(".reg-note");
  assert.equal(reg.getAttribute("role"), "note");
  assert.match(reg.querySelector(".legal-chip").textContent, /Not legal advice/);
  assert.ok(reg.textContent.includes(bundle.vertical.regulatory_note_en));
  assert.ok(host.querySelector(".claims-about"));
  assert.match(host.querySelector("#shield-h").closest("section").textContent, /claims check without errors/);

  const cs = env.document.createElement("div");
  env.DK.ui.about.mount(cs, makeCtx(env, bundle, "cs"));
  assert.deepEqual(cs.querySelectorAll(".glossary-item dt").map((x) => x.textContent), bundle.vertical.glossary.map((g) => g.term_cs));
  assert.match(cs.querySelector(".reg-note .legal-chip").textContent, /Není to právní poradenství/);

  const plain = env.document.createElement("div");
  env.DK.ui.about.mount(plain, makeCtx(env, generic()));
  for (const sel of [".edition-card", ".glossary-list", ".reg-note", ".claims-about"]) assert.equal(plain.querySelector(sel), null, sel);
  assert.doesNotMatch(plain.querySelector("#shield-h").closest("section").textContent, /claims check/);
});

test("Forge: the pack header shows the claims profile pill and the edition sample note; issue codes get readable names", () => {
  const env = loadUi(["ui/forge.js"]);
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.forge.mount(host, makeCtx(env, bundle));
  const pill = host.querySelector(".profile-pill");
  assert.ok(pill);
  assert.match(pill.textContent, /Claims profile: Wellness/);
  assert.match(host.querySelector(".sim-note").textContent, /not confirmed any fact/);
  assert.match(host.querySelector(".sim-note").textContent, /MITO LIGHT/);
  assert.match(host.querySelector(".pack-head h2").textContent, /Sample pack: MITO LIGHT/);

  const cs = env.document.createElement("div");
  env.DK.ui.forge.mount(cs, makeCtx(env, bundle, "cs"));
  assert.match(cs.querySelector(".profile-pill").textContent, /Profil tvrzení: Wellness/);
  assert.match(cs.querySelector(".sim-note").textContent, /nepotvrdila/);

  const plain = env.document.createElement("div");
  const b = generic();
  b.forge_samples = [clone(bundle.forge_samples[1])];
  b.forge_samples[0].brief.vertical = null; b.forge_samples[0].brief.claims_profile = "general"; b.forge_samples[0].summary.claims_profile = "general";
  env.DK.ui.forge.mount(plain, makeCtx(env, b));
  assert.equal(plain.querySelector(".profile-pill"), null, "no pill for the general profile");
  assert.doesNotMatch(plain.querySelector(".sim-note").textContent, /not confirmed any fact/);
});

test("Forge: issue names for the claims codes show next to the raw code", () => {
  const env = loadUi(["ui/forge.js"]);
  const b = clone(bundle);
  const pack = b.forge_samples.find((p) => p.brief.lang === "en");
  pack.items[0].issues.push({ severity: "error", code: "CLAIM_MEDICAL", message: "Medical claim (test).", where: "x" }, { severity: "info", code: "THERAPY_WORD", message: "Therapy.", where: "y" });
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.forge.mount(host, makeCtx(env, b));
  const items = host.querySelectorAll(".issue-list .issue");
  const medical = items.find((li) => li.querySelector(".issue-code").textContent === "CLAIM_MEDICAL");
  assert.equal(medical.querySelector(".issue-name").textContent, "Medical claim");
  const therapy = items.find((li) => li.querySelector(".issue-code").textContent === "THERAPY_WORD");
  assert.equal(therapy.querySelector(".issue-name").textContent, "The word therapy");
  const placeholder = items.find((li) => li.querySelector(".issue-code").textContent === "PLACEHOLDER_OPEN");
  assert.equal(placeholder.querySelector(".issue-name"), null, "codes without a name keep their old look");
});

test("Forge: the brief keeps the vertical, the claims profile and the safety note and sends them", () => {
  const shared = forge._shared;
  const sample = bundle.forge_samples.find((p) => p.brief.lang === "en");
  const before = JSON.stringify(shared.brief);
  shared.seeded = false;
  forge.seedBrief(null, Object.assign({}, sample.brief, { safety_note: "Protect your eyes." }));
  assert.deepEqual([shared.brief.vertical, shared.brief.claims_profile, shared.brief.safety_note], ["pbm", "wellness", "Protect your eyes."]);
  const api = forge.briefToApi(shared.brief);
  assert.equal(api.vertical, "pbm");
  assert.equal(api.claims_profile, "wellness");
  assert.equal(api.safety_note, "Protect your eyes.");
  assert.deepEqual(api.facts, sample.brief.facts);
  const general = forge.briefToApi(Object.assign({}, shared.brief, { claims_profile: "general", safety_note: "  ", vertical: null }));
  assert.equal(general.claims_profile, "general");
  assert.ok(!("vertical" in general) && !("safety_note" in general), "empty fields are left out");
  Object.assign(shared.brief, JSON.parse(before));
  shared.seeded = false;
});

test("Forge: the live form has a claims profile select with General and Wellness, and the safety note follows it", () => {
  const env = loadUi(["ui/forge.js"]);
  const ctx = makeCtx(env, bundle);
  ctx.live = () => ({ enabled: true, formats: [{ id: "instagram_caption", name_en: "Instagram caption", platform: "instagram" }] });
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  const shared = env.DK.ui.forge._shared;
  shared.seeded = false;
  env.DK.ui.forge.mount(host, ctx);
  const select = host.querySelector("#bf-profile");
  assert.ok(select, "a visible claims profile select");
  assert.deepEqual(select.querySelectorAll("option").map((o) => o.getAttribute("value")), ["general", "wellness"]);
  assert.equal(select.querySelectorAll("option").map((o) => o.textContent).join("|"), "General|Wellness (non-medical device)");
  assert.equal(shared.brief.claims_profile, "wellness", "seeded from the MITO LIGHT sample");
  assert.equal(shared.brief.vertical, "pbm");
  const note = host.querySelector("#bf-safety_note").closest(".field");
  assert.equal(note.hasAttribute("hidden"), false, "visible with the wellness profile");
  select.value = "general";
  select.dispatchEvent({ type: "change", target: select });
  assert.equal(shared.brief.claims_profile, "general");
  assert.equal(note.hasAttribute("hidden"), true, "hidden for the general profile");
});

test("an edition card of the Forge, Guru or a plan is recognised by its brief", () => {
  assert.equal(forge.isEdition(bundle.forge_samples[0]), true);
  assert.equal(forge.isEdition(bundle.guru_samples[0]), true);
  assert.equal(forge.isEdition({ brief: { claims_profile: "general" }, summary: { claims_profile: "general" } }), false);
  assert.equal(forge.isEdition({ brief: {} }), false);
  assert.equal(forge.isEdition(null), false);
});
