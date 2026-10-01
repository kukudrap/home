/* Charts and meters, all hand written: HTML meters, SVG line, bar and interval charts, a ring gauge.
 * SVG charts are drawn at the real container width (ResizeObserver) so text stays readable on phones.
 * Every chart has a table twin inside <details>, a legend when there are several series, and a hover and
 * keyboard readout; values are never only in a tooltip.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.charts = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  function dom() { return root.DK.ui.dom; }
  function icons() { return root.DK.ui.icons; }

  // -- pure helpers (unit tested) ----------------------------------------------------------------
  function niceStep(range, count) {
    var raw = range / Math.max(1, count);
    var mag = Math.pow(10, Math.floor(Math.log10(raw)));
    var norm = raw / mag;
    return (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
  }

  /** Round tick values covering [min, max]. Returns {ticks, step, niceMax}. */
  function niceTicks(min, max, count) {
    if (!(max > min)) max = min + 1;
    var step = niceStep(max - min, count || 5);
    var first = Math.ceil(min / step - 1e-9) * step;
    var ticks = [];
    for (var v = first; v <= max + step * 1e-9; v += step) ticks.push(Number(v.toFixed(10)));
    return { ticks: ticks, step: step, niceMax: Math.ceil(max / step - 1e-9) * step };
  }

  /** Evenly spaced sample of at most n points that always keeps the first and the last. */
  function sample(points, n) {
    if (points.length <= n) return points.slice();
    var out = [];
    for (var i = 0; i < n; i++) out.push(points[Math.round(i * (points.length - 1) / (n - 1))]);
    return out;
  }

  // -- meter ------------------------------------------------------------------------------------
  /**
   * Horizontal meter. opts: {value, max, label, tone, size, marker, markerLabel, valueText(v)}.
   * The element has set(value) to animate to a new value and setMarker(value).
   */
  function meter(opts) {
    var d = dom();
    opts = opts || {};
    var max = opts.max || 100;
    var el = d.h("div.meter" + (opts.tone ? ".tone-" + opts.tone : "") + (opts.size ? ".meter-" + opts.size : ""), {
      role: "meter", "aria-label": opts.label || null, "aria-valuemin": 0, "aria-valuemax": max, "aria-valuenow": 0
    });
    var fill = d.h("div.meter-fill");
    var track = d.h("div.meter-track", null, fill);
    var flag = null, markerEl = null;
    if (opts.marker !== undefined && opts.marker !== null) {
      flag = d.h("span.meter-flag", null, opts.markerLabel || "");
      markerEl = d.h("div.meter-marker", { "aria-hidden": "true" }, flag);
      markerEl.style.setProperty("--m", String(d.clamp(opts.marker / max, 0, 1)));
      track.appendChild(markerEl);
    }
    el.appendChild(track);
    var current = 0;
    function set(v, immediate) {
      v = d.clamp(Number(v) || 0, 0, max);
      current = v;
      el.setAttribute("aria-valuenow", String(Math.round(v * 10) / 10));
      el.setAttribute("aria-valuetext", opts.valueText ? opts.valueText(v) : Math.round(v) + " / " + max);
      el.classList.toggle("is-empty", v <= 0);
      if (immediate) fill.style.setProperty("--v", String(v / max));
      else d.raf(function () { fill.style.setProperty("--v", String(v / max)); });
    }
    el.set = set;
    el.setMarker = function (v, label) {
      if (!markerEl) return;
      markerEl.style.setProperty("--m", String(d.clamp(v / max, 0, 1)));
      if (label !== undefined && flag) flag.textContent = label;
    };
    el.current = function () { return current; };
    set(opts.value || 0, opts.value === undefined);
    return el;
  }

  /** Six driver bars with labels from the scoring spec. opts: {labels, lang, drivers, parts, compact}. */
  function driverBars(opts) {
    var d = dom();
    var drivers = opts.drivers;
    var rows = {};
    var wrap = d.h("div.drivers" + (opts.compact ? ".compact" : ""));
    drivers.forEach(function (k) {
      var lab = opts.labels && opts.labels[k] ? (opts.labels[k][opts.lang] || opts.labels[k].en) : k;
      var val = d.h("span.driver-val", null, "0");
      var m = meter({ max: 100, label: lab, tone: "d-" + k, size: "sm", value: 0 });
      var row = d.h("div.driver-row", null,
        d.h("span.driver-name", null, icons().icon(icons().DRIVER_ICON[k] || "spark", { size: 15 }), d.h("span", null, lab)), m, val);
      rows[k] = { meter: m, val: val, shown: 0 };
      wrap.appendChild(row);
    });
    function update(parts) {
      drivers.forEach(function (k) {
        var v = parts && typeof parts[k] === "number" ? parts[k] : 0;
        var r = rows[k];
        r.meter.set(v);
        d.tween({ from: r.shown, to: v, ms: 450, onUpdate: function (x) { r.val.textContent = String(Math.round(x)); } });
        r.shown = v;
      });
    }
    wrap.update = update;
    update(opts.parts || {});
    return wrap;
  }

  /** Two-sided probability bar (for the model's win probability). */
  function splitBar(opts) {
    var d = dom();
    var a = d.clamp(opts.a, 0, 1);
    var pa = Math.round(a * 100), pb = 100 - pa;
    var el = d.h("div.split", { role: "img", "aria-label": opts.aria || (opts.labelA + " " + pa + "%, " + opts.labelB + " " + pb + "%") },
      d.h("div.split-labels", { "aria-hidden": "true" }, d.h("span", null, opts.labelA + " " + pa + "%"), d.h("span", null, opts.labelB + " " + pb + "%")),
      d.h("div.split-track", { "aria-hidden": "true" },
        d.h("div.split-a" + (a >= 0.5 ? ".is-lead" : ""), { style: { "--w": "0%" } }),
        d.h("div.split-b" + (a < 0.5 ? ".is-lead" : ""), { style: { "--w": "0%" } })));
    var sa = el.querySelector(".split-a"), sb = el.querySelector(".split-b");
    d.raf(function () { sa.style.setProperty("--w", pa + "%"); sb.style.setProperty("--w", pb + "%"); });
    return el;
  }

  /** Circular gauge. opts: {value, max, size, stroke, label, tone}. Returns an element with set(value, text). */
  function ring(opts) {
    var d = dom();
    var size = opts.size || 88, stroke = opts.stroke || 9, max = opts.max || 100;
    var r = (size - stroke) / 2, c = 2 * Math.PI * r;
    var prog = d.svg("circle", { cx: size / 2, cy: size / 2, r: r, class: "ring-prog", "stroke-dasharray": c, "stroke-dashoffset": c, "stroke-width": stroke, fill: "none", "stroke-linecap": "round", transform: "rotate(-90 " + size / 2 + " " + size / 2 + ")" });
    var text = d.h("span.ring-text", null, opts.text === undefined ? "" : opts.text);
    var el = d.h("div.ring" + (opts.tone ? ".tone-" + opts.tone : ""), { role: "img", "aria-label": opts.label || null, style: { width: size + "px", height: size + "px" } },
      d.svg("svg", { viewBox: "0 0 " + size + " " + size, width: size, height: size, "aria-hidden": "true", focusable: "false" },
        d.svg("circle", { cx: size / 2, cy: size / 2, r: r, class: "ring-track", fill: "none", "stroke-width": stroke }), prog),
      text);
    el.set = function (v, txt, label) {
      var k = d.clamp(v / max, 0, 1);
      d.raf(function () { prog.setAttribute("stroke-dashoffset", String(c * (1 - k))); });
      if (txt !== undefined) text.textContent = txt;
      if (label) el.setAttribute("aria-label", label);
    };
    el.set(opts.value || 0);
    return el;
  }

  // -- width aware SVG helper ----------------------------------------------------------------------
  function sized(stage, draw) {
    var last = 0;
    function go(force) {
      var w = Math.floor(stage.clientWidth) || 560;
      if (!force && Math.abs(w - last) < 1) return;
      last = w;
      draw(w);
    }
    if (typeof ResizeObserver === "function") {
      var ro = new ResizeObserver(function () { go(false); });
      ro.observe(stage);
      stage.__ro = ro;
    } else if (root.addEventListener) {
      root.addEventListener("resize", function () { go(false); });
    }
    return go;
  }

  /** Collapsible table twin of a chart. rows: array of arrays of strings. */
  function dataTable(caption, headers, rows) {
    var d = dom();
    var body = d.h("tbody");
    rows.forEach(function (r) { body.appendChild(d.h("tr", null, r.map(function (c, i) { return i === 0 ? d.h("th", { scope: "row" }, c) : d.h("td", null, c); }))); });
    return d.h("details.chart-table", null,
      d.h("summary", null, d.t("chart.showTable")),
      d.h("div.table-scroll", null,
        d.h("table.data-table", null, d.h("caption", null, caption),
          d.h("thead", null, d.h("tr", null, headers.map(function (hd) { return d.h("th", { scope: "col" }, hd); }))), body)));
  }

  // -- line chart -------------------------------------------------------------------------------------
  /**
   * opts: {series: [{id, label, slot, points: [[x, y], ...]}], xLabel, yLabel, xFmt, yFmt, height, ariaLabel,
   *        caption, nominal: {y, label}, yMin, tableRows}
   * Colours come from the --series-N tokens through the s1..s4 classes. Returns {el, setSeries(series), redraw()}.
   */
  function lineChart(opts) {
    var d = dom();
    var series = opts.series || [];
    var height = opts.height || 260;
    var xFmt = opts.xFmt || function (v) { return String(v); };
    var yFmt = opts.yFmt || function (v) { return String(v); };
    var stage = d.h("div.chart-stage", { tabindex: "0", role: "group", "aria-label": opts.ariaLabel || "" });
    var tip = d.h("div.chart-tip", { "aria-hidden": "true" });
    tip.style.display = "none";
    var legend = d.h("ul.legend");
    var tableHost = d.h("div.chart-table-host");
    var live = d.h("div.sr-only", { "aria-live": "polite" });
    var el = d.h("figure.chart", null,
      opts.caption ? d.h("figcaption.chart-caption", null, opts.caption) : null,
      legend, stage, live, tableHost);
    var hoverIdx = null;
    var geo = null;

    function allX() {
      var xs = [];
      series.forEach(function (s) { s.points.forEach(function (p) { if (xs.indexOf(p[0]) < 0) xs.push(p[0]); }); });
      return xs.sort(function (a, b) { return a - b; });
    }

    function buildLegend() {
      d.clear(legend);
      if (series.length < 2) { legend.style.display = "none"; return; }
      legend.style.display = "";
      series.forEach(function (s) {
        legend.appendChild(d.h("li.legend-item", null, d.h("span.legend-key.s" + s.slot, { "aria-hidden": "true" }), d.h("span", null, s.label)));
      });
    }

    function buildTable() {
      var xs = sample(allX(), opts.tableRows || 11);
      var rows = xs.map(function (x) {
        return [xFmt(x)].concat(series.map(function (s) {
          var p = s.points.reduce(function (best, q) { return Math.abs(q[0] - x) < Math.abs(best[0] - x) ? q : best; }, s.points[0]);
          return p ? yFmt(p[1]) : "-";
        }));
      });
      d.fill(tableHost, dataTable(opts.caption || opts.ariaLabel || "", [opts.xLabel || "x"].concat(series.map(function (s) { return s.label; })), rows));
    }

    function draw(W) {
      d.clear(stage);
      stage.appendChild(tip);
      if (!series.length || !series[0].points.length) return;
      var narrow = W < 440;
      var M = { l: narrow ? 40 : 48, r: narrow ? 14 : 72, t: 12, b: 40 };
      var iw = W - M.l - M.r, ih = height - M.t - M.b;
      var xs = allX();
      var xmin = xs[0], xmax = xs[xs.length - 1] === xs[0] ? xs[0] + 1 : xs[xs.length - 1];
      var ymaxData = 0;
      series.forEach(function (s) { s.points.forEach(function (p) { ymaxData = Math.max(ymaxData, p[1]); }); });
      if (opts.nominal) ymaxData = Math.max(ymaxData, opts.nominal.y);
      var yt = niceTicks(opts.yMin || 0, ymaxData * 1.05 || 1, 4);
      var ymin = opts.yMin || 0, ymax = yt.niceMax;
      function X(x) { return M.l + (x - xmin) / (xmax - xmin) * iw; }
      function Y(y) { return M.t + ih - (y - ymin) / (ymax - ymin) * ih; }
      geo = { X: X, Y: Y, xs: xs, M: M, iw: iw, ih: ih, W: W };

      var svg = d.svg("svg", { viewBox: "0 0 " + W + " " + height, width: W, height: height, class: "chart-svg", "aria-hidden": "true", focusable: "false" });
      yt.ticks.forEach(function (v) {
        svg.appendChild(d.svg("line", { x1: M.l, x2: W - M.r, y1: Y(v), y2: Y(v), class: "grid" }));
        svg.appendChild(d.svg("text", { x: M.l - 8, y: Y(v) + 4, class: "tick", "text-anchor": "end" }, yFmt(v)));
      });
      svg.appendChild(d.svg("line", { x1: M.l, x2: W - M.r, y1: Y(ymin), y2: Y(ymin), class: "axis" }));
      niceTicks(xmin, xmax, narrow ? 3 : 5).ticks.forEach(function (v) {
        svg.appendChild(d.svg("text", { x: X(v), y: height - M.b + 18, class: "tick", "text-anchor": "middle" }, xFmt(v)));
      });
      if (opts.xLabel) svg.appendChild(d.svg("text", { x: M.l + iw / 2, y: height - 6, class: "axis-title", "text-anchor": "middle" }, opts.xLabel));
      if (opts.nominal) {
        svg.appendChild(d.svg("line", { x1: M.l, x2: W - M.r, y1: Y(opts.nominal.y), y2: Y(opts.nominal.y), class: "ref-line" }));
        svg.appendChild(d.svg("text", { x: W - M.r, y: Y(opts.nominal.y) - 6, class: "ref-label", "text-anchor": "end" }, opts.nominal.label));
      }
      series.forEach(function (s) {
        if (!s.points.length) return;
        var path = s.points.map(function (p, i) { return (i ? "L" : "M") + X(p[0]).toFixed(1) + " " + Y(p[1]).toFixed(1); }).join(" ");
        svg.appendChild(d.svg("path", { d: path, class: "line s" + s.slot, fill: "none" }));
        var last = s.points[s.points.length - 1];
        svg.appendChild(d.svg("circle", { cx: X(last[0]), cy: Y(last[1]), r: 6, class: "dot-ring" }));
        svg.appendChild(d.svg("circle", { cx: X(last[0]), cy: Y(last[1]), r: 4, class: "dot s" + s.slot }));
      });
      if (!narrow && series.length >= 2) {
        // Direct labels at the line ends; when two ends are close the legend above still carries identity.
        var ends = series.map(function (s) { var p = s.points[s.points.length - 1]; return { s: s, y: Y(p[1]) }; }).sort(function (a, b) { return a.y - b.y; });
        var ok = ends.every(function (e, i) { return i === 0 || e.y - ends[i - 1].y >= 14; });
        if (ok) ends.forEach(function (e) { svg.appendChild(d.svg("text", { x: W - M.r + 10, y: e.y + 4, class: "end-label" }, e.s.label.length > 14 ? e.s.label.slice(0, 13) + "." : e.s.label)); });
      }
      var cross = d.svg("g", { class: "cross", style: { display: "none" } },
        d.svg("line", { x1: 0, x2: 0, y1: M.t, y2: M.t + ih }));
      series.forEach(function (s) { cross.appendChild(d.svg("circle", { r: 5, class: "dot s" + s.slot })); });
      svg.appendChild(cross);
      var hit = d.svg("rect", { x: M.l, y: M.t, width: iw, height: ih, fill: "transparent", class: "hit" });
      svg.appendChild(hit);
      stage.insertBefore(svg, tip);
      svg.__cross = cross;

      function nearest(px) {
        var best = 0, bd = Infinity;
        xs.forEach(function (x, i) { var dd = Math.abs(X(x) - px); if (dd < bd) { bd = dd; best = i; } });
        return best;
      }
      hit.addEventListener("pointermove", function (e) {
        var rect = svg.getBoundingClientRect();
        showAt(nearest(e.clientX - rect.left));
      });
      hit.addEventListener("pointerleave", function () { if (document.activeElement !== stage) hideTip(); });
      if (hoverIdx !== null) showAt(Math.min(hoverIdx, xs.length - 1));
    }

    function valueAt(s, x) {
      var best = null;
      s.points.forEach(function (p) { if (best === null || Math.abs(p[0] - x) < Math.abs(best[0] - x)) best = p; });
      return best;
    }

    function showAt(i) {
      if (!geo) return;
      hoverIdx = i;
      var x = geo.xs[i], px = geo.X(x);
      var svg = stage.querySelector("svg");
      if (!svg) return;
      var cross = svg.__cross;
      cross.style.display = "";
      cross.firstChild.setAttribute("x1", px);
      cross.firstChild.setAttribute("x2", px);
      var rows = [d.h("div.tip-x", null, (opts.xLabel ? opts.xLabel + " " : "") + xFmt(x))];
      series.forEach(function (s, k) {
        var p = valueAt(s, x);
        if (!p) return;
        var dot = cross.childNodes[k + 1];
        dot.setAttribute("cx", px);
        dot.setAttribute("cy", geo.Y(p[1]));
        rows.push(d.h("div.tip-row", null, d.h("span.legend-key.s" + s.slot, { "aria-hidden": "true" }), d.h("strong.tip-val", null, yFmt(p[1])), d.h("span.tip-name", null, s.label)));
      });
      d.fill(tip, rows);
      tip.style.display = "";
      var tw = tip.offsetWidth || 150;
      var left = px + 14;
      if (left + tw > geo.W - 4) left = px - tw - 14;
      tip.style.left = Math.max(4, left) + "px";
      tip.style.top = geo.M.t + 4 + "px";
      live.textContent = rows.map(function (r) { return r.textContent; }).join(", ");
    }

    function hideTip() {
      hoverIdx = null;
      tip.style.display = "none";
      var svg = stage.querySelector("svg");
      if (svg && svg.__cross) svg.__cross.style.display = "none";
    }

    stage.addEventListener("keydown", function (e) {
      if (!geo) return;
      var n = geo.xs.length;
      if (e.key === "ArrowRight") { e.preventDefault(); showAt(hoverIdx === null ? n - 1 : Math.min(n - 1, hoverIdx + 1)); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); showAt(hoverIdx === null ? n - 1 : Math.max(0, hoverIdx - 1)); }
      else if (e.key === "Escape") hideTip();
    });
    stage.addEventListener("focus", function () { if (hoverIdx === null && geo) showAt(geo.xs.length - 1); });
    stage.addEventListener("blur", hideTip);

    var go = sized(stage, draw);
    buildLegend();
    buildTable();
    stage.style.minHeight = height + "px";
    d.raf(function () { go(true); });

    return {
      el: el,
      setSeries: function (next) { series = next; buildLegend(); go(true); },
      refreshTable: function () { buildTable(); },
      redraw: function () { go(true); }
    };
  }

  // -- horizontal bar chart -------------------------------------------------------------------------------
  /**
   * opts: {bars: [{id, label, value, slot, note}], max, fmt(v), refLine: {value, label}, ariaLabel, caption, headers}
   * Bars are at most 24px thick with a rounded data end; the reference line is a plain hairline.
   */
  function barChart(opts) {
    var d = dom();
    var bars = opts.bars;
    var fmtv = opts.fmt || function (v) { return String(v); };
    var stage = d.h("div.chart-stage", { role: "img", "aria-label": opts.ariaLabel || "" });
    var el = d.h("figure.chart", null,
      opts.caption ? d.h("figcaption.chart-caption", null, opts.caption) : null, stage,
      dataTable(opts.caption || opts.ariaLabel || "", opts.headers || ["", ""], bars.map(function (b) { return [b.label, fmtv(b.value)]; })));
    var shown = false;

    function draw(W) {
      d.clear(stage);
      var narrow = W < 460;
      var labelW = narrow ? 0 : Math.min(190, Math.round(W * 0.36));
      var valueW = 64;
      var rowH = narrow ? 58 : 44;
      var top = opts.refLine ? 22 : 6;
      var H = top + bars.length * rowH + 6;
      var x0 = labelW, x1 = W - valueW;
      var max = opts.max || Math.max.apply(null, bars.map(function (b) { return b.value; })) * 1.1;
      function X(v) { return x0 + (v / max) * (x1 - x0); }
      var svg = d.svg("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, class: "chart-svg", "aria-hidden": "true", focusable: "false" });
      bars.forEach(function (b, i) {
        var y = top + i * rowH;
        var by = narrow ? y + 22 : y + (rowH - 22) / 2;
        var label = d.svg("text", { x: narrow ? 0 : 0, y: narrow ? y + 14 : by + 15, class: "bar-label" }, b.label);
        svg.appendChild(label);
        svg.appendChild(d.svg("rect", { x: x0, y: by, width: x1 - x0, height: 22, rx: 4, class: "bar-track" }));
        var w = Math.max(2, X(b.value) - x0);
        var rect = d.svg("rect", { x: x0, y: by, width: shown ? w : 0, height: 22, rx: 4, class: "bar s" + b.slot });
        svg.appendChild(rect);
        svg.appendChild(d.svg("text", { x: x1 + 8, y: by + 16, class: "bar-value" }, fmtv(b.value)));
        if (!shown) d.raf(function () { rect.setAttribute("width", w); rect.style.transition = "width .9s cubic-bezier(.2,.8,.2,1)"; });
      });
      if (opts.refLine) {
        var rx = X(opts.refLine.value);
        svg.appendChild(d.svg("line", { x1: rx, x2: rx, y1: top - 4, y2: H - 4, class: "ref-line" }));
        svg.appendChild(d.svg("text", { x: rx, y: 12, class: "ref-label", "text-anchor": "middle" }, opts.refLine.label));
      }
      stage.appendChild(svg);
      shown = true;
    }
    var go = sized(stage, draw);
    d.raf(function () { go(true); });
    return { el: el, redraw: function () { shown = false; go(true); } };
  }

  // -- interval plot --------------------------------------------------------------------------------------
  /**
   * Point with an interval against a zero line. opts: {point, lo, hi, fmt, zeroLabel, ariaLabel}
   * Used for "B minus A" with its Newcombe interval.
   */
  function intervalPlot(opts) {
    var d = dom();
    var fmtv = opts.fmt || function (v) { return v.toFixed(1); };
    var stage = d.h("div.chart-stage.interval", { role: "img", "aria-label": opts.ariaLabel || "" });
    function draw(W) {
      d.clear(stage);
      var H = 92, pad = 22;
      var span = Math.max(Math.abs(opts.lo), Math.abs(opts.hi), Math.abs(opts.point), 1e-9) * 1.25;
      var X = function (v) { return pad + (v + span) / (2 * span) * (W - 2 * pad); };
      var svg = d.svg("svg", { viewBox: "0 0 " + W + " " + H, width: W, height: H, class: "chart-svg", "aria-hidden": "true", focusable: "false" });
      var zx = X(0), y = 38;
      svg.appendChild(d.svg("line", { x1: pad, x2: W - pad, y1: y, y2: y, class: "axis" }));
      svg.appendChild(d.svg("line", { x1: zx, x2: zx, y1: 12, y2: 62, class: "ref-line" }));
      svg.appendChild(d.svg("text", { x: zx, y: 76, class: "ref-label", "text-anchor": "middle" }, opts.zeroLabel || "0"));
      var excl = opts.lo > 0 || opts.hi < 0;
      svg.appendChild(d.svg("line", { x1: X(opts.lo), x2: X(opts.hi), y1: y, y2: y, class: "ci-line " + (excl ? "is-clear" : "is-unclear") }));
      svg.appendChild(d.svg("line", { x1: X(opts.lo), x2: X(opts.lo), y1: y - 8, y2: y + 8, class: "ci-cap " + (excl ? "is-clear" : "is-unclear") }));
      svg.appendChild(d.svg("line", { x1: X(opts.hi), x2: X(opts.hi), y1: y - 8, y2: y + 8, class: "ci-cap " + (excl ? "is-clear" : "is-unclear") }));
      svg.appendChild(d.svg("circle", { cx: X(opts.point), cy: y, r: 9, class: "dot-ring" }));
      svg.appendChild(d.svg("circle", { cx: X(opts.point), cy: y, r: 6, class: "dot s1" }));
      var anchorLo = X(opts.lo) < pad + 30 ? "start" : "middle";
      svg.appendChild(d.svg("text", { x: X(opts.lo), y: 14, class: "tick", "text-anchor": anchorLo }, fmtv(opts.lo)));
      svg.appendChild(d.svg("text", { x: X(opts.hi), y: 14, class: "tick", "text-anchor": X(opts.hi) > W - pad - 30 ? "end" : "middle" }, fmtv(opts.hi)));
      stage.appendChild(svg);
    }
    var go = sized(stage, draw);
    d.raf(function () { go(true); });
    return { el: stage, redraw: function () { go(true); } };
  }

  return {
    niceTicks: niceTicks, niceStep: niceStep, sample: sample, meter: meter, driverBars: driverBars, splitBar: splitBar,
    ring: ring, lineChart: lineChart, barChart: barChart, intervalPlot: intervalPlot, dataTable: dataTable
  };
});
