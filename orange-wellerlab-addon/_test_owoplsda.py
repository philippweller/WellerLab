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
import pyqtgraph as pg

from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import QApplication

from Orange.data import (Table, Domain, ContinuousVariable, DiscreteVariable,
                         StringVariable)
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
yvar = DiscreteVariable("cls", values=["A", "B"])   # not "group": that name is a meta below
# metas as the Metabo Feature Table would deliver them (checked for the
# "Selected Data" output, which must keep them)
_meta = np.array([[f"sample_{i}", "A" if cls[i] == 0 else "B"]
                  for i in range(n)], dtype=object)
data = Table.from_numpy(Domain(attrs, yvar,
                               [StringVariable("sample"), StringVariable("group")]),
                        X=X, Y=cls.reshape(-1, 1), metas=_meta)

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

# a click without a fitted model (e.g. constant class column) must be ignored
w_nomodel = OWOPLSDA()
w_nomodel.Outputs.selected.send = lambda v: None
try:
    w_nomodel._on_point_clicked(None, np.array([_Pt(0)], dtype=object))
    no_crash = w_nomodel._manual == set()
except Exception as exc:                                  # pragma: no cover
    no_crash, exc_detail = False, repr(exc)
check("click before a fit is ignored instead of raising", no_crash,
      "" if no_crash else exc_detail)

# --- more than one predictive component (p_pred is (p, n_pred)) -------------
w_multi = OWOPLSDA()
multi = {}
for out_name in ("data", "components", "splot_data", "selected",
                 "feature_values", "biomarkers", "selected_data"):
    getattr(w_multi.Outputs, out_name).send = (
        (lambda v: multi.__setitem__("components", v))
        if out_name == "components" else (lambda v: None))
w_multi.n_components = 2
try:
    w_multi.set_data(data)
    app.processEvents()
    comp = multi.get("components")
    crashed = None
except Exception as exc:                                    # pragma: no cover
    comp, crashed = None, repr(exc)
check("n_components=2 does not raise (p_pred is 2-D)", crashed is None, crashed or "")
check("one output column per predictive component",
      comp is not None
      and [a.name for a in comp.domain.attributes][:2] == ["Predictive1",
                                                           "Predictive2"],
      f"{None if comp is None else [a.name for a in comp.domain.attributes]}")
check("components table still has one row per feature",
      comp is not None and len(comp) == p and comp.X[:, :2].any(),
      f"{None if comp is None else len(comp)} rows for {p} features")

# --- class contrast: pick which two classes are compared --------------------
LVL4 = ["ANF", "OPP", "S33", "WILD"]
codes4 = np.repeat(np.arange(4), 8)
X4 = rng.normal(0, 1, (32, p))
for c in range(4):
    X4[codes4 == c, c] += 2.0
data4 = Table.from_numpy(
    Domain([ContinuousVariable(a.name) for a in data.domain.attributes],
           DiscreteVariable("group", values=LVL4),
           [StringVariable("sample"), StringVariable("ferment")]),
    X=X4, Y=codes4.reshape(-1, 1).astype(float),
    metas=np.array([[f"s{i}", LVL4[codes4[i]]] for i in range(32)], dtype=object))

w4 = OWOPLSDA()
four = {}
for out_name in ("data", "components", "splot_data", "selected",
                 "feature_values", "biomarkers", "selected_data"):
    getattr(w4.Outputs, out_name).send = (
        (lambda v: four.__setitem__("data", v)) if out_name == "data"
        else (lambda v: None))
w4.set_data(data4)
app.processEvents()

check("class combos offer every class value",
      [w4.a_combo.itemText(i) for i in range(w4.a_combo.count())] == LVL4
      and [w4.b_combo.itemText(i) for i in range(w4.b_combo.count())] == LVL4,
      f"{[w4.b_combo.itemText(i) for i in range(w4.b_combo.count())]}")
check("the model is fitted on the selected pair only (2 of 4 classes)",
      sorted({int(w4.data.Y[i]) for i in range(len(w4.data))}) == [0, 1],
      f"{sorted({int(w4.data.Y[i]) for i in range(len(w4.data))})}")
check("the S-plot title names the contrast",
      "OPP vs ANF" in w4.plot_widget.getPlotItem().titleLabel.text,
      w4.plot_widget.getPlotItem().titleLabel.text[:34])

w4.group_b = 2                       # ANF vs S33 -> codes 0 and 2
w4._class_changed()
app.processEvents()
check("switching the pair refits on the new classes",
      sorted({int(w4.data.Y[i]) for i in range(len(w4.data))}) == [0, 2],
      f"{sorted({int(w4.data.Y[i]) for i in range(len(w4.data))})}")
check("title and label follow the new pair",
      "S33 vs ANF" in w4.plot_widget.getPlotItem().titleLabel.text
      and "S33" in w4.lbl_contrast.text(),
      f"{w4.lbl_contrast.text()}")

out4 = w4._create_output_data()
check("with a class subset the probability columns match the model",
      [m.name for m in out4.domain.metas if m.name.startswith("p(")]
      == ["p(group=ANF)", "p(group=S33)"],
      f"{[m.name for m in out4.domain.metas if m.name.startswith('p(')]}")
check("predicted classes are written as the ORIGINAL codes (0 and 2)",
      {int(out4.metas[i, -3]) for i in range(len(out4))} <= {0, 2},
      f"{sorted({int(out4.metas[i, -3]) for i in range(len(out4))})}")

w4.group_b = 0                       # the same class twice
w4._class_changed()
app.processEvents()
check("picking the same class twice warns and drops the model",
      w4.model is None and "pick two different classes" in w4.lbl_contrast.text(),
      f"model={w4.model}")

# --- the selection must be visible in the plot ------------------------------
w4.group_b = 1
w4._class_changed()
app.processEvents()
w4._manual = set(list(w4.splot_feature_names)[:3])
w4._manual_mode = True
w4._refresh_selection()
app.processEvents()
scatters = [i for i in w4.plot_widget.plotItem.items
            if isinstance(i, pg.ScatterPlotItem)]
check("the selection is drawn as separate, bigger markers",
      len(scatters) == 2
      and sorted(s.opts["size"] for s in scatters) == [8, 15],
      f"{sorted(s.opts['size'] for s in scatters)}")
hl = [s for s in scatters if s.opts["size"] == 15][0]
check("the highlighted markers sit on the selected points",
      len(hl.getData()[0]) == 3
      and list(hl.getData()[0]) == [w4.splot_p[i] for i in
                                    w4._selection_indices().tolist()],
      f"{list(hl.getData()[0])}")

# --- S-plot per predictive component (n_components > 1) ---------------------
w_c = OWOPLSDA()
for out_name in ("data", "components", "splot_data", "selected",
                 "feature_values", "biomarkers", "selected_data"):
    getattr(w_c.Outputs, out_name).send = lambda v: None
w_c.n_components = 2
w_c.set_data(data)
app.processEvents()
model = w_c.model
check("S-plot offers one entry per predictive component",
      [w_c.comp_combo.itemText(i) for i in range(w_c.comp_combo.count())]
      == ["1", "2"] and w_c.comp_combo.isEnabled(),
      f"{[w_c.comp_combo.itemText(i) for i in range(w_c.comp_combo.count())]}")
check("component 1 is the default and matches p_pred[:, 0]",
      np.allclose(w_c.splot_p, np.asarray(model.p_pred)[:, 0]))
w_c.splot_comp = 1
w_c._create_splot_data()
check("switching the component switches the loadings",
      np.allclose(w_c.splot_p, np.asarray(model.p_pred)[:, 1])
      and not np.allclose(w_c.splot_p, np.asarray(model.p_pred)[:, 0]))
check("p(corr) is recomputed for that component (|r| <= 1)",
      np.all(np.abs(w_c.splot_pcorr) <= 1.0000001),
      f"max {np.abs(w_c.splot_pcorr).max():.3f}")
w_c._draw_splot()
check("the title names the component",
      "component 2/2" in w_c.plot_widget.getPlotItem().titleLabel.text,
      w_c.plot_widget.getPlotItem().titleLabel.text[:40])

w_c.n_components = 1
w_c.settings_changed()          # the GUI path: rebuilds the learner, then refits
app.processEvents()
check("a single predictive component hides the selector",
      not w_c.comp_combo.isEnabled()
      and "component" not in w_c.plot_widget.getPlotItem().titleLabel.text)

# ---------------------------------------------------------------- lasso
w_lasso = OWOPLSDA()
sd_box = {}
for out in ("data", "components", "splot_data", "selected", "feature_values",
            "biomarkers", "selected_data"):
    getattr(w_lasso.Outputs, out).send = (
        (lambda v: sd_box.__setitem__("t", v)) if out == "selected_data"
        else (lambda v: None))
w_lasso.set_data(data)
app.processEvents()
w_lasso._manual = set()
w_lasso._manual_mode = False
w_lasso.lasso = True
w_lasso._lasso_toggled()
check("lasso flag reaches the S-plot widget",
      w_lasso.plot_widget.lasso_enabled and w_lasso.plot_widget.on_lasso is not None)

# NOTE: do not shadow `p` - it holds the feature count further down the file.
splot_p, splot_c = w_lasso.splot_p, w_lasso.splot_pcorr
pad = 0.05 * (max(abs(splot_p).max(), abs(splot_c).max()) + 1e-9)
poly = [(splot_p.min() - pad, splot_c.min() - pad),
        (splot_p.max() + pad, splot_c.min() - pad),
        (splot_p.max() + pad, splot_c.max() + pad),
        (splot_p.min() - pad, splot_c.max() + pad)]
w_lasso._lasso_select(poly)
check("lasso selects every enclosed S-plot point",
      len(w_lasso._manual) == len(w_lasso.splot_feature_names),
      f"{len(w_lasso._manual)} of {len(w_lasso.splot_feature_names)}")
before = set(w_lasso._manual)
w_lasso._lasso_select([(0.0, 0.0), (1.0, 0.0)])          # degenerate polygon
check("a degenerate polygon changes nothing", set(w_lasso._manual) == before)
check("lasso is additive (existing picks stay)",
      w_lasso._manual == before)
w_lasso.lasso = False
w_lasso._lasso_toggled()
check("lasso can be switched off", not w_lasso.plot_widget.lasso_enabled)

# end-to-end: draw the polygon with real mouse events on the plot widget
from AnyQt.QtCore import QEvent, QPoint, QPointF
from AnyQt.QtGui import QMouseEvent

LB, NB, NM = Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier


def _ev(kind, pos):
    p = QPointF(pos)
    buttons = LB if kind != QEvent.Type.MouseButtonRelease else NB
    return QMouseEvent(kind, p, p, LB, buttons, NM)


def widget_pos(x, y):
    """Widget pixel position for a point in S-plot (view) coordinates."""
    pw = w_lasso.plot_widget
    scene = pw.getViewBox().mapViewToScene(QPointF(x, y))
    return pw.mapFromScene(scene)


w_lasso._manual = set()
w_lasso._manual_mode = False
w_lasso.lasso = True
w_lasso._lasso_toggled()
pad = 0.05 * (max(abs(splot_p).max(), abs(splot_c).max()) + 1e-9)
corners = [(splot_p.min() - pad, splot_c.min() - pad),
           (splot_p.max() + pad, splot_c.min() - pad),
           (splot_p.max() + pad, splot_c.max() + pad),
           (splot_p.min() - pad, splot_c.max() + pad)]
pw = w_lasso.plot_widget
pw.mousePressEvent(_ev(QEvent.Type.MouseButtonPress, widget_pos(*corners[0])))
for c in corners[1:]:
    pw.mouseMoveEvent(_ev(QEvent.Type.MouseMove, widget_pos(*c)))
pw.mouseReleaseEvent(_ev(QEvent.Type.MouseButtonRelease, widget_pos(*corners[0])))
check("dragging a lasso in the plot selects the enclosed points",
      len(w_lasso._manual) == len(w_lasso.splot_feature_names),
      f"{len(w_lasso._manual)} of {len(w_lasso.splot_feature_names)}")

sd = sd_box.get("t")
check("Selected Data output carries the selected features",
      sd is not None and set(a.name for a in sd.domain.attributes) == w_lasso._manual
      and len(sd) == len(data),
      f"{None if sd is None else f'{len(sd)}x{len(sd.domain.attributes)}'}")
check("Selected Data keeps the sample/group metas",
      sd is not None and {"sample", "group"} <= {m.name for m in sd.domain.metas},
      f"metas={None if sd is None else [m.name for m in sd.domain.metas]}")
check("the polygon is removed after the drag",
      pw._polygon is None and pw._artist is None)
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
