/* Claims checker: JavaScript port of ClaimsProfile.scan_text (src/dopamine_king/generate/claims.py).
 *
 * A non-medical wellness device (photobiomodulation panels) may describe routines, regeneration and how the
 * technology works with hedged wording, but never diagnosis, treatment, prevention or relief of a disease or
 * symptom. The Python side ships the term lists and claim topics as data (bundle.claim_rules); this module
 * compiles them with the same compiler and finds the same hits. It is a HEURISTIC reviewer, not legal advice.
 *
 * Exactness: web/tests/claims.test.js replays the golden cases written by scripts/gen_golden_claims.py and
 * requires identical (code, topic, start, end). Keep this file in step with the Python reference:
 *   claims.py  term_regex, terms_regex, proximity, ClaimsProfile.__init__, negated, masked, hedged, scan, scan_text
 *   guard.py   fold_aligned, _sentence_spans, _is_question_at
 *
 * Known, accepted differences from Python (the text is folded first, so Czech and English are not affected):
 *   - JavaScript regex classes \w, \d and \b are ASCII only without the u flag. Letters that do not decompose
 *     under NFD (for example the Polish l with stroke) and non Latin scripts behave as separators here.
 *   - Offsets count UTF-16 code units; Python counts code points (the same for text without emoji).
 * The rule patterns are Python regexes written to be valid JavaScript too, so no regex flags are used.
 * Special characters are built with String.fromCharCode so the source stays plain ASCII.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else { root.DK = root.DK || {}; root.DK.claims = factory(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  function chars() { return String.fromCharCode.apply(null, arguments); }

  var WINDOW = 5;                                   // words allowed between a verb and an outcome word
  var SEP = "[^\\w.!?;\\n]+";                       // separator that never crosses a sentence boundary
  var NEVER = "(?!x)x";                             // matches nothing
  var CLASS_RANK = { context: 0, wellness: 1, cosmetic: 2, medical: 3, avoid: 4 };

  var SPACE_LIKE = chars(0xa0, 0x2009, 0x202f);     // no-break, thin and narrow no-break space
  var APOSTROPHE = chars(0x2019);
  var ELLIPSIS = chars(0x2026);
  // Python's \s and str.strip() whitespace (str.isspace); JavaScript's \s differs in a few control characters.
  var PY_WS = "\\t\\n\\x0b\\x0c\\r\\x1c-\\x1f \\x85" + chars(0xa0, 0x1680, 0x2000) + "-" + chars(0x200a, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000);
  var NON_WS_RE = new RegExp("[^" + PY_WS + "]");
  var SENT_BOUNDARY_SRC = "(?<=[.!?" + ELLIPSIS + "])[\"')\\]]*[" + PY_WS + "]+|\\n+";

  // severity per code, as in claims.RULES
  var SEVERITY = {
    CLAIM_MEDICAL: "error", CLAIM_AVOID: "error", DISEASE_MENTION: "error", STATUS_CLAIM: "error",
    SAFETY_ABSOLUTE: "error", MEDICATION_ADVICE: "error",
    CLAIM_UNHEDGED: "warn", OUTCOME_PROMISE: "warn", DOSE_NOT_FROM_MANUAL: "warn", SAFETY_NOTE_MISSING: "warn",
    THERAPY_WORD: "info"
  };
  var CODES = Object.keys(SEVERITY);
  var SEVERITIES = ["error", "warn", "info"];

  function severity(code) { return Object.prototype.hasOwnProperty.call(SEVERITY, code) ? SEVERITY[code] : "info"; }
  function isError(code) { return severity(code) === "error"; }

  /** Counts per severity: {error, warn, info, total}. */
  function summarize(hits) {
    var out = { error: 0, warn: 0, info: 0, total: 0 };
    (hits || []).forEach(function (h) { out[severity(h.code)] += 1; out.total += 1; });
    return out;
  }

  // -- text plumbing (guard.py) ----------------------------------------------------------------------------
  /** Strip diacritics (scoring.fold): NFD without combining marks. */
  function fold(text) { return String(text).normalize("NFD").replace(/\p{Mn}/gu, ""); }

  var ALPHA_RE = /^\p{L}$/u;

  function codePointCount(s) { var n = 0; for (var _c of s) n++; return n; } // eslint-disable-line no-unused-vars

  /**
   * Lower case, diacritics free copy of the text with exactly the same length, so indexes map 1:1.
   * Space like characters become a space, the typographic apostrophe a plain one, letters are lower cased and
   * folded; a character whose folded form is not a single character is kept as it is.
   */
  function foldAligned(text) {
    var s = String(text == null ? "" : text);
    var out = [];
    for (var c of s) {
      var cp = c.codePointAt(0);
      if (cp < 128) { out.push(cp >= 65 && cp <= 90 ? String.fromCharCode(cp + 32) : c); continue; }
      if (SPACE_LIKE.indexOf(c) >= 0) { out.push(" "); continue; }
      if (c === APOSTROPHE) { out.push("'"); continue; }
      var f = c;
      if (ALPHA_RE.test(c)) f = fold(c.toLowerCase());
      out.push(codePointCount(f) === 1 && f.length === c.length ? f : c);
    }
    return out.join("");
  }

  /** [start, end) of every sentence of the original text (line breaks and sentence ends split). */
  function sentenceSpans(text) {
    var s = String(text == null ? "" : text);
    var spans = [];
    var start = 0;
    var re = new RegExp(SENT_BOUNDARY_SRC, "g");
    var m;
    while ((m = re.exec(s)) !== null) {
      if (NON_WS_RE.test(s.slice(start, m.index))) spans.push([start, m.index]);
      start = m.index + m[0].length;
      if (m[0].length === 0) re.lastIndex += 1;
    }
    if (NON_WS_RE.test(s.slice(start))) spans.push([start, s.length]);
    return spans;
  }

  /** True when the first sentence terminator after `end` on the same line is a question mark. */
  function isQuestionAt(text, end) {
    var rest = text.slice(end);
    var nl = rest.indexOf("\n");
    if (nl >= 0) rest = rest.slice(0, nl);
    var m = /[.!?]/.exec(rest);
    return !!m && m[0] === "?";
  }

  function sentenceOf(spans, pos) {
    for (var i = 0; i < spans.length; i++) {
      var a = spans[i][0], b = spans[i][1];
      if ((a <= pos && pos < b) || pos < a) return spans[i];
    }
    return spans.length ? spans[spans.length - 1] : [0, 0];
  }

  // -- term compiler (claims.py) ---------------------------------------------------------------------------------
  /** re.escape of Python 3.7 and later: only the regex special characters (no whitespace here, words are split). */
  function escapeWord(word) { return word.replace(/[()[\]{}?*+\-|^$\\.&~#]/g, "\\$&"); }

  var SPLIT_WS_RE = new RegExp("[" + PY_WS + "]+");

  function pyStrip(text) { return text.replace(new RegExp("^[" + PY_WS + "]+"), "").replace(new RegExp("[" + PY_WS + "]+$"), ""); }

  /** Regex source for one plain term: folded, words joined by space or hyphen, a trailing * on a word is a stem wildcard. */
  function termRegex(term) {
    var words = [];
    fold(pyStrip(String(term)).toLowerCase()).split(SPLIT_WS_RE).forEach(function (word) {
      if (!word) return;
      var star = word.charAt(word.length - 1) === "*";
      word = word.replace(/\*+$/, "");
      if (word) words.push(escapeWord(word) + (star ? "\\w*" : ""));
    });
    return words.join("[\\s-]+");
  }

  /** One alternation for many terms, longest first, with word boundaries. */
  function termsRegex(terms) {
    var seen = new Set();
    (terms || []).forEach(function (t) {
      if (!t) return;
      var r = termRegex(t);
      if (r) seen.add(r);
    });
    var parts = Array.from(seen).sort(function (a, b) { return b.length - a.length; });
    return parts.length ? "\\b(?:" + parts.join("|") + ")\\b" : NEVER;
  }

  function both(table) {
    table = table || {};
    return (table.en || []).concat(table.cs || []);
  }

  /** `first` and `second` within `window` words in either order, never across a sentence end. */
  function proximity(first, second, window) {
    var w = window === undefined ? WINDOW : window;
    var gap = "(?:" + SEP + "\\w+){0," + w + "}" + SEP;
    return "(?:" + first + gap + second + "|" + second + gap + first + ")";
  }

  function escapedFolded(words) { return both(words).map(function (w) { return escapeWord(fold(String(w).toLowerCase())); }); }

  // -- compile -------------------------------------------------------------------------------------------------------------
  var cache = typeof WeakMap === "function" ? new WeakMap() : null;

  /**
   * Compile the rules (bundle.claim_rules) once. Patterns that are not valid JavaScript are skipped and listed in
   * `errors`, so one bad pattern never takes the checker down; the tests require `errors` to be empty.
   */
  function compile(rules) {
    rules = rules || {};
    if (cache && typeof rules === "object" && cache.has(rules)) return cache.get(rules);
    var errors = [];
    function rx(src, what) {
      try { return new RegExp(src, "g"); } catch (e) { errors.push({ what: what, pattern: src, message: String(e && e.message || e) }); return new RegExp(NEVER, "g"); }
    }
    function rxList(list, what) { return (list || []).map(function (p) { return rx(p, what); }); }

    var verbRe = termsRegex(both(rules.treatment_verbs).concat(both(rules.benefit_verbs)));
    var diseaseRe = termsRegex(both(rules.disease_terms));
    var deviceRe = termsRegex(both(rules.device_words));
    var prepRe = termsRegex(both(rules.indication_prepositions));
    var negation = escapedFolded(rules.negation_words);
    var breakers = escapedFolded(rules.clause_breakers);
    var stems = rules.negated_verb_stems || [];
    var targetingRe = termsRegex(both(rules.targeting_phrases));
    var indication = "(?:" + deviceRe + SEP + "(?:" + prepRe + SEP + ")(?:\\w+" + SEP + "){0,3}?)";

    var c = {
      profile: rules.profile || "wellness",
      statusRe: rx(termsRegex(both(rules.regulated_status)), "regulated_status"),
      safetyAbsRe: rx(termsRegex(both(rules.safety_absolute)), "safety_absolute"),
      therapyRe: rx(termsRegex(both(rules.therapy_words)), "therapy_words"),
      approvedRe: rx(termsRegex(both(rules.approved_terms)), "approved_terms"),
      hedgeRe: rx(termsRegex(both(rules.hedge_words)), "hedge_words"),
      safetyTermsRe: rx(termsRegex(both(rules.safety_terms)), "safety_terms"),
      negRe: rx(negation.length ? "\\b(?:" + negation.join("|") + ")\\b" : NEVER, "negation_words"),
      clauseBreakRe: rx(breakers.length ? ",\\s*(?:" + breakers.join("|") + ")\\b" : NEVER, "clause_breakers"),
      maskRe: rx(termsRegex(both(rules.masking_phrases)), "masking_phrases"),
      negVerbRe: rx(stems.length ? "\\bne(?:" + stems.join("|") + ")\\w*\\b" : NEVER, "negated_verb_stems"),
      medication: rxList(both({ en: (rules.medication_patterns || {}).en, cs: (rules.medication_patterns || {}).cs }), "medication_patterns"),
      timeline: rxList(both(rules.timeline_patterns), "timeline_patterns"),
      dose: rxList(both(rules.dose_patterns), "dose_patterns"),
      doseCtxRe: rx(termsRegex(both(rules.dose_context)), "dose_context"),
      longForm: (rules.long_form_formats || []).slice(),
      topics: [],
      byId: {},
      errors: errors
    };
    (rules.topics || []).forEach(function (t) {
      var nouns = (t.nouns_en || []).concat(t.nouns_cs || []);
      var topic = {
        id: t.id, klass: t["class"], name_en: t.name_en, name_cs: t.name_cs, nouns: nouns,
        safe_en: (t.safe_en || []).slice(), safe_cs: (t.safe_cs || []).slice(), label: t.label_cap || "none",
        regex: null, patterns: []
      };
      if (nouns.length) {
        var nounRe = termsRegex(nouns);
        topic.regex = rx(proximity(verbRe, nounRe), "topic " + t.id);
        if (topic.klass === "medical" || topic.klass === "avoid") topic.patterns.push(rx(indication + nounRe, "topic " + t.id));
      }
      (t.patterns || []).forEach(function (p) { topic.patterns.push(rx(p, "topic " + t.id + " pattern")); });
      c.topics.push(topic);
      c.byId[topic.id] = topic;
    });
    // words that claim a cure or treatment by themselves (see claims.py): they lift a wellness or appearance topic to a
    // medical claim and form a topic of their own
    var strong = rules.strong_claims || {};
    var strongTerms = both(strong.terms);
    c.strongRe = strongTerms.length ? rx(termsRegex(strongTerms), "strong_claims") : null;
    var strongPatterns = both(strong.patterns);
    if (c.strongRe || strongPatterns.length) {
      var sname = strong.name || {}, ssafe = strong.safe || {};
      var generic = {
        id: strong.id || "generic-cure", klass: "medical",
        name_en: sname.en || "Cure or treatment claim", name_cs: sname.cs || sname.en || "Cure or treatment claim",
        nouns: [], safe_en: (ssafe.en || []).slice(), safe_cs: (ssafe.cs || []).slice(), label: "none", regex: null,
        patterns: (c.strongRe ? [c.strongRe] : []).concat(strongPatterns.map(function (p) { return rx(p, "strong_claims pattern"); }))
      };
      c.topics.push(generic);
      c.byId[generic.id] = generic;
    }
    c.diseaseRe = rx(proximity(verbRe, diseaseRe), "disease_terms");
    // an ad that addresses people with a problem is a claim: next to a disease or next to the nouns of every topic but the context ones
    var symptomNouns = [];
    (rules.topics || []).forEach(function (t) { if (t["class"] !== "context") symptomNouns = symptomNouns.concat(t.nouns_en || [], t.nouns_cs || []); });
    c.targetingRe = rx(proximity(targetingRe, "(?:" + diseaseRe + "|" + termsRegex(symptomNouns) + ")", 8), "targeting_phrases");
    c.indicationRe = rx(indication + diseaseRe, "disease_terms");
    if (cache && typeof rules === "object") cache.set(rules, c);
    return c;
  }

  // -- regex helpers: every compiled regex is global, so lastIndex is reset before each use --------------------
  function all(re, s) {
    var out = [];
    re.lastIndex = 0;
    var m;
    while ((m = re.exec(s)) !== null) {
      out.push({ start: m.index, end: m.index + m[0].length, text: m[0] });
      if (m[0].length === 0) re.lastIndex += 1;
    }
    re.lastIndex = 0;
    return out;
  }

  function first(re, s) {
    re.lastIndex = 0;
    var m = re.exec(s);
    re.lastIndex = 0;
    return m ? { start: m.index, end: m.index + m[0].length, text: m[0] } : null;
  }

  // -- scanning ---------------------------------------------------------------------------------------------------------------
  /** The hit sits in a negated clause ("does not treat", "neslouzi k lecbe", "bez rizika"); the nearest negation word counts. */
  function negated(c, low, start, end, spans) {
    var a = sentenceOf(spans, start)[0];
    var before = low.slice(Math.max(a, start - 60), start);
    var last = null;
    all(c.negRe, before).forEach(function (m) { last = m; });
    if (last !== null) {
      var gap = before.slice(last.end);
      if (gap.length <= 40 && !first(c.clauseBreakRe, gap)) return true;
    }
    return !!first(c.negVerbRe, low.slice(Math.max(a, start - 40), end));
  }

  function hedged(c, low, start, spans) {
    var s = sentenceOf(spans, start);
    return !!first(c.hedgeRe, low.slice(s[0], s[1]));
  }

  /**
   * Hits for plain text with no facts, citations or placeholders in play (hooks, headlines): the same as
   * ClaimsProfile.scan_text. Returns [{code, topic (id or null), start, end}] sorted by (start, end, code).
   * options.formatId adds SAFETY_NOTE_MISSING for long form formats without a safety term.
   */
  function scan(c, text, options) {
    var src = String(text == null ? "" : text);
    var formatId = options && options.formatId !== undefined ? options.formatId : null;
    var low = foldAligned(src);
    var spans = sentenceSpans(src);
    var hits = [];
    var masks = all(c.maskRe, low);

    function usable(a, b) {
      for (var i = 0; i < masks.length; i++) if (masks[i].start < b && a < masks[i].end) return false;
      return !negated(c, low, a, b, spans);
    }
    function isQuestion(end) { return isQuestionAt(low, end); }

    var candidates = [];
    c.topics.forEach(function (topic) {
      var list = (topic.regex ? [topic.regex] : []).concat(topic.patterns);
      list.forEach(function (re) {
        all(re, low).forEach(function (m) {
          if (!usable(m.start, m.end) || isQuestion(m.end)) return;
          var code;
          if (topic.klass === "medical") code = "CLAIM_MEDICAL";
          else if (topic.klass === "avoid") code = "CLAIM_AVOID";
          else if (c.strongRe && first(c.strongRe, m.text)) code = "CLAIM_MEDICAL";
          else if (hedged(c, low, m.start, spans)) return;
          else code = "CLAIM_UNHEDGED";
          candidates.push({ code: code, start: m.start, end: m.end, topic: topic });
        });
      });
    });
    // the strictest class wins where hits of several topics overlap (stable sort, like Python's)
    candidates.sort(function (x, y) { return (CLASS_RANK[y.topic.klass] - CLASS_RANK[x.topic.klass]) || (x.start - y.start); });
    candidates.forEach(function (h) {
      var clash = hits.some(function (k) { return k.start < h.end && h.start < k.end; });
      if (!clash) hits.push(h);
    });
    hits.sort(function (x, y) { return x.start - y.start; });
    var taken = hits.map(function (h) { return [h.start, h.end]; });
    function free(a, b) { return !taken.some(function (t) { return t[0] < b && a < t[1]; }); }

    [c.diseaseRe, c.indicationRe, c.targetingRe].forEach(function (re) {
      all(re, low).forEach(function (m) {
        // an ad that addresses people with a condition is a claim even as a question
        if (usable(m.start, m.end) && free(m.start, m.end) && (re === c.targetingRe || !isQuestion(m.end))) {
          hits.push({ code: "DISEASE_MENTION", start: m.start, end: m.end, topic: null });
          taken.push([m.start, m.end]);
        }
      });
    });
    c.medication.forEach(function (re) {
      all(re, low).forEach(function (m) {
        if (usable(m.start, m.end)) hits.push({ code: "MEDICATION_ADVICE", start: m.start, end: m.end, topic: null });
      });
    });
    all(c.statusRe, low).forEach(function (m) {
      if (usable(m.start, m.end)) hits.push({ code: "STATUS_CLAIM", start: m.start, end: m.end, topic: null });
    });
    all(c.safetyAbsRe, low).forEach(function (m) {
      if (usable(m.start, m.end)) hits.push({ code: "SAFETY_ABSOLUTE", start: m.start, end: m.end, topic: null });
    });
    c.timeline.forEach(function (re) {
      all(re, low).forEach(function (m) {
        if (usable(m.start, m.end) && !isQuestion(m.end)) hits.push({ code: "OUTCOME_PROMISE", start: m.start, end: m.end, topic: null });
      });
    });
    var seenDose = {};
    c.dose.forEach(function (re) {
      all(re, low).forEach(function (m) {
        var s = sentenceOf(spans, m.start);
        if (Object.prototype.hasOwnProperty.call(seenDose, m.text) || !first(c.doseCtxRe, low.slice(s[0], s[1]))) return;
        seenDose[m.text] = true;
        hits.push({ code: "DOSE_NOT_FROM_MANUAL", start: m.start, end: m.end, topic: null });
      });
    });
    var approved = all(c.approvedRe, low);
    var therapy = all(c.therapyRe, low);
    for (var ti = 0; ti < therapy.length; ti++) {
      var th = therapy[ti];
      if (negated(c, low, th.start, th.end, spans)) continue;
      if (approved.some(function (ap) { return ap.start <= th.start && th.end <= ap.end; })) continue;
      hits.push({ code: "THERAPY_WORD", start: th.start, end: th.end, topic: null });   // the first use that is not the approved name or a negation
      break;
    }
    if (formatId !== null && c.longForm.indexOf(formatId) >= 0 && !first(c.safetyTermsRe, low)) {
      hits.push({ code: "SAFETY_NOTE_MISSING", start: 0, end: 0, topic: null });
    }

    return hits.map(function (h) { return { code: h.code, topic: h.topic ? h.topic.id : null, start: h.start, end: h.end }; })
      .sort(function (x, y) {
        return (x.start - y.start) || (x.end - y.end) || (x.code < y.code ? -1 : x.code > y.code ? 1 : 0);
      });
  }

  /** The compiled topic of an id (name, class, safer wording, label cap) or null. */
  function topicOf(c, id) { return (c && id && c.byId[id]) || null; }

  return {
    compile: compile, scan: scan, scanText: scan, topicOf: topicOf,
    severity: severity, isError: isError, summarize: summarize,
    SEVERITY: SEVERITY, CODES: CODES, SEVERITIES: SEVERITIES, CLASS_RANK: CLASS_RANK,
    foldAligned: foldAligned, sentenceSpans: sentenceSpans, isQuestionAt: isQuestionAt, fold: fold,
    termRegex: termRegex, termsRegex: termsRegex, proximity: proximity
  };
});
