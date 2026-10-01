"use strict";
// Czech and English strings: identical key sets, no gaps, matching placeholders, and every key the sources use exists.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const i18n = require("../src/i18n.js");
const game = require("../src/game.js");

const SRC = path.resolve(__dirname, "..", "src");
const ROOT = path.resolve(__dirname, "..", "..");
const EN = i18n.dictionaries.en;
const CS = i18n.dictionaries.cs;
const placeholders = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
const EM = "\u2014";
const EN_DASH = "\u2013";

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) return walk(p);
    return e.name.endsWith(".js") ? [p] : [];
  });
}

test("both languages have exactly the same keys", () => {
  assert.deepEqual(Object.keys(EN).sort(), Object.keys(CS).sort());
  assert.ok(Object.keys(EN).length > 800, "expected the full string table");
});

test("no empty, untrimmed or placeholder-looking values", () => {
  for (const lang of ["en", "cs"]) {
    const dict = i18n.dictionaries[lang];
    for (const [k, v] of Object.entries(dict)) {
      assert.equal(typeof v, "string", `${lang} ${k}`);
      assert.ok(v.length > 0, `${lang} ${k} is empty`);
      assert.equal(v, v.trim(), `${lang} ${k} has surrounding whitespace`);
      assert.ok(!/TODO|TBD|lorem ipsum|undefined|\[object/i.test(v), `${lang} ${k} looks unfinished: ${v}`);
    }
  }
});

test("placeholders match between Czech and English", () => {
  for (const k of Object.keys(EN)) assert.deepEqual(placeholders(CS[k]), placeholders(EN[k]), `placeholders of ${k}`);
});

test("no em dash or en dash in any string", () => {
  for (const [k, v] of Object.entries(EN)) assert.ok(!v.includes(EM) && !v.includes(EN_DASH), `en ${k}`);
  for (const [k, v] of Object.entries(CS)) assert.ok(!v.includes(EM) && !v.includes(EN_DASH), `cs ${k}`);
});

test("Czech is really translated for most keys, and carries diacritics", () => {
  const keys = Object.keys(EN);
  const same = keys.filter((k) => EN[k] === CS[k]);
  // Brand names, units and a few shared words are identical in both languages; copy-pasted English would be far more.
  assert.ok(same.length / keys.length < 0.12, `${same.length} of ${keys.length} Czech strings equal the English ones`);
  const withDiacritics = keys.filter((k) => /[áčďéěíňóřšťúůýž]/i.test(CS[k]));
  assert.ok(withDiacritics.length / keys.length > 0.5, "Czech strings should use diacritics");
  assert.ok(!keys.some((k) => /\ufffd/.test(CS[k]) || /Ã|Å¡|Ä/.test(CS[k])), "mojibake in a Czech string");
});

test("plural families are complete in both languages", () => {
  // A family is every key that has a ".one" form (the plain key "platform.other" is just the platform called Other).
  const bases = new Set(Object.keys(EN).filter((k) => /\.one$/.test(k)).map((k) => k.replace(/\.one$/, "")));
  assert.ok(bases.size >= 8);
  for (const b of bases) {
    assert.ok(EN[b + ".one"] && EN[b + ".other"], `${b}: one and other`);
    assert.ok(CS[b + ".one"] && CS[b + ".few"] && CS[b + ".other"], `${b}: Czech needs one, few and other`);
  }
});

test("tp picks the right plural form per language", () => {
  assert.equal(i18n.tp("guru.weeks", 1, null, "en"), "1 week");
  assert.equal(i18n.tp("guru.weeks", 4, null, "en"), "4 weeks");
  assert.equal(i18n.tp("guru.weeks", 1, null, "cs"), "1 týden");
  assert.equal(i18n.tp("guru.weeks", 2, null, "cs"), "2 týdny");
  assert.equal(i18n.tp("guru.weeks", 4, null, "cs"), "4 týdny");
  assert.equal(i18n.tp("guru.weeks", 5, null, "cs"), "5 týdnů");
  assert.equal(i18n.tp("guru.weeks", 0, null, "cs"), "0 týdnů");
});

test("t, pick, fmt and detectLang behave", () => {
  assert.equal(i18n.t("nav.home", null, "cs"), "Domů");
  assert.equal(i18n.t("nav.home", null, "en"), "Home");
  assert.equal(i18n.t("no.such.key"), "no.such.key");
  assert.equal(i18n.t("top.level", { n: 3 }, "en"), "Level 3");
  assert.equal(i18n.t("top.level", {}, "en"), "Level {n}", "missing params keep the placeholder");
  assert.equal(i18n.pick({ name_en: "A", name_cs: "B" }, "name", "cs"), "B");
  assert.equal(i18n.pick({ name_en: "A" }, "name", "cs"), "A", "falls back to English");
  assert.equal(i18n.pick({ name: "Z" }, "name", "cs"), "Z", "falls back to the plain field");
  assert.equal(i18n.pick(null, "name"), "");
  i18n.setLang("cs");
  assert.equal(i18n.fmt(1234.5, 1), "1\u00a0234,5");
  assert.equal(i18n.fmt(NaN), "-");
  i18n.setLang("en");
  assert.equal(i18n.fmt(1234.5, 1), "1,234.5");
  assert.equal(i18n.getLang(), "en");
  assert.equal(i18n.setLang("de"), "en", "unknown language falls back to English");
  assert.equal(i18n.detectLang("cs-CZ"), "cs");
  assert.equal(i18n.detectLang("cs"), "cs");
  assert.equal(i18n.detectLang("en-GB"), "en");
  assert.equal(i18n.detectLang(""), "en");
  assert.equal(i18n.detectLang(undefined), "en");
});

// ---- every key used in the sources exists -------------------------------------------------------
const CALL = /\b(?:t|tp)\(\s*"([A-Za-z0-9_.]+)"(\s*\+)?/g;

test("every translation key used in the sources exists", () => {
  const files = walk(SRC).filter((f) => path.basename(f) !== "i18n.js");
  assert.ok(files.length >= 15, "expected to scan the UI sources");
  const missing = [];
  let literal = 0, dynamic = 0;
  for (const file of files) {
    const text = fs.readFileSync(file, "utf8");
    for (const m of text.matchAll(CALL)) {
      const key = m[1];
      const rel = path.relative(SRC, file);
      if (m[2] || key.endsWith(".")) {
        dynamic += 1;
        const prefix = key;
        if (!Object.keys(EN).some((k) => k.startsWith(prefix))) missing.push(`${rel}: no keys start with ${prefix}`);
      } else {
        literal += 1;
        if (!(key in EN) && !(key + ".other" in EN)) missing.push(`${rel}: ${key}`);
      }
    }
  }
  assert.ok(literal > 400, `only ${literal} literal keys found`);
  assert.ok(dynamic > 15, `only ${dynamic} dynamic prefixes found`);
  assert.deepEqual(missing, []);
});

test("keys composed at run time exist for every possible value", () => {
  const need = [];
  const family = (prefix, suffixes) => suffixes.forEach((s) => need.push(prefix + s));
  family("nav.", ["home", "arena", "boss", "lab", "vault", "forge", "guru", "about", "more", "label", "moreLabel"]);
  family("quest.", game.QUEST_POOL.map((q) => q.id));
  family("forge.goal.", ["awareness", "consideration", "conversion", "retention", "community"]);
  family("forge.verdict.", ["ok", "review", "blocked"]);
  family("forge.sev.", ["error", "warn", "info"]);
  family("forge.shield.", ["ok", "review", "blocked"]);
  family("boss.shield.", ["intact", "cracked", "broken", "idle"]);
  family("boss.shieldRange.", ["intact", "cracked", "broken"]);
  family("vault.rarity.", game.RARITIES);
  family("vault.kind.", ["pattern", "tip", "study", "tactic"]);
  family("about.score.d.", ["curiosity", "surprise", "emotion", "relevance", "utility", "fluency", "risk"]);
  family("about.score.step.", ["1", "2", "3", "4", "5", "6"]);
  family("guru.day.", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
  family("guru.dayShort.", ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]);
  family("profile.importErr.", ["empty", "too_large", "invalid_json", "wrong_app", "invalid_profile", "read"]);
  family("boss.tier", ["1", "2", "3"]);
  for (const k of need) assert.ok(k in EN || k + ".other" in EN, `missing ${k}`);
});

test("channel, format and KPI names cover everything the Python planner can produce", (t) => {
  const code = [
    "import json, sys",
    "sys.path.insert(0, 'src')",
    "from dopamine_king.guru import planner",
    "from dopamine_king.generate import formats",
    "print(json.dumps({'channels': list(planner.CHANNELS), 'kpis': [c['kpi'] for c in planner.CHANNELS.values()] + [h[2] for h in planner.HYPOTHESES],",
    " 'formats': [s.id for s in formats.list_formats()], 'days': list(planner.DAYS)}))"
  ].join("\n");
  const run = spawnSync("python3", ["-c", code], { cwd: ROOT, encoding: "utf8" });
  if (run.status !== 0) { t.skip("python3 or the package is not available: " + String(run.stderr).split("\n")[0]); return; }
  const info = JSON.parse(run.stdout);
  const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  for (const c of info.channels) assert.ok(("guru.channel." + c) in EN, "channel " + c);
  for (const f of info.formats) assert.ok(("fmt." + f) in EN, "format " + f);
  for (const k of info.kpis) assert.ok(("guru.kpi." + slug(k)) in EN, "kpi " + k);
  for (const d of info.days) assert.ok(("guru.day." + d) in EN && ("guru.dayShort." + d) in EN, "day " + d);
});

test("game content is bilingual and free of dashes", () => {
  for (const lv of game.LEVELS) { assert.ok(lv.en && lv.cs); assert.ok(!(lv.en + lv.cs).match(/[\u2013\u2014]/)); }
  for (const a of game.ACHIEVEMENTS) {
    for (const f of ["name", "desc"]) {
      assert.ok(a[f].en && a[f].cs, `${a.id}.${f}`);
      assert.ok(!(a[f].en + a[f].cs).match(/[\u2013\u2014]/), `${a.id}.${f}`);
    }
  }
  assert.equal(game.ACHIEVEMENTS.length >= 12, true);
});

test("the bundle carries both languages for every piece of text the UI reads", () => {
  const bundle = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "dev", "bundle.json"), "utf8"));
  for (const d of bundle.arena) assert.ok(d.a && d.b, "arena duel texts");
  for (const m of bundle.myths) { assert.ok(m.en && m.cs && m.why_en && m.why_cs, m.id); }
  for (const b of bundle.bosses) { assert.ok(b.brief_en && b.brief_cs && b.taunt_en && b.taunt_cs, b.id); }
  for (const c of bundle.loot.cards) { assert.ok(c.title_en && c.title_cs && c.body_en && c.body_cs, c.id); }
  for (const s of bundle.lab.scenarios) { assert.ok(s.title_en && s.title_cs, s.id); }
  for (const [k, v] of Object.entries(bundle.spec.labels)) assert.ok(v.en && v.cs, k);
  for (const [k, v] of Object.entries(bundle.spec.messages)) assert.ok(v.en && v.cs, k);
});

// ---- Czech typography ---------------------------------------------------------------------------
test("Czech text keeps one letter words and units together with a no-break space", () => {
  const NB = "\u00a0";
  assert.equal(i18n.czechTypo("v lese a v poli"), `v${NB}lese a${NB}v${NB}poli`);
  assert.equal(i18n.czechTypo("A nebo B"), `A${NB}nebo B`);
  assert.equal(i18n.czechTypo("Je to 20 % a 5 XP za 3 min"), `Je to 20${NB}% a${NB}5${NB}XP za 3${NB}min`);
  assert.equal(i18n.czechTypo("2 z 3"), `2 z${NB}3`);
  assert.equal(i18n.czechTypo("ve se na do"), "ve se na do", "longer words are left alone");
  assert.equal(i18n.czechTypo("5 minut"), "5 minut", "a unit must be a whole word");
  assert.equal(i18n.t("top.level", { n: 3 }, "en"), "Level 3", "English is untouched");
  assert.ok(i18n.t("home.xp.ethics", null, "cs").includes(NB), "t() applies it to Czech strings");
});

test("dom.typo uses the quotation marks of the UI language", () => {
  const vm = require("node:vm");
  const load = (lang) => {
    const sandbox = { DK: { i18n: { getLang: () => lang, t: (k) => k, fmt: String } } };
    sandbox.self = sandbox;
    vm.runInNewContext(fs.readFileSync(path.join(SRC, "ui", "dom.js"), "utf8"), sandbox);
    return sandbox.DK.ui.dom;
  };
  const q = (a, b) => String.fromCharCode(a) + "ahoj" + String.fromCharCode(b);
  assert.equal(load("cs").typo('say "ahoj"'), "say " + q(0x201e, 0x201c));
  assert.equal(load("en").typo('say "ahoj"'), "say " + q(0x201c, 0x201d));
  assert.equal(load("cs").typo("no quotes"), "no quotes");
  assert.equal(load("cs").typo(null), "");
  assert.equal(load("cs").typo('"a" and "b"'), String.fromCharCode(0x201e) + "a" + String.fromCharCode(0x201c) + " and " + String.fromCharCode(0x201e) + "b" + String.fromCharCode(0x201c));
});
