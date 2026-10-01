/* Lab statistics for the game: frequentist and Bayesian A/B tests, sample sizes, a seeded RNG,
 * bandit simulation and the peeking demo. Mirrors src/dopamine_king/lab (ab.py, bandit.py); reference
 * values from the Python implementation are checked in web/tests/labstats.test.js.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else { root.DK = root.DK || {}; root.DK.labstats = factory(); }
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  var SQRT2 = Math.SQRT2;

  // -- normal distribution ------------------------------------------------------------------
  // erfc by Chebyshev fitting (Numerical Recipes, 3rd ed., erfccheb): relative error about 1e-16.
  var ERFC_COF = [
    -1.3026537197817094, 6.4196979235649026e-1, 1.9476473204185836e-2, -9.561514786808631e-3,
    -9.46595344482036e-4, 3.66839497852761e-4, 4.2523324806907e-5, -2.0278578112534e-5,
    -1.624290004647e-6, 1.303655835580e-6, 1.5626441722e-8, -8.5238095915e-8, 6.529054439e-9,
    5.059343495e-9, -9.91364156e-10, -2.27365122e-10, 9.6467911e-11, 2.394038e-12, -6.886027e-12,
    8.94487e-13, 3.13092e-13, -1.12708e-13, 3.81e-16, 7.106e-15, -1.523e-15, -9.4e-17, 1.21e-16,
    -2.8e-17
  ];

  function erfccheb(z) {
    var t = 2 / (2 + z);
    var ty = 4 * t - 2;
    var d = 0, dd = 0, tmp;
    for (var j = ERFC_COF.length - 1; j > 0; j--) {
      tmp = d;
      d = ty * d - dd + ERFC_COF[j];
      dd = tmp;
    }
    return t * Math.exp(-z * z + 0.5 * (ERFC_COF[0] + ty * d) - dd);
  }

  function erfc(x) { return x >= 0 ? erfccheb(x) : 2 - erfccheb(-x); }

  function normCdf(x) { return 0.5 * erfc(-x / SQRT2); }

  /** Inverse of normCdf. Starts from Abramowitz-Stegun 26.2.23, then refines with Halley steps. */
  function normInv(p) {
    if (p === 0) return -Infinity;
    if (p === 1) return Infinity;
    if (!(p > 0 && p < 1)) return NaN;
    if (p > 0.5) return -normInv(1 - p);
    var t = Math.sqrt(-2 * Math.log(p));
    var x = -(t - (2.515517 + 0.802853 * t + 0.010328 * t * t) /
      (1 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t * t * t));
    for (var i = 0; i < 5; i++) {
      var e = normCdf(x) - p;
      var u = e * Math.sqrt(2 * Math.PI) * Math.exp(x * x / 2);
      var step = u / (1 + x * u / 2);
      x -= step;
      if (Math.abs(step) < 1e-15 * Math.max(1, Math.abs(x))) break;
    }
    return x;
  }

  // -- frequentist tests --------------------------------------------------------------------
  function wilsonInterval(k, n, level) {
    if (level === undefined) level = 0.95;
    if (n <= 0) return [0.0, 1.0];
    var z = normInv(1 - (1 - level) / 2);
    var p = k / n;
    var denom = 1 + z * z / n;
    var centre = (p + z * z / (2 * n)) / denom;
    var half = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom;
    return [Math.max(0.0, centre - half), Math.min(1.0, centre + half)];
  }

  /** Pooled two-proportion z test with a Newcombe hybrid score interval for the difference B - A. */
  function twoProportionTest(convA, nA, convB, nB, alpha) {
    if (alpha === undefined) alpha = 0.05;
    if (!(nA > 0) || !(nB > 0)) throw new RangeError("both arms need at least one visitor");
    var pa = convA / nA, pb = convB / nB;
    var pooled = (convA + convB) / (nA + nB);
    var se = Math.sqrt(pooled * (1 - pooled) * (1 / nA + 1 / nB));
    var z = se ? (pb - pa) / se : 0.0;
    var pValue = 2 * normCdf(-Math.abs(z));
    var wa = wilsonInterval(convA, nA, 1 - alpha), wb = wilsonInterval(convB, nB, 1 - alpha);
    var la = wa[0], ua = wa[1], lb = wb[0], ub = wb[1];
    var lo = (pb - pa) - Math.sqrt(Math.pow(pb - lb, 2) + Math.pow(ua - pa, 2));
    var hi = (pb - pa) + Math.sqrt(Math.pow(ub - pb, 2) + Math.pow(pa - la, 2));
    return {
      nA: nA, nB: nB, rateA: pa, rateB: pb, diff: pb - pa, relUplift: pa ? (pb - pa) / pa : null,
      z: z, pValue: pValue, ciDiff: [lo, hi], wilsonA: wa, wilsonB: wb, alpha: alpha, significant: pValue < alpha
    };
  }

  /** Visitors needed per arm to detect a relative lift of mdeRel over baseline (two sided). */
  function sampleSizePerArm(baseline, mdeRel, alpha, power) {
    if (alpha === undefined) alpha = 0.05;
    if (power === undefined) power = 0.8;
    var p1 = baseline;
    var p2 = baseline * (1 + mdeRel);
    if (!(p1 > 0 && p1 < 1 && p2 > 0 && p2 < 1)) throw new RangeError("baseline and lifted rate must be inside (0, 1)");
    var pbar = (p1 + p2) / 2;
    var za = normInv(1 - alpha / 2), zb = normInv(power);
    var num = Math.pow(za * Math.sqrt(2 * pbar * (1 - pbar)) + zb * Math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)), 2);
    return Math.ceil(num / Math.pow(p2 - p1, 2));
  }

  /** Step-down correction for several variants against one control. Returns reject flags. */
  function holmBonferroni(pValues, alpha) {
    if (alpha === undefined) alpha = 0.05;
    var order = pValues.map(function (_, i) { return i; }).sort(function (a, b) { return pValues[a] - pValues[b]; });
    var reject = pValues.map(function () { return false; });
    var m = pValues.length;
    for (var rank = 0; rank < order.length; rank++) {
      var i = order[rank];
      if (pValues[i] <= alpha / (m - rank)) reject[i] = true; else break;
    }
    return reject;
  }

  /** Display helper: "p < 0.001", "p = 0.036". */
  function formatP(p) {
    if (!(p >= 0)) return "p = ?";
    if (p < 0.001) return "p < 0.001";
    return "p = " + p.toFixed(p < 0.1 ? 3 : 2);
  }

  // -- seeded randomness ---------------------------------------------------------------------
  function mulberry32(seed) {
    var a = seed >>> 0;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  /** 32 bit seed from a string (xmur3), so dates and scenario ids give stable random streams. */
  function hashSeed(str) {
    str = String(str);
    var h = 1779033703 ^ str.length;
    for (var i = 0; i < str.length; i++) {
      h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
      h = (h << 13) | (h >>> 19);
    }
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    return (h ^ (h >>> 16)) >>> 0;
  }

  function normalSample(rng) {
    return Math.sqrt(-2 * Math.log(1 - rng())) * Math.cos(2 * Math.PI * rng());
  }

  /** Marsaglia and Tsang (2000) gamma sampler, scale 1. */
  function gammaSample(rng, shape) {
    if (shape < 1) {
      var boost = rng();
      return gammaSample(rng, shape + 1) * Math.pow(boost, 1 / shape);
    }
    var d = shape - 1 / 3;
    var c = 1 / Math.sqrt(9 * d);
    for (;;) {
      var x, v;
      do { x = normalSample(rng); v = 1 + c * x; } while (v <= 0);
      v = v * v * v;
      var u = rng();
      if (u < 1 - 0.0331 * x * x * x * x) return d * v;
      if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
    }
  }

  function betaSample(rng, a, b) {
    var x = gammaSample(rng, a);
    var y = gammaSample(rng, b);
    return x / (x + y);
  }

  /** Number of successes in n Bernoulli trials (exact up to 100000 trials, normal approximation above). */
  function binomialSample(rng, n, p) {
    if (p <= 0 || n <= 0) return 0;
    if (p >= 1) return n;
    if (n > 100000) {
      var sd = Math.sqrt(n * p * (1 - p));
      return Math.min(n, Math.max(0, Math.round(n * p + sd * normalSample(rng))));
    }
    var k = 0;
    for (var i = 0; i < n; i++) if (rng() < p) k += 1;
    return k;
  }

  /** One simulated A/B test with true conversion rates rateA and rateB. */
  function simulateAB(rateA, rateB, nPerArm, seed) {
    var rng = mulberry32(seed);
    return { nA: nPerArm, nB: nPerArm, convA: binomialSample(rng, nPerArm, rateA), convB: binomialSample(rng, nPerArm, rateB) };
  }

  // -- Bayesian comparison -------------------------------------------------------------------
  function bayesAB(convA, nA, convB, nB, opts) {
    opts = opts || {};
    var prior = opts.prior || [1.0, 1.0];
    var draws = opts.draws || 20000;
    var rng = mulberry32(opts.seed === undefined ? 0 : opts.seed);
    var a1 = prior[0] + convA, b1 = prior[1] + nA - convA;
    var a2 = prior[0] + convB, b2 = prior[1] + nB - convB;
    var sa = new Float64Array(draws), sb = new Float64Array(draws);
    var i;
    for (i = 0; i < draws; i++) sa[i] = betaSample(rng, a1, b1);
    for (i = 0; i < draws; i++) sb[i] = betaSample(rng, a2, b2);
    var wins = 0, uplift = 0, lossA = 0, lossB = 0;
    for (i = 0; i < draws; i++) {
      var x = sa[i], y = sb[i];
      if (y > x) wins += 1;
      if (x > 0) uplift += (y - x) / x;
      lossA += Math.max(y - x, 0.0);
      lossB += Math.max(x - y, 0.0);
    }
    var ssa = Float64Array.from(sa).sort(), ssb = Float64Array.from(sb).sort();
    var lo = Math.floor(0.025 * draws), hi = Math.floor(0.975 * draws) - 1;
    return {
      pBBetter: wins / draws, expectedUplift: uplift / draws,
      expectedLossChooseA: lossA / draws, expectedLossChooseB: lossB / draws,
      credibleA: [ssa[lo], ssa[hi]], credibleB: [ssb[lo], ssb[hi]], draws: draws
    };
  }

  // -- bandits -------------------------------------------------------------------------------
  /**
   * A steppable bandit simulation (so the UI can animate it). policy: "thompson" or "uniform".
   * Uniform is an even split (round robin), the way a classic fixed A/B/C/D test allocates traffic.
   */
  function createBandit(trueRates, policy, seed) {
    var rng = mulberry32(seed === undefined ? 0 : seed);
    var n = trueRates.length;
    var best = Math.max.apply(null, trueRates);
    var bandit = {
      policy: policy, rates: trueRates.slice(), n: n, best: best, bestArm: trueRates.indexOf(best),
      pulls: new Array(n).fill(0), wins: new Array(n).fill(0), t: 0, regret: 0, conversions: 0,
      select: function () {
        if (policy === "thompson") {
          var bestArm = 0, bestDraw = -1;
          for (var i = 0; i < n; i++) {
            var d = betaSample(rng, 1 + bandit.wins[i], 1 + bandit.pulls[i] - bandit.wins[i]);
            if (d > bestDraw) { bestDraw = d; bestArm = i; }
          }
          return bestArm;
        }
        return bandit.t % n;
      },
      step: function () {
        var arm = bandit.select();
        var reward = rng() < trueRates[arm] ? 1 : 0;
        bandit.pulls[arm] += 1;
        bandit.wins[arm] += reward;
        bandit.t += 1;
        bandit.conversions += reward;
        bandit.regret += best - trueRates[arm];
        return { arm: arm, reward: reward };
      }
    };
    return bandit;
  }

  function simulateBandit(trueRates, rounds, policy, seed, curvePoints) {
    if (curvePoints === undefined) curvePoints = 50;
    var b = createBandit(trueRates, policy || "thompson", seed);
    var step = Math.max(1, Math.floor(rounds / curvePoints));
    var curve = [];
    for (var t = 1; t <= rounds; t++) {
      b.step();
      if (t % step === 0 || t === rounds) curve.push([t, b.regret]);
    }
    return {
      policy: b.policy, rounds: rounds, pulls: b.pulls.slice(), wins: b.wins.slice(), conversions: b.conversions,
      regret: b.regret, bestArmShare: b.pulls[b.bestArm] / rounds, regretCurve: curve
    };
  }

  // -- the peeking demo ----------------------------------------------------------------------
  // Light weight pooled z test p value (same maths as twoProportionTest, without the intervals).
  function pooledP(ca, na, cb, nb) {
    var pooled = (ca + cb) / (na + nb);
    var se = Math.sqrt(pooled * (1 - pooled) * (1 / na + 1 / nb));
    if (!se) return 1;
    return 2 * normCdf(-Math.abs((cb / nb - ca / na) / se));
  }

  /**
   * Simulate `trials` A/A tests (no real difference). Analyse each at every look (peeking: stop at the
   * first p below alpha) and only once at the end (fixed horizon).
   * Returns {trials, looks, nPerLook, peeking, fixed, byLook} where byLook[k] is the share of tests that
   * had already crossed p < alpha after k + 1 looks.
   */
  function peekingExperiment(o) {
    o = o || {};
    var looks = o.looks || 10, nPerLook = o.nPerLook || 200, baseRate = o.baseRate === undefined ? 0.05 : o.baseRate;
    var alpha = o.alpha === undefined ? 0.05 : o.alpha, trials = o.trials || 1000;
    var rng = mulberry32(o.seed === undefined ? 0 : o.seed);
    var crossedBy = new Array(looks).fill(0);
    var peekHits = 0, fixedHits = 0;
    for (var tr = 0; tr < trials; tr++) {
      var ca = 0, cb = 0, na = 0, nb = 0, hit = false, lastSig = false;
      for (var k = 0; k < looks; k++) {
        ca += binomialSample(rng, nPerLook, baseRate);
        cb += binomialSample(rng, nPerLook, baseRate);
        na += nPerLook; nb += nPerLook;
        var sig = false;
        if (ca + cb > 0) sig = pooledP(ca, na, cb, nb) < alpha;
        if (sig && !hit) { hit = true; }
        if (hit) crossedBy[k] += 1;
        lastSig = sig;
      }
      if (hit) peekHits += 1;
      if (lastSig) fixedHits += 1;
    }
    return {
      trials: trials, looks: looks, nPerLook: nPerLook, baseRate: baseRate, alpha: alpha,
      peeking: peekHits / trials, fixed: fixedHits / trials,
      byLook: crossedBy.map(function (c) { return c / trials; })
    };
  }

  /** Share of A/A tests declared significant when checked at every look (Python peeking_false_positive_rate). */
  function peekingFalsePositiveRate(looks, nPerLook, trials, opts) {
    opts = opts || {};
    return peekingExperiment({
      looks: looks, nPerLook: nPerLook === undefined ? 200 : nPerLook, trials: trials === undefined ? 1000 : trials,
      baseRate: opts.baseRate, alpha: opts.alpha, seed: opts.seed
    }).peeking;
  }

  return {
    erfc: erfc, normCdf: normCdf, normInv: normInv,
    wilsonInterval: wilsonInterval, twoProportionTest: twoProportionTest, sampleSizePerArm: sampleSizePerArm,
    holmBonferroni: holmBonferroni, formatP: formatP,
    mulberry32: mulberry32, hashSeed: hashSeed, normalSample: normalSample, gammaSample: gammaSample,
    betaSample: betaSample, binomialSample: binomialSample, simulateAB: simulateAB,
    bayesAB: bayesAB, createBandit: createBandit, simulateBandit: simulateBandit,
    peekingExperiment: peekingExperiment, peekingFalsePositiveRate: peekingFalsePositiveRate
  };
});
