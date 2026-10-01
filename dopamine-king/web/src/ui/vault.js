/* Vault: evidence cards, studies and the Myth or Fact quiz.
 *  Cards: chests with PUBLISHED drop rates and a visible pity counter, the loot collection with rarity
 *         frames (locked silhouettes until owned), and the evidence tactics from the research ledger.
 *  Studies: the ledger with grade, design, year, venue and a verified flag (seed entries are unverified).
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
  var EVIDENCE_LEVEL = { strong: 4, moderate: 3, limited: 2, contested: 2, none: 0 };
  var CONFETTI_BY_RARITY = { common: 0, rare: 70, epic: 130, legendary: 230 };

  var state = { tab: "cards", studyFilter: "all", myth: { current: null, answered: null, correctRun: 0, played: 0 } };

  function rarityOf(card) { return RARITIES.indexOf(card.rarity) >= 0 ? card.rarity : "common"; }

  function mount(container, ctx, route) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets;
    var t = d.t;
    var sub = (route && route.sub) || (route && route.params && route.params.tab) || null;
    if (sub === "cards" || sub === "studies" || sub === "myths") state.tab = sub;
    var page = d.h("div.page.vault");
    var current = null;
    var builders = { cards: buildCards, studies: buildStudies, myths: buildMyths };
    var tabs = widgets.tabs({
      label: t("vault.tabs"), active: state.tab,
      items: [{ id: "cards", label: t("vault.tab.cards"), icon: "gem" }, { id: "studies", label: t("vault.tab.studies"), icon: "book" }, { id: "myths", label: t("vault.tab.myths"), icon: "bulb" }],
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
        d.h("p.page-lead", null, t("vault.lead"))),
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
          d.h("span.loot-lock", null, icons.icon("lock", { size: 28 })),
          d.h("span.loot-title", null, t("vault.locked")),
          d.h("span.loot-kind", null, kindLabel(c.kind))));
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
      var sorted = cards.slice().sort(function (a, b) { return RARITIES.indexOf(rarityOf(b)) - RARITIES.indexOf(rarityOf(a)); });
      var ownedN = cards.filter(function (c) { return p.deck.indexOf(c.id) >= 0; }).length;
      if (!cards.length) return widgets.emptyState({ icon: "gem", title: t("vault.noCards.title"), text: t("vault.noCards.text") });
      return d.h("section", { "aria-labelledby": "loot-h" },
        widgets.heading(2, t("vault.collection"), t("vault.collectionSub"), d.h("span.chip.tone-brand", null, t("common.of", { a: ownedN, b: cards.length }))),
        charts.meter({ value: ownedN, max: Math.max(1, cards.length), size: "sm", tone: "brand", label: t("vault.collection"), valueText: function () { return ownedN + " / " + cards.length; } }),
        d.h("ul.loot-grid", null, sorted.map(lootCard)));
    }

    // -- evidence tactics
    function evidenceChip(label) {
      var lv = EVIDENCE_LEVEL[label];
      if (lv === undefined) label = "none";
      var segs = d.h("span.ev-segs", { "aria-hidden": "true" });
      for (var i = 1; i <= 4; i++) segs.appendChild(d.h("i" + (i <= (EVIDENCE_LEVEL[label] || 0) ? ".on" : "")));
      return d.h("span.chip.ev-" + label, null, segs, label === "contested" ? icons.icon("alert", { size: 13 }) : null, d.h("span", null, t("vault.ev." + label)));
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
          tc.driver ? d.h("span.chip.tone-info", null, tc.driver) : null,
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
      return d.h("section", { "aria-labelledby": "tac-h" },
        widgets.heading(2, t("vault.tactics"), t("vault.tacticsSub")),
        d.h("ul.tactic-grid", null, tactics.map(tacticCard)));
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
    var vault = ctx.bundle.vault || {};
    var studies = (vault.studies || []).slice();
    var links = vault.links || [];
    var tactics = {};
    (vault.tactics || []).forEach(function (x) { tactics[x.id] = x; });
    var host = d.h("div.vault-studies");
    d.fill(panel, host);

    function authors(list) {
      if (!Array.isArray(list) || !list.length) return t("vault.unknownAuthors");
      var first = String(list[0]).split(",")[0];
      return list.length > 1 ? first + " " + t("vault.etAl") : first;
    }
    function usedBy(id) {
      return links.filter(function (l) { return l.study_id === id; }).map(function (l) { return tactics[l.tactic_id] ? (ctx.pick(tactics[l.tactic_id], "name") || l.tactic_id) : l.tactic_id; })
        .filter(function (x, i, arr) { return arr.indexOf(x) === i; });
    }

    function studyCard(s) {
      var verified = s.verified === true;
      var tacticNames = usedBy(s.id);
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
        tacticNames.length ? d.h("p.small", null, d.h("strong", null, t("vault.usedBy") + " "), tacticNames.join(", ")) : null,
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
        d.h("p", null, t("vault.unverifiedNote")),
        d.h("p.small.muted", null, t("vault.gradeNote")));
    }
    render();
    return { destroy: function () {} };
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
