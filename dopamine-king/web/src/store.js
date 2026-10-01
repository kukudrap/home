/* Profile persistence: localStorage under "dk.profile.v1" inside try/catch with an in-memory fallback
 * (private windows, blocked storage, quota errors), plus export and import as JSON.
 * Nothing here ever touches the network: the profile stays in this browser.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(function (n) { return require("./" + n + ".js"); });
  else { root.DK = root.DK || {}; root.DK.store = factory(function (n) { return root.DK[n]; }); }
})(typeof self !== "undefined" ? self : this, function (dep) {
  "use strict";

  var game = dep("game");
  var EXPORT_APP = "dopamine-king";
  var EXPORT_FORMAT = 1;
  var MAX_IMPORT_CHARS = 1000000;

  function memoryStorage() {
    var m = {};
    return {
      getItem: function (k) { return Object.prototype.hasOwnProperty.call(m, k) ? m[k] : null; },
      setItem: function (k, v) { m[k] = String(v); },
      removeItem: function (k) { delete m[k]; }
    };
  }

  /** The browser's localStorage when it really works (it can throw or be missing), else null. */
  function detectStorage() {
    try {
      var g = typeof globalThis !== "undefined" ? globalThis : {};
      var s = g.localStorage;
      if (!s) return null;
      var probe = "__dk_probe__";
      s.setItem(probe, "1");
      s.removeItem(probe);
      return s;
    } catch (e) { return null; }
  }

  function ImportError(code, message) {
    var e = new Error(message || code);
    e.name = "ImportError";
    e.code = code;
    return e;
  }

  /**
   * opts: {storage, key, lang, now}. storage defaults to localStorage; pass null to force memory only.
   */
  function createStore(opts) {
    opts = opts || {};
    var key = opts.key || game.PROFILE_KEY;
    var storage = opts.storage !== undefined ? opts.storage : detectStorage();
    var fallback = !storage;
    var memory = memoryStorage();
    var listeners = [];

    function today() {
      var v = typeof opts.now === "function" ? opts.now() : Date.now();
      return game.localDate(v instanceof Date ? v : new Date(v));
    }
    function fresh() { return game.defaultProfile({ lang: opts.lang, today: today() }); }

    function readRaw() {
      if (storage && !fallback) {
        try { return storage.getItem(key); } catch (e) { fallback = true; }
      }
      return memory.getItem(key);
    }
    function writeRaw(text) {
      if (storage && !fallback) {
        try { storage.setItem(key, text); return; } catch (e) { fallback = true; }
      }
      memory.setItem(key, text);
    }

    function load() {
      var raw = readRaw();
      if (!raw) return fresh();
      try {
        return game.normalizeProfile(JSON.parse(raw), { lang: opts.lang, today: today() });
      } catch (e) { return fresh(); }
    }

    var profile = load();

    function notify() { listeners.slice().forEach(function (fn) { try { fn(profile); } catch (e) { /* a listener must not break the store */ } }); }
    function persist() { writeRaw(JSON.stringify(profile)); }

    return {
      get: function () { return profile; },
      /** Replace the profile (validated), persist and notify (unless o.silent). */
      set: function (next, o) {
        profile = game.normalizeProfile(next, { lang: opts.lang, today: today() });
        persist();
        if (!o || !o.silent) notify();
        return profile;
      },
      /** Apply fn(profile) -> new profile (or {profile}); persists and notifies (unless o.silent). */
      update: function (fn, o) {
        var out = fn(profile);
        var next = out && out.profile ? out.profile : out;
        profile = game.normalizeProfile(next, { lang: opts.lang, today: today() });
        persist();
        if (!o || !o.silent) notify();
        return profile;
      },
      subscribe: function (fn) {
        listeners.push(fn);
        return function () { var i = listeners.indexOf(fn); if (i >= 0) listeners.splice(i, 1); };
      },
      reset: function () {
        var keepSettings = profile.settings;
        profile = fresh();
        profile.settings = keepSettings;
        persist(); notify();
        return profile;
      },
      /** True when progress is only kept in memory (storage blocked or failing). */
      usingFallback: function () { return fallback; },
      exportJSON: function () {
        return JSON.stringify({ app: EXPORT_APP, format: EXPORT_FORMAT, exported: new Date().toISOString(), profile: profile }, null, 2);
      },
      /** Replace the profile with an exported one. Throws ImportError (code: empty, too_large, invalid_json, wrong_app, invalid_profile). */
      importJSON: function (text) {
        var next = parseExport(text);
        profile = game.normalizeProfile(next, { lang: opts.lang, today: today() });
        persist(); notify();
        return profile;
      }
    };
  }

  /** Validate an exported file and return the raw profile object inside (not yet normalised). */
  function parseExport(text) {
    if (typeof text !== "string" || !text.trim()) throw ImportError("empty", "The file is empty.");
    if (text.length > MAX_IMPORT_CHARS) throw ImportError("too_large", "The file is too large.");
    var data;
    try { data = JSON.parse(text); } catch (e) { throw ImportError("invalid_json", "The file is not valid JSON."); }
    if (!data || typeof data !== "object" || Array.isArray(data)) throw ImportError("invalid_profile", "Unexpected file content.");
    if (data.app !== undefined && data.app !== EXPORT_APP) throw ImportError("wrong_app", "This file was not exported by Dopamine King.");
    var prof = data.profile !== undefined ? data.profile : data;
    if (!prof || typeof prof !== "object" || Array.isArray(prof) || typeof prof.xp !== "number") throw ImportError("invalid_profile", "No profile found in the file.");
    return prof;
  }

  return {
    createStore: createStore, memoryStorage: memoryStorage, detectStorage: detectStorage,
    parseExport: parseExport, EXPORT_APP: EXPORT_APP, EXPORT_FORMAT: EXPORT_FORMAT
  };
});
