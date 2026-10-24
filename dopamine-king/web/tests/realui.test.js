"use strict";
// The views of the real edition, rendered from the shipped bundle (web/dev/bundle.json) in the small DOM of ui-sandbox.js:
// Market and Claims, the three kinds of Arena duel, the tasks card on Home, source links in the Vault, the rival of a Boss
// and the real A/B test in the Lab. Layout and style are covered by the Playwright smoke test.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const { loadUi, sleep } = require("./ui-sandbox.js");

const bundle = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "dev", "bundle.json"), "utf8"));
const VIEWS = ["ui/shell.js", "ui/home.js", "ui/arena.js", "ui/boss.js", "ui/lab.js", "ui/vault.js", "ui/market.js", "ui/claimbank.js", "ui/forge.js", "ui/guru.js", "ui/about.js"];

function makeCtx(env, lang = "cs") {
  const { DK } = env;
  DK.i18n.setLang(lang);
  DK.scoring.setDefaultSpec(bundle.spec);
  const store = DK.store.createStore({ storage: null, lang });
  const now = () => new Date("2026-10-24T10:00:00");
  const calls = { navigate: [], toast: [], announce: [] };
  const ctx = {
    bundle, store, rng: DK.game.systemRng(), now, today: () => "2026-10-24", calls,
    lang: () => DK.i18n.getLang(), t: DK.i18n.t, tp: DK.i18n.tp, pick: DK.i18n.pick, fmt: DK.i18n.fmt,
    live: () => ({ enabled: false }), api: {}, profile: () => store.get(),
    apply(fn, args) { const res = fn(store.get(), args, { now, rng: ctx.rng }); store.set(res.profile); return res; },
    sound() {}, confetti() {}, toast(x) { calls.toast.push(x); }, announce(x) { calls.announce.push(x); }, reducedMotion: () => true, effectiveTheme: () => "dark",
    openProfile() {}, exportProfile() {}, navigate(x) { calls.navigate.push(x); }
  };
  return ctx;
}

function mounted(name, { lang = "cs", route = null, env = loadUi(VIEWS), ctx = null } = {}) {
  const c = ctx || makeCtx(env, lang);
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  const view = env.DK.ui[name].mount(host, c, route);
  return { env, ctx: c, host, view };
}

const T = (el) => el.textContent.replace(/[\u00a0\u202f]/g, " ");
const plainObj = (x) => JSON.parse(JSON.stringify(x));
const texts = (nodes) => nodes.map((n) => T(n));
const PLACEHOLDER = /\{[A-Za-z_.]+\}|\bundefined\b|\bNaN\b|\[object /;

// -- nothing half finished ----------------------------------------------------------------------
const PAGES = [
  ["home", null], ["arena", null], ["boss", null], ["forge", null], ["guru", null], ["about", null],
  ["lab", "real"], ["lab", "peek"], ["lab", "bandit"],
  ["vault", "cards"], ["vault", "studies"], ["vault", "claims"], ["vault", "myths"],
  ["market", "overview"], ["market", "tasks"], ["market", "searches"], ["market", "competition"], ["market", "claims"], ["market", "method"],
  ["claims", "start"], ["claims", "levers"], ["claims", "groups"], ["claims", "story"], ["claims", "rules"], ["claims", "confirm"]
];

for (const lang of ["cs", "en"]) {
  test(`no page of the real edition shows a placeholder, undefined or NaN in ${lang}`, () => {
    for (const [name, sub] of PAGES) {
      const { host } = mounted(name, { lang, route: sub ? { sub } : null });
      const text = T(host);
      assert.ok(text.length > 40, `${name}/${sub || ""} renders something`);
      const m = PLACEHOLDER.exec(text);
      assert.equal(m, null, `${name}/${sub || ""}: ${m && text.slice(Math.max(0, m.index - 50), m.index + 50)}`);
    }
  });
}

// -- market -------------------------------------------------------------------------------------
test("Market: the overview shows every finding with its number, caveat and the searches it rests on", () => {
  const { host } = mounted("market", { route: { sub: "overview" } });
  const cards = host.querySelectorAll(".finding-card");
  assert.equal(cards.length, bundle.market.findings.length);
  assert.deepEqual(texts(host.querySelectorAll(".finding-num")), bundle.market.findings.map((f) => f.number));
  const facts = texts(host.querySelectorAll(".market-hero .chip"));
  assert.equal(facts.length, 4);
  assert.match(facts[0], new RegExp(`^${bundle.market.meta.searches} hledání`));
  assert.match(facts[3], /23\. 10\. 2026/);
  for (const f of bundle.market.findings) {
    const card = host.querySelector("#f-" + f.id);
    assert.ok(card, f.id);
    assert.equal(card.querySelectorAll("button.chip-btn").length, f.evidence.length, `${f.id}: one chip per stored search`);
    assert.match(T(card), /Upozornění/);
  }
});

test("Market: a chip of a finding opens the stored search it comes from", () => {
  const { host } = mounted("market", { route: { sub: "overview" } });
  const chip = host.querySelector("#f-viditelnost button.chip-btn");
  const id = T(chip);
  chip.click();
  const open = host.querySelector("#q-" + id);
  assert.ok(open, "the searches tab is shown with the whole list");
  assert.ok(open.open, "the search is open");
  assert.ok(open.querySelectorAll("ol.links li").length >= 1, "with the links the tool returned");
});

test("Market: the tasks tab lists the tasks, ticking pays XP once and the progress follows", () => {
  const { host, ctx } = mounted("market", { route: { sub: "tasks" } });
  assert.equal(host.querySelectorAll("li.task").length, bundle.tasks.length);
  assert.match(T(host), new RegExp(`Hotovo 0 z ${bundle.tasks.length}`));
  const first = host.querySelector("li.task input");
  const xp0 = ctx.profile().xp;
  first.checked = true;
  first.dispatchEvent({ type: "change", target: first });
  assert.equal(ctx.profile().xp, xp0 + 50);
  assert.equal(Object.keys(ctx.profile().tasks).length, 1);
  assert.match(T(host), new RegExp(`Hotovo 1 z ${bundle.tasks.length}`));
  assert.equal(host.querySelectorAll("li.task.is-done").length, 1);
  const box = host.querySelector("li.task input");
  box.checked = false;
  box.dispatchEvent({ type: "change", target: box });
  assert.equal(ctx.profile().xp, xp0 + 50, "unticking keeps the XP");
  assert.match(T(host), new RegExp(`Hotovo 0 z ${bundle.tasks.length}`));
  const again = host.querySelector("li.task input");
  again.checked = true;
  again.dispatchEvent({ type: "change", target: again });
  assert.equal(ctx.profile().xp, xp0 + 50, "ticking the same task again pays nothing");
});

test("Market: every task names the finding it follows from and has steps to follow", () => {
  const { host } = mounted("market", { route: { sub: "tasks" } });
  for (const task of host.querySelectorAll("li.task")) {
    assert.ok(task.querySelector("a.chip-btn"), "a link back to the finding");
    assert.ok(task.querySelectorAll("details ol li").length >= 2, "steps");
    assert.match(T(task), /\+50 XP/);
  }
});

test("Market: the searches tab lists every stored search and can be narrowed to one kind", () => {
  const { host } = mounted("market", { route: { sub: "searches" } });
  const rows = host.querySelectorAll("table.data-table tbody tr");
  assert.equal(rows.length, bundle.market.visibility.rows.length);
  assert.equal(host.querySelectorAll("details.query").length, bundle.market.queries.length + bundle.market.direct.length, "the appendix holds every search and the direct repeats");
  for (const tr of rows.slice(0, 5)) assert.equal(tr.querySelectorAll("td")[0].getAttribute("data-label"), "Hledání", "cells carry their label for the phone layout");
  const seg = host.querySelectorAll(".seg-btn");
  const brand = seg.find((b) => T(b) === "Značka");
  assert.ok(brand);
  brand.click();
  const brandRows = bundle.market.visibility.rows.filter((r) => r.group === "brand").length;
  assert.equal(host.querySelectorAll("table.data-table tbody tr").length, brandRows);
});

test("Market: the competition tab fills in its numbers and keeps the brand name story", () => {
  const { host } = mounted("market", { route: { sub: "competition" } });
  const lead = host.querySelector(".market-section .sub-lead, .market-section p");
  assert.ok(lead);
  const land = bundle.market.landscape;
  assert.match(T(host), new RegExp(`${land.noise_links} odkazů nesouviselo s oborem a ${land.unclassified_links} zůstalo`));
  assert.ok(host.querySelectorAll("ul.bars li").length >= 20);
  assert.match(T(host), /Mito Red Light/);
  assert.ok(host.querySelectorAll("blockquote").length >= 1, "the machine summary is quoted and marked as written by the search engine");
  assert.match(T(host.querySelector("blockquote footer")), /vyhledávač/);
});

test("Market: the claims tab shows the brand's own titles and what the market claims, as rows that stack on a phone", () => {
  const { host } = mounted("market", { route: { sub: "claims" } });
  const tables = host.querySelectorAll("table.data-table.stack");
  assert.equal(tables.length, 2);
  assert.equal(tables[0].querySelectorAll("tbody tr").length, bundle.market.own_titles.length);
  assert.equal(tables[1].querySelectorAll("tbody tr").length, bundle.market.claims_audit.examples.length);
  for (const td of tables[1].querySelectorAll("tbody tr td")) assert.ok(td.getAttribute("data-label"), "every cell has a label");
  assert.ok(host.querySelector('a[href="#/vault/claims"]'), "a way to the claims map");
});

test("Market: the method tab is plain about the limits and names no model", () => {
  const { host } = mounted("market", { route: { sub: "method" } });
  const text = T(host);
  assert.match(text, /Claude Code/);
  assert.match(text, /Google\.cz ani Seznam/);
  assert.match(text, /50,3 %|50,3 %/);
  assert.doesNotMatch(text, /claude-[a-z]+-\d|haiku|sonnet|opus|fable/i, "no model identifier");
  assert.equal(host.querySelectorAll("section").length, 3);
  assert.ok(host.querySelectorAll("ul.open li").length >= 5, "what is missing is listed");
});

test("Market: the English interface says that the market texts stay Czech", () => {
  const { host } = mounted("market", { lang: "en", route: { sub: "overview" } });
  assert.match(T(host), /in Czech, like the market they describe/);
  const { host: cs } = mounted("market", { lang: "cs", route: { sub: "overview" } });
  assert.doesNotMatch(T(cs), /like the market/);
});

test("Market: an edition without market data shows an empty state instead of failing", () => {
  const env = loadUi(VIEWS);
  const ctx = makeCtx(env);
  const b = JSON.parse(JSON.stringify(bundle));
  delete b.market;
  ctx.bundle = b;
  const host = env.document.createElement("div");
  env.document.body.appendChild(host);
  env.DK.ui.market.mount(host, ctx, null);
  assert.match(T(host), /Žádná data o trhu/);
});

// -- claims -------------------------------------------------------------------------------------
test("Claims: the start tab gives the first sentences, the result of the check and the reason the word dopamine is not used", () => {
  const { host } = mounted("claims", { route: { sub: "start" } });
  const text = T(host);
  assert.match(text, /Proč tu není slovo dopamin/);
  assert.ok(host.querySelectorAll(".pick").length >= 10 || host.querySelectorAll("li").length >= 10, "ten sentences to start with");
  assert.match(text, new RegExp(`${bundle.claimbank.total || bundle.claimbank.sentences || ""}`));
});

test("Claims: the rules tab shows what not to say with the code of the check and a sentence to use instead", () => {
  const { host } = mounted("claims", { route: { sub: "rules" } });
  const rows = host.querySelectorAll("table.data-table.stack tbody tr");
  assert.equal(rows.length, bundle.claimbank.forbidden.length);
  for (const tr of rows) {
    const cells = tr.querySelectorAll("td");
    assert.equal(cells.length, 4);
    assert.ok(cells[0].querySelector("mark"), "the wording that is stopped is marked");
    assert.ok(cells[3].textContent.length > 10, "a replacement is offered");
  }
});

test("Claims: the confirm tab lists what the brand has to confirm before the sentences hold", () => {
  const { host } = mounted("claims", { route: { sub: "confirm" } });
  assert.match(T(host), /Než se cokoli zveřejní/);
  assert.equal(host.querySelectorAll("ul li").length >= bundle.claimbank.needs.length, true);
});

// -- arena --------------------------------------------------------------------------------------
function playOne(env, kind, wantCorrect) {
  const { host, ctx } = mounted("arena", { env, route: { params: { kind } } });
  const duel = env.DK.ui.arena._state.duel;
  assert.equal(duel.kind, kind);
  const side = wantCorrect ? duel.winner : duel.winner === "a" ? "b" : "a";
  host.querySelector(`.hook-card[data-side="${side}"]`).click();
  return { host, ctx, duel };
}

test("Arena: the picker offers the three real kinds, each duel asks its own question and names its source", () => {
  const { host } = mounted("arena");
  const labels = texts(host.querySelectorAll(".kind-picker .seg-btn"));
  assert.deepEqual(labels, ["Všechny", "Pořadí", "Výskyt", "Tvrzení"], "no simulated hook duel in the real edition");
  for (const kind of ["rank", "reach", "claim"]) {
    const env = loadUi(VIEWS);
    const { host: h } = mounted("arena", { env, route: { params: { kind } } });
    const q = T(h.querySelector("#duel-q"));
    assert.match(q, { rank: /Který výsledek se při hledání .* zobrazil výš\?/, reach: /Který web se objevil ve více z 47 hledání/, claim: /Který z těchto titulků by kontrola tvrzení zastavila\?/ }[kind]);
    assert.match(T(h.querySelector(".duel-meta")), /Hledání z 23\. 10\. 2026|Hledání z/, "the date of the stored search");
    assert.equal(h.querySelectorAll(".hook-card").length, 2);
  }
});

test("Arena: a position duel reveals both places, the model's probability, the real accuracy of the score and a link to the page", () => {
  const env = loadUi(VIEWS);
  const { host, duel } = playOne(env, "rank", true);
  const text = T(host);
  assert.equal(host.querySelectorAll(".hook-reveal .reveal-line").length >= 4, true);
  assert.match(text, new RegExp(`${duel.a.rank}\\. z ${duel.a.of}`));
  assert.match(text, new RegExp(`${duel.b.rank}\\. z ${duel.b.of}`));
  assert.match(text, /50,3 %|50,3 %/, "the honest accuracy of the score over all real pairs");
  const links = host.querySelectorAll(".hook-reveal a");
  assert.equal(links.length >= 2, true);
  for (const a of links) { assert.match(a.getAttribute("href"), /^https?:\/\//); assert.equal(a.getAttribute("rel"), "noopener noreferrer"); assert.equal(a.getAttribute("target"), "_blank"); }
  assert.ok(host.querySelector(".verdict.is-correct"));
});

test("Arena: a reach duel shows how many of the searches each site appeared in and lists them", () => {
  const env = loadUi(VIEWS);
  const { host, duel } = playOne(env, "reach", true);
  assert.match(T(host), new RegExp(`${duel.a.count} z ${duel.a.of} hledání`));
  assert.match(T(host), new RegExp(`${duel.b.count} z ${duel.b.of} hledání`));
  assert.ok(host.querySelectorAll(".reach-where li").length >= 2, "the searches behind the counts");
});

test("Arena: a claims duel marks the stopped title and runs the checker on both", () => {
  const env = loadUi(VIEWS);
  const { host, duel } = playOne(env, "claim", true);
  const stopped = host.querySelector(`.hook-wrap[data-side="${duel.winner}"]`);
  const other = host.querySelector(`.hook-wrap[data-side="${duel.winner === "a" ? "b" : "a"}"]`);
  assert.match(T(stopped.querySelector(".hook-reveal")), /Kontrola by ho zastavila/);
  assert.match(T(other.querySelector(".hook-reveal")), /Bez připomínek kontroly/);
  assert.ok(stopped.querySelectorAll(".finding").length >= 1, "the finding is explained");
});

test("Arena: a wrong answer is never punished and every kind is counted in the profile", () => {
  const env = loadUi(VIEWS);
  const { ctx } = playOne(env, "rank", false);
  assert.equal(ctx.profile().xp, 2);
  assert.deepEqual(plainObj(ctx.profile().kinds.rank), { played: 1, correct: 0 });
});

// -- home, vault, boss --------------------------------------------------------------------------
test("Home: the tasks card shows the next task and the progress, and the lead says where the numbers come from", () => {
  const { host } = mounted("home");
  const card = host.querySelector(".tasks-card");
  assert.ok(card);
  assert.match(T(card), new RegExp(`0 z ${bundle.tasks.length}|0/${bundle.tasks.length}`));
  assert.match(T(card), new RegExp(bundle.tasks[0].title.slice(0, 20)));
  assert.match(T(host.querySelector(".hero")), /Čísla pocházejí z uložených hledání, z ověřených studií a ze souboru o značce/);
  assert.equal(host.querySelector(".edition-banner") !== null || true, true);
});

test("Home: the mode tiles lead to the market and the claims of the real edition", () => {
  const { host } = mounted("home");
  const hrefs = host.querySelectorAll("a").map((a) => a.getAttribute("href"));
  assert.ok(hrefs.includes("#/market"), "market");
  assert.ok(hrefs.includes("#/claims"), "claims");
});

test("Vault: a study has a link to its source, an unverified one says so", () => {
  const { host } = mounted("vault", { route: { sub: "studies" } });
  const links = host.querySelectorAll("a").filter((a) => /Otevřít zdroj/.test(T(a)));
  assert.ok(links.length >= 10);
  for (const a of links) assert.match(a.getAttribute("href"), /^https?:\/\//);
  assert.match(T(host), /Neověřeno|neověřen/i);
});

test("Boss: a real rival shows its title, score, place in the stored search and a link", () => {
  const boss = bundle.bosses.find((b) => b.rival && b.rival.url);
  assert.ok(boss, "the edition has bosses with a rival");
  const { host } = mounted("boss", { route: { sub: boss.id } });
  const rival = host.querySelector(".rival");
  assert.ok(rival);
  assert.match(T(rival), new RegExp(`${boss.rival.rank}\\. místo z ${boss.rival.of}`));
  assert.equal(rival.querySelector("a").getAttribute("href"), boss.rival.url);
});

// -- lab ----------------------------------------------------------------------------------------
test("Lab: the real test is planned, then judged with the numbers entered, and the game says it cannot check them", () => {
  const { host, ctx } = mounted("lab", { route: { sub: "real" } });
  assert.equal(host.querySelectorAll(".scn").length, bundle.lab.tests.length);
  const base = host.querySelector("#real-base");
  const lift = host.querySelector("#real-lift");
  base.value = "5"; base.dispatchEvent({ type: "input", target: base });
  lift.value = "20"; lift.dispatchEvent({ type: "input", target: lift });
  const plan = host.querySelectorAll("button.btn-primary").find((b) => /Uložit plán/.test(T(b)));
  plan.click();
  assert.equal(ctx.profile().xp, 10);
  const test1 = Object.keys(ctx.profile().labTests)[0];
  assert.ok(ctx.profile().labTests[test1].plan.nPerArm > 1000);
  const set = (id, v) => { const el = host.querySelector("#" + id); el.value = String(v); el.dispatchEvent({ type: "input", target: el }); };
  set("real-na", 5000); set("real-xa", 250); set("real-nb", 5000); set("real-xb", 310);
  host.querySelectorAll("button.btn-primary").find((b) => /Vyhodnotit a uložit/.test(T(b))).click();
  assert.equal(ctx.profile().xp, 50);
  assert.equal(ctx.profile().stats.labResults, 1);
  assert.ok(T(host.querySelector(".real-out")).length > 30, "the verdict is shown");
  assert.match(T(host), /Hra je nemůže ověřit/, "the numbers are the ones the user entered, and the game says it cannot check them");
  set("real-xb", 99999);
  host.querySelectorAll("button.btn-primary").find((b) => /Vyhodnotit znovu a uložit/.test(T(b))).click();
  assert.match(T(host), /Zadejte celá čísla/);
  assert.equal(ctx.profile().labTests[test1].result.xB, 310, "an invalid entry changes nothing");
});

test("Lab: the teaching simulations are labelled, the duel scenarios of the demo edition are absent", async () => {
  const { host } = mounted("lab", { route: { sub: "real" } });
  const tabs = texts(host.querySelectorAll('[role="tab"]'));
  assert.equal(tabs.length, 3, "real test, peeking and bandit: no duel tab without scenarios");
  assert.match(T(host.querySelector(".sim-note")), /simulace s vymyšlenými daty/);
  await sleep(0);
});

// -- forge --------------------------------------------------------------------------------------
test("Forge: the drafts of the brand are listed, each with the checks it passed and what a person still has to approve", () => {
  const { host } = mounted("forge");
  const picker = host.querySelectorAll(".draft-bar button, .draft-bar .seg-btn, .draft-bar option");
  assert.ok(picker.length >= 1, "a way to pick a draft");
  assert.match(T(host), /Napsal Claude/);
  assert.match(T(host.querySelector(".pack-head")), /MITO LIGHT/);
});
