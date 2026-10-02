// Browser smoke test for the built game file. Not part of `node --test`: it needs Chromium.
//
//   NODE_PATH=/opt/node22/lib/node_modules node web/tests/smoke.playwright.mjs [options]
//
//   --file <html>     the built file (default web/dist/dopamine-king.html)
//   --shots <dir>     where screenshots go (default: a folder under the system temp directory)
//   --only <WxH:scheme>   run one combination, for example 390x844:dark
//   --skip-live       skip the live mode check (a tiny local server stands in for kingctl serve)
//   --live-only       run only the live mode check
//   --skip-generic    skip the check of the generic edition (it needs python3 to build a second file)
//
// It uses the Chromium that is already installed (never downloads one). Every run fails on any console error,
// page error, failed request or request that leaves the machine. Per combination (390x844 and 1280x800, dark and
// light) it plays 3 Arena rounds, types a hook in a Boss fight and checks the meter moves, opens a chest, runs a Lab
// duel, switches language, and screenshots every view in both languages. Extra checks: no horizontal scroll at 360px,
// Tab order and visible focus rings, the break card (fake clock), reduced motion, and live mode.
// The default build is the MITO LIGHT edition, so every combination also checks the claims features: the Boss claims
// panel (a medical claim is an error, a compliant hook passes and wins), the Vault Claims map and its "Check your own
// text" box, the Home banner, and the Studies tab marking studies that are not verified yet. A second build of the
// generic edition (python3 scripts/build_web.py --vertical general) must show none of it; --skip-generic turns that off.
// `node --test web/tests/` may pick this file up on older Node versions. It needs a browser, so it only runs when started directly.
if (process.env.NODE_TEST_CONTEXT) {
  console.log("smoke.playwright.mjs is a browser test: run it directly with node, skipping under node --test");
  process.exit(0);
}

import { createRequire } from "node:module";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..", "..");

// -- options --------------------------------------------------------------------------------------------------
const argv = process.argv.slice(2);
const opt = (name, fallback) => { const i = argv.indexOf(name); return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback; };
const FILE = path.resolve(opt("--file", path.join(ROOT, "web", "dist", "dopamine-king.html")));
const SHOTS = path.resolve(opt("--shots", path.join(os.tmpdir(), "dopamine-king-shots")));
const ONLY = opt("--only", null);
const SKIP_LIVE = argv.includes("--skip-live");
const LIVE_ONLY = argv.includes("--live-only");
const SKIP_GENERIC = argv.includes("--skip-generic");
const CHROMIUM = process.env.CHROMIUM_PATH || "/opt/pw-browsers/chromium";

function loadPlaywright() {
  const places = [import.meta.url, "file:///opt/node22/lib/node_modules/noop.js"];
  for (const p of places) {
    try { return createRequire(p)("playwright"); } catch (e) { /* try the next place */ }
  }
  throw new Error("Cannot find the playwright package. Run with NODE_PATH=/opt/node22/lib/node_modules");
}
const { chromium } = loadPlaywright();

if (!fs.existsSync(FILE)) { console.error(`Built file not found: ${FILE}\nBuild it first: python3 scripts/build_web.py`); process.exit(2); }
fs.mkdirSync(SHOTS, { recursive: true });

// -- tiny assertion collector -----------------------------------------------------------------------------------
const failures = [];
let checks = 0;
function check(ok, message) {
  checks += 1;
  if (!ok) { failures.push(message); console.log("  FAIL " + message); }
}
const log = (m) => console.log(m);

const COMBOS = [
  { w: 390, h: 844, scheme: "dark" }, { w: 390, h: 844, scheme: "light" },
  { w: 1280, h: 800, scheme: "dark" }, { w: 1280, h: 800, scheme: "light" }
].filter((c) => !LIVE_ONLY && (!ONLY || `${c.w}x${c.h}:${c.scheme}` === ONLY));

const VIEWS = [
  ["home", "home"], ["arena", "arena"], ["boss", "boss"], ["lab", "lab"], ["lab-peek", "lab/peek"], ["lab-bandit", "lab/bandit"],
  ["vault-cards", "vault/cards"], ["vault-studies", "vault/studies"], ["vault-claims", "vault/claims"], ["vault-myths", "vault/myths"],
  ["forge", "forge"], ["guru", "guru"], ["about", "about"]
];

// -- page helpers -----------------------------------------------------------------------------------------------
function watch(page, label, allowedOrigin, ignore = []) {
  const problems = [];
  page.on("console", (m) => { if (m.type() === "error" && !ignore.some((re) => re.test(m.text()))) problems.push(`${label} console error: ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`${label} page error: ${e.message}`));
  page.on("requestfailed", (r) => problems.push(`${label} request failed: ${r.url()}`));
  page.on("request", (r) => {
    const u = r.url();
    if (/^(file:|data:|blob:|about:)/.test(u)) return;
    if (allowedOrigin && u.startsWith(allowedOrigin)) return;
    problems.push(`${label} request leaves the machine: ${u}`);
  });
  return problems;
}
function flush(problems) {
  const list = problems.splice(0, problems.length);
  check(list.length === 0, list.join(" | ") || "no problems");
}
async function open(browser, combo, extra = {}) {
  const context = await browser.newContext({
    viewport: { width: combo.w, height: combo.h }, colorScheme: combo.scheme, deviceScaleFactor: 1,
    locale: extra.locale || "en-US", reducedMotion: extra.reducedMotion || "no-preference", acceptDownloads: true
  });
  const page = await context.newPage();
  return { context, page };
}
async function go(page, route) {
  await page.evaluate((r) => { location.hash = "#/" + r; }, route);
  await page.waitForSelector("#main h1", { timeout: 8000 });
  await page.waitForTimeout(350);
}
async function boot(page, url) {
  await page.goto(url || "file://" + FILE);
  await page.waitForSelector("#main h1", { timeout: 10000 });
}
const profile = (page) => page.evaluate(() => { try { return JSON.parse(localStorage.getItem("dk.profile.v1")); } catch (e) { return null; } });
const shot = (page, name) => page.screenshot({ path: path.join(SHOTS, name + ".png"), fullPage: true });
async function overflow(page) {
  return page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }));
}
async function setLang(page, lang) {
  await page.click(`.lang-seg .seg-btn:has-text("${lang.toUpperCase()}")`);
  await page.waitForFunction((l) => document.documentElement.lang === l, lang);
  await page.waitForTimeout(350);
}

// -- game flows -------------------------------------------------------------------------------------------------
async function arenaFlow(page, rounds, tag) {
  await go(page, "arena");
  for (let i = 0; i < rounds; i++) {
    const side = i === 1 ? "b" : "a";
    await page.waitForSelector(`.hook-card[data-side="${side}"]`, { timeout: 6000 });
    await page.click(`.hook-card[data-side="${side}"]`);
    await page.waitForSelector(".verdict", { timeout: 8000 });
    const title = ((await page.textContent(".result-title")) || "").trim();
    check(title.length > 0, `${tag} arena round ${i + 1} shows a result`);
    check((await page.locator(".sim-chip, .sim-note").count()) > 0, `${tag} arena reveal is labelled as simulated`);
    if (i === 0) await shot(page, `${tag}-flow-arena-reveal`);
    await page.click(".next-btn");
    await page.waitForSelector(".verdict", { state: "detached", timeout: 6000 });
  }
  const p = await profile(page);
  check(p && p.stats.arenaPlayed === rounds, `${tag} profile counts ${rounds} arena rounds (got ${p && p.stats.arenaPlayed})`);
  check(p && p.xp > 0, `${tag} arena rounds earned XP`);
}

async function bossFlow(page, tag) {
  await go(page, "boss");
  await page.waitForSelector(".boss-card", { timeout: 5000 });
  await page.locator(".boss-card").first().click();
  await page.waitForSelector("#hook-input", { timeout: 5000 });
  const meter = ".score-meter [role=meter]";
  const before = Number(await page.getAttribute(meter, "aria-valuenow"));
  await page.type("#hook-input", "7 mistakes every beginner runner makes (and how to fix them)", { delay: 3 });
  await page.waitForFunction((sel) => Number(document.querySelector(sel).getAttribute("aria-valuenow")) > 5, meter, { timeout: 5000 });
  const mid = Number(await page.getAttribute(meter, "aria-valuenow"));
  check(mid > before, `${tag} boss meter moves while typing (${before} to ${mid})`);
  await shot(page, `${tag}-flow-boss-typed`);
  await page.fill("#hook-input", "You will NOT BELIEVE this SHOCKING trick!!! Guaranteed 100% results, doctors hate it");
  await page.waitForFunction((sel) => /Broken|Rozbit/i.test((document.querySelector(sel) || {}).textContent || ""), ".shield-state", { timeout: 5000 });
  const risky = Number(await page.getAttribute(meter, "aria-valuenow"));
  check(Number.isFinite(risky), `${tag} boss meter still reads a number for a risky hook (${risky})`);
  await page.fill("#hook-input", "7 mistakes every beginner runner makes (and how to fix them)");
  await page.waitForTimeout(500);
  await page.click(".attack-btn");
  await page.waitForSelector(".fight-result", { timeout: 8000 });
  check((await page.locator(".fight-result").count()) === 1, `${tag} boss fight ends with a result`);
  await shot(page, `${tag}-flow-boss-result`);
}

async function vaultFlow(page, tag) {
  await go(page, "vault");
  const before = await profile(page);
  check(before && before.chestsReady >= 1, `${tag} a welcome chest is waiting`);
  await page.click(".chest-panel .btn-primary");
  await page.waitForSelector(".chest-dialog .flip.is-flipped", { timeout: 6000 });
  await page.waitForTimeout(800);
  await shot(page, `${tag}-flow-chest`);
  check((await page.locator(".chest-dialog .loot-card").count()) === 1, `${tag} the chest shows a card`);
  await page.click(".chest-dialog .stage-actions .btn-ghost");
  await page.waitForSelector(".chest-dialog", { state: "detached", timeout: 4000 });
  const after = await profile(page);
  check(after.deck.length >= 1, `${tag} the opened card is in the deck`);
  check(after.chestsReady === before.chestsReady - 1, `${tag} one chest was used`);
  check(after.stats.chests === 1, `${tag} chest count is 1`);
}

async function labFlow(page, tag) {
  await go(page, "lab");
  await page.click(".lab-controls-grid .btn-primary");
  await page.waitForSelector(".decide-btn:not([disabled])", { timeout: 30000 });
  const text = await page.textContent(".lab-results");
  check(/p\s*[=<]|p\s*hodnot/i.test(text || ""), `${tag} lab results show a p value`);
  await page.locator(".decide-btn").first().click();
  await page.waitForSelector(".truth-card", { timeout: 6000 });
  await shot(page, `${tag}-flow-lab-truth`);
  const p = await profile(page);
  check(p.stats.labPlayed >= 1, `${tag} the Lab decision is counted`);
}

// Myth or Fact: keyboard (M, Enter), buttons, and a mouse swipe on the card.
async function mythFlow(page, tag) {
  await go(page, "vault/myths");
  await page.waitForSelector(".myth-card");
  const before = (await profile(page)).stats.mythsPlayed;
  await page.keyboard.press("m");
  await page.waitForSelector("#myth-result", { timeout: 4000 });
  check((await page.locator("#myth-result .ref, #myth-result p.small.muted").count()) >= 1, `${tag} a myth answer explains itself and shows the caveat`);
  await shot(page, `${tag}-flow-myth-answer`);
  await page.keyboard.press("Enter");
  await page.waitForSelector("#myth-result", { state: "detached", timeout: 4000 });
  await page.click(".myth-btn-fact");
  await page.waitForSelector("#myth-result", { timeout: 4000 });
  await page.click("#myth-result .btn-primary");
  await page.waitForSelector("#myth-result", { state: "detached", timeout: 4000 });
  const box = await page.locator(".myth-card").boundingBox();
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 160, box.y + box.height / 2 + 6, { steps: 8 });
  await page.mouse.up();
  await page.waitForSelector("#myth-result", { timeout: 4000 });
  const after = await profile(page);
  check(after.stats.mythsPlayed === before + 3, `${tag} three Myth or Fact answers were counted (${before} to ${after.stats.mythsPlayed})`);
  check(after.mythsSeen.length === 3, `${tag} seen cards are remembered`);
}

async function languageFlow(page, tag) {
  await go(page, "home");
  const en = {
    h1: await page.textContent("#main h1"), nav: await page.textContent(".nav-link >> nth=0"), lang: await page.evaluate(() => document.documentElement.lang)
  };
  await setLang(page, "cs");
  const cs = { h1: await page.textContent("#main h1"), nav: await page.textContent(".nav-link >> nth=0"), lang: await page.evaluate(() => document.documentElement.lang), title: await page.title() };
  check(en.lang === "en" && cs.lang === "cs", `${tag} the html lang follows the switch (${en.lang} to ${cs.lang})`);
  check(cs.h1 !== en.h1, `${tag} the heading is translated (${en.h1} / ${cs.h1})`);
  check(/Domů/.test(cs.nav), `${tag} Czech navigation says Domů (${cs.nav})`);
  check(/dopamine king/i.test(cs.title) && /Domů/.test(cs.title), `${tag} the document title follows the view and language (${cs.title})`);
  const stored = await profile(page);
  check(stored.settings.lang === "cs", `${tag} the language choice is stored`);
}

async function themeFlow(page, tag) {
  const before = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.click(".theme-btn");
  await page.waitForTimeout(300);
  const attr = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
  const after = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check(attr === "light" || attr === "dark", `${tag} the theme switch sets data-theme (${attr})`);
  const bar = await page.evaluate(() => document.querySelector('meta[name="theme-color"]').getAttribute("content"));
  check(bar === (attr === "light" ? "#f1f3fb" : "#070b16"), `${tag} the browser bar colour follows the theme (${attr} ${bar})`);
  check(before !== after, `${tag} the theme switch changes the page colour`);
  await page.click(".theme-btn");
  await page.waitForTimeout(200);
}

// WCAG 1.4.3 on the rendered page: every visible text element against the colour it really sits on (text on
// gradients is covered by the token test in hygiene.test.js). Runs inside the page.
const CONTRAST_AUDIT = () => {
  function parse(c) { const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/.exec(c); return m ? { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] } : null; }
  const over = (f, b) => ({ r: f.r * f.a + b.r * (1 - f.a), g: f.g * f.a + b.g * (1 - f.a), b: f.b * f.a + b.b * (1 - f.a), a: 1 });
  const lum = (c) => { const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }; return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
  const ratio = (a, b) => { const la = lum(a), lb = lum(b); return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05); };
  const bodyBg = parse(getComputedStyle(document.body).backgroundColor) || { r: 255, g: 255, b: 255, a: 1 };
  function backdrop(el) {
    const layers = [];
    let gradient = false;
    for (let n = el; n && n.nodeType === 1; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.backgroundImage && cs.backgroundImage !== "none" && /gradient/.test(cs.backgroundImage)) { gradient = true; }
      const bg = parse(cs.backgroundColor);
      if (bg && bg.a > 0) { layers.push(bg); if (bg.a >= 0.99) break; }
    }
    let base = { r: bodyBg.r, g: bodyBg.g, b: bodyBg.b, a: 1 };
    if (layers.length && layers[layers.length - 1].a >= 0.99) base = layers.pop();
    for (let i = layers.length - 1; i >= 0; i--) base = over(layers[i], base);
    return { color: base, gradient };
  }
  const out = [];
  const walker = document.createTreeWalker(document.getElementById("main"), NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const tn = walker.currentNode;
    if (!tn.nodeValue.trim()) continue;
    const el = tn.parentElement;
    if (!el || seen.has(el)) continue;
    seen.add(el);
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || parseFloat(cs.opacity) < 0.05) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    if (el.closest("[hidden], .sr-only, .hl-layer, dialog:not([open]), svg")) continue;
    if (el.closest("[disabled], [aria-disabled=true]")) continue;
    let fg = parse(cs.color);
    if (!fg) continue;
    const bd = backdrop(el);
    if (bd.gradient) continue; // text on gradients is checked through the token test
    fg = over(fg, bd.color);
    const cr = ratio(fg, bd.color);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight, 10) >= 700;
    const large = size >= 24 || (size >= 18.66 && bold);
    const need = large ? 3 : 4.5;
    if (cr < need) out.push({ text: tn.nodeValue.trim().slice(0, 40), cr: Math.round(cr * 100) / 100, need, cls: String(el.className).slice(0, 40), tag: el.tagName.toLowerCase(), fg: cs.color, size });
  }
  return out;
};

// Structure that assistive technology relies on: names for every control, one h1 and no skipped heading levels,
// unique ids, references that resolve, labelled landmarks. Runs inside the page.
const A11Y_AUDIT = () => {
  const problems = [];
  const visible = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return cs.visibility !== "hidden" && cs.display !== "none" && (r.width > 0 || r.height > 0 || el.matches(".sr-only")); };
  const text = (el) => (el.textContent || "").replace(/\s+/g, " ").trim();
  function nameOf(el) {
    const al = el.getAttribute("aria-label"); if (al && al.trim()) return al.trim();
    const lb = el.getAttribute("aria-labelledby");
    if (lb) { const t = lb.split(/\s+/).map((id) => { const n = document.getElementById(id); return n ? text(n) : ""; }).join(" ").trim(); if (t) return t; }
    if (el.labels && el.labels.length) { const t = Array.from(el.labels).map(text).join(" ").trim(); if (t) return t; }
    if (el.tagName === "INPUT" && /^(button|submit)$/.test(el.type) && el.value) return el.value;
    const t = text(el); if (t) return t;
    const img = el.querySelector("img[alt]"); if (img && img.alt.trim()) return img.alt.trim();
    const title = el.getAttribute("title"); if (title && title.trim()) return title.trim();
    return "";
  }
  document.querySelectorAll("button, a[href], input:not([type=hidden]), select, textarea, [role=tab], [role=button], summary, [role=switch], [role=slider], [role=meter], [role=img]").forEach((el) => {
    if (!visible(el)) return;
    if (el.closest("[aria-hidden=true]") && !el.matches("input[type=file]")) return;
    if (!nameOf(el)) problems.push(`no accessible name: <${el.tagName.toLowerCase()} class="${String(el.className).slice(0, 40)}">`);
  });
  // duplicate ids
  const ids = {};
  document.querySelectorAll("[id]").forEach((el) => { ids[el.id] = (ids[el.id] || 0) + 1; });
  Object.keys(ids).filter((k) => ids[k] > 1).forEach((k) => problems.push(`duplicate id ${k} x${ids[k]}`));
  // dangling references
  document.querySelectorAll("[aria-labelledby],[aria-controls],[aria-describedby],label[for]").forEach((el) => {
    ["aria-labelledby", "aria-controls", "aria-describedby", "for"].forEach((attr) => {
      const v = el.getAttribute(attr); if (!v) return;
      v.split(/\s+/).forEach((id) => { if (id && !document.getElementById(id)) problems.push(`${attr}="${id}" points nowhere (<${el.tagName.toLowerCase()} class="${String(el.className).slice(0, 30)}">)`); });
    });
  });
  // headings
  const hs = Array.from(document.querySelectorAll("#main h1, #main h2, #main h3, #main h4")).filter(visible);
  const h1s = hs.filter((h) => h.tagName === "H1").length;
  if (h1s !== 1) problems.push(`expected one h1, found ${h1s}`);
  let prev = 0;
  hs.forEach((h) => { const lv = +h.tagName[1]; if (prev && lv > prev + 1) problems.push(`heading level jumps from h${prev} to h${lv}: "${text(h).slice(0, 40)}"`); prev = lv; });
  // landmarks and misc
  if (document.querySelectorAll("main").length !== 1) problems.push("expected exactly one <main>");
  document.querySelectorAll("nav").forEach((n) => { if (!n.getAttribute("aria-label") && !n.getAttribute("aria-labelledby")) problems.push("a <nav> has no label"); });
  document.querySelectorAll("[tabindex]").forEach((el) => { if (+el.getAttribute("tabindex") > 0) problems.push("positive tabindex"); });
  document.querySelectorAll("img:not([alt])").forEach(() => problems.push("img without alt"));
  document.querySelectorAll("table").forEach((t) => { if (visible(t) && !t.querySelector("caption") && !t.getAttribute("aria-label")) problems.push("table without caption"); });
  if (!document.documentElement.lang) problems.push("no html lang");
  return problems;
};

async function tour(page, tag, langs) {
  for (const lang of langs) {
    await setLang(page, lang);
    for (const [name, route] of VIEWS) {
      await go(page, route);
      const h1 = ((await page.textContent("#main h1")) || "").trim();
      check(h1.length > 0, `${tag}-${lang} ${name}: has a heading`);
      const o = await overflow(page);
      check(o.sw <= o.cw, `${tag}-${lang} ${name}: no horizontal scroll (${o.sw} > ${o.cw})`);
      check((await page.locator(".demo-chip").count()) === 1, `${tag}-${lang} ${name}: the Demo data chip is visible`);
      const low = await page.evaluate(CONTRAST_AUDIT);
      check(low.length === 0, `${tag}-${lang} ${name}: text contrast (${low.slice(0, 4).map((x) => `${x.cr}<${x.need} ${x.tag}.${x.cls} ${JSON.stringify(x.text)}`).join("; ")})`);
      const a11y = await page.evaluate(A11Y_AUDIT);
      check(a11y.length === 0, `${tag}-${lang} ${name}: accessibility structure (${a11y.slice(0, 4).join("; ")})`);
      await shot(page, `${tag}-${lang}-${name}`);
    }
  }
}

async function dialogFlow(page, tag) {
  await go(page, "home");
  await page.click(".level-chip");
  await page.waitForSelector("dialog[open]", { timeout: 3000 });
  await page.waitForTimeout(350);
  await shot(page, `${tag}-dialog-profile`);
  const w = await page.evaluate(() => { const r = document.querySelector("dialog[open]").getBoundingClientRect(); return { l: r.left, r: r.right, vw: document.documentElement.clientWidth }; });
  check(w.l >= 0 && w.r <= w.vw, `${tag} the profile dialog fits the screen`);
  await page.keyboard.press("Escape");
  await page.waitForSelector("dialog[open]", { state: "detached", timeout: 3000 });
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.className);
  check(/level-chip/.test(focused || ""), `${tag} focus returns to the button that opened the dialog (${focused})`);
}

// Mobile bottom navigation: direct links, and the "More" menu with Escape and outside click.
async function navFlow(page, tag) {
  await go(page, "home");
  await page.click('.nav-list > li:nth-child(2) .nav-link');
  await page.waitForFunction(() => { const a = document.querySelector('.nav-list a[href="#/arena"]'); return location.hash === "#/arena" && a && a.getAttribute("aria-current") === "page"; }, null, { timeout: 4000 }).then(
    () => check(true, "nav"), () => check(false, `${tag} the current page is marked in the navigation`));
  await page.click(".nav-more");
  check((await page.getAttribute(".nav-more", "aria-expanded")) === "true", `${tag} the More menu opens`);
  const items = await page.locator(".nav-sub .nav-link").allTextContents();
  check(items.length >= 2, `${tag} the More menu lists the remaining views (${items.join(", ")})`);
  await shot(page, `${tag}-nav-more-open`);
  await page.keyboard.press("Escape");
  check((await page.getAttribute(".nav-more", "aria-expanded")) === "false", `${tag} Escape closes the More menu`);
  check(await page.evaluate(() => document.activeElement.classList.contains("nav-more")), `${tag} focus returns to the More button`);
  await page.click(".nav-more");
  await page.mouse.click(180, 300);
  check((await page.getAttribute(".nav-more", "aria-expanded")) === "false", `${tag} a click outside closes the More menu`);
  await page.click(".nav-more");
  await page.click('.nav-sub a[href="#/guru"]');
  await page.waitForFunction(() => location.hash === "#/guru" && /Guru/.test(document.querySelector("#main h1").textContent), null, { timeout: 4000 }).then(
    () => check(true, "nav"), () => check(false, `${tag} the More menu leads to Guru`));
  check((await page.getAttribute(".nav-more", "aria-expanded")) === "false", `${tag} choosing a view closes the menu`);
}

// Settings, export, reset and import through the real dialog.
async function profileFlow(page, tag) {
  await go(page, "home");
  const before = await profile(page);
  check(before.xp > 0, `${tag} there is progress to export`);
  await page.click(".level-chip");
  await page.waitForSelector("dialog[open] .profile");
  await page.fill("dialog[open] .profile input.input", "Tester");
  await page.waitForTimeout(700); // the name is saved shortly after typing stops
  check((await profile(page)).name === "Tester", `${tag} the display name is saved`);
  const [download] = await Promise.all([page.waitForEvent("download"), page.click('dialog[open] button:has-text("Export progress")')]);
  const exported = JSON.parse(fs.readFileSync(await download.path(), "utf8"));
  check(/dopamine-king-progress-\d{4}-\d{2}-\d{2}\.json$/.test(download.suggestedFilename()), `${tag} the export has a dated file name (${download.suggestedFilename()})`);
  check(JSON.stringify(exported).includes('"xp":' + before.xp), `${tag} the export contains the XP`);
  const exportedPath = path.join(os.tmpdir(), "dk-smoke-export.json");
  fs.writeFileSync(exportedPath, JSON.stringify(exported));
  await page.click('dialog[open] button:has-text("Reset progress")');
  await page.click('dialog[open] button:has-text("Yes, reset everything")');
  await page.waitForSelector("dialog[open]", { state: "detached", timeout: 3000 });
  const wiped = await profile(page);
  check(wiped.xp === 0 && wiped.deck.length === 0, `${tag} reset starts over (xp ${wiped.xp})`);
  await page.click(".level-chip");
  await page.waitForSelector("dialog[open] .profile");
  await page.setInputFiles('dialog[open] input[type="file"]', { name: "bad.json", mimeType: "application/json", buffer: Buffer.from('{"hello": 1}') });
  await page.waitForSelector("dialog[open] .form-msg.is-bad", { timeout: 3000 });
  check(true, `${tag} a foreign file is refused with a message`);
  await page.setInputFiles('dialog[open] input[type="file"]', exportedPath);
  await page.waitForSelector("dialog[open] .form-msg.is-ok", { timeout: 3000 });
  await page.waitForSelector("dialog[open]", { state: "detached", timeout: 3000 });
  const back = await profile(page);
  check(back.xp === before.xp && back.stats.arenaPlayed === before.stats.arenaPlayed && back.deck.length === before.deck.length, `${tag} import restores the progress (xp ${back.xp} vs ${before.xp})`);
  fs.rmSync(exportedPath, { force: true });
}

async function guruDialogFlow(page, tag) {
  await go(page, "guru");
  await page.locator(".cal-item:has(.cal-ab)").first().scrollIntoViewIfNeeded();
  await page.locator(".cal-item:has(.cal-ab)").first().click();
  await page.waitForSelector("dialog[open] .cal-ab-box", { timeout: 3000 });
  await page.waitForTimeout(300);
  await shot(page, `${tag}-dialog-guru-item`);
  await page.keyboard.press("Escape");
  await page.waitForSelector("dialog[open]", { state: "detached", timeout: 3000 });
  const focused = await page.evaluate(() => document.activeElement && document.activeElement.className);
  check(/cal-item/.test(focused || ""), `${tag} focus returns to the calendar item (${focused})`);
}

// -- the MITO LIGHT edition: claims check, claims map, banner, studies ---------------------------------------------------
const BAD_HOOK = { en: "Red light cures joint pain", cs: "Červené světlo léčí bolest kloubů" };
const GOOD_HOOK = { en: "5 mistakes people make when choosing a red light panel", cs: "5 chyb při výběru červeného světla" };
const RE = {
  claimsTitle: { en: /Claims check/, cs: /Kontrola tvrzení/ }, error: { en: /Error/, cs: /Chyba/ }, blocking: { en: /blocking problem/, cs: /blokující problém/ },
  // Czech text keeps one letter words with the next word through a no-break space, so spaces are matched with \s
  clean: { en: /No claim problems/, cs: /Žádné\sproblémy\ss\stvrzeními/ }, passed: { en: /Claims check passed/, cs: /Kontrola\stvrzení\sprošla/ },
  lostClaims: { en: /claims check found 1 blocking problem/, cs: /Kontrola\stvrzení\snašla\s1\sblokující\sproblém/ }
};

// The Boss claims panel in one language: a medical claim is an error with severity text, icon, topic, evidence label and a
// safer wording; a compliant hook is clean; an error loses the fight and says why; a strong clean hook wins.
async function claimsBossFlow(page, tag, lang) {
  const t = `${tag}-${lang}`;
  await setLang(page, lang);
  await go(page, "boss");
  await page.waitForSelector(".boss-card", { timeout: 5000 });
  await page.locator(".boss-card").first().click();
  await page.waitForSelector("#hook-input", { timeout: 5000 });
  check((await page.locator(".claims-card").count()) === 1, `${t} boss: the claims check panel is on the page`);
  check(RE.claimsTitle[lang].test((await page.textContent(".claims-card h2")) || ""), `${t} boss: the panel is titled in ${lang}`);
  check((await page.locator(".cond").count()) === 3, `${t} boss: three win conditions are listed`);
  await page.fill("#hook-input", BAD_HOOK[lang]);
  await page.waitForSelector('.claims-card .finding[data-code="CLAIM_MEDICAL"]', { timeout: 4000 });
  const sev = (await page.textContent(".claims-card .finding .sev-chip")) || "";
  check(RE.error[lang].test(sev), `${t} boss: the finding names its severity in words (${sev.trim()})`);
  check((await page.locator(".claims-card .finding .sev-chip svg").count()) >= 1, `${t} boss: and with an icon, not colour alone`);
  check(RE.blocking[lang].test((await page.textContent(".claims-status")) || ""), `${t} boss: the status counts blocking problems`);
  check(((await page.textContent(".claims-card .finding-topic strong")) || "").trim().length > 3, `${t} boss: the finding names the topic`);
  check((await page.locator('.claims-card .finding-topic .chip[class*="ev-"]').count()) === 1, `${t} boss: and shows its evidence label`);
  check(((await page.textContent(".claims-card .finding-safer")) || "").length > 40, `${t} boss: and a safer wording`);
  check((await page.locator(".cond.is-no").count()) >= 3 || (await page.locator(".cond:nth-child(3).is-no").count()) === 1, `${t} boss: the claims condition is not met`);
  check((await page.locator(".strip-claims.is-blocked").count()) === 1, `${t} boss: the live strip shows the claims state`);
  await shot(page, `${t}-boss-claims-error`);
  await page.fill("#hook-input", GOOD_HOOK[lang]);
  await page.waitForSelector(".claims-status.is-clean", { timeout: 4000 });
  check(RE.clean[lang].test((await page.textContent(".claims-status")) || ""), `${t} boss: a compliant hook shows "no claim problems"`);
  check((await page.locator(".claims-card .finding").count()) === 0, `${t} boss: and lists no findings`);
  await shot(page, `${t}-boss-claims-clean`);
  const wins = (await profile(page)).stats.bossWins;
  await page.fill("#hook-input", BAD_HOOK[lang]);
  await page.waitForSelector('.claims-card .finding[data-code="CLAIM_MEDICAL"]');
  await page.click(".attack-btn");
  await page.waitForSelector(".fight-result.is-lose", { timeout: 6000 });
  check(RE.lostClaims[lang].test((await page.textContent(".fight-result")) || ""), `${t} boss: the result says the claims check failed`);
  check((await page.locator(".fight-result .result-claims .finding").count()) === 1, `${t} boss: and repeats the blocking finding`);
  check((await profile(page)).stats.bossWins === wins, `${t} boss: a claim error is no win`);
  await shot(page, `${t}-boss-claims-lost`);
  await page.fill("#hook-input", GOOD_HOOK[lang]);
  await page.waitForSelector(".claims-status.is-clean");
  await page.click(".attack-btn");
  await page.waitForSelector(".fight-result.is-win", { timeout: 6000 });
  check(RE.passed[lang].test((await page.textContent(".fight-result")) || ""), `${t} boss: the win says the claims check passed`);
  check((await profile(page)).stats.bossWins === wins + 1, `${t} boss: a compliant strong hook wins`);
  await shot(page, `${t}-boss-claims-won`);
}

// The Vault Claims map: legend, regulatory note, class groups, cards with badges, counts and studies, jump buttons and
// the "Check your own text" box.
async function claimsMapFlow(page, tag, lang) {
  const t = `${tag}-${lang}`;
  await setLang(page, lang);
  await go(page, "vault/claims");
  const info = await page.evaluate(() => {
    const b = DK.app.bundle;
    const studies = Object.fromEntries(b.vault.studies.map((s) => [s.id, s]));
    const topics = b.claims.topics;
    return {
      topics: topics.length, blocked: topics.filter((x) => x.class === "medical" || x.class === "avoid").length, capped: topics.filter((x) => x.capped).length,
      pending: topics.reduce((n, x) => n + x.study_ids.filter((id) => !studies[id] || studies[id].verified !== true).length, 0), note: b.vertical["regulatory_note_" + DK.i18n.getLang()]
    };
  });
  const tab = ((await page.textContent('[role="tab"][aria-selected="true"]')) || "").trim();
  check(/Claims map|Mapa tvrzení/.test(tab), `${t} claims: the Claims map tab is selected (${tab})`);
  check((await page.locator('[role="tab"]').count()) === 4, `${t} claims: the Vault has four tabs`);
  check((await page.locator(".class-legend > li").count()) === 5, `${t} claims: the legend lists five classes`);
  check((await page.locator(".class-legend > li svg").count()) >= 5, `${t} claims: each with an icon`);
  const note = (await page.textContent(".reg-note")) || "";
  check(note.includes(info.note.slice(0, 60)), `${t} claims: the regulatory note is shown`);
  check(/Not legal advice|Není to právní poradenství/.test(note), `${t} claims: and marked as not legal advice`);
  check((await page.locator(".claim-group").count()) === 5, `${t} claims: five class groups`);
  check((await page.locator(".claim-card").count()) === info.topics, `${t} claims: one card per topic (${info.topics})`);
  check((await page.locator(".claim-card.is-blocked").count()) === info.blocked && (await page.locator(".claim-card .blocked-badge").count()) === info.blocked && (await page.locator(".claim-card:not(.is-blocked) .blocked-badge").count()) === 0, `${t} claims: every medical and avoid card, and only those, is badged as blocked (${info.blocked})`);
  check((await page.locator(".claim-group-head .blocked-badge").count()) === 2, `${t} claims: and so are the two blocked groups`);
  const badge = ((await page.textContent(".blocked-badge")) || "").trim();
  check(/Blocked for this product|Pro tento výrobek zakázáno/.test(badge) && (await page.locator(".blocked-badge svg").count()) >= 1, `${t} claims: the badge has an icon and words (${badge})`);
  check((await page.locator(".claim-card .cap-box").count()) === info.capped, `${t} claims: a capped label is explained (${info.capped})`);
  check((await page.locator(".claim-card .safe-list li").count()) >= info.topics, `${t} claims: safer wording is listed`);
  check((await page.locator(".claim-card .avoid-list li").count()) >= info.topics, `${t} claims: and what to avoid`);
  check((await page.locator(".claim-study.is-unverified").count()) === info.pending, `${t} claims: every unverified link is tagged (${info.pending})`);
  const tag1 = ((await page.locator(".claim-study.is-unverified .chip").first().textContent()) || "").trim();
  check(/Not verified yet|Zatím neověřeno/.test(tag1), `${t} claims: the tag says not verified yet (${tag1})`);
  // the legend jumps to a group and moves focus there
  await page.click(".class-legend .legend-class.class-medical");
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === "claims-group-medical", null, { timeout: 3000 }).then(
    () => check(true, "claims"), () => check(false, `${t} claims: the legend button moves focus to its group`));
  // a card's details open and list the studies
  const more = page.locator(".claim-card.klass-medical .claim-more").first();
  await more.locator("summary").click();
  check((await more.locator(".claim-study").count()) >= 1, `${t} claims: the details list the linked studies`);
  await more.scrollIntoViewIfNeeded();
  await shot(page, `${t}-claims-medical-open`);
  // check your own text
  await page.locator("#claims-check-input").scrollIntoViewIfNeeded();
  const bar = page.locator(".claims-check-bar button");
  await bar.nth(2).click(); // an earlier pass may have left text in the box (it is kept while the page stays open)
  check((await page.locator(".claims-check .claims-empty").count()) === 1, `${t} claims: an empty checker explains what it does`);
  await bar.nth(0).click();
  check(/Paste some text first|Nejdřív vlož/.test((await page.textContent(".claims-check .claims-empty")) || ""), `${t} claims: an empty check asks for text`);
  await page.fill("#claims-check-input", BAD_HOOK[lang] + ". " + (lang === "cs" ? "Výsledky za 14 dní." : "Results in 14 days."));
  await bar.nth(0).click();
  await page.waitForSelector(".claims-check .finding", { timeout: 3000 });
  const codes = await page.$$eval(".claims-check .finding", (els) => els.map((e) => e.getAttribute("data-code")));
  check(codes.includes("CLAIM_MEDICAL") && codes.includes("OUTCOME_PROMISE"), `${t} claims: the checker finds the medical claim and the promise (${codes.join(", ")})`);
  const first = page.locator(".claims-check .finding").first();
  check(RE.error[lang].test((await first.locator(".sev-chip").textContent()) || ""), `${t} claims: severity as text`);
  check((await first.locator(".finding-topic strong").count()) === 1 && (await first.locator('.finding-topic .chip[class*="ev-"]').count()) === 1 && (await first.locator(".finding-safer").count()) === 1, `${t} claims: topic, evidence label and safer wording`);
  await shot(page, `${t}-claims-check`);
  await bar.nth(1).click();
  check(((await page.inputValue("#claims-check-input")) || "").length > 60, `${t} claims: the example fills the box`);
  await bar.nth(2).click();
  check((await page.inputValue("#claims-check-input")) === "" && (await page.locator(".claims-check .finding").count()) === 0, `${t} claims: clear empties the box and the result`);
  await page.fill("#claims-check-input", GOOD_HOOK[lang]);
  await page.keyboard.press("Control+Enter");
  await page.waitForSelector(".claims-check .claims-status.is-clean", { timeout: 3000 });
  check(true, `${t} claims: Ctrl+Enter checks, and clean copy is clean`);
  // nothing is sent anywhere while checking
  check(/nothing is sent anywhere|nic se nikam neodesílá/.test(((await page.textContent(".claims-check")) || "")), `${t} claims: the box says nothing leaves the page`);
}

// The Studies tab: claim topics are named, each link says how the study bears on it, studies that are not verified yet are tagged.
async function studiesFlow(page, tag) {
  await setLang(page, "en");
  await go(page, "vault/studies");
  const info = await page.evaluate(() => {
    const b = DK.app.bundle;
    const claimLinks = b.vault.links.filter((l) => /^pbm-/.test(l.tactic_id)).length;
    return { studies: b.vault.studies.length, unverified: b.vault.studies.filter((s) => s.verified !== true).length, claimLinks, names: b.claims.topics.map((x) => x.name_en) };
  });
  check((await page.locator(".study").count()) === info.studies, `${tag} studies: every study is listed (${info.studies})`);
  check((await page.locator(".study .chip:has-text('Not verified yet')").count()) === info.unverified, `${tag} studies: ${info.unverified} are tagged not verified yet`);
  const links = (await page.$$eval(".study-links", (els) => els.map((e) => e.textContent))).join(" | ");
  check(info.names.some((n) => links.includes(n)) && !/pbm-[a-z-]+/.test(links), `${tag} studies: links show claim topic names, not ids`);
  check(/\((supports|mixed results|contradicts|background)\)/.test(links), `${tag} studies: each link says how the study bears on the topic`);
  await page.click('.seg-btn:has-text("Not verified yet")');
  check((await page.locator(".study").count()) === info.unverified, `${tag} studies: the filter shows the unverified ones`);
  await page.click('.seg-btn:has-text("All")');
}

// Home banner and its two links.
async function editionFlow(page, tag) {
  await setLang(page, "en");
  await go(page, "home");
  const name = await page.evaluate(() => DK.app.bundle.vertical.edition_en);
  check((await page.locator(".edition-banner").count()) === 1, `${tag} home: the edition banner is shown`);
  check(((await page.textContent(".edition-banner .edition-name")) || "").trim() === name, `${tag} home: it names the edition (${name})`);
  check(/confirmed by the brand/.test((await page.textContent(".edition-banner")) || ""), `${tag} home: and says the facts need the brand's confirmation`);
  await page.click('.edition-banner a:has-text("Open the Claims map")');
  await page.waitForSelector(".vault-claims .claim-card", { timeout: 4000 });
  check(/Claims map/.test((await page.textContent('[role="tab"][aria-selected="true"]')) || ""), `${tag} home: the first link opens the Claims map`);
  await go(page, "home");
  await page.click('.edition-banner a:has-text("Check your own text")');
  await page.waitForFunction(() => document.activeElement && document.activeElement.id === "claims-check-input", null, { timeout: 4000 }).then(
    () => check(true, "home"), () => check(false, `${tag} home: the second link focuses the text box`));
  await go(page, "about");
  check((await page.locator(".glossary-item").count()) >= 5 && (await page.locator(".reg-note .legal-chip").count()) === 1, `${tag} about: the glossary and the regulatory note are there`);
  await go(page, "forge");
  check(/Claims profile/.test((await page.textContent(".pack-head .profile-pill")) || ""), `${tag} forge: the pack header shows the claims profile`);
  check(/not confirmed any fact/.test((await page.textContent(".pack-head .sim-note")) || ""), `${tag} forge: the sample says its facts are unconfirmed`);
}

// The generic edition, built from the same sources, shows none of the claims features and still works.
async function genericFlow(browser) {
  const file = path.join(os.tmpdir(), "dopamine-king-generic.html");
  const build = spawnSync("python3", [path.join(ROOT, "scripts", "build_web.py"), "--vertical", "general", "--out", file, "--quiet"], {
    cwd: ROOT, encoding: "utf8", env: Object.assign({}, process.env, { PYTHONPATH: path.join(ROOT, "src") })
  });
  if (build.status !== 0) { log("  (the generic edition could not be built, check skipped: " + String(build.stderr).split("\n")[0] + ")"); return; }
  const { context, page } = await open(browser, { w: 1280, h: 800, scheme: "dark" });
  const problems = watch(page, "generic");
  await boot(page, "file://" + file);
  check((await page.evaluate(() => !DK.app.bundle.vertical && !DK.app.bundle.claims && !DK.app.bundle.claim_rules)), "generic: the bundle has no vertical, claims or rules");
  check((await page.locator(".edition-banner").count()) === 0, "generic: the Home page has no edition banner");
  await go(page, "vault");
  check((await page.locator('[role="tab"]').count()) === 3, "generic: the Vault has three tabs");
  await go(page, "vault/claims");
  check(/Cards|Karty/.test((await page.textContent('[role="tab"][aria-selected="true"]')) || "") && (await page.locator(".claim-card").count()) === 0, "generic: a claims deep link falls back to the cards");
  await go(page, "boss");
  await page.locator(".boss-card").first().click();
  await page.waitForSelector("#hook-input");
  await page.fill("#hook-input", BAD_HOOK.en);
  await page.waitForTimeout(500);
  check((await page.locator(".claims-card").count()) === 0 && (await page.locator(".cond").count()) === 2, "generic: the Boss fight has no claims check and two win conditions");
  await go(page, "about");
  check((await page.locator(".glossary-list, .reg-note, .edition-card").count()) === 0, "generic: About has no glossary or regulatory note");
  await go(page, "forge");
  check((await page.locator(".profile-pill").count()) === 0, "generic: the Forge pack has no claims profile pill");
  await shot(page, "generic-forge");
  const o = await overflow(page);
  check(o.sw <= o.cw, "generic: no horizontal scroll");
  flush(problems);
  await context.close();
  fs.rmSync(file, { force: true });
}

// -- keyboard ---------------------------------------------------------------------------------------------------
async function keyboardFlow(page, tag) {
  await go(page, "home");
  await page.evaluate(() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); });
  await page.evaluate(() => { document.body.setAttribute("tabindex", "-1"); document.body.focus(); document.body.removeAttribute("tabindex"); });
  const stops = [];
  for (let i = 0; i < 26; i++) {
    await page.keyboard.press("Tab");
    if (i === 0) await page.waitForTimeout(300);
    const s = await page.evaluate(() => {
      const el = document.activeElement;
      if (!el || el === document.body) return null;
      const cs = getComputedStyle(el);
      const r = el.getBoundingClientRect();
      const ring = cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2;
      return {
        tag: el.tagName.toLowerCase(), id: el.id, cls: String(el.className && el.className.baseVal !== undefined ? "" : el.className).slice(0, 40),
        name: (el.getAttribute("aria-label") || el.textContent || "").trim().slice(0, 30), ring, top: Math.round(r.top), height: Math.round(r.height),
        width: Math.round(r.width), inline: cs.display === "inline", order: Array.prototype.indexOf.call(document.querySelectorAll("*"), el)
      };
    });
    if (s) stops.push(s);
  }
  check(stops.length >= 18, `${tag} Tab reaches at least 18 controls (got ${stops.length})`);
  check(stops[0] && stops[0].id === "dk-skip", `${tag} the first Tab stop is the skip link (${stops[0] && stops[0].id})`);
  check(stops[0] && stops[0].top >= 0 && stops[0].height > 20, `${tag} the skip link becomes visible when focused`);
  const noRing = stops.filter((s) => !s.ring);
  check(noRing.length === 0, `${tag} every focused control shows a focus ring (missing: ${noRing.map((s) => s.tag + "." + s.cls + "[" + s.name + "]").join(", ")})`);
  // WCAG 2.5.8: 24px targets, except links that sit inside a sentence.
  const tiny = stops.filter((s) => !s.inline && (s.width < 24 || s.height < 24));
  check(tiny.length === 0, `${tag} focused controls are at least 24px big (${tiny.map((s) => s.name + " " + s.width + "x" + s.height).join(", ")})`);
  let backwards = 0;
  for (let i = 1; i < stops.length; i++) if (stops[i].order < stops[i - 1].order) backwards += 1;
  check(backwards <= 1, `${tag} Tab order follows the page order (${backwards} jumps back)`);
  await page.keyboard.press("Shift+Tab");
  const back = await page.evaluate(() => document.activeElement && (document.activeElement.id || document.activeElement.className));
  check(!!back, `${tag} Shift+Tab moves back`);
  await page.keyboard.press("Enter").catch(() => {});
  await page.keyboard.press("Escape");
  log(`  tab stops: ${stops.slice(0, 12).map((s) => s.name || s.cls || s.tag).join(" > ")} ...`);
}

// Every view: Tab through the content after the heading and check each stop has a visible focus indicator
// (on the control itself or on the wrapper that shows :focus-within) and a big enough target.
async function keyboardTour(page, tag) {
  for (const [name, route] of VIEWS) {
    await go(page, route);
    const stops = [];
    for (let i = 0; i < 70; i++) {
      await page.keyboard.press("Tab");
      const s = await page.evaluate(() => {
        const el = document.activeElement;
        if (!el || el === document.body || !document.getElementById("main").contains(el)) return { left: true };
        const visible = (node) => { const cs = getComputedStyle(node); return cs.outlineStyle !== "none" && parseFloat(cs.outlineWidth) >= 2; };
        let ring = visible(el);
        for (let n = el.parentElement, k = 0; !ring && n && k < 3; n = n.parentElement, k++) ring = visible(n);
        if (!ring && el.nextElementSibling) ring = visible(el.nextElementSibling);
        const box = (el.type === "checkbox" || el.type === "radio") && el.closest("label") ? el.closest("label") : el;
        const r = box.getBoundingClientRect();
        const inline = getComputedStyle(el).display === "inline";
        return { ring, w: Math.round(r.width), h: Math.round(r.height), inline, name: (el.getAttribute("aria-label") || el.textContent || el.id || el.tagName).trim().slice(0, 28), tag: el.tagName.toLowerCase(), cls: String(el.className && el.className.baseVal === undefined ? el.className : "").slice(0, 30) };
      });
      if (s.left) break;
      stops.push(s);
    }
    check(stops.length >= 1 || name === "lab-peek", `${tag} ${name}: Tab finds controls (${stops.length})`);
    const noRing = stops.filter((s) => !s.ring);
    check(noRing.length === 0, `${tag} ${name}: every focus stop is visible (missing: ${noRing.map((s) => `${s.tag}.${s.cls}[${s.name}]`).join(", ")})`);
    const tiny = stops.filter((s) => !s.inline && (s.w < 24 || s.h < 24));
    check(tiny.length === 0, `${tag} ${name}: targets are at least 24px (${tiny.map((s) => `${s.name} ${s.w}x${s.h}`).join(", ")})`);
  }
}

async function arenaKeyboard(page, tag) {
  await go(page, "arena");
  await page.waitForSelector('.hook-card[data-side="a"]');
  await page.keyboard.press("b");
  await page.waitForSelector(".verdict", { timeout: 8000 });
  check(true, `${tag} arena answers to the keyboard`);
  await page.keyboard.press("Enter");
  await page.waitForSelector(".verdict", { state: "detached", timeout: 6000 });
}

// -- break card, reduced motion ---------------------------------------------------------------------------------
async function breakCardFlow(browser, combo) {
  const { context, page } = await open(browser, combo);
  const problems = watch(page, "break");
  if (!page.clock || typeof page.clock.install !== "function") { log("  (page.clock not available, break card check skipped)"); await context.close(); return; }
  await page.clock.install();
  await boot(page);
  await page.clock.runFor(21 * 60 * 1000);
  await page.waitForSelector(".break-card", { timeout: 4000 });
  const text = (await page.textContent(".break-card")) || "";
  check(/20/.test(text), `break card names the session length (${text.slice(0, 80)})`);
  const modal = await page.evaluate(() => !!document.querySelector("dialog[open]"));
  check(!modal, "the break card is not a blocking dialog");
  await shot(page, `${combo.w}x${combo.h}-${combo.scheme}-break-card`);
  const noGuilt = !/lost|lose|streak.*(broken|gone)|disappoint|shame/i.test(text);
  check(noGuilt, "the break card has no guilt wording");
  await page.click(".break-card .btn");
  await page.waitForSelector(".break-card", { state: "detached", timeout: 3000 }).catch(() => {});
  flush(problems);
  await context.close();
}

async function reducedMotionFlow(browser, combo) {
  const { context, page } = await open(browser, combo, { reducedMotion: "reduce" });
  const problems = watch(page, "reduced-motion");
  await boot(page);
  const hasClass = await page.evaluate(() => document.documentElement.classList.contains("reduce-motion"));
  check(hasClass, "reduced motion: the reduce-motion class is set from the system preference");
  const dur = await page.evaluate(() => getComputedStyle(document.querySelector(".btn, .chip, .card")).transitionDuration);
  check(/^0(\.0+1)?m?s/.test(dur) || parseFloat(dur) < 0.01, `reduced motion: transitions are switched off (${dur})`);
  await go(page, "vault");
  await page.click(".chest-panel .btn-primary");
  await page.waitForSelector(".chest-dialog .flip.is-flipped", { timeout: 4000 });
  await page.waitForTimeout(900);
  const confetti = await page.evaluate(() => document.getElementById("dk-confetti").classList.contains("is-on"));
  check(!confetti, "reduced motion: no confetti");
  const p = await profile(page);
  check(p.settings.sound === false, "sound is off by default");
  flush(problems);
  await context.close();
}

// -- layout at 360px ----------------------------------------------------------------------------------------------
async function narrowFlow(browser) {
  for (const locale of ["en-US", "cs-CZ"]) {
    const { context, page } = await open(browser, { w: 360, h: 740, scheme: "dark" }, { locale });
    const problems = watch(page, "360px");
    await boot(page);
    for (const [name, route] of VIEWS) {
      await go(page, route);
      const o = await overflow(page);
      check(o.sw <= o.cw, `360px ${locale} ${name}: no horizontal scroll (${o.sw} > ${o.cw})`);
    }
    await page.click(".level-chip");
    await page.waitForSelector("dialog[open]");
    const o = await overflow(page);
    check(o.sw <= o.cw, `360px ${locale} profile dialog: no horizontal scroll`);
    const fits = await page.evaluate(() => { const r = document.querySelector("dialog[open]").getBoundingClientRect(); return r.left >= 0 && r.right <= document.documentElement.clientWidth; });
    check(fits, `360px ${locale} profile dialog fits`);
    await page.keyboard.press("Escape");
    await go(page, "guru");
    await page.locator(".cal-item").first().click();
    await page.waitForSelector("dialog[open] .cal-detail");
    const o2 = await overflow(page);
    check(o2.sw <= o2.cw, `360px ${locale} guru dialog: no horizontal scroll`);
    flush(problems);
    await context.close();
  }
}

// -- live mode with a stand-in for kingctl serve ----------------------------------------------------------------------
function startLiveServer() {
  const scoring = createRequire(import.meta.url)("../src/scoring.js");
  const spec = JSON.parse(fs.readFileSync(path.join(ROOT, "src", "dopamine_king", "data", "scoring_spec.json"), "utf8"));
  const pack = JSON.parse(fs.readFileSync(path.join(ROOT, "web", "dev", "mock-forge.json"), "utf8"));
  const plan = JSON.parse(fs.readFileSync(path.join(ROOT, "web", "dev", "mock-guru.json"), "utf8"));
  const html = fs.readFileSync(FILE);
  const seen = { forge: [], guru: [] };
  const formats = pack.items.map((i) => ({ id: i.format, name_en: i.name_en, name_cs: i.name_cs, family: i.family, platform: i.family, limits: {} }));
  const server = http.createServer((req, res) => {
    const send = (status, obj, type) => { res.writeHead(status, { "Content-Type": type || "application/json; charset=utf-8" }); res.end(type ? obj : JSON.stringify(obj)); };
    const url = req.url.split("?")[0];
    if (req.method === "GET" && (url === "/" || url === "/index.html")) return send(200, html, "text/html; charset=utf-8");
    if (req.method === "GET" && url === "/api/health") return send(200, { ok: true, version: "smoke", writer: "offline" });
    if (req.method === "GET" && url === "/api/formats") return send(200, formats);
    if (req.method === "POST" && (url === "/api/forge" || url === "/api/guru" || url === "/api/score")) {
      let body = "";
      req.on("data", (c) => { body += c; });
      req.on("end", () => {
        let data = {};
        try { data = JSON.parse(body || "{}"); } catch (e) { return send(400, { ok: false, error: "invalid JSON body" }); }
        if (url === "/api/score") {
          if (typeof data.text !== "string") return send(400, { ok: false, error: "field 'text' (string) is required" });
          return send(200, { total: Math.round(scoring.scoreHook(data.text, "", { lang: data.lang, spec }).total * 100) / 100 });
        }
        const kind = url === "/api/forge" ? "forge" : "guru";
        seen[kind].push(data);
        if (data.brief && /FAIL/.test(data.brief.topic || "")) return send(502, { ok: false, error: "writer unavailable" });
        if (kind === "forge") return send(200, Object.assign({}, pack, { brief: Object.assign({}, pack.brief, data.brief), items: pack.items.filter((i) => !data.formats || data.formats.includes(i.format)) }));
        return send(200, Object.assign({}, plan, { brief: Object.assign({}, plan.brief, data.brief) }));
      });
      return undefined;
    }
    return send(404, { ok: false, error: "not found" });
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve({ server, seen, origin: `http://127.0.0.1:${server.address().port}` })));
}

async function liveFlow(browser) {
  const { server, seen, origin } = await startLiveServer();
  const { context, page } = await open(browser, { w: 1280, h: 800, scheme: "dark" });
  // The test deliberately makes the stand-in server answer once with a 502, which Chromium logs as a console error.
  const problems = watch(page, "live", origin, [/status of 502/]);
  try {
    await boot(page, origin + "/");
    await page.waitForSelector('.chip:has-text("Live")', { timeout: 6000 });
    await go(page, "forge");
    await page.waitForSelector(".live-form", { timeout: 5000 });
    check((await page.locator(".run-live").count()) === 0, "live: the 'run it live' hint is gone");
    await page.waitForSelector(".live-form .checks input[type=checkbox]", { timeout: 5000 });
    await shot(page, "live-forge-form");
    // Validation: an empty brief is refused without a request.
    await page.fill("#bf-brand", "");
    await page.click(".live-form button[type=submit]");
    await page.waitForSelector(".form-msg.is-bad");
    check(seen.forge.length === 0, "live: an incomplete brief is not sent");
    await page.fill("#bf-brand", "Acme Shoes");
    await page.fill("#bf-topic", "trail running shoes");
    await page.fill("#bf-audience", "weekend hikers");
    // The brief is seeded from the MITO LIGHT sample: the claims profile select is visible and so is the safety note.
    const edition = await page.evaluate(() => !!DK.app.bundle.vertical);
    if (edition) {
      check((await page.inputValue("#bf-profile")) === "wellness", "live: the claims profile select is seeded with wellness");
      check((await page.locator("#bf-profile option").allTextContents()).length === 2, "live: it offers General and Wellness");
      check(await page.locator("#bf-safety_note").isVisible(), "live: the safety note field is visible with the wellness profile");
      await page.fill("#bf-safety_note", "Follow the manual and protect your eyes.");
    }
    await page.click(".live-form button[type=submit]");
    await page.waitForSelector('.pack-head:has-text("Acme Shoes")', { timeout: 8000 });
    if (edition) {
      const b = seen.forge[0].brief;
      check(b.vertical === "pbm" && b.claims_profile === "wellness" && b.safety_note === "Follow the manual and protect your eyes.", `live: the request keeps the vertical, the claims profile and the safety note (${b.vertical} ${b.claims_profile})`);
      check((await page.locator(".pack-head .profile-pill").count()) === 1, "live: the pack header shows the claims profile");
    }
    check(seen.forge.length === 1 && seen.forge[0].brief.brand === "Acme Shoes" && Array.isArray(seen.forge[0].formats) && seen.forge[0].formats.length >= 1, "live: forge request has the brief and formats");
    check((await page.locator(".sim-note").count()) === 0, "live: a server pack is not labelled as the offline sample");
    await shot(page, "live-forge-result");
    if (edition) {
      await page.selectOption("#bf-profile", "general");
      check(!(await page.locator("#bf-safety_note").isVisible()), "live: the safety note is hidden for the general profile");
    }
    await page.fill("#bf-topic", "FAIL please");
    await page.click(".live-form button[type=submit]");
    await page.waitForSelector(".form-msg.is-bad:has-text('writer unavailable')", { timeout: 5000 });
    check(true, "live: a server error is shown in the form");
    if (edition) check(seen.forge[1].brief.claims_profile === "general" && !("safety_note" in seen.forge[1].brief), "live: the general profile is sent as general, without a safety note");
    await go(page, "guru");
    await page.waitForSelector(".live-form");
    check((await page.inputValue("#bf-brand")) === "Acme Shoes", "live: the Guru form keeps the brief from the Forge");
    await page.fill("#bf-topic", "trail running shoes");
    await page.click(".live-form button[type=submit]");
    await page.waitForSelector('.plan-head:has-text("Acme Shoes")', { timeout: 8000 });
    check(seen.guru.length === 1 && seen.guru[0].options && seen.guru[0].options.weeks === 4 && seen.guru[0].options.posts_per_week === 5, "live: guru request carries the plan options");
    check((await page.locator(".cal-item").count()) === 20, "live: the plan calendar shows 20 posts");
    await shot(page, "live-guru-result");
    const about = await (async () => { await go(page, "about"); return page.textContent("#main"); })();
    check(/Live mode is on/.test(about || ""), "live: About explains what live mode sends");
    await page.click(".parity button");
    await page.waitForSelector(".parity-list li.is-same", { timeout: 5000 });
    check((await page.locator(".parity-list li.is-same").count()) === 2 && (await page.locator(".parity-list li.is-diff").count()) === 0, "live: the scorer check agrees with the server for both languages");
  } catch (e) {
    check(false, "live mode flow threw: " + e.message);
    try { await shot(page, "live-failure"); } catch (e2) { /* the page may be gone */ }
  }
  flush(problems);
  await context.close();
  server.close();
}

// -- main -------------------------------------------------------------------------------------------------------
const started = Date.now();
// The browser itself must stay quiet too: no update checks, sync or pings that would show up as outside connections.
const QUIET = ["--disable-background-networking", "--disable-component-update", "--disable-sync", "--disable-default-apps", "--no-pings", "--no-first-run", "--disable-features=OptimizationHints,Translate,MediaRouter,AutofillServerCommunication"];
const browser = await chromium.launch(Object.assign({ args: QUIET }, fs.existsSync(CHROMIUM) ? { executablePath: CHROMIUM } : {}));
try {
  for (const combo of COMBOS) {
    const tag = `${combo.w}x${combo.h}-${combo.scheme}`;
    log(`\n== ${tag}`);
    const { context, page } = await open(browser, combo);
    const problems = watch(page, tag);
    try {
      await boot(page);
      check(/dopamine king/i.test(await page.title()), `${tag} title`);
      await shot(page, `${tag}-en-first-paint`);
      await arenaFlow(page, 3, tag); log("  arena ok"); flush(problems);
      await bossFlow(page, tag); log("  boss ok"); flush(problems);
      await vaultFlow(page, tag); log("  vault ok"); flush(problems);
      await labFlow(page, tag); log("  lab ok"); flush(problems);
      await mythFlow(page, tag); log("  myths ok"); flush(problems);
      await claimsBossFlow(page, tag, "en"); log("  claims check in the Boss Battle (en) ok"); flush(problems);
      await claimsMapFlow(page, tag, "en"); log("  claims map (en) ok"); flush(problems);
      await studiesFlow(page, tag); log("  studies ok"); flush(problems);
      await editionFlow(page, tag); log("  edition banner, about and forge ok"); flush(problems);
      await claimsBossFlow(page, tag, "cs"); log("  claims check in the Boss Battle (cs) ok"); flush(problems);
      await claimsMapFlow(page, tag, "cs"); log("  claims map (cs) ok"); flush(problems);
      await setLang(page, "en");
      await dialogFlow(page, tag); flush(problems);
      if (combo.w < 600 && combo.scheme === "dark") { await navFlow(page, tag); log("  mobile navigation ok"); flush(problems); }
      if (combo.w >= 1000 && combo.scheme === "dark") { await profileFlow(page, tag); log("  profile export, reset and import ok"); flush(problems); }
      await guruDialogFlow(page, tag); flush(problems);
      await themeFlow(page, tag); flush(problems);
      await tour(page, tag, ["en"]); log("  tour en ok"); flush(problems);
      await languageFlow(page, tag); log("  language ok"); flush(problems);
      await tour(page, tag, ["cs"]); log("  tour cs ok"); flush(problems);
      if (combo.w >= 1000 && combo.scheme === "dark") {
        await setLang(page, "en");
        await keyboardFlow(page, tag); flush(problems);
        await keyboardTour(page, tag); log("  keyboard tour ok"); flush(problems);
        await arenaKeyboard(page, tag); flush(problems);
      }
    } catch (e) {
      check(false, `${tag} flow threw: ${e.message}`);
      try { await shot(page, `${tag}-failure`); } catch (e2) { /* the page may be gone */ }
    }
    await context.close();
  }
  if (!ONLY) {
    log("\n== extras");
    if (!LIVE_ONLY) {
      await narrowFlow(browser); log("  360px ok");
      await breakCardFlow(browser, { w: 1280, h: 800, scheme: "dark" }); log("  break card ok");
      await reducedMotionFlow(browser, { w: 390, h: 844, scheme: "dark" }); log("  reduced motion ok");
    }
    if (!SKIP_LIVE) { await liveFlow(browser); log("  live mode done"); }
    if (!LIVE_ONLY && !SKIP_GENERIC) { await genericFlow(browser); log("  generic edition done"); }
  }
} finally {
  await browser.close();
}

const seconds = Math.round((Date.now() - started) / 1000);
const shots = fs.readdirSync(SHOTS).filter((f) => f.endsWith(".png")).length;
console.log(`\n${checks} checks, ${failures.length} failed, ${shots} screenshots in ${SHOTS}, ${seconds}s`);
if (failures.length) {
  console.log("\nFailures:\n" + failures.map((f) => " - " + f).join("\n"));
  process.exitCode = 1;
} else {
  console.log("SMOKE TEST PASSED");
}
