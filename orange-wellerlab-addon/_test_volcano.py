#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless checks for the Metabo Volcano widget (offscreen).

    python3 run_tests.py        # runs this with the other suites

Covers the selection features: single click, shift-click multi-select, lasso
selection and the "Selected Data" output (samples x selected features).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

import AnyQt.QtWidgets as QtW
from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import QApplication

from Orange.data import (Table, Domain, ContinuousVariable, DiscreteVariable,
                         StringVariable)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wellerlab.metabo.widgets.owvolcano import OWVolcano

app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


def volcano_data(n_feat=8, per=4, groups=("A", "B"), seed=2):
    rng = np.random.RandomState(seed)
    n = len(groups) * per
    X = rng.normal(10, 1.0, (n, n_feat))
    g = np.repeat(list(groups), per)
    X[g == groups[0], 0] += 5.0
    X[g == groups[1], 1] += 4.0
    return Table.from_numpy(
        Domain([ContinuousVariable(f"feat_{i:02d}") for i in range(n_feat)],
               DiscreteVariable("cls", values=["a", "b"]),
               [StringVariable("sample"), StringVariable("group")]),
        X=X, Y=np.zeros((n, 1)),
        metas=np.array([[f"{g[i]}_{i}", g[i]] for i in range(n)], dtype=object))


def make_volcano(data):
    w = OWVolcano()
    w.Outputs.feature_values.send = lambda v: None
    out = {}
    w.Outputs.selected_data.send = lambda v: out.__setitem__("sel", v)
    w.set_data(data)
    app.processEvents()
    return w, out


def shift_clicks(w, indices):
    """Shift-click the given point indices (multi-select)."""
    orig = QtW.QApplication.keyboardModifiers
    QtW.QApplication.keyboardModifiers = staticmethod(lambda: Qt.ShiftModifier)
    try:
        offs = w._sc.get_offsets()
        for i in indices:
            w._select_at(w._ax_scatter, float(offs[i, 0]), float(offs[i, 1]))
    finally:
        QtW.QApplication.keyboardModifiers = orig


data = volcano_data()
w, out = make_volcano(data)

check("volcano plotted points from Data alone",
      w._sc is not None and len(w._feat) > 0, f"{0 if w._feat is None else len(w._feat)} points")

# --- single click -----------------------------------------------------------
offs = w._sc.get_offsets()
w._select_at(w._ax_scatter, float(offs[0, 0]), float(offs[0, 1]))
check("single click selects one feature", len(w._selected) == 1, f"{w._selected}")
first = list(w._selected)

# --- multi-select via shift-click ------------------------------------------
shift_clicks(w, [1, 2])
check("shift-click adds features", len(w._selected) == 3, f"{len(w._selected)}")
shift_clicks(w, [1])
check("shift-click removes an already selected feature",
      len(w._selected) == 2 and first[0] in w._selected, f"{len(w._selected)}")

# --- lasso ------------------------------------------------------------------
w.lasso = True
w._lasso_toggled()
check("lasso flag reaches the canvas",
      w.canvas.lasso_enabled and w.canvas.on_lasso is not None)
before = len(w._selected)
xs, ys = w._sc.get_offsets()[:, 0], w._sc.get_offsets()[:, 1]
pad = 0.5
poly = [(xs.min() - pad, ys.min() - pad), (xs.max() + pad, ys.min() - pad),
        (xs.max() + pad, ys.max() + pad), (xs.min() - pad, ys.max() + pad)]
w._lasso_select(w._ax_scatter, poly)
check("lasso selects every enclosed point", len(w._selected) == len(w._feat),
      f"{before} -> {len(w._selected)} of {len(w._feat)}")
w.lasso = False
w._lasso_toggled()
check("lasso can be switched off", not w.canvas.lasso_enabled)

# --- Selected Data output ---------------------------------------------------
sel = w._selected_data_table()
features = [a.name for a in sel.domain.attributes] if sel is not None else []
check("Selected Data is samples x selected features",
      sel is not None and len(sel) == len(data) and set(features) == set(w._selected),
      f"{None if sel is None else f'{len(sel)}x{len(features)}'}")
check("Selected Data carries the sample/group metas",
      sel is not None and {"sample", "group"} <= {m.name for m in sel.domain.metas})

w._clear_selection()
check("clearing empties the selection and the output",
      w._selected == [] and w._selected_data_table() is None)

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Metabo Volcano: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
