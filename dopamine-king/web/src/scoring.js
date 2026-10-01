/* Dopamine Score: JavaScript port of src/dopamine_king/scoring.py.
 *
 * The Dopamine Score is an explainable HEURISTIC, not a neuroscience measurement. It counts how many
 * well documented attention triggers a hook carries (curiosity gap, surprise, emotional arousal,
 * relevance to the reader, concrete utility), weighs how easy it is to process, and subtracts a
 * penalty for clickbait and overclaiming.
 *
 * This file mirrors the Python scorer line by line. web/tests/scoring.parity.test.js replays the
 * golden cases produced by the Python engine and requires every number to match. Result keys are the
 * same snake_case keys as HookScore.to_dict(ndigits=None).
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else { root.DK = root.DK || {}; root.DK.scoring = factory(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var WEIGHTED_DRIVERS = ["curiosity", "surprise", "emotion", "relevance", "utility"];
  var ALL_PARTS = WEIGHTED_DRIVERS.concat(["fluency"]);
  var LEX_CATEGORIES = [
    "curiosity", "contrast", "emotion", "practical", "social", "second_person",
    "clickbait", "overclaim", "positive", "negative"
  ];
  var FEATURE_NAMES = [
    "n_words", "has_number", "starts_with_number", "is_question", "open_loop", "exclaim",
    "caps_ratio", "avg_word_len", "promise_gap",
    "curiosity_hits", "contrast_hits", "emotion_hits", "practical_hits", "social_hits",
    "second_person_hits", "clickbait_hits", "overclaim_hits", "positive_hits", "negative_hits"
  ];

  // Same alternation order as the Python regex: digit groups such as 1,000 or 3.5 stay one token.
  var TOKEN_SRC = "[0-9]+(?:[.,][0-9]+)+|[\\p{L}\\p{N}]+(?:['\\u2019][\\p{L}\\p{N}]+)*";
  var NUM_RE = /^[0-9]+(?:[.,][0-9]+)*$/;
  var INT_RE = /^[0-9]+$/;
  var YEAR_DIGITS_RE = /^[0-9]{4}$/;
  // Python's re.M caret only matches after a line feed; the lookbehind reproduces that exactly.
  var LIST_LINE_RE = /(?<![^\n])[ \t]*(?:[-*•]|[0-9]{1,2}[.)])[ \t]+\S/g;
  var HEADING_RE = /(?<![^\n])[ \t]*#{2,3}[ \t]+\S/g;
  var CS_CHARS = "ěščřžůďťň"; // ě š č ř ž ů ď ť ň
  // Python str.strip() whitespace (str.isspace): not identical to JavaScript trim().
  var PY_WS = "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000";
  var STRIP_LEAD_RE = new RegExp("^[" + PY_WS + "]+");
  var STRIP_TRAIL_RE = new RegExp("[" + PY_WS + "]+$");

  var defaultSpec = null;
  var compiledCache = new WeakMap();

  function setDefaultSpec(spec) { defaultSpec = spec || null; }
  function getDefaultSpec() { return defaultSpec; }

  function has(obj, key) { return Object.prototype.hasOwnProperty.call(obj, key); }

  function normalize(text) { return String(text == null ? "" : text).normalize("NFC"); }

  /** Strip diacritics (used for Czech matching so ASCII-typed text still scores). */
  function fold(text) { return String(text).normalize("NFD").replace(/\p{Mn}/gu, ""); }

  function pyStrip(text) { return text.replace(STRIP_LEAD_RE, "").replace(STRIP_TRAIL_RE, ""); }

  /** Number of leading whitespace characters pyStrip would remove (for overlay offsets). */
  function leadingSpace(text) {
    var m = STRIP_LEAD_RE.exec(text);
    return m ? m[0].length : 0;
  }

  function cpLen(s) { var n = 0; for (var _c of s) n++; return n; } // eslint-disable-line no-unused-vars

  function tokenize(text) {
    var out = [];
    var re = new RegExp(TOKEN_SRC, "gu");
    var m;
    while ((m = re.exec(text)) !== null) {
      var t = m[0];
      out.push({ text: t, norm: t.toLowerCase().replace(/’/g, "'"), start: m.index, end: m.index + t.length });
    }
    return out;
  }

  function compileEntries(entries, foldOn) {
    return (entries || []).map(function (entry) {
      var parts = entry.toLowerCase().split(/\s+/).filter(Boolean);
      if (foldOn) parts = parts.map(fold);
      return {
        toks: parts.map(function (p) { return p.replace(/\*+$/, ""); }),
        wild: parts.map(function (p) { return p.charAt(p.length - 1) === "*"; })
      };
    });
  }

  function tables(lang, spec) {
    var perSpec = compiledCache.get(spec);
    if (!perSpec) { perSpec = {}; compiledCache.set(spec, perSpec); }
    if (!perSpec[lang]) {
      var block = spec.langs[lang];
      var foldOn = lang === "cs";
      var lex = {};
      LEX_CATEGORIES.forEach(function (cat) { lex[cat] = compileEntries((block.lexicons || {})[cat], foldOn); });
      perSpec[lang] = { lex: lex, starters: compileEntries(block.question_starters, foldOn), fold: foldOn };
    }
    return perSpec[lang];
  }

  /** Left to right, longest entry first, non overlapping. Returns [[start, endExclusive], ...]. */
  function findMatches(norms, compiled) {
    var out = [];
    var n = norms.length;
    var i = 0;
    while (i < n) {
      var best = 0;
      for (var e = 0; e < compiled.length; e++) {
        var toks = compiled[e].toks, wild = compiled[e].wild;
        var size = toks.length;
        if (size <= best || i + size > n) continue;
        var ok = true;
        for (var j = 0; j < size; j++) {
          var t = norms[i + j];
          if (wild[j]) {
            if (t.indexOf(toks[j]) !== 0) { ok = false; break; }
          } else if (t !== toks[j]) { ok = false; break; }
        }
        if (ok) best = size;
      }
      if (best) { out.push([i, i + best]); i += best; } else { i += 1; }
    }
    return out;
  }

  function detectLang(text, spec) {
    spec = spec || defaultSpec;
    if (!spec) throw new Error("scoring spec not loaded");
    var low = normalize(text).toLowerCase();
    for (var k = 0; k < low.length; k++) { if (CS_CHARS.indexOf(low.charAt(k)) >= 0) return "cs"; }
    var csStop = new Set(spec.langs.cs.stopwords.map(fold));
    var enStop = new Set(spec.langs.en.stopwords);
    var toks = tokenize(low).map(function (t) { return t.norm; });
    var cs = 0, en = 0;
    toks.forEach(function (t) { if (csStop.has(fold(t))) cs += 1; if (enStop.has(t)) en += 1; });
    return cs > en ? "cs" : "en";
  }

  function sat(x, k) { return 1.0 - Math.exp(-x / k); }

  function brevity(n) {
    if (n === 0) return 0.0;
    if (n < 3) return 0.4;
    if (n < 6) return 0.4 + 0.6 * (n - 3) / 3;
    if (n <= 12) return 1.0;
    if (n <= 25) return 1.0 - 0.7 * (n - 12) / 13;
    return 0.3;
  }

  function countMatches(re, body) { var m = body.match(re); return m ? m.length : 0; }

  function promiseGap(tokens, startsWithNumber, body) {
    if (!body || !startsWithNumber || !tokens.length) return 0.0;
    if (!INT_RE.test(tokens[0].norm)) return 0.0;
    var promised = parseInt(tokens[0].norm, 10);
    if (promised < 2 || promised > 60) return 0.0;
    var found = Math.max(countMatches(LIST_LINE_RE, body), countMatches(HEADING_RE, body));
    return Math.max(0.0, (promised - found) / promised);
  }

  var TIP_FOR_DRIVER = [
    ["curiosity", "open_loop"], ["utility", "add_utility"], ["relevance", "address_reader"],
    ["emotion", "add_emotion"], ["surprise", "add_contrast"]
  ];

  function buildTips(spec, d01, fluency, risk, gap, n, avgLen, ref, w, wsum, total) {
    var cands = [];
    if (risk > 0.35) cands.push([1.0 + risk, "reduce_clickbait"]);
    if (gap > 0.2) cands.push([0.9 + gap, "keep_promise"]);
    TIP_FOR_DRIVER.forEach(function (pair) {
      var d = pair[0], key = pair[1];
      if (d01[d] < 0.35) cands.push([(has(w, d) ? w[d] : 0.0) / wsum * (0.6 - d01[d]), key]);
    });
    if (fluency < 0.65) {
      if (n > 12) cands.push([(1.0 - fluency) * 0.6, "shorten"]);
      else if (avgLen > ref + 0.8) cands.push([(1.0 - fluency) * 0.6, "simplify"]);
    }
    cands.sort(function (a, b) {
      if (a[0] !== b[0]) return b[0] - a[0];
      return a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0;
    });
    var keys = cands.slice(0, 3).map(function (c) { return c[1]; });
    if (!keys.length && total >= 70 && risk < 0.2) keys = ["ship_it"];
    return keys.map(function (k) { return { key: k, en: spec.messages[k].en, cs: spec.messages[k].cs }; });
  }

  /**
   * Score one hook. opts: {lang, weights, spec}. Returns the same keys as Python HookScore.to_dict().
   */
  function scoreHook(text, body, opts) {
    opts = opts || {};
    var spec = opts.spec || defaultSpec;
    if (!spec) throw new Error("scoring spec not loaded: pass opts.spec or call setDefaultSpec(spec)");
    var p = spec.params;
    text = pyStrip(normalize(text || ""));
    var lang = opts.lang && has(spec.langs, opts.lang) ? opts.lang : detectLang(text, spec);
    var tb = tables(lang, spec);

    var tokens = tokenize(text).slice(0, p.max_tokens);
    var n = tokens.length;
    var norms = tokens.map(function (t) { return tb.fold ? fold(t.norm) : t.norm; });

    var hits = {};
    var spans = [];
    LEX_CATEGORIES.forEach(function (cat) {
      var matches = findMatches(norms, tb.lex[cat]);
      hits[cat] = matches.length;
      matches.forEach(function (ab) {
        var a = ab[0], b = ab[1];
        spans.push({
          category: cat, tok_start: a, tok_end: b,
          start: tokens[a].start, end: tokens[b - 1].end,
          text: text.slice(tokens[a].start, tokens[b - 1].end)
        });
      });
    });

    var isNum = tokens.map(function (t) { return NUM_RE.test(t.norm); });
    // A four digit integer between 1900 and 2100 reads as a year, not as a payoff number.
    // (The Python scorer calls int() on any 4 character numeric token, which fails for "9.99";
    // here a decimal token is simply not year-like.)
    var yearLike = tokens.map(function (t, i) {
      return isNum[i] && YEAR_DIGITS_RE.test(t.norm) && parseInt(t.norm, 10) >= 1900 && parseInt(t.norm, 10) <= 2100;
    });
    var hasNumber = false;
    for (var i = 0; i < n; i++) { if (isNum[i] && !yearLike[i]) { hasNumber = true; break; } }
    var startsWithNumber = !!(n && isNum[0] && !yearLike[0]);

    var isQuestion = text.endsWith("?") || text.endsWith("？") ||
      !!(n && findMatches(norms.slice(0, 1), tb.starters).length);
    var openLoop = text.indexOf(":") >= 0 || text.indexOf("...") >= 0 || text.indexOf("…") >= 0;
    var exclaim = text.split("!").length - 1;
    var caps = 0;
    tokens.forEach(function (t) {
      if (/^\p{L}+$/u.test(t.text) && cpLen(t.text) >= p.caps_min_len &&
          t.text === t.text.toUpperCase() && t.text !== t.text.toLowerCase()) caps += 1;
    });
    var capsRatio = caps / Math.max(n, 1);
    var alphaLengths = [];
    tokens.forEach(function (t) { if (/^\p{L}+$/u.test(t.norm)) alphaLengths.push(cpLen(t.norm)); });
    var avgWordLen = alphaLengths.length ? alphaLengths.reduce(function (a, b) { return a + b; }, 0) / alphaLengths.length : 0.0;
    var gap = promiseGap(tokens, startsWithNumber, body || "");

    var sc = p.scales;
    var B = function (x) { return x ? 1 : 0; };
    var d01 = {
      curiosity: sat(1.0 * Math.min(hits.curiosity, 3) + 0.6 * B(isQuestion) + 0.35 * B(openLoop), sc.curiosity),
      surprise: sat(1.0 * Math.min(hits.contrast, 3) + 0.4 * (hasNumber && hits.negative > 0 ? 1 : 0), sc.surprise),
      emotion: sat(1.0 * Math.min(hits.emotion, 3) + 0.3 * Math.min(exclaim, 2) +
        0.25 * Math.min(hits.positive, 2) + 0.35 * Math.min(hits.negative, 2), sc.emotion),
      relevance: sat(1.0 * Math.min(hits.second_person, 2) + 0.6 * Math.min(hits.social, 2), sc.relevance),
      utility: sat(1.0 * Math.min(hits.practical, 3) + 0.35 * B(hasNumber) + 0.65 * B(startsWithNumber), sc.utility)
    };
    var ref = p.avg_len_ref[lang];
    var ease = avgWordLen > 0 ? Math.min(1.0, Math.max(0.0, 1.0 - (avgWordLen - ref) / 3.0)) : 0.5;
    var fluency = 0.6 * brevity(n) + 0.4 * ease;

    var w = opts.weights && Object.keys(opts.weights).length ? opts.weights : p.weights;
    var wsum = 0.0;
    WEIGHTED_DRIVERS.forEach(function (d) { wsum += has(w, d) ? w[d] : 0.0; });
    wsum = wsum || 1.0;
    var weighted = 0.0;
    WEIGHTED_DRIVERS.forEach(function (d) { weighted += (has(w, d) ? w[d] : 0.0) * d01[d]; });
    var raw5 = weighted / wsum;
    var modulator = p.fluency_floor + (1.0 - p.fluency_floor) * fluency;
    var raw = raw5 * modulator;
    var display = 100.0 * (1.0 - Math.exp(-raw / p.display_tau));

    var riskRaw = 1.0 * Math.min(hits.clickbait, 3) + 0.5 * Math.min(hits.overclaim, 3) +
      0.35 * Math.max(exclaim - 1, 0) + 2.0 * Math.max(capsRatio - p.caps_threshold, 0.0) + 0.6 * gap;
    var risk = sat(riskRaw, sc.risk);
    var total = display * (1.0 - p.risk_penalty * risk);

    var features = {
      n_words: n, has_number: B(hasNumber), starts_with_number: B(startsWithNumber),
      is_question: B(isQuestion), open_loop: B(openLoop), exclaim: exclaim,
      caps_ratio: capsRatio, avg_word_len: avgWordLen, promise_gap: gap,
      curiosity_hits: hits.curiosity, contrast_hits: hits.contrast, emotion_hits: hits.emotion,
      practical_hits: hits.practical, social_hits: hits.social, second_person_hits: hits.second_person,
      clickbait_hits: hits.clickbait, overclaim_hits: hits.overclaim,
      positive_hits: hits.positive, negative_hits: hits.negative
    };
    var parts = {};
    WEIGHTED_DRIVERS.forEach(function (d) { parts[d] = 100.0 * d01[d]; });
    parts.fluency = 100.0 * fluency;

    var tips = buildTips(spec, d01, fluency, risk, gap, n, avgWordLen, ref, w, wsum, total);
    return {
      total: total, raw: raw, parts: parts, clickbait_risk: risk, lang: lang,
      features: features, hits: hits, spans: spans, tips: tips, text: text
    };
  }

  function featureVector(score) { return FEATURE_NAMES.map(function (name) { return score.features[name]; }); }

  /** Score and sort candidates best first (ties keep input order). */
  function rankHooks(candidates, opts) {
    opts = opts || {};
    var scored = candidates.map(function (c, i) { return { text: c, score: scoreHook(c, opts.body || "", opts), i: i }; });
    scored.sort(function (a, b) { return (b.score.total - a.score.total) || (a.i - b.i); });
    return scored.map(function (s) { return [s.text, s.score]; });
  }

  // -- display helpers (not part of the Python contract) ---------------------------------------

  // When several categories cover the same words, the first one in this list wins the highlight.
  var DISPLAY_PRIORITY = [
    "clickbait", "overclaim", "curiosity", "contrast", "emotion", "practical",
    "social", "second_person", "negative", "positive"
  ];

  function primaryCategory(cats) {
    for (var i = 0; i < DISPLAY_PRIORITY.length; i++) if (cats.indexOf(DISPLAY_PRIORITY[i]) >= 0) return DISPLAY_PRIORITY[i];
    return null;
  }

  /**
   * Split text into consecutive pieces so every piece is covered by the same set of spans.
   * Returns [{text, start, end, cats, primary}] covering the whole string (cats is [] for plain text).
   */
  function segments(text, spans) {
    var cuts = [0, text.length];
    (spans || []).forEach(function (s) {
      if (s.start >= 0 && s.end <= text.length && s.end > s.start) { cuts.push(s.start); cuts.push(s.end); }
    });
    cuts = Array.from(new Set(cuts)).sort(function (a, b) { return a - b; });
    var out = [];
    for (var i = 0; i + 1 < cuts.length; i++) {
      var a = cuts[i], b = cuts[i + 1];
      var cats = [];
      (spans || []).forEach(function (s) { if (s.start <= a && s.end >= b && cats.indexOf(s.category) < 0) cats.push(s.category); });
      out.push({ text: text.slice(a, b), start: a, end: b, cats: cats, primary: primaryCategory(cats) });
    }
    return out;
  }

  /** Trust Shield state from the clickbait risk: intact below 0.2, cracked below 0.35, else broken. */
  function shieldState(risk) { return risk < 0.2 ? "intact" : risk < 0.35 ? "cracked" : "broken"; }

  return {
    WEIGHTED_DRIVERS: WEIGHTED_DRIVERS, ALL_PARTS: ALL_PARTS, LEX_CATEGORIES: LEX_CATEGORIES,
    FEATURE_NAMES: FEATURE_NAMES, DISPLAY_PRIORITY: DISPLAY_PRIORITY,
    setDefaultSpec: setDefaultSpec, getDefaultSpec: getDefaultSpec,
    scoreHook: scoreHook, detectLang: detectLang, tokenize: tokenize, findMatches: findMatches,
    fold: fold, normalize: normalize, leadingSpace: leadingSpace, featureVector: featureVector,
    rankHooks: rankHooks, segments: segments, primaryCategory: primaryCategory, shieldState: shieldState
  };
});
