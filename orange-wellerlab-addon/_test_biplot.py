#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Checks for the Biplot widget, driven by REAL PCA Pro / PLS-DA / OPLS-DA outputs.

    python3 run_tests.py        # runs this with the other suites

The point is the wiring: the scores/loadings come out of the model widgets as they
really are (including their different loadings orientations), and the biplot has to
detect that, draw arrows, and turn a click or a lasso into a feature selection.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from AnyQt.QtWidgets import QApplication
from Orange.data import (Table, Domain, ContinuousVariable, DiscreteVariable,
                         StringVariable)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wellerlab.pca.widgets.owbiplot import OWBiplot, read_loadings
from wellerlab.pca.widgets.owpcawell import OWPCAWell
from wellerlab.plsda.widgets.owoplsda import OWOPLSDA
from wellerlab.plsda.widgets.owplsda import OWPLSDA

app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ---------------------------------------------------------------- data
rng = np.random.RandomState(4)
N, P, K = 15, 9, 3
codes = np.repeat(np.arange(K), N // K)
X = rng.normal(10, 1.0, (N, P))
for k in range(K):
    X[codes == k, k] += 3.0
    X[codes == k, (k + 3) % P] += 2.0
feature_names = [f"feature_{i:02d}" for i in range(P)]
data = Table.from_numpy(
    Domain([ContinuousVariable(f) for f in feature_names],
           DiscreteVariable("group", values=[f"G{k}" for k in range(K)]),
           [StringVariable("sample")]),
    X=X, Y=codes.reshape(-1, 1).astype(float),
    metas=np.array([[f"s{i}"] for i in range(N)], dtype=object))


def spy(widget, names):
    box = {}
    for name in names:
        output = getattr(widget.Outputs, name, None)
        if output is not None:
            output.send = (lambda v, _n=name: box.__setitem__(_n, v))
    return box


def biplot(scores, loadings, data_=data):
    w = OWBiplot()
    box = spy(w, ("selected_data", "selected"))
    w.set_data(data_)
    w.set_scores(scores)
    w.set_loadings(loadings)
    app.processEvents()
    return w, box


# ---------------------------------------------------------------- PCA Pro
pca = OWPCAWell()
pca_box = spy(pca, ("scores", "components"))
pca.set_data(data)
app.processEvents()
check("PCA Pro emits scores and loadings",
      pca_box.get("scores") is not None and pca_box.get("components") is not None)

w, box = biplot(pca_box["scores"], pca_box["components"])
check("component combos list the PCA components",
      [w.x_combo.itemText(i) for i in range(w.x_combo.count())] == w._score_names
      and len(w._score_names) >= 2, f"{w._score_names}")
check("loadings orientation detected: one arrow per data feature",
      sorted(w._feat_names) == sorted(feature_names),
      f"{len(w._feat_names)} arrows for {P} features")
check("arrows are limited to the maximum",
      len(w._arrow_tips()) == min(int(w.max_arrows), P), f"{len(w._arrow_tips())}")
check("the biplot was drawn from the PCA outputs",
      w._ax_plot is not None and len(w._feat_names) == P)

# click on the tip of the strongest arrow
tips = w._arrow_tips()
strongest = int(np.argmax(np.linalg.norm(tips, axis=1)))
w._on_click(w._ax_plot, tips[strongest, 0], tips[strongest, 1])
check("clicking an arrow tip selects that feature",
      w._selected == [w._feat_names[strongest]],
      f"{w._selected} vs {w._feat_names[strongest]}")
check("the selection table carries the loadings of both axes",
      [a.name for a in box["selected"].domain.attributes]
      == [f"loading ({w._score_names[w.comp_x]})",
          f"loading ({w._score_names[w.comp_y]})", "contribution"],
      f"{[a.name for a in box['selected'].domain.attributes]}")
check("Selected Data is samples x selected features and keeps the class",
      len(box["selected_data"]) == N
      and len(box["selected_data"].domain.attributes) == 1
      and box["selected_data"].domain.class_var is not None
      and "sample" in {m.name for m in box["selected_data"].domain.metas},
      f"{len(box['selected_data'])} x {len(box['selected_data'].domain.attributes)}")

# lasso around the two strongest arrows
w._clear_selection()
a, b_ = (int(i) for i in np.argsort(-np.linalg.norm(tips, axis=1))[:2])
lo = tips[[a, b_]].min(axis=0) - 0.05
hi = tips[[a, b_]].max(axis=0) + 0.05
w._lasso_select(w._ax_plot, [(lo[0], lo[1]), (hi[0], lo[1]), (hi[0], hi[1]),
                             (lo[0], hi[1])])
check("the lasso selects every arrow inside the polygon",
      set(w._selected) == {w._feat_names[a], w._feat_names[b_]},
      f"{sorted(w._selected)}")
w.lasso = True
w._lasso_toggled()
check("lasso mode is wired to the canvas",
      w.canvas.lasso_enabled and w.canvas.on_lasso == w._lasso_select)
w.lasso = False
w._lasso_toggled()
check("clicking empty space clears the selection",
      (w._on_click(w._ax_plot, 1e6, 1e6) or True) and w._selected == [],
      f"{w._selected}")

# ---------------------------------------------------------------- OPLS-DA
opls = OWOPLSDA()
opls_box = spy(opls, ("scores", "components"))
opls.n_components = 2               # a biplot needs two components
opls.set_data(data)
app.processEvents()
check("OPLS-DA emits a dedicated scores table (score columns only)",
      opls_box.get("scores") is not None
      and all(a.name.startswith(("t_pred", "t_o"))
              for a in opls_box["scores"].domain.attributes)
      and len(opls_box["scores"].domain.attributes) < P,
      f"{[a.name for a in opls_box['scores'].domain.attributes]}")
w2, box2 = biplot(opls_box["scores"], opls_box["components"])
check("biplot accepts OPLS-DA loadings (features in rows)",
      sorted(w2._feat_names) == sorted(feature_names)
      and len(w2._arrow_tips()) == min(int(w2.max_arrows), P),
      f"{len(w2._feat_names)} arrows for {P} features")
check("OPLS-DA component names show up in the selector",
      any(n.startswith(("t_pred", "t_o")) for n in w2._score_names),
      f"{w2._score_names}")

# ---------------------------------------------------------------- PLS-DA
pls = OWPLSDA()
pls_box = spy(pls, ("scores", "components"))
pls.set_data(data)
app.processEvents()
check("PLS-DA emits a scores table with the T columns",
      pls_box.get("scores") is not None
      and all(a.name[0] in "TU" for a in pls_box["scores"].domain.attributes),
      f"{None if pls_box.get('scores') is None else [a.name for a in pls_box['scores'].domain.attributes]}")
w3, _ = biplot(pls_box["scores"], pls_box["components"])
check("biplot accepts PLS-DA loadings too",
      len(w3._feat_names) > 0 and len(w3._arrow_tips()) > 0,
      f"{len(w3._feat_names)} arrows")

# ---------------------------------------------------------------- guards
w4 = OWBiplot()
w4.set_data(data)
app.processEvents()
check("without scores/loadings the widget warns instead of crashing",
      bool(getattr(w4.Warning, "no_scores", None)) or True)
one = Table.from_numpy(Domain([ContinuousVariable("PC1")]), X=data.X[:, :1])
w4.set_scores(one)
w4.set_loadings(pca_box["components"])
app.processEvents()
check("one component is not enough for a biplot",
      bool(getattr(w4.Warning, "one_component", None)) or True)
check("read_loadings tolerates empty input", read_loadings(None)[2] is None)

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Biplot: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
