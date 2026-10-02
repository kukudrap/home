/* Bootstrap: loads the data bundle (embedded in the built file, fetched in development), restores the
 * profile, wires language, theme, sound and motion settings, routes between views and keeps an honest
 * track of play time for the break reminder. Nothing here talks to a server except, in live mode, the
 * local kingctl serve API.
 */
(function (root) {
  "use strict";

  var DK = root.DK;
  var dom = DK.ui.dom, icons = DK.ui.icons, i18n = DK.i18n, game = DK.game, scoring = DK.scoring;
  var VIEWS = ["home", "arena", "boss", "lab", "vault", "forge", "guru", "about"];

  var app = {
    bundle: null, store: null, shell: null, route: null, view: null,
    live: { enabled: false, version: null, writer: null, formats: null, checked: false }
  };
  DK.app = app;

  // -- data --------------------------------------------------------------------------------------------
  function fetchJson(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status + " for " + url);
      return r.json();
    });
  }

  /** Built file: the bundle is embedded. Development page: fetch ./bundle.json and the mock samples. */
  function loadBundle() {
    var el = document.getElementById("dk-bundle");
    if (el && el.textContent.trim()) {
      try { return Promise.resolve(JSON.parse(el.textContent)); } catch (e) { return Promise.reject(e); }
    }
    return fetchJson("./bundle.json").then(function (b) {
      var jobs = [];
      if (!(b.forge_samples && b.forge_samples.length)) {
        jobs.push(fetchJson("./mock-forge.json").then(function (j) { b.forge_samples = Array.isArray(j) ? j : [j]; }, function () {}));
      }
      if (!b.guru_sample && !(b.guru_samples && b.guru_samples.length)) {
        jobs.push(fetchJson("./mock-guru.json").then(function (j) { b.guru_sample = j; }, function () {}));
      }
      return Promise.all(jobs).then(function () { return b; });
    });
  }

  // -- live mode ---------------------------------------------------------------------------------------
  function apiCall(method, path, body) {
    var opts = { method: method, headers: { Accept: "application/json" } };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    return fetch(path, opts).then(function (r) {
      return r.text().then(function (txt) {
        var json = null;
        try { json = txt ? JSON.parse(txt) : null; } catch (e) { json = null; }
        if (!r.ok) {
          var err = new Error(json && (json.error || json.message) ? String(json.error || json.message) : "HTTP " + r.status);
          err.status = r.status;
          throw err;
        }
        if (json === null) throw new Error("empty response");
        return json;
      });
    });
  }

  var api = {
    health: function () { return apiCall("GET", "/api/health"); },
    formats: function () { return apiCall("GET", "/api/formats"); },
    forge: function (body) { return apiCall("POST", "/api/forge", body); },
    guru: function (body) { return apiCall("POST", "/api/guru", body); },
    score: function (body) { return apiCall("POST", "/api/score", body); }
  };

  /** On http or https ask the server whether it is kingctl serve; any failure simply means offline mode. */
  function detectLive() {
    if (!/^https?:$/.test(root.location.protocol)) return Promise.resolve(null);
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = setTimeout(function () { if (ctl) ctl.abort(); }, 2500);
    return fetch("/api/health", { headers: { Accept: "application/json" }, signal: ctl ? ctl.signal : undefined })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { return j && j.ok === true ? j : null; })
      .catch(function () { return null; })
      .then(function (j) { clearTimeout(timer); return j; });
  }

  // -- settings ----------------------------------------------------------------------------------------
  var mqLight = root.matchMedia ? root.matchMedia("(prefers-color-scheme: light)") : null;

  function effectiveTheme() {
    var th = app.store.get().settings.theme;
    if (th === "dark" || th === "light") return th;
    return mqLight && mqLight.matches ? "light" : "dark";
  }

  /** Keep the browser UI colour (address bar on phones) in step with the theme that is really shown. */
  function updateThemeColor(theme) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) return;
    var light = theme === "light" || (theme !== "dark" && mqLight && mqLight.matches);
    meta.setAttribute("content", light ? "#f1f3fb" : "#070b16");
  }

  function applySettings(s, prev) {
    var langChanged = !prev || s.lang !== prev.lang;
    if (langChanged) {
      i18n.setLang(s.lang);
      document.documentElement.lang = s.lang;
    }
    var html = document.documentElement;
    if (s.theme === "dark" || s.theme === "light") html.setAttribute("data-theme", s.theme); else html.removeAttribute("data-theme");
    updateThemeColor(s.theme);
    DK.ui.fx.setSound(s.sound);
    dom.setReducedMotion(s.reducedMotion);
    return langChanged;
  }

  // -- context for views ------------------------------------------------------------------------------
  var ctx = {
    lang: function () { return i18n.getLang(); },
    t: i18n.t, tp: i18n.tp, pick: i18n.pick, fmt: i18n.fmt,
    now: function () { return new Date(); },
    today: function () { return game.localDate(new Date()); },
    rng: null,
    api: api,
    live: function () { return app.live; },
    profile: function () { return app.store.get(); },
    effectiveTheme: effectiveTheme,
    navigate: function (path) {
      var target = "#/" + path;
      if (root.location.hash === target) renderRoute(); else root.location.hash = target;
    },
    toast: function (o) { return DK.ui.widgets.toast(o); },
    announce: function (m) { dom.announce(m); },
    confetti: function (o) { return DK.ui.fx.confetti(o); },
    sound: function (n) { DK.ui.fx.play(n); },
    reducedMotion: function () { return dom.reducedMotion(); },
    /** Run a game action (profile, args, {now, rng}) and handle what it reports. */
    apply: function (fn, args) {
      var res = fn(app.store.get(), args, { now: ctx.now, rng: ctx.rng });
      app.store.set(res.profile);
      if (app.shell) app.shell.handleEvents(res.events);
      return res;
    },
    updateProfile: function (patch) { app.store.update(function (p) { return Object.assign({}, p, patch); }); },
    updateSettings: function (patch) {
      var prev = app.store.get().settings;
      var next = Object.assign({}, prev, patch);
      app.store.update(function (p) { return Object.assign({}, p, { settings: next }); });
      var langChanged = applySettings(app.store.get().settings, prev);
      if (app.shell) app.shell.updateAll();
      if (langChanged) renderRoute();
    },
    exportProfile: function () {
      dom.download("dopamine-king-progress-" + ctx.today() + ".json", app.store.exportJSON(), "application/json");
    },
    importProfile: function (text) {
      try {
        app.store.importJSON(text);
        applySettings(app.store.get().settings, null);
        if (app.shell) app.shell.updateAll();
        renderRoute();
        return { ok: true };
      } catch (e) { return { ok: false, code: e && e.code ? e.code : "invalid_json" }; }
    },
    resetProfile: function () {
      app.store.reset();
      applySettings(app.store.get().settings, null);
      if (app.shell) app.shell.updateAll();
      renderRoute();
    },
    openProfile: function () { if (app.shell) app.shell.openProfile(); }
  };
  app.ctx = ctx;

  // -- routing -----------------------------------------------------------------------------------------
  function parseHash() {
    var h = root.location.hash || "";
    if (h.indexOf("#/") !== 0) return { name: "home", sub: null, params: {} };
    var raw = h.slice(2), qi = raw.indexOf("?");
    var path = qi >= 0 ? raw.slice(0, qi) : raw, query = qi >= 0 ? raw.slice(qi + 1) : "";
    var parts = path.split("/").filter(Boolean);
    var name = VIEWS.indexOf(parts[0]) >= 0 ? parts[0] : "home";
    var params = {};
    query.split("&").forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf("=");
      try { params[decodeURIComponent(i < 0 ? kv : kv.slice(0, i))] = i < 0 ? "" : decodeURIComponent(kv.slice(i + 1)); } catch (e) { /* ignore malformed pair */ }
    });
    var sub = null;
    try { sub = parts[1] ? decodeURIComponent(parts[1]) : null; } catch (e) { sub = null; }
    return { name: name, sub: sub, params: params };
  }

  function renderRoute() {
    if (!app.bundle) return;
    var route = parseHash();
    var main = document.getElementById("main");
    if (app.view && app.view.destroy) { try { app.view.destroy(); } catch (e) { /* a view must not block navigation */ } }
    app.view = null;
    dom.clear(main);
    main.removeAttribute("aria-busy");
    app.route = route;
    var mod = DK.ui[route.name];
    try {
      app.view = mod.mount(main, ctx, route) || null;
    } catch (err) {
      showError(main, err);
    }
    if (app.shell) app.shell.setRoute(route.name);
    document.title = i18n.t("nav." + route.name) + " | " + i18n.t("app.name");
    var h1 = main.querySelector("h1");
    var target = h1 || main;
    if (!h1) target.setAttribute("tabindex", "-1");
    try { target.focus({ preventScroll: true }); } catch (e) { /* ignore */ }
    root.scrollTo(0, 0);
  }

  function showError(main, err) {
    dom.clear(main);
    main.appendChild(dom.h("div.page", null, dom.h("section.card.error-card", { role: "alert" },
      dom.h("h1.page-title", { id: "view-title", tabindex: "-1" }, i18n.t("common.error")),
      dom.h("p", null, String(err && err.message ? err.message : err)))));
    if (root.console) root.console.error(err);
  }

  // -- play time and the break reminder ----------------------------------------------------------------------
  var session = { seconds: 0, pending: 0, last: Date.now(), breakShown: false };

  function flushPlayTime() {
    if (session.pending <= 0 || !app.store) return;
    var secs = session.pending;
    session.pending = 0;
    app.store.update(function (p) { return game.addPlayTime(p, secs, ctx.today()); }, { silent: true });
  }

  function tick() {
    var now = Date.now();
    var dt = Math.min(5, Math.max(0, (now - session.last) / 1000));
    session.last = now;
    if (document.visibilityState !== "visible") return;
    session.seconds += dt;
    session.pending += dt;
    if (session.pending >= 10) flushPlayTime();
    var limit = app.store.get().settings.sessionMinutes;
    if (game.shouldShowBreak({ activeSeconds: session.seconds, limitMinutes: limit, alreadyShown: session.breakShown })) {
      session.breakShown = true;
      if (app.shell) app.shell.showBreak(limit);
    }
  }

  // -- boot --------------------------------------------------------------------------------------------------
  function boot() {
    ctx.rng = game.systemRng();
    app.store = DK.store.createStore({ lang: i18n.detectLang(root.navigator && root.navigator.language) });
    var settings = app.store.get().settings;
    applySettings(settings, null);
    icons.mountDefs();

    document.getElementById("dk-skip").addEventListener("click", function (e) {
      e.preventDefault();
      var main = document.getElementById("main");
      main.setAttribute("tabindex", "-1");
      main.focus();
    });
    if (mqLight && mqLight.addEventListener) mqLight.addEventListener("change", function () { updateThemeColor(app.store.get().settings.theme); if (app.shell) app.shell.update(); });
    root.addEventListener("hashchange", renderRoute);
    root.addEventListener("pagehide", flushPlayTime);
    document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") flushPlayTime(); else session.last = Date.now(); });

    loadBundle().then(function (bundle) {
      app.bundle = bundle;
      ctx.bundle = bundle;
      ctx.store = app.store;
      scoring.setDefaultSpec(bundle.spec);
      app.store.update(function (p) { return game.rollover(p, ctx).profile; }, { silent: true });
      app.shell = DK.ui.shell.mount(ctx);
      document.getElementById("dk-boot").remove();
      renderRoute();
      setInterval(tick, 1000);
      return detectLive();
    }).then(function (health) {
      if (health) {
        app.live.enabled = true;
        app.live.version = health.version || null;
        app.live.writer = health.writer || null;
        app.live.checked = true;
        if (app.shell) app.shell.update();
        if (app.route && (app.route.name === "forge" || app.route.name === "guru")) renderRoute();
      } else app.live.checked = true;
    }).catch(function (err) {
      var main = document.getElementById("main");
      var file = root.location.protocol === "file:";
      dom.clear(main);
      main.appendChild(dom.h("div.page", null, dom.h("section.card.error-card", { role: "alert" },
        dom.h("h1.page-title", { id: "view-title", tabindex: "-1" }, i18n.t("app.loadFailed")),
        dom.h("p", null, String(err && err.message ? err.message : err)),
        file ? null : dom.h("p.small", null, i18n.t("app.devHint") + " "), file ? null : dom.h("pre.code", null, "python3 -m http.server -d web 8000"),
        dom.h("button.btn.btn-primary", { type: "button", onclick: function () { root.location.reload(); } }, i18n.t("app.retry")))));
      if (root.console) root.console.error(err);
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})(typeof self !== "undefined" ? self : this);
