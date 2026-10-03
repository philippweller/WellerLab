"""PCA Weller widget - chemometrics PCA with outlier diagnostics for Orange3.

Features vs. the stock OW PCA:
- preprocessing: none / center / pareto / autoscale (unit variance)
- component selection: fixed count OR variance-fraction threshold
- explained variance (%) shown on the score-plot axes
- scores plot with class colour + point size by Q residual
- Hotelling T2 / Q-residual plot with 95% control limits
- "Remove outliers" refits the model on the inliers and re-emits everything

Plotting uses pyqtgraph directly (as in the Spectroscopy add-on).
"""

import numpy as np
import pyqtgraph as pg

from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import QApplication
from pyqtgraph import ScatterPlotItem
from Orange.data import Table, Domain, ContinuousVariable, StringVariable
from Orange.data.util import get_unique_names
from Orange.widgets import gui, widget
from Orange.widgets.settings import Setting
from Orange.widgets.utils.annotated_data import add_columns
from Orange.widgets.widget import Input, Output

from .. import pca_analysis as pa

# discrete-class colour palette (RGB tuples for pyqtgraph symbolBrush)
_CLASS_COLORS = [
    (0x1f, 0x77, 0xb4),  # blue
    (0xff, 0x7f, 0x0e),  # orange
    (0x2c, 0xa0, 0x2c),  # green
    (0xd6, 0x27, 0x28),  # red
    (0x94, 0x67, 0xbd),  # purple
    (0x8c, 0x56, 0x4b),  # brown
    (0xe3, 0x77, 0xc2),  # pink
    (0x7f, 0x7f, 0x7f),  # grey
    (0xbc, 0xbd, 0x22),  # olive
    (0x17, 0xbe, 0xcf),  # teal
]


def _class_color(i):
    return _CLASS_COLORS[i % len(_CLASS_COLORS)]


class OWPCAWell(widget.OWWidget):
    name = "PCA Weller"
    description = ("Chemometrics PCA with scaling, explained variance on axes "
                   "and Hotelling T2/Q-residual outlier diagnostics.")
    icon = "icons/PCAWell.svg"
    priority = 3120
    keywords = "pca, t2, hotelling, q residual, outlier, chemometrics, autoscale, kaiser"

    # comp_method index: 0 = kaiser, 1 = frac, 2 = count
    COMP_METHODS = ("kaiser", "frac", "count")
    COMP_METHOD_LABELS = ("Kaiser criterion (automatic)",
                          "Explained variance fraction",
                          "Fixed number")

    # scale index: 0 = auto, 1 = pareto, 2 = center, 3 = none
    SCALES = ("auto", "pareto", "center", "none")
    SCALE_LABELS = ("Autoscale (unit variance)", "Pareto", "Center only", "None")

    class Inputs:
        data = Input("Data", Table)

    class Outputs:
        transformed_data = Output("Transformed Data", Table)
        data = Output("Data", Table, default=True)
        components = Output("Components (loadings)", Table)
        scores = Output("Scores", Table)
        outliers = Output("Outliers", Table)
        inliers = Output("Inliers", Table)

    # settings
    scale = Setting(0)             # index into SCALES: 0=auto,1=pareto,2=center,3=none
    comp_method = Setting(1)           # index into COMP_METHODS: 0=kaiser,1=frac,2=count
    n_components = Setting(2)              # used when comp_method == 2 (count)
    variance_frac = Setting(0.80)          # used when comp_method == 1 (frac)
    alpha = Setting(0.05)
    use_T2 = Setting(True)
    use_Q = Setting(True)
    auto_commit = Setting(True)
    point_size = Setting(6)
    color_by_class = Setting(True)
    size_by_Q = Setting(True)

    graph_name = "scores_plot"

    def __init__(self):
        super().__init__()
        self.data = None
        self.analytics = None          # pa.PCAOutliers
        self._scores = None
        self._loadings = None
        self._selected = set()         # row indices selected in the plots
        self._scatter_items = []       # ScatterPlotItem + their row indices

        # --- control area: preprocessing -------------------------------
        box = gui.widgetBox(self.controlArea, "Preprocessing")
        gui.comboBox(
            box, self, "scale", items=self.SCALE_LABELS,
            label="Scaling:", callback=self._param_changed,
            orientation=Qt.Horizontal)
        gui.checkBox(box, self, "color_by_class", "Colour scores by class",
                     callback=self._replot, attribute=Qt.WA_LayoutUsesWidgetRect)
        gui.checkBox(box, self, "size_by_Q", "Size points by Q residual",
                     callback=self._replot, attribute=Qt.WA_LayoutUsesWidgetRect)

        # --- components ------------------------------------------------
        cbox = gui.widgetBox(self.controlArea, "Components")
        gui.comboBox(
            cbox, self, "comp_method", items=self.COMP_METHOD_LABELS,
            label="Method:", callback=self._param_changed,
            orientation=Qt.Horizontal)
        self.frac_spin = gui.doubleSpin(
            cbox, self, "variance_frac", 0.05, 1.0, 0.05,
            label="Variance:", callback=self._param_changed, decimals=2)
        self.count_spin = gui.spin(
            cbox, self, "n_components", 1, 100,
            label="Components:", callback=self._param_changed)
        gui.hSlider(cbox, self, "point_size", label="Point size:",
                    minValue=2, maxValue=16, callback=self._replot)

        # --- outlier diagnostics ---------------------------------------
        obox = gui.widgetBox(self.controlArea, "Outlier diagnostics")
        gui.doubleSpin(obox, self, "alpha", 0.001, 0.50, 0.005,
                       label="Significance (alpha):", callback=self._recalc_limits,
                       decimals=3)
        gui.checkBox(obox, self, "use_T2", "Use Hotelling T2 limit",
                     callback=self._recalc_limits, attribute=Qt.WA_LayoutUsesWidgetRect)
        gui.checkBox(obox, self, "use_Q", "Use Q-residual limit",
                     callback=self._recalc_limits, attribute=Qt.WA_LayoutUsesWidgetRect)
        b = gui.button(obox, self, "Remove outliers & refit",
                       callback=self._remove_outliers)
        b.setEnabled(False)
        self._remove_button = b
        self.remove_selected_button = gui.button(
            obox, self, "Remove selected point(s)",
            callback=self._remove_selected)
        self.remove_selected_button.setEnabled(False)
        self.clear_selection_button = gui.button(
            obox, self, "Clear selection",
            callback=self._clear_selection)

        # --- reset to defaults ------------------------------------------
        rbox = gui.widgetBox(self.controlArea, "Defaults")
        self.reset_button = gui.button(
            rbox, self, "Reset all to defaults",
            callback=self._reset_defaults)

        gui.rubber(self.controlArea)
        gui.auto_apply(self.buttonsArea, self, "auto_commit")

        # --- main area: two plots --------------------------------------
        self.scores_plot = pg.PlotWidget(background="w")
        self.scores_plot.setLabel("bottom", "PC1")
        self.scores_plot.setLabel("left", "PC2")
        self.t2q_plot = pg.PlotWidget(background="w")
        self.t2q_plot.setLabel("bottom", "Hotelling T2")
        self.t2q_plot.setLabel("left", "Q residual")

        tbox = gui.vBox(self.mainArea, "Scores")
        tbox.layout().addWidget(self.scores_plot)
        qbox = gui.vBox(self.mainArea, "T2 vs Q residual")
        qbox.layout().addWidget(self.t2q_plot)

        self._recalc_enabled_controls()

    # ------------------------------------------------------------------ signals
    @Inputs.data
    def set_data(self, data):
        self.data = data
        self._selected.clear()
        self._scatter_items = []
        self._update_selection_buttons()
        self.clear_messages()
        if data is None or not len(data):
            self.analytics = None
            self._scores = self._loadings = None
            self._clear_outputs()
            return
        self.Error.clear()
        if not data.domain.attributes:
            self.Error.no_features()
            self._clear_outputs()
            return
        self._fit()

    # ------------------------------------------------------------------ fitting
    def _param_changed(self):
        self._recalc_enabled_controls()
        self._fit()

    def _comp_method_name(self):
        """Current method key: 'kaiser' | 'frac' | 'count'."""
        i = self.comp_method
        if not (0 <= i < len(self.COMP_METHODS)):
            i = 1
        return self.COMP_METHODS[i]

    def _scale_name(self):
        """Current scaling key: 'auto' | 'pareto' | 'center' | 'none'."""
        i = self.scale
        if not (0 <= i < len(self.SCALES)):
            i = 0
        return self.SCALES[i]

    def _recalc_enabled_controls(self):
        m = self._comp_method_name()
        is_count = m == "count"
        is_frac = m == "frac"
        for spin, enable in ((self.count_spin, is_count),
                             (self.frac_spin, is_frac)):
            try:
                spin.setEnabled(enable)
            except Exception:
                pass

    def _resolved_n(self):
        m = self._comp_method_name()
        if m == "count":
            return int(self.n_components)
        if m == "kaiser":
            return "kaiser"
        return float(self.variance_frac)

    def _fit(self):
        if self.data is None:
            return
        X = self.data.X.copy()
        try:
            self.analytics = pa.PCAOutliers(
                X, scale=self._scale_name(), n_components=self._resolved_n(),
                alpha=self.alpha)
        except Exception as exc:  # pragma: no cover
            self.Error.fit_failed(str(exc))
            self.analytics = None
            self._scores = self._loadings = None
            self._remove_button.setEnabled(False)
            self._clear_outputs()
            return
        self.Error.clear()
        r = self.analytics.result
        self._scores = r["scores"]
        self._loadings = r["loadings"]
        self._remove_button.setEnabled(True)
        self._replot()
        self._replot_t2q()
        self.commit.now() if self.auto_commit else self.commit.deferred()

    def _recalc_limits(self):
        if self.analytics is None:
            return
        self.analytics.update_stats()
        self._replot_t2q()
        if self.auto_commit:
            self.commit.now()
        else:
            self.commit.deferred()

    def _replot(self):
        self._render_scores()

    def _replot_t2q(self):
        self._render_t2q()

    def _remove_outliers(self):
        if self.analytics is None:
            return
        mask = self.analytics.inlier_mask(use_T2=self.use_T2, use_Q=self.use_Q)
        keep = self.data[mask]
        if len(keep) == len(self.data):
            self.information("No outliers beyond the limits; nothing removed.")
            return
        n_removed = int((~mask).sum())
        self.data = keep
        self._fit()
        self.information(f"Removed {n_removed} outlier(s); model refit on {len(keep)} samples.")

    def _reset_defaults(self):
        """Reset every Setting to its class default and recompute."""
        if self.data is None:
            return
        for name in self._all_setting_names():
            default = getattr(type(self), name)
            if isinstance(default, Setting):
                setattr(self, name, default.default)
        self._recalc_enabled_controls()
        self._fit()
        self.information("All settings reset to defaults.")

    def _all_setting_names(self):
        """Names of the Setting attributes defined on this widget."""
        names = []
        import inspect
        for cls in type(self).__mro__:
            for name, val in vars(cls).items():
                if isinstance(val, Setting) and name not in names:
                    names.append(name)
        return names

    # ------------------------------------------------------------------ rendering
    def _variance_label(self, k):
        """Percent explained variance for component k (1-indexed season)."""
        r = self.analytics.result
        ratio = r["explained_variance_ratio"]
        if k <= len(ratio):
            return f"PC{k} ({100 * ratio[k - 1]:.1f}%)"
        return f"PC{k}"

    def _add_interactive_scatter(self, plot, x, y, rows, color=None, size=None):
        """Add a clickable ScatterPlotItem to `plot`; each point carries its
        row index in `data` so clicks map back to the sample row."""
        rows = np.asarray(rows)
        scatter = ScatterPlotItem()
        sz = size if size is not None else self.point_size
        scatter.setData(
            x=x, y=y, size=sz, data=rows,
            pen=pg.mkPen(None), symbol="o", brush=color or (0, 0, 0))
        scatter.sigClicked.connect(lambda item, points: self._on_point_click(item, points))
        self._scatter_items.append((scatter, rows))
        plot.addItem(scatter)

    def _on_point_click(self, item, points):
        """Toggle selection of clicked point(s). Modifier = keyboard state is
        read via QApplication; default selects the clicked point."""
        for pt in points:
            idx = pt.data()
            self._select_index(idx)
        self._replot()
        self._replot_t2q()

    def _select_index(self, idx):
        """Select a single row index (toggle with Ctrl/Cmd, else set-only)."""
        mods = QApplication.keyboardModifiers()
        if mods & (Qt.ControlModifier | Qt.MetaModifier):
            if idx in self._selected:
                self._selected.discard(idx)
            else:
                self._selected.add(idx)
        else:
            self._selected = {idx}
        self._update_selection_buttons()

    def _selected_rows(self):
        """All selected row indices, filtered to valid range."""
        n = len(self.data) if self.data is not None else 0
        return sorted(i for i in self._selected if 0 <= i < n)

    def _clear_selection(self):
        self._selected.clear()
        self._update_selection_buttons()
        self._replot()
        self._replot_t2q()

    def _remove_selected(self):
        """Remove the manually selected point(s) and refit the model."""
        sel = self._selected_rows()
        if not sel or self.data is None:
            return
        keep_mask = np.ones(len(self.data), dtype=bool)
        keep_mask[sel] = False
        self.data = self.data[keep_mask]
        self._selected.clear()
        self._update_selection_buttons()
        self._fit()
        self.information(f"Removed {len(sel)} selected point(s); model refit on "
                         f"{len(self.data)} samples.")

    def _update_selection_buttons(self):
        has = len(self._selected) > 0
        try:
            self.remove_selected_button.setEnabled(has)
        except Exception:
            pass

    def _render_scores(self):
        self.scores_plot.clear()
        r = self.analytics.result
        s = self._scores
        if s is None or s.shape[1] < 1:
            return
        self.scores_plot.setLabel("bottom", self._variance_label(1))
        self.scores_plot.setLabel("left", self._variance_label(2))
        x = s[:, 0]
        y = s[:, 1] if s.shape[1] > 1 else np.zeros_like(x)
        rows = np.arange(len(x))

        base_size = self.point_size
        if self.size_by_Q:
            q = self.analytics.Q
            qn = (q - q.min()) / (q.max() - q.min() + 1e-12)
            base_size = 3 + 13 * qn

        # class-coloured scatter (or single colour) keeping per-index mapping
        if self.color_by_class and self.data.domain.has_discrete_class:
            yv = self.data.Y.astype(int)
            for i_class in np.unique(yv):
                m = yv == i_class
                if m.any():
                    rge = np.where(m)[0]
                    self._add_interactive_scatter(
                        self.scores_plot, x[m], y[m], rge,
                        color=_class_color(int(i_class)),
                        size=base_size[m])
        else:
            self._add_interactive_scatter(self.scores_plot, x, y, rows)

        # highlight selection on top
        sel = self._selected_rows()
        if sel:
            sel_arr = np.asarray(sel)
            self._add_interactive_scatter(
                self.scores_plot, x[sel_arr], y[sel_arr], sel_arr,
                color=(255, 20, 35, 200),
                size=np.full(len(sel), max(base_size) + 3))

    def _render_t2q(self):
        self.t2q_plot.clear()
        if self.analytics is None:
            return
        T2 = self.analytics.T2
        Q = self.analytics.Q
        t2l = self.analytics.T2_lim
        ql = self.analytics.Q_lim
        rows = np.arange(len(T2))
        self._add_interactive_scatter(self.t2q_plot, T2, Q, rows,
                                      color=(0, 0, 0))
        # highlight selection
        sel = self._selected_rows()
        if sel:
            sel_arr = np.asarray(sel)
            self._add_interactive_scatter(
                self.t2q_plot, T2[sel_arr], Q[sel_arr], sel_arr,
                color=(255, 20, 35, 200), size=self.point_size + 3)
        # control limits
        if np.isfinite(t2l):
            self.t2q_plot.plot([t2l, t2l], [0, Q.max() + Q.std() + 1e-9],
                               pen=pg.mkPen("r", width=2))
        if np.isfinite(ql):
            self.t2q_plot.plot([0, T2.max() + T2.std() + 1e-9], [ql, ql],
                               pen=pg.mkPen("r", width=2))

    # ------------------------------------------------------------------ outputs
    @gui.deferred
    def commit(self):
        transformed = data = components = scores = outliers = inliers = None
        if self.analytics is not None and self.data is not None:
            r = self.analytics.result
            c = r["n_components"]
            ratio = r["explained_variance_ratio"][:c]

            # transformed data (first c components), with variance attributes
            dom_attr = [ContinuousVariable(f"PC{i + 1}") for i in range(c)]
            for var, expl in zip(dom_attr, ratio):
                var.attributes["variance"] = round(float(expl), 6)
            src_metas = self.data.domain.metas if self.data.domain.metas else []
            transformed = Table(
                Domain(dom_attr, self.data.domain.class_vars, src_metas),
                self._scores[:, :c],
                self.data.Y if self.data.domain.has_discrete_class else None,
                metas=self.data.metas if src_metas else None)

            # components (loadings): rows = components (c), cols = features (p)
            proposed = [a.name for a in self.data.domain.attributes]
            comp_dom = Domain(
                [ContinuousVariable(name) for name in proposed],
                metas=[StringVariable("component")])
            comp_meta = np.array([[f"PC{i + 1}"] for i in range(c)], dtype=object)
            components = Table(comp_dom, self._loadings[:, :c].T, metas=comp_meta)
            components.name = "components"

            # scores as a stand-alone table (with T2 & Q metas)
            T2 = self.analytics.T2[:, None]
            Q = self.analytics.Q[:, None]
            q_name = get_unique_names(proposed, "Q_residual")
            t2_name = get_unique_names(proposed, "T2")
            meta_vars = [ContinuousVariable(t2_name), ContinuousVariable(q_name)]
            metas = np.hstack([T2, Q])
            scores = Table(
                Domain(dom_attr, self.data.domain.class_vars, meta_vars),
                self._scores[:, :c],
                self.data.Y if self.data.domain.has_discrete_class else None,
                metas=metas)
            scores.name = "scores"

            # full data table with T2/Q columns appended (as metas)
            add = [ContinuousVariable(t2_name), ContinuousVariable(q_name)]
            new_dom = add_columns(self.data.domain, metas=add)
            data = self.data.transform(new_dom)
            with data.unlocked(data.metas):
                data.metas[:, -2] = T2.ravel()
                data.metas[:, -1] = Q.ravel()

            # inlier / outlier subsets
            mask = self.analytics.inlier_mask(use_T2=self.use_T2, use_Q=self.use_Q)
            inliers = self.data[mask]
            outliers = self.data[~mask]
            if len(outliers) == 0:
                outliers = None

        self.Outputs.transformed_data.send(transformed)
        self.Outputs.data.send(data)
        self.Outputs.components.send(components)
        self.Outputs.scores.send(scores)
        self.Outputs.outliers.send(outliers)
        self.Outputs.inliers.send(inliers)

    def _clear_outputs(self):
        for name in ("transformed_data", "data", "components",
                     "scores", "outliers", "inliers"):
            getattr(self.Outputs, name).send(None)

    # ------------------------------------------------------------------ error reporting
    class Error(widget.OWWidget.Error):
        no_features = widget.Msg("At least one feature is required.")
        fit_failed = widget.Msg("PCA fit failed: {}")

    class Warning(widget.OWWidget.Warning):
        trivial = widget.Msg("All components are trivial (constant data).")

    def send_report(self):
        if self.data is None or self.analytics is None:
            return
        r = self.analytics.result
        self.report_items((
            ("Preprocessing", self._scale_name()),
            ("Component method", self._comp_method_name()),
            ("Components", r["n_components"]),
            ("Explained variance", f"{100 * r['cumulative'][-1]:.1f}%"),
            ("T2 limit", f"{self.analytics.T2_lim:.3f}"),
            ("Q limit", f"{self.analytics.Q_lim:.3f}"),
        ))
        self.report_plot(self.scores_plot)
        self.report_plot(self.t2q_plot)

    @classmethod
    def migrate_settings(cls, settings, version):
        # scale was originally a string ('auto'/'pareto'/'center'/'none');
        # now an index into SCALES. Convert old string -> index.
        sc = settings.get("scale")
        if isinstance(sc, str):
            try:
                settings["scale"] = cls.SCALES.index(sc)
            except ValueError:
                settings["scale"] = 0  # fallback to auto
        # comp_method was originally a string ('kaiser'/'frac'/'count');
        # now an index into COMP_METHODS. Convert old string -> index.
        cm = settings.get("comp_method")
        if isinstance(cm, str):
            try:
                settings["comp_method"] = cls.COMP_METHODS.index(cm)
            except ValueError:
                settings["comp_method"] = 1  # fallback to frac


if __name__ == "__main__":  # pragma: no cover
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    from Orange.data import Table
    WidgetPreview(OWPCAWell).run(Table("iris"))