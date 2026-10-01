/* Tiny DOM toolkit shared by all views: element builder, SVG builder, animation helpers and a few
 * browser conveniences. No innerHTML anywhere: text always goes through text nodes, so data from the
 * bundle or from a server can never inject markup.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.dom = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var counter = 0;

  function i18n() { return root.DK && root.DK.i18n; }
  /** Translate through DK.i18n (falls back to the key when i18n is not loaded, e.g. in unit tests). */
  function t(key, params) { var i = i18n(); return i ? i.t(key, params) : key; }
  function lang() { var i = i18n(); return i ? i.getLang() : "en"; }
  function fmt(n, digits) { var i = i18n(); return i ? i.fmt(n, digits) : String(n); }

  function toNode(child) {
    if (child === null || child === undefined || child === false || child === true) return null;
    if (typeof child === "string" || typeof child === "number") return document.createTextNode(String(child));
    return child;
  }

  function append(el, children) {
    for (var i = 0; i < children.length; i++) {
      var c = children[i];
      if (Array.isArray(c)) { append(el, c); continue; }
      var n = toNode(c);
      if (n) el.appendChild(n);
    }
    return el;
  }

  var LATE = { value: 1, checked: 1, selected: 1, indeterminate: 1 };

  function applyProps(el, props, isSvg) {
    if (!props) return;
    var late = [];
    Object.keys(props).forEach(function (key) {
      var v = props[key];
      if (v === null || v === undefined || v === false) return;
      if (!isSvg && LATE[key]) { late.push(key); return; }
      if (key === "class" || key === "className") {
        el.setAttribute("class", el.getAttribute("class") ? el.getAttribute("class") + " " + v : v);
      } else if (key === "style") {
        if (typeof v === "string") el.style.cssText = v;
        else Object.keys(v).forEach(function (k) { if (k.indexOf("--") === 0) el.style.setProperty(k, v[k]); else el.style[k] = v[k]; });
      } else if (key === "dataset") {
        Object.keys(v).forEach(function (k) { el.dataset[k] = v[k]; });
      } else if (key === "text") {
        el.textContent = v;
      } else if (key.slice(0, 2) === "on" && typeof v === "function") {
        el.addEventListener(key.slice(2).toLowerCase(), v);
      } else if (v === true) {
        el.setAttribute(key, "");
      } else {
        el.setAttribute(key, String(v));
      }
    });
    late.forEach(function (key) {
      if (key === "value") el.value = props.value;
      else el[key] = !!props[key];
    });
  }

  // The second argument is the property bag when it is a plain object (or null); anything else is a child.
  function takeProps(args) {
    var first = args[0];
    if (first === null || first === undefined) { args.shift(); return null; }
    if (typeof first === "object" && !Array.isArray(first) && typeof first.nodeType !== "number") return args.shift();
    return null;
  }

  /** h("div.card.wide", {id: "x", onclick: fn}, child, [children], "text"); props may be left out. */
  function h(tag) {
    var args = Array.prototype.slice.call(arguments, 1);
    var props = takeProps(args);
    var parts = String(tag).split(".");
    var el = document.createElement(parts[0] || "div");
    if (parts.length > 1) el.setAttribute("class", parts.slice(1).join(" "));
    applyProps(el, props, false);
    return append(el, args);
  }

  /** SVG builder: svg("path", {d: "..."}) */
  function svg(tag) {
    var args = Array.prototype.slice.call(arguments, 1);
    var attrs = takeProps(args);
    var el = document.createElementNS(SVG_NS, tag);
    applyProps(el, attrs, true);
    return append(el, args);
  }

  function clear(el) { while (el.firstChild) el.removeChild(el.firstChild); return el; }

  /** Replace the content of el with children. */
  function fill(el, children) { clear(el); append(el, Array.isArray(children) ? children : [children]); return el; }

  function clamp(x, lo, hi) { return Math.min(hi, Math.max(lo, x)); }
  function lerp(a, b, k) { return a + (b - a) * k; }
  function uid(prefix) { counter += 1; return (prefix || "dk") + "-" + counter; }

  function debounce(fn, ms) {
    var timer = null;
    function d() {
      var args = arguments, self = this;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () { timer = null; fn.apply(self, args); }, ms);
    }
    d.cancel = function () { if (timer) clearTimeout(timer); timer = null; };
    d.flush = function () { if (timer) { clearTimeout(timer); timer = null; fn(); } };
    return d;
  }

  // -- motion -----------------------------------------------------------------------------------
  var motion = { forced: false };
  function setReducedMotion(on) {
    motion.forced = !!on;
    if (typeof document !== "undefined") document.documentElement.classList.toggle("reduce-motion", reducedMotion());
  }
  /** True when the user asked for less motion (OS setting or the in-game switch). */
  function reducedMotion() {
    if (motion.forced) return true;
    try { return !!(root.matchMedia && root.matchMedia("(prefers-reduced-motion: reduce)").matches); } catch (e) { return false; }
  }

  var ease = {
    linear: function (x) { return x; },
    outCubic: function (x) { return 1 - Math.pow(1 - x, 3); },
    outBack: function (x) { var c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2); },
    inOutCubic: function (x) { return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2; }
  };

  /**
   * Animate a number. opts: {from, to, ms, ease, onUpdate(v), onDone()}. With reduced motion (or ms <= 0)
   * it jumps straight to the end value. Returns {cancel()}.
   */
  function tween(opts) {
    var from = opts.from || 0, to = opts.to, ms = opts.ms === undefined ? 700 : opts.ms;
    var fn = opts.ease || ease.outCubic;
    if (reducedMotion() || ms <= 0 || typeof requestAnimationFrame !== "function") {
      if (opts.onUpdate) opts.onUpdate(to);
      if (opts.onDone) opts.onDone();
      return { cancel: function () {} };
    }
    var start = null, id = 0, dead = false;
    function frame(ts) {
      if (dead) return;
      if (start === null) start = ts;
      var k = clamp((ts - start) / ms, 0, 1);
      if (opts.onUpdate) opts.onUpdate(lerp(from, to, fn(k)));
      if (k < 1) id = requestAnimationFrame(frame);
      else if (opts.onDone) opts.onDone();
    }
    id = requestAnimationFrame(frame);
    return { cancel: function () { dead = true; if (id) cancelAnimationFrame(id); } };
  }

  /** Count a number up inside an element. opts: {from, ms, digits, prefix, suffix}. */
  function countUp(el, to, opts) {
    opts = opts || {};
    var digits = opts.digits || 0, prefix = opts.prefix || "", suffix = opts.suffix || "";
    return tween({
      from: opts.from === undefined ? 0 : opts.from, to: to, ms: opts.ms === undefined ? 800 : opts.ms,
      onUpdate: function (v) { el.textContent = prefix + fmt(Number(v.toFixed(digits)), digits) + suffix; }
    });
  }

  function raf(fn) { return typeof requestAnimationFrame === "function" ? requestAnimationFrame(fn) : setTimeout(fn, 16); }
  function wait(ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); }

  // -- accessibility and browser helpers ---------------------------------------------------------
  /** Announce a message to screen readers through the polite live region. */
  function announce(msg) {
    var region = document.getElementById("dk-live");
    if (!region) return;
    region.textContent = "";
    setTimeout(function () { region.textContent = msg; }, 30);
  }

  function copyText(text) {
    function fallback() {
      var ta = h("textarea", { "aria-hidden": "true", tabindex: "-1", style: { position: "fixed", left: "-9999px", top: "0" } });
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      return ok;
    }
    try {
      if (root.navigator && root.navigator.clipboard && root.navigator.clipboard.writeText) {
        return root.navigator.clipboard.writeText(text).then(function () { return true; }, function () { return fallback(); });
      }
    } catch (e) { /* fall through */ }
    return Promise.resolve(fallback());
  }

  /** Offer a text file for download (works from file:// too). */
  function download(filename, text, mime) {
    var blob = new Blob([text], { type: mime || "text/plain;charset=utf-8" });
    var url = URL.createObjectURL(blob);
    var a = h("a", { href: url, download: filename, style: { display: "none" } });
    document.body.appendChild(a);
    a.click();
    setTimeout(function () { document.body.removeChild(a); URL.revokeObjectURL(url); }, 500);
  }

  function isFormField(el) {
    if (!el || !el.tagName) return false;
    var tag = el.tagName.toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable === true;
  }

  /** A short "press this key" hint. */
  function kbd(text) { return h("kbd", { class: "kbd" }, text); }

  /** Format minutes of play for display, e.g. 75 -> "1 h 15 min". */
  function fmtMinutes(min) {
    if (min < 60) return t("common.min", { n: min });
    var hrs = Math.floor(min / 60), rest = min % 60;
    return hrs + " h" + (rest ? " " + t("common.min", { n: rest }) : "");
  }

  return {
    SVG_NS: SVG_NS, h: h, svg: svg, clear: clear, fill: fill, append: append, clamp: clamp, lerp: lerp, uid: uid,
    debounce: debounce, t: t, lang: lang, fmt: fmt, ease: ease, tween: tween, countUp: countUp, raf: raf, wait: wait,
    setReducedMotion: setReducedMotion, reducedMotion: reducedMotion, announce: announce, copyText: copyText,
    download: download, isFormField: isFormField, kbd: kbd, fmtMinutes: fmtMinutes
  };
});
