/* Guru: a 4 week content plan. Renders a Plan (bundle.guru_sample, or the result of /api/guru in live mode):
 * positioning, content pillars with their share, channels, a calendar with A/B test markers, the experiment
 * backlog with the sample size each test needs (the formula the Lab uses), KPIs, the GEO workstream and the
 * guardrails. Every field is optional: missing data never breaks the view. The plan can be copied or saved
 * as Markdown. Nothing here is an engagement forecast: baselines in the sample are placeholders.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.guru = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var CHANNEL_ICON = { linkedin: "users", blog: "book", email: "send", youtube: "play", short_video: "play", instagram: "heart", x: "quote", facebook: "users", pinterest: "star", google_business: "globe" };
  var WEEK_CHOICES = [2, 4, 6, 8];
  var POST_CHOICES = [3, 4, 5];

  // What the player chose last; the plan returned by the server in live mode.
  var state = { plan: null, options: { weeks: 4, ppw: 5 }, explorer: null };

  // Labels the planner writes in the language of the brief, mapped to UI strings so the page stays in one language.
  var POS_LABELS = { audience: "forge.audience", publikum: "forge.audience", topic: "forge.topic", "téma": "forge.topic", promise: "guru.pos.promise", slib: "guru.pos.promise", proof: "guru.pos.proof", "důkaz": "guru.pos.proof", tone: "forge.tone", "tón": "forge.tone" };

  function slug(s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, ""); }
  function fileSlug(s) { return String(s || "").normalize("NFD").replace(/\p{Mn}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "plan"; }

  /** "Brand | Audience: x | Topic: y" into [{label, value}]; the first part is the brand and has no label. */
  function parsePositioning(text) {
    var parts = String(text || "").split(/\s\|\s/);
    if (parts.length < 2) return [{ label: null, value: String(text || "") }];
    function tidy(v) { return v.replace(/([.!?]);\s/g, "$1 "); }
    return parts.map(function (p, i) {
      var m = i > 0 ? /^([^:]{1,24}):\s*([\s\S]*)$/.exec(p) : null;
      return m ? { label: m[1], value: tidy(m[2]) } : { label: null, value: tidy(p) };
    });
  }

  function groupWeeks(calendar) {
    var map = {}, order = [];
    (calendar || []).forEach(function (it) {
      var w = Number(it.week) || 1;
      if (!map[w]) { map[w] = []; order.push(w); }
      map[w].push(it);
    });
    order.sort(function (a, b) { return a - b; });
    return order.map(function (w) { return { n: w, items: map[w] }; });
  }

  /** A calendar experiment ({hypothesis, variant_b, metric}, or just an id) joined with its backlog entry. */
  function normExperiment(plan, exp, pick) {
    if (!exp) return null;
    var list = plan.experiments || [];
    var def = null;
    var i;
    if (typeof exp === "string") {
      for (i = 0; i < list.length; i++) if (list[i].id === exp) def = list[i];
      return def ? { hypothesis: pick(def, "hypothesis"), variantB: null, metric: def.metric, def: def } : null;
    }
    for (i = 0; i < list.length && !def; i++) if (list[i].hypothesis_en === exp.hypothesis || list[i].hypothesis_cs === exp.hypothesis) def = list[i];
    for (i = 0; i < list.length && !def; i++) if (list[i].metric === exp.metric) def = list[i];
    return { hypothesis: exp.hypothesis || (def ? pick(def, "hypothesis") : ""), variantB: exp.variant_b || null, metric: exp.metric || (def ? def.metric : ""), def: def };
  }

  function mount(container, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets, forge = root.DK.ui.forge;
    var scoring = root.DK.scoring, labstats = root.DK.labstats, i18n = root.DK.i18n;
    var t = d.t;
    var page = d.h("div.page.guru");
    container.appendChild(page);
    var live = ctx.live();
    var sample = forge.pickByLang(ctx.bundle.guru_samples || [], ctx.lang()) || ctx.bundle.guru_sample || null;
    var plan = state.plan || sample;
    var isSample = !state.plan;
    var alive = true;
    forge.seedBrief(ctx, sample && sample.brief);

    var planLang = "en";
    var pillarIdx = {};
    /** Derived values that depend on which plan is shown (the sample, or the one the server just built). */
    function prepare() {
      planLang = plan && plan.brief && (plan.brief.lang === "cs" || plan.brief.lang === "en") ? plan.brief.lang : ctx.lang();
      pillarIdx = {};
      ((plan && plan.pillars) || []).forEach(function (p, i) { pillarIdx[p.id] = (i % 4) + 1; });
    }
    prepare();

    function nameOf(prefix, id) {
      var key = prefix + "." + id;
      return i18n.has(key) ? t(key) : String(id || "").replace(/_/g, " ");
    }
    function channelName(id) { return nameOf("guru.channel", id); }
    function formatName(id) { return nameOf("fmt", id); }
    function dayName(day, short) { return nameOf(short ? "guru.dayShort" : "guru.day", day); }
    function kpiText(text) { var key = "guru.kpi." + slug(text); return i18n.has(key) ? t(key) : String(text || ""); }
    function pillarName(id) {
      var list = (plan && plan.pillars) || [];
      for (var i = 0; i < list.length; i++) if (list[i].id === id) return ctx.pick(list[i], "name") || id;
      return id;
    }
    function scoreOf(text) {
      try { return scoring.scoreHook(String(text || ""), "", { lang: planLang }); } catch (e) { return null; }
    }
    function pctText(x) { var whole = Math.abs(x * 100 - Math.round(x * 100)) < 1e-9; return d.fmtPct(x, whole ? 0 : 1); }
    function numText(x) {
      var r = Math.round(x * 100) / 100;
      var digits = Math.abs(r - Math.round(r)) < 1e-9 ? 0 : (Math.abs(r * 10 - Math.round(r * 10)) < 1e-9 ? 1 : 2);
      return d.fmt(r, digits);
    }

    function block(id, title, sub, content) {
      return d.h("section.block", { "aria-labelledby": id },
        d.h("div.heading", null, d.h("div.heading-main", null, d.h("h2.heading-title", { id: id }, title), sub ? d.h("p.heading-sub", null, sub) : null)),
        content);
    }
    function swatch(i) { return d.h("span.swatch.p-" + i, { "aria-hidden": "true" }); }

    // -- Markdown export ------------------------------------------------------------------------------------
    function markdown() {
      var o = [];
      var brand = (plan.brief && plan.brief.brand) || "";
      function cell(s) { return String(s === undefined || s === null ? "" : s).replace(/\|/g, "/").replace(/\r?\n/g, " "); }
      o.push("# " + t("guru.md.title", { brand: brand }), "");
      if (plan.positioning) o.push("**" + t("guru.positioning") + ":** " + plan.positioning, "");
      if ((plan.pillars || []).length) {
        o.push("## " + t("guru.pillars"), "");
        plan.pillars.forEach(function (p) {
          var angles = p["angles_" + ctx.lang()] || p.angles || [];
          o.push("- **" + (ctx.pick(p, "name") || p.id) + "** (" + pctText(p.share || 0) + "): " + angles.slice(0, 2).join("; "));
        });
        o.push("");
      }
      if ((plan.channels || []).length) {
        o.push("## " + t("guru.channels"), "");
        plan.channels.forEach(function (c) {
          o.push("- **" + channelName(c.id) + "**: " + t("guru.perWeek", { n: numText(c.posts_per_week || 0) }) + ", " + (c.formats || []).map(formatName).join(", ") + ". " + ctx.pick(c, "why"));
        });
        o.push("");
      }
      if ((plan.calendar || []).length) {
        o.push("## " + t("guru.calendar"), "");
        o.push("| " + [t("guru.md.week"), t("guru.md.day"), t("guru.md.channel"), t("guru.md.format"), t("guru.md.pillar"), "Hook"].join(" | ") + " |", "|---|---|---|---|---|---|");
        plan.calendar.forEach(function (it) {
          o.push("| " + [it.week, dayName(it.day), channelName(it.channel), formatName(it.format), pillarName(it.pillar), cell(it.hook) + (it.experiment ? " (A/B)" : "")].join(" | ") + " |");
        });
        o.push("");
      }
      if ((plan.experiments || []).length) {
        o.push("## " + t("guru.experiments"), "");
        plan.experiments.forEach(function (e) {
          o.push("- " + ctx.pick(e, "hypothesis") + " (" + kpiText(e.metric) + ", " + t("guru.nPerArm", { n: d.fmt(e.n_per_arm) }) + ")");
        });
        o.push("");
      }
      if ((plan.kpis || []).length) {
        o.push("## " + t("guru.kpis"), "");
        plan.kpis.forEach(function (k) { o.push("- **" + t("forge.goal." + k.goal) + "**: " + ctx.pick(k, "metric") + ". " + ctx.pick(k, "target_rule")); });
        o.push("");
      }
      if (plan.geo) {
        o.push("## " + t("guru.geo"), "");
        (plan.geo.queries || []).forEach(function (q) { o.push("- " + q); });
        (plan.geo["tasks_" + ctx.lang()] || plan.geo.tasks_en || []).forEach(function (x, i) { o.push((i + 1) + ". " + x); });
        o.push("");
      }
      var rails = plan["guardrails_" + ctx.lang()] || plan.guardrails_en || [];
      if (rails.length) { o.push("## " + t("guru.guardrails"), ""); rails.forEach(function (g) { o.push("- " + g); }); o.push(""); }
      if ((plan.needs_input || []).length) { o.push("## " + t("guru.needs"), ""); plan.needs_input.forEach(function (n) { o.push("- " + n); }); o.push(""); }
      return o.join("\n");
    }

    // -- sections -------------------------------------------------------------------------------------------
    function headCard() {
      var cal = plan.calendar || [];
      var weeks = groupWeeks(cal).length;
      var pos = parsePositioning(plan.positioning);
      var hasLabels = pos.some(function (p) { return p.label; });
      var posView;
      if (hasLabels) {
        posView = d.h("dl.pos-list", null, pos.map(function (p, i) {
          return d.h("div.pos-item" + (p.label ? "" : ".is-brand"), null,
            d.h("dt", null, p.label ? (POS_LABELS[p.label.toLowerCase()] ? t(POS_LABELS[p.label.toLowerCase()]) : p.label) : t("guru.brand")),
            d.h("dd", null, forge.slotNodes(p.value, d, icons)));
        }));
      } else {
        posView = d.h("p.pos-text", null, forge.slotNodes(plan.positioning || "", d, icons));
      }
      var brand = (plan.brief && plan.brief.brand) || "";
      return d.h("section.card.plan-head", { "aria-labelledby": "plan-h" },
        d.h("div.editor-head", null,
          d.h("h2.card-title", { id: "plan-h" }, isSample ? t("guru.sampleTitle", { brand: brand }) : t("guru.planTitle", { brand: brand })),
          d.h("div.chip-row", null,
            plan.brief && plan.brief.goal ? d.h("span.chip.tone-brand", null, icons.icon("target", { size: 13 }), d.h("span", null, t("forge.goal." + plan.brief.goal))) : null,
            d.h("span.chip", null, icons.icon("calendar", { size: 13 }), d.h("span", null, ctx.tp("guru.weeks", weeks) + ", " + ctx.tp("guru.posts", cal.length))))),
        d.h("h3.sub", null, t("guru.positioning")),
        posView,
        isSample ? d.h("p.small.sim-note", null, icons.icon("flask", { size: 15 }), d.h("span", null, t("guru.sampleNote"))) : d.h("p.small.muted", null, t("guru.liveNote")),
        d.h("div.row.wrap", null,
          widgets.copyButton(markdown, t("guru.copyMd")),
          d.h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: function () {
            d.download("content-plan-" + fileSlug(brand) + ".md", markdown(), "text/markdown;charset=utf-8");
            d.announce(t("guru.saved"));
          } }, icons.icon("download", { size: 15 }), d.h("span", null, t("guru.downloadMd")))));
    }

    function needsCard() {
      var list = plan.needs_input || [];
      if (!list.length) return null;
      return d.h("section.card.needs-card", { "aria-labelledby": "needs-h" },
        d.h("h2.card-title", { id: "needs-h" }, icons.icon("pencil", { size: 20 }), t("guru.needs")),
        d.h("p.small.muted", null, t("guru.needsHint")),
        d.h("ul.need-list", null, list.map(function (n) { return d.h("li", null, icons.icon("alert", { size: 16 }), d.h("span", null, d.rich(n))); })));
    }

    function pillarsBlock() {
      var pillars = plan.pillars || [];
      if (!pillars.length) return null;
      var aria = pillars.map(function (p) { return (ctx.pick(p, "name") || p.id) + " " + pctText(p.share || 0); }).join(", ");
      var bar = d.h("div.share-bar", { role: "img", "aria-label": aria }, pillars.map(function (p, i) {
        return d.h("span.share-seg.p-" + ((i % 4) + 1), { style: { flexGrow: String(Math.max(1, Math.round((p.share || 0) * 1000))) } });
      }));
      var grid = d.h("ul.pillar-grid", null, pillars.map(function (p, i) {
        var angles = p["angles_" + ctx.lang()] || p.angles || [];
        return d.h("li.pillar.p-" + ((i % 4) + 1), null,
          d.h("div.pillar-head", null, swatch((i % 4) + 1), d.h("strong.pillar-name", null, ctx.pick(p, "name") || p.id), d.h("span.num.pillar-share", null, pctText(p.share || 0))),
          d.h("ul.angle-list", null, angles.map(function (a) { return d.h("li", null, String(a)); })));
      }));
      return block("pillars-h", t("guru.pillars"), t("guru.pillarsSub"), d.h("div.card.pillars-card", null, bar, grid));
    }

    function channelsBlock() {
      var channels = plan.channels || [];
      if (!channels.length) return null;
      return block("channels-h", t("guru.channels"), t("guru.channelsSub"), d.h("ul.channel-grid", null, channels.map(function (c) {
        return d.h("li.channel", null,
          d.h("div.channel-head", null,
            d.h("span.channel-icon", { "aria-hidden": "true" }, icons.icon(CHANNEL_ICON[c.id] || "layers", { size: 20 })),
            d.h("strong.channel-name", null, channelName(c.id)),
            d.h("span.chip.tone-brand", null, t("guru.perWeek", { n: numText(c.posts_per_week || 0) }))),
          d.h("p.small.channel-why", null, ctx.pick(c, "why")),
          d.h("div.chip-row", null, (c.formats || []).map(function (f) { return d.h("span.chip", null, formatName(f)); })),
          c.kpi ? d.h("p.small.muted", null, d.h("strong", null, t("guru.watch") + " "), kpiText(c.kpi)) : null);
      })));
    }

    function openItem(it) {
      var exp = normExperiment(plan, it.experiment, ctx.pick);
      var s = scoreOf(it.hook);
      var body = d.h("div.cal-detail", null,
        d.h("p.cal-detail-hook", null, it.hook || ""),
        d.h("div.chip-row", null,
          d.h("span.chip", null, icons.icon(CHANNEL_ICON[it.channel] || "layers", { size: 13 }), d.h("span", null, channelName(it.channel))),
          d.h("span.chip", null, formatName(it.format)),
          d.h("span.chip", null, swatch(pillarIdx[it.pillar] || 1), d.h("span", null, pillarName(it.pillar))),
          it.kpi ? d.h("span.chip", null, icons.icon("chart", { size: 13 }), d.h("span", null, kpiText(it.kpi))) : null),
        s ? d.h("p.small", null, icons.icon("bolt", { size: 15 }), " ", d.h("strong", null, t("guru.hookScore", { n: d.fmt(s.total, 1) })), " ", d.h("span.muted", null, t("guru.scoreTail", { r: d.fmtPct(s.clickbait_risk, 0) })))
          : null,
        exp ? d.h("section.cal-ab-box", null,
          d.h("h3.sub", null, icons.icon("flask", { size: 16 }), " " + t("guru.abTest")),
          d.h("p", null, exp.hypothesis),
          exp.variantB ? d.h("p.small", null, d.h("strong", null, t("guru.variantB") + " "), d.quote(exp.variantB)) : null,
          (function () {
            var sb = exp.variantB ? scoreOf(exp.variantB) : null;
            if (!s || !sb) return null;
            return d.h("p.small.muted", null, t("guru.abScores", { a: d.fmt(s.total, 1), b: d.fmt(sb.total, 1) }));
          })(),
          d.h("div.chip-row", null,
            d.h("span.chip", null, icons.icon("target", { size: 13 }), d.h("span", null, kpiText(exp.metric))),
            exp.def && exp.def.n_per_arm ? d.h("span.chip.tone-info", null, t("guru.nPerArm", { n: d.fmt(exp.def.n_per_arm) })) : null),
          d.h("p.small.muted", null, t("guru.abNote"))) : null);
      var dlg = widgets.dialog({
        title: t("guru.weekDay", { n: it.week, day: dayName(it.day) }),
        body: body,
        actions: [widgets.copyButton(it.hook || "", t("guru.copyHook")), d.h("button.btn.btn-primary", { type: "button", onclick: function () { dlg.close(); } }, t("common.close"))]
      });
    }

    function calendarBlock() {
      var cal = plan.calendar || [];
      if (!cal.length) return null;
      var pillars = plan.pillars || [];
      var legend = d.h("ul.cal-legend", { "aria-label": t("guru.legend") },
        pillars.map(function (p, i) { return d.h("li", null, swatch((i % 4) + 1), d.h("span", null, ctx.pick(p, "name") || p.id)); }),
        d.h("li", null, icons.icon("flask", { size: 15 }), d.h("span", null, t("guru.abTest"))));
      var weeks = groupWeeks(cal).map(function (w) {
        var tests = w.items.filter(function (it) { return !!it.experiment; }).length;
        var hid = d.uid("wk");
        return d.h("section.cal-week", { "aria-labelledby": hid },
          d.h("div.cal-week-head", null,
            d.h("h3.cal-week-title", { id: hid }, t("guru.week", { n: w.n })),
            d.h("span.small.muted", null, ctx.tp("guru.posts", w.items.length) + (tests ? ", " + ctx.tp("guru.tests", tests) : ""))),
          d.h("ol.cal-days", null, w.items.map(function (it) {
            var pi = pillarIdx[it.pillar] || 1;
            var label = dayName(it.day) + ", " + channelName(it.channel) + ", " + (it.hook || "") + (it.experiment ? ", " + t("guru.abTest") : "");
            return d.h("li.cal-cell", null, d.h("button.cal-item.p-" + pi, { type: "button", "aria-haspopup": "dialog", "aria-label": label, onclick: function () { openItem(it); } },
              d.h("span.cal-day", { "aria-hidden": "true" }, dayName(it.day, true)),
              d.h("span.cal-body", { "aria-hidden": "true" },
                d.h("span.cal-channel", null, icons.icon(CHANNEL_ICON[it.channel] || "layers", { size: 14 }), d.h("span", null, channelName(it.channel))),
                d.h("span.cal-hook", null, it.hook || ""),
                d.h("span.cal-foot", null, d.h("span.cal-pillar", null, pillarName(it.pillar)), it.experiment ? d.h("span.cal-ab", null, icons.icon("flask", { size: 12 }), "A/B") : null))));
          })));
      });
      return block("calendar-h", t("guru.calendar"), t("guru.calendarSub"), d.h("div.cal", null, legend, weeks));
    }

    function explorerCard() {
      var first = (plan.experiments || [])[0];
      if (!state.explorer) state.explorer = { base: first && first.baseline ? Math.round(first.baseline * 1000) / 10 : 3, mde: first && first.mde_rel ? Math.round(first.mde_rel * 100) : 20 };
      var ex = state.explorer;
      var out = d.h("output.calc-out");
      function update() {
        try {
          var n = labstats.sampleSizePerArm(ex.base / 100, ex.mde / 100);
          out.textContent = t("guru.explorer.result", { n: d.fmt(n), total: d.fmt(2 * n) });
          out.classList.remove("is-bad");
        } catch (e) {
          out.textContent = t("guru.explorer.invalid");
          out.classList.add("is-bad");
        }
      }
      var s1 = widgets.slider({ label: t("guru.explorer.baseline"), min: 0.5, max: 50, step: 0.5, value: ex.base, format: function (v) { return d.fmtPct(v / 100, 1); }, onInput: function (v) { ex.base = v; update(); } });
      var s2 = widgets.slider({ label: t("guru.explorer.mde"), min: 5, max: 100, step: 1, value: ex.mde, format: function (v) { return "+" + d.fmtPct(v / 100, 0); }, onInput: function (v) { ex.mde = v; update(); } });
      update();
      return d.h("section.card.explorer", { "aria-labelledby": "explorer-h" },
        d.h("h3.card-title", { id: "explorer-h" }, icons.icon("scale", { size: 20 }), t("guru.explorer.title")),
        d.h("p.small.muted", null, t("guru.explorer.text")),
        d.h("div.explorer-grid", null, s1.el, s2.el),
        out,
        d.h("p.small.muted", null, t("guru.explorer.note")));
    }

    function experimentsBlock() {
      var exps = plan.experiments || [];
      if (!exps.length) return null;
      var cards = d.h("ul.exp-grid", null, exps.map(function (e) {
        var n = e.n_per_arm;
        return d.h("li.exp", null,
          d.h("div.chip-row", null, d.h("span.chip.tone-brand", null, icons.icon("flask", { size: 13 }), d.h("span", null, String(e.id || "").toUpperCase())), d.h("span.chip", null, kpiText(e.metric))),
          d.h("p.exp-hyp", null, ctx.pick(e, "hypothesis")),
          d.h("dl.exp-stats", null,
            d.h("div", null, d.h("dt", null, t("guru.baseline")), d.h("dd.num", null, e.baseline !== undefined ? pctText(e.baseline) : "-")),
            d.h("div", null, d.h("dt", null, t("guru.mde")), d.h("dd.num", null, e.mde_rel !== undefined ? "+" + pctText(e.mde_rel) : "-")),
            d.h("div", null, d.h("dt", null, t("guru.perArm")), d.h("dd.num", null, typeof n === "number" ? d.fmt(n) : "-")),
            d.h("div", null, d.h("dt", null, t("guru.bothArms")), d.h("dd.num", null, typeof n === "number" ? d.fmt(2 * n) : "-"))),
          d.h("p.small.muted", null, ctx.pick(e, "note")));
      }));
      return block("experiments-h", t("guru.experiments"), t("guru.experimentsSub"), d.h("div.stack", null, cards, explorerCard(),
        d.h("a.btn.btn-ghost.btn-sm.exp-lab", { href: "#/lab" }, icons.icon("flask", { size: 15 }), d.h("span", null, t("guru.practise")))));
    }

    function kpisBlock() {
      var kpis = plan.kpis || [];
      if (!kpis.length) return null;
      var mine = plan.brief && plan.brief.goal;
      return block("kpis-h", t("guru.kpis"), t("guru.kpisSub"), d.h("ul.kpi-list", null, kpis.map(function (k) {
        var primary = k.primary === true || (k.primary === undefined && k.goal === mine);
        return d.h("li.kpi" + (primary ? ".is-primary" : ""), null,
          d.h("div.kpi-goal", null, d.h("span.chip" + (primary ? ".tone-brand" : ""), null, t("forge.goal." + k.goal)), primary ? d.h("span.small.muted", null, t("guru.yourGoal")) : null),
          d.h("div.kpi-body", null, d.h("strong", null, ctx.pick(k, "metric")), d.h("p.small", null, ctx.pick(k, "target_rule"))));
      })));
    }

    function geoBlock() {
      var geo = plan.geo;
      if (!geo) return null;
      var tasks = geo["tasks_" + ctx.lang()] || geo.tasks_en || [];
      return block("geo-h", t("guru.geo"), t("guru.geoSub"), d.h("div.card.geo-card", null,
        (geo.queries || []).length ? d.h("div", null,
          d.h("h3.sub", null, t("guru.geoQueries")),
          d.h("ul.query-list", null, geo.queries.map(function (q) { return d.h("li", null, icons.icon("question", { size: 15 }), d.h("span", null, String(q))); }))) : null,
        tasks.length ? d.h("div", null,
          d.h("h3.sub", null, t("guru.geoTasks")),
          d.h("ol.task-list", null, tasks.map(function (x) { return d.h("li", null, d.rich(x)); }))) : null,
        d.h("p.small.sim-note", null, icons.icon("info", { size: 15 }), d.h("span", null, t("guru.geoNote")))));
    }

    function guardrailsBlock() {
      var rails = plan["guardrails_" + ctx.lang()] || plan.guardrails_en || [];
      if (!rails.length) return null;
      return block("guardrails-h", t("guru.guardrails"), t("guru.guardrailsSub"), d.h("div.card.guard-card", null,
        d.h("ul.guard-list", null, rails.map(function (g) { return d.h("li", null, icons.icon("shieldCheck", { size: 18 }), d.h("span", null, d.rich(g))); }))));
    }

    // -- live form ------------------------------------------------------------------------------------------
    function liveBox() {
      if (!live.enabled) {
        return d.h("section.card.run-live", { "aria-labelledby": "rl-h" },
          d.h("h2.card-title", { id: "rl-h" }, icons.icon("send", { size: 20 }), t("forge.runLive")),
          d.h("p", null, t("guru.runLiveText")),
          d.h("pre.code", null, "kingctl serve"),
          d.h("div.row.wrap", null, widgets.copyButton("kingctl serve", t("common.copy")), d.h("span.small.muted", null, t("forge.runLiveHint"))));
      }
      var wSel = d.h("select.input", { id: "gf-weeks", onchange: function () { state.options.weeks = Number(wSel.value); } },
        WEEK_CHOICES.map(function (n) { return d.h("option", { value: n, selected: state.options.weeks === n }, ctx.tp("guru.weeks", n)); }));
      var pSel = d.h("select.input", { id: "gf-ppw", onchange: function () { state.options.ppw = Number(pSel.value); } },
        POST_CHOICES.map(function (n) { return d.h("option", { value: n, selected: state.options.ppw === n }, ctx.tp("guru.posts", n)); }));
      var form = forge.briefForm({
        ctx: ctx, withFormats: false, submitLabel: t("guru.generate"),
        extra: d.h("div.form-grid.two", null, widgets.field(t("guru.optWeeks"), wSel), widgets.field(t("guru.optPosts"), pSel)),
        onSubmit: function (brief) {
          form.setBusy(true);
          form.setMessage(t("guru.working"), null);
          ctx.api.guru({ brief: brief, options: { weeks: state.options.weeks, posts_per_week: state.options.ppw } }).then(function (res) {
            if (!res || !Array.isArray(res.calendar)) throw new Error(t("guru.badResponse"));
            state.plan = res;
            state.explorer = null;
            plan = res;
            isSample = false;
            prepare();
            if (alive) { render(); forge.showResult(page, "plan-h"); }
            d.announce(t("guru.done", { n: res.calendar.length }));
          }).catch(function (err) {
            form.setBusy(false);
            form.setMessage(t("guru.failed", { e: err && err.message ? err.message : "?" }), "bad");
          });
        }
      });
      return d.h("section.card.live-form", { "aria-labelledby": "gf-h" },
        d.h("div.editor-head", null, d.h("h2.card-title", { id: "gf-h" }, icons.icon("send", { size: 20 }), t("guru.formTitle")), d.h("span.chip.tone-ok", null, icons.icon("spark", { size: 13 }), d.h("span", null, t("top.live")))),
        d.h("p.small.muted", null, t("guru.formIntro")), form.el);
    }

    function render() {
      var parts = [];
      if (!plan) {
        parts.push(widgets.emptyState({ icon: "guru", title: t("guru.empty.title"), text: live.enabled ? t("guru.empty.live") : t("guru.empty.offline") }));
      } else {
        parts.push(headCard(), needsCard(), pillarsBlock(), channelsBlock(), calendarBlock(), experimentsBlock(), kpisBlock(), geoBlock(), guardrailsBlock());
      }
      d.fill(page, [
        d.h("div.arena-head", null,
          d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("guru.title")),
          d.h("p.page-lead", null, t("guru.lead"))),
        live.enabled ? liveBox() : null,
        parts,
        live.enabled ? null : liveBox()
      ]);
    }
    render();
    return { destroy: function () { alive = false; } };
  }

  return { mount: mount, parsePositioning: parsePositioning, groupWeeks: groupWeeks, normExperiment: normExperiment, _state: state };
});
