"use strict";
// scripts/build_web.py: one self-contained HTML file, strict about what goes in, and honest about failures.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const vm = require("node:vm");
const { spawnSync } = require("node:child_process");

const ROOT = path.resolve(__dirname, "..", "..");
const SCRIPT = path.join(ROOT, "scripts", "build_web.py");
const BUNDLE = path.join(ROOT, "web", "dev", "bundle.json");
const FORGE = path.join(ROOT, "web", "dev", "mock-forge.json");
const GURU = path.join(ROOT, "web", "dev", "mock-guru.json");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "dk-build-"));
test.after(() => fs.rmSync(TMP, { recursive: true, force: true }));

const EM = String.fromCharCode(0x2014);
const EN = String.fromCharCode(0x2013);

function run(args) {
  const res = spawnSync("python3", [SCRIPT, ...args], { cwd: ROOT, encoding: "utf8" });
  return { status: res.status, out: res.stdout, err: res.stderr };
}
function build(name, extra = []) {
  const out = path.join(TMP, name);
  const res = run(["--bundle", BUNDLE, "--out", out, "--quiet", ...extra]);
  assert.equal(res.status, 0, `build failed: ${res.err}`);
  return fs.readFileSync(out, "utf8");
}
function embeddedBundle(html) {
  const m = /<script id="dk-bundle" type="application\/json">([\s\S]*?)<\/script>/.exec(html);
  assert.ok(m, "bundle script tag");
  return JSON.parse(m[1]);
}
function jsOrder() {
  const src = fs.readFileSync(SCRIPT, "utf8");
  const block = /JS_ORDER = \[([\s\S]*?)\]/.exec(src)[1];
  return [...block.matchAll(/"([^"]+\.js)"/g)].map((m) => m[1]);
}

test("the build produces one self-contained file", () => {
  const html = build("a.html");
  assert.ok(html.startsWith("<!doctype html>") || html.startsWith("<!DOCTYPE html>"));
  assert.ok(Buffer.byteLength(html) < 1_500_000, "size limit");
  assert.equal((html.match(/<style\b/g) || []).length, 1, "one inline stylesheet");
  assert.equal((html.match(/<script\b/g) || []).length, 2, "the bundle and the code, nothing else");
  const links = html.match(/<link\b[^>]*>/gi) || [];
  assert.ok(links.every((l) => /\bhref="data:/i.test(l)), "the only <link> is the data: URI icon");
  assert.ok(!/<(?:img|iframe|audio|video|source|object|embed)\b/i.test(html), "no media or embeds in the shell");
  assert.ok(!html.includes(EM) && !html.includes(EN), "no em or en dash");
  assert.ok(!/@import|url\(\s*["']?https?:/i.test(html), "no CSS imports or remote urls");
  assert.ok(!/\bsrc\s*=\s*["']?https?:|\bhref\s*=\s*["']?https?:/i.test(html.replace(/<script id="dk-bundle"[\s\S]*?<\/script>/, "")), "no remote src or href");
  assert.match(html, /<meta name="viewport"/);
  assert.match(html, /<html lang="/);
  assert.match(html, /id="dk-skip"/, "skip link");
  assert.match(html, /<noscript>/);
});

test("the inline code is in dependency order and compiles as one script", () => {
  const html = build("order.html");
  const order = jsOrder();
  assert.ok(order.length >= 20);
  let last = -1;
  for (const rel of order) {
    const at = html.indexOf(`/* ---- ${rel} ---- */`);
    assert.ok(at > last, `${rel} must come after the previous file`);
    last = at;
  }
  const blocks = [...html.matchAll(/<script(?![^>]*type="application\/json")[^>]*>([\s\S]*?)<\/script>/g)];
  assert.equal(blocks.length, 1);
  assert.doesNotThrow(() => new vm.Script(blocks[0][1], { filename: "dopamine-king.inline.js" }));
});

test("every source file is in the build order and the dev page loads the same files in the same order", () => {
  const order = jsOrder();
  const found = [];
  const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).forEach((e) => {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p); else if (e.name.endsWith(".js")) found.push(path.relative(path.join(ROOT, "web", "src"), p).split(path.sep).join("/"));
  });
  walk(path.join(ROOT, "web", "src"));
  assert.deepEqual([...found].sort(), [...order].sort());
  const dev = fs.readFileSync(path.join(ROOT, "web", "dev", "index.html"), "utf8");
  const devOrder = [...dev.matchAll(/<script src="\.\.\/src\/([^"]+)"><\/script>/g)].map((m) => m[1]);
  assert.deepEqual(devOrder, order);
});

test("the data bundle is embedded intact, with the development samples as a fallback", () => {
  const source = JSON.parse(fs.readFileSync(BUNDLE, "utf8"));
  const html = build("samples.html", ["--forge", FORGE, "--guru", GURU]);
  const b = embeddedBundle(html);
  assert.deepEqual(Object.keys(b).sort(), Object.keys(source).concat(source.guru_sample ? [] : ["guru_sample"]).sort());
  assert.deepEqual(b.arena, source.arena);
  assert.deepEqual(b.spec, source.spec);
  assert.equal(b.forge_samples.length, 1);
  assert.equal(b.forge_samples[0].items.length, 4);
  assert.equal(b.guru_sample.calendar.length, 20);
  const plain = build("plain.html", ["--no-samples"]);
  const p = embeddedBundle(plain);
  assert.deepEqual(p.forge_samples || [], []);
  assert.ok(!p.guru_sample);
  // Without flags the development samples are picked up on their own.
  const out = path.join(TMP, "default.html");
  const res = run(["--bundle", BUNDLE, "--out", out, "--quiet"]);
  assert.equal(res.status, 0, res.err);
  assert.equal(embeddedBundle(fs.readFileSync(out, "utf8")).forge_samples.length, 1);
});

test("a real sample in the bundle wins over the development one", () => {
  const source = JSON.parse(fs.readFileSync(BUNDLE, "utf8"));
  source.forge_samples = [{ brief: { brand: "Real Co" }, items: [], summary: {}, writer: "x", created: "2026-01-01" }];
  const file = path.join(TMP, "with-real.json");
  fs.writeFileSync(file, JSON.stringify(source));
  const out = path.join(TMP, "real.html");
  const res = run(["--bundle", file, "--out", out, "--quiet", "--forge", FORGE]);
  assert.equal(res.status, 0, res.err);
  assert.equal(embeddedBundle(fs.readFileSync(out, "utf8")).forge_samples[0].brief.brand, "Real Co");
});

test("long dashes in data are replaced and markup-breaking text is escaped", () => {
  const source = JSON.parse(fs.readFileSync(BUNDLE, "utf8"));
  source.myths[0].why_en = `Dash ${EM} test ${EN} here ${EM}</script><script>alert(1)</script><!-- x`;
  const file = path.join(TMP, "evil.json");
  fs.writeFileSync(file, JSON.stringify(source));
  const out = path.join(TMP, "evil.html");
  const res = run(["--bundle", file, "--out", out, "--quiet"]);
  assert.equal(res.status, 0, res.err);
  const html = fs.readFileSync(out, "utf8");
  assert.ok(!html.includes(EM) && !html.includes(EN));
  assert.ok(!html.includes("</script><script>alert(1)"), "a closing script tag in data must be escaped");
  assert.ok(!html.includes("<!-- x"), "an HTML comment opener in data must be escaped");
  const text = embeddedBundle(html).myths[0].why_en;
  assert.ok(text.includes("</script><script>alert(1)</script><!-- x"), "the data survives the round trip");
  assert.ok(text.startsWith("Dash - test - here -"), text);
});

test("problems are reported plainly with a non-zero exit code and no output file", () => {
  const out = path.join(TMP, "never.html");
  const bad = path.join(TMP, "bad.json");
  fs.writeFileSync(bad, "{not json");
  const missingKeys = path.join(TMP, "partial.json");
  fs.writeFileSync(missingKeys, JSON.stringify({ spec: {} }));
  const cases = [
    [["--bundle", path.join(TMP, "nope.json")], /bundle file not found/],
    [["--bundle", bad], /not valid JSON/],
    [["--bundle", missingKeys], /missing required key/],
    [["--bundle", BUNDLE, "--forge", bad], /forge file is not valid JSON/],
    [["--bundle", BUNDLE, "--guru", path.join(TMP, "nope.json")], /guru file not found/]
  ];
  for (const [args, pattern] of cases) {
    const res = run([...args, "--out", out, "--quiet"]);
    assert.equal(res.status, 1, args.join(" "));
    assert.match(res.err, /build failed/);
    assert.match(res.err, pattern);
    assert.ok(!/Traceback/.test(res.err), "no traceback for a user error");
  }
  assert.ok(!fs.existsSync(out), "nothing is written when the build fails");
});

test("the real default path (bundle computed by the Python package) builds too", (t) => {
  const out = path.join(TMP, "computed.html");
  const res = run(["--out", out, "--quiet"]);
  if (res.status !== 0 && /cannot import/.test(res.err)) { t.skip(res.err); return; }
  assert.equal(res.status, 0, res.err);
  const b = embeddedBundle(fs.readFileSync(out, "utf8"));
  assert.equal(b.meta.synthetic, true, "the bundle says its data is simulated");
  assert.ok(b.arena.length >= 100);
  assert.equal(b.forge_samples.length, 2, "one real offline pack per language");
  assert.deepEqual(b.forge_samples.map((p) => p.brief.lang), ["en", "cs"]);
  assert.deepEqual(b.guru_samples.map((p) => p.brief.lang), ["en", "cs"]);
  assert.ok(b.guru_sample, "the legacy single sample stays available");
  assert.ok(b.forge_samples.every((p) => p.writer === "offline" && p.summary.open_slots > 0), "samples are engine output, gaps stay open");
});

test("the demo data is labelled as simulated inside the bundle", () => {
  const b = JSON.parse(fs.readFileSync(BUNDLE, "utf8"));
  assert.equal(b.meta.synthetic, true);
  assert.match(b.meta.note, /SIMULATED/);
});
