"use strict";
// Lab statistics checked against reference values computed with the Python engine
// (src/dopamine_king/lab/ab.py, bandit.py and math.erfc / statistics.NormalDist).
const test = require("node:test");
const assert = require("node:assert/strict");
const L = require("../src/labstats.js");

const near = (actual, expected, tol, msg) =>
  assert.ok(Math.abs(actual - expected) <= tol, `${msg || "value"}: ${actual} vs ${expected} (tol ${tol})`);

test("normal CDF is accurate far beyond 1e-7", () => {
  const ref = [
    [-6, 9.865876450377012e-10], [-4, 3.1671241833119965e-05], [-3, 0.0013498980316300957],
    [-2, 0.02275013194817922], [-1, 0.15865525393145707], [-0.5, 0.3085375387259869], [0, 0.5],
    [0.5, 0.6914624612740131], [1, 0.8413447460685429], [2, 0.9772498680518208],
    [3, 0.9986501019683699], [4, 0.9999683287581669], [5, 0.9999997133484281], [6, 0.9999999990134123]
  ];
  for (const [x, p] of ref) near(L.normCdf(x), p, Math.max(1e-12 * p, 1e-15), `cdf(${x})`);
  near(L.erfc(0), 1, 1e-15);
  near(L.erfc(3), 2.2090496998585438e-05, 1e-18);
  near(L.erfc(-1), 1.842700792949715, 1e-14);
  near(L.normCdf(1.96) + L.normCdf(-1.96), 1, 1e-14);
});

test("normal quantile function inverts the CDF", () => {
  const ref = [
    [1e-10, -6.361340902404056], [1e-6, -4.753424308822899], [0.001, -3.090232306167813],
    [0.01, -2.3263478740408408], [0.025, -1.9599639845400538], [0.05, -1.6448536269514726],
    [0.25, -0.6744897501960817], [0.5, 0], [0.75, 0.6744897501960817], [0.8, 0.8416212335729144],
    [0.9, 1.2815515655446008], [0.975, 1.9599639845400536], [0.999, 3.090232306167813]
  ];
  for (const [p, x] of ref) near(L.normInv(p), x, 1e-11, `inv(${p})`);
  assert.equal(L.normInv(0), -Infinity);
  assert.equal(L.normInv(1), Infinity);
  assert.ok(Number.isNaN(L.normInv(1.5)));
  for (let p = 0.001; p < 1; p += 0.037) near(L.normCdf(L.normInv(p)), p, 1e-13);
});

test("two proportion test matches the reference", () => {
  const t = L.twoProportionTest(100, 1000, 130, 1000);
  near(t.z, 2.102740605622114, 1e-9, "z");
  near(t.z, 2.1027, 1e-4, "z (spec)");
  near(t.pValue, 0.03548845046647475, 1e-9, "p");
  near(t.pValue, 0.0355, 5e-5, "p (spec)");
  near(t.diff, 0.03, 1e-12);
  near(t.relUplift, 0.3, 1e-12);
  near(t.ciDiff[0], 0.0020023487152830075, 1e-9, "newcombe lo");
  near(t.ciDiff[1], 0.05807048502220285, 1e-9, "newcombe hi");
  assert.equal(t.significant, true);
  assert.equal(t.nA, 1000);
});

test("two proportion test edge cases", () => {
  const same = L.twoProportionTest(50, 1000, 50, 1000);
  assert.equal(same.z, 0);
  near(same.pValue, 1, 1e-12);
  near(same.ciDiff[0], -0.019375338999310925, 1e-9);
  assert.equal(same.significant, false);
  const zero = L.twoProportionTest(0, 100, 5, 100);
  assert.equal(zero.relUplift, null);
  near(zero.z, 2.2645540682891916, 1e-9);
  near(zero.pValue, 0.023540058261178, 1e-9);
  const neg = L.twoProportionTest(30, 1000, 10, 1000);
  near(neg.z, -3.1943828249996993, 1e-9);
  near(neg.ciDiff[1], -0.007819328386507708, 1e-9);
  const unequal = L.twoProportionTest(12, 300, 25, 310);
  near(unequal.pValue, 0.035509048236079144, 1e-9);
  assert.throws(() => L.twoProportionTest(1, 0, 1, 10), RangeError);
});

test("Wilson interval", () => {
  const [lo, hi] = L.wilsonInterval(5, 10);
  near(lo, 0.2366, 5e-5);
  near(hi, 0.7634, 5e-5);
  near(lo, 0.23659309051256405, 1e-12);
  assert.deepEqual(L.wilsonInterval(5, 0), [0, 1]);
  const z = L.wilsonInterval(0, 10);
  assert.ok(z[0] >= 0 && z[0] < 1e-12);
  near(z[1], 0.27753279986288915, 1e-12);
  const full = L.wilsonInterval(10, 10);
  assert.equal(full[1], 1);
  near(full[0], 0.7224672001371109, 1e-12);
  const w = L.wilsonInterval(400, 1000);
  near(w[0], 0.37007478121137727, 1e-12);
  near(w[1], 0.4306905704857338, 1e-12);
});

test("sample size per arm", () => {
  assert.ok(Math.abs(L.sampleSizePerArm(0.05, 0.2) - 8158) <= 6);
  assert.equal(L.sampleSizePerArm(0.05, 0.2), 8158);
  assert.equal(L.sampleSizePerArm(0.04, 0.25), 6745);
  assert.equal(L.sampleSizePerArm(0.08, 0.15), 8568);
  assert.equal(L.sampleSizePerArm(0.03, 0.4), 3782);
  assert.equal(L.sampleSizePerArm(0.1, 0.1, 0.01, 0.9), 27964);
  assert.throws(() => L.sampleSizePerArm(0.9, 0.5), RangeError);
});

test("Holm Bonferroni and p formatting", () => {
  assert.deepEqual(L.holmBonferroni([0.01, 0.04, 0.03]), [true, false, false]);
  assert.deepEqual(L.holmBonferroni([0.001, 0.01, 0.02]), [true, true, true]);
  assert.equal(L.formatP(0.0004), "p < 0.001");
  assert.equal(L.formatP(0.03548845), "p = 0.035");
  assert.equal(L.formatP(0.0456), "p = 0.046");
  assert.equal(L.formatP(0.5), "p = 0.50");
});

test("mulberry32 is deterministic and uniform", () => {
  const a = L.mulberry32(42), b = L.mulberry32(42), c = L.mulberry32(43);
  const sa = Array.from({ length: 5 }, a), sb = Array.from({ length: 5 }, b), sc = Array.from({ length: 5 }, c);
  assert.deepEqual(sa, sb);
  assert.notDeepEqual(sa, sc);
  const r = L.mulberry32(7);
  let sum = 0;
  const n = 20000;
  for (let i = 0; i < n; i++) { const x = r(); assert.ok(x >= 0 && x < 1); sum += x; }
  near(sum / n, 0.5, 0.01, "mean of uniforms");
  assert.equal(L.hashSeed("2026-10-01"), L.hashSeed("2026-10-01"));
  assert.notEqual(L.hashSeed("2026-10-01"), L.hashSeed("2026-10-02"));
  assert.ok(Number.isInteger(L.hashSeed("x")) && L.hashSeed("x") >= 0);
});

test("beta sampler has the right mean and variance", () => {
  const rng = L.mulberry32(5);
  for (const [a, b] of [[1, 1], [2, 5], [0.5, 0.5], [101, 901], [30, 3]]) {
    const n = 30000;
    let s = 0, s2 = 0;
    for (let i = 0; i < n; i++) { const x = L.betaSample(rng, a, b); s += x; s2 += x * x; }
    const mean = s / n, variance = s2 / n - mean * mean;
    const em = a / (a + b), ev = (a * b) / ((a + b) * (a + b) * (a + b + 1));
    near(mean, em, 4 * Math.sqrt(ev / n) + 1e-4, `beta(${a},${b}) mean`);
    near(variance, ev, ev * 0.08 + 1e-6, `beta(${a},${b}) variance`);
  }
});

test("binomial sampler", () => {
  const rng = L.mulberry32(9);
  assert.equal(L.binomialSample(rng, 100, 0), 0);
  assert.equal(L.binomialSample(rng, 100, 1), 100);
  assert.equal(L.binomialSample(rng, 0, 0.5), 0);
  let s = 0;
  for (let i = 0; i < 200; i++) s += L.binomialSample(rng, 1000, 0.04);
  near(s / 200, 40, 1.5, "mean successes");
  const big = L.binomialSample(rng, 1000000, 0.1);
  near(big, 100000, 2000, "normal approximation branch");
  const ab = L.simulateAB(0.05, 0.05, 1000, 1);
  assert.equal(ab.nA, 1000);
  assert.deepEqual(L.simulateAB(0.05, 0.06, 500, 3), L.simulateAB(0.05, 0.06, 500, 3));
});

test("Bayesian A/B agrees with the Monte Carlo reference", () => {
  const r = L.bayesAB(100, 1000, 130, 1000, { draws: 40000, seed: 1 });
  near(r.pBBetter, 0.9822, 0.01, "P(B > A)");
  near(r.expectedUplift, 0.3087, 0.03, "uplift");
  near(r.expectedLossChooseA, 0.030039, 0.002, "loss A");
  near(r.expectedLossChooseB, 0.0000922, 0.0005, "loss B");
  near(r.credibleA[0], 0.08293, 0.002);
  near(r.credibleB[1], 0.15236, 0.002);
  const flat = L.bayesAB(50, 1000, 50, 1000, { draws: 40000, seed: 2 });
  near(flat.pBBetter, 0.5, 0.02, "A/A is a coin flip");
  const small = L.bayesAB(5, 100, 9, 100, { draws: 40000, seed: 3 });
  near(small.pBBetter, 0.8581, 0.012, "small sample");
  assert.equal(small.draws, 40000);
  assert.deepEqual(L.bayesAB(5, 100, 9, 100, { draws: 500, seed: 3 }), L.bayesAB(5, 100, 9, 100, { draws: 500, seed: 3 }));
});

test("Thompson sampling regrets less than an even split and stays deterministic", () => {
  const rates = [0.04, 0.05, 0.07, 0.045];
  let u = 0, t = 0;
  const runs = 30;
  for (let s = 0; s < runs; s++) {
    u += L.simulateBandit(rates, 2000, "uniform", s).regret;
    t += L.simulateBandit(rates, 2000, "thompson", s).regret;
  }
  near(u / runs, 37.5, 0.01, "uniform regret is exactly rounds * mean gap");
  assert.ok(t / runs < 0.75 * (u / runs), `thompson ${t / runs} should beat uniform ${u / runs}`);
  near(t / runs, 20.6, 5, "thompson regret near the Python reference");
  const a = L.simulateBandit(rates, 500, "thompson", 11);
  assert.deepEqual(a, L.simulateBandit(rates, 500, "thompson", 11));
  assert.equal(a.pulls.reduce((x, y) => x + y, 0), 500);
  assert.equal(a.regretCurve[a.regretCurve.length - 1][0], 500);
  for (let i = 1; i < a.regretCurve.length; i++) assert.ok(a.regretCurve[i][1] >= a.regretCurve[i - 1][1]);
  const even = L.simulateBandit(rates, 400, "uniform", 1);
  assert.deepEqual(even.pulls, [100, 100, 100, 100]);
  assert.equal(even.bestArmShare, 0.25);
});

test("steppable bandit matches the batch simulation", () => {
  const rates = [0.03, 0.06, 0.05];
  const b = L.createBandit(rates, "thompson", 21);
  for (let i = 0; i < 300; i++) b.step();
  const s = L.simulateBandit(rates, 300, "thompson", 21);
  assert.deepEqual(b.pulls, s.pulls);
  near(b.regret, s.regret, 1e-9);
  assert.equal(b.bestArm, 1);
});

test("peeking inflates false positives, a fixed horizon does not", () => {
  const exp = L.peekingExperiment({ looks: 10, nPerLook: 200, trials: 4000, seed: 5 });
  assert.ok(exp.peeking > 0.14 && exp.peeking < 0.25, `peeking rate ${exp.peeking}`);
  assert.ok(exp.fixed > 0.03 && exp.fixed < 0.07, `fixed rate ${exp.fixed}`);
  assert.equal(exp.byLook.length, 10);
  for (let i = 1; i < exp.byLook.length; i++) assert.ok(exp.byLook[i] >= exp.byLook[i - 1]);
  near(exp.byLook[9], exp.peeking, 1e-12);
  const rate = L.peekingFalsePositiveRate(10, 200, 4000, { seed: 5 });
  near(rate, exp.peeking, 1e-12);
  const one = L.peekingFalsePositiveRate(1, 2000, 4000, { seed: 5 });
  assert.ok(one > 0.03 && one < 0.07, `single look rate ${one}`);
});

test("peeking p value shortcut equals the full test", () => {
  // The demo uses a light weight z test; make sure the decision agrees with twoProportionTest.
  const rng = L.mulberry32(77);
  for (let i = 0; i < 200; i++) {
    const na = 200 + Math.floor(rng() * 2000), nb = na;
    const ca = L.binomialSample(rng, na, 0.05), cb = L.binomialSample(rng, nb, 0.05);
    if (ca + cb === 0) continue;
    const full = L.twoProportionTest(ca, na, cb, nb).pValue;
    const z = (cb / nb - ca / na) / Math.sqrt(((ca + cb) / (na + nb)) * (1 - (ca + cb) / (na + nb)) * (1 / na + 1 / nb));
    near(2 * L.normCdf(-Math.abs(z)), full, 1e-12);
  }
});
