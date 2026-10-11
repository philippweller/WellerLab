#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless checks for the shared table helpers (offscreen).

    python3 run_tests.py        # runs this with the other suites

Guards the recurring bug behind "my categorical groups show up as 0.0/1.0/2.0":
a categorical column can carry CODES in the data array, and stringifying those
gives numbers instead of the group names.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from Orange.data import (Table, Domain, ContinuousVariable, DiscreteVariable,
                         StringVariable)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wellerlab.tableutils import group_labels, labels_of, looks_numeric, variable_of

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


LVL = ["ANF", "OPP", "S33", "WILD"]
n, p = 12, 6
codes = np.repeat(np.arange(4), 3)
rng = np.random.RandomState(0)
X = rng.normal(10, 1, (n, p))
attrs = [ContinuousVariable(f"f{i}") for i in range(p)]


def meta_table(kind):
    """'codes' -> discrete meta holding codes; 'strings' -> holding the values."""
    col = [float(c) for c in codes] if kind == "codes" else [LVL[c] for c in codes]
    return Table.from_numpy(
        Domain(attrs, DiscreteVariable("cls", values=["a", "b"]),
               [StringVariable("sample"),
                DiscreteVariable("group", values=LVL)]),
        X=X, Y=np.zeros((n, 1)),
        metas=np.array([[f"s{i}", col[i]] for i in range(n)], dtype=object))


def class_table():
    return Table.from_numpy(
        Domain(attrs, DiscreteVariable("group", values=LVL),
               [StringVariable("sample")]),
        X=X, Y=codes.reshape(-1, 1).astype(float),
        metas=np.array([[f"s{i}"] for i in range(n)], dtype=object))


def numeric_table(with_class=True):
    cls = (DiscreteVariable("ferment", values=LVL) if with_class
           else ContinuousVariable("target"))
    y = (codes.reshape(-1, 1).astype(float) if with_class
         else np.zeros((n, 1)))
    return Table.from_numpy(
        Domain(attrs, cls, [StringVariable("sample"), ContinuousVariable("group")]),
        X=X, Y=y, metas=np.array([[f"s{i}", float(codes[i])] for i in range(n)],
                                 dtype=object))


# --- the helper itself -------------------------------------------------------
for kind in ("codes", "strings"):
    labels, levels = group_labels(meta_table(kind))
    check(f"discrete meta with {kind}: codes resolved to names", levels == LVL,
          f"{levels}")
    check(f"discrete meta with {kind}: one label per sample",
          len(labels) == n and labels[0] == "ANF", f"{labels[:4]}")

labels, levels = group_labels(class_table())
check("a discrete CLASS variable works too (Y, not metas)",
      levels == LVL and len(labels) == n, f"{levels}")

labels, levels = group_labels(numeric_table(with_class=True))
check("a purely numeric group column falls back to the discrete class",
      levels == LVL, f"{levels}")
labels, levels = group_labels(numeric_table(with_class=False))
check("…but keeps the numbers when there is no discrete class to fall back to",
      all(looks_numeric([l]) for l in labels), f"{levels}")

check("no group column -> (None, [])",
      group_labels(Table.from_numpy(Domain(attrs, DiscreteVariable("cls", values=["a"])),
                                    X=X, Y=np.zeros((n, 1)))) == (None, []))
check("a group stored as an ATTRIBUTE is found",
      bool(variable_of(meta_table("strings"), "group")))

# --- the widgets use it ------------------------------------------------------
from wellerlab.metabo.widgets.owheatmap import OWMetaboHeatmap
from wellerlab.metabo.widgets.owunivariate import OWUnivariateStats
from wellerlab.metabo.widgets.owvolcano import OWVolcano

from AnyQt.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv or ["test"])
coded = meta_table("codes")

h = OWMetaboHeatmap()
for out in ("heatmap", "selected_data"):
    getattr(h.Outputs, out).send = lambda v: None
h.set_data(coded)
app.processEvents()
check("heatmap colour bar shows names, not codes",
      h._read_groups()[1] == LVL, f"{h._read_groups()[1]}")

v = OWVolcano()
for out in ("selected", "selected_data", "feature_values", "volcano_data",
            "group_means"):
    o = getattr(v.Outputs, out, None)
    if o is not None:
        o.send = lambda value: None
v.set_data(coded)
app.processEvents()
check("volcano group levels show names", v._levels == LVL, f"{v._levels}")
check("volcano group combo shows names",
      [v.a_combo.itemText(i) for i in range(v.a_combo.count())] == LVL,
      f"{[v.a_combo.itemText(i) for i in range(v.a_combo.count())]}")

u = OWUnivariateStats()
u.Outputs.results.send = lambda value: None
u.set_data(coded)
app.processEvents()
check("univariate base-group combo shows names", u._groups_list == LVL,
      f"{u._groups_list}")

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Table-Helpers: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
