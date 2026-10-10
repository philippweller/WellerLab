#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless end-to-end check of the OPLS-DA widget (offscreen Qt).

Run with Orange's own Python:
    /Applications/Orange.app/Contents/MacOS/python _test_owoplsda.py

Verifies what the rework added: model quality numbers, S-Plot thresholds and
colour coding, "select relevant", manual click selection, and the outputs
(Data with Scores, Components, S-Plot Data, Selected Features, Feature Values).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from AnyQt.QtWidgets import QApplication

from Orange.data import Table, Domain, ContinuousVariable, DiscreteVariable
from wellerlab.plsda.widgets.owoplsda import OWOPLSDA

app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{('  ' + detail) if detail else ''}")
    if not ok:
        fails.append(name)


# ---------------------------------------------------------------- test data
rng = np.random.RandomState(7)
n, p = 40, 15
cls = np.array([0] * (n // 2) + [1] * (n // 2))
X = rng.normal(0, 1.0, (n, p))
X[np.ix_(cls == 1, [2, 5, 9])] += 2.2          # 3 discriminating features
attrs = [ContinuousVariable(f"f{i}") for i in range(p)]
yvar = DiscreteVariable("group", values=["A", "B"])
data = Table.from_numpy(Domain(attrs, yvar), X=X, Y=cls.reshape(-1, 1))

# ---------------------------------------------------------------- widget
w = OWOPLSDA()
captured = {}


def spy(name):
    def _send(value):
        captured[name] = value
    return _send


for out_name in ("data", "components", "splot_data", "selected",
                 "feature_values", "biomarkers"):
    getattr(w.Outputs, out_name).send = spy(out_name)

w.set_data(data)
app.processEvents()

check("quality labels filled (R2X/R2Y/Q2)",
      "—" not in w.lbl_r2x.text() and "—" not in w.lbl_r2y.text()
      and "—" not in w.lbl_q2.text(),
      f"{w.lbl_r2x.text()} | {w.lbl_r2y.text()} | {w.lbl_q2.text()}")

model = w.model
check("R2Y/Q2 in a sane range",
      model is not None and 0.5 < model.quality()["r2y"] <= 1.0
      and -1.0 <= model.quality()["q2"] <= 1.0,
      f"{model}")

# ---------------------------------------------------------------- S-Plot data
splot = captured.get("splot_data")
check("S-Plot Data output emitted", splot is not None,
      f"{len(splot) if splot is not None else 0} rows")
if splot is not None:
    names = [a.name for a in splot.domain.attributes]
    check("S-Plot table carries p1, p(corr), VIP",
          names == ["p1", "p(corr)", "VIP"], f"{names}")
    vi = names.index("VIP")
    vip = splot.X[:, vi]
    top = set(np.argsort(-vip)[:3])
    check("VIP ranks the 3 discriminating features first",
          top == {2, 5, 9}, f"top3={sorted(top)}")

check("thresholds produced relevant features",
      w._relevant is not None and 0 <= w._relevant.sum() <= len(data.domain.attributes),
      w.lbl_relevant.text())
check("plot has a scatter item", w.scatter_item is not None)
pts = w.scatter_item.points() if w.scatter_item is not None else []
colours = {pt.brush().color().name() for pt in pts}
check("relevant points are coloured differently",
      len(colours) > 1, f"{len(colours)} distinct colours, {len(pts)} points")

# ---------------------------------------------------------------- selection
w._clear_selection()
check("cleared selection emits no selected table", captured.get("selected") is None)

w._select_relevant()
sel = captured.get("selected")
rel_n = int(w._relevant.sum()) if w._relevant is not None else 0
check("'Select relevant' fills the Selected Features output",
      sel is not None and len(sel) == rel_n,
      f"{len(sel) if sel is not None else 0} rows vs relevant={rel_n}")

fv = captured.get("feature_values")
check("Feature Values output matches the selection",
      fv is not None and len(fv.domain.attributes) == rel_n
      and fv.domain.attributes[0].name in {a.name for a in data.domain.attributes},
      f"{[a.name for a in fv.domain.attributes] if fv is not None else None}")

check("legacy 'Selected Biomarkers' output kept in sync",
      captured.get("biomarkers") is not None
      and len(captured["biomarkers"]) == len(sel))

# ---------------------------------------------------------------- manual click
class _Pt:
    def __init__(self, i):
        self._i = i

    def index(self):
        return self._i


w._manual = set()
# pyqtgraph hands the clicked points as a NUMPY ARRAY, not a list - with more
# than one element `if not points` raises "truth value ... is ambiguous".
w._on_point_clicked(None, np.array([_Pt(0)], dtype=object))
check("manual click selects exactly one feature",
      len(w._manual) == 1, f"{sorted(w._manual)}")
w._on_point_clicked(None, np.array([_Pt(1), _Pt(2)], dtype=object))
check("multi-point click (numpy array) does not raise and selects both",
      len(w._manual) == 2, f"{sorted(w._manual)}")
w._manual = {sorted(w._manual)[0]}
w._refresh_selection()
check("manual selection overrides the relevant set",
      captured.get("selected") is not None and len(captured["selected"]) == 1)

# ---------------------------------------------------------------- data output
aug = captured.get("data")
check("Data with Scores output has the score columns",
      aug is not None and any(a.name.startswith("t_pred")
                              for a in aug.domain.attributes)
      and "Predicted" in [m.name for m in aug.domain.metas],
      f"{[a.name for a in aug.domain.attributes][-3:] if aug is not None else None}")

comp = captured.get("components")
check("Components output exists", comp is not None and len(comp) == p)

# ---------------------------------------------------------------- cleanup
w.set_data(None)
app.processEvents()
check("clearing the input sends empty outputs", captured.get("selected") is None)

print()
if fails:
    print(f"{len(fails)} FEHLGESCHLAGEN: {fails}")
    sys.exit(1)
print("alle Pruefungen bestanden")
