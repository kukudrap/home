/* Reusable interface pieces: tabs, segmented filters, switches, sliders, dialogs, toasts, chips,
 * empty states. They build plain DOM and take care of keyboard use and ARIA.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.widgets = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  function dom() { return root.DK.ui.dom; }
  function icons() { return root.DK.ui.icons; }

  /** Pill with optional icon. tone: brand, info, ok, xp, risk, warn, muted. */
  function chip(text, opts) {
    opts = opts || {};
    var d = dom();
    return d.h("span.chip" + (opts.tone ? ".tone-" + opts.tone : ""), { title: opts.title || null },
      opts.icon ? icons().icon(opts.icon, { size: opts.iconSize || 14 }) : null,
      d.h("span.chip-text", null, text));
  }

  /** Section heading with an optional subtitle and a right-hand slot. */
  function heading(level, title, sub, right) {
    var d = dom();
    return d.h("div.heading",
      d.h("div.heading-main", d.h("h" + level + ".heading-title", null, title), sub ? d.h("p.heading-sub", null, sub) : null),
      right ? d.h("div.heading-right", null, right) : null);
  }

  function emptyState(opts) {
    var d = dom();
    return d.h("div.empty", { role: "note" },
      d.h("div.empty-icon", null, icons().icon(opts.icon || "info", { size: 32 })),
      d.h("h3.empty-title", null, opts.title),
      opts.text ? d.h("p.empty-text", null, opts.text) : null,
      opts.action || null);
  }

  /**
   * Tabs with the WAI-ARIA keyboard pattern. opts: {label, items: [{id, label, icon}], active, onChange(id, panel)}.
   * Returns {el, panel, select(id), active()}; the caller fills `panel` inside onChange.
   */
  function tabs(opts) {
    var d = dom();
    var base = d.uid("tabs");
    var panel = d.h("div.tabpanel", { role: "tabpanel", id: base + "-panel" });
    var list = d.h("div.tabs", { role: "tablist", "aria-label": opts.label || "" });
    var btns = {};
    var order = opts.items.map(function (i) { return i.id; });
    var active = null;

    function select(id, focus, silent) {
      if (!btns[id]) return;
      active = id;
      order.forEach(function (k) {
        var on = k === id;
        btns[k].setAttribute("aria-selected", on ? "true" : "false");
        btns[k].setAttribute("tabindex", on ? "0" : "-1");
        btns[k].classList.toggle("is-active", on);
      });
      panel.setAttribute("aria-labelledby", btns[id].id);
      if (focus) btns[id].focus();
      if (!silent && opts.onChange) opts.onChange(id, panel);
    }

    opts.items.forEach(function (it) {
      var b = d.h("button.tab", {
        type: "button", role: "tab", id: base + "-" + it.id, "aria-controls": panel.id, "aria-selected": "false", tabindex: "-1",
        onclick: function () { select(it.id, false); },
        onkeydown: function (e) {
          var i = order.indexOf(it.id), n = order.length, to = null;
          if (e.key === "ArrowRight") to = order[(i + 1) % n];
          else if (e.key === "ArrowLeft") to = order[(i - 1 + n) % n];
          else if (e.key === "Home") to = order[0];
          else if (e.key === "End") to = order[n - 1];
          if (to) { e.preventDefault(); select(to, true); }
        }
      }, it.icon ? icons().icon(it.icon, { size: 18 }) : null, d.h("span.tab-label", null, it.label));
      btns[it.id] = b;
      list.appendChild(b);
    });

    var api = { el: list, panel: panel, select: function (id, focus) { select(id, !!focus); }, active: function () { return active; } };
    if (opts.active || order.length) select(opts.active || order[0], false);
    return api;
  }

  /** A group of toggle buttons for filters. opts: {label, items: [{id, label}], active, onChange(id)}. */
  function segmented(opts) {
    var d = dom();
    var active = opts.active;
    var wrap = d.h("div.seg", { role: "group", "aria-label": opts.label || "" });
    var btns = {};
    opts.items.forEach(function (it) {
      var b = d.h("button.seg-btn", {
        type: "button", "aria-pressed": it.id === active ? "true" : "false",
        onclick: function () { set(it.id); if (opts.onChange) opts.onChange(it.id); }
      }, it.icon ? icons().icon(it.icon, { size: 15 }) : null, d.h("span", null, it.label));
      btns[it.id] = b;
      wrap.appendChild(b);
    });
    function set(id) {
      active = id;
      Object.keys(btns).forEach(function (k) { btns[k].setAttribute("aria-pressed", k === id ? "true" : "false"); });
    }
    return { el: wrap, set: set, value: function () { return active; } };
  }

  /** A labelled on/off switch built on a checkbox. */
  function switchControl(opts) {
    var d = dom();
    var id = opts.id || d.uid("sw");
    var input = d.h("input", { type: "checkbox", role: "switch", id: id, checked: !!opts.checked,
      onchange: function () { if (opts.onChange) opts.onChange(input.checked); } });
    var el = d.h("label.switch", { for: id }, input, d.h("span.switch-ui", { "aria-hidden": "true" }), d.h("span.switch-text", null, opts.label));
    return { el: el, input: input };
  }

  /** Range input with a visible value. opts: {label, min, max, step, value, format(v), onInput(v), describedBy}. */
  function slider(opts) {
    var d = dom();
    var id = opts.id || d.uid("rng");
    var fmtv = opts.format || function (v) { return String(v); };
    var out = d.h("output.slider-value", { for: id }, fmtv(opts.value));
    var input = d.h("input", { type: "range", id: id, min: opts.min, max: opts.max, step: opts.step || 1, value: opts.value,
      "aria-describedby": opts.describedBy || null });
    function paint() {
      var p = (Number(input.value) - Number(opts.min)) / (Number(opts.max) - Number(opts.min));
      input.style.setProperty("--p", String(d.clamp(p, 0, 1) * 100) + "%");
    }
    input.addEventListener("input", function () {
      out.textContent = fmtv(Number(input.value));
      paint();
      if (opts.onInput) opts.onInput(Number(input.value));
    });
    paint();
    var el = d.h("div.slider", d.h("label.slider-label", { for: id }, d.h("span", null, opts.label), out), input);
    return {
      el: el, input: input, value: function () { return Number(input.value); },
      set: function (v) { input.value = v; out.textContent = fmtv(Number(v)); paint(); },
      disable: function (on) { input.disabled = !!on; el.classList.toggle("is-disabled", !!on); }
    };
  }

  /** A labelled form field. input is any element. */
  function field(label, input, hint) {
    var d = dom();
    var id = input.id || d.uid("f");
    if (!input.id) input.id = id;
    return d.h("div.field", d.h("label.field-label", { for: id }, label), input, hint ? d.h("p.field-hint", null, hint) : null);
  }

  // -- dialogs ----------------------------------------------------------------------------------
  /**
   * Modal dialog on the native <dialog> element (focus trap, Escape and inert background for free).
   * opts: {title, body (node), actions (nodes), wide, onClose}. Returns {el, close()}.
   */
  function dialog(opts) {
    var d = dom();
    var titleId = d.uid("dlg-title");
    var closeBtn = d.h("button.btn.btn-ghost.btn-icon", { type: "button", "aria-label": d.t("common.close"), onclick: function () { api.close(); } }, icons().icon("x", { size: 20 }));
    var dlg = d.h("dialog.dialog" + (opts.wide ? ".wide" : ""), { "aria-labelledby": titleId },
      d.h("div.dialog-head", d.h("h2.dialog-title", { id: titleId }, opts.title), closeBtn),
      d.h("div.dialog-body", null, opts.body),
      opts.actions && opts.actions.length ? d.h("div.dialog-actions", null, opts.actions) : null);
    var closed = false;
    var api = {
      el: dlg,
      close: function () {
        if (closed) return;
        closed = true;
        try { if (dlg.open) dlg.close(); } catch (e) { /* already closed */ }
        if (dlg.parentNode) dlg.parentNode.removeChild(dlg);
        if (opts.onClose) opts.onClose();
      }
    };
    dlg.addEventListener("cancel", function (e) { e.preventDefault(); api.close(); });
    dlg.addEventListener("click", function (e) { if (e.target === dlg) api.close(); });
    document.body.appendChild(dlg);
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
    return api;
  }

  // -- toasts -----------------------------------------------------------------------------------
  /** Short, non-blocking message. opts: {title, text, tone, icon, ms}. Never traps focus or demands action. */
  function toast(opts) {
    var d = dom();
    var host = document.getElementById("dk-toasts");
    if (!host) return null;
    var timer = null;
    var el = d.h("div.toast" + (opts.tone ? ".tone-" + opts.tone : ""), { role: "status" },
      opts.icon ? d.h("span.toast-icon", null, icons().icon(opts.icon, { size: 22 })) : null,
      d.h("div.toast-body", null, d.h("strong.toast-title", null, opts.title), opts.text ? d.h("span.toast-text", null, opts.text) : null),
      d.h("button.toast-close", { type: "button", "aria-label": d.t("common.close"), onclick: function () { remove(); } }, icons().icon("x", { size: 16 })));
    function remove() {
      if (timer) clearTimeout(timer);
      if (!el.parentNode) return;
      el.classList.add("is-leaving");
      setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, d.reducedMotion() ? 0 : 220);
    }
    function arm() { timer = setTimeout(remove, opts.ms || 4800); }
    el.addEventListener("pointerenter", function () { if (timer) clearTimeout(timer); });
    el.addEventListener("pointerleave", arm);
    el.addEventListener("focusin", function () { if (timer) clearTimeout(timer); });
    el.addEventListener("focusout", arm);
    host.appendChild(el);
    while (host.children.length > 4) host.removeChild(host.firstChild);
    arm();
    return { el: el, remove: remove };
  }

  /** Spinner dot for pending requests. */
  function spinner() { return dom().h("span.spinner", { role: "presentation", "aria-hidden": "true" }); }

  /** A button that copies text and briefly says so. */
  function copyButton(getText, label) {
    var d = dom();
    var textEl = d.h("span", null, label || d.t("common.copy"));
    var btn = d.h("button.btn.btn-ghost.btn-sm", { type: "button" }, icons().icon("copy", { size: 15 }), textEl);
    btn.addEventListener("click", function () {
      d.copyText(typeof getText === "function" ? getText() : getText).then(function (ok) {
        textEl.textContent = ok ? d.t("common.copied") : d.t("common.copyFailed");
        d.announce(textEl.textContent);
        setTimeout(function () { textEl.textContent = label || d.t("common.copy"); }, 1600);
      });
    });
    return btn;
  }

  return {
    chip: chip, heading: heading, emptyState: emptyState, tabs: tabs, segmented: segmented, switchControl: switchControl,
    slider: slider, field: field, dialog: dialog, toast: toast, spinner: spinner, copyButton: copyButton
  };
});
