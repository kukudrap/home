"use strict";
// A tiny DOM and a loader that runs the game's browser code (the same files the build concatenates) inside a vm
// context, so views can be rendered and inspected from `node --test` without a browser. It implements only what the
// views use: elements, text, attributes, classes, events, value, and a small querySelector (tag, #id, .class,
// [attr], [attr=value], descendant and child combinators). The Playwright smoke test covers real layout and style.
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const SRC = path.resolve(__dirname, "..", "src");

class FNode {
  constructor() { this.childNodes = []; this.parentNode = null; }
  get firstChild() { return this.childNodes[0] || null; }
  get lastChild() { return this.childNodes[this.childNodes.length - 1] || null; }
  appendChild(n) {
    if (n.parentNode) n.parentNode.removeChild(n);
    n.parentNode = this;
    this.childNodes.push(n);
    return n;
  }
  removeChild(n) {
    const i = this.childNodes.indexOf(n);
    if (i < 0) throw new Error("removeChild: not a child");
    this.childNodes.splice(i, 1);
    n.parentNode = null;
    return n;
  }
  insertBefore(n, ref) {
    if (!ref) return this.appendChild(n);
    if (n.parentNode) n.parentNode.removeChild(n);
    const i = this.childNodes.indexOf(ref);
    n.parentNode = this;
    this.childNodes.splice(i, 0, n);
    return n;
  }
  replaceChild(n, old) { this.insertBefore(n, old); this.removeChild(old); return old; }
  contains(n) { for (let x = n; x; x = x.parentNode) if (x === this) return true; return false; }
  get textContent() { return this.childNodes.map((c) => c.textContent).join(""); }
  set textContent(v) {
    this.childNodes.forEach((c) => { c.parentNode = null; });
    this.childNodes = [];
    if (v !== "" && v !== null && v !== undefined) this.appendChild(new FText(String(v)));
  }
}

class FText extends FNode {
  constructor(data) { super(); this.data = data; this.nodeType = 3; }
  get textContent() { return this.data; }
  set textContent(v) { this.data = String(v); }
}

function parseCompound(src) {
  const out = { tag: null, id: null, classes: [], attrs: [] };
  const re = /^([a-zA-Z][\w-]*|\*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:=("?)([^\]"]*)\5)?\]/y;
  let m;
  re.lastIndex = 0;
  while (re.lastIndex < src.length && (m = re.exec(src))) {
    if (m[1]) out.tag = m[1].toLowerCase();
    else if (m[2]) out.id = m[2];
    else if (m[3]) out.classes.push(m[3]);
    else if (m[4]) out.attrs.push([m[4], m[6] === undefined ? null : m[6]]);
  }
  if (re.lastIndex !== src.length) throw new Error("unsupported selector: " + src);
  return out;
}

function parseSelector(sel) {
  return sel.split(",").map((part) => {
    const tokens = part.trim().replace(/\s*>\s*/g, " > ").split(/\s+/);
    const chain = [];
    let rel = " ";
    for (const tok of tokens) {
      if (tok === ">") { rel = ">"; continue; }
      chain.push({ rel, compound: parseCompound(tok) });
      rel = " ";
    }
    return chain;
  });
}

function matchesCompound(el, c) {
  if (!(el instanceof FElement)) return false;
  if (c.tag && c.tag !== "*" && el.localName !== c.tag) return false;
  if (c.id && el.id !== c.id) return false;
  for (const k of c.classes) if (!el.classList.contains(k)) return false;
  for (const [name, val] of c.attrs) {
    const v = el.getAttribute(name);
    if (v === null || (val !== null && v !== val)) return false;
  }
  return true;
}

function matchesChain(el, chain, i) {
  const link = chain[i];
  if (!matchesCompound(el, link.compound)) return false;
  if (i === 0) return true;
  if (link.rel === ">") return el.parentNode instanceof FElement && matchesChain(el.parentNode, chain, i - 1);
  for (let p = el.parentNode; p instanceof FElement; p = p.parentNode) if (matchesChain(p, chain, i - 1)) return true;
  return false;
}

class FElement extends FNode {
  constructor(tag, ns) {
    super();
    this.nodeType = 1;
    this.localName = ns ? tag : tag.toLowerCase();
    this.tagName = ns ? tag : tag.toUpperCase();
    this.namespaceURI = ns || "http://www.w3.org/1999/xhtml";
    this.attrs = new Map();
    this.listeners = {};
    this._value = "";
    const el = this;
    this.style = {
      setProperty(k, v) { this[k] = String(v); },
      get cssText() { return ""; },
      set cssText(v) { this._css = v; }
    };
    this.classList = {
      add: (...cs) => { const s = new Set(el.className.split(/\s+/).filter(Boolean)); cs.forEach((c) => s.add(c)); el.className = [...s].join(" "); },
      remove: (...cs) => { const s = new Set(el.className.split(/\s+/).filter(Boolean)); cs.forEach((c) => s.delete(c)); el.className = [...s].join(" "); },
      contains: (c) => el.className.split(/\s+/).includes(c),
      toggle: (c, force) => { const on = force === undefined ? !el.classList.contains(c) : !!force; el.classList[on ? "add" : "remove"](c); return on; }
    };
  }
  get className() { return this.attrs.get("class") || ""; }
  set className(v) { this.attrs.set("class", String(v)); }
  get id() { return this.attrs.get("id") || ""; }
  set id(v) { this.attrs.set("id", String(v)); }
  setAttribute(k, v) { this.attrs.set(k, String(v)); }
  getAttribute(k) { return this.attrs.has(k) ? this.attrs.get(k) : null; }
  removeAttribute(k) { this.attrs.delete(k); }
  hasAttribute(k) { return this.attrs.has(k); }
  get children() { return this.childNodes.filter((c) => c instanceof FElement); }
  get hidden() { return this.attrs.has("hidden"); }
  set hidden(v) { if (v) this.attrs.set("hidden", ""); else this.attrs.delete("hidden"); }
  get disabled() { return this.attrs.has("disabled"); }
  set disabled(v) { if (v) this.attrs.set("disabled", ""); else this.attrs.delete("disabled"); }
  get open() { return this.attrs.has("open"); }
  set open(v) { if (v) this.attrs.set("open", ""); else this.attrs.delete("open"); }
  // option and button values reflect the attribute; the value of an input, textarea or select is a property of its own
  get value() { return ["textarea", "input", "select"].includes(this.localName) ? this._value : (this.attrs.get("value") || ""); }
  set value(v) { if (["textarea", "input", "select"].includes(this.localName)) this._value = String(v); else this.attrs.set("value", String(v)); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter((f) => f !== fn); }
  dispatchEvent(ev) {
    ev.target = ev.target || this;
    (this.listeners[ev.type] || []).slice().forEach((fn) => fn.call(this, ev));
    return true;
  }
  click() { this.dispatchEvent({ type: "click", target: this, preventDefault() {}, stopPropagation() {} }); }
  focus() { if (this.ownerDocument) this.ownerDocument.activeElement = this; }
  scrollIntoView() {}
  scrollTo() {}
  select() {}
  getBoundingClientRect() { return { x: 0, y: 0, width: 0, height: 0, top: 0, left: 0, right: 0, bottom: 0 }; }
  get scrollWidth() { return 0; }
  get clientWidth() { return 0; }
  get offsetLeft() { return 0; }
  get offsetWidth() { return 0; }
  get scrollHeight() { return 0; }
  get dataset() { return {}; }
  matches(sel) { return parseSelector(sel).some((chain) => matchesChain(this, chain, chain.length - 1)); }
  closest(sel) { for (let e = this; e instanceof FElement; e = e.parentNode) if (e.matches(sel)) return e; return null; }
  querySelectorAll(sel) {
    const chains = parseSelector(sel);
    const out = [];
    const walk = (n) => {
      n.childNodes.forEach((c) => {
        if (c instanceof FElement) {
          if (chains.some((chain) => matchesChain(c, chain, chain.length - 1))) out.push(c);
          walk(c);
        }
      });
    };
    walk(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
}

function createDocument() {
  const doc = {
    activeElement: null,
    createElement(tag) { const e = new FElement(tag); e.ownerDocument = doc; return e; },
    createElementNS(ns, tag) { const e = new FElement(tag, ns); e.ownerDocument = doc; return e; },
    createTextNode(text) { return new FText(String(text)); },
    getElementById(id) { return doc.body.querySelector("#" + id); },
    querySelector(sel) { return doc.body.querySelector(sel); },
    querySelectorAll(sel) { return doc.body.querySelectorAll(sel); },
    addEventListener() {}, removeEventListener() {},
    visibilityState: "visible"
  };
  doc.documentElement = doc.createElement("html");
  doc.body = doc.createElement("body");
  doc.documentElement.appendChild(doc.body);
  return doc;
}

// the files in the same order the build uses; the sandbox loads only the logic and views a test asks for
const LOGIC = ["scoring.js", "labstats.js", "claims.js", "game.js", "i18n.js", "store.js"];
const UI = ["ui/dom.js", "ui/icons.js", "ui/charts.js", "ui/widgets.js", "ui/claimsui.js"];

/** A fresh sandbox with the game code loaded. `views` lists extra UI files such as "ui/boss.js". */
function loadUi(views = []) {
  const document = createDocument();
  const sandbox = {
    document, console, setTimeout, clearTimeout, setInterval, clearInterval, Intl, URL, Blob,
    navigator: { language: "en" },
    history: { replaceState() {} },
    location: { hash: "", protocol: "file:" },
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    localStorage: undefined
  };
  sandbox.self = sandbox;
  vm.createContext(sandbox);
  for (const rel of [...LOGIC, ...UI, ...views]) {
    vm.runInContext(fs.readFileSync(path.join(SRC, rel), "utf8"), sandbox, { filename: rel });
  }
  return { DK: sandbox.DK, document, sandbox };
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

module.exports = { loadUi, createDocument, FElement, FText, sleep };
