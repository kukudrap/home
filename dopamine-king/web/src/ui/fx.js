/* Celebration effects: canvas confetti and a tiny WebAudio synth. Both respect the user: confetti is
 * skipped for reduced motion and sound is OFF unless the player switches it on.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else { root.DK = root.DK || {}; root.DK.ui = root.DK.ui || {}; root.DK.ui.fx = factory(root); }
})(typeof self !== "undefined" ? self : this, function (root) {
  "use strict";

  function dom() { return root.DK.ui.dom; }

  // -- confetti ---------------------------------------------------------------------------------
  var COLORS = ["#8b6cff", "#ff4fa3", "#38d4f0", "#a3e635", "#fbbf24", "#ffffff"];
  var running = null;

  /** Burst of confetti from (x, y) as fractions of the viewport. Does nothing for reduced motion. */
  function confetti(opts) {
    opts = opts || {};
    var d = dom();
    if (d.reducedMotion()) return false;
    var canvas = document.getElementById("dk-confetti");
    if (!canvas || !canvas.getContext) return false;
    var ctx = canvas.getContext("2d");
    var dpr = Math.min(root.devicePixelRatio || 1, 2);
    var W = root.innerWidth, H = root.innerHeight;
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    canvas.style.width = W + "px";
    canvas.style.height = H + "px";
    canvas.classList.add("is-on");
    // A modal dialog lives in the top layer, above any z-index. Promote the canvas to the top layer too (popover),
    // so a burst over an open chest dialog is visible. Engines without popovers just use the z-index.
    try {
      if (typeof canvas.showPopover === "function") {
        if (!canvas.hasAttribute("popover")) canvas.setAttribute("popover", "manual");
        if (!canvas.matches(":popover-open")) canvas.showPopover();
      }
    } catch (e) { /* fall back to z-index */ }
    if (running) cancelAnimationFrame(running.id);

    var ox = (opts.x === undefined ? 0.5 : opts.x) * W, oy = (opts.y === undefined ? 0.35 : opts.y) * H;
    var n = opts.count || 150;
    var parts = [];
    for (var i = 0; i < n; i++) {
      var a = Math.random() * Math.PI * 2, sp = 220 + Math.random() * 520;
      parts.push({
        x: ox, y: oy, vx: Math.cos(a) * sp * (0.6 + Math.random() * 0.6), vy: Math.sin(a) * sp - 260,
        w: 6 + Math.random() * 7, h: 4 + Math.random() * 5, rot: Math.random() * 6.28, vr: (Math.random() - 0.5) * 12,
        color: COLORS[i % COLORS.length], round: Math.random() < 0.25
      });
    }
    var start = null, last = null, total = opts.ms || 2600;
    var state = { id: 0 };
    running = state;
    function frame(ts) {
      if (start === null) { start = ts; last = ts; }
      var dt = Math.min(0.04, (ts - last) / 1000);
      last = ts;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      var alive = 0, age = ts - start;
      parts.forEach(function (p) {
        p.vy += 980 * dt;
        p.vx *= 1 - 0.9 * dt;
        p.vy *= 1 - 0.35 * dt;
        p.x += p.vx * dt; p.y += p.vy * dt; p.rot += p.vr * dt;
        if (p.y < H + 30) alive += 1; else return;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rot);
        ctx.globalAlpha = Math.max(0, Math.min(1, (total - age) / 700));
        ctx.fillStyle = p.color;
        if (p.round) { ctx.beginPath(); ctx.arc(0, 0, p.h / 1.4, 0, 6.283); ctx.fill(); }
        else ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        ctx.restore();
      });
      if (alive && age < total) state.id = requestAnimationFrame(frame);
      else {
        ctx.clearRect(0, 0, W, H);
        canvas.classList.remove("is-on");
        try { if (canvas.matches(":popover-open")) canvas.hidePopover(); } catch (e) { /* not a popover here */ }
        running = null;
      }
    }
    state.id = requestAnimationFrame(frame);
    return true;
  }

  // -- sound ------------------------------------------------------------------------------------
  var audio = { ctx: null, on: false };
  // [frequency Hz, start s, duration s, waveform]
  var TUNES = {
    correct: [[659, 0, 0.1, "triangle"], [880, 0.09, 0.16, "triangle"]],
    wrong: [[246, 0, 0.16, "sine"], [220, 0.12, 0.2, "sine"]],
    tick: [[740, 0, 0.05, "triangle"]],
    level: [[523, 0, 0.1, "triangle"], [659, 0.1, 0.1, "triangle"], [784, 0.2, 0.1, "triangle"], [1047, 0.3, 0.3, "triangle"]],
    win: [[392, 0, 0.12, "square"], [523, 0.12, 0.12, "square"], [659, 0.24, 0.12, "square"], [784, 0.36, 0.34, "square"]],
    chest: [[330, 0, 0.1, "sine"], [494, 0.1, 0.1, "sine"], [659, 0.2, 0.1, "sine"], [988, 0.3, 0.4, "triangle"]],
    legendary: [[523, 0, 0.1, "triangle"], [659, 0.08, 0.1, "triangle"], [784, 0.16, 0.1, "triangle"], [1047, 0.24, 0.1, "triangle"], [1319, 0.32, 0.5, "triangle"]],
    pop: [[520, 0, 0.06, "sine"]]
  };

  function setSound(on) { audio.on = !!on; }
  function soundOn() { return audio.on; }

  function play(name) {
    if (!audio.on) return;
    var tune = TUNES[name];
    if (!tune) return;
    try {
      var AC = root.AudioContext || root.webkitAudioContext;
      if (!AC) return;
      if (!audio.ctx) audio.ctx = new AC();
      var ctx = audio.ctx;
      if (ctx.state === "suspended") ctx.resume();
      var t0 = ctx.currentTime + 0.01;
      tune.forEach(function (n) {
        var osc = ctx.createOscillator(), gain = ctx.createGain();
        osc.type = n[3];
        osc.frequency.value = n[0];
        gain.gain.setValueAtTime(0.0001, t0 + n[1]);
        gain.gain.exponentialRampToValueAtTime(0.07, t0 + n[1] + 0.015);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + n[1] + n[2]);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(t0 + n[1]);
        osc.stop(t0 + n[1] + n[2] + 0.05);
      });
    } catch (e) { /* audio is a nicety, never an error */ }
  }

  return { confetti: confetti, setSound: setSound, soundOn: soundOn, play: play, TUNES: TUNES };
});
