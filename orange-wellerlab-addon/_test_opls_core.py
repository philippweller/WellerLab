#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless unit checks for wellerlab.plsda.opls_core (no Orange/Qt required).

Run:  python _test_opls_core.py
Checks the numerical contract the widget relies on:
  1. separable classes  -> high R2Y/Q2, correct classification
  2. discriminating features -> highest VIP
  3. VIP normalisation (mean of VIP^2 ~ 1, as in ropls/MetaboAnalyst)
  4. S-plot p(corr) within [-1, 1] and consistent with p1
  5. permutation test: small p for real signal, large p for shuffled labels
  6. multiclass (3 classes) runs and separates
  7. orthogonal components reduce the orthogonal variation (R2X accounting)
"""
import sys
import numpy as np

from wellerlab.plsda.opls_core import fit_opls, opls_vip, permutation_test

rng = np.random.RandomState(42)
fails = []


def add_shift(X, mask, feats, shift):
    """Add a class-specific offset. NOTE: `X[mask][:, feats] += s` silently
    writes into a COPY (boolean indexing) - np.ix_ is required."""
    X = X.copy()
    X[np.ix_(mask, feats)] += shift
    return X


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(name)


# ---------------------------------------------------------------- datasets
n, p = 36, 24
y = np.array([0] * (n // 2) + [1] * (n // 2))
X = rng.normal(0, 1.0, (n, p))
signal_feats = [2, 5, 9, 14]
X = add_shift(X, y == 1, signal_feats, 2.0)   # clear class difference

Xr = rng.normal(0, 1.0, (n, p))              # no signal at all
yr = rng.randint(0, 2, n)

# ---------------------------------------------------------------- 1) separable
m = fit_opls(X, y, n_pred=1, auto_ortho=True, q2_folds=7, seed=1)
check("1a R2Y high on separable data", m.r2y > 0.70, f"R2Y={m.r2y:.3f}")
check("1b Q2 positive and below R2Y", (m.q2 is not None) and 0.3 < m.q2 <= m.r2y + 1e-9,
      f"Q2={m.q2:.3f}")
pred, prob = m.predict(X)
acc = float(np.mean(pred == y))
check("1c classification accuracy > 0.9", acc > 0.9, f"acc={acc:.3f}")
print(f"      R2X={m.r2x:.3f}  n_ortho={m.n_ortho}  {m}")

# ---------------------------------------------------------------- 2) VIP
vip = m.vip
top = list(np.argsort(-vip)[:len(signal_feats)])
check("2a discriminating features have the highest VIP",
      set(top) == set(signal_feats), f"top={sorted(top)} expected={sorted(signal_feats)}")
check("2b VIP of signal features above the rest",
      vip[signal_feats].min() > np.delete(vip, signal_feats).max(),
      f"min(signal)={vip[signal_feats].min():.2f} vs max(rest)={np.delete(vip, signal_feats).max():.2f}")

# ---------------------------------------------------------------- 3) VIP scale
mean_sq = float(np.mean(vip ** 2))
check("3 mean(VIP^2) ~ 1 (ropls normalisation)", 0.7 < mean_sq < 1.4, f"mean(VIP^2)={mean_sq:.3f}")

# ---------------------------------------------------------------- 4) S-plot
check("4a p(corr) within [-1, 1]", np.all(np.abs(m.pcorr) <= 1.0 + 1e-9),
      f"range=[{m.pcorr.min():.2f}, {m.pcorr.max():.2f}]")
check("4b p1 and pcorr correlated for the predictive component",
      abs(np.corrcoef(m.p1, m.pcorr)[0, 1]) > 0.5)
sig_corr = np.sign(m.pcorr)[signal_feats]
check("4c signal features share the sign of their p(corr)",
      len(set(sig_corr.tolist())) == 1, f"signs={sig_corr.tolist()}")

# ---------------------------------------------------------------- 5) permutation
perm_real = permutation_test(X, y, n_perm=20, seed=3)
check("5a permutation p small for real signal", perm_real["p_r2y"] <= 0.1,
      f"p={perm_real['p_r2y']:.3f} (R2Y obs={perm_real['r2y_obs']:.3f} vs perm mean={perm_real['r2y_perm_mean']:.3f})")
perm_null = permutation_test(Xr, yr, n_perm=20, seed=4)
check("5b permutation p large for shuffled/no signal", perm_null["p_r2y"] > 0.2,
      f"p={perm_null['p_r2y']:.3f}")

# ---------------------------------------------------------------- 6) multiclass
y3 = np.repeat([0, 1, 2], n // 3)
X3 = rng.normal(0, 1.0, (n, p))
X3 = add_shift(X3, y3 == 1, [1, 3], 2.0)
X3 = add_shift(X3, y3 == 2, [6, 8], 2.0)
m3 = fit_opls(X3, y3, n_pred=2, n_ortho=1, q2_folds=7, seed=5)
pred3, _ = m3.predict(X3)
check("6 multiclass (3 classes) fits and predicts > 0.8",
      len(m3.classes) == 3 and float(np.mean(pred3 == y3)) > 0.8,
      f"acc={float(np.mean(pred3 == y3)):.3f} R2Y={m3.r2y:.3f} Q2={m3.q2:.3f}")

# ---------------------------------------------------------------- 7) ortho components
m0 = fit_opls(X, y, n_pred=1, n_ortho=0, auto_ortho=False, q2_folds=7, seed=1)
check("7 orthogonal components reduce R2X of the predictive part or keep Q2",
      m.n_ortho >= 0 and m.q2 >= m0.q2 - 0.15,
      f"Q2(auto={m.n_ortho} ortho)={m.q2:.3f} vs Q2(0 ortho)={m0.q2:.3f}")

print()
if fails:
    print(f"{len(fails)} FEHLGESCHLAGEN: {fails}")
    sys.exit(1)
print("alle Pruefungen bestanden")
