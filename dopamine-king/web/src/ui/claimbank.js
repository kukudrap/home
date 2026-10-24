/* Claims: the bank of emotional, experience based claims for the brand (bundle.claimbank, from radar/claims_emotional.json).
 *
 * Every sentence passed the claims check without an error or a warning, rests only on facts of the brand file and names no effect on
 * the body, the mood or hormones. They stand on seven levers (anticipation, ritual, surprise, story, feeling, belonging, choice) whose
 * strength is the evidence label of the tactic in the study ledger. The strength belongs to the lever, not to a sentence: a sentence is
 * a hypothesis until a test says otherwise (see the real test in the Lab).
 *
 *  Start        the sentences to begin with, and why the word "dopamine" is not used
 *  Levers       the seven levers with their evidence and sentences
 *  Audiences    sentences for each audience, slogans, and texts for the app, e-mails and the packaging
 *  Story        the story of the brand in three lengths, and names for the ritual and the features
 *  Rules        what not to say and what to say instead, and the rules of the game
 *  Confirm      what the brand has to confirm before the sentences hold
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.claims = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var TABS = ["start", "levers", "groups", "story", "rules", "confirm"];
  var RISK = { high: ["warn", "bank.risk.high"], medium: ["muted", "bank.risk.medium"], low: ["ok", "bank.risk.low"] };
  var CODE_KEY = { CLAIM_MEDICAL: "medical", CLAIM_AVOID: "avoid", STATUS_CLAIM: "status", SAFETY_ABSOLUTE: "safety", OUTCOME_PROMISE: "promise", DISEASE_MENTION: "disease", MEDICATION_ADVICE: "medication" };
  var DIRECTION_KEY = { supports: "supports", mixed: "mixed", contradicts: "contradicts", context: "context" };

  var state = { tab: "start" };

  function mount(container, ctx, route) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets, ui = root.DK.ui.claimsui;
    var t = d.t;
    var bank = ctx.bundle.claimbank;
    var page = d.h("div.page.claim-bank");
    container.appendChild(page);
    if (!bank) {
      d.fill(page, [d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("bank.title")), widgets.emptyState({ icon: "shieldCheck", title: t("bank.empty.title"), text: t("bank.empty.text") })]);
      return { destroy: function () {} };
    }
    var sub = (route && route.sub) || (route && route.params && route.params.tab) || null;
    if (TABS.indexOf(sub) >= 0) state.tab = sub;
    var uses = bank.uses, names = bank.lever_names;
    var current = null;

    function useName(key) { return String(uses[key] || key).split(":")[0]; }
    function codeLabel(code) { return CODE_KEY[code] ? t("bank.found." + CODE_KEY[code]) : code; }
    function czechNote() { return ctx.lang() === "cs" ? null : d.h("p.small.muted", null, icons.icon("globe", { size: 15 }), " ", t("bank.czechOnly")); }

    function verdictChip(c) {
      var v = c.verdict;
      if (v.errors.length) return d.h("span.chip.tone-risk", null, v.errors.map(codeLabel).join(", "));
      if (v.warnings.length) return d.h("span.chip.tone-warn", null, v.warnings.map(codeLabel).join(", "));
      return null;
    }

    function copyId(prefix, c) { return prefix + c.id; }

    function needsNote(c) {
      return c.needs ? d.h("p.approve", null, d.h("strong", null, t("bank.confirm.label") + " "), c.needs) : null;
    }

    function factsNote(c) {
      return c.facts && c.facts.length ? d.h("p.small.muted", null, d.h("strong", null, t("bank.restsOn") + " "), c.facts.join(" ")) : null;
    }

    /** One sentence with its tags, the verdict of the claims check (only when there is something to report) and a copy button. */
    function claimRow(c, showLever) {
      var text = d.h("p.ctext", { id: copyId("ct-", c) }, c.text);
      return d.h("li.claim", { id: "c-" + c.id },
        text,
        d.h("div.cmeta", null,
          d.h("span.tag", null, useName(c.use)),
          showLever ? d.h("span.tag", null, names[c.lever]) : null,
          c.where_cs ? d.h("span.tag", null, c.where_cs) : null,
          c.concept ? d.h("span.chip", null, t("bank.concept")) : null,
          verdictChip(c),
          widgets.copyButton(c.text, t("common.copy"))),
        needsNote(c), factsNote(c));
    }

    function pickCard(c) {
      return d.h("li.pick", { id: "p-" + c.id },
        d.h("span.kind", null, useName(c.use) + " · " + names[c.lever]),
        d.h("p.big-claim", null, c.text),
        d.h("p.pwhy", null, c.why_cs),
        needsNote(c), factsNote(c),
        d.h("div.cmeta", null, verdictChip(c), widgets.copyButton(c.text, t("common.copy"))));
    }

    function studyItem(s) {
      var title = s.url ? d.extLink(s.url, d.clip(s.title, 110)) : d.h("span", null, d.clip(s.title, 110));
      return d.h("li", null, title, " ", d.h("span.small.muted.host", null, s.year + ", " + t("bank.dir." + (DIRECTION_KEY[s.direction] || "context"))), d.h("br"), d.h("span.small.muted", null, s.note));
    }

    function evidenceBlock(list) {
      return list.map(function (e) {
        return d.h("div.evi", null,
          d.h("p", null, d.h("strong", null, e.name), " ", ui.evidenceChip(e.label), " ", d.h("span.chip", null, ctx.tp("vault.claims.verified", e.n_verified))),
          d.h("p.small.muted", null, e.headline),
          e.studies.length ? d.h("ul.plain", null, e.studies.map(studyItem)) : null,
          e.ethics ? d.h("p.small.muted", null, d.h("strong", null, t("bank.watch") + " "), e.ethics) : null);
      });
    }

    function dopamineBlock() {
      var dp = bank.dopamine;
      return d.h("section.card.callout-card", { "aria-labelledby": "dopa-h" },
        d.h("h2.card-title", { id: "dopa-h" }, t("bank.dopa.title")),
        d.h("p", null, t("bank.dopa.p1")),
        d.h("p", null, dp.summary + " " + t("bank.dopa.p2")),
        d.h("p.small.muted", null, d.h("strong", null, t("bank.watch") + " "), dp.ethics),
        d.h("details", null,
          d.h("summary", null, t("bank.dopa.studies", { n: dp.n_verified })),
          d.h("ul.plain", null, dp.studies.map(studyItem))));
    }

    // ===== start ========================================================================================
    function buildStart(panel) {
      var tt = bank.totals;
      var verdict = !(tt.errors || tt.warnings) ? t("bank.verdictClean") : t("bank.verdictFound", { e: tt.errors, w: tt.warnings });
      d.fill(panel, [
        d.h("section.card", null,
          d.h("h2.card-title", null, t("bank.start.title")),
          d.h("p", null, t("bank.start.lead", { n: tt.claims, k: bank.levers.length })),
          d.h("p.small.muted", null, verdict + " " + t("bank.start.limits")),
          d.h("p.small.muted", null, t("bank.start.concept"))),
        czechNote(),
        dopamineBlock(),
        d.h("section", null,
          widgets.heading(2, t("bank.picks.title"), t("bank.picks.sub")),
          d.h("ul.picks", null, bank.picks.map(pickCard))),
        d.h("p", null, d.h("a.btn.btn-ghost", { href: "#/lab/real" }, icons.icon("flask", { size: 16 }), d.h("span", null, t("bank.toLab"))))
      ]);
      return { destroy: function () {} };
    }

    // ===== levers =======================================================================================
    function buildLevers(panel) {
      var list = bank.levers.map(function (lv) {
        return d.h("details.topic.lever", { id: "lever-" + lv.id },
          d.h("summary", null,
            d.h("span.tname", null, lv.name_cs),
            ui.evidenceChip(lv.label),
            d.h("span.chip", null, ctx.tp("vault.claims.verified", lv.n_verified)),
            d.h("span.muted", null, ctx.tp("bank.nSentences", lv.claims.length))),
          d.h("div.tbody", null,
            d.h("p", null, lv.what_cs),
            d.h("p.small.muted", null, d.h("strong", null, t("bank.watch") + " "), lv.watch_cs),
            d.h("details", null, d.h("summary", null, t("bank.evidence")), evidenceBlock(lv.evidence)),
            d.h("ul.claims", null, lv.claims.map(function (c) { return claimRow(c, false); }))));
      });
      d.fill(panel, [
        d.h("section.card", null, d.h("h2.card-title", null, t("bank.levers.title")), d.h("p", null, t("bank.levers.lead")), d.h("p.small.muted", null, t("bank.levers.strength"))),
        czechNote(), list
      ]);
      return { destroy: function () {} };
    }

    // ===== groups =======================================================================================
    function buildGroups(panel) {
      var personas = bank.personas.map(function (p) {
        var tone = (RISK[p.risk] || RISK.medium);
        return d.h("details.topic", null,
          d.h("summary", null, d.h("span.tname", null, p.name), d.h("span.chip.tone-" + tone[0], null, t(tone[1]))),
          d.h("div.tbody", null, d.h("ul.claims", null, p.claims.map(function (c) { return claimRow(c, true); }))));
      });
      d.fill(panel, [
        czechNote(),
        d.h("section", null, widgets.heading(2, t("bank.groups.title"), t("bank.groups.sub")), personas),
        d.h("section", null, widgets.heading(2, t("bank.slogans.title") + " (" + bank.taglines.length + ")"), d.h("ul.claims", null, bank.taglines.map(function (c) { return claimRow(c, true); }))),
        d.h("section", null, widgets.heading(2, t("bank.micro.title"), t("bank.micro.sub")),
          d.h("details", null, d.h("summary", null, t("bank.micro.open", { n: bank.microcopy.length })), d.h("ul.claims", null, bank.microcopy.map(function (c) { return claimRow(c, true); }))))
      ]);
      return { destroy: function () {} };
    }

    // ===== story ========================================================================================
    function buildStory(panel) {
      var versions = bank.story.map(function (s) {
        return d.h("details.card", null,
          d.h("summary", null, s.name_cs),
          d.h("pre.text", null, s.text),
          widgets.copyButton(s.text, t("common.copy")),
          d.h("p.small.muted", null, d.h("strong", null, t("bank.restsOn") + " "), s.facts.join(" ")));
      });
      var naming = bank.naming.map(function (n) {
        return d.h("li", null, d.h("strong", null, n.name), ": ", n.meaning_cs, n.needs ? d.h("p.approve", null, d.h("strong", null, t("bank.confirm.label") + " "), n.needs) : null);
      });
      d.fill(panel, [
        czechNote(),
        d.h("section", null, widgets.heading(2, t("bank.story.title"), t("bank.story.sub")), versions),
        d.h("section.card", null, d.h("h2.card-title", null, t("bank.naming.title")), d.h("ul.plain", null, naming))
      ]);
      return { destroy: function () {} };
    }

    // ===== rules ========================================================================================
    function buildRules(panel) {
      var rows = bank.forbidden.map(function (r) {
        return d.h("tr", null,
          d.h("td", { "data-label": t("bank.forbidden.colSay") }, d.h("mark", null, r.text)), d.h("td", { "data-label": t("bank.forbidden.colWhy") }, r.why_cs),
          d.h("td", { "data-label": t("bank.forbidden.colCheck") }, r.found.map(function (c) { return d.h("span.chip.tone-risk", null, codeLabel(c)); })),
          d.h("td", { "data-label": t("bank.forbidden.colInstead") }, r.swap));
      });
      var guard = bank.guardrails.map(function (g) {
        return d.h("li", null, d.h("strong", null, g.title_cs), d.h("br"), g.text_cs,
          g.evidence.map(function (x) { return d.h("span.small.muted", null, d.h("br"), d.h("strong", null, x.name + ": "), t("vault.ev." + x.label) + ". " + x.ethics); }));
      });
      d.fill(panel, [
        czechNote(),
        d.h("section.card", null, widgets.heading(2, t("bank.forbidden.title"), t("bank.forbidden.sub")),
          d.h("div.table-scroll", null, d.h("table.data-table.stack", null,
            d.h("caption.sr-only", null, t("bank.forbidden.title")),
            d.h("thead", null, d.h("tr", null, [t("bank.forbidden.colSay"), t("bank.forbidden.colWhy"), t("bank.forbidden.colCheck"), t("bank.forbidden.colInstead")].map(function (h) { return d.h("th", { scope: "col" }, h); }))),
            d.h("tbody", null, rows)))),
        d.h("section.card", null, widgets.heading(2, t("bank.rules.title")), d.h("ul.open", null, guard))
      ]);
      return { destroy: function () {} };
    }

    // ===== confirm ======================================================================================
    function buildConfirm(panel) {
      var items = bank.needs.map(function (n) {
        return d.h("li", null, d.h("strong", null, n.need), d.h("br"),
          d.h("span.small.muted", null, t("bank.confirm.concerns") + " " + n.texts.map(function (x) { return /^Název /.test(x) ? x : "„" + x + "“"; }).join(", ")));
      });
      d.fill(panel, [
        czechNote(),
        d.h("section.card", null, widgets.heading(2, t("bank.confirm.title"), t("bank.confirm.sub")), d.h("ul.open", null, items))
      ]);
      return { destroy: function () {} };
    }

    var builders = { start: buildStart, levers: buildLevers, groups: buildGroups, story: buildStory, rules: buildRules, confirm: buildConfirm };
    var icon = { start: "star", levers: "layers", groups: "users", story: "book", rules: "shieldCheck", confirm: "check" };
    var tabs = widgets.tabs({
      label: t("bank.tabs"), active: state.tab,
      items: TABS.map(function (id) { return { id: id, label: t("bank.tab." + id), icon: icon[id] }; }),
      onChange: function (id, panel) {
        state.tab = id;
        if (current && current.destroy) current.destroy();
        d.clear(panel);
        current = builders[id](panel);
        try { root.history.replaceState(null, "", "#/claims/" + id); } catch (e) { /* file:// in some browsers */ }
      }
    });
    d.fill(page, [
      d.h("div.arena-head", null,
        d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("bank.title")),
        d.h("p.page-lead", null, t("bank.lead"))),
      tabs.el, tabs.panel
    ]);
    return { destroy: function () { if (current && current.destroy) current.destroy(); } };
  }

  return { mount: mount, TABS: TABS };
});
