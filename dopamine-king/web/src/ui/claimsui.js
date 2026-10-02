/* Claims presentation shared by the Boss Battle (live panel), the Vault (Claims map and "Check your own text")
 * and the Forge (issue names). The pure parts (engine, check, claimsMap, topicNames, status) need no DOM and are
 * unit tested; the render helpers build plain DOM through DK.ui.dom and always pair colour with an icon and text.
 * Everything runs in the page: the checker is claims.js, the data is bundle.claim_rules and bundle.claims.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.claimsui = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var CLASS_ORDER = ["wellness", "cosmetic", "context", "medical", "avoid"];
  var BLOCKED = { medical: true, avoid: true };
  var CLASS_META = {
    wellness: { icon: "sprout", tone: "ok" },
    cosmetic: { icon: "eye", tone: "info" },
    context: { icon: "book", tone: "muted" },
    medical: { icon: "medical", tone: "risk" },
    avoid: { icon: "ban", tone: "risk" }
  };
  var SEVERITY_META = { error: { icon: "ban", tone: "risk" }, warn: { icon: "alert", tone: "warn" }, info: { icon: "info", tone: "info" } };
  var SEV_RANK = { error: 0, warn: 1, info: 2 };
  var EVIDENCE_LEVEL = { strong: 4, moderate: 3, limited: 2, contested: 2, none: 0 };
  var DIRECTIONS = ["supports", "mixed", "contradicts", "context"];
  var PHRASE_MAX = 90;
  var CHECK_MAX_CHARS = 5000;

  function dom() { return root.DK.ui.dom; }
  function icons() { return root.DK.ui.icons; }

  function claimsLib() {
    if (root.DK && root.DK.claims) return root.DK.claims;
    if (typeof require === "function") { try { return require("../claims.js"); } catch (e) { return null; } }
    return null;
  }

  function uiLang(lang) { return lang === "cs" ? "cs" : "en"; }

  /** obj.name_cs / obj.name_en (field "name"), or obj.cs / obj.en when no field is given; empty values fall back to English. */
  function pickLang(obj, field, lang) {
    if (!obj) return "";
    var l = uiLang(lang);
    var key = function (x) { return field ? field + "_" + x : x; };
    var v = obj[key(l)];
    if (v === undefined || v === null || v === "") v = obj[key("en")];
    return v === undefined || v === null ? "" : v;
  }

  function list(obj, field, lang) {
    var v = obj && obj[field + "_" + uiLang(lang)];
    if (!Array.isArray(v) || !v.length) v = obj && obj[field + "_en"];
    return Array.isArray(v) ? v : [];
  }

  function clip(text, max) {
    var s = String(text).replace(/\s+/g, " ").trim();
    if (s.length <= max) return s;
    var cut = s.slice(0, max - 3);
    var sp = cut.lastIndexOf(" ");
    return (sp > max / 2 ? cut.slice(0, sp) : cut) + "...";
  }

  // -- the checker in the page -----------------------------------------------------------------------------------
  var engines = typeof WeakMap === "function" ? new WeakMap() : null;

  /** The compiled claims checker of a bundle, or null when the edition has no claims profile. Cached per bundle. */
  function engine(bundle) {
    if (!bundle || typeof bundle !== "object" || !bundle.claim_rules) return null;
    if (engines && engines.has(bundle)) return engines.get(bundle);
    var claims = claimsLib();
    if (!claims) return null;
    var topics = {};
    ((bundle.claims && bundle.claims.topics) || []).forEach(function (t) { topics[t.id] = t; });
    var e = { claims: claims, compiled: claims.compile(bundle.claim_rules), bundleTopics: topics, profile: bundle.claim_rules.profile || "wellness" };
    if (engines) engines.set(bundle, e);
    return e;
  }

  /** What a finding shows about its claim topic: name, class, evidence label and the first safer wording. */
  function topicView(e, id, lang) {
    var rt = e.compiled.byId[id];
    if (!rt) return null;
    var bt = e.bundleTopics[id] || null;
    var l = uiLang(lang);
    var safe = (l === "cs" ? rt.safe_cs : rt.safe_en) || [];
    if (!safe.length) safe = rt.safe_en || [];
    return {
      id: id, klass: rt.klass, blocked: !!BLOCKED[rt.klass],
      name: (l === "cs" ? rt.name_cs : rt.name_en) || rt.name_en || (bt && pickLang(bt, "name", l)) || id,
      label: (bt && bt.label) || rt.label || "none",
      safe: safe.length ? safe[0] : ""
    };
  }

  /**
   * Run the checker on a text. The text is normalised to NFC first, so a letter typed with a combining accent counts
   * as one character. Returns {text, hits, findings (errors first, then by position), summary, errors}.
   */
  function check(e, text, lang) {
    var norm = String(text == null ? "" : text).normalize("NFC");
    var hits = e.claims.scan(e.compiled, norm);
    var findings = hits.map(function (h) {
      return {
        code: h.code, severity: e.claims.severity(h.code), start: h.start, end: h.end,
        phrase: h.end > h.start ? clip(norm.slice(h.start, h.end), PHRASE_MAX) : "",
        topic: h.topic ? topicView(e, h.topic, lang) : null
      };
    });
    findings.sort(function (a, b) { return (SEV_RANK[a.severity] - SEV_RANK[b.severity]) || (a.start - b.start); });
    var summary = e.claims.summarize(hits);
    return { text: norm, hits: hits, findings: findings, summary: summary, errors: summary.error };
  }

  /** idle (nothing typed), clean (no findings), blocked (errors) or advice (warnings and notes only). */
  function statusOf(report) {
    if (!report) return { kind: "idle", n: 0 };
    var s = report.summary;
    if (s.total === 0) return { kind: "clean", n: 0 };
    if (s.error > 0) return { kind: "blocked", n: s.error };
    return { kind: "advice", n: s.warn + s.info };
  }

  // -- the Claims map model -----------------------------------------------------------------------------------------
  function topicModel(t, studiesById, lang) {
    var studies = (t.study_ids || []).map(function (id) {
      var s = studiesById[id];
      if (!s) return { id: id, title: id, year: null, verified: false, grade: "", url: null };
      return { id: s.id, title: s.title || s.id, year: s.year || null, verified: s.verified === true, grade: s.grade || "", url: s.url || null };
    });
    studies.sort(function (a, b) {
      return (a.verified === b.verified ? 0 : a.verified ? -1 : 1) || ((b.year || 0) - (a.year || 0)) || String(a.title).localeCompare(String(b.title));
    });
    var label = t.label || "none";
    return {
      id: t.id, klass: t["class"], blocked: !!BLOCKED[t["class"]], domain: t.domain || "",
      name: pickLang(t, "name", lang) || t.id, claim: pickLang(t, "claim", lang), summary: pickLang(t, "summary", lang), headline: pickLang(t, "headline", lang),
      label: label, computedLabel: t.computed_label || label, capped: t.capped === true, capReason: pickLang(t, "cap_reason", lang),
      grade: t.grade || "", nVerified: t.n_studies || 0, nPending: t.n_pending || 0,
      safe: list(t, "safe", lang), avoid: list(t, "avoid", lang), caveats: list(t, "caveats", lang), studies: studies
    };
  }

  /**
   * Claim topics grouped by class in the order wellness, cosmetic, context, medical, avoid (unknown classes follow).
   * `legend` always lists the five classes with their meaning; `groups` only the classes that have topics.
   */
  function claimsMap(bundle, lang) {
    var claims = bundle && bundle.claims;
    if (!claims || !Array.isArray(claims.topics)) return null;
    var studiesById = {};
    ((bundle.vault || {}).studies || []).forEach(function (s) { studiesById[s.id] = s; });
    var classes = claims.classes || {};
    var order = CLASS_ORDER.slice();
    claims.topics.forEach(function (t) { if (order.indexOf(t["class"]) < 0) order.push(t["class"]); });
    var groups = order.map(function (k) { return { klass: k, meaning: pickLang(classes[k], null, lang), blocked: !!BLOCKED[k], topics: [] }; });
    claims.topics.forEach(function (t) {
      groups.filter(function (g) { return g.klass === t["class"]; })[0].topics.push(topicModel(t, studiesById, lang));
    });
    var vertical = bundle.vertical || {};
    return {
      legend: groups.filter(function (g) { return CLASS_ORDER.indexOf(g.klass) >= 0; }),
      groups: groups.filter(function (g) { return g.topics.length > 0; }),
      note: pickLang(vertical, "regulatory_note", lang),
      total: claims.topics.length,
      blockedTotal: claims.topics.filter(function (t) { return BLOCKED[t["class"]]; }).length
    };
  }

  /** id to display name for everything a study link can point to: the evidence tactics and the claim topics. */
  function topicNames(bundle, lang) {
    var out = {};
    ((bundle && bundle.vault && bundle.vault.tactics) || []).forEach(function (x) { out[x.id] = pickLang(x, "name", lang) || x.id; });
    ((bundle && bundle.claims && bundle.claims.topics) || []).forEach(function (x) { out[x.id] = pickLang(x, "name", lang) || x.id; });
    return out;
  }

  /** The links of one study as [{id, name, direction}] with names resolved, one entry per topic. */
  function studyLinks(bundle, studyId, lang) {
    var names = topicNames(bundle, lang);
    var seen = {};
    var out = [];
    (((bundle && bundle.vault) || {}).links || []).forEach(function (l) {
      if (l.study_id !== studyId || seen[l.tactic_id]) return;
      seen[l.tactic_id] = true;
      out.push({ id: l.tactic_id, name: names[l.tactic_id] || l.tactic_id, direction: DIRECTIONS.indexOf(l.direction) >= 0 ? l.direction : "context" });
    });
    return out;
  }

  // -- DOM helpers -------------------------------------------------------------------------------------------------------
  /** Evidence label chip: four segments, an icon for "contested" and the label text. */
  function evidenceChip(label) {
    var d = dom();
    if (EVIDENCE_LEVEL[label] === undefined) label = "none";
    var segs = d.h("span.ev-segs", { "aria-hidden": "true" });
    for (var i = 1; i <= 4; i++) segs.appendChild(d.h("i" + (i <= EVIDENCE_LEVEL[label] ? ".on" : "")));
    return d.h("span.chip.ev-" + label, null, segs, label === "contested" ? icons().icon("alert", { size: 13 }) : null, d.h("span", null, d.t("vault.ev." + label)));
  }

  function severityChip(sev) {
    var d = dom();
    var meta = SEVERITY_META[sev] || SEVERITY_META.info;
    return d.h("span.chip.tone-" + meta.tone + ".sev-chip", null, icons().icon(meta.icon, { size: 14 }), d.h("span", null, d.t("claims.sev." + (SEVERITY_META[sev] ? sev : "info"))));
  }

  function classChip(klass) {
    var d = dom();
    var meta = CLASS_META[klass] || CLASS_META.context;
    return d.h("span.chip.tone-" + meta.tone + ".class-chip.class-" + klass, null, icons().icon(meta.icon, { size: 13 }),
      d.h("span", null, CLASS_META[klass] ? d.t("claims.class." + klass) : String(klass)));
  }

  function blockedBadge() {
    var d = dom();
    return d.h("span.chip.tone-risk.blocked-badge", null, icons().icon("ban", { size: 14, stroke: 2.4 }), d.h("span", null, d.t("claims.blockedBadge")));
  }

  /** One finding: severity chip with icon and text, the message, the phrase found, the topic with its label and a safer wording. */
  function findingItem(f) {
    var d = dom();
    var t = d.t;
    return d.h("li.finding.sev-" + f.severity, { "data-code": f.code },
      d.h("div.finding-head", null, severityChip(f.severity), d.h("code.finding-code", null, f.code)),
      d.h("p.finding-msg", null, d.typo(t("claims.code." + f.code))),
      f.phrase ? d.h("p.finding-phrase", null, d.h("span.finding-label", null, t("claims.phrase")), " ", d.h("q", null, f.phrase)) : null,
      f.topic ? d.h("div.finding-topic", null,
        d.h("span.finding-label", null, t("claims.topic")), " ", d.h("strong", null, f.topic.name), " ", classChip(f.topic.klass), " ", evidenceChip(f.topic.label)) : null,
      f.topic ? d.h("p.finding-safer", null, d.h("span.finding-label", null, t("claims.safer")), " ", f.topic.safe ? d.quote(f.topic.safe) : t("claims.saferNone")) : null);
  }

  function findingList(findings) {
    var d = dom();
    return d.h("ul.finding-list", { "aria-label": d.t("claims.findings") }, findings.map(findingItem));
  }

  /** The sentence for a status: "No claim problems", "2 blocking problems", "No blocking problem, 1 note to review". */
  function statusText(st) {
    var d = dom();
    if (st.kind === "clean") return d.t("claims.ok");
    if (st.kind === "blocked") return root.DK.i18n.tp("claims.blocked", st.n);
    if (st.kind === "advice") return root.DK.i18n.tp("claims.advice", st.n);
    return d.t("claims.empty");
  }

  /** Fill a status element (persistent live region) for a report; the text only changes when the summary changes. */
  function fillStatus(el, report) {
    var d = dom();
    var st = statusOf(report);
    var key = st.kind + ":" + st.n;
    if (el.getAttribute("data-key") === key) return st;
    el.setAttribute("data-key", key);
    el.className = "claims-status is-" + st.kind;
    var icon = st.kind === "clean" ? "shieldCheck" : st.kind === "blocked" ? "ban" : st.kind === "advice" ? "alert" : "info";
    d.fill(el, [icons().icon(icon, { size: 22, stroke: 2.4 }), d.h("strong", null, statusText(st))]);
    return st;
  }

  return {
    CLASS_ORDER: CLASS_ORDER, CLASS_META: CLASS_META, SEVERITY_META: SEVERITY_META, EVIDENCE_LEVEL: EVIDENCE_LEVEL, DIRECTIONS: DIRECTIONS,
    CHECK_MAX_CHARS: CHECK_MAX_CHARS, BLOCKED: BLOCKED,
    engine: engine, check: check, statusOf: statusOf, claimsMap: claimsMap, topicNames: topicNames, studyLinks: studyLinks, pickLang: pickLang,
    evidenceChip: evidenceChip, severityChip: severityChip, classChip: classChip, blockedBadge: blockedBadge,
    findingItem: findingItem, findingList: findingList, fillStatus: fillStatus, statusText: statusText
  };
});
