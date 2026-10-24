/* Market: what the stored web searches showed about the brand and its market, and the real tasks that follow from it.
 *
 *  Overview     the findings, each with a number, a caveat and links to the searches behind it
 *  Tasks        real work to tick off (XP is paid once per task; it is self reported, so the game never checks it)
 *  Searches     where the brand shows up, and every stored search with its links
 *  Competition  who fills the Czech results, how the brand name gets confused with another brand, what leading brands publish
 *  Claims       titles of the brand's own pages that promise a result, and what the market claims, run through the claims check
 *  Method       how the data was collected, its limits, and what is still missing
 *
 * Every number comes from bundle.market (computed in Python from the stored searches). The text of the findings is Czech, like the market.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.market = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var TABS = ["overview", "tasks", "searches", "competition", "claims", "method"];
  var GROUPS = ["brand", "category", "persona", "competitor"];
  var TRAFFIC = { context: ["ok", "market.rule.context"], wellness: ["warn", "market.rule.wellness"], cosmetic: ["warn", "market.rule.cosmetic"], medical: ["risk", "market.rule.medical"], avoid: ["risk", "market.rule.avoid"] };

  var state = { tab: "overview", group: "all", openQuery: null };

  function mount(container, ctx, route) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets, charts = root.DK.ui.charts, game = root.DK.game;
    var t = d.t;
    var market = ctx.bundle.market;
    var page = d.h("div.page.market");
    container.appendChild(page);
    if (!market) {
      d.fill(page, [d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("market.title")), widgets.emptyState({ icon: "globe", title: t("market.empty.title"), text: t("market.empty.text") })]);
      return { destroy: function () {} };
    }
    var sub = (route && route.sub) || (route && route.params && route.params.tab) || null;
    if (TABS.indexOf(sub) >= 0) state.tab = sub;
    var queries = market.queries || [];
    // the direct repeats of a few searches are listed with the others, so a finding can point at them too
    var direct = (market.direct || []).map(function (x) {
      return { id: x.id, group: "direct", query: x.query, purpose: "", domains: x.domains || [], retrieved_at: x.retrieved_on, links: x.links || [] };
    });
    var everySearch = queries.concat(direct);
    var byId = {};
    everySearch.forEach(function (q) { byId[q.id] = q; });
    var tabs = null;
    var current = null;

    function host(url) {
      var m = /^https?:\/\/([^\/]+)/i.exec(url || "");
      return m ? m[1].replace(/^www\./, "") : "";
    }

    function link(url, text, cls) {
      return d.extLink(url, text, cls);
    }

    function section(title, sub2, children) {
      return d.h("section.card.market-section", null, widgets.heading(2, title, sub2), children);
    }

    function czechNote() {
      return ctx.lang() === "cs" ? null : d.h("p.small.muted", null, icons.icon("globe", { size: 15 }), " ", t("market.czechOnly"));
    }

    function openQuery(id) {
      state.openQuery = id;
      state.tab = "searches";
      tabs.select("searches");
    }

    function evidenceChips(ids) {
      return d.h("p.small.muted.finding-src", null, d.h("span", null, t("market.basis") + " "), (ids || []).filter(function (id) { return byId[id]; }).map(function (id) {
        return d.h("button.chip.chip-btn", { type: "button", title: byId[id].query, onclick: function () { openQuery(id); } }, id);
      }));
    }

    // ===== overview =====================================================================================
    function buildOverview(panel) {
      var meta = market.meta || {};
      var sci = market.science || {};
      var facts = [
        t("market.fact.searches", { n: d.fmt(meta.searches || 0) }),
        t("market.fact.links", { n: d.fmt(meta.links || 0), s: d.fmt(meta.hosts || 0) }),
        t("market.fact.studies", { v: sci.verified || 0, n: sci.total || 0 }),
        t("market.fact.date", { date: d.fmtDate(meta.date) })
      ];
      var cards = (market.findings || []).map(function (f) {
        return d.h("article.finding-card", { id: "f-" + f.id },
          d.h("div.finding-num", null, f.number),
          d.h("h3.finding-title", null, f.title),
          d.h("p", null, f.text),
          d.h("p.small.muted", null, d.h("strong", null, t("market.caveat") + " "), f.caveat),
          evidenceChips(f.evidence));
      });
      d.fill(panel, [
        d.h("section.card.market-hero", null,
          d.h("h2.card-title", null, t("market.overview.title")),
          d.h("p", null, t("market.overview.lead", { n: d.fmt(meta.searches || 0), date: d.fmtDate(meta.date) })),
          d.h("div.chip-row", null, facts.map(function (f) { return d.h("span.chip.tone-ok", null, f); })),
          d.h("p.small.muted", null, t("market.overview.how"))),
        czechNote(),
        d.h("div.finding-grid", null, cards)
      ]);
      return { destroy: function () {} };
    }

    // ===== tasks ========================================================================================
    function buildTasks(panel) {
      var tasks = ctx.bundle.tasks || [];
      var host2 = d.h("div.market-tasks");
      d.fill(panel, host2);
      function render() {
        var p = ctx.profile();
        var done = tasks.filter(function (x) { return p.tasks[x.id]; }).length;
        var items = tasks.map(function (x) {
          var on = !!p.tasks[x.id];
          var id = "task-" + x.id;
          var box = d.h("input", { type: "checkbox", id: id, checked: on, onchange: function () {
            var res = ctx.apply(game.toggleTask, { id: x.id, done: box.checked, xp: x.xp });
            if (res.xp) ctx.sound("correct");
            render();
          } });
          return d.h("li.task" + (on ? ".is-done" : ""), { "data-id": x.id },
            d.h("label.task-head", { for: id }, box, d.h("span.task-title", null, x.title)),
            d.h("p.small.muted.task-why", null, x.why),
            d.h("div.chip-row", null,
              d.h("span.chip.tone-xp", null, "+" + x.xp + " XP"),
              on ? d.h("span.chip.tone-ok", null, icons.icon("check", { size: 13 }), d.h("span", null, t("market.tasks.doneOn", { date: d.fmtDate(p.tasks[x.id]) }))) : null,
              x.finding ? d.h("a.chip.chip-btn", { href: "#/market/overview", onclick: function () { state.tab = "overview"; } }, t("market.tasks.finding")) : null),
            d.h("details.task-steps", null, d.h("summary", null, t("market.tasks.steps")), d.h("ol", null, x.steps.map(function (s) { return d.h("li", null, s); }))));
        });
        d.fill(host2, [
          d.h("section.card", null,
            d.h("h2.card-title", null, t("market.tasks.title")),
            d.h("p", null, t("market.tasks.lead", { xp: game.XP.taskDone, chest: game.XP.tasksPerChest })),
            d.h("p.small.muted", null, t("market.tasks.honest")),
            charts.meter({ value: done, max: Math.max(1, tasks.length), size: "md", tone: "ok", label: t("market.tasks.progress", { a: done, b: tasks.length }), valueText: function () { return t("market.tasks.progress", { a: done, b: tasks.length }); } }),
            d.h("p.small", { "aria-live": "polite" }, t("market.tasks.progress", { a: done, b: tasks.length }))),
          d.h("ul.task-list", null, items)
        ]);
      }
      render();
      return { destroy: function () {} };
    }

    // ===== searches =====================================================================================
    function buildSearches(panel) {
      var vis = market.visibility || { rows: [], all: {} };
      var host2 = d.h("div.market-searches");
      d.fill(panel, host2);
      function table() {
        var rows = vis.rows.filter(function (r) { return state.group === "all" || r.group === state.group; }).map(function (r) {
          var top = r.top;
          return d.h("tr", null,
            d.h("td", { "data-label": t("market.vis.colQuery") }, d.h("button.link-btn", { type: "button", onclick: function () { state.openQuery = r.id; paintAll(); } }, r.query)),
            d.h("td", { "data-label": t("market.vis.colOwn") }, r.own_rank ? d.h("span.chip.tone-ok", null, t("market.place", { n: r.own_rank })) : d.h("span.chip", null, t("market.notFound"))),
            d.h("td", { "data-label": t("market.vis.colFirst") }, top ? [link(top.url, d.clip(top.title, 80)), " ", d.h("span.small.muted.host", null, top.host)] : ""));
        });
        var seg = widgets.segmented({
          label: t("market.group.label"), active: state.group,
          items: [{ id: "all", label: t("common.all") }].concat(GROUPS.map(function (g) { return { id: g, label: t("market.group." + g) }; })),
          onChange: function (id) { state.group = id; paintAll(); }
        });
        return d.h("section.card", null,
          d.h("h2.card-title", null, t("market.vis.title")),
          d.h("p", null, t("market.vis.lead", { own: (vis.all || {}).own || 0, n: (vis.all || {}).queries || 0 })),
          seg.el,
          d.h("div.table-scroll", null, d.h("table.data-table.stack", null,
            d.h("caption.sr-only", null, t("market.vis.title")),
            d.h("thead", null, d.h("tr", null, [t("market.vis.colQuery"), t("market.vis.colOwn"), t("market.vis.colFirst")].map(function (h) { return d.h("th", { scope: "col" }, h); }))),
            d.h("tbody", null, rows))));
      }
      function appendix() {
        var groups = {};
        everySearch.forEach(function (q) { (groups[q.group] = groups[q.group] || []).push(q); });
        var order = GROUPS.concat(Object.keys(groups).filter(function (g) { return GROUPS.indexOf(g) < 0; }));
        return d.h("section.card", null,
          d.h("h2.card-title", null, t("market.all.title")),
          d.h("p.small.muted", null, t("market.all.lead", { n: queries.length, d: direct.length })),
          order.filter(function (g) { return groups[g]; }).map(function (g) {
            return d.h("div.query-group", null,
              d.h("h3.sub", null, (GROUPS.indexOf(g) >= 0 || g === "direct" ? t("market.group." + g) : g) + " (" + groups[g].length + ")"),
              groups[g].map(function (q) {
                var det = d.h("details.query", { id: "q-" + q.id, open: state.openQuery === q.id },
                  d.h("summary", null, d.h("strong", null, q.id), " ", q.query, q.domains && q.domains.length ? d.h("span.small.muted.host", null, " " + t("market.onlySite", { s: q.domains.join(", ") })) : null),
                  d.h("p.small.muted", null, (q.purpose || "") + " " + t("market.retrieved", { date: d.fmtDate(q.retrieved_at) })),
                  d.h("ol.links", null, q.links.map(function (l) { return d.h("li", null, d.h("span.rk", null, String(l.rank)), " ", link(l.url, d.clip(l.title, 90)), " ", d.h("span.small.muted.host", null, host(l.url))); })));
                return det;
              }));
          }));
      }
      function paintAll() {
        d.fill(host2, [czechNote(), table(), appendix()]);
        if (state.openQuery) {
          var el = host2.querySelector("#q-" + state.openQuery);
          if (el) { el.open = true; d.raf(function () { el.scrollIntoView({ block: "center", behavior: ctx.reducedMotion() ? "auto" : "smooth" }); }); }
          state.openQuery = null;
        }
      }
      paintAll();
      return { destroy: function () {} };
    }

    // ===== competition ==================================================================================
    function buildCompetition(panel) {
      var land = market.landscape || { domains: [], types: {} };
      var vis = market.visibility || { market: { queries: 1 } };
      var n = (vis.market || {}).queries || 1;
      var bars = land.domains.slice(0, 22).map(function (x) {
        var width = Math.round(100 * x.queries / Math.max(1, n));
        return d.h("li", null,
          d.h("div.bar-head", null, d.h("b", null, x.name), " ", d.h("span.tag", null, land.types[x.type] || x.type), d.h("span.val", null, t("market.of", { a: x.queries, b: n }))),
          d.h("div.track", null, d.h("span", { style: { width: width + "%" } })),
          x.note ? d.h("div.small.muted", null, x.note) : null);
      });
      var ident = market.identity || { rows: [], about: [], quotes: [] };
      var identRows = ident.rows.map(function (r) {
        var share = Math.round(100 * r.lookalike / Math.max(1, r.links));
        return d.h("li", null,
          d.h("div.bar-head", null, d.h("button.link-btn", { type: "button", onclick: function () { openQuery(r.id); } }, r.query), d.h("span.val", null, t("market.identity.row", { a: r.lookalike, b: r.links }))),
          d.h("div.track.warm", null, d.h("span", { style: { width: share + "%" } })));
      });
      var about = ident.about.map(function (a) { return d.h("li", null, link(a.url, d.clip(a.title, 80)), " ", d.h("span.small.muted.host", null, a.host)); });
      var quotes = ident.quotes.map(function (q) {
        return d.h("blockquote", null, d.h("p", null, q.text), d.h("footer.small.muted", null, t("market.identity.machine", { id: q.id })));
      });
      var bs = market.brandsites || { themes: [] };
      var own = (market.own || {}).themes || {};
      var themeRows = bs.themes.map(function (th) {
        var ex = th.examples && th.examples[0];
        return d.h("tr", null,
          d.h("td", { "data-label": t("market.themes.colTheme") }, th.name), d.h("td.num", { "data-label": t("market.themes.colMakers") }, String(th.maker.pages)),
          d.h("td.num", { "data-label": t("market.themes.colMedia") }, String(th.media.pages)), d.h("td.num.mine", { "data-label": t("market.themes.colOwn") }, String(own[th.id] || 0)),
          d.h("td", { "data-label": t("market.themes.colExample") }, ex ? [link(ex.url, d.clip(ex.title, 60)), " ", d.h("span.small.muted.host", null, ex.site)] : ""));
      });
      d.fill(panel, [
        czechNote(),
        section(t("market.land.title"), t("market.land.lead", { n: n, links: land.links, hosts: land.hosts, noise: land.noise_links, other: land.unclassified_links }), d.h("ul.bars", null, bars)),
        section(t("market.identity.title"), t("market.identity.lead"), [
          d.h("h3.sub", null, t("market.identity.rows")), d.h("ul.bars", null, identRows),
          d.h("h3.sub", null, t("market.identity.about")), d.h("ul.plain", null, about),
          d.h("h3.sub", null, t("market.identity.quotes")), quotes.length ? quotes : d.h("p", null, t("market.identity.none"))]),
        section(t("market.themes.title"), t("market.themes.lead", { pages: bs.pages, sites: bs.sites_with_pages, makers: bs.makers, media: bs.media }),
          d.h("div.table-scroll", null, d.h("table.data-table.stack", null,
            d.h("caption.sr-only", null, t("market.themes.title")),
            d.h("thead", null, d.h("tr", null, [t("market.themes.colTheme"), t("market.themes.colMakers"), t("market.themes.colMedia"), t("market.themes.colOwn"), t("market.themes.colExample")].map(function (h) { return d.h("th", { scope: "col" }, h); }))),
            d.h("tbody", null, themeRows))))
      ]);
      return { destroy: function () {} };
    }

    // ===== claims =======================================================================================
    function buildClaims(panel) {
      var titles = market.own_titles || [];
      var audit = market.claims_audit || { examples: [] };
      var ownRows = titles.map(function (x) {
        var tr = TRAFFIC[x["class"]] || TRAFFIC.context;
        return d.h("tr", null,
          d.h("td", { "data-label": t("market.own.colPage") }, link(x.url, x.title)), d.h("td", { "data-label": t("market.own.colTopic") }, x.topic),
          d.h("td", { "data-label": t("market.own.colRule") }, d.h("span.chip.tone-" + tr[0], null, t(tr[1]))),
          d.h("td", { "data-label": t("market.own.colSafer") }, x.safe));
      });
      var examples = audit.examples.map(function (e) {
        return d.h("tr", null,
          d.h("td", { "data-label": t("market.audit.colWho") }, e.name), d.h("td", { "data-label": t("market.audit.colTitle") }, link(e.url, d.clip(e.title, 90))),
          d.h("td", { "data-label": t("market.audit.colRule") }, e.rule), d.h("td", { "data-label": t("market.audit.colPart") }, d.h("mark", null, e.fragment)));
      });
      d.fill(panel, [
        czechNote(),
        section(t("market.own.title"), titles.length ? t("market.own.lead", { a: titles.length, b: ((market.own || {}).pages || []).length }) : t("market.own.none"),
          titles.length ? d.h("div.table-scroll", null, d.h("table.data-table.stack", null,
            d.h("caption.sr-only", null, t("market.own.title")),
            d.h("thead", null, d.h("tr", null, [t("market.own.colPage"), t("market.own.colTopic"), t("market.own.colRule"), t("market.own.colSafer")].map(function (h) { return d.h("th", { scope: "col" }, h); }))),
            d.h("tbody", null, ownRows))) : null),
        section(t("market.audit.title"), t("market.audit.lead", { a: audit.flagged, b: audit.scanned }),
          [d.h("div.table-scroll", null, d.h("table.data-table.stack", null,
            d.h("caption.sr-only", null, t("market.audit.title")),
            d.h("thead", null, d.h("tr", null, [t("market.audit.colWho"), t("market.audit.colTitle"), t("market.audit.colRule"), t("market.audit.colPart")].map(function (h) { return d.h("th", { scope: "col" }, h); }))),
            d.h("tbody", null, examples))),
            d.h("p.small.muted", null, t("market.audit.note")),
            d.h("a.btn.btn-ghost.btn-sm", { href: "#/vault/claims" }, icons.icon("shieldCheck", { size: 16 }), d.h("span", null, t("edition.openMap")))])
      ]);
      return { destroy: function () {} };
    }

    // ===== method =======================================================================================
    function buildMethod(panel) {
      var meta = market.meta || {};
      var real = (ctx.bundle.meta && ctx.bundle.meta.real) || {};
      var val = (market.validation || []).map(function (v) {
        return d.h("tr", null, d.h("td", { "data-label": t("market.valid.colQuery") }, v.query), d.h("td.num", { "data-label": t("market.valid.colShared") }, t("market.of", { a: v.shared, b: v.direct_links })),
          d.h("td", { "data-label": t("market.valid.colOrder") }, v.same_order ? t("common.yes") : t("common.no")));
      });
      var items = (market.open_items || []).map(function (x) {
        return d.h("li", null, d.h("b", null, x.what), d.h("br"), x.why, d.h("br"), d.h("span.need", null, t("market.missing.need") + " " + x.need));
      });
      var model = real.model;
      d.fill(panel, [
        czechNote(),
        section(t("market.method.title"), null, [
          d.h("p", null, t("market.method.how", { n: meta.searches, date: d.fmtDate(meta.date), tool: meta.tool })),
          d.h("ul.plain", null, ["market.method.l1", "market.method.l2", "market.method.l3", "market.method.l4"].map(function (k) { return d.h("li", null, t(k)); })),
          model && model.pct !== null && model.pct !== undefined ? d.h("p", null, t("market.method.model", { pct: d.fmt(model.pct, 1), n: model.decided, pairs: model.pairs })) : null]),
        section(t("market.valid.title"), t("market.valid.lead"), d.h("div.table-scroll", null, d.h("table.data-table", null,
          d.h("caption.sr-only", null, t("market.valid.title")),
          d.h("thead", null, d.h("tr", null, [t("market.valid.colQuery"), t("market.valid.colShared"), t("market.valid.colOrder")].map(function (h) { return d.h("th", { scope: "col" }, h); }))),
          d.h("tbody", null, val)))),
        section(t("market.missing.title"), t("market.missing.lead"), d.h("ul.open", null, items))
      ]);
      return { destroy: function () {} };
    }

    var builders = { overview: buildOverview, tasks: buildTasks, searches: buildSearches, competition: buildCompetition, claims: buildClaims, method: buildMethod };
    var items = TABS.map(function (id) {
      return { id: id, label: t("market.tab." + id), icon: { overview: "chart", tasks: "check", searches: "globe", competition: "users", claims: "shieldCheck", method: "info" }[id] };
    });
    tabs = widgets.tabs({
      label: t("market.tabs"), active: state.tab, items: items,
      onChange: function (id, panel) {
        state.tab = id;
        if (current && current.destroy) current.destroy();
        d.clear(panel);
        current = builders[id](panel);
        try { root.history.replaceState(null, "", "#/market/" + id); } catch (e) { /* file:// in some browsers */ }
      }
    });
    d.fill(page, [
      d.h("div.arena-head", null,
        d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("market.title")),
        d.h("p.page-lead", null, t("market.lead"))),
      tabs.el, tabs.panel
    ]);
    return { destroy: function () { if (current && current.destroy) current.destroy(); } };
  }

  return { mount: mount, TABS: TABS };
});
