/* Arena: duels with an answer that was measured or computed from real material. Two results, pick one, optionally with
 * a confidence level; the reveal shows what the stored data says and links to the real pages.
 *
 * Kinds of duel (duel.kind):
 *   rank   which of two results of one stored web search was placed higher (the Dopamine Score of the titles is the "model")
 *   reach  which of two sites showed up in more of the market searches
 *   claim  which of two real page titles the claims check would stop
 *   hook   the old edition on a simulated corpus: which hook got the higher success index (labelled SIMULATED)
 *
 * Fully playable by keyboard: A or Left for the first card, B or Right for the second, Enter for the next duel.
 * The verdict replaces the prompt above the cards, so the "Next duel" button always sits in the same place.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.arena = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var PLATFORMS = ["blog", "newsroom", "youtube", "instagram", "tiktok", "x", "linkedin", "facebook", "threads", "reddit", "email", "ad", "podcast", "web", "other"];
  var DIFFS = ["easy", "medium", "hard"];
  var KINDS = ["rank", "reach", "claim", "hook"];
  var SITE_TYPES = ["maker", "media", "pharmacy", "ecommerce", "service", "forum", "foreign_media", "foreign_shop", "science", "reviews", "authority"];

  // Survives navigation and language changes within a session.
  var state = {
    duel: null, picked: null, revealed: false, result: null, confidenceOn: false, confidence: 70,
    difficulty: "all", kind: "all", preferLang: true, round: 0, sessionPlayed: 0, sessionCorrect: 0, cycled: false
  };

  function platformLabel(id, t) {
    return PLATFORMS.indexOf(id) >= 0 ? t("platform." + id) : String(id || "");
  }

  function kindOf(duel) { return KINDS.indexOf(duel.kind) >= 0 ? duel.kind : "hook"; }
  function typeLabel(type, t) { return SITE_TYPES.indexOf(type) >= 0 ? t("type." + type) : ""; }

  function mount(container, ctx, route) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets, game = root.DK.game;
    var t = d.t;
    var claimsui = root.DK.ui.claimsui;
    var arena = ctx.bundle.arena || [];
    var real = (ctx.bundle.meta && ctx.bundle.meta.real) || null;
    var engine = claimsui.engine(ctx.bundle);
    var page = d.h("div.page.arena");
    container.appendChild(page);
    var timers = [];
    var tweens = [];
    var alive = true;
    var filtersOpen = false;

    var kindsPresent = KINDS.filter(function (k) { return arena.some(function (x) { return kindOf(x) === k; }); });

    if (route && route.params) {
      if (DIFFS.indexOf(route.params.difficulty) >= 0 && state.difficulty !== route.params.difficulty) {
        state.difficulty = route.params.difficulty;
        if (!state.revealed) state.duel = null;
      }
      if (kindsPresent.indexOf(route.params.kind) >= 0 && state.kind !== route.params.kind) {
        state.kind = route.params.kind;
        if (!state.revealed) state.duel = null;
      }
    }
    if (state.kind !== "all" && kindsPresent.indexOf(state.kind) < 0) state.kind = "all";

    function cohortName(id) {
      var c = ctx.bundle.cohort_labels && ctx.bundle.cohort_labels[id];
      return c ? c[ctx.lang()] || c.en || id : id;
    }

    function queryText(recordId) {
      var qs = (ctx.bundle.market && ctx.bundle.market.queries) || [];
      for (var i = 0; i < qs.length; i++) if (qs[i].id === recordId) return qs[i].query;
      return recordId;
    }

    function nextDuel() {
      var p = ctx.profile();
      var res = game.pickDuel(arena, {
        seen: p.arenaSeen, lang: ctx.lang(), preferLang: state.preferLang, difficulty: state.difficulty, kind: state.kind,
        rng: ctx.rng, avoid: state.duel ? state.duel.id : null
      });
      state.duel = res.duel;
      state.cycled = res.cycled;
      state.picked = null;
      state.revealed = false;
      state.result = null;
      state.round += 1;
    }

    // -- pieces --------------------------------------------------------------------------------------
    function diffChip(diff) {
      var n = DIFFS.indexOf(diff) + 1;
      var dots = d.h("span.dots", { "aria-hidden": "true" });
      for (var i = 0; i < 3; i++) dots.appendChild(d.h("i" + (i < n ? ".on" : "")));
      return d.h("span.chip.diff-" + diff, null, dots, d.h("span", null, t("arena." + diff)));
    }

    // Confidence sits right above the cards because it has to be chosen before the pick.
    function confidenceRow() {
      var confSlider = widgets.slider({
        label: t("arena.confValue"), min: 50, max: 100, step: 5, value: state.confidence,
        format: function (v) { return v + " %"; }, onInput: function (v) { state.confidence = v; }
      });
      var sliderHost = d.h("div.conf-slider", { hidden: !state.confidenceOn }, confSlider.el);
      var hint = d.h("p.small.muted.conf-hint", { hidden: state.confidenceOn }, t("arena.confShort"));
      var help = d.h("p.small.muted.conf-help", { hidden: !state.confidenceOn }, t("arena.confHint"));
      var confSw = widgets.switchControl({
        label: t("arena.confidence"), checked: state.confidenceOn,
        onChange: function (on) { state.confidenceOn = on; sliderHost.hidden = !on; hint.hidden = on; help.hidden = !on; }
      });
      return d.h("div.conf-row", null, d.h("div.conf-switch", null, confSw.el, hint), sliderHost, help);
    }

    function kindPicker() {
      if (kindsPresent.length < 2) return null;
      var seg = widgets.segmented({
        label: t("arena.kind.label"), active: state.kind,
        items: [{ id: "all", label: t("arena.kind.all") }].concat(kindsPresent.map(function (k) { return { id: k, label: t("arena.kind." + k) }; })),
        onChange: function (id) {
          state.kind = id;
          if (!state.revealed) { nextDuel(); render(); }
        }
      });
      return d.h("div.kind-picker", null, seg.el);
    }

    function filtersCard() {
      var diffSeg = widgets.segmented({
        label: t("arena.difficulty"), active: state.difficulty,
        items: [{ id: "all", label: t("common.all") }].concat(DIFFS.map(function (k) { return { id: k, label: t("arena." + k) }; })),
        onChange: function (id) {
          state.difficulty = id;
          if (!state.revealed) { nextDuel(); render(); }
        }
      });
      var langSw = widgets.switchControl({
        label: t("arena.preferLang"), checked: state.preferLang,
        onChange: function (on) { state.preferLang = on; if (!state.revealed) { nextDuel(); render(); } }
      });
      var det = d.h("details.card.arena-filters-card", { open: filtersOpen },
        d.h("summary", null, icons.icon("settings", { size: 18 }), d.h("span", null, t("arena.controls")), icons.icon("chevronDown", { size: 18, class: "chev" })),
        d.h("div.arena-filters", null,
          d.h("div.setting", null, d.h("span.setting-label", null, t("arena.difficulty")), diffSeg.el),
          langSw.el));
      det.addEventListener("toggle", function () { filtersOpen = det.open; });
      return det;
    }

    function statsStrip() {
      var p = ctx.profile();
      var mult = game.comboMultiplier(p.combo);
      var toNext = mult >= game.XP.comboMax ? 0 : game.XP.comboStep - (p.combo % game.XP.comboStep);
      var oracle = game.oracleRating(p.brier);
      var comboMeter = charts.meter({
        value: mult >= game.XP.comboMax ? 100 : (p.combo % game.XP.comboStep) / game.XP.comboStep * 100, max: 100, size: "sm", tone: "xp",
        label: t("arena.combo"), valueText: function () { return t("arena.comboRow", { n: p.combo }); }
      });
      return d.h("section.arena-stats", { "aria-label": t("arena.stats") },
        d.h("div.stat-chip.combo-chip" + (mult > 1 ? ".is-hot" : ""), null,
          d.h("span.combo-x", { id: "combo-x" }, "x" + mult),
          d.h("div.combo-body", null,
            d.h("strong", null, t("arena.combo") + ": " + t("arena.comboRow", { n: p.combo })),
            comboMeter,
            d.h("span.small.muted", null, mult >= game.XP.comboMax ? t("arena.comboMax") : t("arena.comboNext", { n: toNext, m: mult + 1 })))),
        d.h("div.stat-chip", null, d.h("span.stat-val", null, String(state.round)), d.h("span.stat-label", null, t("arena.round", { n: state.round }))),
        d.h("div.stat-chip", null, d.h("span.stat-val", null, state.sessionCorrect + "/" + state.sessionPlayed), d.h("span.stat-label", null, t("arena.session"))),
        d.h("div.stat-chip", null, d.h("span.stat-val", null, oracle === null ? "?" : String(Math.round(oracle))), d.h("span.stat-label", null, t("arena.oracle"))));
    }

    function typeChip(type) {
      var label = typeLabel(type, t);
      return label ? d.h("span.chip.tone-info.type-chip", null, d.h("span", null, label)) : null;
    }

    function hookCard(side, hook, duel) {
      var kind = kindOf(duel);
      var letter = side.toUpperCase();
      var body = [
        d.h("span.hook-top", null, d.h("span.hook-letter", { "aria-hidden": "true" }, letter), d.h("span.hook-brand", null, hook.brand || ""), typeChip(hook.host_type)),
        d.h("span.hook-text", null, kind === "claim" || kind === "rank" ? d.typo(hook.text) : hook.text)
      ];
      if (kind === "reach" && hook.example) body.push(d.h("span.hook-example", null, d.quote(hook.example)));
      body.push(d.h("span.hook-key", { "aria-hidden": "true" }, d.kbd(letter), d.h("span", null, " / "), d.kbd(side === "a" ? "←" : "→")));
      var btn = d.h("button.hook-card", {
        type: "button", "data-side": side, "aria-label": t("arena.pick", { side: letter }) + ": " + hook.text,
        onclick: function () { pick(side); }
      }, body);
      return d.h("article.hook-wrap", { "data-side": side }, btn, d.h("div.hook-reveal", { hidden: true }));
    }

    function snapshotDate(duel) {
      return d.fmtDate(duel.retrieved_at || (real && real.snapshot) || "");
    }

    function promptQuestion(duel) {
      var kind = kindOf(duel);
      if (kind === "rank") return t("arena.q.rank", { query: duel.query });
      if (kind === "reach") return t("arena.q.reach", { n: duel.a.of });
      if (kind === "claim") return t("arena.q.claim");
      return t("arena.prompt");
    }

    function promptPanel(duel) {
      var kind = kindOf(duel);
      var chips = [];
      if (kind === "hook") {
        chips.push(d.h("span.chip.tone-info", null, icons.icon("layers", { size: 14 }), d.h("span", null, cohortName(duel.cohort))));
        chips.push(d.h("span.chip", null, platformLabel(duel.platform, t)));
        chips.push(d.h("span.chip", null, duel.lang === "cs" ? t("arena.langCs") : t("arena.langEn")));
      } else {
        chips.push(d.h("span.chip.tone-ok", null, icons.icon("shieldCheck", { size: 14 }), d.h("span", null, t("arena.real.source", { date: snapshotDate(duel) }))));
        chips.push(d.h("span.chip", null, t("arena.kind." + kind)));
      }
      chips.push(diffChip(duel.difficulty));
      return d.h("div.duel-prompt", null, d.h("h2.duel-q", { id: "duel-q" }, d.typo(promptQuestion(duel))), d.h("div.duel-meta", null, chips), confidenceRow());
    }

    // -- reveal ----------------------------------------------------------------------------------------
    function placeBlock(hook, isWinner, extra) {
      var m = charts.meter({ value: 0, max: 100, tone: isWinner ? "ok" : "brand", label: t("arena.place") + " " + extra, valueText: function () { return t("arena.placeOf", { n: hook.rank, of: hook.of }); } });
      d.raf(function () { m.set(hook.success); });
      return [
        d.h("div.reveal-line", null, d.h("span.reveal-label", null, t("arena.place")), d.h("strong.num", null, t("arena.placeOf", { n: hook.rank, of: hook.of }))),
        m,
        d.h("div.reveal-line.score-line", null, d.h("span.reveal-label", null, t("arena.score")), d.h("strong.num", null, d.fmt(hook.score, 1)))
      ];
    }

    function reachBlock(hook, duel, isWinner) {
      var max = Math.max(duel.a.count, duel.b.count);
      var m = charts.meter({ value: 0, max: max, tone: isWinner ? "ok" : "brand", label: t("arena.reach"), valueText: function () { return t("arena.appeared", { n: hook.count, of: hook.of }); } });
      d.raf(function () { m.set(hook.count); });
      var queries = (hook.searches || []).slice(0, 8).map(function (id) { return d.h("li", null, queryText(id)); });
      return [
        d.h("div.reveal-line", null, d.h("span.reveal-label", null, t("arena.reach")), d.h("strong.num", null, t("arena.appeared", { n: hook.count, of: hook.of }))),
        m,
        queries.length ? d.h("details.reach-where", null, d.h("summary", null, t("arena.reachWhere")), d.h("ul.plain", null, queries)) : null
      ];
    }

    function claimBlock(hook) {
      var report = engine ? claimsui.check(engine, hook.text, ctx.lang()) : null;
      var findings = report ? report.findings : (hook.findings || []);
      var items = report ? findings : [];
      return [
        d.h("div.reveal-line", null, hook.flagged
          ? d.h("span.chip.tone-risk", null, icons.icon("ban", { size: 14, stroke: 2.4 }), d.h("span", null, t("arena.stopped")))
          : d.h("span.chip.tone-ok", null, icons.icon("shieldCheck", { size: 14 }), d.h("span", null, t("arena.clean")))),
        items.length ? claimsui.findingList(items.slice(0, 3)) : (findings.length ? d.h("p.small.muted", null, findings.map(function (f) { return f.code; }).join(", ")) : null)
      ];
    }

    function fillReveal(wrap, side, duel) {
      var hook = duel[side];
      var kind = kindOf(duel);
      var box = wrap.querySelector(".hook-reveal");
      var isWinner = duel.winner === side;
      var badges = d.h("div.hook-badges", null);
      if (isWinner) badges.appendChild(d.h("span.chip.tone-ok", null, icons.icon("trophy", { size: 14 }), d.h("span", null, kind === "claim" ? t("arena.stopWinner") : t("arena.winner"))));
      if (state.picked === side) badges.appendChild(d.h("span.chip.tone-brand", null, icons.icon("user", { size: 14 }), d.h("span", null, t("arena.yourPick"))));
      if (kind === "rank" || kind === "hook") {
        var isModelPick = (side === "a") === (duel.model_p_a >= 0.5);
        if (isModelPick) badges.appendChild(d.h("span.chip.tone-info", null, icons.icon("target", { size: 14 }), d.h("span", null, t("arena.modelPick"))));
      }
      var content;
      if (kind === "rank") content = placeBlock(hook, isWinner, side.toUpperCase());
      else if (kind === "reach") content = reachBlock(hook, duel, isWinner);
      else if (kind === "claim") content = claimBlock(hook);
      else {
        var m = charts.meter({ value: 0, max: 100, tone: isWinner ? "ok" : "brand", label: t("arena.success") + " " + side.toUpperCase(), valueText: function () { return hook.success + " / 100"; } });
        var val = d.h("strong.num.success-val", null, "0");
        tweens.push(d.tween({ from: 0, to: hook.success, ms: 1000, onUpdate: function (v) { val.textContent = d.fmt(v, 1); } }));
        content = [
          d.h("div.reveal-line", null, d.h("span.reveal-label", null, t("arena.success")), val, d.h("span.chip.tone-warn.sim-chip", null, icons.icon("flask", { size: 13 }), d.h("span", null, t("common.simulated")))),
          m,
          d.h("div.reveal-line.score-line", null, d.h("span.reveal-label", null, t("arena.score")), d.h("strong.num", null, d.fmt(hook.score, 1)))
        ];
        d.raf(function () { m.set(hook.success); });
      }
      var foot = [];
      if (hook.derived) foot.push(d.h("span.chip.tone-warn", { title: t("arena.derivedHint") }, icons.icon("info", { size: 13 }), d.h("span", null, t("arena.derived"))));
      if (hook.url) foot.push(d.extLink(hook.url, [icons.icon("arrowRight", { size: 14 }), d.h("span", null, t("arena.open"))], "link.small.open-link"));
      d.fill(box, [badges, content, foot.length ? d.h("div.reveal-foot", null, foot) : null]);
      box.hidden = false;
      wrap.classList.add(isWinner ? "is-winner" : "is-loser");
      if (state.picked === side) wrap.classList.add("is-picked");
    }

    function verdictPanel(duel, res) {
      var correct = res.correct;
      var xp = res.xp;
      var chips = [];
      if (correct) {
        chips.push(d.h("span.chip", null, t("arena.xpBase", { n: xp.base })));
        if (xp.difficulty) chips.push(d.h("span.chip", null, t("arena.xpDifficulty", { level: t("arena." + duel.difficulty), n: xp.difficulty })));
        if (xp.upset) chips.push(d.h("span.chip.tone-brand", null, t("arena.xpUpset", { n: xp.upset })));
        if (xp.multiplier > 1) chips.push(d.h("span.chip.tone-xp", null, t("arena.xpCombo", { n: xp.multiplier })));
        if (xp.confidence) chips.push(d.h("span.chip.tone-info", null, t("arena.xpConfidence", { n: xp.confidence })));
      } else {
        chips.push(d.h("span.chip", null, t("arena.xpParticipation", { n: xp.participation })));
      }
      var xpNum = d.h("strong.xp-gain", null, "+0 XP");
      tweens.push(d.countUp(xpNum, xp.total, { prefix: "+", suffix: " XP", ms: 800 }));
      var upsetBadge = res.upsetCaught
        ? d.h("div.upset-badge", { role: "status" }, icons.icon("bolt", { size: 28 }), d.h("div", null, d.h("strong", null, t("arena.upset")), d.h("span", null, t("arena.upsetText"))))
        : null;
      return d.h("div.verdict" + (correct ? ".is-correct" : ".is-wrong"), { id: "duel-verdict", role: "group", "aria-label": t("arena.result") },
        upsetBadge,
        d.h("div.result-head", null,
          d.h("span.result-icon", { "aria-hidden": "true" }, icons.icon(correct ? "check" : "heart", { size: 26, stroke: 2.4 })),
          d.h("h2.result-title", null, correct ? t("arena.correct") : t("arena.wrong")),
          xpNum),
        d.h("div.verdict-foot", null,
          d.h("div.chip-row", null, chips),
          d.h("div.verdict-actions", null,
            d.h("span.small.muted.enter-hint", null, d.kbd("Enter")),
            d.h("button.btn.btn-primary.next-btn", { type: "button", onclick: function () { advance(); } }, t("arena.next"), icons.icon("arrowRight", { size: 18 })))),
        !res.upsetCaught && duel.upset ? d.h("p.small.upset-note", null, icons.icon("bolt", { size: 15 }), d.h("span", null, t("arena.upsetMissed"))) : null);
    }

    function modelBox(duel) {
      var pA = Math.round(duel.model_p_a * 100);
      var modelPickA = duel.model_p_a >= 0.5;
      var reasons = ctx.pick(duel, "reasons", ctx.lang());
      var reasonList = Array.isArray(reasons) && reasons.length
        ? d.h("ul.reason-list", null, reasons.map(function (r) { return d.h("li", null, icons.icon("chevronRight", { size: 14 }), d.h("span", null, r)); }))
        : d.h("p.small.muted", null, t("arena.noReasons"));
      return [
        d.h("div.model-box", null,
          d.h("h3.sub", null, t("arena.modelProb")),
          charts.splitBar({ a: duel.model_p_a, labelA: "A", labelB: "B", aria: t("arena.modelAria", { a: pA, b: 100 - pA, pick: modelPickA ? "A" : "B" }) }),
          d.h("p.small.muted", null, t("arena.scores", { a: d.fmt(duel.a.score, 1), b: d.fmt(duel.b.score, 1) }))),
        d.h("div", null, d.h("h3.sub", null, t("arena.why")), reasonList)
      ];
    }

    function detailsPanel(duel) {
      var kind = kindOf(duel);
      var parts = [];
      if (kind === "rank") {
        parts = parts.concat(modelBox(duel));
        var m = real && real.model;
        if (m && m.pct !== null && m.pct !== undefined) parts.push(d.h("p.small", null, icons.icon("target", { size: 15 }), " ", t("arena.modelReal", { n: m.pairs, pct: d.fmt(m.pct, 1) })));
        parts.push(d.h("p.small.muted", null, icons.icon("shieldCheck", { size: 15 }), " ", t("arena.realNote.rank", { date: snapshotDate(duel) })));
      } else if (kind === "reach") {
        parts.push(d.h("p", null, t("arena.reachExplain", { a: duel.a.brand, an: duel.a.count, b: duel.b.brand, bn: duel.b.count, of: duel.a.of })));
        parts.push(d.h("p.small.muted", null, icons.icon("shieldCheck", { size: 15 }), " ", t("arena.realNote.reach", { date: snapshotDate(duel) })));
      } else if (kind === "claim") {
        parts.push(d.h("p", null, t("arena.claimExplain")));
        parts.push(d.h("p.small.muted", null, icons.icon("info", { size: 15 }), " ", t("arena.realNote.claim")));
      } else {
        parts = parts.concat(modelBox(duel));
        parts.push(d.h("p.small.sim-note", null, icons.icon("flask", { size: 15 }), d.h("span", null, t("arena.simNote"))));
      }
      if (state.cycled) parts.push(d.h("p.small.muted", null, t("arena.cycled")));
      return d.h("section.card.result-details", { "aria-label": t("arena.details") }, parts);
    }

    // -- actions ---------------------------------------------------------------------------------------
    function pick(side) {
      if (state.revealed || !state.duel) return;
      state.picked = side;
      state.revealed = true;
      var conf = state.confidenceOn ? state.confidence : undefined;
      var res = ctx.apply(game.answerDuel, { duel: state.duel, pick: side, confidence: conf });
      state.result = res;
      state.sessionPlayed += 1;
      if (res.correct) state.sessionCorrect += 1;
      ctx.sound(res.upsetCaught ? "level" : res.correct ? "correct" : "wrong");
      showReveal(true);
      ctx.announce(t(res.correct ? "arena.announceCorrect" : "arena.announceWrong", { side: state.duel.winner.toUpperCase(), xp: "+" + res.xp.total }) + (res.upsetCaught ? " " + t("arena.upset") : ""));
    }

    function advance() {
      if (!state.revealed) return;
      nextDuel();
      render();
      var first = page.querySelector(".hook-card");
      if (first) first.focus({ preventScroll: true });
      scrollToDuel();
    }

    function stickyOffset() {
      var top = root.document.getElementById("topbar");
      var nav = root.document.getElementById("nav");
      var desktop = root.matchMedia && root.matchMedia("(min-width: 900px)").matches;
      return (top ? top.offsetHeight : 0) + (desktop && nav ? nav.offsetHeight : 0) + 12;
    }

    function scrollToDuel() {
      var area = page.querySelector(".duel-area");
      if (!area) return;
      var y = area.getBoundingClientRect().top + root.pageYOffset - stickyOffset();
      if (Math.abs(root.pageYOffset - y) > 40) root.scrollTo({ top: Math.max(0, y), behavior: ctx.reducedMotion() ? "auto" : "smooth" });
    }

    function showReveal(animate) {
      var duel = state.duel, res = state.result;
      var area = page.querySelector(".duel-area");
      area.classList.add("is-revealed");
      ["a", "b"].forEach(function (side) {
        var wrap = page.querySelector('.hook-wrap[data-side="' + side + '"]');
        fillReveal(wrap, side, duel);
        wrap.querySelector(".hook-card").setAttribute("aria-disabled", "true");
      });
      d.fill(page.querySelector(".duel-top"), verdictPanel(duel, res));
      d.fill(page.querySelector(".details-host"), detailsPanel(duel));
      if (animate) {
        var combo = page.querySelector("#combo-x");
        if (combo) { combo.classList.remove("pop"); void combo.offsetWidth; combo.classList.add("pop"); }
        scrollToDuel();
        var nextBtn = page.querySelector(".next-btn");
        if (nextBtn) timers.push(setTimeout(function () { if (alive) { try { nextBtn.focus({ preventScroll: true }); } catch (e) { /* ignore */ } } }, 350));
      }
    }

    // -- render ----------------------------------------------------------------------------------------------
    function render() {
      tweens.forEach(function (tw) { tw.cancel(); });
      tweens = [];
      var duel = state.duel;
      if (!arena.length || !duel) {
        d.fill(page, [
          d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t(real ? "arena.titleReal" : "arena.title")),
          kindPicker(),
          widgets.emptyState({ icon: "swords", title: t("arena.empty.title"), text: t("arena.empty.text") })
        ]);
        return;
      }
      var top = d.h("div.duel-top");
      var area = d.h("section.duel-area", { "aria-label": promptQuestion(duel) },
        top,
        d.h("div.duel-cards", null, hookCard("a", duel.a, duel), d.h("span.vs", { "aria-hidden": "true" }, "VS"), hookCard("b", duel.b, duel)),
        d.h("p.small.muted.key-help", null, t("arena.keys")));
      d.fill(page, [
        d.h("div.arena-head", null,
          d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t(real ? "arena.titleReal" : "arena.title")),
          d.h("p.page-lead", null, real ? t("arena.leadReal") : t("arena.lead"))),
        kindPicker(),
        statsStrip(),
        area,
        d.h("div.details-host"),
        filtersCard()
      ]);
      if (state.revealed && state.result) showReveal(false);
      else d.fill(top, promptPanel(duel));
    }

    // -- keyboard ----------------------------------------------------------------------------------------------
    function onKey(e) {
      if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented) return;
      var inField = d.isFormField(e.target);
      var isRange = inField && e.target.type === "range";
      var k = e.key;
      if (!state.revealed) {
        if (k === "a" || k === "A" || (k === "ArrowLeft" && !inField)) { e.preventDefault(); pick("a"); }
        else if (k === "b" || k === "B" || (k === "ArrowRight" && !inField)) { e.preventDefault(); pick("b"); }
      } else if (k === "Enter" && !isRange && !(e.target.closest && e.target.closest("button, a, input, select, textarea, summary"))) {
        e.preventDefault();
        advance();
      }
    }

    var wrongKind = state.duel && state.kind !== "all" && kindOf(state.duel) !== state.kind;
    if (!state.duel || wrongKind || (arena.length && !state.revealed && state.difficulty !== "all" && state.duel.difficulty !== state.difficulty)) nextDuel();
    render();
    root.document.addEventListener("keydown", onKey);

    return {
      destroy: function () {
        alive = false;
        root.document.removeEventListener("keydown", onKey);
        timers.forEach(clearTimeout);
        tweens.forEach(function (tw) { tw.cancel(); });
      }
    };
  }

  return { mount: mount, platformLabel: platformLabel, kindOf: kindOf, KINDS: KINDS, SITE_TYPES: SITE_TYPES, _state: state };
});
