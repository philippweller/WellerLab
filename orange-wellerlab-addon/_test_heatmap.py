#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless checks for the Metabo Heatmap widget (offscreen).

    python3 run_tests.py        # runs this with the other suites

Reproduces the workflow that used to fail: Metabo Feature Table -> Preprocess ->
Feature Filter -> Heatmap, i.e. Data WITHOUT a Results connection. The widget must
still draw and emit a table (ranking computed from Data).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from AnyQt.QtWidgets import QApplication

from Orange.data import Table, Domain, ContinuousVariable, DiscreteVariable, StringVariable

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wellerlab.metabo import metabo_core as mc
from wellerlab.metabo.widgets.owheatmap import OWMetaboHeatmap

app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


def feature_table(n_group=3, per_group=3, n_feat=8, group_meta=True, seed=1):
    """A table shaped like the Metabo Feature Table output (sample×feature,
    with 'group' / 'sample' metas)."""
    rng = np.random.RandomState(seed)
    n = n_group * per_group
    X = rng.normal(10, 1.0, (n, n_feat))
    groups = np.repeat([f"G{i}" for i in range(n_group)], per_group)
    for k, g in enumerate([f"G{i}" for i in range(n_group)]):     # make 2 features differ
        X[groups == g, k] += 5.0
    names = [f"f{i}" for i in range(n_feat)]
    attrs = [ContinuousVariable(f) for f in names]
    metas = [StringVariable("sample")] + ([StringVariable("group")] if group_meta else [])
    rows = [[f"s{i}"] + ([groups[i]] if group_meta else []) for i in range(n)]
    return Table.from_numpy(
        Domain(attrs, DiscreteVariable("cls", values=["a", "b"]), metas),
        X=X, Y=np.zeros((n, 1)), metas=np.array(rows, dtype=object))


def spy(widget):
    box = {}
    widget.Outputs.heatmap.send = lambda v: box.__setitem__("heatmap", v)
    return box


# --- 1) the reported workflow: Data only, no Results ------------------------
w = OWMetaboHeatmap()
out = spy(w)
data = feature_table(group_meta=True)
w.set_data(data)
app.processEvents()

check("no exception with Data only", True)
check("sends a Heatmap Data table without Results", out.get("heatmap") is not None,
      f"{len(out['heatmap']) if out.get('heatmap') is not None else 0} rows")
check("ranking computed from Data used the group meta",
      w._ranking_source == "data" and w._ranking_kind == "one-way ANOVA",
      f"source={w._ranking_source} kind={w._ranking_kind}")
check("status message reports the self-computed ranking",
      w.Information.ranked_from_data.is_shown())
if out.get("heatmap") is not None:
    check("output has top_n feature columns", len(out["heatmap"].domain.attributes) == w.top_n
          or len(out["heatmap"].domain.attributes) == len(data.domain.attributes),
          f"{len(out['heatmap'].domain.attributes)} Spalten")
check("figure actually contains a heatmap image",
      any(getattr(a, "images", []) for a in w.fig.axes))

# --- 2) without a group meta -> variance ranking ---------------------------
w2 = OWMetaboHeatmap()
out2 = spy(w2)
w2.set_data(feature_table(group_meta=False))
app.processEvents()
check("falls back to variance ranking without a group column",
      w2._ranking_source == "data" and w2._ranking_kind == "variance",
      f"kind={w2._ranking_kind}")
check("still draws and emits", out2.get("heatmap") is not None
      and any(getattr(a, "images", []) for a in w2.fig.axes))

# --- 3) with Results connected the Results ranking wins ---------------------
w3 = OWMetaboHeatmap()
out3 = spy(w3)
d3 = feature_table()
feat = [a.name for a in d3.domain.attributes]
groups = [str(v) for v in d3.metas[:, d3.domain.metas.index(d3.domain["group"])]]
res_df, _ = mc.univariate(np.asarray(d3.X, float).T, groups, "anova", feature_names=feat)
res_tab = Table.from_numpy(
    Domain([ContinuousVariable("p")], metas=[StringVariable("Feature")]),
    X=res_df[["p"]].to_numpy(float),
    metas=res_df[["Feature"]].to_numpy(dtype=object))
w3.set_data(d3)
w3.set_results(res_tab)
app.processEvents()
check("Results ranking takes precedence when connected",
      w3._ranking_source == "results", f"source={w3._ranking_source}")

# --- 4) no data at all -> warning, no crash --------------------------------
w4 = OWMetaboHeatmap()
out4 = spy(w4)
w4.set_data(None)
app.processEvents()
check("no data shows a warning instead of an empty plot",
      out4.get("heatmap") is None and w4.Warning.no_data.is_shown())

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Metabo Heatmap: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
