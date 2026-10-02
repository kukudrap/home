/* Inline SVG icons and small illustrations (crown logo, flame, trust shield, chest, boss avatars).
 * Everything is drawn here, nothing is fetched. Icons use currentColor so they follow the theme.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.icons = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  function dom() { return root.DK.ui.dom; }

  // Mini description language: "M.." path, ["c", cx, cy, r] circle, ["cf", ...] filled circle,
  // ["r", x, y, w, h, rx] rect, ["l", x1, y1, x2, y2] line, ["f", "M.."] filled path.
  var ICONS = {
    home: ["M3 11.5L12 4l9 7.5", "M5.5 10v9.5a1 1 0 0 0 1 1H10v-5.5h4v5.5h3.5a1 1 0 0 0 1-1V10"],
    swords: ["M14.5 17.5L3 6V3h3l11.5 11.5", "M13 19l6-6", "M16 16l4 4", "M19 21l2-2", "M14.5 6.5L18 3h3v3l-3.5 3.5", "M5 14l4 4", "M7 17l-3 3", "M3 19l2 2"],
    skull: ["M12 3a8 8 0 0 0-8 8c0 2.7 1.3 4.4 3 5.5V20h10v-3.5c1.7-1.1 3-2.8 3-5.5a8 8 0 0 0-8-8z", ["cf", 9, 11.2, 1.5], ["cf", 15, 11.2, 1.5], "M10.3 20v-2.6", "M13.7 20v-2.6", "M12 13.6l-.9 1.9h1.8z"],
    flask: ["M9.5 3h5", "M10 3v6.3L4.7 19.2A1.6 1.6 0 0 0 6.1 21.5h11.8a1.6 1.6 0 0 0 1.4-2.3L14 9.3V3", "M7.6 15.5h8.8"],
    vault: ["M4 10V8a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v2", "M3 10h18v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z", ["r", 10.2, 12.2, 3.6, 3.6, 0.9], "M12 14.4v.1"],
    forge: ["M10.5 3l1.8 4.9 4.9 1.8-4.9 1.8-1.8 4.9-1.8-4.9L3.8 9.7l4.9-1.8z", "M18.5 14l.9 2.3 2.3.9-2.3.9-.9 2.3-.9-2.3-2.3-.9 2.3-.9z"],
    guru: [["c", 12, 12, 9], "M15.9 8.1l-2.2 5.6-5.6 2.2 2.2-5.6z", ["cf", 12, 12, 1]],
    info: [["c", 12, 12, 9], "M12 11v5.2", ["cf", 12, 7.9, 0.5]],
    crown: ["M4 19.5h16", "M4.5 19.5L3 8l5.3 4.2L12 5l3.7 7.2L21 8l-1.5 11.5", ["cf", 3, 7.6, 1.1], ["cf", 12, 4.6, 1.1], ["cf", 21, 7.6, 1.1]],
    flame: ["M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.4-.5-2-1-3-1.1-2.1-.2-4.1 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.2.4-2.3 1-3a2.5 2.5 0 0 0 2.5 2.5z"],
    snowflake: ["M12 3v18", "M4.2 7.5l15.6 9", "M19.8 7.5l-15.6 9", "M9.5 4.6L12 6.6l2.5-2", "M9.5 19.4L12 17.4l2.5 2"],
    shield: ["M12 3l7.5 2.8v5.6c0 4.8-3.2 8.6-7.5 10.1-4.3-1.5-7.5-5.3-7.5-10.1V5.8z"],
    shieldCheck: ["M12 3l7.5 2.8v5.6c0 4.8-3.2 8.6-7.5 10.1-4.3-1.5-7.5-5.3-7.5-10.1V5.8z", "M8.6 12.1l2.4 2.4 4.4-4.7"],
    star: ["M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"],
    bolt: ["M13 2.5L4.5 14H11l-1 7.5L19.5 10H13z"],
    target: [["c", 12, 12, 9], ["c", 12, 12, 5], ["cf", 12, 12, 1.2]],
    eye: ["M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z", ["c", 12, 12, 3]],
    bulb: ["M9 18h6", "M10 21h4", "M12 3a6 6 0 0 0-3.5 10.9c.7.6 1 1.3 1 2.1h5c0-.8.3-1.5 1-2.1A6 6 0 0 0 12 3z"],
    globe: [["c", 12, 12, 9], "M3 12h18", "M12 3c3 3 3 15 0 18", "M12 3c-3 3-3 15 0 18"],
    check: ["M5 12.5l4.5 4.5L19 7.5"],
    x: ["M6 6l12 12", "M18 6L6 18"],
    lock: [["r", 5, 11, 14, 9, 2], "M8 11V8a4 4 0 0 1 8 0v3", "M12 15v2"],
    clock: [["c", 12, 12, 9], "M12 7v5l3.2 2"],
    sun: [["c", 12, 12, 4], "M12 2.5v2.2", "M12 19.3v2.2", "M2.5 12h2.2", "M19.3 12h2.2", "M5.3 5.3l1.6 1.6", "M17.1 17.1l1.6 1.6", "M5.3 18.7l1.6-1.6", "M17.1 6.9l1.6-1.6"],
    moon: ["M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"],
    speaker: ["M4 9.5v5h3.8l5.2 4V5.5l-5.2 4z", "M16.5 9a4.2 4.2 0 0 1 0 6", "M19 6.5a8 8 0 0 1 0 11"],
    speakerOff: ["M4 9.5v5h3.8l5.2 4V5.5l-5.2 4z", "M17 9.5l4 5", "M21 9.5l-4 5"],
    user: [["c", 12, 8, 4], "M4.5 20.5a7.5 7.5 0 0 1 15 0"],
    users: [["c", 9, 8, 3.2], "M3 20a6 6 0 0 1 12 0", ["c", 17, 9, 2.6], "M17.4 14.2A5 5 0 0 1 21.5 19"],
    download: ["M12 4v11", "M7.5 11l4.5 4.5 4.5-4.5", "M5 20h14"],
    upload: ["M12 15V4", "M7.5 8L12 3.5 16.5 8", "M5 20h14"],
    copy: [["r", 8, 8, 12, 12, 2], "M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"],
    play: ["M7 4.5l12 7.5-12 7.5z"],
    pause: ["M8 5v14", "M16 5v14"],
    restart: ["M4 12a8 8 0 1 0 2.6-5.9", "M4 4v5h5"],
    chevronRight: ["M9 5l7 7-7 7"],
    chevronLeft: ["M15 5l-7 7 7 7"],
    chevronDown: ["M5 9l7 7 7-7"],
    chevronUp: ["M5 15l7-7 7 7"],
    plus: ["M12 5v14", "M5 12h14"],
    minus: ["M5 12h14"],
    heart: ["M12 20.5s-8.5-5-8.5-11A4.6 4.6 0 0 1 12 7a4.6 4.6 0 0 1 8.5 2.5c0 6-8.5 11-8.5 11z"],
    question: [["c", 12, 12, 9], "M9.4 9.4a2.7 2.7 0 1 1 3.8 2.5c-.8.4-1.2 1-1.2 1.8", ["cf", 12, 16.8, 0.5]],
    chart: ["M4 20V10", "M10 20V4", "M16 20v-7", "M21 20H3"],
    wrench: ["M14.7 6.3a4 4 0 0 0-5.4 5.4L3.5 17.5a1.6 1.6 0 0 0 0 2.3l.7.7a1.6 1.6 0 0 0 2.3 0l5.8-5.8a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"],
    alert: ["M12 3.5l9.5 16.5h-19z", "M12 10v4.5", ["cf", 12, 17.3, 0.5]],
    megaphone: ["M4 10v4h3l8 4V6L7 10z", "M18.5 9.5a4 4 0 0 1 0 5"],
    book: ["M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z", "M4 5v16", "M8.5 7.5h6"],
    sprout: ["M12 21v-8", "M12 13c0-4 3-6.5 7.5-6.5 0 4-3 6.5-7.5 6.5z", "M12 15.5c0-3-2-5.5-6.5-5.5 0 3 2 5.5 6.5 5.5z"],
    arrowRight: ["M5 12h14", "M13 6l6 6-6 6"],
    quote: ["M9 8H6.5A2.5 2.5 0 0 0 4 10.5V13h5v-5", "M19 8h-2.5a2.5 2.5 0 0 0-2.5 2.5V13h5v-5", "M9 13c0 3-1 4-3 5", "M19 13c0 3-1 4-3 5"],
    gem: ["M6.5 3.5h11l4 5.5-9.5 12L2.5 9z", "M2.5 9h19", "M9 3.5L7.5 9 12 21", "M15 3.5L16.5 9 12 21"],
    trophy: ["M8 21h8", "M12 17v4", "M7 4h10v5a5 5 0 0 1-10 0z", "M17 5h3v2a3 3 0 0 1-3 3", "M7 5H4v2a3 3 0 0 0 3 3"],
    coffee: ["M4 9h12v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5z", "M16 10h1.5a2.5 2.5 0 0 1 0 5H16", "M7.5 3.5v2.2", "M10.5 3.5v2.2", "M13.5 3.5v2.2"],
    dots: [["cf", 5, 12, 1.4], ["cf", 12, 12, 1.4], ["cf", 19, 12, 1.4]],
    trash: ["M4 7h16", "M9 7V4.5h6V7", "M6.5 7l.8 13h9.4l.8-13", "M10 11v6", "M14 11v6"],
    settings: [["c", 12, 12, 3], "M12 2.5v3", "M12 18.5v3", "M2.5 12h3", "M18.5 12h3", "M5.3 5.3l2.1 2.1", "M16.6 16.6l2.1 2.1", "M5.3 18.7l2.1-2.1", "M16.6 7.4l2.1-2.1"],
    calendar: [["r", 3.5, 5, 17, 15.5, 2.5], "M3.5 10h17", "M8 3v4", "M16 3v4"],
    layers: ["M12 3l9 5-9 5-9-5z", "M3 12.5l9 5 9-5", "M3 16.5l9 5 9-5"],
    send: ["M21 3L10.5 13.5", "M21 3l-6.5 18-4-7.5L3 9.5z"],
    pencil: ["M4 20l1-4.5L16.5 4a2.1 2.1 0 0 1 3 3L8 18.5z", "M14.5 6l3.5 3.5"],
    spark: ["M12 3v5", "M12 16v5", "M3 12h5", "M16 12h5", "M6 6l3 3", "M15 15l3 3", "M6 18l3-3", "M15 9l3-3"],
    scale: ["M12 4v16", "M5 20h14", "M5 7h14", "M5 7l-2.5 6a3 3 0 0 0 5 0z", "M19 7l-2.5 6a3 3 0 0 0 5 0z"],
    cube: ["M12 3l8 4.5v9L12 21l-8-4.5v-9z", "M4 7.5L12 12l8-4.5", "M12 12v9"],
    anchor: [["c", 12, 5, 2], "M12 7v14", "M5 12a7 7 0 0 0 14 0", "M8 11H5v3", "M16 11h3v3"],
    ban: [["c", 12, 12, 9], "M5.6 5.6l12.8 12.8"],
    medical: ["M9.5 3.5h5v6h6v5h-6v6h-5v-6h-6v-5h6z"]
  };

  var CATEGORY_ICON = {
    curiosity: "question", contrast: "bolt", emotion: "heart", practical: "wrench", social: "users",
    second_person: "user", clickbait: "alert", overclaim: "megaphone", positive: "plus", negative: "minus"
  };
  var DRIVER_ICON = {
    curiosity: "question", surprise: "bolt", emotion: "heart", relevance: "user", utility: "wrench", fluency: "pencil", risk: "shield"
  };

  function icon(name, opts) {
    opts = opts || {};
    var d = dom();
    var size = opts.size || 20;
    var def = ICONS[name] || ICONS.question;
    var s = d.svg("svg", {
      viewBox: "0 0 24 24", width: size, height: size, fill: "none", stroke: "currentColor", "stroke-width": opts.stroke || 2,
      "stroke-linecap": "round", "stroke-linejoin": "round", class: "icon icon-" + name + (opts.class ? " " + opts.class : ""),
      "aria-hidden": "true", focusable: "false"
    });
    def.forEach(function (item) {
      if (typeof item === "string") s.appendChild(d.svg("path", { d: item }));
      else if (item[0] === "c") s.appendChild(d.svg("circle", { cx: item[1], cy: item[2], r: item[3] }));
      else if (item[0] === "cf") s.appendChild(d.svg("circle", { cx: item[1], cy: item[2], r: item[3], fill: "currentColor", stroke: "none" }));
      else if (item[0] === "r") s.appendChild(d.svg("rect", { x: item[1], y: item[2], width: item[3], height: item[4], rx: item[5] || 0 }));
      else if (item[0] === "l") s.appendChild(d.svg("line", { x1: item[1], y1: item[2], x2: item[3], y2: item[4] }));
      else if (item[0] === "f") s.appendChild(d.svg("path", { d: item[1], fill: "currentColor", stroke: "none" }));
    });
    if (opts.title) { s.removeAttribute("aria-hidden"); s.setAttribute("role", "img"); s.setAttribute("aria-label", opts.title); }
    return s;
  }

  /** Shared gradient definitions, mounted once at start (referenced as url(#dk-g-...)). */
  function mountDefs() {
    if (typeof document === "undefined" || document.getElementById("dk-defs")) return;
    var d = dom();
    function grad(id, stops, x2, y2) {
      return d.svg("linearGradient", { id: id, x1: 0, y1: 0, x2: x2 || 1, y2: y2 || 1 },
        stops.map(function (s) { return d.svg("stop", { offset: s[0], "stop-color": s[1] }); }));
    }
    var el = d.svg("svg", { id: "dk-defs", width: 0, height: 0, "aria-hidden": "true", focusable: "false", style: { position: "absolute", width: 0, height: 0, overflow: "hidden" } },
      d.svg("defs", null,
        grad("dk-g-brand", [[0, "#8b6cff"], [1, "#ff4fa3"]]),
        grad("dk-g-flame", [[0, "#ffd166"], [0.5, "#ff8a4c"], [1, "#ff4f7b"]], 0, 1),
        grad("dk-g-gold", [[0, "#fff1b8"], [0.45, "#fbbf24"], [1, "#f59e0b"]], 0, 1),
        grad("dk-g-ice", [[0, "#bff4ff"], [1, "#4fb9ff"]], 0, 1)
      ));
    document.body.insertBefore(el, document.body.firstChild);
  }

  /** The crown logo mark with the brand gradient. */
  function logo(size) {
    var d = dom();
    size = size || 28;
    return d.svg("svg", { viewBox: "0 0 24 24", width: size, height: size, class: "logo-mark", "aria-hidden": "true", focusable: "false" },
      d.svg("path", { d: "M3.2 18.6L2 7.2l5.7 4.5L12 3.4l4.3 8.3L22 7.2l-1.2 11.4z", fill: "url(#dk-g-brand)" }),
      d.svg("rect", { x: 3.6, y: 20, width: 16.8, height: 2, rx: 1, fill: "url(#dk-g-brand)" }),
      d.svg("circle", { cx: 12, cy: 3.4, r: 1.4, fill: "#fff", opacity: 0.9 }));
  }

  /** A filled, two-tone flame for the streak. lit=false draws it as a muted outline shape. */
  function flame(size, lit) {
    var d = dom();
    size = size || 22;
    var outer = "M12 2.2c.7 3.2 3.4 4.9 5 7.4 1.6 2.5 1.7 5.5.2 7.7C15.9 19.6 14.1 21.8 12 21.8s-3.9-2.2-5.2-4.5C5.3 15.1 5.4 12 7 9.6c1 1.4 1.8 2 3 2.4C9.3 8.4 10.7 5 12 2.2z";
    var inner = "M12 12.4c.4 1.8 2.3 2.7 2.3 4.7 0 1.7-1.1 3-2.3 3s-2.3-1.3-2.3-3c0-1.6.8-2.3 1.2-3.4.4.5.8.7 1.1.7z";
    return d.svg("svg", { viewBox: "0 0 24 24", width: size, height: size, class: "flame" + (lit === false ? " is-out" : ""), "aria-hidden": "true", focusable: "false" },
      d.svg("path", { d: outer, fill: lit === false ? "currentColor" : "url(#dk-g-flame)", opacity: lit === false ? 0.45 : 1 }),
      lit === false ? null : d.svg("path", { d: inner, fill: "#fff5d6", opacity: 0.95 }));
  }

  /** Trust Shield drawn in three states: intact, cracked, broken. */
  function shield(state, size) {
    var d = dom();
    size = size || 56;
    var whole = "M12 2.8l7.7 2.9v5.7c0 4.9-3.3 8.8-7.7 10.4-4.4-1.6-7.7-5.5-7.7-10.4V5.7z";
    var s = d.svg("svg", { viewBox: "0 0 24 24", width: size, height: size, class: "shield shield-" + state, "aria-hidden": "true", focusable: "false", fill: "none", stroke: "currentColor", "stroke-width": 1.7, "stroke-linecap": "round", "stroke-linejoin": "round" });
    if (state === "broken") {
      s.appendChild(d.svg("g", { transform: "rotate(-7 8 20)" },
        d.svg("path", { d: "M11 3.3L4.3 5.7v5.7c0 4.6 3 8.3 6.9 10l.6-4.6-2.2-2.6 2.3-3-1.3-3.4 1.2-4.4z", class: "shield-fill" })));
      s.appendChild(d.svg("g", { transform: "rotate(7 16 20)" },
        d.svg("path", { d: "M13.4 3.3l6.3 2.4v5.7c0 4.5-2.8 8.1-6.5 9.8l-.4-4.4 2.1-2.5-2.4-3.2 1.4-3.3-.9-4.5z", class: "shield-fill" })));
    } else {
      s.appendChild(d.svg("path", { d: whole, class: "shield-fill" }));
      if (state === "cracked") s.appendChild(d.svg("path", { d: "M12 2.9l-.9 4.6 2.3 2.4-2.6 3 1.7 3.2-.9 4.8", "stroke-width": 1.5 }));
      else s.appendChild(d.svg("path", { d: "M8.3 12.2l2.5 2.5 4.9-5.1", "stroke-width": 2 }));
    }
    return s;
  }

  var RARITY_GEMS = { common: 1, rare: 2, epic: 3, legendary: 4 };
  /** One to four small gems: an extra, non-colour cue for the rarity. */
  function gems(rarity, size) {
    var d = dom();
    var n = RARITY_GEMS[rarity] || 1;
    var wrap = d.h("span.gems", { "aria-hidden": "true" });
    for (var i = 0; i < n; i++) wrap.appendChild(icon("gem", { size: size || 13, stroke: 2 }));
    return wrap;
  }

  /** Treasure chest illustration, closed or open. */
  function chest(opts) {
    opts = opts || {};
    var d = dom();
    var open = !!opts.open;
    var s = d.svg("svg", { viewBox: "0 0 120 100", width: opts.size || 140, class: "chest" + (open ? " is-open" : ""), "aria-hidden": "true", focusable: "false" });
    s.appendChild(d.svg("defs", null,
      d.svg("linearGradient", { id: "ch-wood", x1: 0, y1: 0, x2: 0, y2: 1 }, d.svg("stop", { offset: 0, "stop-color": "#8b5a3c" }), d.svg("stop", { offset: 1, "stop-color": "#5b3524" })),
      d.svg("radialGradient", { id: "ch-glow", cx: 0.5, cy: 0.5, r: 0.5 }, d.svg("stop", { offset: 0, "stop-color": "#fff3b0", "stop-opacity": 0.95 }), d.svg("stop", { offset: 1, "stop-color": "#fbbf24", "stop-opacity": 0 }))));
    if (open) s.appendChild(d.svg("ellipse", { cx: 60, cy: 46, rx: 46, ry: 26, fill: "url(#ch-glow)" }));
    s.appendChild(d.svg("rect", { x: 14, y: 46, width: 92, height: 42, rx: 6, fill: "url(#ch-wood)" }));
    s.appendChild(d.svg("rect", { x: 14, y: 58, width: 92, height: 7, fill: "url(#dk-g-gold)" }));
    s.appendChild(d.svg("rect", { x: 22, y: 46, width: 7, height: 42, fill: "url(#dk-g-gold)", opacity: 0.9 }));
    s.appendChild(d.svg("rect", { x: 91, y: 46, width: 7, height: 42, fill: "url(#dk-g-gold)", opacity: 0.9 }));
    var lid = d.svg("g", open ? { transform: "rotate(-24 16 48)" } : null,
      d.svg("path", { d: "M14 48V36a22 22 0 0 1 22-22h48a22 22 0 0 1 22 22v12z", fill: "url(#ch-wood)" }),
      d.svg("rect", { x: 14, y: 40, width: 92, height: 8, fill: "url(#dk-g-gold)" }),
      d.svg("rect", { x: 22, y: 14, width: 7, height: 34, fill: "url(#dk-g-gold)", opacity: 0.9 }),
      d.svg("rect", { x: 91, y: 14, width: 7, height: 34, fill: "url(#dk-g-gold)", opacity: 0.9 }));
    s.appendChild(lid);
    s.appendChild(d.svg("rect", { x: 53, y: open ? 56 : 42, width: 14, height: 16, rx: 3, fill: "url(#dk-g-gold)", stroke: "#8a5a00", "stroke-width": 1.5 }));
    s.appendChild(d.svg("circle", { cx: 60, cy: open ? 63 : 49, r: 2.2, fill: "#5b3524" }));
    return s;
  }

  function hashString(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); }
    return h >>> 0;
  }

  /** A friendly monster for each boss, generated from its id and tier (tier = more horns and spikes). */
  function bossAvatar(boss, size) {
    var d = dom();
    size = size || 84;
    var seed = hashString(String(boss.id || boss.name || "boss"));
    var tier = Math.min(3, Math.max(1, boss.tier || 1));
    var hues = { 1: [168, 190], 2: [262, 292], 3: [336, 8] };
    var span = hues[tier];
    var hue = span[0] + (seed % 20);
    var hue2 = span[1] + ((seed >> 3) % 20);
    var gid = "bg-" + (seed % 100000) + "-" + dom().uid("a");
    var eyes = 1 + (seed >> 5) % 3;
    var teeth = 3 + (seed >> 7) % 3;
    var s = d.svg("svg", { viewBox: "0 0 96 96", width: size, height: size, class: "boss-avatar tier-" + tier, "aria-hidden": "true", focusable: "false" });
    s.appendChild(d.svg("defs", null, d.svg("linearGradient", { id: gid, x1: 0, y1: 0, x2: 1, y2: 1 },
      d.svg("stop", { offset: 0, "stop-color": "hsl(" + hue + " 80% 62%)" }), d.svg("stop", { offset: 1, "stop-color": "hsl(" + hue2 + " 78% 48%)" }))));
    // horns or spikes
    var horns = tier === 1 ? [[24, 24, 14, 6], [72, 24, 82, 6]] : tier === 2 ? [[22, 26, 8, 2], [74, 26, 88, 2]] : [[22, 26, 8, 2], [74, 26, 88, 2], [40, 18, 48, 2], [56, 18, 48, 2]];
    horns.forEach(function (hn) {
      s.appendChild(d.svg("path", { d: "M" + hn[0] + " " + (hn[1] + 8) + " L" + hn[2] + " " + hn[3] + " L" + (hn[0] + (hn[0] < 48 ? 14 : -14)) + " " + (hn[1] + 2) + " Z", fill: "#ffe9b0", stroke: "rgba(0,0,0,.25)", "stroke-width": 1.2, "stroke-linejoin": "round" }));
    });
    s.appendChild(d.svg("path", { d: "M14 56c0-22 15-36 34-36s34 14 34 36c0 16-12 26-34 26S14 72 14 56z", fill: "url(#" + gid + ")", stroke: "rgba(0,0,0,.28)", "stroke-width": 1.6 }));
    var eyeXs = eyes === 1 ? [48] : eyes === 2 ? [36, 60] : [30, 48, 66];
    eyeXs.forEach(function (x, i) {
      var r = eyes === 1 ? 11 : 7.5;
      var y = 48 + (eyes === 3 && i === 1 ? -4 : 0);
      s.appendChild(d.svg("circle", { cx: x, cy: y, r: r, fill: "#fff", stroke: "rgba(0,0,0,.3)", "stroke-width": 1 }));
      s.appendChild(d.svg("circle", { cx: x + 1.4, cy: y + 1.2, r: r * 0.46, fill: "#1a1030" }));
      s.appendChild(d.svg("circle", { cx: x - 0.4, cy: y - 1.6, r: r * 0.16, fill: "#fff" }));
    });
    var my = 66, mw = 30;
    s.appendChild(d.svg("path", { d: "M" + (48 - mw / 2) + " " + my + "q" + (mw / 2) + " 12 " + mw + " 0q-" + (mw / 2) + " 4 -" + mw + " 0z", fill: "#2a0f2e" }));
    for (var i = 0; i < teeth; i++) {
      var tx = 48 - mw / 2 + 4 + i * ((mw - 8) / Math.max(teeth - 1, 1));
      s.appendChild(d.svg("path", { d: "M" + (tx - 2.2) + " " + (my + 0.4) + "l2.2 4.2l2.2 -4.2z", fill: "#fff" }));
    }
    return s;
  }

  var VERDICT_ICON = { ok: "shieldCheck", review: "alert", blocked: "x" };
  var SEVERITY_ICON = { error: "x", warn: "alert", info: "info" };

  return {
    icon: icon, ICONS: ICONS, CATEGORY_ICON: CATEGORY_ICON, DRIVER_ICON: DRIVER_ICON, mountDefs: mountDefs, logo: logo,
    flame: flame, shield: shield, gems: gems, chest: chest, bossAvatar: bossAvatar, hashString: hashString,
    VERDICT_ICON: VERDICT_ICON, SEVERITY_ICON: SEVERITY_ICON
  };
});
