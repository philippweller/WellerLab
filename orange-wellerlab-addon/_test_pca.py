#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless checks for the PCA Pro widget (offscreen).

    python3 run_tests.py        # runs this with the other suites

Focus: the T2 / Q-residual control chart, where three defects were found
(limit lines drawn with a data-derived length, so the Q line ran past the axes
while the T2 line stopped short and hid the outlier; the lines stayed visible
when their check box was off; the greyed "Components" spin showed the
count-method value, not the number of components actually in use).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pyqtgraph as pg

from AnyQt.QtWidgets import QApplication
from Orange.data import (Table, Domain, ContinuousVariable, DiscreteVariable,
                         StringVariable)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wellerlab.pca.pca_analysis import t2_limit
from wellerlab.pca.widgets.owpcawell import OWPCAWell

app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ---------------------------------------------------------------- data
rng = np.random.RandomState(0)
n, p = 30, 8
cls = np.repeat(["A", "B"], n // 2)
X = rng.normal(0, 1.0, (n, p))
X[cls == "B", :3] += 2.0
X[7] += 6.0                                   # one clear outlier
table = Table.from_numpy(
    Domain([ContinuousVariable(f"f{i}") for i in range(p)],
           DiscreteVariable("cls", values=["A", "B"]),
           [StringVariable("sample"), StringVariable("group")]),
    X=X, Y=(cls == "B").astype(float).reshape(-1, 1),
    metas=np.array([[f"s{i}", cls[i]] for i in range(n)], dtype=object))

# ---------------------------------------------------------------- widget
w = OWPCAWell()
sent = {}
for out in ("transformed_data", "data", "components", "scores", "outliers",
            "inliers"):
    o = getattr(w.Outputs, out, None)
    if o is not None:
        o.send = lambda v, _n=out: sent.__setitem__(_n, v)
w.set_data(table)
app.processEvents()

an = w.analytics
check("model was fitted", an is not None and w._scores is not None)
k = int(an.result["n_components"])

# ---------------------------------------------------------------- the count shown
check("the UI reports the number of components actually in use",
      str(k) in w.used_lbl.text(), f"{w.used_lbl.text()!r}")
check("that count can differ from the greyed 'Components' spin",
      w.comp_method != 2 or k == w.n_components,
      f"method={w.comp_method} spin={w.n_components} used={k}")

# ---------------------------------------------------------------- the limits
check("T2 limit matches the formula for the components in use",
      np.isclose(an.T2_lim, t2_limit(n, k, w.alpha)),
      f"{an.T2_lim:.3f} vs {t2_limit(n, k, w.alpha):.3f}")


def limit_lines():
    return [i for i in w.t2q_plot.plotItem.items if isinstance(i, pg.InfiniteLine)]


lines = limit_lines()
check("both limits are drawn as view-spanning lines", len(lines) == 2,
      f"{len(lines)} line(s)")
check("one vertical (T2) and one horizontal (Q) line",
      sorted(l.angle for l in lines) == [0, 90])
check("the lines sit on the computed limits",
      sorted(round(l.value(), 3) for l in lines)
      == sorted([round(an.T2_lim, 3), round(an.Q_lim, 3)]))

(x0, x1), (y0, y1) = w.t2q_plot.getViewBox().viewRange()
check("x range covers the data and the T2 limit",
      x1 >= max(float(an.T2.max()), an.T2_lim), f"x1={x1:.2f}")
check("y range covers the data and the Q limit",
      y1 >= max(float(an.Q.max()), an.Q_lim), f"y1={y1:.2f}")
check("ranges start at 0 (no wasted space below)",
      abs(x0) < 1e-9 and abs(y0) < 1e-9, f"({x0}, {y0})")
beyond = int((an.T2 > an.T2_lim).sum() + (an.Q > an.Q_lim).sum())
check("the planted outlier lies beyond a limit", beyond >= 1,
      f"{beyond} point(s) beyond; max T2 {an.T2.max():.2f} vs limit {an.T2_lim:.2f}")

# ---------------------------------------------------------------- toggling
w.use_Q = False
w._recalc_limits()
check("unchecking 'Use Q-residual limit' hides its line",
      len(limit_lines()) == 1, f"{len(limit_lines())} line(s)")
w.use_T2 = False
w._recalc_limits()
check("unchecking both hides both lines", len(limit_lines()) == 0)
w.use_T2 = w.use_Q = True
w._recalc_limits()
check("re-rendering does not stack duplicate lines", len(limit_lines()) == 2)
(x0, x1), (y0, y1) = w.t2q_plot.getViewBox().viewRange()
check("ranges are recomputed on redraw (no stale view)",
      x1 >= an.T2_lim and y1 >= an.Q_lim)

# ---------------------------------------------------------------- mask consistency
mask = an.inlier_mask(use_T2=True, use_Q=True)
check("inlier mask equals the two limits applied together",
      np.array_equal(mask, (an.T2 <= an.T2_lim) & (an.Q <= an.Q_lim)),
      f"{int((~mask).sum())} outlier(s)")
check("the Q limit is ignored when switched off",
      np.array_equal(an.inlier_mask(use_T2=True, use_Q=False),
                     an.T2 <= an.T2_lim))
check("the outlier is caught", not mask.all())

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "PCA Pro: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
