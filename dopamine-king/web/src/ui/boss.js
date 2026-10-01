/* Boss Battle: write a hook for a brief and beat a benchmark. Live scoring (debounced) drives the
 * Dopamine meter against the boss threshold percentile, six driver bars, the Trust Shield for clickbait
 * risk, scorer tips, and matched phrases highlighted inside the text. Attack resolves the fight.
 * Victory needs: percentile in the boss cohort >= boss.percentile AND clickbait risk <= 0.35.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.boss = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  // Lexicon categories are shown grouped by what they feed: the five weighted drivers, risk, and tone.
  var GROUP = {
    curiosity: "curiosity", contrast: "surprise", emotion: "emotion", practical: "utility", social: "relevance",
    second_person: "relevance", clickbait: "risk", overclaim: "risk", positive: "tone", negative: "tone"
  };
  var LEGEND_ORDER = ["curiosity", "surprise", "emotion", "utility", "relevance", "risk", "tone"];
  var GROUP_ICON = { curiosity: "question", surprise: "bolt", emotion: "heart", utility: "wrench", relevance: "users", risk: "alert", tone: "plus" };
  var DRIVERS = ["curiosity", "surprise", "emotion", "relevance", "utility", "fluency"];
  var MAX_CHARS = 300;

  var drafts = {};       // boss id -> text, kept while the page stays open
  var langChoice = "auto";

  function groupOf(cat) { return GROUP[cat] || "tone"; }

  function mount(container, ctx, route) {
    if (route && route.sub) return fight(container, ctx, route.sub);
    return list(container, ctx);
  }

  // ===== list ============================================================================================
  function list(container, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets, game = root.DK.game;
    var t = d.t;
    var page = d.h("div.page.boss-list");
    container.appendChild(page);

    function cohortName(id) {
      var c = ctx.bundle.cohort_labels && ctx.bundle.cohort_labels[id];
      return c ? c[ctx.lang()] || c.en || id : id;
    }

    function card(boss) {
      var p = ctx.profile();
      var wonToday = !!(p.bossWinsByDay[ctx.today()] && p.bossWinsByDay[ctx.today()][boss.id]);
      var stars = d.h("span.stars", { "aria-hidden": "true" });
      for (var i = 1; i <= 3; i++) stars.appendChild(icons.icon("star", { size: 15, class: i <= boss.tier ? "on" : "off" }));
      return d.h("li", null, d.h("a.boss-card.tier-" + boss.tier, { href: "#/boss/" + encodeURIComponent(boss.id) },
        d.h("div.boss-card-top", null,
          d.h("div.boss-art", null, icons.bossAvatar(boss, 84)),
          d.h("div.boss-card-id", null,
            d.h("strong.boss-name", null, boss.name),
            d.h("span.boss-tier", null, stars, d.h("span", null, t("boss.tier" + boss.tier))),
            d.h("em.boss-taunt", null, d.quote(ctx.pick(boss, "taunt"))))),
        d.h("p.boss-brief", null, ctx.pick(boss, "brief")),
        d.h("div.chip-row", null,
          d.h("span.chip.tone-info", null, icons.icon("layers", { size: 13 }), d.h("span", null, cohortName(boss.cohort))),
          d.h("span.chip", null, boss.lang === "cs" ? t("arena.langCs") : t("arena.langEn")),
          d.h("span.chip.tone-brand", null, t("boss.needs", { p: boss.percentile })),
          d.h("span.chip.tone-xp", null, "+" + boss.xp + " XP"),
          wonToday ? d.h("span.chip.tone-ok", null, icons.icon("check", { size: 13 }), d.h("span", null, t("boss.wonToday"))) : null),
        d.h("span.boss-go", null, d.h("span", null, wonToday ? t("boss.fightAgain") : t("boss.fight")), icons.icon("arrowRight", { size: 18 }))));
    }

    var bosses = (ctx.bundle.bosses || []).slice().sort(function (a, b) {
      return (a.lang === ctx.lang() ? 0 : 1) - (b.lang === ctx.lang() ? 0 : 1) || a.tier - b.tier;
    });
    d.fill(page, [
      d.h("div.arena-head", null,
        d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("boss.title")),
        d.h("p.page-lead", null, t("boss.lead"))),
      bosses.length
        ? d.h("ul.boss-grid", null, bosses.map(card))
        : widgets.emptyState({ icon: "skull", title: t("boss.empty.title"), text: t("boss.empty.text") }),
      d.h("p.small.sim-note", null, icons.icon("flask", { size: 15 }), d.h("span", null, t("boss.benchNote")))
    ]);
    return { destroy: function () {} };
  }

  // ===== fight ===========================================================================================
  function fight(container, ctx, bossId) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets;
    var game = root.DK.game, scoring = root.DK.scoring;
    var t = d.t;
    var page = d.h("div.page.boss-fight");
    container.appendChild(page);
    var timers = [];
    var tweens = [];
    var alive = true;

    var boss = (ctx.bundle.bosses || []).filter(function (b) { return b.id === bossId; })[0];
    if (!boss) {
      d.fill(page, [
        d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("boss.title")),
        widgets.emptyState({ icon: "skull", title: t("boss.notFound"), text: t("boss.notFoundText"), action: d.h("a.btn.btn-primary", { href: "#/boss" }, t("boss.all")) })
      ]);
      return { destroy: function () {} };
    }

    var benchmarks = ctx.bundle.benchmarks || {};
    var cohort = (ctx.bundle.cohort_labels && ctx.bundle.cohort_labels[boss.cohort]) ? (ctx.bundle.cohort_labels[boss.cohort][ctx.lang()] || ctx.bundle.cohort_labels[boss.cohort].en) : boss.cohort;
    var bench = benchmarks[boss.cohort] || benchmarks.all || null;
    var quantiles = bench && bench.quantiles && bench.quantiles.length ? bench.quantiles : null;
    var needScore = quantiles ? game.thresholdScore(boss.percentile, quantiles) : null;

    var els = {};
    var legendHost = d.h("div.legend-host");
    var last = { result: null, resolution: null, shown: 0 };

    // -- editor ---------------------------------------------------------------------------------------
    var input = d.h("textarea.hl-input", {
      id: "hook-input", rows: 3, maxlength: String(MAX_CHARS), spellcheck: "true", autocapitalize: "sentences", enterkeyhint: "done",
      "aria-describedby": "hook-count hook-help", "aria-label": t("boss.inputLabel"), placeholder: t("boss.placeholder")
    });
    input.value = drafts[boss.id] || "";
    var layer = d.h("div.hl-layer", { "aria-hidden": "true" });
    var wrap = d.h("div.hl-wrap", null, layer, input);
    var count = d.h("span.hook-count", { id: "hook-count" }, "");
    var detected = d.h("span.chip.detected", null, "");
    var langSeg = widgets.segmented({
      label: t("boss.scoringLang"), active: langChoice,
      items: [{ id: "auto", label: t("boss.langAuto") }, { id: "cs", label: "CS" }, { id: "en", label: "EN" }],
      onChange: function (id) { langChoice = id; analyze(true); }
    });

    function resize() {
      input.style.height = "auto";
      input.style.height = Math.max(96, input.scrollHeight + 2) + "px";
    }

    function renderLayer(text, result) {
      d.clear(layer);
      var norm = scoring.normalize(text);
      var inner = d.h("div.hl-inner");
      if (norm !== text || !result || !result.spans.length) {
        inner.appendChild(d.h("span", null, text + "​"));
        layer.appendChild(inner);
        return;
      }
      var lead = scoring.leadingSpace(norm);
      var spans = result.spans.filter(function (s) { return norm.slice(s.start + lead, s.end + lead) === s.text; })
        .map(function (s) { return { category: s.category, start: s.start + lead, end: s.end + lead }; });
      scoring.segments(norm, spans).forEach(function (seg) {
        if (!seg.cats.length) { inner.appendChild(d.h("span", null, seg.text)); return; }
        var g = groupOf(seg.primary);
        inner.appendChild(d.h("mark.hl.g-" + g, { "data-cats": seg.cats.join(" ") }, seg.text));
      });
      inner.appendChild(d.h("span", null, "​"));
      layer.appendChild(inner);
    }

    // -- analysis panel -------------------------------------------------------------------------------------
    function legend(result) {
      var counts = {};
      if (result) result.spans.forEach(function (s) { var g = groupOf(s.category); counts[g] = (counts[g] || 0) + 1; });
      return d.h("ul.hl-legend", { "aria-label": t("boss.legend") }, LEGEND_ORDER.map(function (g) {
        var n = counts[g] || 0;
        return d.h("li.legend-chip" + (n ? ".has" : ""), null,
          icons.icon(GROUP_ICON[g], { size: 14 }),
          d.h("span.sample.g-" + g, { "aria-hidden": "true" }, "Aa"),
          d.h("span.legend-name", null, t("boss.group." + g)),
          d.h("b.legend-n", null, String(n)));
      }));
    }

    function phrases(result) {
      if (!result || !result.spans.length) return d.h("p.small.muted", null, t("boss.noPhrases"));
      var seen = {};
      var items = [];
      result.spans.slice().sort(function (a, b) { return a.start - b.start; }).forEach(function (s) {
        var key = s.category + ":" + s.text.toLowerCase();
        if (seen[key]) return;
        seen[key] = true;
        var g = groupOf(s.category);
        items.push(d.h("li.phrase.g-" + g, null,
          icons.icon(GROUP_ICON[g], { size: 14 }), d.h("q", null, s.text), d.h("span.phrase-cat", null, t("boss.cat." + s.category))));
      });
      return d.h("ul.phrase-list", null, items);
    }

    function conditionRow(ok, label, detailText) {
      return d.h("li.cond" + (ok ? ".is-ok" : ".is-no"), null,
        d.h("span.cond-mark", { "aria-hidden": "true" }, icons.icon(ok ? "check" : "x", { size: 16, stroke: 2.6 })),
        d.h("span.cond-text", null, d.h("strong", null, label), d.h("span", null, detailText)),
        d.h("span.sr-only", null, ok ? t("boss.met") : t("boss.notMet")));
    }

    function buildAnalysis() {
      var scoreVal = d.h("span.num.score-num", null, "0");
      var meter = charts.meter({
        value: 0, max: 100, size: "lg", tone: "brand", label: t("boss.meter"),
        marker: needScore === null ? null : needScore, markerLabel: needScore === null ? "" : t("boss.bossMarker", { n: d.fmt(needScore, 1) }),
        valueText: function (v) { return t("boss.meterText", { n: Math.round(v) }); }
      });
      var pctText = d.h("p.pct-line", null, "");
      var conds = d.h("ul.cond-list");
      var drivers = charts.driverBars({ labels: ctx.bundle.spec.labels, lang: ctx.lang(), drivers: DRIVERS, parts: {} });
      var shieldHost = d.h("div.shield-icon", { "aria-hidden": "true" });
      var shieldState = d.h("strong.shield-state", null, "");
      var shieldRisk = d.h("span.num.shield-risk", null, "");
      var riskMeter = charts.meter({ value: 0, max: 100, size: "sm", tone: "ok", label: t("boss.riskMeter"), marker: 35, markerLabel: "35 %", valueText: function (v) { return Math.round(v) + " %"; } });
      var tips = d.h("ul.tip-list");
      var phraseHost = d.h("div.phrase-host");
      els = { scoreVal: scoreVal, meter: meter, pctText: pctText, conds: conds, drivers: drivers, shieldHost: shieldHost, shieldState: shieldState, shieldRisk: shieldRisk, riskMeter: riskMeter, tips: tips, phraseHost: phraseHost, legendHost: legendHost };

      var scoreCard = d.h("section.card.score-card", { "aria-labelledby": "score-h" },
        d.h("h2.card-title", { id: "score-h" }, t("boss.scoreTitle")),
        d.h("div.score-row", null,
          d.h("div.score-big", { "aria-live": "off" }, scoreVal, d.h("span.score-of", null, "/ 100")),
          d.h("div.score-meter", null, meter)),
        pctText,
        conds,
        quantiles ? null : d.h("p.small.upset-note", null, icons.icon("alert", { size: 15 }), d.h("span", null, t("boss.noBench"))),
        d.h("p.small.sim-note", null, icons.icon("flask", { size: 15 }), d.h("span", null, t("boss.benchLine", { n: bench && bench.stats ? bench.stats.n : "?", cohort: cohort }))));

      var driversCard = d.h("section.card", { "aria-labelledby": "drv-h" },
        d.h("h2.card-title", { id: "drv-h" }, t("boss.driversTitle")), drivers,
        d.h("p.small.muted", null, t("boss.driversNote")));

      var stateRows = ["intact", "cracked", "broken"].map(function (k) {
        return d.h("li.shield-opt.is-" + k, { "data-state": k }, icons.shield(k, 26), d.h("strong", null, t("boss.shield." + k)), d.h("span", null, t("boss.shieldRange." + k)));
      });
      els.shieldOpts = d.h("ul.shield-opts", { "aria-label": t("boss.shieldTitle") }, stateRows);
      var shieldCard = d.h("section.card.shield-card", { "aria-labelledby": "shield-h" },
        d.h("h2.card-title", { id: "shield-h" }, t("boss.shieldTitle")),
        d.h("div.shield-row", null, shieldHost, d.h("div.shield-text", null, shieldState, shieldRisk)),
        riskMeter,
        els.shieldOpts,
        d.h("p.small.muted", null, t("boss.shieldNote")));

      var tipsCard = d.h("section.card", { "aria-labelledby": "tips-h" },
        d.h("h2.card-title", { id: "tips-h" }, t("boss.tipsTitle")), tips);

      var phraseCard = d.h("section.card.phrase-card", { "aria-labelledby": "ph-h" },
        d.h("h2.card-title", { id: "ph-h" }, t("boss.phrasesTitle")), phraseHost);

      return d.h("div.analysis", null, scoreCard, shieldCard, driversCard, tipsCard, phraseCard);
    }

    // -- scoring ------------------------------------------------------------------------------------------------
    function scoreNow() {
      var text = input.value;
      return scoring.scoreHook(text, "", { lang: langChoice === "auto" ? undefined : langChoice, spec: ctx.bundle.spec });
    }

    function analyze(immediate) {
      var text = input.value;
      drafts[boss.id] = text;
      var chars = Array.from(text).length;
      var words = text.trim() ? text.trim().split(/\s+/).length : 0;
      count.textContent = t("boss.count", { c: chars, max: MAX_CHARS, w: words });
      resize();
      var result = text.trim() ? scoreNow() : null;
      var shownResult = result || scoring.scoreHook("", "", { lang: langChoice === "auto" ? undefined : langChoice, spec: ctx.bundle.spec });
      var resolution = game.resolveBoss(boss, shownResult, benchmarks);
      last.result = result; last.resolution = result ? resolution : null;
      renderLayer(text, result);
      input.setAttribute("lang", shownResult.lang);

      // score and meter
      var total = result ? shownResult.total : 0;
      els.meter.set(total);
      tweens.forEach(function (tw) { tw.cancel(); });
      tweens = [d.tween({ from: last.shown, to: total, ms: immediate ? 0 : 450, onUpdate: function (v) { els.scoreVal.textContent = v.toFixed(1); } })];
      last.shown = total;
      detected.textContent = result ? t("boss.detected", { lang: shownResult.lang.toUpperCase() }) : t("boss.detectedNone");

      // percentile and conditions
      var pct = result && resolution.percentile !== null ? resolution.percentile : null;
      els.pctText.textContent = result
        ? (pct === null ? t("boss.noBench") : t("boss.pctLine", { p: Math.round(pct), cohort: cohort }))
        : t("boss.pctEmpty");
      var conds = [];
      conds.push(conditionRow(!!(result && resolution.pctOk), t("boss.condPct", { p: boss.percentile }),
        result ? (pct === null ? "-" : t("boss.condNow", { p: Math.round(pct) })) + (needScore !== null ? " · " + t("boss.condScore", { n: d.fmt(needScore, 1) }) : "") : t("boss.condWait")));
      conds.push(conditionRow(!!(result && resolution.riskOk), t("boss.condRisk"), result ? t("boss.condNowRisk", { n: Math.round(shownResult.clickbait_risk * 100) }) : t("boss.condWait")));
      d.fill(els.conds, conds);

      // drivers
      els.drivers.update(result ? shownResult.parts : {});

      // shield
      var risk = result ? shownResult.clickbait_risk : 0;
      var st = scoring.shieldState(risk);
      d.fill(els.shieldHost, icons.shield(st, 72));
      els.shieldHost.className = "shield-icon is-" + st;
      els.shieldState.textContent = result ? t("boss.shield." + st) : t("boss.shield.idle");
      els.shieldRisk.textContent = result ? t("boss.riskPct", { n: Math.round(risk * 100) }) : "";
      Array.prototype.forEach.call(els.shieldOpts.children, function (li) {
        var cur = !!result && li.getAttribute("data-state") === st;
        li.classList.toggle("is-current", cur);
        if (cur) li.setAttribute("aria-current", "true"); else li.removeAttribute("aria-current");
      });
      els.riskMeter.set(risk * 100);
      els.riskMeter.className = els.riskMeter.className.replace(/tone-\w+/, st === "intact" ? "tone-ok" : st === "cracked" ? "tone-xp" : "tone-risk");

      // tips
      var tipItems;
      if (!result) tipItems = [d.h("li", null, icons.icon("pencil", { size: 16 }), d.h("span", null, t("boss.tipEmpty")))];
      else tipItems = shownResult.tips.map(function (tip) { return d.h("li", null, icons.icon(tip.key === "ship_it" ? "check" : "bulb", { size: 16 }), d.h("span", null, tip[ctx.lang()] || tip.en)); });
      d.fill(els.tips, tipItems);

      d.fill(els.phraseHost, phrases(result));
      d.fill(els.legendHost, legend(result));
      attackBtn.disabled = !result;
      liveStrip(result ? shownResult : null, resolution);
    }

    var onInput = d.debounce(function () { analyze(false); }, 120);
    input.addEventListener("input", function () { resize(); renderLayer(input.value, null); onInput(); });
    input.addEventListener("keydown", function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); attack(); }
    });

    // -- the live strip with the attack button ---------------------------------------------------------------------------
    var strip = d.h("div.live-strip", { "aria-label": t("boss.liveStrip"), role: "group" });
    var attackBtn = d.h("button.btn.btn-primary.btn-lg.attack-btn", { type: "button", onclick: function () { attack(); } },
      icons.icon("swords", { size: 20 }), d.h("span", null, t("boss.attack")));

    function liveStrip(result, resolution) {
      var pctTxt = result && resolution.percentile !== null ? "P" + Math.round(resolution.percentile) : "-";
      var st = result ? scoring.shieldState(result.clickbait_risk) : null;
      d.fill(strip, [
        d.h("div.strip-item", null, d.h("span.strip-label", null, t("boss.stripScore")), d.h("strong.num", null, result ? result.total.toFixed(1) : "-")),
        d.h("div.strip-item", null, d.h("span.strip-label", null, t("boss.stripPct", { p: boss.percentile })), d.h("strong.num", null, pctTxt)),
        d.h("div.strip-item", null, d.h("span.strip-label", null, t("boss.stripShield")), d.h("strong", null, st ? t("boss.shield." + st) : "-")),
        attackBtn
      ]);
    }

    // -- attack ---------------------------------------------------------------------------------------------------------------
    var resultHost = d.h("div.result-host", { role: "region", "aria-label": t("boss.resultRegion") });

    function attack() {
      if (!input.value.trim()) {
        input.focus();
        d.announce(t("boss.writeFirst"));
        wrap.classList.remove("shake"); void wrap.offsetWidth; wrap.classList.add("shake");
        return;
      }
      onInput.cancel();
      analyze(true);
      var result = scoreNow();
      var resolution = game.resolveBoss(boss, result, benchmarks);
      var out = ctx.apply(game.applyBoss, { boss: boss, resolution: resolution, lang: result.lang });
      d.fill(resultHost, resultCard(result, resolution, out));
      d.raf(function () {
        var card = resultHost.firstChild;
        if (card && card.scrollIntoView) card.scrollIntoView({ block: "center", behavior: ctx.reducedMotion() ? "auto" : "smooth" });
      });
      if (out.won) {
        ctx.sound("win");
        ctx.confetti({ x: 0.5, y: 0.45, count: 190 });
        d.announce(t("boss.announceWin", { xp: out.xp }));
      } else {
        ctx.sound("wrong");
        d.announce(t("boss.announceLose"));
      }
    }

    function resultCard(result, resolution, out) {
      if (out.won) {
        var xpNum = d.h("strong.xp-gain", null, "+0 XP");
        tweens.push(d.countUp(xpNum, out.xp, { prefix: "+", suffix: " XP", ms: 900 }));
        return d.h("section.card.fight-result.is-win", { tabindex: "-1" },
          d.h("div.victory-banner", null, icons.icon("trophy", { size: 34 }), d.h("div", null, d.h("h2.result-title", null, t("boss.victory")), d.h("p", null, t("boss.victoryText", { name: boss.name })))),
          d.h("div.result-head", null, xpNum, d.h("span.small.muted", null, out.firstWin ? t("boss.xpFirst") : t("boss.xpRepeat", { n: Math.round(game.XP.bossRepeatShare * 100) }))),
          d.h("div.chip-row", null,
            out.honest ? d.h("span.chip.tone-ok", null, icons.icon("shieldCheck", { size: 14 }), d.h("span", null, t("boss.honestWin"))) : null,
            out.chestGranted ? d.h("span.chip.tone-xp", null, icons.icon("vault", { size: 14 }), d.h("span", null, t("boss.chestGained"))) : d.h("span.chip", null, t("boss.noChestRepeat")),
            d.h("span.chip.tone-brand", null, t("boss.winPct", { p: Math.round(resolution.percentile) }))),
          d.h("div.row.wrap", null,
            out.chestGranted ? d.h("a.btn.btn-primary", { href: "#/vault" }, icons.icon("vault", { size: 18 }), t("boss.openChest")) : null,
            d.h("a.btn.btn-ghost", { href: "#/boss" }, t("boss.all")),
            d.h("button.btn.btn-ghost", { type: "button", onclick: function () { resultHost.textContent = ""; input.focus(); } }, t("boss.keepEditing"))));
      }
      var reasons = [];
      if (!resolution.pctOk) {
        var gap = resolution.needScore !== null ? Math.max(0, resolution.needScore - result.total) : null;
        reasons.push(d.h("li", null, icons.icon("chevronRight", { size: 14 }), d.h("span", null, resolution.hasBenchmark ? t("boss.lostPct", { p: Math.round(resolution.percentile), need: boss.percentile, gap: d.fmt(gap, 1) }) : t("boss.noBench"))));
      }
      if (!resolution.riskOk) reasons.push(d.h("li", null, icons.icon("chevronRight", { size: 14 }), d.h("span", null, t("boss.lostRisk", { n: Math.round(resolution.risk * 100) }))));
      return d.h("section.card.fight-result.is-lose", { tabindex: "-1" },
        d.h("div.victory-banner.soft", null, icons.icon("heart", { size: 30 }), d.h("div", null, d.h("h2.result-title", null, t("boss.notYet")), d.h("p", null, t("boss.notYetText", { name: boss.name })))),
        d.h("ul.reason-list", null, reasons),
        result.tips.length ? d.h("div", null, d.h("h3.sub", null, t("boss.tryThis")), d.h("ul.tip-list", null, result.tips.map(function (tip) { return d.h("li", null, icons.icon("bulb", { size: 16 }), d.h("span", null, tip[ctx.lang()] || tip.en)); }))) : null,
        d.h("div.row.wrap", null,
          d.h("button.btn.btn-primary", { type: "button", onclick: function () { resultHost.textContent = ""; input.focus(); } }, t("boss.tryAgain")),
          d.h("a.btn.btn-ghost", { href: "#/boss" }, t("boss.all"))));
    }

    // -- layout ---------------------------------------------------------------------------------------------------------------------
    var head = d.h("section.card.boss-head.tier-" + boss.tier, null,
      d.h("div.boss-art.big", null, icons.bossAvatar(boss, 112)),
      d.h("div.boss-head-body", null,
        d.h("a.link.small.back-link", { href: "#/boss" }, icons.icon("chevronLeft", { size: 14 }), t("boss.all")),
        d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, boss.name),
        d.h("p.boss-taunt-big", null, d.quote(ctx.pick(boss, "taunt"))),
        d.h("div.chip-row", null,
          d.h("span.chip.tone-info", null, icons.icon("layers", { size: 13 }), d.h("span", null, cohort)),
          d.h("span.chip", null, boss.lang === "cs" ? t("arena.langCs") : t("arena.langEn")),
          d.h("span.chip.tone-brand", null, t("boss.needs", { p: boss.percentile })),
          d.h("span.chip", null, t("boss.tier" + boss.tier)),
          d.h("span.chip.tone-xp", null, "+" + boss.xp + " XP"))));

    var briefCard = d.h("section.card.brief", { "aria-labelledby": "brief-h" },
      d.h("h2.card-title", { id: "brief-h" }, t("boss.briefTitle")),
      d.h("p.brief-text", null, ctx.pick(boss, "brief")),
      d.h("p.small.muted", null, t("boss.winRule", { p: boss.percentile, cohort: cohort })),
      boss.lang !== ctx.lang() ? d.h("p.small.lang-hint", null, icons.icon("globe", { size: 15 }), d.h("span", null, t("boss.langHint", { lang: t("boss.langName." + boss.lang) }))) : null);

    var editorCard = d.h("section.card.editor", { "aria-labelledby": "editor-h" },
      d.h("div.editor-head", null,
        d.h("h2.card-title", { id: "editor-h" }, t("boss.yourHook")),
        d.h("div.editor-tools", null, langSeg.el, detected)),
      wrap,
      d.h("div.editor-meta", null, count, d.h("span.small.muted", { id: "hook-help" }, t("boss.help"))),
      d.h("div", null, d.h("h3.sub", null, t("boss.legendTitle")), legendHost),
      strip,
      resultHost);

    d.fill(page, [head, briefCard, editorCard, buildAnalysis()]);
    analyze(true);
    d.raf(resize);

    return {
      destroy: function () {
        alive = false;
        onInput.cancel();
        timers.forEach(clearTimeout);
        tweens.forEach(function (tw) { tw.cancel(); });
      }
    };
  }

  return { mount: mount, GROUP: GROUP, groupOf: groupOf, LEGEND_ORDER: LEGEND_ORDER };
});
