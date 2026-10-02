/* Vault: evidence cards, studies, the claims map and the Myth or Fact quiz.
 *  Cards: chests with PUBLISHED drop rates and a visible pity counter, the loot collection with rarity
 *         frames (locked silhouettes until owned), and the evidence tactics from the research ledger.
 *  Studies: the ledger with grade, design, year, venue and a verified flag; links resolve to evidence tactics
 *         and to claim topics, and a study that is not verified yet is always marked.
 *  Claims map (editions with bundle.claims): the claim topics grouped by class with their evidence label, safer
 *         wording and studies, the regulatory note, and a box that runs the claims checker on any pasted text.
 *  Myth or Fact: swipe or click, with the explanation, reference and caveat.
 * Missing or empty data always gets a friendly empty state.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.vault = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var RARITIES = ["common", "rare", "epic", "legendary"];
  var DESIGNS = ["meta-analysis", "systematic-review", "rct", "field-experiment", "lab-experiment", "observational", "survey", "theory", "qualitative", "book", "preprint", "guideline", "unknown"];
  var KIND_ICON = { pattern: "chart", tip: "bulb", study: "book", tactic: "layers" };
  var CONFETTI_BY_RARITY = { common: 0, rare: 70, epic: 130, legendary: 230 };

  var state = { tab: "cards", studyFilter: "all", lootFilter: "all", tacticTheme: "all", tacticEvidence: "all", checkText: "", focusCheck: false, myth: { current: null, answered: null, correctRun: 0, played: 0 } };
  var TABS = ["cards", "studies", "claims", "myths"];

  function rarityOf(card) { return RARITIES.indexOf(card.rarity) >= 0 ? card.rarity : "common"; }

  function mount(container, ctx, route) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets;
    var t = d.t;
    var sub = (route && route.sub) || (route && route.params && route.params.tab) || null;
    var hasClaims = !!root.DK.ui.claimsui.claimsMap(ctx.bundle, ctx.lang());     // only editions with a claims map get the tab
    if (TABS.indexOf(sub) >= 0) state.tab = sub;
    if (hasClaims && route && route.params && route.params.focus === "check") { state.tab = "claims"; state.focusCheck = true; }
    if (state.tab === "claims" && !hasClaims) state.tab = "cards";
    var page = d.h("div.page.vault");
    var current = null;
    var builders = { cards: buildCards, studies: buildStudies, claims: buildClaims, myths: buildMyths };
    var items = [{ id: "cards", label: t("vault.tab.cards"), icon: "gem" }, { id: "studies", label: t("vault.tab.studies"), icon: "book" }];
    if (hasClaims) items.push({ id: "claims", label: t("vault.tab.claims"), icon: "shieldCheck" });
    items.push({ id: "myths", label: t("vault.tab.myths"), icon: "bulb" });
    var tabs = widgets.tabs({
      label: t("vault.tabs"), active: state.tab,
      items: items,
      onChange: function (id, panel) {
        state.tab = id;
        if (current && current.destroy) current.destroy();
        d.clear(panel);
        current = builders[id](panel, ctx);
        try { root.history.replaceState(null, "", "#/vault/" + id); } catch (e) { /* ignore */ }
      }
    });
    d.fill(page, [
      d.h("div.arena-head", null,
        d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("vault.title")),
        d.h("p.page-lead", null, t("vault.lead") + (hasClaims ? " " + t("vault.leadClaims") : ""))),
      tabs.el, tabs.panel
    ]);
    container.appendChild(page);
    return { destroy: function () { if (current && current.destroy) current.destroy(); } };
  }

  // ===== Cards =============================================================================================
  function buildCards(panel, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets, game = root.DK.game;
    var t = d.t;
    var loot = ctx.bundle.loot || { cards: [], rates: {}, pity_after: 8 };
    var cards = loot.cards || [];
    var vault = ctx.bundle.vault || {};
    var tactics = vault.tactics || [];
    var host = d.h("div.vault-cards");
    d.fill(panel, host);
    var timers = [];
    var openDialog = null;

    function owned() { return ctx.profile().deck; }
    function cardTitle(c) { return ctx.pick(c, "title") || c.id; }
    function kindLabel(kind) { return t("vault.kind." + (KIND_ICON[kind] ? kind : "tip")); }
    function rarityLabel(r) { return t("vault.rarity." + r); }

    // -- chest panel
    function pityPips(pity, max) {
      var wrap = d.h("div.pity-pips", { role: "img", "aria-label": t("vault.pityAria", { n: Math.min(pity, max), max: max }) });
      for (var i = 0; i < max; i++) wrap.appendChild(d.h("i" + (i < pity ? ".on" : "")));
      return wrap;
    }

    function dropTable() {
      var p = ctx.profile();
      var rates = loot.rates || {};
      var rows = RARITIES.map(function (r) {
        var inRar = cards.filter(function (c) { return rarityOf(c) === r; });
        var own = inRar.filter(function (c) { return p.deck.indexOf(c.id) >= 0; }).length;
        var empty = inRar.length === 0;
        return d.h("tr" + (empty ? ".is-empty" : ""), null,
          d.h("th", { scope: "row" }, d.h("span.rar-name.r-" + r, null, icons.gems(r, 13), d.h("span", null, rarityLabel(r)))),
          d.h("td.num", null, d.fmtPct(+rates[r] || 0, 0)),
          d.h("td.num", null, String(inRar.length)),
          d.h("td.num", null, inRar.length ? own + "/" + inRar.length : "-"));
      });
      var missing = RARITIES.filter(function (r) { return !cards.some(function (c) { return rarityOf(c) === r; }) && (+((loot.rates || {})[r]) || 0) > 0; });
      return d.h("section.card.drop-card", { "aria-labelledby": "drop-h" },
        d.h("h2.card-title", { id: "drop-h" }, icons.icon("scale", { size: 20 }), t("vault.dropTitle")),
        d.h("p.small.muted", null, t("vault.dropIntro")),
        d.h("div.table-scroll", null, d.h("table.data-table.drop-table", null,
          d.h("caption.sr-only", null, t("vault.dropTitle")),
          d.h("thead", null, d.h("tr", null, [t("vault.colRarity"), t("vault.colRate"), t("vault.colCards"), t("vault.colOwned")].map(function (h, i) { return d.h("th", { scope: "col", class: i ? "num" : "" }, h); }))),
          d.h("tbody", null, rows))),
        missing.length ? d.h("p.small.upset-note", null, icons.icon("info", { size: 15 }), d.h("span", null, t("vault.dropFallback", { r: missing.map(rarityLabel).join(", ") }))) : null,
        d.h("p.small.muted", null, t("vault.pityRule", { n: loot.pity_after || 8 })),
        d.h("p.small.muted", null, t("vault.noMoney")));
    }

    function chestPanel() {
      var p = ctx.profile();
      var max = loot.pity_after || 8;
      var guaranteed = p.pity >= max;
      var openBtn = d.h("button.btn.btn-primary.btn-lg", { type: "button", disabled: p.chestsReady < 1 || !cards.length, onclick: function () { openFlow(); } }, icons.icon("vault", { size: 20 }), d.h("span", null, t("vault.openChest")));
      return d.h("section.card.chest-panel", { "aria-labelledby": "chest-h" },
        d.h("div.chest-art", { "aria-hidden": "true" }, icons.chest({ size: 150 })),
        d.h("div.chest-body", null,
          d.h("h2.card-title", { id: "chest-h" }, t("vault.chestTitle")),
          d.h("p.chest-count", { "aria-live": "polite" }, ctx.tp("vault.chestsReady", p.chestsReady)),
          p.chestsReady < 1 ? d.h("p.small.muted", null, t("vault.chestHow")) : null,
          d.h("div.pity", null,
            d.h("span.small", null, guaranteed ? t("vault.pityGuaranteed") : t("vault.pityLine", { n: p.pity, max: max })),
            pityPips(p.pity, max)),
          openBtn));
    }

    // -- loot grid
    function lootCard(c) {
      var r = rarityOf(c);
      var own = owned().indexOf(c.id) >= 0;
      if (!own) {
        return d.h("li", null, d.h("div.loot-card.r-" + r + ".is-locked", { role: "img", "aria-label": t("vault.lockedAria", { r: rarityLabel(r) }) },
          d.h("span.loot-top", null, icons.gems(r, 13), d.h("span.loot-rarity", null, rarityLabel(r))),
          d.h("span.loot-lock", null, icons.icon("lock", { size: 24 })),
          d.h("span.loot-kind", null, t("vault.locked") + " \u00b7 " + kindLabel(c.kind))));
      }
      return d.h("li", null, d.h("button.loot-card.r-" + r + ".is-owned", { type: "button", onclick: function () { showCard(c); } },
        d.h("span.loot-top", null, icons.gems(r, 13), d.h("span.loot-rarity", null, rarityLabel(r))),
        d.h("span.loot-kind", null, icons.icon(KIND_ICON[c.kind] || "bulb", { size: 16 }), d.h("span", null, kindLabel(c.kind))),
        d.h("strong.loot-title", null, cardTitle(c)),
        c.demo ? d.h("span.chip.tone-warn", null, t("common.simulatedShort")) : null));
    }

    function showCard(c) {
      var r = rarityOf(c);
      ctx.apply(game.applyVaultOpen, null);
      var dlg = widgets.dialog({
        title: cardTitle(c),
        body: d.h("div.stack.tight.card-detail", null,
          d.h("div.row.wrap", null, d.h("span.rar-name.r-" + r, null, icons.gems(r, 14), d.h("span", null, rarityLabel(r))), d.h("span.chip", null, icons.icon(KIND_ICON[c.kind] || "bulb", { size: 13 }), d.h("span", null, kindLabel(c.kind))),
            c.demo ? d.h("span.chip.tone-warn", null, icons.icon("flask", { size: 13 }), d.h("span", null, t("common.simulated"))) : null),
          d.h("p.detail-body", null, ctx.pick(c, "body")),
          c.demo ? d.h("p.small.muted", null, t("vault.demoCard")) : null),
        actions: [d.h("button.btn.btn-primary", { type: "button", onclick: function () { dlg.close(); } }, t("common.close"))]
      });
    }

    function lootGrid() {
      var p = ctx.profile();
      var rank = function (c) { return RARITIES.indexOf(rarityOf(c)); };
      var isOwned = function (c) { return p.deck.indexOf(c.id) >= 0; };
      var sorted = cards.slice().sort(function (a, b) { return rank(b) - rank(a) || (isOwned(b) ? 1 : 0) - (isOwned(a) ? 1 : 0); });
      var ownedN = cards.filter(isOwned).length;
      if (!cards.length) return widgets.emptyState({ icon: "gem", title: t("vault.noCards.title"), text: t("vault.noCards.text") });
      var shown = sorted.filter(function (c) { return state.lootFilter === "all" || (state.lootFilter === "owned") === isOwned(c); });
      var filter = widgets.segmented({
        label: t("vault.lootFilter"), active: state.lootFilter,
        items: [{ id: "all", label: t("common.all") }, { id: "owned", label: t("common.owned") }, { id: "locked", label: t("common.locked") }],
        onChange: function (id) { state.lootFilter = id; var host2 = grid.parentNode; if (host2) host2.replaceChild(lootGrid(), grid); }
      });
      var grid = d.h("section", { "aria-labelledby": "loot-h" },
        widgets.heading(2, t("vault.collection"), t("vault.collectionSub"), d.h("span.chip.tone-brand", null, t("common.of", { a: ownedN, b: cards.length })), "loot-h"),
        charts.meter({ value: ownedN, max: Math.max(1, cards.length), size: "sm", tone: "brand", label: t("vault.collection"), valueText: function () { return ownedN + " / " + cards.length; } }),
        filter.el,
        shown.length ? d.h("ul.loot-grid", null, shown.map(lootCard)) : d.h("p.muted", null, t("vault.noMatch2")));
      return grid;
    }

    // -- evidence tactics
    function evidenceChip(label) { return root.DK.ui.claimsui.evidenceChip(label); }

    function themeLabel(id) {
      var labels = (ctx.bundle.spec && ctx.bundle.spec.labels) || {};
      if (labels[id]) return labels[id][ctx.lang()] || labels[id].en;
      return d.t("vault.theme." + id) === "vault.theme." + id ? String(id || "") : d.t("vault.theme." + id);
    }

    function tacticCard(tc) {
      var ev = tc.evidence || {};
      var label = ev.label || "none";
      var caveats = ctx.pick(ev, "caveats");
      var caveatList = Array.isArray(caveats) ? caveats : (caveats ? [caveats] : []);
      var headline = ctx.pick(ev, "headline");
      var det = d.h("details.tactic-more", null,
        d.h("summary", null, d.h("span", null, t("vault.tacticMore")), icons.icon("chevronDown", { size: 16, class: "chev" })),
        caveatList.length ? d.h("div", null, d.h("h4.sub", null, t("vault.caveats")), d.h("ul.reason-list", null, caveatList.map(function (c) { return d.h("li", null, icons.icon("alert", { size: 14 }), d.h("span", null, String(c))); }))) : null,
        ctx.pick(tc, "ethics") ? d.h("div", null, d.h("h4.sub", null, t("vault.ethics")), d.h("p.small", null, ctx.pick(tc, "ethics"))) : null);
      det.addEventListener("toggle", function () { if (det.open) ctx.apply(game.applyVaultOpen, null); });
      return d.h("li", null, d.h("article.tactic.ev-card-" + label, null,
        d.h("div.tactic-head", null,
          d.h("h3.tactic-name", null, ctx.pick(tc, "name") || tc.id),
          evidenceChip(label)),
        d.h("div.chip-row", null,
          tc.driver ? d.h("span.chip.tone-info", null, themeLabel(tc.driver)) : null,
          ev.grade ? d.h("span.chip.grade-" + String(ev.grade).toLowerCase(), null, t("vault.grade", { g: ev.grade })) : null,
          typeof ev.n_studies === "number" ? d.h("span.chip", null, ctx.tp("vault.nStudies", ev.n_studies)) : null),
        ctx.pick(tc, "summary") ? d.h("p", null, ctx.pick(tc, "summary")) : null,
        headline ? d.h("p.small.tactic-headline", null, icons.icon("book", { size: 15 }), d.h("span", null, headline)) : null,
        det));
    }

    function tacticsSection() {
      if (!tactics.length) {
        return widgets.emptyState({ icon: "layers", title: t("vault.noTactics.title"), text: t("vault.noTactics.text") });
      }
      var themes = [];
      tactics.forEach(function (x) { if (x.driver && themes.indexOf(x.driver) < 0) themes.push(x.driver); });
      var levels = ["strong", "moderate", "limited", "contested", "none"].filter(function (l) { return tactics.some(function (x) { return ((x.evidence || {}).label || "none") === l; }); });
      var list = d.h("ul.tactic-grid");
      var count = d.h("p.small.muted", { role: "status" });
      function paint() {
        var shown = tactics.filter(function (x) {
          return (state.tacticTheme === "all" || x.driver === state.tacticTheme) && (state.tacticEvidence === "all" || ((x.evidence || {}).label || "none") === state.tacticEvidence);
        });
        d.fill(list, shown.map(tacticCard));
        count.textContent = t("vault.tacticCount", { a: shown.length, b: tactics.length });
      }
      var themeSel = d.h("select.input", { id: "tac-theme", onchange: function () { state.tacticTheme = themeSel.value; paint(); } },
        [d.h("option", { value: "all", selected: state.tacticTheme === "all" }, t("common.all"))].concat(themes.map(function (th) { return d.h("option", { value: th, selected: state.tacticTheme === th }, themeLabel(th)); })));
      var levelSel = d.h("select.input", { id: "tac-level", onchange: function () { state.tacticEvidence = levelSel.value; paint(); } },
        [d.h("option", { value: "all", selected: state.tacticEvidence === "all" }, t("common.all"))].concat(levels.map(function (l) { return d.h("option", { value: l, selected: state.tacticEvidence === l }, t("vault.ev." + l)); })));
      paint();
      return d.h("section", { "aria-labelledby": "tac-h" },
        widgets.heading(2, t("vault.tactics"), t("vault.tacticsSub"), null, "tac-h"),
        d.h("div.tactic-filters", null, widgets.field(t("vault.themeFilter"), themeSel), widgets.field(t("vault.evidenceFilter"), levelSel), count),
        list);
    }

    // -- chest opening
    function openFlow() {
      if (openDialog) return;
      var p = ctx.profile();
      if (p.chestsReady < 1) return;
      var res = ctx.apply(game.openChest, loot);
      if (!res || !res.ok) { ctx.toast({ title: t("vault.noChest"), icon: "vault", tone: "info" }); return; }
      var reduced = ctx.reducedMotion();
      var r = res.rarity;
      var stage = d.h("div.chest-stage");
      var chestEl = d.h("div.stage-chest", { "aria-hidden": "true" }, icons.chest({ size: 190 }));
      var status = d.h("p.stage-status", { role: "status", "aria-live": "polite" }, t("vault.opening"));
      var flip = buildFlip(res);
      var actions = d.h("div.row.wrap.stage-actions");
      d.fill(stage, [chestEl, status, flip.el, actions]);
      var dlg = widgets.dialog({ title: t("vault.chestTitle"), body: stage, onClose: function () { openDialog = null; timers.forEach(clearTimeout); renderAll(); } });
      openDialog = dlg;
      dlg.el.classList.add("chest-dialog");

      function reveal() {
        d.fill(chestEl, icons.chest({ size: 190, open: true }));
        chestEl.classList.remove("is-shaking");
        chestEl.classList.add("is-open");
        flip.el.hidden = false;
        d.raf(function () { flip.el.classList.add("is-in"); });
        timers.push(setTimeout(function () { flip.el.classList.add("is-flipped"); }, reduced ? 0 : 420));
        var line = res.duplicate ? t("vault.dupe", { n: res.dust }) : t("vault.newCard");
        var pityLine = res.guaranteed ? t("vault.pityUsed") : (res.pity ? t("vault.pityNow", { n: res.pity, max: loot.pity_after || 8 }) : t("vault.pityReset"));
        status.textContent = rarityLabel(r) + ": " + cardTitle(res.card) + ". " + line;
        var left = ctx.profile().chestsReady;
        d.fill(actions, [
          d.h("p.small.stage-pity", null, pityLine),
          d.h("div.row.wrap", null,
            left > 0 ? d.h("button.btn.btn-primary", { type: "button", onclick: function () { dlg.close(); setTimeout(openFlow, 60); } }, t("vault.openAnother", { n: left })) : null,
            d.h("button.btn.btn-ghost", { type: "button", onclick: function () { dlg.close(); } }, t("common.close")))
        ]);
        ctx.sound(r === "legendary" ? "legendary" : r === "epic" ? "level" : "chest");
        if (CONFETTI_BY_RARITY[r]) timers.push(setTimeout(function () { ctx.confetti({ x: 0.5, y: 0.4, count: CONFETTI_BY_RARITY[r] }); }, reduced ? 0 : 500));
      }
      flip.el.hidden = true;
      if (reduced) { reveal(); }
      else {
        chestEl.classList.add("is-shaking");
        timers.push(setTimeout(reveal, 1100));
      }
    }

    function buildFlip(res) {
      var c = res.card, r = res.rarity;
      var face = d.h("div.flip-face.flip-front.loot-card.r-" + r + ".is-owned", null,
        d.h("span.loot-top", null, icons.gems(r, 14), d.h("span.loot-rarity", null, rarityLabel(r))),
        d.h("span.loot-kind", null, icons.icon(KIND_ICON[c.kind] || "bulb", { size: 16 }), d.h("span", null, kindLabel(c.kind))),
        d.h("strong.loot-title", null, cardTitle(c)),
        d.h("span.loot-body", null, ctx.pick(c, "body")),
        res.duplicate ? d.h("span.chip.tone-xp", null, t("vault.dupeChip", { n: res.dust })) : d.h("span.chip.tone-ok", null, icons.icon("star", { size: 13 }), d.h("span", null, t("common.new"))));
      var back = d.h("div.flip-face.flip-back", null, icons.icon("crown", { size: 56 }), d.h("span", null, t("app.name")));
      return { el: d.h("div.flip", { hidden: true }, d.h("div.flip-inner", null, back, face)), face: face };
    }

    function renderAll() {
      var dt = dropTable();
      d.fill(host, [
        d.h("div.chest-row", null, chestPanel(), dt),
        lootGrid(),
        tacticsSection()
      ]);
    }
    renderAll();
    return { destroy: function () { timers.forEach(clearTimeout); if (openDialog) { var dlg = openDialog; openDialog = null; dlg.close(); } } };
  }

  // ===== Studies ===========================================================================================
  function buildStudies(panel, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets;
    var t = d.t;
    var ui = root.DK.ui.claimsui;
    var vault = ctx.bundle.vault || {};
    var studies = (vault.studies || []).slice();
    var host = d.h("div.vault-studies");
    d.fill(panel, host);

    function authors(list) {
      if (!Array.isArray(list) || !list.length) return t("vault.unknownAuthors");
      var first = String(list[0]).split(",")[0];
      return list.length > 1 ? first + " " + t("vault.etAl") : first;
    }
    /** The topics a study is linked to, with names from the evidence tactics and the claim topics, and how it bears on each. */
    function linkNodes(id) {
      var links = ui.studyLinks(ctx.bundle, id, ctx.lang());
      if (!links.length) return null;
      return d.h("p.small.study-links", null, d.h("strong", null, t("vault.linkedTopics") + " "), links.map(function (l, i) {
        return d.h("span.study-link", null, i ? ", " : "", l.name, d.h("span.muted", null, " (" + t("vault.dir." + l.direction) + ")"));
      }));
    }

    function studyCard(s) {
      var verified = s.verified === true;
      var doi = s.doi ? String(s.doi) : null;
      return d.h("li", null, d.h("article.study", { "data-grade": s.grade || "" },
        d.h("div.study-head", null,
          d.h("span.grade-badge.grade-" + String(s.grade || "x").toLowerCase(), { title: t("vault.gradeHelp"), "aria-label": t("vault.grade", { g: s.grade || "?" }) }, s.grade || "?"),
          d.h("div.study-id", null,
            d.h("h3.study-title", null, s.title || s.id),
            d.h("p.small.muted", null, authors(s.authors) + (s.year ? ", " + s.year : "") + (s.venue ? ", " + s.venue : "")))),
        d.h("div.chip-row", null,
          d.h("span.chip", null, t("vault.design." + (DESIGNS.indexOf(s.design) >= 0 ? s.design : "unknown"))),
          verified ? d.h("span.chip.tone-ok", null, icons.icon("shieldCheck", { size: 13 }), d.h("span", null, t("vault.verified")))
                   : d.h("span.chip.tone-warn", null, icons.icon("alert", { size: 13 }), d.h("span", null, t("vault.unverified"))),
          s.retracted ? d.h("span.chip.tone-risk", null, t("vault.retracted")) : null,
          typeof s.cited_by === "number" ? d.h("span.chip", null, t("vault.cited", { n: d.fmt(s.cited_by) })) : null,
          s.peer_reviewed === true ? d.h("span.chip", null, t("vault.peer")) : (s.peer_reviewed === false ? d.h("span.chip", null, t("vault.notPeer")) : null)),
        s.verification_note ? d.h("p.small.muted", null, s.verification_note) : null,
        linkNodes(s.id),
        doi ? d.h("div.row.wrap.doi-row", null, d.h("code.doi", null, "doi:" + doi), widgets.copyButton(doi, t("vault.copyDoi"))) : null));
    }

    function render() {
      if (!studies.length) {
        d.fill(host, [widgets.emptyState({ icon: "book", title: t("vault.noStudies.title"), text: t("vault.noStudies.text") }), noteBox()]);
        return;
      }
      var seg = widgets.segmented({
        label: t("vault.filter"), active: state.studyFilter,
        items: [{ id: "all", label: t("common.all") }, { id: "verified", label: t("vault.verified") }, { id: "unverified", label: t("vault.unverified") }],
        onChange: function (id) { state.studyFilter = id; render(); }
      });
      var list = studies.filter(function (s) { return state.studyFilter === "all" || (state.studyFilter === "verified") === (s.verified === true); })
        .sort(function (a, b) { return String(a.grade || "Z").localeCompare(String(b.grade || "Z")) || (b.year || 0) - (a.year || 0); });
      var nVer = studies.filter(function (s) { return s.verified === true; }).length;
      d.fill(host, [
        noteBox(),
        d.h("div.row.wrap.studies-bar", null, seg.el, d.h("span.small.muted", null, t("vault.studyCount", { v: nVer, n: studies.length }))),
        list.length ? d.h("ul.study-list", null, list.map(studyCard)) : d.h("p.muted", null, t("vault.noMatch"))
      ]);
    }

    function noteBox() {
      return d.h("section.card.note-card", { role: "note" },
        d.h("h2.card-title", null, icons.icon("shield", { size: 20 }), t("vault.honestyTitle")),
        d.h("p", null, d.rich(t("vault.unverifiedNote"))),
        d.h("p.small.muted", null, t("vault.gradeNote")));
    }
    render();
    return { destroy: function () {} };
  }

  // ===== Claims map ==========================================================================================
  function buildClaims(panel, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets, ui = root.DK.ui.claimsui, game = root.DK.game;
    var t = d.t;
    var model = ui.claimsMap(ctx.bundle, ctx.lang());
    var host = d.h("div.vault-claims");
    d.fill(panel, host);
    if (!model || !model.total) {
      d.fill(host, widgets.emptyState({ icon: "shieldCheck", title: t("vault.claims.noTopics.title"), text: t("vault.claims.noTopics.text") }));
      return { destroy: function () {} };
    }
    var engine = ui.engine(ctx.bundle);
    var groupEls = {};
    var legendEl = null;

    /** Back to the class list: the page is long, so every group offers a way up. */
    function jumpLegend() {
      if (!legendEl) return;
      legendEl.scrollIntoView({ block: "start", behavior: ctx.reducedMotion() ? "auto" : "smooth" });
      var h = legendEl.querySelector("h3");
      if (h) { h.setAttribute("tabindex", "-1"); try { h.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
    }

    function jump(klass) {
      var el = groupEls[klass];
      if (!el) return;
      el.scrollIntoView({ block: "start", behavior: ctx.reducedMotion() ? "auto" : "smooth" });
      var h = el.querySelector("h3");
      if (h) { h.setAttribute("tabindex", "-1"); try { h.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
    }

    // -- class legend: five classes with icon and meaning, each a button that jumps to its topics
    function legendSection() {
      var items = model.legend.map(function (g) {
        var meta = ui.CLASS_META[g.klass];
        var n = g.topics.length;
        var meaningId = "claims-meaning-" + g.klass;
        var body = [
          d.h("span.legend-head", null, icons.icon(meta.icon, { size: 18 }), d.h("strong", null, t("claims.class." + g.klass)), d.h("span.chip.tone-" + meta.tone, null, String(n))),
          d.h("span.small.muted.legend-meaning", { id: meaningId }, g.meaning)
        ];
        return d.h("li", null, n
          ? d.h("button.legend-class.class-" + g.klass, { type: "button", "aria-describedby": meaningId, onclick: function () { jump(g.klass); } }, body)
          : d.h("div.legend-class.class-" + g.klass, null, body));
      });
      legendEl = d.h("section.card.claims-legend", { "aria-labelledby": "claims-legend-h" },
        d.h("h3.card-title", { id: "claims-legend-h" }, t("vault.claims.legendTitle")),
        d.h("p.small.muted", null, t("vault.claims.legendHint")),
        d.h("ul.class-legend", null, items));
      return legendEl;
    }

    function regNote() {
      if (!model.note) return null;
      return d.h("section.card.note-card.reg-note", { role: "note", "aria-labelledby": "claims-reg-h" },
        d.h("div.editor-head", null,
          d.h("h3.card-title", { id: "claims-reg-h" }, icons.icon("scale", { size: 20 }), d.h("span", null, t("vault.claims.regTitle"))),
          d.h("span.chip.tone-warn.legal-chip", null, icons.icon("info", { size: 13 }), d.h("span", null, t("vault.claims.notLegal")))),
        d.h("p", null, model.note));
    }

    // -- check your own text: the same checker as in the Boss Battle, on pasted copy, in this page only
    function checker() {
      if (!engine) return null;
      var max = ui.CHECK_MAX_CHARS;
      var input = d.h("textarea.input.claims-input", {
        id: "claims-check-input", rows: 5, maxlength: String(max), spellcheck: "true", "aria-describedby": "claims-check-count claims-check-privacy",
        placeholder: t("vault.check.placeholder")
      });
      input.value = state.checkText || "";
      var count = d.h("span.small.muted", { id: "claims-check-count" }, "");
      var out = d.h("div.claims-result");
      var statusEl = d.h("div.claims-status.is-idle", { role: "status" });

      function updateCount() { count.textContent = t("vault.check.count", { c: Array.from(input.value).length, max: max }); }
      function drawEmpty(msg) {
        d.fill(out, d.h("p.small.muted.claims-empty", null, icons.icon("info", { size: 16 }), d.h("span", null, msg || t("vault.check.empty"))));
      }
      function draw(report) {
        statusEl.removeAttribute("data-key");
        var st = ui.fillStatus(statusEl, report);
        d.fill(out, [
          d.h("h4.sub", null, t("vault.check.resultTitle")),
          statusEl,
          report.findings.length ? ui.findingList(report.findings) : d.h("p.small.claims-clean", null, t("claims.okText")),
          d.h("p.small.muted", null, t("claims.heuristic"))
        ]);
        d.announce(ui.statusText(st));
      }
      function run() {
        state.checkText = input.value;
        if (!input.value.trim()) {
          drawEmpty(t("vault.check.needText"));
          d.announce(t("vault.check.needText"));
          input.focus();
          return;
        }
        draw(ui.check(engine, input.value, ctx.lang()));
      }
      input.addEventListener("input", function () { state.checkText = input.value; updateCount(); });
      input.addEventListener("keydown", function (e) { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(); } });
      updateCount();
      if (input.value.trim()) draw(ui.check(engine, input.value, ctx.lang())); else drawEmpty();

      return d.h("section.card.claims-check", { "aria-labelledby": "claims-check-h" },
        d.h("h3.card-title", { id: "claims-check-h" }, icons.icon("pencil", { size: 20 }), d.h("span", null, t("vault.check.title"))),
        d.h("p.small", null, t("vault.check.lead")),
        widgets.field(t("vault.check.label"), input),
        d.h("div.row.wrap.claims-check-bar", null,
          d.h("button.btn.btn-primary", { type: "button", onclick: function () { run(); } }, icons.icon("shieldCheck", { size: 18 }), d.h("span", null, t("vault.check.run"))),
          d.h("button.btn.btn-ghost", { type: "button", onclick: function () { input.value = t("vault.check.exampleText"); updateCount(); run(); } }, d.h("span", null, t("vault.check.example"))),
          d.h("button.btn.btn-ghost", { type: "button", onclick: function () { input.value = ""; state.checkText = ""; updateCount(); drawEmpty(); input.focus(); } }, d.h("span", null, t("vault.check.clear"))),
          count),
        out,
        d.h("p.small.muted", { id: "claims-check-privacy" }, icons.icon("lock", { size: 14 }), " ", t("vault.check.privacy")));
    }

    // -- one claim topic
    function studyRow(s) {
      return d.h("li.claim-study" + (s.verified ? "" : ".is-unverified"), null,
        d.h("span.study-line", null, d.h("span.study-name", null, s.title), s.year ? d.h("span.muted", null, " (" + s.year + ")") : null),
        s.verified
          ? d.h("span.chip.tone-ok", null, icons.icon("shieldCheck", { size: 13 }), d.h("span", null, t("vault.verified")))
          : d.h("span.chip.tone-warn", null, icons.icon("alert", { size: 13 }), d.h("span", null, t("vault.unverified"))));
    }

    function bulletList(items, icon, cls) {
      return d.h("ul.claim-list." + cls, null, items.map(function (x) { return d.h("li", null, icons.icon(icon, { size: 15 }), d.h("span", null, x)); }));
    }

    function topicCard(tp) {
      var nameId = "claim-" + tp.id;
      var chips = [ui.classChip(tp.klass), ui.evidenceChip(tp.label)];
      if (tp.grade) chips.push(d.h("span.chip.grade-" + String(tp.grade).toLowerCase(), null, t("vault.grade", { g: tp.grade })));
      var countChips = [tp.nVerified > 0
        ? d.h("span.chip.tone-ok", null, icons.icon("shieldCheck", { size: 13 }), d.h("span", null, ctx.tp("vault.claims.verified", tp.nVerified)))
        : d.h("span.chip", null, icons.icon("shield", { size: 13 }), d.h("span", null, ctx.tp("vault.claims.verified", tp.nVerified)))];
      if (tp.nPending > 0) countChips.push(d.h("span.chip.tone-warn", null, icons.icon("alert", { size: 13 }), d.h("span", null, ctx.tp("vault.claims.pending", tp.nPending))));
      var more = d.h("details.claim-more", null,
        d.h("summary", null, d.h("span", null, t("vault.claims.more")), icons.icon("chevronDown", { size: 16, class: "chev" })),
        tp.caveats.length ? d.h("div", null, d.h("h5.sub", null, t("vault.caveats")),
          d.h("ul.reason-list", null, tp.caveats.map(function (c) { return d.h("li", null, icons.icon("alert", { size: 14 }), d.h("span", null, c)); }))) : null,
        d.h("div", null, d.h("h5.sub", null, t("vault.claims.studies")),
          tp.studies.length ? d.h("ul.claim-studies", null, tp.studies.map(studyRow)) : d.h("p.small.muted", null, t("vault.claims.noLinked"))));
      more.addEventListener("toggle", function () { if (more.open) ctx.apply(game.applyVaultOpen, null); });
      return d.h("li", null, d.h("article.claim-card.klass-" + tp.klass + (tp.blocked ? ".is-blocked" : ""), { "aria-labelledby": nameId, "data-topic": tp.id },
        d.h("div.claim-head", null,
          d.h("h4.claim-name", { id: nameId }, tp.name),
          tp.blocked ? ui.blockedBadge() : null),
        d.h("div.chip-row", null, chips),
        tp.claim ? d.h("p.claim-sentence", null, d.h("span.finding-label", null, t("vault.claims.claim")), " ", d.quote(tp.claim)) : null,
        tp.capped ? d.h("div.callout.cap-box", null, icons.icon("scale", { size: 20 }),
          d.h("div", null, d.h("strong", null, t("vault.claims.capped")),
            d.h("p.small", null, t("vault.claims.cappedLine", { from: t("vault.ev." + tp.computedLabel), to: t("vault.ev." + tp.label) })),
            tp.capReason ? d.h("p.small", null, tp.capReason) : null)) : null,
        d.h("div.chip-row.claim-counts", null, countChips),
        tp.summary ? d.h("div.claim-summary", null, d.h("h5.sub", null, t("vault.claims.summary")), d.h("p", null, tp.summary), tp.headline ? d.h("p.small.muted", null, tp.headline) : null) : null,
        d.h("div.claim-lists", null,
          tp.safe.length ? d.h("div.safe-box", null, d.h("h5.sub", null, icons.icon("check", { size: 15, stroke: 2.6 }), d.h("span", null, t("claims.safer"))), bulletList(tp.safe, "check", "safe-list")) : null,
          tp.avoid.length ? d.h("div.avoid-box", null, d.h("h5.sub", null, icons.icon("x", { size: 15, stroke: 2.6 }), d.h("span", null, t("vault.claims.avoid"))), bulletList(tp.avoid, "x", "avoid-list")) : null),
        more));
    }

    function groupSection(g) {
      var meta = ui.CLASS_META[g.klass] || ui.CLASS_META.context;
      var hid = "claims-group-" + g.klass;
      var el = d.h("section.claim-group.klass-" + g.klass, { "aria-labelledby": hid },
        d.h("div.claim-group-head", null,
          d.h("h3.claim-group-title", { id: hid }, icons.icon(meta.icon, { size: 20 }),
            d.h("span", null, ui.CLASS_META[g.klass] ? t("claims.class." + g.klass) : String(g.klass)),
            d.h("span.chip.tone-" + meta.tone, null, ctx.tp("vault.claims.topics", g.topics.length))),
          d.h("div.claim-group-tools", null,
            g.blocked ? ui.blockedBadge() : null,
            d.h("button.btn.btn-ghost.btn-sm.to-legend", { type: "button", onclick: function () { jumpLegend(); } }, icons.icon("chevronUp", { size: 16 }), d.h("span", null, t("vault.claims.toLegend"))))),
        g.meaning ? d.h("p.small.muted", null, g.meaning) : null,
        d.h("ul.claim-grid", null, g.topics.map(topicCard)));
      groupEls[g.klass] = el;
      return el;
    }

    d.fill(host, [
      widgets.heading(2, t("vault.claims.title"), t("vault.claims.lead")),
      legendSection(),
      regNote(),
      checker(),
      model.groups.map(groupSection)
    ]);
    if (state.focusCheck) {
      state.focusCheck = false;
      d.raf(function () {
        var el = host.querySelector("#claims-check-input");
        if (!el) return;
        try { el.scrollIntoView({ block: "center", behavior: "auto" }); el.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
      });
    }
    return { destroy: function () { groupEls = {}; } };
  }

  // ===== Myth or Fact =========================================================================================
  function buildMyths(panel, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets, game = root.DK.game;
    var t = d.t;
    var myths = ctx.bundle.myths || [];
    var st = state.myth;
    var host = d.h("div.vault-myths");
    d.fill(panel, host);
    var alive = true;
    var cardEl = null;

    if (!myths.length) {
      d.fill(host, widgets.emptyState({ icon: "bulb", title: t("vault.noMyths.title"), text: t("vault.noMyths.text") }));
      return { destroy: function () {} };
    }

    function nextMyth() {
      st.current = game.pickMyth(myths, { seen: ctx.profile().mythsSeen, avoid: st.current ? st.current.id : null, rng: ctx.rng });
      st.answered = null;
    }
    if (!st.current || !myths.some(function (m) { return m.id === st.current.id; })) nextMyth();

    function statement(m) { return m[ctx.lang()] || m.en; }

    function answer(choice) {
      if (st.answered) return;
      var m = st.current;
      var res = ctx.apply(game.answerMyth, { myth: m, answer: choice });
      st.answered = { choice: choice, correct: res.correct, xp: res.xp };
      st.played += 1;
      st.correctRun = res.correct ? st.correctRun + 1 : 0;
      ctx.sound(res.correct ? "correct" : "wrong");
      d.announce((res.correct ? t("vault.myth.right") : t("vault.myth.wrong")) + " " + t("vault.myth.answerWas", { a: t(m.answer === "myth" ? "vault.myth.isMyth" : "vault.myth.isFact") }));
      render(true);
    }

    function swipeCard(m) {
      var stampL = d.h("span.stamp.stamp-myth", { "aria-hidden": "true" }, t("vault.myth.myth"));
      var stampR = d.h("span.stamp.stamp-fact", { "aria-hidden": "true" }, t("vault.myth.fact"));
      var el = d.h("div.myth-card", { "data-id": m.id },
        stampL, stampR,
        d.h("span.eyebrow", null, t("vault.myth.prompt")),
        d.h("p.myth-text", null, statement(m)));
      var startX = null, dx = 0;
      el.addEventListener("pointerdown", function (e) {
        if (st.answered || (e.pointerType === "mouse" && e.button !== 0)) return;
        startX = e.clientX; dx = 0;
        try { el.setPointerCapture(e.pointerId); } catch (err) { /* ignore */ }
        el.classList.add("is-drag");
      });
      el.addEventListener("pointermove", function (e) {
        if (startX === null) return;
        dx = e.clientX - startX;
        el.style.transform = "translateX(" + dx + "px) rotate(" + (dx / 24) + "deg)";
        stampL.style.opacity = String(Math.min(1, Math.max(0, -dx / 90)));
        stampR.style.opacity = String(Math.min(1, Math.max(0, dx / 90)));
      });
      function end() {
        if (startX === null) return;
        var moved = dx;
        startX = null;
        el.classList.remove("is-drag");
        if (Math.abs(moved) > 90) answer(moved < 0 ? "myth" : "fact");
        else { el.style.transform = ""; stampL.style.opacity = "0"; stampR.style.opacity = "0"; }
      }
      el.addEventListener("pointerup", end);
      el.addEventListener("pointercancel", end);
      return el;
    }

    function explanation(m) {
      var a = st.answered;
      return d.h("section.card.myth-result" + (a.correct ? ".is-right" : ".is-wrong"), { tabindex: "-1", id: "myth-result" },
        d.h("div.result-head", null,
          d.h("span.result-icon", { "aria-hidden": "true" }, icons.icon(a.correct ? "check" : "heart", { size: 26, stroke: 2.4 })),
          d.h("h2.result-title", null, a.correct ? t("vault.myth.right") : t("vault.myth.wrong")),
          d.h("strong.xp-gain", null, "+" + a.xp + " XP")),
        d.h("p", null, d.h("strong", null, t("vault.myth.answerWas", { a: t(m.answer === "myth" ? "vault.myth.isMyth" : "vault.myth.isFact") }))),
        d.h("div", null, d.h("h3.sub", null, t("vault.myth.why")), d.h("p", null, ctx.pick(m, "why"))),
        m.ref ? d.h("p.small.ref", null, icons.icon("book", { size: 15 }), d.h("span", null, d.h("strong", null, t("vault.myth.ref") + " "), m.ref)) : null,
        d.h("p.small.muted", null, t("vault.myth.caveat")),
        d.h("div.row.wrap", null,
          d.h("button.btn.btn-primary", { type: "button", onclick: function () { nextMyth(); render(false); var b = host.querySelector(".myth-btn"); if (b) b.focus({ preventScroll: true }); } }, t("vault.myth.next"), icons.icon("arrowRight", { size: 18 })),
          d.h("span.small.muted", null, d.kbd("Enter"))));
    }

    function render(afterAnswer) {
      var m = st.current;
      var p = ctx.profile();
      var seen = myths.filter(function (x) { return p.mythsSeen.indexOf(x.id) >= 0; }).length;
      cardEl = swipeCard(m);
      var answered = !!st.answered;
      if (answered) {
        cardEl.classList.add("is-answered");
        cardEl.classList.add(st.answered.correct ? "is-right" : "is-wrong");
      }
      d.fill(host, [
        d.h("div.row.wrap.myth-stats", null,
          d.h("span.chip.tone-brand", null, t("vault.myth.progress", { a: seen, b: myths.length })),
          d.h("span.chip", null, t("vault.myth.run", { n: st.correctRun })),
          d.h("span.small.muted", null, t("vault.myth.xpHint", { r: game.XP.mythRight, w: game.XP.mythWrong }))),
        cardEl,
        d.h("div.myth-buttons", null,
          d.h("button.btn.btn-ghost.btn-lg.myth-btn.myth-btn-myth", { type: "button", disabled: answered, onclick: function () { answer("myth"); } }, icons.icon("chevronLeft", { size: 20 }), d.h("span", null, t("vault.myth.myth"))),
          d.h("button.btn.btn-ghost.btn-lg.myth-btn.myth-btn-fact", { type: "button", disabled: answered, onclick: function () { answer("fact"); } }, d.h("span", null, t("vault.myth.fact")), icons.icon("chevronRight", { size: 20 }))),
        d.h("p.small.muted.key-help", null, t("vault.myth.keys")),
        answered ? explanation(m) : null
      ]);
      if (afterAnswer) {
        var res = host.querySelector("#myth-result");
        if (res) { try { res.focus({ preventScroll: true }); } catch (e) { /* ignore */ } res.scrollIntoView({ block: "nearest", behavior: ctx.reducedMotion() ? "auto" : "smooth" }); }
      }
    }

    function onKey(e) {
      if (!alive || e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented || d.isFormField(e.target)) return;
      if (document.querySelector("dialog[open]")) return;
      if (!st.answered) {
        if (e.key === "ArrowLeft" || e.key === "m" || e.key === "M") { e.preventDefault(); answer("myth"); }
        else if (e.key === "ArrowRight" || e.key === "f" || e.key === "F") { e.preventDefault(); answer("fact"); }
      } else if (e.key === "Enter" && !(e.target.closest && e.target.closest("button, a, summary"))) {
        e.preventDefault(); nextMyth(); render(false);
      }
    }
    root.document.addEventListener("keydown", onKey);
    render(false);
    return { destroy: function () { alive = false; root.document.removeEventListener("keydown", onKey); } };
  }

  return { mount: mount, _state: state };
});
