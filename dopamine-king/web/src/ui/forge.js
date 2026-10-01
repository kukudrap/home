/* Forge: content packs. Renders a Pack (bundle.forge_samples[0], or the result of /api/forge in live mode):
 * one tab per format with the hook and its score meter, the body with open [[ADD: ...]] slots highlighted,
 * issues as severity badges, the Trust Shield verdict and alternative hooks. In live mode (kingctl serve) a
 * brief form posts to /api/forge. Every field is optional: missing data never breaks the view.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.forge = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var FAMILY_ICON = { social: "users", article: "book", video: "play", ad: "megaphone", email: "send", audio: "speaker", hooks: "bolt" };
  var VERDICT = { ok: { shield: "intact", icon: "shieldCheck", tone: "ok" }, review: { shield: "cracked", icon: "alert", tone: "warn" }, blocked: { shield: "broken", icon: "x", tone: "risk" } };
  var SEVERITY = { error: { icon: "x", tone: "risk" }, warn: { icon: "alert", tone: "warn" }, info: { icon: "info", tone: "info" } };
  var GOALS = ["awareness", "consideration", "conversion", "retention", "community"];
  var DRIVERS = ["curiosity", "surprise", "emotion", "relevance", "utility", "fluency"];

  // Shared by Forge and Guru: what the player typed and what the server returned last.
  var shared = {
    brief: { brand: "", topic: "", audience: "", goal: "awareness", lang: null, tone: "friendly, direct, no hype", keyword: "", facts: "", offer: "", cta: "" },
    formats: [], offline: false, seeded: false
  };
  var forgeState = { pack: null, active: null, busy: false, message: null };

  /** The sample written in the UI language, else the first one. */
  function pickByLang(samples, lang) {
    for (var i = 0; i < samples.length; i++) {
      if (samples[i] && samples[i].brief && samples[i].brief.lang === lang) return samples[i];
    }
    return samples[0] || null;
  }

  function seedBrief(ctx, brief) {
    if (shared.seeded || !brief) return;
    shared.seeded = true;
    var b = shared.brief;
    ["brand", "topic", "audience", "goal", "tone", "keyword", "offer", "cta"].forEach(function (k) { if (brief[k]) b[k] = brief[k]; });
    if (Array.isArray(brief.facts)) b.facts = brief.facts.join("\n");
    if (brief.lang === "cs" || brief.lang === "en") b.lang = brief.lang;
  }

  /** Brief to the object the API expects: empty fields are left out, facts become a list. */
  function briefToApi(b) {
    var out = { brand: b.brand.trim(), topic: b.topic.trim(), audience: b.audience.trim(), goal: b.goal, lang: b.lang || "en", tone: b.tone.trim() };
    if (b.keyword.trim()) out.keyword = b.keyword.trim();
    if (b.offer.trim()) out.offer = b.offer.trim();
    if (b.cta.trim()) out.cta = b.cta.trim();
    var facts = b.facts.split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean);
    if (facts.length) out.facts = facts;
    return out;
  }

  /**
   * The brief form shared by Forge and Guru. opts: {ctx, withFormats, formats (api list), submitLabel, extra (node
   * placed above the submit row), onSubmit(brief, formats, writer)}. Returns {el, setBusy(on), setMessage(text, tone), setFormats(list)}.
   */
  function briefForm(opts) {
    var ctx = opts.ctx;
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, widgets = root.DK.ui.widgets;
    var t = d.t;
    var b = shared.brief;
    if (!b.lang) b.lang = ctx.lang();
    function text(key, label, o) {
      o = o || {};
      var input = d.h(o.area ? "textarea.input" : "input.input", { id: "bf-" + key, type: o.area ? null : "text", rows: o.area ? 4 : null, value: b[key] || "", autocomplete: "off", placeholder: o.placeholder || null, required: !!o.required, "aria-required": o.required ? "true" : null, maxlength: o.max || 400 });
      input.addEventListener("input", function () { b[key] = input.value; });
      return widgets.field(label + (o.required ? " *" : ""), input, o.hint);
    }
    var goalSel = d.h("select.input", { id: "bf-goal", onchange: function () { b.goal = goalSel.value; } },
      GOALS.map(function (g) { return d.h("option", { value: g, selected: b.goal === g }, t("forge.goal." + g)); }));
    var langSel = d.h("select.input", { id: "bf-lang", onchange: function () { b.lang = langSel.value; } },
      ["cs", "en"].map(function (l) { return d.h("option", { value: l, selected: b.lang === l }, l === "cs" ? t("arena.langCs") : t("arena.langEn")); }));

    var formatHost = d.h("fieldset.fieldset", null, d.h("legend", null, t("forge.formats")));
    function drawFormats() {
      d.clear(formatHost);
      formatHost.appendChild(d.h("legend", null, t("forge.formats")));
      var list = opts.formats || [];
      if (!list.length) { formatHost.appendChild(d.h("p.small.muted", null, t("forge.formatsNone"))); return; }
      if (!shared.formats.length) shared.formats = list.slice(0, 3).map(function (f) { return f.id; });
      var grid = d.h("div.checks");
      list.forEach(function (f) {
        var cb = d.h("input", { type: "checkbox", value: f.id, checked: shared.formats.indexOf(f.id) >= 0, onchange: function () {
          var i = shared.formats.indexOf(f.id);
          if (cb.checked && i < 0) shared.formats.push(f.id);
          if (!cb.checked && i >= 0) shared.formats.splice(i, 1);
        } });
        grid.appendChild(d.h("label.check", null, cb, d.h("span", null, ctx.pick(f, "name") || f.id, d.h("small.muted", null, " " + (f.platform || f.family || "")))));
      });
      formatHost.appendChild(grid);
    }
    if (opts.withFormats) drawFormats();

    var offlineSw = opts.withFormats ? widgets.switchControl({ label: t("forge.offlineWriter"), checked: shared.offline, onChange: function (on) { shared.offline = on; } }) : null;
    var msg = d.h("p.form-msg", { role: "status" });
    var submit = d.h("button.btn.btn-primary.btn-lg", { type: "submit" }, icons.icon("forge", { size: 20 }), d.h("span", null, opts.submitLabel));
    var spin = widgets.spinner();
    spin.hidden = true;

    var form = d.h("form.brief-form", { novalidate: true, onsubmit: function (e) {
      e.preventDefault();
      var missing = ["brand", "topic", "audience"].filter(function (k) { return !String(b[k]).trim(); });
      if (missing.length) {
        msg.textContent = t("forge.missing");
        msg.className = "form-msg is-bad";
        var first = form.querySelector("#bf-" + missing[0]);
        if (first) first.focus();
        return;
      }
      if (opts.withFormats && !shared.formats.length) { msg.textContent = t("forge.pickFormat"); msg.className = "form-msg is-bad"; return; }
      msg.textContent = "";
      opts.onSubmit(briefToApi(b), shared.formats.slice(), shared.offline ? "offline" : undefined);
    } },
      d.h("div.form-grid.two", null,
        text("brand", t("forge.brand"), { required: true }),
        text("topic", t("forge.topic"), { required: true, hint: t("forge.topicHint") }),
        text("audience", t("forge.audience"), { required: true }),
        widgets.field(t("forge.goal"), goalSel),
        widgets.field(t("forge.language"), langSel),
        text("tone", t("forge.tone")),
        text("keyword", t("forge.keyword")),
        text("offer", t("forge.offer")),
        text("cta", t("forge.cta")),
        d.h("div.span-2", null, text("facts", t("forge.facts"), { area: true, hint: t("forge.factsHint"), max: 1500 }))),
      opts.withFormats ? formatHost : null,
      offlineSw ? offlineSw.el : null,
      opts.extra || null,
      d.h("div.row.wrap", null, submit, spin, msg));
    return {
      el: form,
      setBusy: function (on) { submit.disabled = on; spin.hidden = !on; form.setAttribute("aria-busy", on ? "true" : "false"); },
      setMessage: function (text2, tone) { msg.textContent = text2 || ""; msg.className = "form-msg" + (tone ? " is-" + tone : ""); },
      setFormats: function (list) { opts.formats = list; drawFormats(); }
    };
  }

  var MARK_RE = /(\[\[(?:ADD|DOPLŇTE|cite)\b[\s\S]*?\]\])/g;

  /** **bold** and `code` inside a piece of text. */
  function inlineNodes(str, d) {
    var out = [];
    String(str).split(/(\*\*[^*\n]+\*\*|`[^`\n]+`)/g).forEach(function (part) {
      if (/^\*\*[^*]+\*\*$/.test(part)) out.push(d.h("strong", null, part.slice(2, -2)));
      else if (/^`[^`]+`$/.test(part)) out.push(d.h("code.inline", null, part.slice(1, -1)));
      else if (part) out.push(part);
    });
    return out;
  }

  /**
   * Text as an array of strings and nodes: [[ADD: ...]] placeholders (the writer's open slots) become
   * highlighted slots, [[cite:id]] marks become citation marks, **bold** and `code` are styled. Shared with Guru.
   */
  function slotNodes(text, d, icons) {
    var out = [];
    String(text || "").split(MARK_RE).forEach(function (p) {
      if (/^\[\[(?:ADD|DOPLŇTE)\b/.test(p)) out.push(d.h("span.slot", null, icons.icon("pencil", { size: 13 }), d.h("span", null, p)));
      else if (/^\[\[cite\b/.test(p)) out.push(d.h("span.cite", null, icons.icon("book", { size: 13 }), d.h("span", null, p)));
      else out.push.apply(out, inlineNodes(p, d));
    });
    return out;
  }

  /** Draft text: slots are highlighted, Markdown headings become headings, blank lines stay as spacing. */
  function renderBody(text, d, icons) {
    var lines = String(text || "").split(/\r?\n/);
    var wrap = d.h("div.pack-body");
    lines.forEach(function (line) {
      var level = 0;
      var m = /^(#{1,3})\s+(.*)$/.exec(line);
      var content = line;
      if (m) { level = m[1].length; content = m[2]; }
      wrap.appendChild(d.h("div.md-line" + (level ? ".md-h" + level : "") + (line.trim() ? "" : ".md-blank"), null, slotNodes(content, d, icons)));
    });
    return wrap;
  }

  /** After a live response: bring the new result into view and move keyboard focus to its heading. */
  function showResult(page, headingId) {
    var d = root.DK.ui.dom;
    d.raf(function () {
      var h = page.querySelector("#" + headingId);
      if (!h) return;
      h.setAttribute("tabindex", "-1");
      try { h.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
      var target = h.closest(".card") || h;
      if (typeof target.scrollIntoView === "function") target.scrollIntoView({ block: "start", behavior: d.reducedMotion() ? "auto" : "smooth" });
    });
  }

  function mount(container, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets, scoring = root.DK.scoring;
    var t = d.t;
    var page = d.h("div.page.forge");
    container.appendChild(page);
    var live = ctx.live();
    var sample = pickByLang(ctx.bundle.forge_samples || [], ctx.lang());
    var pack = forgeState.pack || sample;
    var isSample = !forgeState.pack;
    var current = null;
    var formatsList = live.formats;
    var alive = true;
    seedBrief(ctx, sample && sample.brief);

    function verdictBadge(v) {
      var meta = VERDICT[v] || VERDICT.review;
      return d.h("span.chip.tone-" + meta.tone + ".verdict-chip", null, icons.icon(meta.icon, { size: 14 }), d.h("span", null, t("forge.verdict." + (VERDICT[v] ? v : "review"))));
    }

    function scoreTile(label, value, note, digits) {
      return d.h("div.stat-box", null, d.h("span.stat-label", null, label), d.h("strong.num", null, typeof value === "number" ? d.fmt(value, digits === undefined ? 1 : digits) : "-"), note ? d.h("span.small.muted", null, note) : null);
    }

    function scoreFor(item) {
      var hs = item.hook_score;
      if (hs && typeof hs.total === "number" && hs.parts) return hs;
      try { return scoring.scoreHook(item.hook || "", "", { lang: pack.brief && pack.brief.lang === "cs" ? "cs" : (pack.brief && pack.brief.lang === "en" ? "en" : undefined), spec: ctx.bundle.spec }); } catch (e) { return null; }
    }

    function hookCard(item) {
      var hs = scoreFor(item);
      var total = hs ? hs.total : (item.scores && typeof item.scores.dopamine === "number" ? item.scores.dopamine : 0);
      var risk = hs ? hs.clickbait_risk : 0;
      var st = scoring.shieldState(risk);
      var meter = charts.meter({ value: 0, max: 100, size: "lg", tone: "brand", label: t("forge.hookScore"), valueText: function (v) { return Math.round(v) + " / 100"; } });
      d.raf(function () { meter.set(total); });
      var num = d.h("span.num.score-num", null, "0");
      d.tween({ from: 0, to: total, ms: 800, onUpdate: function (v) { num.textContent = v.toFixed(1); } });
      var tips = hs && hs.tips ? hs.tips : [];
      return d.h("section.card.hook-card-pack", { "aria-labelledby": "hook-h" },
        d.h("div.editor-head", null,
          d.h("h3.card-title", { id: "hook-h" }, t("forge.hook")),
          widgets.copyButton(item.hook || "", t("common.copy"))),
        d.h("p.pack-hook", null, item.hook || ""),
        d.h("div.score-row", null,
          d.h("div.score-big", null, num, d.h("span.score-of", null, "/ 100")),
          d.h("div.score-meter", null, meter)),
        d.h("div.shield-line", null, icons.shield(st, 34), d.h("span", null, d.h("strong", null, t("boss.shield." + st)), " ", t("boss.riskPct", { n: Math.round(risk * 100) }))),
        hs && hs.parts ? charts.driverBars({ labels: ctx.bundle.spec.labels, lang: ctx.lang(), drivers: DRIVERS, parts: hs.parts, compact: true }) : null,
        tips.length ? d.h("ul.tip-list", null, tips.map(function (tip) { return d.h("li", null, icons.icon(tip.key === "ship_it" ? "check" : "bulb", { size: 16 }), d.h("span", null, d.typo(tip[ctx.lang()] || tip.en))); })) : null,
        d.h("p.small.muted", null, t("forge.scoreNote")));
    }

    function issuesCard(item) {
      var issues = item.issues || [];
      var v = VERDICT[item.verdict] ? item.verdict : "review";
      var lines = {
        ok: t("forge.shield.ok"), review: t("forge.shield.review"), blocked: t("forge.shield.blocked")
      };
      return d.h("section.card.issues-card", { "aria-labelledby": "issues-h" },
        d.h("h3.card-title", { id: "issues-h" }, t("forge.issues")),
        d.h("div.verdict-box.is-" + v, null, icons.shield(VERDICT[v].shield, 44), d.h("div", null, d.h("strong", null, t("forge.trust")), verdictBadge(v), d.h("p.small", null, lines[v]))),
        issues.length
          ? d.h("ul.issue-list", null, issues.map(function (is) {
            var sv = SEVERITY[is.severity] ? is.severity : "info";
            return d.h("li.issue.sev-" + sv, null,
              d.h("span.chip.tone-" + SEVERITY[sv].tone, null, icons.icon(SEVERITY[sv].icon, { size: 13 }), d.h("span", null, t("forge.sev." + sv))),
              d.h("div.issue-text", null, d.h("code.issue-code", null, is.code || ""), d.h("span", null, is.message || ""), is.where ? d.h("span.small.muted", null, t("forge.where", { w: is.where })) : null));
          }))
          : d.h("p.small.muted", null, t("forge.noIssues")));
    }

    function altCard(item, hs) {
      var alts = item.alt_hooks || [];
      if (!alts.length) return null;
      var base = hs ? hs.total : 0;
      return d.h("section.card", { "aria-labelledby": "alt-h" },
        d.h("h3.card-title", { id: "alt-h" }, t("forge.alts")),
        d.h("ul.alt-list", null, alts.map(function (a) {
          var diff = typeof a.score === "number" ? a.score - base : null;
          return d.h("li.alt", null,
            d.h("div.alt-main", null, d.h("p.alt-text", null, a.text), d.h("div.chip-row", null,
              a.style ? d.h("span.chip", null, a.style.replace(/_/g, " ")) : null,
              typeof a.score === "number" ? d.h("span.chip.tone-brand", null, t("forge.altScore", { n: d.fmt(a.score, 1) })) : null,
              diff !== null ? d.h("span.chip" + (diff >= 0 ? ".tone-ok" : ""), null, t("forge.vsCurrent", { d: d.fmtSigned(diff, 1) })) : null)),
            widgets.copyButton(a.text, t("common.copy")));
        })));
    }

    function itemPanel(panel, item) {
      var hs = scoreFor(item);
      var scores = item.scores || {};
      var openSlots = (item.slots_open || []).length;
      d.fill(panel, [
        d.h("section.card.item-head", null,
          d.h("div.item-title", null,
            d.h("h2.card-title", null, ctx.pick(item, "name") || item.format),
            d.h("div.chip-row", null,
              item.family ? d.h("span.chip", null, icons.icon(FAMILY_ICON[item.family] || "layers", { size: 13 }), d.h("span", null, item.family)) : null,
              verdictBadge(item.verdict),
              openSlots ? d.h("span.chip.tone-warn", null, icons.icon("pencil", { size: 13 }), d.h("span", null, ctx.tp("forge.openSlots", openSlots))) : null)),
          d.h("div.stat-boxes", null,
            scoreTile(t("forge.dopamine"), scores.dopamine, t("common.heuristic")),
            scores.seo !== null && scores.seo !== undefined ? scoreTile("SEO", scores.seo) : null,
            scores.geo !== null && scores.geo !== undefined ? scoreTile("GEO", scores.geo) : null)),
        hookCard(item),
        d.h("section.card.body-card", { "aria-labelledby": "body-h" },
          d.h("div.editor-head", null, d.h("h3.card-title", { id: "body-h" }, t("forge.body")), widgets.copyButton(item.body || "", t("common.copy"))),
          openSlots ? d.h("p.small.upset-note", null, icons.icon("pencil", { size: 15 }), d.h("span", null, t("forge.slotsNote"))) : null,
          renderBody(item.body, d, icons)),
        issuesCard(item),
        altCard(item, hs)
      ]);
    }

    function packView() {
      var items = (pack && pack.items) || [];
      if (!pack || !items.length) {
        return widgets.emptyState({ icon: "forge", title: t("forge.empty.title"), text: live.enabled ? t("forge.empty.live") : t("forge.empty.offline") });
      }
      var sum = pack.summary || {};
      var activeId = items.some(function (i) { return i.format === forgeState.active; }) ? forgeState.active : items[0].format;
      var tabs = widgets.tabs({
        label: t("forge.formatTabs"), active: activeId,
        items: items.map(function (it) {
          var v = VERDICT[it.verdict] ? it.verdict : "review";
          return { id: it.format, label: [ctx.pick(it, "name") || it.format, d.h("span.tab-verdict.v-" + v, null, icons.icon(VERDICT[v].icon, { size: 14, stroke: 2.6 }), d.h("span.sr-only", null, " " + t("forge.verdict." + v)))] };
        }),
        onChange: function (id, panel) {
          forgeState.active = id;
          itemPanel(panel, items.filter(function (i) { return i.format === id; })[0]);
        }
      });
      return d.h("section", { "aria-labelledby": "pack-h" },
        d.h("div.card.pack-head", null,
          d.h("div.editor-head", null,
            d.h("h2.card-title", { id: "pack-h" }, isSample ? t("forge.sampleTitle", { brand: (pack.brief && pack.brief.brand) || "" }) : t("forge.packTitle", { brand: (pack.brief && pack.brief.brand) || "" })),
            d.h("div.chip-row", null,
              d.h("span.chip.tone-info", null, icons.icon("pencil", { size: 13 }), d.h("span", null, t("forge.writer", { w: pack.writer || "offline" }))),
              pack.created ? d.h("span.chip", null, String(pack.created).slice(0, 10)) : null)),
          d.h("div.stat-boxes.five", null,
            scoreTile(t("forge.sumItems"), sum.n_items === undefined ? items.length : sum.n_items, null, 0),
            scoreTile(t("forge.sumAvg"), sum.avg_dopamine, null, 1),
            scoreTile(t("forge.sumErrors"), sum.errors, null, 0),
            scoreTile(t("forge.sumWarnings"), sum.warnings, null, 0),
            scoreTile(t("forge.sumSlots"), sum.open_slots, null, 0)),
          isSample ? d.h("p.small.sim-note", null, icons.icon("flask", { size: 15 }), d.h("span", null, t("forge.sampleNote"))) : d.h("p.small.muted", null, t("forge.liveNote"))),
        pack.errors && pack.errors.length
          ? d.h("div.card.pack-errors", { role: "note" }, d.h("p.small", null, icons.icon("alert", { size: 16 }), d.h("strong", null, " " + t("forge.packErrors"))), d.h("ul.small", null, pack.errors.map(function (e) { return d.h("li", null, String(e)); })))
          : null,
        tabs.el, tabs.panel);
    }

    function liveBox() {
      if (!live.enabled) {
        return d.h("section.card.run-live", { "aria-labelledby": "rl-h" },
          d.h("h2.card-title", { id: "rl-h" }, icons.icon("send", { size: 20 }), t("forge.runLive")),
          d.h("p", null, t("forge.runLiveText")),
          d.h("pre.code", null, "kingctl serve"),
          d.h("div.row.wrap", null, widgets.copyButton("kingctl serve", t("common.copy")), d.h("span.small.muted", null, t("forge.runLiveHint"))));
      }
      var form = briefForm({
        ctx: ctx, withFormats: true, formats: formatsList, submitLabel: t("forge.generate"),
        onSubmit: function (brief, formats, writer) {
          form.setBusy(true);
          form.setMessage(t("forge.working"), null);
          var body = { brief: brief, formats: formats };
          if (writer) body.writer = writer;
          ctx.api.forge(body).then(function (res) {
            if (!res || !Array.isArray(res.items)) throw new Error(t("forge.badResponse"));
            forgeState.pack = res;
            forgeState.active = res.items[0] ? res.items[0].format : null;
            pack = res;
            isSample = false;
            if (alive) { render(); showResult(page, "pack-h"); }
            d.announce(t("forge.done", { n: res.items.length }));
          }).catch(function (err) {
            form.setBusy(false);
            form.setMessage(t("forge.failed", { e: err && err.message ? err.message : "?" }), "bad");
          });
        }
      });
      if (!formatsList) {
        ctx.api.formats().then(function (list) {
          live.formats = Array.isArray(list) ? list : [];
          formatsList = live.formats;
          if (alive) form.setFormats(formatsList);
        }).catch(function () { if (alive) form.setMessage(t("forge.formatsFailed"), "bad"); });
      }
      return d.h("section.card.live-form", { "aria-labelledby": "lf-h" },
        d.h("div.editor-head", null, d.h("h2.card-title", { id: "lf-h" }, icons.icon("send", { size: 20 }), t("forge.formTitle")), d.h("span.chip.tone-ok", null, icons.icon("spark", { size: 13 }), d.h("span", null, t("top.live")))),
        d.h("p.small.muted", null, t("forge.formIntro")), form.el);
    }

    function render() {
      d.fill(page, [
        d.h("div.arena-head", null,
          d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, t("forge.title")),
          d.h("p.page-lead", null, t("forge.lead"))),
        live.enabled ? liveBox() : null,
        packView(),
        live.enabled ? null : liveBox()
      ]);
    }
    render();
    return { destroy: function () { alive = false; current = null; } };
  }

  return { mount: mount, briefForm: briefForm, briefToApi: briefToApi, renderBody: renderBody, slotNodes: slotNodes, seedBrief: seedBrief, pickByLang: pickByLang, showResult: showResult, _shared: shared, _state: forgeState };
});
