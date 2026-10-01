"use strict";
// Project rules checked mechanically: no long dashes, no network surface, system fonts, accessible colour tokens,
// reduced motion and a viewport that allows zooming.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const WEB = path.resolve(__dirname, "..");
const ROOT = path.resolve(WEB, "..");
const read = (p) => fs.readFileSync(p, "utf8");
const css = read(path.join(WEB, "src", "styles.css"));

function files(dir, pattern) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return files(p, pattern);
    return pattern.test(e.name) ? [p] : [];
  });
}
const ownedFiles = [
  ...files(path.join(WEB, "src"), /\.(js|css|html)$/),
  ...files(path.join(WEB, "tests"), /\.(js|mjs)$/),
  path.join(WEB, "dev", "index.html"),
  path.join(WEB, "dev", "mock-forge.json"),
  path.join(WEB, "dev", "mock-guru.json"),
  path.join(ROOT, "scripts", "build_web.py")
];
const rel = (f) => path.relative(ROOT, f).split(path.sep).join("/");

test("no em dash, en dash or invisible characters in any file this project owns", () => {
  const bad = new Set([0x2013, 0x2014, 0x2015, 0x2212, 0x200b, 0x200c, 0x200d, 0x2060, 0xfeff, 0xfffd]);
  const problems = [];
  for (const f of ownedFiles) {
    const text = read(f);
    for (const ch of text) if (bad.has(ch.codePointAt(0))) problems.push(`${rel(f)}: U+${ch.codePointAt(0).toString(16)}`);
  }
  assert.ok(ownedFiles.length > 30);
  assert.deepEqual(problems, []);
});

test("the built game file, when present, has no long dashes either", (t) => {
  const dist = path.join(WEB, "dist", "dopamine-king.html");
  if (!fs.existsSync(dist)) { t.skip("web/dist is not built"); return; }
  const text = read(dist);
  assert.ok(!text.includes(String.fromCharCode(0x2014)) && !text.includes(String.fromCharCode(0x2013)));
});

test("the sources have no network surface beyond the local kingctl API", () => {
  const src = files(path.join(WEB, "src"), /\.js$/);
  for (const f of src) {
    const text = read(f);
    const name = rel(f);
    assert.ok(!/\bXMLHttpRequest\b|\bWebSocket\b|\bEventSource\b|sendBeacon|importScripts|serviceWorker/.test(text), `${name}: network API`);
    assert.ok(!/\beval\(|new Function\(|document\.write\(|\.innerHTML\b|insertAdjacentHTML|outerHTML/.test(text), `${name}: unsafe markup API`);
    const urls = (text.match(/https?:\/\/[^\s"'`)]+/g) || []).filter((u) => u !== "http://www.w3.org/2000/svg");
    if (name !== "web/src/i18n.js") assert.deepEqual(urls, [], `${name}: external URL`);
    if (!/app\.js$/.test(name)) assert.ok(!/\bfetch\(/.test(text), `${name}: fetch outside app.js`);
  }
  const app = read(path.join(WEB, "src", "app.js"));
  const targets = [...app.matchAll(/(?:fetchJson|apiCall)\(\s*(?:"[A-Z]+",\s*)?"([^"]+)"/g)].map((m) => m[1]);
  assert.ok(targets.length >= 5);
  for (const u of targets) assert.match(u, /^(\.\/[a-z-]+\.json|\/api\/[a-z]+)$/, `unexpected request target ${u}`);
  const tpl = read(path.join(WEB, "src", "index.template.html"));
  assert.ok(!/<(?:script|link|img|iframe)\b[^>]*\b(?:src|href)\s*=\s*["']?(?:https?:)?\/\//i.test(tpl.replace(/<link rel="icon" href="data:[^>]*>/, "")), "template pulls nothing from the network");
});

test("fonts are system stacks and the stylesheet imports nothing", () => {
  assert.ok(!/@font-face|@import/i.test(css));
  assert.ok(!/url\(\s*["']?(?!#|data:)/i.test(css), "css url() must be data: or a fragment");
  const font = /--font:\s*([^;]+);/.exec(css)[1];
  assert.match(font, /system-ui/);
  assert.match(font, /sans-serif\s*$/);
  const mono = /--mono:\s*([^;]+);/.exec(css)[1];
  assert.match(mono, /monospace\s*$/);
  const families = [...css.matchAll(/font-family:\s*([^;}]+)[;}]/g)].map((m) => m[1].trim());
  for (const f of families) assert.match(f, /^(inherit|var\(--(?:font|mono)\))$/, `font-family ${f}`);
});

test("the page can be zoomed and declares its language and title", () => {
  const tpl = read(path.join(WEB, "src", "index.template.html"));
  const vp = /<meta name="viewport" content="([^"]+)"/.exec(tpl)[1];
  assert.match(vp, /width=device-width/);
  assert.match(vp, /initial-scale=1/);
  assert.ok(!/user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b/.test(vp), "zoom must stay allowed");
  assert.match(tpl, /<html lang="[a-z]{2}"/);
  assert.match(tpl, /<title>[^<]{3,}<\/title>/);
  assert.match(tpl, /id="main"/);
  assert.match(tpl, /id="dk-live"[^>]*aria-live="polite"/);
  assert.match(tpl, /id="dk-skip"/);
});

test("motion is switched off for reduced motion, by the system setting and by the in-game switch", () => {
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /\.reduce-motion \*/);
  assert.match(css, /animation-duration: \.001ms !important/);
  assert.match(css, /:focus-visible\s*\{[^}]*outline: 3px solid var\(--focus\)/);
  assert.match(css, /\.sr-only/);
  assert.match(css, /scroll-padding-top/);
});

// ---- colour tokens ------------------------------------------------------------------------------
function blockAfter(text, header) {
  const at = text.indexOf(header);
  assert.ok(at >= 0, `block not found: ${header}`);
  const open = text.indexOf("{", at);
  let depth = 0, i = open;
  for (; i < text.length; i++) {
    if (text[i] === "{") depth += 1;
    else if (text[i] === "}") { depth -= 1; if (depth === 0) break; }
  }
  return text.slice(open + 1, i);
}
function tokens(body) {
  const out = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) out[m[1]] = m[2].trim();
  return out;
}
const DARK = tokens(blockAfter(css, "\n:root {"));
const LIGHT_MEDIA = tokens(blockAfter(css, ':root:not([data-theme="dark"]) {'));
const LIGHT_EXPLICIT = tokens(blockAfter(css, ':root[data-theme="light"] {'));

function parseColor(v) {
  v = String(v).trim();
  let m = /^#([0-9a-f]{3})$/i.exec(v);
  if (m) return { r: parseInt(m[1][0] + m[1][0], 16), g: parseInt(m[1][1] + m[1][1], 16), b: parseInt(m[1][2] + m[1][2], 16), a: 1 };
  m = /^#([0-9a-f]{6})$/i.exec(v);
  if (m) return { r: parseInt(m[1].slice(0, 2), 16), g: parseInt(m[1].slice(2, 4), 16), b: parseInt(m[1].slice(4, 6), 16), a: 1 };
  m = /^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$/i.exec(v);
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  return null;
}
const over = (fg, bg) => ({ r: fg.r * fg.a + bg.r * (1 - fg.a), g: fg.g * fg.a + bg.g * (1 - fg.a), b: fg.b * fg.a + bg.b * (1 - fg.a), a: 1 });
function luminance(c) {
  const f = (x) => { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
}
function contrast(a, b) {
  const la = luminance(a), lb = luminance(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

test("the two light theme blocks are identical, and cover every colour the dark theme sets", () => {
  assert.deepEqual(LIGHT_MEDIA, LIGHT_EXPLICIT, "the OS-preference block and the data-theme block must not drift apart");
  const shared = new Set(["--on-accent", "--grad-btn", "--grad-meter", "--grad-xp", "--grade-a", "--grade-b", "--grade-c", "--grade-d"]);
  const colourful = (v) => /#[0-9a-f]{3,6}\b|rgba?\(/i.test(v);
  const gaps = Object.keys(DARK).filter((k) => colourful(DARK[k]) && !(k in LIGHT_EXPLICIT) && !shared.has(k));
  assert.deepEqual(gaps, [], "colour tokens that the light theme forgot to override");
  for (const k of Object.keys(LIGHT_EXPLICIT)) assert.ok(k in DARK, `${k} exists only in the light theme`);
});

for (const theme of ["dark", "light"]) {
  test(`${theme} theme: text colours reach 4.5:1 on every surface they sit on`, () => {
    const T = theme === "dark" ? DARK : Object.assign({}, DARK, LIGHT_EXPLICIT);
    const col = (k) => { const c = parseColor(T[k]); assert.ok(c, `${theme} ${k} = ${T[k]}`); return c; };
    const surfaces = ["--bg", "--surface", "--surface-2", "--surface-3"];
    const fails = [];
    const check = (fgName, bg, bgName, min) => {
      const fg = col(fgName);
      const ratio = contrast(over(fg, bg), bg);
      if (ratio < min) fails.push(`${fgName} on ${bgName}: ${ratio.toFixed(2)} (needs ${min})`);
    };
    for (const s of surfaces) {
      for (const fg of ["--text", "--text-2", "--text-3", "--accent-ink", "--info-ink", "--ok-ink", "--xp-ink", "--risk-ink", "--warn-ink", "--pink-ink"]) {
        check(fg, col(s), s, 4.5);
      }
    }
    // Chips and notes: the ink colour over its own tint over the card surface.
    for (const [ink, tint] of [["--accent-ink", "--tint-brand"], ["--info-ink", "--tint-info"], ["--ok-ink", "--tint-ok"], ["--xp-ink", "--tint-xp"], ["--risk-ink", "--tint-risk"], ["--warn-ink", "--tint-warn"]]) {
      for (const s of ["--surface", "--surface-2"]) {
        const bg = over(col(tint), col(s));
        check(ink, bg, `${tint} over ${s}`, 4.5);
      }
    }
    // The text colour on gradient buttons, and on the grade badges, in both ends of the gradient.
    const ends = [...T["--grad-btn"].matchAll(/#[0-9a-f]{6}/gi)].map((m) => parseColor(m[0]));
    assert.equal(ends.length, 2);
    for (const e of ends) { const r = contrast(col("--on-accent"), e); if (r < 4.5) fails.push(`on-accent on button gradient: ${r.toFixed(2)}`); }
    for (const g of ["--grade-a", "--grade-b", "--grade-c", "--grade-d"]) { const r = contrast({ r: 255, g: 255, b: 255, a: 1 }, col(g)); if (r < 4.5) fails.push(`white on ${g}: ${r.toFixed(2)}`); }
    assert.deepEqual(fails, []);
  });

  test(`${theme} theme: focus rings and chart colours reach 3:1 on the surfaces`, () => {
    const T = theme === "dark" ? DARK : Object.assign({}, DARK, LIGHT_EXPLICIT);
    const col = (k) => parseColor(T[k]);
    const fails = [];
    for (const s of ["--bg", "--surface", "--surface-2"]) {
      for (const fg of ["--focus", "--series-1", "--series-2", "--series-3", "--series-4", "--rc-rare", "--rc-epic", "--rc-legendary"]) {
        const r = contrast(col(fg), col(s));
        if (r < 3) fails.push(`${fg} on ${s}: ${r.toFixed(2)}`);
      }
    }
    assert.deepEqual(fails, []);
  });
}

test("chart series colours stay distinguishable for the common kinds of colour blindness", () => {
  // Simulate protanopia, deuteranopia and tritanopia with the Machado matrices and require a minimum distance
  // between the first two series (the blue and orange pair used for A versus B) in both themes.
  const M = {
    protan: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
    deutan: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
    tritan: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.303900]]
  };
  const lin = (x) => { x /= 255; return x <= 0.04045 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); };
  const apply = (m, c) => [0, 1, 2].map((i) => m[i][0] * lin(c.r) + m[i][1] * lin(c.g) + m[i][2] * lin(c.b));
  const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
  for (const T of [DARK, Object.assign({}, DARK, LIGHT_EXPLICIT)]) {
    const a = parseColor(T["--series-1"]), b = parseColor(T["--series-2"]);
    assert.ok(dist([lin(a.r), lin(a.g), lin(a.b)], [lin(b.r), lin(b.g), lin(b.b)]) > 0.2, "normal vision");
    for (const [name, m] of Object.entries(M)) assert.ok(dist(apply(m, a), apply(m, b)) > 0.1, `${name}: series 1 and 2 are too close`);
  }
});
