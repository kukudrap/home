/* About: what is real and what is simulated, how the Dopamine Score works (weights and limits are read from
 * the scoring spec in the bundle), the Trust Shield, the ethics of the game with the published chest odds,
 * privacy, keyboard help, sources and build information. In an edition with a vertical (bundle.vertical) it
 * also describes the edition, the claims check, the glossary and the regulatory note (not legal advice).
 * Everything here is reference text, so every number comes from the bundle or from game.js and never from a
 * second copy.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.about = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var DRIVERS = ["curiosity", "surprise", "emotion", "relevance", "utility"];
  var RARITIES = ["common", "rare", "epic", "legendary"];
  var SHIELDS = ["intact", "cracked", "broken"];

  /** Unique references from the Myth or Fact cards ("Berridge and Robinson, 1998; Schultz et al., 1997"). */
  function collectRefs(myths) {
    var seen = {}, out = [];
    (myths || []).forEach(function (m) {
      String(m && m.ref ? m.ref : "").split(/;\s*/).forEach(function (r) {
        r = r.trim();
        if (r && !seen[r]) { seen[r] = true; out.push(r); }
      });
    });
    return out.sort(function (a, b) { return a.localeCompare(b); });
  }

  function mount(container, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets, game = root.DK.game;
    var t = d.t;
    var b = ctx.bundle || {};
    var spec = b.spec || {};
    var params = spec.params || {};
    var meta = b.meta || {};
    var loot = b.loot || { cards: [], rates: {}, pity_after: 8 };
    var lang = ctx.lang();
    var page = d.h("div.page.about");
    container.appendChild(page);

    function card(id, title, icon, children, cls) {
      return d.h("section.card.about-card" + (cls ? "." + cls : ""), { "aria-labelledby": id },
        d.h("h2.card-title", { id: id }, icon ? icons.icon(icon, { size: 20 }) : null, d.h("span", null, title)),
        children);
    }
    function bullets(keys, icon, params2) {
      return d.h("ul.fact-list", null, keys.map(function (k) { return d.h("li", null, icons.icon(icon, { size: 17 }), d.h("span", null, t(k, params2))); }));
    }

    // -- intro ----------------------------------------------------------------------------------------------
    function intro() {
      return d.h("section.card.hero.about-hero", null,
        d.h("div.hero-main", null,
          d.h("p.eyebrow", null, t("app.tagline")),
          d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("about.title")),
          d.h("p.hero-lead", null, t("about.lead")),
          d.h("div.chip-row", null,
            widgets.chip(t("top.demo"), { tone: "warn", icon: "flask", title: t("top.demoTitle") }),
            widgets.chip(t("about.chipOffline"), { tone: "ok", icon: "lock" }),
            widgets.chip(t("about.chipNoTrack"), { tone: "info", icon: "shieldCheck" }))),
        d.h("div.hero-art", { "aria-hidden": "true" }, icons.logo(120)));
    }

    // -- the edition (vertical) -------------------------------------------------------------------------------
    var vertical = b.vertical || null;
    var ui = root.DK.ui.claimsui;
    var claimsOn = !!ui.engine(b);

    function editionCard() {
      if (!vertical) return null;
      return d.h("section", { "aria-labelledby": "edition-h" },
        d.h("div.heading", null, d.h("div.heading-main", null, d.h("h2.heading-title", { id: "edition-h" }, t("about.edition.title")), d.h("p.heading-sub", null, t("about.edition.sub")))),
        d.h("div.card.edition-card", null,
          d.h("h3.edition-name", null, ui.pickLang(vertical, "edition", lang) || ui.pickLang(vertical, "name", lang)),
          d.h("p.edition-tagline", null, ui.pickLang(vertical, "tagline", lang)),
          bullets(["about.edition.1", "about.edition.2", "about.edition.3", "about.edition.4"], "check"),
          d.h("p.small.muted", null, t("edition.built"))));
    }

    function claimsCard() {
      if (!claimsOn) return null;
      var rows = [["about.claims.error", "error"], ["about.claims.warn", "warn"], ["about.claims.info", "info"]];
      return card("claims-h", t("about.claims.title"), "shieldCheck", [
        d.h("p.small.muted", null, t("about.claims.sub")),
        d.h("p", null, t("about.claims.intro")),
        d.h("ul.fact-list", null, rows.map(function (r) { return d.h("li", null, ui.severityChip(r[1]), d.h("span", null, t(r[0]))); })),
        d.h("p.small.muted", null, t("about.claims.limits")),
        d.h("a.btn.btn-ghost.btn-sm", { href: "#/vault/claims" }, icons.icon("shieldCheck", { size: 16 }), d.h("span", null, t("edition.openMap")))
      ], "claims-about");
    }

    function glossaryCard() {
      var list = vertical && Array.isArray(vertical.glossary) ? vertical.glossary : [];
      if (!list.length) return null;
      return card("glossary-h", t("about.glossary.title"), "book", [
        d.h("p.small.muted", null, t("about.glossary.sub")),
        d.h("dl.glossary-list", null, list.map(function (g) {
          return d.h("div.glossary-item", null, d.h("dt", null, ui.pickLang(g, "term", lang) || g.id), d.h("dd", null, ui.pickLang(g, "def", lang)));
        }))
      ], "glossary-card");
    }

    function regCard() {
      var note = vertical ? ui.pickLang(vertical, "regulatory_note", lang) : "";
      if (!note) return null;
      return d.h("section.card.about-card.note-card.reg-note", { role: "note", "aria-labelledby": "reg-h" },
        d.h("div.editor-head", null,
          d.h("h2.card-title", { id: "reg-h" }, icons.icon("scale", { size: 20 }), d.h("span", null, t("about.reg.title"))),
          d.h("span.chip.tone-warn.legal-chip", null, icons.icon("info", { size: 13 }), d.h("span", null, t("about.reg.badge")))),
        d.h("p", null, note));
    }

    // -- real versus simulated ----------------------------------------------------------------------------
    function honesty() {
      var corpus = meta.corpus || {};
      var date = typeof meta.generated === "string" ? meta.generated.slice(0, 10) : null;
      return d.h("section", { "aria-labelledby": "honest-h" },
        d.h("div.heading", null, d.h("div.heading-main", null, d.h("h2.heading-title", { id: "honest-h" }, t("about.honest.title")), d.h("p.heading-sub", null, t("about.honest.sub")))),
        d.h("div.grid-2.honest-grid", null,
          d.h("div.card.real-card", null,
            d.h("h3.card-title", null, icons.icon("check", { size: 20, stroke: 2.6 }), d.h("span", null, t("about.real.title"))),
            bullets(["about.real.1", "about.real.2", "about.real.3"], "check")),
          d.h("div.card.sim-card", null,
            d.h("h3.card-title", null, icons.icon("flask", { size: 20 }), d.h("span", null, t("about.sim.title"))),
            bullets(["about.sim.1", "about.sim.2", "about.sim.3"], "flask"))),
        d.h("p.small.muted.bundle-line", null, t("about.bundleLine", { brands: corpus.brands === undefined ? "?" : d.fmt(corpus.brands), items: corpus.items === undefined ? "?" : d.fmt(corpus.items), date: date || "?" })));
    }

    // -- how the score works ------------------------------------------------------------------------------
    function scoreCard() {
      var w = params.weights || {};
      var sum = DRIVERS.reduce(function (s, k) { return s + (+w[k] || 0); }, 0) || 1;
      var labels = spec.labels || {};
      function label(k) { return labels[k] ? (labels[k][lang] || labels[k].en) : k; }
      var rows = DRIVERS.map(function (k) {
        var share = (+w[k] || 0) / sum;
        return d.h("li.de-row", null,
          d.h("div.de-name", null, icons.icon(icons.DRIVER_ICON[k] || "spark", { size: 18 }), d.h("strong", null, label(k))),
          d.h("div.de-weight", null,
            charts.meter({ value: share * 100, max: 100, size: "sm", tone: "d-" + k, label: label(k) + ": " + t("about.score.weight"), valueText: function () { return d.fmtPct(share, 0); } }),
            d.h("span.num", null, d.fmtPct(share, 0))),
          d.h("p.small.de-desc", null, t("about.score.d." + k)));
      });
      var floor = typeof params.fluency_floor === "number" ? params.fluency_floor : 0.55;
      var penalty = typeof params.risk_penalty === "number" ? params.risk_penalty : 0.65;
      rows.push(d.h("li.de-row.is-mod", null,
        d.h("div.de-name", null, icons.icon(icons.DRIVER_ICON.fluency || "spark", { size: 18 }), d.h("strong", null, label("fluency"))),
        d.h("div.de-weight", null, d.h("span.chip", null, t("about.score.fluencyRange", { lo: d.fmtPct(floor, 0) }))),
        d.h("p.small.de-desc", null, t("about.score.d.fluency"))));
      rows.push(d.h("li.de-row.is-mod", null,
        d.h("div.de-name", null, icons.icon("alert", { size: 18 }), d.h("strong", null, label("risk"))),
        d.h("div.de-weight", null, d.h("span.chip.tone-risk", null, t("about.score.riskRange", { n: d.fmtPct(penalty, 0) }))),
        d.h("p.small.de-desc", null, t("about.score.d.risk"))));

      var cal = b.calibration;
      var calBox = null;
      if (cal && typeof cal.cv_spearman_default === "number" && typeof cal.cv_spearman_calibrated === "number") {
        calBox = d.h("div.callout.cal-box", null,
          icons.icon("scale", { size: 20 }),
          d.h("div", null,
            d.h("strong", null, t("about.cal.title")),
            d.h("p.small", null, t("about.cal.text", { n: d.fmt(cal.n || 0), a: d.fmt(cal.cv_spearman_default, 2), b: d.fmt(cal.cv_spearman_calibrated, 2) }))));
      }

      return d.h("section", { "aria-labelledby": "score-h" },
        d.h("div.heading", null, d.h("div.heading-main", null, d.h("h2.heading-title", { id: "score-h" }, t("about.score.title")), d.h("p.heading-sub", null, t("about.score.sub")))),
        d.h("div.card.score-explain", null,
          d.h("p", null, t("about.score.intro")),
          d.h("ul.driver-explain", null, rows),
          d.h("h3.sub", null, t("about.score.stepsTitle")),
          d.h("ol.step-list", null, [1, 2, 3, 4, 5, 6].map(function (n) { return d.h("li", null, t("about.score.step." + n, { penalty: d.fmtPct(penalty, 0) })); })),
          calBox,
          d.h("h3.sub", null, t("about.limits.title")),
          bullets(["about.limits.1", "about.limits.2", "about.limits.3", "about.limits.4"], "info")));
    }

    function shieldCard() {
      return card("shield-h", t("about.shield.title"), "shieldCheck", [
        d.h("p", null, t("about.shield.text")),
        d.h("div.shield-opts", null, SHIELDS.map(function (s) {
          return d.h("div.shield-opt.is-" + s, null, icons.shield(s, 30), d.h("strong", null, t("boss.shield." + s)), d.h("span", null, t("boss.shieldRange." + s)));
        })),
        d.h("p.small.muted", null, t("about.shield.rule", { risk: d.fmtPct(game.BOSS_MAX_RISK, 0) })),
        claimsOn ? d.h("p.small.muted", null, t("about.shield.claims")) : null
      ]);
    }

    // -- ethics and odds ------------------------------------------------------------------------------------
    function ethicsCard() {
      var pity = loot.pity_after || 8;
      var minutes = game.DEFAULT_SESSION_MINUTES;
      return card("ethics-h", t("about.ethics.title"), "heart", [
        d.h("p", null, t("about.ethics.intro")),
        d.h("ul.fact-list", null, [
          ["about.ethics.1", {}], ["about.ethics.2", { n: pity }], ["about.ethics.3", {}], ["about.ethics.4", {}], ["about.ethics.5", { m: minutes }], ["about.ethics.6", {}], ["about.ethics.7", {}]
        ].map(function (e) { return d.h("li", null, icons.icon("shieldCheck", { size: 17 }), d.h("span", null, t(e[0], e[1]))); }))
      ]);
    }

    function oddsCard() {
      var cards = loot.cards || [];
      var rates = loot.rates || {};
      var rows = RARITIES.map(function (r) {
        var n = cards.filter(function (c) { return (RARITIES.indexOf(c.rarity) >= 0 ? c.rarity : "common") === r; }).length;
        return d.h("tr" + (n ? "" : ".is-empty"), null,
          d.h("th", { scope: "row" }, d.h("span.rar-name.r-" + r, null, icons.gems(r, 13), d.h("span", null, t("vault.rarity." + r)))),
          d.h("td.num", null, d.fmtPct(+rates[r] || 0, 0)),
          d.h("td.num", null, String(n)));
      });
      var missing = RARITIES.filter(function (r) { return !cards.some(function (c) { return c.rarity === r; }) && (+rates[r] || 0) > 0; });
      return card("odds-h", t("vault.dropTitle"), "scale", [
        d.h("p.small.muted", null, t("vault.dropIntro")),
        d.h("div.table-scroll", null, d.h("table.data-table.drop-table", null,
          d.h("caption.sr-only", null, t("vault.dropTitle")),
          d.h("thead", null, d.h("tr", null, [t("vault.colRarity"), t("vault.colRate"), t("vault.colCards")].map(function (h, i) { return d.h("th", { scope: "col", class: i ? "num" : "" }, h); }))),
          d.h("tbody", null, rows))),
        missing.length ? d.h("p.small.upset-note", null, icons.icon("info", { size: 15 }), d.h("span", null, t("vault.dropFallback", { r: missing.map(function (r) { return t("vault.rarity." + r); }).join(", ") }))) : null,
        d.h("p.small.muted", null, t("vault.pityRule", { n: loot.pity_after || 8 })),
        d.h("p.small.muted", null, t("vault.noMoney"))
      ], "odds-card");
    }

    // -- privacy --------------------------------------------------------------------------------------------
    function privacyCard() {
      var live = ctx.live();
      return card("privacy-h", t("about.privacy.title"), "lock", [
        d.h("ul.fact-list", null, ["about.privacy.1", "about.privacy.2", "about.privacy.3", "about.privacy.4"].map(function (k) {
          return d.h("li", null, icons.icon("lock", { size: 17 }), d.h("span", null, t(k, { key: game.PROFILE_KEY })));
        })),
        d.h("div.row.wrap", null,
          d.h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: function () { ctx.openProfile(); } }, icons.icon("settings", { size: 15 }), d.h("span", null, t("top.profile"))),
          d.h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: function () { ctx.exportProfile(); } }, icons.icon("download", { size: 15 }), d.h("span", null, t("profile.export")))),
        d.h("p.small.muted", null, live.enabled ? t("about.privacy.liveOn") : t("about.privacy.liveOff"))
      ]);
    }

    // -- keyboard -------------------------------------------------------------------------------------------
    function keysCard() {
      var rows = [
        { keys: ["Tab"], text: "about.keys.tab" },
        { keys: ["A", "←"], sep: "or", text: "about.keys.arenaA" },
        { keys: ["B", "→"], sep: "or", text: "about.keys.arenaB" },
        { keys: ["Enter"], text: "about.keys.next" },
        { keys: ["M", "←"], sep: "or", text: "about.keys.myth" },
        { keys: ["F", "→"], sep: "or", text: "about.keys.fact" },
        { keys: ["Ctrl", "Enter"], sep: "+", text: "about.keys.boss" },
        { keys: ["←", "→", "Home", "End"], text: "about.keys.tabs" },
        { keys: ["Esc"], text: "about.keys.esc" }
      ];
      function keyCell(r) {
        var nodes = [];
        r.keys.forEach(function (k, i) {
          if (i && r.sep) nodes.push(d.h("span.small.muted", null, r.sep === "or" ? t("about.keys.or") : r.sep));
          nodes.push(d.kbd(k));
        });
        return d.h("span.keys-cell", null, nodes);
      }
      return card("keys-h", t("about.keys.title"), "settings", [
        d.h("div.table-scroll", null, d.h("table.data-table.keys-table", null,
          d.h("caption.sr-only", null, t("about.keys.title")),
          d.h("thead", null, d.h("tr", null, d.h("th", { scope: "col" }, t("common.key")), d.h("th", { scope: "col" }, t("common.action")))),
          d.h("tbody", null, rows.map(function (r) { return d.h("tr", null, d.h("th", { scope: "row" }, keyCell(r)), d.h("td", null, t(r.text))); })))),
        d.h("h3.sub", null, t("about.a11y.title")),
        bullets(["about.a11y.1", "about.a11y.2", "about.a11y.3", "about.a11y.4"], "check")
      ]);
    }

    // -- credits --------------------------------------------------------------------------------------------
    function creditsCard() {
      var refs = collectRefs(b.myths);
      var nStudies = ((b.vault || {}).studies || []).length;
      return card("credits-h", t("about.credits.title"), "book", [
        d.h("p", null, t("about.credits.text")),
        refs.length ? d.h("ul.ref-list", null, refs.map(function (r) { return d.h("li", null, icons.icon("book", { size: 15 }), d.h("span", null, r)); })) : null,
        d.h("p.small", null, nStudies ? d.h("a.link", { href: "#/vault/studies" }, ctx.tp("about.credits.studies", nStudies)) : t("about.credits.noStudies")),
        d.h("p.small.muted", null, t("vault.myth.caveat")),
        d.h("p.small.muted", null, t("about.credits.made"))
      ]);
    }

    // -- build info -----------------------------------------------------------------------------------------
    function buildCard() {
      var live = ctx.live();
      var corpus = meta.corpus || {};
      var rowsData = [
        [t("about.build.bundle"), meta.version === undefined ? "?" : "v" + meta.version],
        [t("about.build.generated"), typeof meta.generated === "string" ? meta.generated.slice(0, 10) : "?"],
        [t("about.build.corpus"), t("about.build.corpusValue", { brands: corpus.brands === undefined ? "?" : d.fmt(corpus.brands), items: corpus.items === undefined ? "?" : d.fmt(corpus.items) })],
        [t("about.build.spec"), spec.version === undefined ? "?" : "v" + spec.version],
        [t("about.build.mode"), live.enabled ? t("about.build.modeLive", { v: live.version || "?" }) : t("about.build.modeOffline")],
        [t("about.build.storage"), ctx.store && ctx.store.usingFallback && ctx.store.usingFallback() ? t("about.build.storageMemory") : t("about.build.storageBrowser")]
      ];
      return card("build-h", t("about.build.title"), "info", [
        d.h("dl.build-list", null, rowsData.map(function (r) { return d.h("div", null, d.h("dt", null, r[0]), d.h("dd", null, r[1])); })),
        live.enabled ? parityBox() : null
      ]);
    }

    /**
     * Live mode only: score two sample hooks in this page and on the Python server (/api/score) and show that the
     * numbers agree. This checks the claim "the same scoring code runs in Python and in this page" on your machine.
     */
    function parityBox() {
      var SAMPLES = [
        { text: "7 mistakes every beginner runner makes (and how to fix them)", lang: "en" },
        { text: "Proč většina firem ztrácí zákazníky a jak to změnit", lang: "cs" }
      ];
      var out = d.h("ul.parity-list", { "aria-live": "polite" });
      var btn = d.h("button.btn.btn-ghost.btn-sm", { type: "button" }, icons.icon("scale", { size: 15 }), d.h("span", null, t("about.parity.run")));
      btn.addEventListener("click", function () {
        btn.disabled = true;
        d.fill(out, d.h("li.muted", null, t("about.parity.running")));
        Promise.all(SAMPLES.map(function (sm) {
          return ctx.api.score({ text: sm.text, lang: sm.lang }).then(function (server) {
            var mine = root.DK.scoring.scoreHook(sm.text, "", { lang: sm.lang });
            return { sm: sm, server: server.total, mine: mine.total, same: Math.abs(server.total - mine.total) <= 0.006 };
          });
        })).then(function (rows) {
          d.fill(out, rows.map(function (r) {
            return d.h("li" + (r.same ? ".is-same" : ".is-diff"), null,
              icons.icon(r.same ? "check" : "alert", { size: 16 }),
              d.h("span", null, d.h("strong", null, d.quote(r.sm.text)), " ", t(r.same ? "about.parity.same" : "about.parity.differ", { a: d.fmt(r.server, 2), b: d.fmt(r.mine, 2) })));
          }));
        }).catch(function (err) {
          d.fill(out, d.h("li.is-diff", null, icons.icon("alert", { size: 16 }), d.h("span", null, t("about.parity.failed", { e: err && err.message ? err.message : "?" }))));
        }).then(function () { btn.disabled = false; });
      });
      return d.h("div.parity", null, d.h("h3.sub", null, t("about.parity.title")), d.h("p.small.muted", null, t("about.parity.text")), d.h("div.row.wrap", null, btn), out);
    }

    d.fill(page, [
      intro(),
      editionCard(),
      honesty(),
      scoreCard(),
      shieldCard(),
      claimsCard(),
      glossaryCard(),
      regCard(),
      d.h("div.grid-2.about-pair", null, ethicsCard(), oddsCard()),
      privacyCard(),
      keysCard(),
      creditsCard(),
      buildCard()
    ]);
    return { destroy: function () { /* nothing to clean up */ } };
  }

  return { mount: mount, collectRefs: collectRefs };
});
