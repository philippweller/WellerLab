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
from matplotlib.patches import Rectangle

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


def widget_with_spy():
    w = OWMetaboHeatmap()
    return w, spy(w)


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

# --- 5) group legend (MetaboAnalyst-style) ---------------------------------
w5, _ = widget_with_spy()
w5.set_data(feature_table())                       # 3 groups
w5.group_mode = "bar + legend"
w5._draw()
leg = w5._ax_heat.get_legend()
labels = [t.get_text() for t in leg.get_texts()] if leg is not None else []
check("legend lists the group names", labels == ["G0", "G1", "G2"], f"{labels}")
check("legend is draggable", leg is not None and leg.get_draggable())
w5.legend_pos = "below"
w5._draw()
check("legend position 'below' also renders",
      w5._ax_heat.get_legend() is not None)
w5.group_mode = "bar + names"
w5._draw()
n_with_bar = len(w5.fig.axes)
check("group display 'bar + names' adds text to the bar",
      any(len(a.texts) for a in w5.fig.axes))
w5.group_mode = "none"
w5._draw()
check("group display 'none' omits bar and legend",
      w5._ax_heat.get_legend() is None and len(w5.fig.axes) == n_with_bar - 1,
      f"{n_with_bar} -> {len(w5.fig.axes)} Achsen")

# --- 6) row dendrogram ------------------------------------------------------
w6, _ = widget_with_spy()
w6.set_data(feature_table(n_feat=10))
n_axes_off = len(w6.fig.axes)
w6.show_dendrogram = True
w6._draw()
check("dendrogram adds its own axes", len(w6.fig.axes) > n_axes_off,
      f"{n_axes_off} -> {len(w6.fig.axes)}")
check("dendrogram axes contains the tree lines",
      any(getattr(a, "collections", []) for a in w6.fig.axes))
w6.show_dendrogram = False
w6._draw()
check("dendrogram can be switched off again", len(w6.fig.axes) == n_axes_off)

# --- 7) click a cell -> feature info ---------------------------------------
w7, _ = widget_with_spy()
data7 = feature_table()
w7.set_data(data7)
app.processEvents()
w7._on_canvas_click(w7._ax_heat, 1.2, 0.1)          # near the top-left cell
top_feature = w7._built["feats"][0]
check("click selects the nearest cell's feature", w7._selected == [top_feature]
      and w7._cell == (0, 1), f"{w7._selected} cell={w7._cell}")
info = w7._info_text()
check("info panel names the feature", top_feature in info, info[:60])
check("info panel reports the clicked sample and group",
      str(w7._built["samples"][1]) in info and "G0" in info)
check("info panel reports a p-value (ranking)", "p = " in info)
check("clicked cell is highlighted in the figure",
      any(isinstance(p, Rectangle) and p.get_linewidth() >= 2.0
          for a in w7.fig.axes for p in a.patches))
w7._on_canvas_click(w7._ax_heat, 50.0, 50.0)        # outside the heatmap
check("click outside the heatmap clears the selection",
      w7._selected == [] and w7._cell is None)

# --- 8) shift-click multi-select -------------------------------------------
from AnyQt.QtCore import Qt
import AnyQt.QtWidgets as _QtW
_orig_mods = _QtW.QApplication.keyboardModifiers
_QtW.QApplication.keyboardModifiers = staticmethod(lambda: Qt.ShiftModifier)
w7._on_canvas_click(w7._ax_heat, 1.0, 0.0)          # feature of row 0
w7._on_canvas_click(w7._ax_heat, 1.0, 1.0)          # feature of row 1
_QtW.QApplication.keyboardModifiers = _orig_mods
check("shift-click adds features to the selection", len(w7._selected) == 2,
      f"{w7._selected}")
check("selection can be cleared with the button", (w7._clear_selection() or True)
      and w7._selected == [])

# --- 9) lasso selection ----------------------------------------------------
w9, sent9 = widget_with_spy()
w9.set_data(feature_table(n_feat=10))
app.processEvents()
w9._lasso_toggled()                                  # lasso off by default
w9.lasso = True
w9._lasso_toggled()
check("lasso flag reaches the canvas", w9.canvas.lasso_enabled
      and w9.canvas.on_lasso is not None)
poly = [(-0.5, -0.5), (2.5, -0.5), (2.5, 2.5), (-0.5, 2.5)]   # cells of 3 rows
w9._lasso_select(w9._ax_heat, poly)
check("lasso selects the features of the enclosed cells",
      len(w9._selected) == 3, f"{len(w9._selected)}")

# --- 10) 'Selected Data' output --------------------------------------------
sel = w9._selected_data_table()
check("Selected Data is samples x selected features",
      sel is not None and len(sel) == len(w9.data)
      and [a.name for a in sel.domain.attributes] == w9._selected,
      f"{None if sel is None else f'{len(sel)}x{len(sel.domain.attributes)}'}")
w9._clear_selection()
check("clearing empties the Selected Data output",
      w9._selected_data_table() is None and sent9.get("heatmap") is not None)

# --- 11) combo-box values are ints in the GUI -------------------------------
# Orange's gui.comboBox stores the item INDEX unless sendSelectedValue is set;
# the widget must cope with that (and with an int saved by an earlier build).
from wellerlab.metabo.widgets.owheatmap import GROUP_MODES, LEGEND_POSITIONS
wi, _ = widget_with_spy()
wi.set_data(feature_table())
wi.group_mode = 0                  # as the combo box would store it
wi.legend_pos = 1
try:
    wi._draw()
    ok_draw = True
except Exception as e:                                    # pragma: no cover
    ok_draw, err = False, repr(e)
check("int combo values do not crash the draw", ok_draw,
      "" if ok_draw else err)
check("int values are normalised to the right modes",
      wi._group_mode() == GROUP_MODES[0] and wi._legend_pos() == LEGEND_POSITIONS[1])
check("legend still rendered for int values",
      wi._ax_heat.get_legend() is not None)

# --- 12) group labels arriving as CODES or as a numeric column ---------------
def coded_group_table():
    """'group' as a discrete META: the metas array then holds CODES (0.0, 1.0,
    ...), which is what turned the colour bar into numbers."""
    base = feature_table()
    n = len(base)
    return Table.from_numpy(
        Domain(list(base.domain.attributes),
               DiscreteVariable("cls", values=["a", "b"]),
               [StringVariable("sample"),
                DiscreteVariable("group", values=["G0", "G1", "G2"])]),
        X=np.asarray(base.X), Y=np.asarray(base.Y),
        metas=np.array([[f"s{i}", float(i // 3)] for i in range(n)], dtype=object))


def numeric_group_table():
    """'group' purely numeric, with the real names in a discrete class."""
    base = feature_table()
    n = len(base)
    return Table.from_numpy(
        Domain(list(base.domain.attributes),
               DiscreteVariable("ferment", values=["ANF", "OPP", "WILD"]),
               [StringVariable("sample"), ContinuousVariable("group")]),
        X=np.asarray(base.X),
        Y=np.repeat([0, 1, 2], n // 3).reshape(-1, 1),
        metas=np.array([[f"s{i}", float(i // 3)] for i in range(n)], dtype=object))


wc, _ = widget_with_spy()
wc.set_data(coded_group_table())
wc.group_mode = "bar + names"
wc._draw()
_, levels_c = wc._read_groups()
check("group codes are resolved to the variable's value names",
      levels_c == ["G0", "G1", "G2"], f"{levels_c}")
bar_texts = [t.get_text() for a in wc.fig.axes for t in a.texts]
check("no numbers are painted on the colour bar",
      bool(bar_texts) and all(t.startswith("G") for t in bar_texts),
      f"{bar_texts[:6]}")

wn, _ = widget_with_spy()
wn.set_data(numeric_group_table())
wn._draw()
_, levels_n = wn._read_groups()
check("a numeric 'group' column falls back to the discrete class names",
      levels_n == ["ANF", "OPP", "WILD"], f"{levels_n}")

# --- 13) the dendrogram spans every row --------------------------------------
wd, _ = widget_with_spy()
wd.set_data(feature_table(n_feat=10))
wd.cluster = True
wd.show_dendrogram = True
wd._draw()
nR = wd._built["Z"].shape[0]
den = [a for a in wd.fig.axes
       if a.get_position().x0 < 0.2 and a.get_position().height > 0.3]
heat = [a for a in wd.fig.axes if a.images][0]
check("dendrogram uses scipy's leaf scale (0 .. 10n)",
      bool(den) and tuple(den[0].get_ylim()) == (10.0 * nR, 0.0),
      f"{None if not den else den[0].get_ylim()}")
check("dendrogram matches the heatmap's vertical extent",
      bool(den) and np.allclose(den[0].get_position().bounds[1::2],
                                heat.get_position().bounds[1::2]),
      f"{None if not den else den[0].get_position().bounds[1::2]}")

# --- 14) distribution of the selected feature --------------------------------
wz, _ = widget_with_spy()
wz.set_data(feature_table())
wz._draw()
ax = wz.dist_canvas.fig.axes[0]
check("distribution shows a hint while nothing is selected",
      not ax.patches and bool(ax.texts))

wz._on_canvas_click(wz._ax_heat, 0.0, 0.0)
ax = wz.dist_canvas.fig.axes[0]
b = wz._built
y = np.asarray(b["raw"][b["feats"].index(wz._feature_of_interest())], dtype=float)
means = [float(np.mean([v for v, g in zip(y, b["groups"]) if g == lv]))
         for lv in b["levels"]]
check("distribution bars are the per-group means",
      np.allclose([p.get_height() for p in ax.patches], means),
      f"{[round(p.get_height(), 2) for p in ax.patches]}")
check("every sample is drawn as a dot",
      sum(len(c.get_offsets()) for c in ax.collections) == len(y),
      f"{sum(len(c.get_offsets()) for c in ax.collections)} of {len(y)}")
check("the x-axis labels the groups",
      [t.get_text() for t in ax.get_xticklabels()] == list(b["levels"]))

for mode, fn in (("Median", np.median), ("Sum", np.sum)):
    wz.agg = mode
    wz._draw_distribution()
    got = [p.get_height() for p in wz.dist_canvas.fig.axes[0].patches]
    exp = [float(fn([v for v, g in zip(y, b["groups"]) if g == lv]))
           for lv in b["levels"]]
    check(f"aggregation '{mode}' is applied per group", np.allclose(got, exp),
          f"{[round(v, 2) for v in got]}")

wz.agg = "Mean"
wz._draw_distribution()
wz._clear_selection()
check("clearing the selection returns the distribution hint",
      not wz.dist_canvas.fig.axes[0].patches and bool(wz.dist_canvas.fig.axes[0].texts))

# --- 15) the distribution panel keeps a usable size in a normal window ------
wsz, _ = widget_with_spy()
wsz.set_data(feature_table())
wsz.resize(1100, 760)
wsz.show()
QApplication.processEvents()
check("the distribution canvas enforces a minimum height",
      wsz.dist_canvas.minimumHeight() >= 200, f"{wsz.dist_canvas.minimumHeight()}")
check("neither canvas is crushed in a normal window",
      wsz.dist_canvas.height() >= 180 and wsz.canvas.height() >= 200,
      f"heatmap {wsz.canvas.height()} px / distribution {wsz.dist_canvas.height()} px")

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Metabo Heatmap: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
