/* Lab: three mini games that teach honest experimentation.
 *  1. Duel: pick a scenario, choose visitors per arm, run a simulated A/B test (seeded RNG, hidden truth),
 *     read the z test, p value, Newcombe interval and the Bayesian chance that B is better, then decide.
 *  2. Don't Peek: 1000 A/A tests, checked at every look versus once at a fixed horizon.
 *  3. Bandit Garden: Thompson sampling versus an even split on 4 variants with an SVG regret chart.
 * Everything is simulated in the browser; the statistics live in labstats.js (tested against Python).
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.lab = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var TABS = ["duel", "peek", "bandit"];
  var SPEEDS = { slow: 3, normal: 9, fast: 36 };

  // Survive navigation and language changes during a session.
  var duelState = { scenarioId: null, n: null, round: null, calc: { baseline: 5, lift: 20 } };
  var peekState = { looks: 10, result: null };
  var banditState = { rounds: 2000, speed: "normal", seed: null, done: null };
  var activeTab = "duel";

  function mount(container, ctx, route) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets;
    var t = d.t;
    var sub = route && route.sub;
    if (TABS.indexOf(sub) >= 0) activeTab = sub;
    var page = d.h("div.page.lab");
    var current = null;
    var builders = { duel: buildDuel, peek: buildPeek, bandit: buildBandit };

    var tabs = widgets.tabs({
      label: t("lab.tabs"), active: activeTab,
      items: [
        { id: "duel", label: t("lab.tab.duel"), icon: "scale" },
        { id: "peek", label: t("lab.tab.peek"), icon: "eye" },
        { id: "bandit", label: t("lab.tab.bandit"), icon: "sprout" }
      ],
      onChange: function (id, panel) {
        activeTab = id;
        if (current && current.destroy) current.destroy();
        d.clear(panel);
        current = builders[id](panel, ctx);
        try { root.history.replaceState(null, "", "#/lab/" + id); } catch (e) { /* file:// in some browsers */ }
      }
    });
    d.fill(page, [
      d.h("div.arena-head", null,
        d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("lab.title")),
        d.h("p.page-lead", null, t("lab.lead")),
        d.h("p.small.sim-note", null, icons.icon("flask", { size: 15 }), d.h("span", null, t("lab.simNote")))),
      tabs.el, tabs.panel
    ]);
    container.appendChild(page);
    return { destroy: function () { if (current && current.destroy) current.destroy(); } };
  }

  // ===== 1. Duel ============================================================================================
  function buildDuel(panel, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets;
    var game = root.DK.game, labstats = root.DK.labstats;
    var t = d.t;
    var st = duelState;
    var scenarios = (ctx.bundle.lab && ctx.bundle.lab.scenarios) || [];
    var tweens = [];
    var timers = [];
    var running = false;
    var alive = true;
    if (!scenarios.length) {
      d.fill(panel, widgets.emptyState({ icon: "flask", title: t("lab.empty.title"), text: t("lab.empty.text") }));
      return { destroy: function () {} };
    }
    function byId(id) { return scenarios.filter(function (s) { return s.id === id; })[0]; }
    if (!byId(st.scenarioId)) st.scenarioId = scenarios[0].id;
    function scenario() { return byId(st.scenarioId); }
    function maxN(s) { return Math.max(3000, Math.round(s.visitors_hint * 3 / 500) * 500); }
    function defaultN(s) { return Math.max(200, Math.round(s.visitors_hint / 2 / 100) * 100); }
    function newRound() {
      var s = scenario();
      var seed = Math.floor(ctx.rng() * 4294967296);
      st.round = { seed: seed, scenarioId: s.id, truth: game.drawLabTruth(s, labstats.mulberry32(seed)), runs: [], decision: null, judged: null };
      st.n = defaultN(s);
    }
    if (!st.round || st.round.scenarioId !== st.scenarioId) newRound();
    if (!st.n) st.n = defaultN(scenario());

    var host = d.h("div.lab-duel");
    d.fill(panel, host);

    function title(s) { return ctx.pick(s, "title"); }
    function daysFor(s, n) { return Math.max(1, Math.ceil(n / (s.visitors_hint / 14))); }

    function scenarioPicker() {
      var s0 = scenario();
      return d.h("fieldset.fieldset.scn-group", null,
        d.h("legend", null, t("lab.duel.scenario")),
        d.h("div.scn-list", null, scenarios.map(function (s) {
          var input = d.h("input", { type: "radio", name: "lab-scn", value: s.id, checked: s.id === s0.id, onchange: function () {
            if (running) return;
            st.scenarioId = s.id; newRound(); render();
          } });
          return d.h("label.scn" + (s.id === s0.id ? ".is-on" : ""), null, input,
            d.h("span.scn-title", null, title(s)),
            d.h("span.scn-meta", null, t("lab.duel.baseline", { p: d.fmtPct(s.baseline, 1) })),
            d.h("span.scn-meta", null, t("lab.duel.traffic", { n: d.fmt(s.visitors_hint) })));
        })));
    }

    function controls() {
      var s = scenario();
      var round = st.round;
      var locked = !!round.decision || running;
      var slider = widgets.slider({
        label: t("lab.duel.visitors"), min: 200, max: maxN(s), step: 100, value: Math.min(st.n, maxN(s)),
        format: function (v) { return d.fmt(v); },
        onInput: function (v) { st.n = v; days.textContent = ctx.tp("lab.duel.days", daysFor(s, v)); }
      });
      slider.disable(locked);
      var days = d.h("span.small.muted", null, ctx.tp("lab.duel.days", daysFor(s, st.n)));
      var plan = t("lab.duel.planning", { m: 20, p: d.fmtPct(s.baseline, 1), n: d.fmt(labstats.sampleSizePerArm(s.baseline, 0.2)) });
      var runBtn = d.h("button.btn.btn-primary", { type: "button", disabled: locked, onclick: function () { run(); } },
        icons.icon("play", { size: 18 }), d.h("span", null, round.runs.length ? t("lab.duel.runAgain") : t("lab.duel.run")));
      return d.h("section.card.lab-controls", null,
        d.h("div.lab-controls-grid", null,
          d.h("div.stack.tight", null, slider.el, days, d.h("p.small.muted", null, plan)),
          d.h("div.run-col", null, runBtn,
            round.runs.length ? d.h("span.small.muted", null, t("lab.duel.runs", { k: round.runs.length })) : null)));
    }

    function rateRow(label, rate, k, n, max, tone) {
      return d.h("div.rate-row", null,
        d.h("span.rate-label", null, label),
        charts.meter({ value: rate, max: max, size: "md", tone: tone, label: label, valueText: function () { return d.fmtPct(rate, 2); } }),
        d.h("span.rate-val", null, d.h("strong.num", null, d.fmtPct(rate, 2)), d.h("span.small.muted", null, t("lab.duel.counts", { k: d.fmt(k), n: d.fmt(n) }))));
    }

    function resultBlock(run) {
      var tt = run.test, by = run.bayes;
      var max = Math.max(tt.rateA, tt.rateB, 0.005) * 1.3;
      var diffPts = tt.diff * 100;
      var lo = tt.ciDiff[0] * 100, hi = tt.ciDiff[1] * 100;
      var sig = tt.significant;
      var rel = tt.relUplift === null ? "-" : d.fmtSigned(tt.relUplift * 100, 1) + "%";
      var bayesPct = Math.round(by.pBBetter * 100);
      return d.h("section.card.lab-results", { "aria-label": t("lab.duel.resultsTitle") },
        d.h("h2.card-title", null, t("lab.duel.resultsTitle")),
        d.h("div.rate-rows", null, rateRow(t("lab.duel.variantA"), tt.rateA, run.convA, run.n, max, "info"), rateRow(t("lab.duel.variantB"), tt.rateB, run.convB, run.n, max, "brand")),
        d.h("div.stat-boxes", null,
          d.h("div.stat-box", null, d.h("span.stat-label", null, t("lab.duel.diff")), d.h("strong.num", null, d.fmtSigned(diffPts, 2) + " " + t("lab.duel.points")), d.h("span.small.muted", null, t("lab.duel.rel", { r: rel }))),
          d.h("div.stat-box", null, d.h("span.stat-label", null, t("lab.duel.zTest")), d.h("strong.num", null, "z = " + d.fmt(tt.z, 2)), d.h("span.small.muted", null, labstats.formatP(tt.pValue).replace(".", d.lang() === "cs" ? "," : "."))),
          d.h("div.stat-box.sig-box" + (sig ? ".is-sig" : ""), null,
            d.h("span.stat-label", null, t("lab.duel.verdict")),
            d.h("strong", null, icons.icon(sig ? "check" : "minus", { size: 16, stroke: 2.6 }), " ", sig ? t("lab.duel.sig") : t("lab.duel.notSig")),
            d.h("span.small.muted", null, sig ? (tt.diff > 0 ? t("lab.duel.sigB") : t("lab.duel.sigA")) : t("lab.duel.notSigHint")))),
        d.h("div.interval-box", null,
          d.h("h3.sub", null, t("lab.duel.ci")),
          charts.intervalPlot({ point: diffPts, lo: lo, hi: hi, fmt: function (v) { return d.fmtSigned(v, 1); }, zeroLabel: t("lab.duel.zero"),
            ariaLabel: t("lab.duel.ciAria", { d: d.fmtSigned(diffPts, 2), lo: d.fmtSigned(lo, 2), hi: d.fmtSigned(hi, 2) }) }).el,
          d.h("p.small.muted", null, t("lab.duel.ciHint"))),
        d.h("div.bayes-box", null,
          d.h("h3.sub", null, t("lab.duel.bayes")),
          d.h("div.bayes-row", null, d.h("strong.num.bayes-num", null, bayesPct + "%"),
            charts.meter({ value: bayesPct, max: 100, size: "md", tone: by.pBBetter >= 0.95 ? "ok" : "brand", label: t("lab.duel.bayes"), valueText: function () { return bayesPct + "%"; }, marker: 95, markerLabel: "95%" })),
          d.h("p.small.muted", null, t("lab.duel.loss", { a: d.fmt(by.expectedLossChooseA * 100, 2), b: d.fmt(by.expectedLossChooseB * 100, 2) }))));
    }

    function historyTable() {
      var runs = st.round.runs;
      if (runs.length < 2) return null;
      return d.h("details.card.history", null,
        d.h("summary", null, icons.icon("chart", { size: 18 }), d.h("span", null, t("lab.duel.history")), icons.icon("chevronDown", { size: 18, class: "chev" })),
        d.h("p.small.muted", null, t("lab.duel.historyNote")),
        d.h("div.table-scroll", null, d.h("table.data-table", null,
          d.h("thead", null, d.h("tr", null, [t("lab.duel.colRun"), t("lab.duel.colN"), t("lab.duel.variantA"), t("lab.duel.variantB"), "p", "P(B)"].map(function (h) { return d.h("th", { scope: "col" }, h); }))),
          d.h("tbody", null, runs.map(function (r, i) {
            return d.h("tr", null, d.h("th", { scope: "row" }, String(i + 1)), d.h("td.num", null, d.fmt(r.n)),
              d.h("td.num", null, d.fmtPct(r.test.rateA, 2)), d.h("td.num", null, d.fmtPct(r.test.rateB, 2)),
              d.h("td.num", null, d.fmt(r.test.pValue, 3)), d.h("td.num", null, Math.round(r.bayes.pBBetter * 100) + "%"));
          })))));
    }

    function decisionBlock() {
      var round = st.round;
      var has = round.runs.length > 0;
      if (round.decision) return truthBlock();
      function btn(id, label, icon) {
        return d.h("button.btn.btn-ghost.decide-btn", { type: "button", disabled: !has || running, onclick: function () { decide(id); } }, icons.icon(icon, { size: 20 }), d.h("span", null, label));
      }
      return d.h("section.card.decision", { "aria-labelledby": "decide-h" },
        d.h("h2.card-title", { id: "decide-h" }, t("lab.duel.decide")),
        d.h("p.small.muted", null, has ? t("lab.duel.decideHint") : t("lab.duel.decideWait")),
        d.h("div.decide-row", null, btn("ship_a", t("lab.duel.shipA"), "anchor"), btn("ship_b", t("lab.duel.shipB"), "send"), btn("keep_testing", t("lab.duel.keep"), "restart")));
    }

    function explainKey(decision, truthKind, judged) {
      var says = judged.evidenceSays;
      var dk = decision === "keep_testing" ? "keep" : decision === "ship_a" ? "a" : "b";
      if (decision !== "keep_testing") return "lab.duel.ex." + truthKind + "." + dk;
      var variant = !judged.conclusive ? "inconclusive" : (judged.correct ? "falseAlarm" : "wasted");
      return "lab.duel.ex." + truthKind + ".keep." + variant;
    }

    function truthBlock() {
      var round = st.round, j = round.judged, tr = round.truth;
      var s = scenario();
      var truthText = tr.kind === "better"
        ? t("lab.duel.truth.better", { a: d.fmtPct(tr.rateA, 2), b: d.fmtPct(tr.rateB, 2), l: d.fmt(tr.trueLiftRel * 100, 0) })
        : tr.kind === "none" ? t("lab.duel.truth.none", { a: d.fmtPct(tr.rateA, 2) })
        : t("lab.duel.truth.worse", { a: d.fmtPct(tr.rateA, 2), b: d.fmtPct(tr.rateB, 2), l: d.fmt(Math.abs(tr.trueLiftRel) * 100, 0) });
      var choice = round.decision === "ship_a" ? t("lab.duel.shipA") : round.decision === "ship_b" ? t("lab.duel.shipB") : t("lab.duel.keep");
      var key = explainKey(round.decision, tr.kind, j);
      var extra = null;
      if (tr.kind === "better" && round.decision === "keep_testing" && !j.conclusive) {
        extra = d.h("p.small.muted", null, t("lab.duel.needMore", { n: d.fmt(labstats.sampleSizePerArm(tr.rateA, tr.trueLiftRel)) }));
      }
      var xpNum = d.h("strong.xp-gain", null, "+0 XP");
      tweens.push(d.countUp(xpNum, j.xp, { prefix: "+", suffix: " XP", ms: 700 }));
      return d.h("section.card.truth-card" + (j.correct ? ".is-right" : ".is-wrong"), { "aria-labelledby": "truth-h", tabindex: "-1", id: "lab-truth" },
        d.h("div.result-head", null,
          d.h("span.result-icon", { "aria-hidden": "true" }, icons.icon(j.correct ? "check" : "heart", { size: 26, stroke: 2.4 })),
          d.h("h2.result-title", { id: "truth-h" }, j.correct ? t("lab.duel.right") : t("lab.duel.wrong")),
          xpNum),
        d.h("p.small.muted", null, t("lab.duel.youChose", { c: choice })),
        d.h("div.truth-box", null, d.h("span.stat-label", null, t("lab.duel.truth")), d.h("strong", null, truthText)),
        d.h("p", null, t(key, { l: d.fmt(Math.abs(tr.trueLiftRel) * 100, 0) })),
        extra,
        d.h("p.small.muted", null, t("lab.duel.truthOdds", { a: Math.round(game.LAB_TRUTH_ODDS.better * 100), b: Math.round(game.LAB_TRUTH_ODDS.none * 100), c: Math.round(game.LAB_TRUTH_ODDS.worse * 100) })),
        d.h("div.row.wrap", null,
          d.h("button.btn.btn-primary", { type: "button", onclick: function () { newRound(); render(); host.scrollIntoView({ block: "start", behavior: ctx.reducedMotion() ? "auto" : "smooth" }); } }, t("lab.duel.next"), icons.icon("arrowRight", { size: 18 }))));
    }

    function calculator() {
      var c = st.calc;
      var out = d.h("p.calc-out", { "aria-live": "polite" });
      var inB = d.h("input.input", { type: "number", inputmode: "decimal", min: "0.1", max: "90", step: "0.1", value: String(c.baseline), id: "calc-b" });
      var inL = d.h("input.input", { type: "number", inputmode: "decimal", min: "1", max: "500", step: "1", value: String(c.lift), id: "calc-l" });
      function update() {
        var b = parseFloat(inB.value), l = parseFloat(inL.value);
        c.baseline = b; c.lift = l;
        try {
          if (!(b > 0 && b < 100 && l > 0)) throw new Error("range");
          var n = labstats.sampleSizePerArm(b / 100, l / 100);
          out.textContent = t("lab.calc.result", { n: d.fmt(n) });
          out.classList.remove("is-bad");
        } catch (e) { out.textContent = t("lab.calc.invalid"); out.classList.add("is-bad"); }
      }
      inB.addEventListener("input", update);
      inL.addEventListener("input", update);
      update();
      return d.h("details.card.calc", null,
        d.h("summary", null, icons.icon("chart", { size: 18 }), d.h("span", null, t("lab.calc.title")), icons.icon("chevronDown", { size: 18, class: "chev" })),
        d.h("p.small.muted", null, t("lab.calc.intro")),
        d.h("div.form-grid.two", null, widgets.field(t("lab.calc.baseline"), inB), widgets.field(t("lab.calc.lift"), inL)), out);
    }

    function runningBlock(n) {
      var counter = d.h("strong.num", null, "0");
      var m = charts.meter({ value: 0, max: n, size: "md", tone: "brand", label: t("lab.duel.running") });
      tweens.push(d.tween({ from: 0, to: n, ms: 1000, ease: d.ease.linear, onUpdate: function (v) { counter.textContent = d.fmt(Math.round(v)); m.set(v, true); } }));
      return d.h("section.card.lab-results", { role: "status" },
        d.h("h2.card-title", null, t("lab.duel.running")),
        d.h("div.row", null, counter, d.h("span.small.muted", null, t("lab.duel.perArm"))), m);
    }

    function render() {
      tweens.forEach(function (tw) { tw.cancel(); });
      tweens = [];
      var s = scenario();
      var round = st.round;
      var latest = round.runs[round.runs.length - 1];
      d.fill(host, [
        d.h("section.card.lab-intro", null,
          d.h("h2.card-title", null, t("lab.duel.title")),
          d.h("p", null, t("lab.duel.intro", { s: title(s) })),
          d.h("p.small.muted", null, t("lab.duel.odds", { a: Math.round(game.LAB_TRUTH_ODDS.better * 100), b: Math.round(game.LAB_TRUTH_ODDS.none * 100), c: Math.round(game.LAB_TRUTH_ODDS.worse * 100) })),
          scenarioPicker()),
        controls(),
        running ? runningBlock(st.pendingN) : (latest ? resultBlock(latest) : null),
        historyTable(),
        decisionBlock(),
        calculator()
      ]);
    }

    function run() {
      if (running || st.round.decision) return;
      var s = scenario();
      var round = st.round;
      var n = st.n;
      var idx = round.runs.length;
      var seed = labstats.hashSeed(round.seed + ":" + idx);
      function finish() {
        var sim = labstats.simulateAB(round.truth.rateA, round.truth.rateB, n, seed);
        var test = labstats.twoProportionTest(sim.convA, sim.nA, sim.convB, sim.nB);
        var bayes = labstats.bayesAB(sim.convA, sim.nA, sim.convB, sim.nB, { draws: 8000, seed: (seed ^ 0x9e3779b9) >>> 0 });
        round.runs.push({ n: n, convA: sim.convA, convB: sim.convB, test: test, bayes: bayes });
        running = false;
        ctx.apply(game.applyLabRun, { kind: "duel" });
        ctx.sound("pop");
        d.announce(t("lab.duel.announce", { k: round.runs.length, a: d.fmtPct(test.rateA, 2), b: d.fmtPct(test.rateB, 2), p: labstats.formatP(test.pValue), pb: Math.round(bayes.pBBetter * 100) }));
        if (alive) render();
      }
      if (ctx.reducedMotion()) { finish(); return; }
      running = true;
      st.pendingN = n;
      render();
      timers.push(setTimeout(function () { if (alive) finish(); else running = false; }, 1050));
      void s;
    }

    function decide(decision) {
      var round = st.round;
      var latest = round.runs[round.runs.length - 1];
      if (!latest || round.decision) return;
      var j = game.judgeLabDecision(decision, round.truth, latest.test);
      var out = ctx.apply(game.applyLabDecision, { correct: j.correct });
      round.decision = decision;
      round.judged = { correct: j.correct, conclusive: j.conclusive, evidenceSays: j.evidenceSays, xp: out.xp };
      ctx.sound(j.correct ? "correct" : "wrong");
      d.announce(j.correct ? t("lab.duel.right") : t("lab.duel.wrong"));
      render();
      var el = host.querySelector("#lab-truth");
      if (el) { try { el.focus({ preventScroll: true }); } catch (e) { /* ignore */ } el.scrollIntoView({ block: "center", behavior: ctx.reducedMotion() ? "auto" : "smooth" }); }
    }

    render();
    return { destroy: function () { alive = false; tweens.forEach(function (tw) { tw.cancel(); }); timers.forEach(clearTimeout); } };
  }

  // ===== 2. Don't Peek ========================================================================================
  function buildPeek(panel, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets;
    var game = root.DK.game, labstats = root.DK.labstats;
    var t = d.t;
    var st = peekState;
    var NOMINAL = 0.05, TRIALS = 1000, PER_LOOK = 200;
    var host = d.h("div.lab-peek");
    var results = d.h("div.peek-results");
    var busy = false;
    var timers = [];
    var alive = true;
    var slider = widgets.slider({ label: t("lab.peek.looks"), min: 2, max: 20, step: 1, value: st.looks, format: function (v) { return String(v); }, onInput: function (v) { st.looks = v; } });
    var runBtn = d.h("button.btn.btn-primary", { type: "button", onclick: function () { run(); } }, icons.icon("play", { size: 18 }), d.h("span", null, t("lab.peek.run", { n: d.fmt(TRIALS) })));

    function showResult(res) {
      var peekPct = d.fmtPct(res.peeking, 1), fixedPct = d.fmtPct(res.fixed, 1);
      var bars = charts.barChart({
        bars: [
          { id: "fixed", label: t("lab.peek.fixed"), value: res.fixed, slot: 1 },
          { id: "peek", label: t("lab.peek.peeking", { n: res.looks }), value: res.peeking, slot: 2 }
        ],
        max: Math.max(0.3, res.peeking * 1.25), fmt: function (v) { return d.fmtPct(v, 1); },
        refLine: { value: NOMINAL, label: t("lab.peek.nominal") },
        ariaLabel: t("lab.peek.barAria", { a: fixedPct, b: peekPct, n: res.looks }), caption: t("lab.peek.barCaption"),
        headers: [t("lab.peek.colMethod"), t("lab.peek.colRate")]
      });
      var curve = charts.lineChart({
        series: [{ id: "peek", label: t("lab.peek.seriesPeek"), slot: 2, points: res.byLook.map(function (v, i) { return [i + 1, v]; }) }],
        xLabel: t("lab.peek.xLabel"), xFmt: function (v) { return String(Math.round(v)); }, yFmt: function (v) { return d.fmtPct(v, 0); },
        height: 240, ariaLabel: t("lab.peek.curveAria"), caption: t("lab.peek.curveCaption"), nominal: { y: NOMINAL, label: t("lab.peek.nominal") }, tableRows: Math.min(res.looks, 10)
      });
      d.fill(results, [
        d.h("section.card", null,
          d.h("h2.card-title", null, t("lab.peek.resultTitle")),
          d.h("p.peek-summary", null, t("lab.peek.summary", { t: d.fmt(res.trials), a: d.fmt(Math.round(res.peeking * res.trials)), b: d.fmt(Math.round(res.fixed * res.trials)) })),
          bars.el,
          d.h("p.small.muted", null, t("lab.peek.barNote"))),
        d.h("section.card", null, curve.el, d.h("p.small.muted", null, t("lab.peek.curveNote"))),
        d.h("section.card.lesson", null,
          d.h("h2.card-title", null, icons.icon("shieldCheck", { size: 22 }), t("lab.peek.lessonTitle")),
          d.h("ul.rule-list.plain", null, [t("lab.peek.l1"), t("lab.peek.l2"), t("lab.peek.l3")].map(function (x) { return d.h("li", null, icons.icon("check", { size: 16 }), d.h("span", null, x)); })))
      ]);
    }

    function run() {
      if (busy) return;
      busy = true;
      runBtn.disabled = true;
      d.fill(results, d.h("div.card.row", { role: "status" }, widgets.spinner(), d.h("span", null, t("lab.peek.running"))));
      timers.push(setTimeout(function () {
        if (!alive) return;
        var seed = Math.floor(ctx.rng() * 4294967296);
        var res = labstats.peekingExperiment({ looks: st.looks, nPerLook: PER_LOOK, trials: TRIALS, baseRate: 0.05, alpha: NOMINAL, seed: seed });
        st.result = res;
        busy = false;
        runBtn.disabled = false;
        showResult(res);
        var out = ctx.apply(game.applyLabRun, { kind: "peek" });
        void out;
        ctx.sound("pop");
        d.announce(t("lab.peek.announce", { a: d.fmtPct(res.peeking, 1), b: d.fmtPct(res.fixed, 1) }));
      }, 60));
    }

    d.fill(host, [
      d.h("section.card.lab-intro", null,
        d.h("h2.card-title", null, t("lab.peek.title")),
        d.h("p", null, t("lab.peek.intro")),
        d.h("p.small.muted", null, t("lab.peek.setup", { t: d.fmt(TRIALS), n: PER_LOOK })),
        d.h("div.lab-controls-grid", null, d.h("div", null, slider.el), d.h("div.run-col", null, runBtn))),
      results
    ]);
    d.fill(panel, host);
    if (st.result) showResult(st.result);
    return { destroy: function () { alive = false; timers.forEach(clearTimeout); } };
  }

  // ===== 3. Bandit Garden ==========================================================================================
  function buildBandit(panel, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets;
    var game = root.DK.game, labstats = root.DK.labstats;
    var t = d.t;
    var st = banditState;
    var K = 4;
    var LETTERS = ["A", "B", "C", "D"];
    var alive = true;
    var rafId = 0;
    var running = false;
    var sim = null;
    var host = d.h("div.lab-bandit");

    function makeRates(seed) {
      var rng = labstats.mulberry32(seed);
      var base = 0.03 + rng() * 0.03;
      var mult = [1, 1.12, 1.3, 1.55];
      for (var i = mult.length - 1; i > 0; i--) { var j = Math.floor(rng() * (i + 1)); var tmp = mult[i]; mult[i] = mult[j]; mult[j] = tmp; }
      return mult.map(function (m) { return Math.round(base * m * 10000) / 10000; });
    }
    function newGarden() {
      st.seed = Math.floor(ctx.rng() * 4294967296);
      st.done = null;
      sim = null;
    }
    if (!st.seed) newGarden();

    // -- DOM pieces that the animation updates every frame
    var rows = { even: [], ts: [] };
    var counters = { even: null, ts: null };
    var chart = null;
    var statusEl = d.h("p.small.muted.bandit-status", { role: "status" });
    var summaryHost = d.h("div.bandit-summary");
    var startBtn = d.h("button.btn.btn-primary", { type: "button", onclick: function () { toggle(); } });
    var roundsSlider = null, speedSeg = null;

    function gardenCard(key, label, desc, tone) {
      var list = d.h("ul.garden-rows");
      rows[key] = [];
      for (var i = 0; i < K; i++) {
        var m = charts.meter({ value: 0, max: 1, size: "md", tone: tone, label: label + " " + LETTERS[i] });
        var count = d.h("span.garden-count", null, "0");
        var rate = d.h("span.garden-rate.small.muted", null, "-");
        var crown = d.h("span.garden-crown", { hidden: true, title: t("lab.bandit.best") }, icons.icon("crown", { size: 16 }));
        rows[key].push({ meter: m, count: count, rate: rate, crown: crown });
        list.appendChild(d.h("li.garden-row", null,
          d.h("span.garden-name", null, icons.icon("sprout", { size: 18 }), d.h("strong", null, LETTERS[i]), crown),
          m, d.h("span.garden-nums", null, count, rate)));
      }
      counters[key] = d.h("strong.num", null, "0");
      return d.h("section.card.garden." + key, { "aria-label": label },
        d.h("div.garden-head", null, d.h("h3.card-title", null, label), d.h("div.garden-total", null, counters[key], d.h("span.small.muted", null, t("lab.bandit.visitors")))),
        d.h("p.small.muted", null, desc), list);
    }

    function paint(final) {
      if (!sim) return;
      ["even", "ts"].forEach(function (key) {
        var b = key === "even" ? sim.even : sim.ts;
        counters[key].textContent = d.fmt(b.t);
        for (var i = 0; i < K; i++) {
          var share = b.t ? b.pulls[i] / b.t : 0;
          rows[key][i].meter.set(share, true);
          rows[key][i].count.textContent = d.fmt(b.pulls[i]);
          rows[key][i].rate.textContent = b.pulls[i] ? d.fmtPct(b.wins[i] / b.pulls[i], 1) : "-";
          if (final) {
            rows[key][i].crown.hidden = i !== b.bestArm;
            rows[key][i].rate.textContent = (b.pulls[i] ? d.fmtPct(b.wins[i] / b.pulls[i], 1) : "-") + " \u00b7 " + t("lab.bandit.true", { p: d.fmtPct(st.rates[i], 1) });
          }
        }
      });
    }

    function chartSeries() {
      return [
        { id: "ts", label: t("lab.bandit.thompson"), slot: 1, points: sim.curveTs },
        { id: "even", label: t("lab.bandit.even"), slot: 2, points: sim.curveEven }
      ];
    }

    function setButton() {
      d.fill(startBtn, [icons.icon(running ? "pause" : "play", { size: 18 }), d.h("span", null, running ? t("lab.bandit.pause") : (sim && sim.even.t > 0 && sim.even.t < st.rounds ? t("lab.bandit.resume") : t("lab.bandit.start")))]);
      if (roundsSlider) roundsSlider.disable(running || (sim && sim.even.t > 0 && sim.even.t < st.rounds));
    }

    function initSim() {
      st.rates = makeRates(st.seed);
      var stride = Math.max(1, Math.floor(st.rounds / 120));
      sim = {
        even: labstats.createBandit(st.rates, "uniform", st.seed + 1), ts: labstats.createBandit(st.rates, "thompson", st.seed + 2),
        curveEven: [[0, 0]], curveTs: [[0, 0]], stride: stride, frames: 0
      };
      st.done = null;
      d.clear(summaryHost);
    }

    function stepSome(n) {
      for (var i = 0; i < n && sim.even.t < st.rounds; i++) {
        sim.even.step(); sim.ts.step();
        if (sim.even.t % sim.stride === 0 || sim.even.t === st.rounds) {
          sim.curveEven.push([sim.even.t, sim.even.regret]);
          sim.curveTs.push([sim.ts.t, sim.ts.regret]);
        }
      }
    }

    function finish(replay) {
      running = false;
      cancelAnimationFrame(rafId);
      paint(true);
      chart.setSeries(chartSeries());
      chart.refreshTable();
      var re = sim.even.regret, rt = sim.ts.regret;
      st.done = { regretEven: re, regretTs: rt };
      var best = sim.ts.bestArm;
      d.fill(summaryHost, d.h("section.card.lesson", null,
        d.h("h2.card-title", null, icons.icon("trophy", { size: 22 }), t("lab.bandit.resultTitle")),
        d.h("p", null, t("lab.bandit.summary", { n: d.fmt(st.rounds), a: d.fmt(re, 1), b: d.fmt(rt, 1), s: d.fmt(Math.max(0, re - rt), 1) })),
        d.h("p.small.muted", null, t("lab.bandit.share", { x: d.fmtPct(sim.ts.pulls[best] / st.rounds, 0), y: d.fmtPct(sim.even.pulls[best] / st.rounds, 0), k: LETTERS[best] })),
        d.h("p.small.muted", null, t("lab.bandit.caveat"))));
      statusEl.textContent = t("lab.bandit.done");
      setButton();
      if (replay) return;
      ctx.apply(game.applyLabRun, { kind: "bandit" });
      ctx.sound("pop");
      d.announce(t("lab.bandit.announce", { a: d.fmt(re, 1), b: d.fmt(rt, 1) }));
    }

    function frame() {
      if (!alive || !running) return;
      stepSome(SPEEDS[st.speed] || 9);
      paint(false);
      sim.frames += 1;
      if (sim.frames % 4 === 0) chart.setSeries(chartSeries());
      statusEl.textContent = t("lab.bandit.progress", { a: d.fmt(sim.even.t), b: d.fmt(st.rounds) });
      if (sim.even.t >= st.rounds) finish(); else rafId = requestAnimationFrame(frame);
    }

    function toggle() {
      if (running) { running = false; cancelAnimationFrame(rafId); setButton(); statusEl.textContent = t("lab.bandit.paused"); return; }
      if (!sim || sim.even.t >= st.rounds) initSim();
      if (ctx.reducedMotion()) { stepSome(st.rounds); running = true; finish(); return; }
      running = true;
      setButton();
      var grid = host.querySelector(".garden-grid");
      if (grid && !(sim.even.t > 0)) grid.scrollIntoView({ block: "start", behavior: "smooth" });
      rafId = requestAnimationFrame(frame);
    }

    function reset() {
      running = false;
      cancelAnimationFrame(rafId);
      newGarden();
      initSim();
      paint(false);
      chart.setSeries(chartSeries());
      statusEl.textContent = t("lab.bandit.ready");
      setButton();
    }

    roundsSlider = widgets.slider({ label: t("lab.bandit.rounds"), min: 500, max: 5000, step: 500, value: st.rounds, format: function (v) { return d.fmt(v); }, onInput: function (v) { st.rounds = v; } });
    speedSeg = widgets.segmented({ label: t("lab.bandit.speed"), active: st.speed, items: [{ id: "slow", label: t("lab.bandit.slow") }, { id: "normal", label: t("lab.bandit.normal") }, { id: "fast", label: t("lab.bandit.fast") }], onChange: function (id) { st.speed = id; } });

    initSim();
    chart = charts.lineChart({
      series: chartSeries(), xLabel: t("lab.bandit.xLabel"), xFmt: function (v) { return d.fmt(Math.round(v)); }, yFmt: function (v) { return d.fmt(v, v < 10 ? 1 : 0); },
      height: 280, ariaLabel: t("lab.bandit.chartAria"), caption: t("lab.bandit.chartCaption"), tableRows: 11
    });

    d.fill(host, [
      d.h("section.card.lab-intro", null,
        d.h("h2.card-title", null, t("lab.bandit.title")),
        d.h("p", null, t("lab.bandit.intro")),
        d.h("div.lab-controls-grid.bandit-controls", null,
          d.h("div.stack.tight", null, roundsSlider.el, d.h("div.setting", null, d.h("span.setting-label", null, t("lab.bandit.speed")), speedSeg.el)),
          d.h("div.run-col", null, startBtn,
            d.h("button.btn.btn-ghost", { type: "button", onclick: function () { reset(); } }, icons.icon("restart", { size: 18 }), t("lab.bandit.newGarden")))),
        statusEl),
      d.h("div.garden-grid", null,
        gardenCard("ts", t("lab.bandit.thompson"), t("lab.bandit.thompsonDesc"), "brand"),
        gardenCard("even", t("lab.bandit.even"), t("lab.bandit.evenDesc"), "info")),
      d.h("section.card", null, d.h("h2.card-title", null, t("lab.bandit.regretTitle")), chart.el, d.h("p.small.muted", null, t("lab.bandit.regretNote"))),
      summaryHost
    ]);
    d.fill(panel, host);
    paint(false);
    setButton();
    statusEl.textContent = t("lab.bandit.ready");
    if (st.done && sim.even.t === 0) {
      // Language change after a finished run: replay it instantly so the result stays visible.
      stepSome(st.rounds);
      running = true;
      finish(true);
    }
    return { destroy: function () { alive = false; running = false; cancelAnimationFrame(rafId); } };
  }

  return { mount: mount, _states: { duelState: duelState, peekState: peekState, banditState: banditState } };
});
