/* The frame around every view: top bar (logo, level and XP, streak, language, theme, demo chip),
 * navigation (tabs on desktop, bottom bar on phones), the profile dialog, game event toasts and the
 * gentle digital wellbeing break card.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.shell = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  function D() { return root.DK.ui.dom; }
  function I() { return root.DK.ui.icons; }
  function W() { return root.DK.ui.widgets; }
  function G() { return root.DK.game; }

  var NAV = [
    { id: "home", icon: "home" }, { id: "arena", icon: "swords" }, { id: "boss", icon: "skull" },
    { id: "lab", icon: "flask" }, { id: "vault", icon: "vault" },
    { id: "forge", icon: "forge", secondary: true }, { id: "guru", icon: "guru", secondary: true }, { id: "about", icon: "info", secondary: true }
  ];
  var SESSION_CHOICES = [0, 10, 15, 20, 30, 45, 60];

  function mount(ctx) {
    var d = D(), icons = I(), widgets = W(), game = G(), t = d.t;
    var topbar = document.getElementById("topbar");
    var nav = document.getElementById("nav");
    var state = { shownPct: null, shownLevel: null, route: "home", moreOpen: false };
    var xpFill = null;

    // -- top bar ---------------------------------------------------------------------------------
    function langSwitch() {
      var cur = ctx.lang();
      var seg = widgets.segmented({
        label: t("top.lang"), active: cur,
        items: [{ id: "cs", label: "CS" }, { id: "en", label: "EN" }],
        onChange: function (id) { ctx.updateSettings({ lang: id }); }
      });
      seg.el.classList.add("lang-seg");
      Array.prototype.forEach.call(seg.el.querySelectorAll("button"), function (b, i) {
        b.setAttribute("lang", i === 0 ? "cs" : "en");
        b.setAttribute("aria-label", i === 0 ? t("top.langCs") : t("top.langEn"));
      });
      return seg.el;
    }

    function themeButton() {
      var dark = ctx.effectiveTheme() === "dark";
      return d.h("button.btn.btn-ghost.btn-icon.theme-btn", {
        type: "button", "aria-label": dark ? t("top.toLight") : t("top.toDark"), title: dark ? t("top.toLight") : t("top.toDark"),
        onclick: function () { ctx.updateSettings({ theme: dark ? "light" : "dark" }); }
      }, icons.icon(dark ? "sun" : "moon", { size: 20 }));
    }

    function soundButton() {
      var on = ctx.profile().settings.sound;
      return d.h("button.btn.btn-ghost.btn-icon.sound-btn", {
        type: "button", "aria-pressed": on ? "true" : "false", "aria-label": t("top.sound"), title: on ? t("top.soundOn") : t("top.soundOff"),
        onclick: function () { ctx.updateSettings({ sound: !on }); }
      }, icons.icon(on ? "speaker" : "speakerOff", { size: 20 }));
    }

    function levelChip(p) {
      var lp = game.levelProgress(p.xp);
      var title = game.levelTitle(lp.level, ctx.lang());
      var fill = d.h("i.xpbar-fill");
      var from = state.shownPct === null ? lp.pct : (state.shownLevel !== null && lp.level > state.shownLevel ? state.shownPct : state.shownPct);
      fill.style.setProperty("--v", String(from));
      var levelUp = state.shownLevel !== null && lp.level > state.shownLevel;
      d.raf(function () {
        fill.style.setProperty("--v", String(levelUp ? 1 : lp.pct));
        if (levelUp) setTimeout(function () { fill.style.setProperty("--v", String(lp.pct)); }, d.reducedMotion() ? 0 : 650);
      });
      state.shownPct = lp.pct;
      state.shownLevel = lp.level;
      xpFill = fill;
      return d.h("button.level-chip", {
        type: "button", onclick: function () { openProfile(); },
        "aria-label": t("top.levelAria", { n: lp.level, title: title, into: d.fmt(lp.into), span: d.fmt(lp.span) }),
        title: t("top.profile")
      },
        d.h("span.lvl-badge", { "aria-hidden": "true" }, String(lp.level)),
        d.h("span.lvl-body", { "aria-hidden": "true" },
          d.h("span.lvl-title", null, title),
          d.h("span.xpbar", null, fill)),
        d.h("span.lvl-xp", { "aria-hidden": "true" }, d.fmt(lp.into) + "/" + d.fmt(lp.span)));
    }

    function streakChip(p) {
      var st = game.streakStatus(p, ctx.today());
      var f = p.freezeTokens;
      var chip = d.h("div.streak-chip" + (st.alive ? "" : ".is-out"), {
        role: "group", "aria-label": t("top.streakAria", { n: st.streak, f: f }), title: t("top.streakTitle")
      },
        icons.flame(22, st.alive),
        d.h("b.streak-n", { "aria-hidden": "true" }, String(st.streak)),
        f > 0 ? d.h("span.freeze", { "aria-hidden": "true", title: t("top.freezes", { n: f }) }, icons.icon("snowflake", { size: 15 }), d.h("span", null, "×" + f)) : null);
      return chip;
    }

    function demoChip() {
      var synthetic = !ctx.bundle.meta || ctx.bundle.meta.synthetic !== false;
      var children = [icons.icon("flask", { size: 14 }), d.h("span", null, synthetic ? t("top.demo") : t("top.demoReal"))];
      return d.h("button.chip.demo-chip" + (synthetic ? ".tone-warn" : ".tone-ok"), { type: "button", title: t("top.demoTitle"), onclick: function () { openDemo(); } }, children);
    }

    function renderTop() {
      var p = ctx.profile();
      var live = ctx.live();
      d.fill(topbar, [
        d.h("a.brand", { href: "#/home", "aria-label": t("app.name") + ": " + t("nav.home") }, icons.logo(30), d.h("span.brand-text", null, t("app.name"))),
        d.h("div.status", null, levelChip(p), streakChip(p), demoChip(),
          live.enabled ? d.h("span.chip.tone-ok.live-chip", { title: t("top.liveTitle") }, icons.icon("spark", { size: 13 }), d.h("span", null, t("top.live"))) : null),
        d.h("div.tools", null, langSwitch(), themeButton(), soundButton(),
          d.h("button.btn.btn-ghost.btn-icon.profile-btn", { type: "button", "aria-label": t("top.profile"), title: t("top.profile"), onclick: function () { openProfile(); } }, icons.icon("user", { size: 20 })))
      ]);
    }

    // -- navigation --------------------------------------------------------------------------------
    function navLink(item) {
      var cur = state.route === item.id;
      return d.h("li", null, d.h("a.nav-link", { href: "#/" + item.id, "aria-current": cur ? "page" : null, onclick: function () { closeMore(); } },
        icons.icon(item.icon, { size: 22 }), d.h("span.nav-label", null, t("nav." + item.id))));
    }

    function closeMore() {
      state.moreOpen = false;
      var item = nav.querySelector(".nav-more-item");
      if (item) item.classList.remove("is-open");
      var btn = nav.querySelector(".nav-more");
      if (btn) btn.setAttribute("aria-expanded", "false");
    }

    function renderNav() {
      var secondaryActive = NAV.some(function (n) { return n.secondary && n.id === state.route; });
      var more = d.h("li.nav-more-item" + (state.moreOpen ? ".is-open" : ""), null,
        d.h("button.nav-link.nav-more", {
          type: "button", "aria-expanded": state.moreOpen ? "true" : "false", "aria-controls": "nav-sub", "aria-label": t("nav.moreLabel"),
          "aria-current": secondaryActive ? "true" : null,
          onclick: function (e) {
            e.stopPropagation();
            state.moreOpen = !state.moreOpen;
            nav.querySelector(".nav-more-item").classList.toggle("is-open", state.moreOpen);
            e.currentTarget.setAttribute("aria-expanded", state.moreOpen ? "true" : "false");
          }
        }, icons.icon("dots", { size: 22 }), d.h("span.nav-label", null, t("nav.more"))),
        d.h("ul.nav-sub", { id: "nav-sub" }, NAV.filter(function (n) { return n.secondary; }).map(navLink)));
      var list = d.h("ul.nav-list", null, NAV.filter(function (n) { return !n.secondary; }).map(navLink), more);
      nav.setAttribute("aria-label", t("nav.label"));
      d.fill(nav, list);
    }

    root.document.addEventListener("click", function (e) {
      if (state.moreOpen && !e.target.closest(".nav-more-item")) closeMore();
    });
    root.document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && state.moreOpen) { closeMore(); var b = nav.querySelector(".nav-more"); if (b) b.focus(); }
    });

    // -- dialogs -----------------------------------------------------------------------------------
    function openDemo() {
      var dlg = widgets.dialog({
        title: t("demo.title"),
        body: d.h("div.stack.tight", null,
          d.h("p", null, t("demo.p1")), d.h("p", null, t("demo.p2")), d.h("p", null, t("demo.p3")),
          d.h("p", null, d.h("a.link", { href: "#/about", onclick: function () { dlg.close(); } }, t("demo.more")))),
        actions: [d.h("button.btn.btn-primary", { type: "button", onclick: function () { dlg.close(); } }, t("common.ok"))]
      });
    }

    function statTile(label, value) {
      return d.h("div.stat-tile", null, d.h("span.stat-val", null, value), d.h("span.stat-label", null, label));
    }

    function openProfile() {
      var p = ctx.profile();
      var lang = ctx.lang();
      var lp = game.levelProgress(p.xp);
      var oracle = game.oracleRating(p.brier);
      var nameInput = d.h("input.input", { type: "text", maxlength: "40", value: p.name, autocomplete: "nickname", placeholder: t("profile.namePlaceholder") });
      nameInput.addEventListener("change", function () { ctx.updateProfile({ name: nameInput.value.trim() }); });

      var ach = d.h("ul.ach-grid", null, game.ACHIEVEMENTS.map(function (a) {
        var on = p.achievements.indexOf(a.id) >= 0;
        return d.h("li.ach" + (on ? ".is-on" : ".is-off"), null,
          d.h("span.ach-icon", null, icons.icon(on ? a.icon : "lock", { size: 22 })),
          d.h("span.ach-text", null, d.h("strong", null, a.name[lang]), d.h("span", null, a.desc[lang]), d.h("em.ach-state", null, on ? t("profile.unlocked") : t("common.locked"))));
      }));

      var sessionSel = d.h("select.input", { "aria-label": t("profile.session"), onchange: function () { ctx.updateSettings({ sessionMinutes: Number(sessionSel.value) }); } },
        SESSION_CHOICES.map(function (m) { return d.h("option", { value: String(m), selected: p.settings.sessionMinutes === m }, m === 0 ? t("common.off") : t("common.min", { n: m })); }));
      var themeSeg = widgets.segmented({
        label: t("top.theme"), active: p.settings.theme,
        items: [{ id: "auto", label: t("profile.themeAuto") }, { id: "dark", label: t("profile.themeDark") }, { id: "light", label: t("profile.themeLight") }],
        onChange: function (id) { ctx.updateSettings({ theme: id }); }
      });
      var langSeg = widgets.segmented({
        label: t("top.lang"), active: p.settings.lang, items: [{ id: "cs", label: t("top.langCs") }, { id: "en", label: t("top.langEn") }],
        onChange: function (id) { dlg.close(); ctx.updateSettings({ lang: id }); setTimeout(openProfile, 30); }
      });
      var soundSw = widgets.switchControl({ label: t("profile.sound"), checked: p.settings.sound, onChange: function (on) { ctx.updateSettings({ sound: on }); } });
      var motionSw = widgets.switchControl({ label: t("profile.reduceMotion"), checked: p.settings.reducedMotion, onChange: function (on) { ctx.updateSettings({ reducedMotion: on }); } });

      var msg = d.h("p.form-msg", { role: "status" });
      var fileInput = d.h("input", { type: "file", accept: "application/json,.json", class: "sr-only", tabindex: "-1", "aria-hidden": "true" });
      fileInput.addEventListener("change", function () {
        var f = fileInput.files && fileInput.files[0];
        if (!f) return;
        var reader = new root.FileReader();
        reader.onload = function () {
          var res = ctx.importProfile(String(reader.result));
          msg.textContent = res.ok ? t("profile.imported") : t("profile.importErr." + res.code);
          msg.className = "form-msg " + (res.ok ? "is-ok" : "is-bad");
          if (res.ok) { setTimeout(function () { dlg.close(); }, 700); }
        };
        reader.onerror = function () { msg.textContent = t("profile.importErr.read"); msg.className = "form-msg is-bad"; };
        reader.readAsText(f);
        fileInput.value = "";
      });
      var resetHost = d.h("div.reset-host");
      function showResetAsk() {
        d.fill(resetHost, [
          d.h("p.small", null, t("profile.resetAsk")),
          d.h("div.row.wrap", null,
            d.h("button.btn.btn-danger.btn-sm", { type: "button", onclick: function () { ctx.resetProfile(); dlg.close(); } }, t("profile.resetYes")),
            d.h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: showResetBtn }, t("common.cancel")))
        ]);
      }
      function showResetBtn() {
        d.fill(resetHost, d.h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: showResetAsk }, icons.icon("trash", { size: 15 }), t("profile.reset")));
      }
      showResetBtn();

      var body = d.h("div.profile", null,
        d.h("section.stack.tight", null,
          d.h("div.profile-head", null,
            d.h("span.lvl-badge.big", { "aria-hidden": "true" }, String(lp.level)),
            d.h("div", null, d.h("strong.profile-level", null, t("top.level", { n: lp.level }) + ": " + game.levelTitle(lp.level, lang)),
              d.h("p.small.muted", null, t("profile.xpTo", { xp: d.fmt(p.xp), next: d.fmt(lp.next) })))),
          widgets.field(t("profile.name"), nameInput)),
        d.h("section", null, d.h("h3.sub", null, t("profile.stats")),
          d.h("div.stat-grid", null,
            statTile(t("profile.statArena"), d.fmt(p.stats.arenaCorrect) + "/" + d.fmt(p.stats.arenaPlayed)),
            statTile(t("profile.statUpsets"), d.fmt(p.stats.upsetsCaught)),
            statTile(t("profile.statBoss"), d.fmt(p.stats.bossWins)),
            statTile(t("profile.statLab"), d.fmt(p.stats.labRuns)),
            statTile(t("profile.statMyths"), d.fmt(p.stats.mythsCorrect) + "/" + d.fmt(p.stats.mythsPlayed)),
            statTile(t("profile.statChests"), d.fmt(p.stats.chests)),
            statTile(t("profile.statBestStreak"), d.fmt(p.bestStreak)),
            statTile(t("profile.statOracle"), oracle === null ? "-" : d.fmt(oracle, 0)))),
        d.h("section", null, d.h("h3.sub", null, t("profile.achievements") + " (" + p.achievements.length + "/" + game.ACHIEVEMENTS.length + ")"), ach),
        d.h("section.stack.tight", null, d.h("h3.sub", null, t("profile.settings")),
          d.h("div.setting", null, d.h("span.setting-label", null, t("top.lang")), langSeg.el),
          d.h("div.setting", null, d.h("span.setting-label", null, t("top.theme")), themeSeg.el),
          d.h("div.setting", null, soundSw.el, d.h("p.small.muted", null, t("profile.soundHint"))),
          d.h("div.setting", null, motionSw.el, d.h("p.small.muted", null, t("profile.reduceMotionHint"))),
          d.h("div.setting", null, widgets.field(t("profile.session"), sessionSel, t("profile.sessionHint")))),
        d.h("section.stack.tight", null, d.h("h3.sub", null, t("profile.data")),
          d.h("p.small.muted", null, ctx.store.usingFallback() ? t("app.memoryOnly") : t("app.stored")),
          d.h("div.row.wrap", null,
            d.h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: function () { ctx.exportProfile(); } }, icons.icon("download", { size: 15 }), t("profile.export")),
            d.h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: function () { fileInput.click(); } }, icons.icon("upload", { size: 15 }), t("profile.import")),
            fileInput),
          msg, resetHost));
      var dlg = widgets.dialog({ title: t("profile.title"), body: body, wide: true });
      return dlg;
    }

    // -- events and toasts --------------------------------------------------------------------------
    /** Turn engine events into friendly toasts, sounds and (for level ups) a small celebration. */
    function handleEvents(events) {
      if (!events || !events.length) return;
      var lang = ctx.lang();
      var level = null;
      events.forEach(function (e) {
        if (e.type === "levelUp") level = level ? { from: level.from, to: e.to } : e;
        else if (e.type === "achievement") {
          var a = game.achievementById(e.id);
          if (a) { widgets.toast({ title: t("toast.achievement"), text: a.name[lang] + ": " + a.desc[lang], icon: a.icon, tone: "xp", ms: 6500 }); ctx.sound("level"); }
        } else if (e.type === "quest") {
          widgets.toast({ title: t("toast.quest", { xp: e.xp }), text: t("quest." + e.id, { n: game.questDef(e.id).target }), icon: "check", tone: "ok" });
        } else if (e.type === "bonusChest") {
          widgets.toast({ title: t("toast.bonusChest"), text: t("toast.bonusChestText"), icon: "vault", tone: "xp", ms: 6500 });
          ctx.sound("chest");
        } else if (e.type === "freezeUsed") {
          widgets.toast({ title: t("toast.freezeUsed"), text: t("toast.freezeUsedText"), icon: "snowflake", tone: "info" });
        } else if (e.type === "freezeEarned") {
          widgets.toast({ title: t("toast.freezeEarned"), text: t("toast.freezeEarnedText"), icon: "snowflake", tone: "info" });
        }
      });
      if (level) {
        widgets.toast({ title: t("toast.levelUp", { n: level.to }), text: game.levelTitle(level.to, lang), icon: "star", tone: "xp", ms: 6000 });
        ctx.sound("level");
        ctx.confetti({ x: 0.5, y: 0.2, count: 90 });
        d.announce(t("toast.levelUp", { n: level.to }) + " " + game.levelTitle(level.to, lang));
      }
    }

    // -- wellbeing break card ---------------------------------------------------------------------------
    var breakEl = null;
    function showBreak(minutes) {
      if (breakEl) return;
      var titleId = d.uid("break-title");
      breakEl = d.h("section.break-card", { role: "dialog", "aria-modal": "false", "aria-labelledby": titleId },
        d.h("span.break-icon", { "aria-hidden": "true" }, icons.icon("coffee", { size: 30 })),
        d.h("div.break-body", null,
          d.h("h2.break-title", { id: titleId }, t("break.title")),
          d.h("p", null, t("break.text", { n: minutes })),
          d.h("p.small.muted", null, t("break.note")),
          d.h("div.row.wrap", null,
            d.h("button.btn.btn-primary.btn-sm", { type: "button", onclick: hideBreak }, t("break.keep")),
            d.h("button.btn.btn-ghost.btn-sm", { type: "button", onclick: function () { hideBreak(); openProfile(); } }, t("break.settings")))));
      document.getElementById("app").appendChild(breakEl);
      d.announce(t("break.title") + ". " + t("break.text", { n: minutes }));
    }
    function hideBreak() { if (breakEl && breakEl.parentNode) breakEl.parentNode.removeChild(breakEl); breakEl = null; }

    // -- public ------------------------------------------------------------------------------------
    renderTop();
    renderNav();
    return {
      update: function () { renderTop(); },
      updateAll: function () { renderTop(); renderNav(); },
      setRoute: function (name) { state.route = name; closeMore(); renderNav(); },
      openProfile: openProfile, openDemo: openDemo, handleEvents: handleEvents, showBreak: showBreak, hideBreak: hideBreak
    };
  }

  return { mount: mount, NAV: NAV, SESSION_CHOICES: SESSION_CHOICES };
});
