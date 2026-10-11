"""
OWOPLSDA widget — OPLS-DA (Orthogonal Partial Least Squares Discriminant
Analysis) with an interactive S-Plot for biomarker discovery.

Reworked to match what MetaboAnalyst offers for OPLS-DA:
  * model quality R2X / R2Y / Q2 (7-fold CV) and an optional permutation test
  * S-Plot of p1 (predictive loading) vs p(corr) with THRESHOLD sliders
  * relevant features are colour-coded (higher / lower), the rest stays grey
  * features can be selected: click a point, shift-click adds/removes
  * VIP and orthoVIP are exported
  * Outputs follow the Metabo widget conventions ("Selected Features",
    "Feature Values") next to the original OPLS-DA outputs

The numerics live in wellerlab.plsda.opls_core (Qt-free, unit-tested).
"""

import numpy as np
from AnyQt.QtCore import Qt
from AnyQt.QtGui import QColor
from AnyQt.QtWidgets import QApplication

import pyqtgraph as pg

from Orange.data import (Table, Domain, ContinuousVariable, DiscreteVariable,
                         StringVariable)
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.owlearnerwidget import OWBaseLearner
from Orange.widgets.utils.signals import Output
from Orange.widgets.utils.widgetpreview import WidgetPreview
from Orange.widgets.widget import Msg

from wellerlab.plsda import OPLSDALearner
from ...selection import LassoPlotWidget, points_in_polygon, select_features

# colours: grey = not relevant, red = higher in the positive class,
# blue = lower, and a dark edge for manually selected points
C_NS = (170, 176, 184, 170)
C_UP = (178, 24, 43, 220)
C_DOWN = (33, 102, 172, 220)
C_SEL = (20, 20, 20, 255)
#: selected points are re-drawn on top in this colour: a coloured point with
#: only a thin dark pen was effectively invisible in the S-plot
C_HL = (255, 145, 0, 255)
MAX_LABELS = 12


class OWOPLSDA(OWBaseLearner):
    name = "OPLS-DA"
    description = ("Orthogonal Partial Least Squares Discriminant Analysis "
                   "with an interactive S-Plot (thresholds, colour coding, "
                   "feature selection) and R2X/R2Y/Q2 validation.")
    icon = "icons/OPLSDA.svg"
    priority = 87
    keywords = ["orthogonal partial least squares", "discriminant analysis",
                "classification", "OPLS-DA", "S-Plot", "biomarker", "VIP",
                "Q2", "permutation"]

    LEARNER = OPLSDALearner

    class Outputs(OWBaseLearner.Outputs):
        data = Output("Data with Scores", Table, default=True)
        components = Output("Components", Table, explicit=True)
        splot_data = Output("S-Plot Data", Table, explicit=True)
        selected = Output("Selected Features", Table, explicit=True)
        feature_values = Output("Feature Values", Table, explicit=True)
        biomarkers = Output("Selected Biomarkers", Table, explicit=True)
        selected_data = Output("Selected Data", Table, explicit=True)

    class Warning(OWBaseLearner.Warning):
        no_class = Msg("OPLS-DA needs a discrete class variable.")
        same_class = Msg("Pick two different classes to compare.")

    # ------------------------------------------------------------- settings
    group_a = Setting(0)                # compared classes (index into the values)
    group_b = Setting(1)
    n_components = Setting(1)
    n_ortho = Setting(0)
    auto_ortho = Setting(True)
    scale = Setting(True)
    cv_folds = Setting(7)
    n_perm = Setting(0)                 # 0 = skip the permutation test
    p1_frac = Setting(20)               # % of max|p1| used as threshold
    pcorr_thr = Setting(0.5)            # |p(corr)| threshold
    label_top = Setting(True)
    lasso = Setting(False)              # left-drag selects a polygon, no panning

    want_main_area = True
    resizing_enabled = True
    graph_name = "plot_widget"

    def __init__(self):
        super().__init__()
        self.splot_p = None
        self.splot_pcorr = None
        self.splot_vip = None
        self.splot_feature_names = None
        self._relevant = None
        self._manual = set()            # manually selected feature names
        self._manual_mode = False       # False = follow the threshold set
        self._input_data = None         # the table as delivered (unfiltered)

        self.plot_widget = LassoPlotWidget(title="S-Plot")
        self.plot_widget.on_lasso = self._lasso_select
        self.plot_widget.lasso_enabled = bool(self.lasso)   # honour a saved setting
        self.plot_widget.setLabel("bottom", "p1 — predictive loading")
        self.plot_widget.setLabel("left", "p(corr) — correlation loading")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.addLine(x=0, pen=pg.mkPen(180, 180, 180, 120))
        self.plot_widget.addLine(y=0, pen=pg.mkPen(180, 180, 180, 120))
        self.mainArea.layout().addWidget(self.plot_widget)

        self.scatter_item = None

    # ------------------------------------------------------------- controls
    def add_main_layout(self):
        cbox = gui.vBox(self.controlArea, "Compare")
        self.a_combo = gui.comboBox(
            cbox, self, "group_a", items=[], label="Group A: ",
            orientation=Qt.Horizontal, callback=self._class_changed)
        self.b_combo = gui.comboBox(
            cbox, self, "group_b", items=[], label="Group B: ",
            orientation=Qt.Horizontal, callback=self._class_changed)
        self.lbl_contrast = gui.label(cbox, self, "")

        box = gui.vBox(self.controlArea, "Optimization Parameters")
        gui.spin(box, self, "n_components", 1, 10, 1,
                 label="Predictive components: ", alignment=Qt.AlignRight,
                 controlWidth=70, callback=self.settings_changed)
        gui.checkBox(box, self, "auto_ortho",
                     "Optimize orthogonal components (by Q2)",
                     callback=self.settings_changed)
        self.ortho_spin = gui.spin(
            box, self, "n_ortho", 0, 20, 1,
            label="Orthogonal components: ", alignment=Qt.AlignRight,
            controlWidth=70, callback=self.settings_changed)
        gui.spin(box, self, "cv_folds", 2, 20, 1,
                 label="CV folds (Q2): ", alignment=Qt.AlignRight,
                 controlWidth=70, callback=self.settings_changed)
        gui.spin(box, self, "n_perm", 0, 1000, 20,
                 label="Permutations: ", alignment=Qt.AlignRight,
                 controlWidth=70, callback=self.settings_changed,
                 tooltip="0 = skip the permutation test (it is slow)")
        gui.checkBox(box, self, "scale", "Autoscale features",
                     callback=self.settings_changed)
        self._sync_ortho_spin()

        qbox = gui.vBox(self.controlArea, "Model quality")
        self.lbl_r2x = gui.label(qbox, self, "R2X (cum): —")
        self.lbl_r2y = gui.label(qbox, self, "R2Y (cum): —")
        self.lbl_q2 = gui.label(qbox, self, "Q2 (cum): —")
        self.lbl_perm = gui.label(qbox, self, "Permutation: —")

        thr = gui.vBox(self.controlArea, "S-Plot thresholds")
        gui.spin(thr, self, "p1_frac", 0, 100, 1,
                 label="|p1| ≥ (% of max): ", alignment=Qt.AlignRight,
                 controlWidth=70, callback=self._thresholds_changed)
        gui.doubleSpin(thr, self, "pcorr_thr", 0.0, 1.0, 0.05,
                       label="|p(corr)| ≥: ", alignment=Qt.AlignRight,
                       controlWidth=70, decimals=2,
                       callback=self._thresholds_changed)
        gui.checkBox(thr, self, "label_top", "Label top features",
                     callback=self._thresholds_changed)
        self.lbl_relevant = gui.label(thr, self, "relevant: —")

        sel = gui.vBox(self.controlArea, "Selection")
        gui.checkBox(sel, self, "lasso", "Lasso select (drag in the plot)",
                     callback=self._lasso_toggled,
                     tooltip="Left-drag draws a polygon; every point inside is "
                             "added to the selection. The wheel still zooms.")
        gui.button(sel, self, "Select relevant", callback=self._select_relevant)
        gui.button(sel, self, "Clear selection", callback=self._clear_selection)
        self.lbl_selected = gui.label(sel, self, "selected: 0")

        gui.rubber(self.controlArea)
        self.controlArea.layout().addStretch(1)

    # ------------------------------------------------------------- classes
    def _class_levels(self):
        """The class values of the input, or [] for a non-discrete class."""
        data = self._input_data
        if data is None:
            return []
        cv = data.domain.class_var
        return list(cv.values) if isinstance(cv, DiscreteVariable) else []

    def _sel_classes(self):
        """(index_a, index_b) of the compared classes, clamped to the values."""
        levels = self._class_levels()
        if len(levels) < 2:
            return None, None
        clamp = lambda i: min(max(int(i), 0), len(levels) - 1)      # noqa: E731
        return clamp(self.group_a), clamp(self.group_b)

    def _contrast_label(self):
        """'ANF vs OPP (up = ANF), ' for the plot title, or ''."""
        levels = self._class_levels()
        ia, ib = self._sel_classes()
        if ia is None or ia == ib:
            return ""
        # opls_core one-hots np.unique(y): the SMALLER code is the 'up' class
        return (f"{levels[ib]} vs {levels[ia]} "
                f"(up = {levels[min(ia, ib)]}), ")

    def _filtered_data(self, data):
        """Keep only the two compared classes.

        OPLS-DA is a two-class contrast; with more classes the pair is chosen by
        the user (MetaboAnalyst style) and everything downstream describes that
        subset. Returns None when no valid pair is selected.
        """
        ia, ib = self._sel_classes()
        if data is None or ia is None:
            return data
        if ia == ib:
            return None
        y = np.asarray(data.Y)
        codes = (y if y.ndim == 1 else y[:, 0]).astype(int)
        keep = np.isin(codes, [ia, ib])
        if keep.all():
            return data
        subset = data[keep]
        levels = self._class_levels()
        subset.name = (f"{data.name or 'data'} - {levels[ia]} vs {levels[ib]}")
        return subset

    def _update_class_combos(self):
        """(Re)fill both class combos from the input's class values."""
        levels = self._class_levels()
        for combo, name in ((self.a_combo, "group_a"), (self.b_combo, "group_b")):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(levels)
            combo.setCurrentIndex(min(max(int(getattr(self, name)), 0),
                                      max(len(levels) - 1, 0)))
            combo.blockSignals(False)
            combo.setEnabled(len(levels) >= 2)
        self._update_contrast_label()

    def _class_changed(self):
        """Refit after the user picked another class pair."""
        self._refit_for_classes()

    def _refit_for_classes(self):
        """(Re)fit on the selected class pair, right away.

        `super().set_data()` only stores the table (the signal machinery would
        update the model later), so the refit is called explicitly - otherwise a
        combo change left a stale model and a stale plot title.
        """
        subset = self._filtered_data(self._input_data)
        self.Warning.same_class.clear()
        if subset is None and self._input_data is not None:
            self.Warning.same_class()           # same class picked twice
        super().set_data(subset)
        self.update_model()
        self._update_contrast_label()

    def _update_contrast_label(self):
        """The muted line under the class combos."""
        levels = self._class_levels()
        contrast = self._contrast_label()       # "" when the pair is invalid
        if len(levels) < 2:
            self.lbl_contrast.setText("needs two classes")
        elif not contrast:
            self.lbl_contrast.setText("pick two different classes")
        else:
            self.lbl_contrast.setText("comparing " + contrast.rstrip(", "))

    def _sync_ortho_spin(self):
        """The orthogonal spinner is only meaningful without auto-optimisation."""
        if hasattr(self, "ortho_spin") and self.ortho_spin is not None:
            self.ortho_spin.setEnabled(not self.auto_ortho)

    # ------------------------------------------------------------- learner
    def create_learner(self):
        return OPLSDALearner(
            n_components=self.n_components,
            n_ortho=None if self.auto_ortho else self.n_ortho,
            auto_ortho=self.auto_ortho,
            scale=self.scale,
            cv_folds=self.cv_folds,
            n_perm=self.n_perm,
            preprocessors=self.preprocessors,
        )

    def settings_changed(self, *args, **kwargs):
        self._sync_ortho_spin()
        super().settings_changed(*args, **kwargs)

    # ------------------------------------------------------------- fitting
    def update_model(self):
        super().update_model()
        if self.model is None:
            self._clear_outputs()
            self._reset_quality_labels()
            self.plot_widget.clear()
            return

        # a new model invalidates any manual selection: fall back to thresholds
        self._manual = set()
        self._manual_mode = False
        self._create_splot_data()
        self._update_quality_labels()
        self._apply_thresholds()
        self._draw_splot()

        self.Outputs.data.send(self._create_output_data())
        self.Outputs.components.send(self._create_output_components())
        self.Outputs.splot_data.send(self._create_splot_table())
        sel = self._selected_table()
        self.Outputs.selected.send(sel)
        self.Outputs.biomarkers.send(sel)          # legacy name
        self.Outputs.selected_data.send(
            select_features(self.data, sorted(self._manual)))
        self.Outputs.feature_values.send(self._feature_values_table())

    # ------------------------------------------------------------- helpers
    def _clear_outputs(self):
        for o in (self.Outputs.data, self.Outputs.components,
                  self.Outputs.splot_data, self.Outputs.selected,
                  self.Outputs.selected_data, self.Outputs.feature_values,
                  self.Outputs.biomarkers):
            o.send(None)

    def set_data(self, data):
        """Remember the input and fit on the two compared classes.

        OWBaseLearner does not call update_model() when the input is removed, so
        the empty case is cleared here.
        """
        self._input_data = data
        self._update_class_combos()
        self._refit_for_classes()
        if data is None:
            self.splot_p = self.splot_pcorr = self.splot_vip = None
            self._relevant = None
            self._manual = set()
            self._manual_mode = False
            self.plot_widget.clear()
            self._clear_outputs()
            self._reset_quality_labels()

    def _feature_names(self):
        return [a.name for a in self.model.domain.attributes]

    def _reset_quality_labels(self):
        for lbl, txt in ((self.lbl_r2x, "R2X (cum): —"),
                         (self.lbl_r2y, "R2Y (cum): —"),
                         (self.lbl_q2, "Q2 (cum): —"),
                         (self.lbl_perm, "Permutation: —"),
                         (self.lbl_relevant, "relevant: —")):
            lbl.setText(txt)
        self.lbl_selected.setText("selected: 0")

    def _update_quality_labels(self):
        q = self.model.quality()
        f = lambda v: "—" if v is None else f"{v:.3f}"
        self.lbl_r2x.setText(f"R2X (cum): {f(q.get('r2x'))}")
        self.lbl_r2y.setText(f"R2Y (cum): {f(q.get('r2y'))}")
        self.lbl_q2.setText(f"Q2 (cum):  {f(q.get('q2'))}   "
                            f"(ortho comp.: {q.get('n_ortho')})")
        perm = getattr(self.model.core, "perm", None)
        if perm:
            pr = perm.get("p_r2y")
            self.lbl_perm.setText(
                f"Permutation: R2Y {perm['r2y_obs']:.2f} vs "
                f"{perm['r2y_perm_mean']:.2f} → p = {pr:.3f}"
                if pr is not None else "Permutation: —")
        else:
            self.lbl_perm.setText("Permutation: not computed")

    def _create_splot_data(self):
        """p1, p(corr) and VIP per feature."""
        model = self.model
        Xt = model.data_to_model_domain(self.data).X
        p1, pcorr, _t = model.plot_data(Xt)
        self.splot_p = p1
        self.splot_pcorr = pcorr
        self.splot_feature_names = self._feature_names()
        self.splot_vip = getattr(model.core, "vip", None)

    def _apply_thresholds(self):
        """Relevant = |p1| above the fraction-of-max cut AND |p(corr)| above thr."""
        if self.splot_p is None:
            self._relevant = None
            return
        p1max = float(np.max(np.abs(self.splot_p))) if len(self.splot_p) else 0.0
        cut = (self.p1_frac / 100.0) * p1max
        rel = (np.abs(self.splot_p) >= cut) & (np.abs(self.splot_pcorr) >= self.pcorr_thr)
        self._relevant = rel
        self.lbl_relevant.setText(f"relevant: {int(rel.sum())} / {len(rel)}")

    def _thresholds_changed(self):
        if self.splot_p is None:
            return
        self._apply_thresholds()
        self._draw_splot()
        self.Outputs.selected.send(self._selected_table())
        self.Outputs.biomarkers.send(self._selected_table())
        self.Outputs.selected_data.send(
            select_features(self.data, sorted(self._manual)))
        self.Outputs.feature_values.send(self._feature_values_table())

    # ------------------------------------------------------------- selection
    def _on_point_clicked(self, _scatter, points, _ev=None):
        # pyqtgraph hands `points` as a numpy array, not a list, so a plain
        # `if not points:` raises "truth value of an array is ambiguous".
        # Without a fitted model there are no S-plot features to select.
        if points is None or len(points) == 0 or not self.splot_feature_names:
            return
        mods = QApplication.keyboardModifiers()
        additive = bool(mods & Qt.ShiftModifier)
        names = list(self.splot_feature_names)
        self._manual_mode = True
        clicked = {names[int(pt.index())] for pt in points}
        if not additive:
            self._manual = set(clicked)
        else:
            for nm in clicked:
                self._manual.symmetric_difference_update({nm})
        self._refresh_selection()

    def _lasso_toggled(self):
        self.plot_widget.lasso_enabled = bool(self.lasso)

    def _lasso_select(self, polygon):
        """Add every S-plot point inside the lasso polygon to the selection."""
        if self.splot_p is None or not self.splot_feature_names:
            return
        offsets = np.column_stack([self.splot_p, self.splot_pcorr])
        idx = points_in_polygon(offsets, polygon)
        if len(idx) == 0:
            return
        self._manual_mode = True
        self._manual |= {self.splot_feature_names[i] for i in idx}
        self._refresh_selection()

    def _select_relevant(self):
        if self._relevant is None:
            return
        self._manual = {self.splot_feature_names[i]
                        for i in np.nonzero(self._relevant)[0]}
        self._manual_mode = True
        self._refresh_selection()

    def _clear_selection(self):
        self._manual = set()
        self._manual_mode = True        # keep it empty despite the thresholds
        self._refresh_selection()

    def _refresh_selection(self):
        n = len(self._manual)
        self.lbl_selected.setText(f"selected: {n}"
                                 + ("" if not n else
                                    "  (" + ", ".join(sorted(self._manual)[:4])
                                    + ("…" if n > 4 else "") + ")"))
        self._draw_splot()
        self.Outputs.selected.send(self._selected_table())
        self.Outputs.biomarkers.send(self._selected_table())
        self.Outputs.selected_data.send(
            select_features(self.data, sorted(self._manual)))
        self.Outputs.feature_values.send(self._feature_values_table())

    def _selection_indices(self):
        """Indices of the selected features: manual picks win, else the relevant set."""
        if not self.splot_feature_names:
            return np.array([], dtype=int)
        if self._manual_mode:
            names = list(self.splot_feature_names)
            return np.array([names.index(nm) for nm in sorted(self._manual)
                             if nm in names], dtype=int)
        if self._relevant is not None:
            return np.nonzero(self._relevant)[0]
        return np.array([], dtype=int)

    # ------------------------------------------------------------- drawing
    def _point_colors(self):
        n = len(self.splot_p) if self.splot_p is not None else 0
        brushes = [pg.mkBrush(*C_NS) for _ in range(n)]
        if self._relevant is not None:
            for i in np.nonzero(self._relevant)[0]:
                brushes[i] = pg.mkBrush(*(C_UP if self.splot_p[i] >= 0 else C_DOWN))
        return brushes

    def _draw_splot(self):
        self.plot_widget.clear()
        self.plot_widget.addLine(x=0, pen=pg.mkPen(180, 180, 180, 120))
        self.plot_widget.addLine(y=0, pen=pg.mkPen(180, 180, 180, 120))
        if self.splot_p is None:
            return

        brushes = self._point_colors()
        sel_idx = set(self._selection_indices().tolist())
        tips = []
        for i, nm in enumerate(self.splot_feature_names or []):
            vip = "" if self.splot_vip is None else f"<br>VIP {self.splot_vip[i]:.2f}"
            tips.append(f"{nm}<br>p1 {self.splot_p[i]:.4f}"
                        f"<br>p(corr) {self.splot_pcorr[i]:.3f}{vip}")

        self.scatter_item = pg.ScatterPlotItem(
            x=self.splot_p, y=self.splot_pcorr,
            symbol="o", size=8,
            brush=[b for b in brushes],
            pen=[pg.mkPen(C_SEL, width=1.6) if i in sel_idx else pg.mkPen(90, 96, 104, 160)
                 for i in range(len(self.splot_p))],
            data=tips, hoverable=True,
            # pyqtgraph calls opts['tip'] as a FORMATTER -> a plain string raises
            # "TypeError: 'str' object is not callable" on hover. Return the
            # per-point tooltip text we built above.
            tip=lambda x, y, data: data,
        )
        self.scatter_item.sigClicked.connect(self._on_point_clicked)
        self.plot_widget.addItem(self.scatter_item)

        # Mark the selection with a second, bigger marker on top: the per-point
        # pen above is too subtle to see on 8 px points.
        sel = np.array(sorted(sel_idx), dtype=int)
        if sel.size:
            p, pcorr = np.asarray(self.splot_p), np.asarray(self.splot_pcorr)
            self.sel_item = pg.ScatterPlotItem(
                x=p[sel], y=pcorr[sel], symbol="o", size=15,
                brush=pg.mkBrush(*C_HL), pen=pg.mkPen(20, 20, 20, 230, width=1.2),
                data=[tips[i] for i in sel], hoverable=True,
                tip=lambda x, y, data: data)
            self.sel_item.sigClicked.connect(self._on_point_clicked)
            self.plot_widget.addItem(self.sel_item)

        if self.label_top:
            if self.splot_vip is not None:
                rank = np.argsort(-self.splot_vip)
            else:
                rank = np.argsort(-np.abs(self.splot_p) * np.abs(self.splot_pcorr))
            for i in rank[:MAX_LABELS]:
                txt = pg.TextItem(text=self.splot_feature_names[i], anchor=(0.5, 1.4),
                                  color=(50, 50, 50))
                txt.setPos(self.splot_p[i], self.splot_pcorr[i])
                self.plot_widget.addItem(txt)

        n_rel = 0 if self._relevant is None else int(self._relevant.sum())
        self.plot_widget.setTitle(
            f"S-Plot — {self._contrast_label()}{n_rel} relevant, "
            f"{len(sel_idx)} selected "
            f"(grey = not relevant, red = higher, blue = lower)")

    # ------------------------------------------------------------- outputs
    def _create_output_data(self):
        """Augment the input data with OPLS scores and predictions."""
        data, model = self.data, self.model
        Xt = model.data_to_model_domain(data).X
        Xd = model._deflate(np.asarray(Xt, dtype=float))
        t_pred = Xd @ model.w_pred
        n_pred = t_pred.shape[1] if t_pred.ndim > 1 else 1

        y_raw = model._predict_raw(Xt)
        pred_class = np.argmax(y_raw, axis=1)
        e = np.exp(y_raw - y_raw.max(axis=1, keepdims=True))
        probs = e / e.sum(axis=1, keepdims=True)

        class_var = data.domain.class_var
        score_names = [f"t_pred{i + 1}" if n_pred > 1 else "t_pred"
                       for i in range(n_pred)]
        ortho_names = [f"t_o{i + 1}" for i in range(model.n_ortho)]
        # The model can cover a SUBSET of the class values (two-class contrast),
        # so the probability columns and the predicted codes must come from the
        # classes it was actually fitted on - using class_var.values raised
        # "could not broadcast input array from shape (20,2) into shape (20,4)".
        classes = np.asarray(model.classes).astype(int)
        prob_names = [f"p({class_var.name}={class_var.values[c]})" for c in classes]

        new_attrs = data.domain.attributes + tuple(
            ContinuousVariable(n) for n in score_names + ortho_names)
        new_metas = data.domain.metas + (
            DiscreteVariable("Predicted", values=class_var.values),) + tuple(
            ContinuousVariable(n) for n in prob_names)
        new_domain = Domain(new_attrs, data.domain.class_vars, new_metas)
        aug = data.transform(new_domain)

        n0 = len(data.domain.attributes)
        with aug.unlocked(aug.X):
            aug.X[:, n0:n0 + n_pred] = t_pred
            Xd2 = np.asarray(Xt, dtype=float)
            Xs = (Xd2 - model.x_mean) / model.x_std if model.scaled else Xd2 - model.x_mean
            Xdef = Xs.copy()
            for i in range(model.n_ortho):
                Xdef = Xdef - np.outer(Xdef @ model.w_ortho[i].ravel(),
                                       model.p_ortho[i].ravel())
                aug.X[:, n0 + n_pred + i] = Xdef @ model.w_ortho[i].ravel()
        with aug.unlocked(aug.metas):
            # pred_class indexes the model's columns -> map back to the class codes
            aug.metas[:, -len(prob_names) - 1] = classes[pred_class].astype(float)
            aug.metas[:, -len(prob_names):] = probs
        aug.name = f"{data.name} - OPLS-DA scores"
        return aug

    def _create_output_components(self):
        model = self.model
        n_pred = max(1, int(model.n_pred))
        # One column per predictive component: with n_components > 1, p_pred is
        # (p, n_pred), and ravel()ing it into a single column mixed 194/291
        # values into the p-row table -> "could not broadcast input array".
        names = (([f"Predictive{i + 1}" for i in range(n_pred)] if n_pred > 1
                  else ["Predictive"])
                 + [f"Ortho {i + 1}" for i in range(model.n_ortho)])
        attrs = [a.name for a in model.domain.attributes]
        dom = Domain([ContinuousVariable(n) for n in names],
                     metas=[StringVariable("Variable")])
        X = np.zeros((len(attrs), len(names)))
        P = np.asarray(model.p_pred, dtype=float).reshape(len(attrs), -1)
        X[:, :P.shape[1]] = P
        for i in range(model.n_ortho):
            X[:, P.shape[1] + i] = np.asarray(model.p_ortho[i]).ravel()
        tab = Table.from_numpy(dom, X=X,
                               metas=np.array(attrs, dtype=object).reshape(-1, 1))
        tab.name = "OPLS-DA components"
        return tab

    def _splot_domain(self, with_flag=True):
        attrs = [ContinuousVariable("p1"), ContinuousVariable("p(corr)")]
        metas = [StringVariable("Variable"), StringVariable("relevance")]
        if with_flag:
            attrs.append(ContinuousVariable("VIP"))
        return Domain(attrs, metas=metas)

    def _create_splot_table(self):
        if self.splot_p is None:
            return None
        vip = (np.zeros(len(self.splot_p)) if self.splot_vip is None
               else np.asarray(self.splot_vip, dtype=float))
        rel = np.asarray(self._relevance_labels())
        X = np.column_stack((self.splot_p, self.splot_pcorr, vip))
        metas = np.column_stack((np.array(self.splot_feature_names, dtype=object), rel))
        tab = Table.from_numpy(self._splot_domain(True), X=X, metas=metas)
        tab.name = "S-Plot data"
        return tab

    def _relevance_labels(self):
        if self.splot_p is None:
            return []
        sel = set(self._selection_indices().tolist())
        out = []
        for i in range(len(self.splot_p)):
            if i in sel:
                out.append("selected")
            elif self._relevant is not None and self._relevant[i]:
                out.append("relevant")
            else:
                out.append("ns")
        return out

    def _selected_table(self):
        idx = self._selection_indices()
        if idx.size == 0:
            return None
        vip = (np.zeros(idx.size) if self.splot_vip is None
               else np.asarray(self.splot_vip)[idx])
        X = np.column_stack((self.splot_p[idx], self.splot_pcorr[idx], vip))
        metas = np.column_stack((
            np.array(self.splot_feature_names, dtype=object)[idx],
            np.array(["selected"] * idx.size, dtype=object)))
        tab = Table.from_numpy(self._splot_domain(True), X=X, metas=metas)
        tab.name = "S-Plot selected features"
        return tab

    def _feature_values_table(self):
        """The original feature values for the selected features."""
        if self.data is None:
            return None
        idx = self._selection_indices()
        names = self.splot_feature_names or []
        if idx.size == 0:
            return None
        keep = [names[i] for i in idx if names[i] in self.data.domain]
        if not keep:
            return None
        return self.data[:, keep]


if __name__ == "__main__":  # pragma: no cover
    WidgetPreview(OWOPLSDA).run(Table("iris"))
