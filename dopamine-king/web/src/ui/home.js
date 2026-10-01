/* Home: the daily loop in one place. Three quests, the chest, Oracle rating, play time today, the next
 * best action and a plain-language "How XP works" panel.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.home = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var QUEST_ICON = { arena: "swords", boss: "skull", lab: "flask", vault: "vault" };

  function routeHref(route, params) {
    var q = params ? "?" + Object.keys(params).map(function (k) { return k + "=" + encodeURIComponent(params[k]); }).join("&") : "";
    return "#/" + route + q;
  }

  function mount(container, ctx) {
    var d = root.DK.ui.dom, icons = root.DK.ui.icons, charts = root.DK.ui.charts, widgets = root.DK.ui.widgets, game = root.DK.game;
    var t = d.t;
    var page = d.h("div.page.home");
    container.appendChild(page);
    var firstPaint = true;

    function nextActionView(p, today) {
      var a = game.nextBestAction(p, today);
      var label;
      if (a.key === "chest") label = t("home.next.chest");
      else if (a.key === "quest") label = t("home.next.quest", { quest: t("quest." + a.quest, { n: game.questDef(a.quest).target }) });
      else if (a.key === "oracle") label = t("home.next.oracle");
      else label = t("home.next.boss");
      return { href: routeHref(a.route, a.params), label: label, key: a.key };
    }

    function questRow(q) {
      var pct = q.progress / q.target;
      var def = game.questDef(q.id);
      return d.h("li.quest" + (q.done ? ".is-done" : ""), null,
        d.h("span.quest-mark", { "aria-hidden": "true" }, q.done ? icons.icon("check", { size: 20, stroke: 2.6 }) : icons.icon(QUEST_ICON[q.route] || "star", { size: 20 })),
        d.h("div.quest-main", null,
          d.h("div.quest-title", null, t("quest." + q.id, { n: def.target })),
          d.h("div.quest-progress", null,
            charts.meter({ value: q.progress, max: q.target, size: "sm", tone: q.done ? "ok" : "brand", label: t("quest." + q.id, { n: def.target }), valueText: function () { return q.progress + " / " + q.target; } }),
            d.h("span.quest-count", null, q.progress + "/" + q.target))),
        q.done
          ? d.h("span.chip.tone-ok", null, icons.icon("check", { size: 13 }), d.h("span", null, t("home.quests.done")))
          : d.h("a.btn.btn-ghost.btn-sm", { href: routeHref(q.route, q.params), "aria-label": t("home.quests.go") + ": " + t("quest." + q.id, { n: def.target }) }, t("home.quests.go")),
        d.h("span.chip.tone-xp.quest-xp", null, "+" + q.xp + " XP"));
    }

    function statCard(title, body) {
      return d.h("section.card.stat-card", null, d.h("h3.stat-title", null, title), body);
    }

    function render() {
      var p = ctx.profile();
      var today = ctx.today();
      var lang = ctx.lang();
      var lp = game.levelProgress(p.xp);
      var quests = game.questView(p, today);
      var doneCount = quests.filter(function (q) { return q.done; }).length;
      var next = nextActionView(p, today);
      var oracle = game.oracleRating(p.brier);
      var st = game.streakStatus(p, today);
      var minutes = game.playMinutesToday(p, today);
      var acc = p.stats.arenaPlayed ? Math.round(100 * p.stats.arenaCorrect / p.stats.arenaPlayed) : null;
      var needOracle = Math.max(0, game.ORACLE_MIN_ANSWERS - p.brier.n);

      var hero = d.h("section.card.hero", null,
        d.h("div.hero-main", null,
          d.h("p.eyebrow", null, t("app.tagline")),
          d.h("h1.page-title", { id: "view-title", tabindex: "-1" }, p.name ? t("home.helloName", { name: p.name }) : t("home.hello")),
          d.h("p.hero-lead", null, t("home.lead")),
          d.h("div.hero-level", null,
            d.h("span.lvl-badge.big", { "aria-hidden": "true" }, String(lp.level)),
            d.h("div.hero-level-body", null,
              d.h("strong", null, game.levelTitle(lp.level, lang)),
              charts.meter({ value: lp.pct * 100, max: 100, size: "sm", tone: "xp", label: t("top.level", { n: lp.level }), valueText: function () { return lp.into + " / " + lp.span + " XP"; } }),
              d.h("span.small.muted", null, t("home.xpLine", { xp: d.fmt(p.xp), n: d.fmt(lp.next - p.xp), level: lp.level + 1 })))),
          d.h("a.btn.btn-primary.btn-lg.hero-cta", { href: next.href }, d.h("span", null, next.label), icons.icon("arrowRight", { size: 20 }))),
        d.h("div.hero-art", { "aria-hidden": "true" }, icons.logo(120)));

      var questsCard = d.h("section.card.quests", { "aria-labelledby": "quests-title" },
        widgets.heading(2, t("home.quests.title"), t("home.quests.sub"), d.h("span.chip.tone-brand", null, t("common.of", { a: doneCount, b: quests.length }))),
        d.h("ul.quest-list", null, quests.map(questRow)),
        doneCount === quests.length
          ? d.h("p.quest-bonus.is-on", null, icons.icon("vault", { size: 18 }), d.h("span", null, t("home.quests.allDone")))
          : d.h("p.quest-bonus", null, icons.icon("vault", { size: 18 }), d.h("span", null, t("home.quests.bonus"))));
      questsCard.querySelector("h2").id = "quests-title";

      var chestCard = d.h("section.card.chest-card", null,
        d.h("div.chest-art", { "aria-hidden": "true" }, icons.chest({ size: 112 })),
        d.h("div.chest-info", null,
          d.h("h2.card-title", null, t("home.chest.title")),
          p.chestsReady > 0
            ? d.h("p.chest-count", null, ctx.tp("home.chest.ready", p.chestsReady))
            : d.h("p.muted", null, t("home.chest.none")),
          d.h("p.small.muted", null, t("home.chest.pity", { n: p.pity, max: ctx.bundle.loot ? ctx.bundle.loot.pity_after : 8 })),
          d.h("div.row.wrap", null,
            d.h("a.btn" + (p.chestsReady > 0 ? ".btn-primary" : ".btn-ghost"), { href: "#/vault" }, icons.icon("vault", { size: 18 }), t("home.chest.open")),
            d.h("a.link.small", { href: "#/vault" }, t("home.chest.odds")))));

      var oracleRing = charts.ring({ value: oracle === null ? 0 : oracle, max: 100, size: 92, stroke: 9, tone: "info", text: oracle === null ? "?" : String(Math.round(oracle)), label: t("home.oracle.title") + ": " + (oracle === null ? t("home.oracle.locked", { n: needOracle }) : Math.round(oracle)) });
      var oracleCard = statCard(t("home.oracle.title"), d.h("div.stat-body.col", null, oracleRing,
        d.h("p.small", null, oracle === null ? t("home.oracle.locked", { n: needOracle }) : t("home.oracle.hint"))));

      var timeCard = statCard(t("home.time.title"), d.h("div.stat-body.col", null,
        d.h("span.big-num", null, d.fmtMinutes(minutes)),
        d.h("p.small.muted", null, p.settings.sessionMinutes > 0 ? t("home.time.hint", { n: p.settings.sessionMinutes }) : t("home.time.hintOff"))));

      var streakCard = statCard(t("home.streak.title"), d.h("div.stat-body.col", null,
        d.h("div.row", null, icons.flame(34, st.alive), d.h("span.big-num", null, ctx.tp("home.streak.days", st.streak))),
        d.h("p.small.muted", null, t("home.streak.best", { n: p.bestStreak }) + " · " + t("home.streak.freezes", { n: p.freezeTokens })),
        d.h("p.small.muted", null, st.alive || st.streak === 0 ? t("home.streak.hint") : t("home.streak.fresh"))));

      var accCard = statCard(t("home.accuracy.title"), d.h("div.stat-body.col", null,
        d.h("span.big-num", null, acc === null ? "-" : acc + " %"),
        d.h("p.small.muted", null, acc === null ? t("home.accuracy.none") : t("home.accuracy.hint", { a: p.stats.arenaCorrect, b: p.stats.arenaPlayed }))));

      var modes = d.h("section", { "aria-labelledby": "modes-title" },
        widgets.heading(2, t("home.modes.title")),
        d.h("ul.mode-grid", null, [
          ["arena", "swords"], ["boss", "skull"], ["lab", "flask"], ["vault", "vault"], ["forge", "forge"], ["guru", "guru"]
        ].map(function (m) {
          return d.h("li", null, d.h("a.mode-tile", { href: "#/" + m[0] },
            d.h("span.mode-icon", null, icons.icon(m[1], { size: 26 })),
            d.h("strong", null, t("nav." + m[0])),
            d.h("span.small.muted", null, t("home.mode." + m[0])),
            icons.icon("chevronRight", { size: 18, class: "mode-go" })));
        })));
      modes.querySelector("h2").id = "modes-title";

      var X = game.XP;
      var rules = [
        ["swords", t("home.xp.arena", { base: X.arenaBase, medium: X.arenaMedium, hard: X.arenaHard })],
        ["bolt", t("home.xp.upset", { n: X.arenaUpset })],
        ["flame", t("home.xp.combo", { step: X.comboStep, max: X.comboMax })],
        ["target", t("home.xp.confidence", { n: X.confidenceBonus, c: X.confidenceThreshold })],
        ["heart", t("home.xp.wrong", { n: X.arenaWrong })],
        ["skull", t("home.xp.boss", { share: Math.round(X.bossRepeatShare * 100) })],
        ["flask", t("home.xp.lab", { right: X.labRight, wrong: X.labWrong })],
        ["bulb", t("home.xp.myth", { right: X.mythRight, wrong: X.mythWrong })],
        ["check", t("home.xp.quest", { n: X.quest })],
        ["gem", t("home.xp.dust", { n: X.dust })],
        ["star", t("home.xp.levels")],
        ["snowflake", t("home.xp.streak")]
      ];
      var xpPanel = d.h("details.card.xp-panel", { open: firstPaint ? p.xp < 400 : (page.querySelector(".xp-panel") ? page.querySelector(".xp-panel").open : false) },
        d.h("summary", null, icons.icon("info", { size: 20 }), d.h("span", null, t("home.xp.title")), icons.icon("chevronDown", { size: 18, class: "chev" })),
        d.h("ul.rule-list", null, rules.map(function (r) { return d.h("li", null, icons.icon(r[0], { size: 18 }), d.h("span", null, r[1])); })),
        d.h("p.ethics-note", null, icons.icon("shieldCheck", { size: 18 }), d.h("span", null, t("home.xp.ethics"))));

      d.fill(page, [
        hero,
        d.h("div.home-grid", null, questsCard, chestCard),
        d.h("div.stat-grid-4", null, oracleCard, timeCard, streakCard, accCard),
        modes,
        xpPanel
      ]);
      firstPaint = false;
    }

    render();
    var off = ctx.store.subscribe(function () { render(); });
    return { destroy: function () { off(); } };
  }

  return { mount: mount, routeHref: routeHref };
});
