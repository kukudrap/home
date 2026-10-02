"use strict";
// The claims checker (web/src/claims.js) is an exact port of ClaimsProfile.scan_text. The golden file is written by
// scripts/gen_golden_claims.py (do not edit it by hand); every case must give identical (code, topic, start, end).
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const claims = require("../src/claims.js");
const golden = require("./claims.golden.json");

const ROOT = path.resolve(__dirname, "..", "..");
const compiled = claims.compile(golden.rules);
const scan = (text, opts) => claims.scan(compiled, text, opts);
const codes = (text, opts) => scan(text, opts).map((h) => h.code);
const brief = (hits) => hits.map((h) => `${h.code}:${h.topic}:${h.start}-${h.end}`);

// -- golden parity ----------------------------------------------------------------------------------------------
test("every rule pattern of the shipped rules compiles in JavaScript", () => {
  assert.deepEqual(compiled.errors, []);
  assert.ok(compiled.topics.length >= 15, "the topics are compiled");
  const silent = compiled.topics.filter((t) => !t.regex && !t.patterns.length);
  assert.ok(compiled.topics.length - silent.length >= 15, "the topics that can be hit have a matcher");
  assert.ok(silent.every((t) => t.klass === "context"), "only background topics (dose, safety) have nothing to match");
});

test("the golden file holds the cases and the rules the game ships", () => {
  assert.ok(golden.cases.length >= 148);
  assert.ok(Array.isArray(golden.rules.topics) && golden.rules.topics.length >= 15);
  for (const key of ["treatment_verbs", "disease_terms", "negation_words", "clause_breakers", "masking_phrases", "targeting_phrases", "medication_patterns", "timeline_patterns", "dose_patterns"]) {
    assert.ok(golden.rules[key], `rules.${key}`);
  }
  const seen = new Set(golden.cases.flatMap((c) => c.hits.map((h) => h.code)));
  for (const code of claims.CODES.filter((c) => c !== "SAFETY_NOTE_MISSING")) assert.ok(seen.has(code), `the golden cases cover ${code}`);
});

test("the JavaScript checker gives the same hits as Python for every golden case", () => {
  const failures = [];
  for (const c of golden.cases) {
    const got = scan(c.text);
    try { assert.deepEqual(got, c.hits); } catch (e) { failures.push(`${JSON.stringify(c.text)}\n   js: ${brief(got).join(" | ")}\n   py: ${brief(c.hits).join(" | ")}`); }
  }
  assert.deepEqual(failures, [], `${failures.length} of ${golden.cases.length} cases differ:\n${failures.join("\n")}`);
});

test("hits come sorted by start, end and code", () => {
  for (const c of golden.cases) {
    const got = scan(c.text);
    for (let i = 1; i < got.length; i++) {
      const a = got[i - 1], b = got[i];
      assert.ok(a.start < b.start || (a.start === b.start && (a.end < b.end || (a.end === b.end && a.code <= b.code))), c.text);
    }
  }
});

test("severities match the Python RULES table", (t) => {
  const res = spawnSync("python3", ["-c", "import json; from dopamine_king.generate.claims import RULES; print(json.dumps({k: v[0] for k, v in RULES.items()}))"],
    { cwd: ROOT, encoding: "utf8", env: Object.assign({}, process.env, { PYTHONPATH: path.join(ROOT, "src") }) });
  if (res.status !== 0) { t.skip(`python3 is not available: ${res.stderr.trim().slice(0, 120)}`); return; }
  const py = JSON.parse(res.stdout);
  assert.deepEqual(claims.SEVERITY, py);
  assert.deepEqual([...claims.CODES].sort(), Object.keys(py).sort());
});

// Random texts built from the rules' own vocabulary (verbs, nouns, diseases, negations, hedges, masks, status words,
// time promises, odd spacing, capitals, no diacritics, line breaks) are scanned by the Python reference and by the port.
// It runs only when python3 and the package are available, and it is seeded, so a failure repeats.
const FUZZ_PY = [
  "import json, random, sys, unicodedata",
  "sys.path.insert(0, 'src')",
  "from dopamine_king.generate import claims",
  "from dopamine_king.verticals import load_vertical",
  "rules = load_vertical('pbm').claim_rules()",
  "p = claims.load_profile('pbm')",
  "random.seed(int(sys.argv[1]))",
  "def words(t): return [x.replace('*', random.choice(['', 's', 'ed', 'ing', 'i', 'e', 'a', 'ou'])) for l in ('en', 'cs') for x in (t or {}).get(l, [])]",
  "keys = ['treatment_verbs','benefit_verbs','disease_terms','device_words','negation_words','hedge_words','regulated_status','safety_absolute','masking_phrases','targeting_phrases','therapy_words']",
  "pools = [words(rules[k]) for k in keys]",
  "nouns = [n.replace('*', '') for t in rules['topics'] for n in (t.get('nouns_en') or []) + (t.get('nouns_cs') or [])]",
  "extra = ['replace your painkillers', 'stop taking medication', 'say goodbye to your doctor', 'nahradte leky', 'results in 14 days', 'za 3 tydny uvidite rozdil', 'vysledky za 14 dni', 'within 30 days you will notice',",
  "         'the', 'a', 'your', 'panel', 'for', 'and', 'se', 'na', 'pro', 'je', 'to', 'every day', '10 minutes', '15 cm', 'sezeni', 'sessions']",
  "puncts = ['.', '.', '!', '?', ',', ';', ':', '\\n', ' - ', '...', ' (', ') ', '\\u00a0', '  ']",
  "def sentence():",
  "    parts = []",
  "    for _ in range(random.randint(2, 9)):",
  "        r = random.random()",
  "        if r < 0.55: parts.append(random.choice(random.choice(pools)))",
  "        elif r < 0.7: parts.append(random.choice(nouns))",
  "        else: parts.append(random.choice(extra))",
  "        if random.random() < 0.12: parts[-1] += random.choice(puncts)",
  "    text = ' '.join(x for x in parts if x)",
  "    if random.random() < 0.3: text += random.choice(['.', '?', '!', '. ', '\\n'])",
  "    if random.random() < 0.25: text = text.upper()",
  "    if random.random() < 0.3: text = ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c))",
  "    return text",
  "cases = []",
  "for _ in range(int(sys.argv[2])):",
  "    text = ' '.join(sentence() for _ in range(random.randint(1, 3)))",
  "    hits = sorted(p.scan_text(text), key=lambda h: (h.start, h.end, h.code))",
  "    cases.append({'text': text, 'hits': [{'code': h.code, 'topic': h.topic.id if h.topic else None, 'start': h.start, 'end': h.end} for h in hits]})",
  "print(json.dumps({'rules': rules, 'cases': cases}, ensure_ascii=False))"
].join("\n");

test("random texts from the rules vocabulary give the same hits in Python and in the port", (t) => {
  const res = spawnSync("python3", ["-c", FUZZ_PY, "7", "600"], {
    cwd: ROOT, encoding: "utf8", maxBuffer: 1 << 28, env: Object.assign({}, process.env, { PYTHONPATH: path.join(ROOT, "src"), PYTHONHASHSEED: "0" })
  });
  if (res.status !== 0) { t.skip(`python3 or the package is not available: ${String(res.stderr).split("\n").filter(Boolean).pop()}`); return; }
  const data = JSON.parse(res.stdout);
  assert.deepEqual(data.rules, golden.rules, "Python and the golden file ship the same rules (regenerate the golden file otherwise)");
  const fuzzed = claims.compile(data.rules);
  assert.equal(fuzzed.errors.length, 0);
  let hits = 0;
  const failures = [];
  for (const c of data.cases) {
    const got = claims.scan(fuzzed, c.text);
    hits += c.hits.length;
    try { assert.deepEqual(got, c.hits); } catch (e) { failures.push(`${JSON.stringify(c.text)}\n   js: ${brief(got).join(" | ")}\n   py: ${brief(c.hits).join(" | ")}`); }
  }
  assert.ok(hits > 300, `the random texts exercise the rules (${hits} hits)`);
  assert.deepEqual(failures.slice(0, 5), [], `${failures.length} of ${data.cases.length} random cases differ`);
});

// -- severity helpers ---------------------------------------------------------------------------------------------
test("severity helpers: errors block, warnings advise, info informs", () => {
  for (const code of ["CLAIM_MEDICAL", "CLAIM_AVOID", "DISEASE_MENTION", "STATUS_CLAIM", "SAFETY_ABSOLUTE", "MEDICATION_ADVICE"]) {
    assert.equal(claims.severity(code), "error");
    assert.equal(claims.isError(code), true);
  }
  for (const code of ["CLAIM_UNHEDGED", "OUTCOME_PROMISE", "DOSE_NOT_FROM_MANUAL", "SAFETY_NOTE_MISSING"]) assert.equal(claims.severity(code), "warn");
  assert.equal(claims.severity("THERAPY_WORD"), "info");
  assert.equal(claims.severity("SOMETHING_NEW"), "info", "unknown codes never block");
  assert.equal(claims.isError("THERAPY_WORD"), false);
  assert.deepEqual(claims.summarize(scan("Red light cures joint pain. Results in 14 days. Light therapy")), { error: 1, warn: 1, info: 1, total: 3 });
  assert.deepEqual(claims.summarize([]), { error: 0, warn: 0, info: 0, total: 0 });
  assert.deepEqual(claims.summarize(null), { error: 0, warn: 0, info: 0, total: 0 });
});

// -- compiler ---------------------------------------------------------------------------------------------------------------
test("the term compiler folds, joins words with space or hyphen and expands the stem wildcard", () => {
  assert.equal(claims.termRegex("lecb*"), "lecb\\w*");
  assert.equal(claims.termRegex("Léč*"), "lec\\w*", "diacritics are folded");
  assert.equal(claims.termRegex("  get rid of "), "get[\\s-]+rid[\\s-]+of");
  assert.equal(claims.termRegex("near-infrared"), "near\\-infrared");
  assert.equal(claims.termRegex("zdravotnick* prostredek"), "zdravotnick\\w*[\\s-]+prostredek");
  assert.equal(claims.termRegex("100%"), "100%");
  assert.equal(claims.termRegex("***"), "", "a bare wildcard is empty");
  assert.equal(claims.termRegex(""), "");
});

test("an alternation lists the longest term first, drops duplicates and anchors on word boundaries", () => {
  const src = claims.termsRegex(["heal", "heals", "healing", "heal", "Heal"]);
  assert.equal(src, "\\b(?:healing|heals|heal)\\b");
  const re = new RegExp(src, "g");
  assert.deepEqual("it heals and healing and healer".match(re), ["heals", "healing"]);
  assert.equal(claims.termsRegex([]), "(?!x)x");
  assert.equal(claims.termsRegex(["", "***"]), "(?!x)x");
  assert.equal(new RegExp(claims.termsRegex([]), "g").test("anything at all"), false);
});

test("proximity allows a window of words in either order and never crosses a sentence end", () => {
  const re = new RegExp(claims.proximity("cure", "pain"), "g");
  assert.ok(re.test("cure the pain"));
  assert.ok(new RegExp(claims.proximity("cure", "pain"), "g").test("pain you can cure"));
  assert.ok(new RegExp(claims.proximity("cure", "pain"), "g").test("cure one two three four five pain"), "five words in between");
  assert.ok(!new RegExp(claims.proximity("cure", "pain"), "g").test("cure one two three four five six pain"), "six words are too far");
  assert.ok(!new RegExp(claims.proximity("cure", "pain"), "g").test("cure it. pain"), "a full stop ends the window");
  assert.ok(!new RegExp(claims.proximity("cure", "pain"), "g").test("cure\npain"), "so does a line break");
  assert.ok(new RegExp(claims.proximity("cure", "pain", 8), "g").test("cure one two three four five six seven pain"), "a wider window");
});

test("compile copes with missing rules and reports a pattern that is not valid JavaScript", () => {
  const empty = claims.compile({});
  assert.deepEqual(claims.scan(empty, "Red light cures joint pain."), []);
  assert.deepEqual(claims.scan(claims.compile(null), "anything"), []);
  const odd = claims.compile({ timeline_patterns: { en: ["(?<broken", "\\bin \\d+ days\\b"], cs: [] } });
  assert.equal(odd.errors.length, 1);
  assert.equal(odd.errors[0].what, "timeline_patterns");
  assert.deepEqual(claims.scan(odd, "Results in 3 days").map((h) => h.code), ["OUTCOME_PROMISE"], "the valid pattern still works");
});

test("compiling the same rules object twice returns the cached result", () => {
  assert.equal(claims.compile(golden.rules), compiled);
  assert.notEqual(claims.compile(Object.assign({}, golden.rules)), compiled);
});

// -- text plumbing -------------------------------------------------------------------------------------------------------
test("fold_aligned keeps every index: same length, folded letters, plain spaces and apostrophes", () => {
  const NBSP = String.fromCharCode(0xa0), THIN = String.fromCharCode(0x2009), NARROW = String.fromCharCode(0x202f), RSQUO = String.fromCharCode(0x2019);
  const text = "Červené SVĚTLO" + NBSP + "léčí" + THIN + "bolest" + NARROW + "kloubů, doesn" + RSQUO + "t";
  const low = claims.foldAligned(text);
  assert.equal(low.length, text.length);
  assert.equal(low, "cervene svetlo leci bolest kloubu, doesn't");
  assert.equal(claims.foldAligned(""), "");
  assert.equal(claims.foldAligned(null), "");
  assert.equal(claims.foldAligned("Straße"), "straße", "a letter that does not decompose stays as it is");
  assert.equal(claims.foldAligned("a\u{1F600}b").length, 4, "astral characters keep their UTF-16 length");
  assert.equal(claims.foldAligned("İ"), "i", "a lower case form of several characters folds to one");
  const DASH = String.fromCharCode(0x2014), ELLIPSIS = String.fromCharCode(0x2026);
  assert.equal(claims.foldAligned(DASH + " " + ELLIPSIS), DASH + " " + ELLIPSIS, "punctuation is untouched");
});

test("sentences end at . ! ? and at line breaks; empty pieces are not sentences", () => {
  const spans = (s) => claims.sentenceSpans(s).map(([a, b]) => s.slice(a, b));
  assert.deepEqual(spans("One. Two! Three? Four"), ["One.", "Two!", "Three?", "Four"]);
  assert.deepEqual(spans("Line one\nLine two\n\n\nLine three"), ["Line one", "Line two", "Line three"]);
  assert.deepEqual(spans("He said (\"stop.\") Then left."), ["He said (\"stop.", "Then left."], "a closing quote or bracket belongs to the boundary");
  assert.deepEqual(spans("Wait" + String.fromCharCode(0x2026) + " what"), ["Wait" + String.fromCharCode(0x2026), "what"]);
  assert.deepEqual(spans("   "), []);
  assert.deepEqual(spans(""), []);
  assert.deepEqual(spans("3.5 cm"), ["3.5 cm"], "no space after the dot, no boundary");
});

test("a claim inside a question is not a claim; the first terminator on the line decides", () => {
  assert.equal(claims.isQuestionAt("does red light cure pain?", 20), true);
  assert.equal(claims.isQuestionAt("it cures pain. really?", 8), false);
  assert.equal(claims.isQuestionAt("it cures pain\nreally?", 8), false, "only the same line counts");
  assert.equal(claims.isQuestionAt("no terminator at all", 3), false);
  assert.equal(claims.isQuestionAt("short", 99), false);
  assert.deepEqual(codes("Does red light cure pain?"), []);
  assert.deepEqual(codes("Can red light cure pain?"), []);
  assert.deepEqual(codes("It is simple. Red light cures joint pain."), ["CLAIM_MEDICAL"]);
  assert.deepEqual(codes("Red light cures joint pain?"), [], "even a rhetorical question is skipped");
});

// -- behaviour -------------------------------------------------------------------------------------------------------------
test("the strongest class wins and the topic and span are reported", () => {
  const hits = scan("Red light cures joint pain.");
  assert.deepEqual(hits, [{ code: "CLAIM_MEDICAL", topic: "pbm-pain-joints", start: 10, end: 26 }]);
  assert.deepEqual(scan("Boosts testosterone."), [{ code: "CLAIM_AVOID", topic: "pbm-testosterone", start: 0, end: 19 }]);
  assert.deepEqual(scan("Supports your recovery."), [{ code: "CLAIM_UNHEDGED", topic: "pbm-muscle-recovery", start: 0, end: 22 }]);
  for (const h of scan("Treats depression and anxiety.")) assert.equal(compiled.byId[h.topic].klass, "medical");
  assert.equal(claims.topicOf(compiled, "pbm-pain-joints").klass, "medical");
  assert.equal(claims.topicOf(compiled, "nope"), null);
  assert.equal(claims.topicOf(compiled, null), null);
});

test("hedged wording is allowed for benefits but never for medical claims", () => {
  assert.deepEqual(codes("Supports muscle recovery."), ["CLAIM_UNHEDGED"]);
  assert.deepEqual(codes("Some studies suggest red light may support muscle recovery after exercise in healthy adults."), []);
  assert.deepEqual(codes("Red light may support recovery, according to some studies."), []);
  assert.deepEqual(codes("Zlepšuje spánek (may support sleep)."), [], "an English hedge covers a Czech sentence too");
  assert.deepEqual(codes("It may cure joint pain."), ["CLAIM_MEDICAL"], "a hedge does not rescue a medical claim");
});

test("negation: the nearest negation word counts while it is close and no new clause starts", () => {
  assert.deepEqual(codes("The device does not treat disease and does not replace medical care."), []);
  assert.deepEqual(codes("Přístroj neslouží k léčbě nemocí a nenahrazuje lékařskou péči."), []);
  assert.deepEqual(codes("This is not a medical device and it cannot cure pain."), []);
  assert.deepEqual(codes("Ochrana očí není nutná, je to naprosto neškodné."), ["SAFETY_ABSOLUTE", "SAFETY_ABSOLUTE"], "a comma and a new clause end the negation");
  assert.deepEqual(codes("You do not need eye protection, it is completely harmless."), ["SAFETY_ABSOLUTE"]);
  assert.ok(!codes("No, it is not true that red light cures joint pain.").includes("CLAIM_MEDICAL"));
  assert.deepEqual(codes("Not one of the many things we have ever said or written down anywhere is that red light cures joint pain."), ["CLAIM_MEDICAL"], "a negation word more than 40 characters back is too far");
});

test("standard disclaimers and commerce phrases are masked", () => {
  assert.deepEqual(codes("Risk-free trial for 60 days."), []);
  assert.deepEqual(codes("100% safe checkout and safe payment."), []);
  assert.deepEqual(codes("Vyzkoušejte bez rizika, bezpečná platba."), []);
  assert.deepEqual(codes("This device is not intended to diagnose, treat, cure, or prevent any disease."), []);
  assert.deepEqual(codes("Completely safe and risk-free."), ["SAFETY_ABSOLUTE", "SAFETY_ABSOLUTE"], "outside a masked phrase it is still caught");
});

test("targeting a condition is a claim even as a question; other questions are skipped", () => {
  assert.deepEqual(codes("Do you suffer from migraines? Try our panel."), ["DISEASE_MENTION"]);
  assert.deepEqual(codes("Trpíte artritidou? Vyzkoušejte panel."), ["DISEASE_MENTION"]);
  assert.deepEqual(codes("For people with diabetes: a new panel."), ["DISEASE_MENTION"]);
  assert.deepEqual(codes("People with epilepsy should ask a doctor first."), []);
  assert.deepEqual(codes("Helps with insomnia."), ["DISEASE_MENTION"]);
  assert.deepEqual(codes("Does it help with insomnia?"), []);
});

test("advice to replace or stop medication or medical care is an error", () => {
  assert.deepEqual(codes("Replace your painkillers with red light."), ["MEDICATION_ADVICE"]);
  assert.deepEqual(codes("Stop taking your medication and use red light instead."), ["MEDICATION_ADVICE"]);
  assert.deepEqual(codes("Say goodbye to your doctor."), ["MEDICATION_ADVICE"]);
  assert.deepEqual(codes("Rozlučte se s lékařem."), ["MEDICATION_ADVICE"]);
  assert.equal(claims.severity("MEDICATION_ADVICE"), "error");
  assert.deepEqual(codes("The device does not replace medical care."), []);
});

test("outcome promises, regulatory status and absolute safety words", () => {
  assert.deepEqual(codes("Results in 14 days."), ["OUTCOME_PROMISE"]);
  assert.deepEqual(codes("Za 3 týdny uvidíte rozdíl."), ["OUTCOME_PROMISE"]);
  assert.deepEqual(codes("Za tři týdny uvidíte rozdíl."), [], "only digits make a time frame");
  assert.deepEqual(codes("FDA approved medical device."), ["STATUS_CLAIM", "STATUS_CLAIM"]);
  assert.deepEqual(codes("It is not FDA approved and makes no medical claims."), []);
  assert.deepEqual(codes("Naprosto bezpečné a bez rizika."), ["SAFETY_ABSOLUTE", "SAFETY_ABSOLUTE"]);
  assert.deepEqual(codes("A harmless way to relax."), ["SAFETY_ABSOLUTE"]);
});

test("a dose is reported once per distinct snippet and only next to a usage word", () => {
  assert.deepEqual(codes("Sessions last 10 minutes at 15 cm."), ["DOSE_NOT_FROM_MANUAL", "DOSE_NOT_FROM_MANUAL"]);
  const twice = scan("Sessions last 10 minutes. Use it for 10 minutes.");
  assert.equal(twice.filter((h) => h.code === "DOSE_NOT_FROM_MANUAL").length, 1, "the same figure is not repeated");
  assert.deepEqual(codes("The video is 10 minutes long."), [], "no usage word in the sentence");
});

test("the word therapy is flagged once, at its first use that is not the approved category name, unless it is negated", () => {
  assert.deepEqual(scan("Light therapy and more light therapy"), [{ code: "THERAPY_WORD", topic: null, start: 6, end: 13 }]);
  assert.deepEqual(scan("Red light therapy and more light therapy"), [{ code: "THERAPY_WORD", topic: null, start: 33, end: 40 }], "the approved name is skipped");
  assert.deepEqual(codes("Red light therapy for athletes."), []);
  assert.deepEqual(codes("Terapie \u010derven\u00fdm sv\u011btlem pro ka\u017ed\u00fd den."), []);
  assert.deepEqual(codes("Red light therapy cures joint pain."), ["CLAIM_MEDICAL"], "the approved name never hides a claim");
  assert.deepEqual(codes("This is not a therapy."), []);
});

test("a safety note is expected in long form formats only, and only when the format is passed", () => {
  const text = "A guide to choosing a light panel for your home";
  assert.deepEqual(codes(text), [], "the game passes no format");
  assert.deepEqual(scan(text, { formatId: "seo_article" }), [{ code: "SAFETY_NOTE_MISSING", topic: null, start: 0, end: 0 }]);
  assert.deepEqual(codes(text, { formatId: "instagram_caption" }), []);
  assert.deepEqual(codes(text + ". Protect your eyes and read the user manual.", { formatId: "seo_article" }), []);
  assert.deepEqual(codes(text, { formatId: null }), []);
});

test("placeholders, brackets and markup are plain text here: no special handling in scan_text", () => {
  assert.deepEqual(scan("[[ADD: Explain how red light cures pain]]"), [{ code: "CLAIM_MEDICAL", topic: "pbm-pain-joints", start: 29, end: 39 }]);
  assert.deepEqual(codes("**Red light cures joint pain**"), ["CLAIM_MEDICAL"]);
  assert.deepEqual(codes("<b>Red light cures joint pain</b>"), ["CLAIM_MEDICAL"]);
});

test("Czech typed without diacritics, in capitals, with odd spacing or across a line break", () => {
  assert.deepEqual(codes("Cervene svetlo leci bolest kloubu."), ["CLAIM_MEDICAL"]);
  assert.deepEqual(codes("ČERVENÉ SVĚTLO LÉČÍ BOLEST!!!"), ["CLAIM_MEDICAL"]);
  assert.deepEqual(codes("Léčí  bolest   zad"), ["CLAIM_MEDICAL"]);
  assert.deepEqual(codes("Léčí" + String.fromCharCode(0xa0) + "bolest" + String.fromCharCode(0xa0) + "zad"), ["CLAIM_MEDICAL"], "no-break spaces count as spaces");
  assert.deepEqual(codes("zmírňuje bolest"), ["CLAIM_MEDICAL"]);
  assert.deepEqual(codes("zmírňuje\nbolest"), [], "a line break ends the window");
});

test("empty and odd input never throws", () => {
  assert.deepEqual(scan(""), []);
  assert.deepEqual(scan("   \n  "), []);
  assert.deepEqual(claims.scan(compiled, null), []);
  assert.deepEqual(claims.scan(compiled, undefined), []);
  assert.deepEqual(claims.scan(compiled, 12345), []);
  assert.doesNotThrow(() => scan("x".repeat(20000)));
  assert.doesNotThrow(() => scan("léčí ".repeat(500)));
  assert.doesNotThrow(() => scan("\ud800 lone surrogate \udc00 and \u{1F600} emoji cures pain"));
});

test("scanning does not leak state between calls", () => {
  const a = scan("Red light cures joint pain.");
  scan("Boosts testosterone and treats depression.");
  const b = scan("Red light cures joint pain.");
  assert.deepEqual(a, b);
});

test("the checker is quick enough to run on every keystroke", () => {
  const text = "Mnoho lidí zařazuje sezení pod červeným světlem do večerní rutiny, zlepšuje spánek a regeneraci svalů. ".repeat(3).slice(0, 300);
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < 40; i++) scan(text);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6 / 40;
  assert.ok(ms < 40, `${ms.toFixed(2)} ms per scan of 300 characters`);
});

// -- the bundle ships the same rules ------------------------------------------------------------------------------------
test("web/dev/bundle.json carries the same claim rules as the golden file", (t) => {
  const file = path.join(ROOT, "web", "dev", "bundle.json");
  const bundle = JSON.parse(fs.readFileSync(file, "utf8"));
  if (!bundle.claim_rules) { t.skip("the development bundle is the generic edition"); return; }
  assert.deepEqual(bundle.claim_rules, golden.rules, "regenerate both: scripts/gen_bundle.py and scripts/gen_golden_claims.py");
});
