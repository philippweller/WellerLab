"""Biplot widget: scores and loadings in one plot, features selectable.

Works with PCA Pro, PLS-DA and OPLS-DA: connect the scores (PC1.., Comp 1..,
t_pred..) and the loadings ("Components (loadings)" / "Components") of either
model, plus the (preprocessed) data table. Samples are drawn as points, every
feature as an arrow, and the arrows can be selected the same way as in the Volcano
or the S-plot: click, shift-click or lasso - the selection leaves through
"Selected Data" for a Data Table, a heat map or a Volcano.

The loadings orientation differs between the widgets (PCA Pro writes components as
rows, PLS-DA/OPLS-DA write features as rows), so it is detected by looking for the
data's feature names in the loadings table.
"""
import numpy as np

from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import QApplication

from Orange.data import Table, Domain, ContinuousVariable, StringVariable
from Orange.widgets import gui, widget
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output, Msg

from ...plotcanvas import PlotCanvas, attach_toolbar, draggable
from ...selection import points_in_polygon, select_features

#: point colours per class (fixed list, like the other widgets in the suite)
CLASS_COLORS = ("#1f77b4", "#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
                "#8c564b", "#17becf", "#e377c2")
C_ARROW = "#5b6472"
C_SEL = "#ff9100"


def read_loadings(table, data=None):
    """(component names, feature names, P) with P of shape (n_features, n_comp).

    The orientation is detected: wipe the feature names of `data` against the
    loadings table's attributes (features as columns, PCA Pro) and its string meta
    column (features as rows, PLS-DA / OPLS-DA).
    """
    if table is None:
        return [], [], None
    X = np.asarray(table.X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(1, -1)
    attrs = [a.name for a in table.domain.attributes]
    meta_names = None
    for i, meta in enumerate(table.domain.metas):
        if meta.is_string:
            meta_names = [str(v) for v in table.metas[:, i]]
            break
    known = {a.name for a in data.domain.attributes} if data is not None else set()

    if known and set(attrs) & known:
        # features in the columns -> components are the rows
        return ([f"Comp {i + 1}" for i in range(X.shape[0])], attrs, X.T)
    if meta_names is not None and len(meta_names) == X.shape[0]:
        components = attrs
        return (components, meta_names, X)
    # last resort: assume features in the rows and name the components by position
    return ([f"Comp {i + 1}" for i in range(X.shape[1])],
            [f"feature {i}" for i in range(X.shape[0])], X)


class OWBiplot(widget.OWWidget):
    name = "Biplot"
    description = ("Scores and loadings in one plot (PCA Pro, PLS-DA, OPLS-DA) "
                   "with click / shift-click / lasso selection of the features.")
    icon = "icons/Biplot.svg"
    priority = 90
    keywords = ["biplot", "scores", "loadings", "pca", "pls", "opls", "ordination",
                "chemometrics", "selection", "metabolomics"]

    class Inputs:
        data = Input("Data", Table)
        scores = Input("Scores", Table)
        loadings = Input("Loadings", Table)

    class Outputs:
        selected_data = Output("Selected Data", Table, default=True)
        selected = Output("Selected Features", Table, explicit=True)

    class Information(widget.OWWidget.Information):
        marked = Msg("{} feature(s) selected: {}")

    class Warning(widget.OWWidget.Warning):
        no_loadings = Msg("Connect the loadings of PCA Pro, PLS-DA or OPLS-DA.")
        no_scores = Msg("Connect the scores (PC1.., Comp 1.., t_pred..).")
        one_component = Msg("At least two components are needed for a biplot.")
        empty = Msg("No features to draw.")

    # ------------------------------------------------------------- settings
    comp_x = Setting(0)
    comp_y = Setting(1)
    max_arrows = Setting(15)
    label_top = Setting(True)
    arrow_scale = Setting(0.8)
    color_by_class = Setting(True)
    lasso = Setting(False)

    want_main_area = True
    resizing_enabled = True

    def __init__(self):
        super().__init__()
        self.data = None               # the (preprocessed) feature table
        self.scores = None             # samples x components
        self.loadings = None           # components x features, or the transpose
        self._scores = None
        self._score_names = []
        self._classes = None
        self._feat_names = []
        self._P = None                 # (n_features, n_components)
        self._selected = []            # selected feature names
        self._cell = None              # last clicked sample (row, name)
        self._ax_plot = None

        cbox = gui.vBox(self.controlArea, "Components")
        self.x_combo = gui.comboBox(cbox, self, "comp_x", items=[],
                                    label="x axis: ", orientation=Qt.Horizontal,
                                    callback=self._redraw)
        self.y_combo = gui.comboBox(cbox, self, "comp_y", items=[],
                                    label="y axis: ", orientation=Qt.Horizontal,
                                    callback=self._redraw)

        abox = gui.vBox(self.controlArea, "Arrows")
        gui.spin(abox, self, "max_arrows", 1, 200, 1, label="Show top features: ",
                 callback=self._redraw)
        gui.checkBox(abox, self, "label_top", "Label them",
                     callback=self._redraw)
        gui.doubleSpin(abox, self, "arrow_scale", 0.1, 3.0, 0.1,
                       label="Arrow scale: ", decimals=1, callback=self._redraw)
        gui.checkBox(abox, self, "color_by_class", "Colour samples by class",
                     callback=self._redraw)

        sbox = gui.vBox(self.controlArea, "Selection")
        gui.checkBox(sbox, self, "lasso", "Lasso select (drag in the plot)",
                     callback=self._lasso_toggled,
                     tooltip="Left-drag draws a polygon; every feature arrow "
                             "ending inside is added to the selection.")
        gui.button(sbox, self, "Clear selection", callback=self._clear_selection)
        self.lbl_selected = gui.label(sbox, self, "no feature selected")

        gui.rubber(self.controlArea)

        box = gui.vBox(self.mainArea, "Biplot")
        self.canvas = PlotCanvas((9, 6))
        self.canvas.on_click = self._on_click
        box.layout().addWidget(self.canvas)
        attach_toolbar(box, self.canvas, self)
        row = gui.hBox(box)
        gui.button(row, self, "Reset view", callback=self.canvas.reset_view)
        gui.button(row, self, "Export PNG…", callback=self._export_png)

    # ------------------------------------------------------------- inputs
    @Inputs.data
    def set_data(self, data):
        self.data = data
        self._redraw()

    @Inputs.scores
    def set_scores(self, scores):
        self.scores = scores
        self._redraw()

    @Inputs.loadings
    def set_loadings(self, loadings):
        self.loadings = loadings
        self._redraw()

    # ------------------------------------------------------------- drawing
    def _redraw(self):
        self.Information.clear()
        self.Warning.clear()
        self._scores = None
        self._feat_names, self._P = [], None

        if self.data is None or self.scores is None or self.loadings is None:
            missing = (self.Warning.no_scores if self.scores is None
                       else self.Warning.no_loadings)
            missing()
            self._draw_message("Connect Data, Scores and Loadings.")
            self._send_outputs()
            return

        score_attr = [a for a in self.scores.domain.attributes]
        self._score_names = [a.name for a in score_attr]
        if len(score_attr) < 2:
            self.Warning.one_component()
            self._draw_message("The biplot needs two components.")
            self._send_outputs()
            return

        components, self._feat_names, self._P = read_loadings(self.loadings, self.data)
        known = {a.name for a in self.data.domain.attributes}
        keep = [i for i, n in enumerate(self._feat_names) if n in known]
        if not keep:
            self.Warning.empty()
            self._draw_message("None of the loadings match the data's features.")
            self._send_outputs()
            return
        self._P = self._P[keep]
        self._feat_names = [self._feat_names[i] for i in keep]
        self._components = components
        self._scores = np.asarray(self.scores.X, dtype=float)

        for combo, setting in ((self.x_combo, "comp_x"), (self.y_combo, "comp_y")):
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(self._score_names)
            combo.setCurrentIndex(min(int(getattr(self, setting)),
                                      len(self._score_names) - 1))
            combo.blockSignals(False)
        ix = min(int(self.comp_x), len(self._score_names) - 1)
        iy = min(int(self.comp_y), len(self._score_names) - 1)
        if ix == iy:
            iy = 0 if ix != 0 else 1
        self.comp_x, self.comp_y = ix, iy

        # Class colours must line up with the SCORES rows: OPLS-DA/PLS-DA emit a
        # subset (the compared classes), so the data table can be longer than the
        # scores. Prefer the row-aligned source, fall back only if lengths match.
        self._classes = None
        if self.color_by_class:
            for table in (self.scores, self.data):
                if table is None or table.domain.class_var is None:
                    continue
                cv = table.domain.class_var
                if len(cv.values) and len(table) == len(self._scores):
                    codes = np.asarray(table.Y).ravel().astype(int)
                    self._classes = np.array([cv.values[c] for c in codes],
                                             dtype=object)
                    break

        self._draw_biplot(ix, iy)
        self._update_selection_label()
        self._send_outputs()

    def _draw_message(self, text):
        fig = self.canvas.fig
        fig.clear()
        ax = fig.add_subplot(111)
        ax.text(0.5, 0.5, text, ha="center", va="center", fontsize=10,
                color="#6b7684")
        ax.axis("off")
        self._ax_plot = None
        self.canvas.after_draw(ax, new_data=True)
        self.canvas.draw_idle()

    def _draw_biplot(self, ix, iy):
        fig = self.canvas.fig
        fig.clear()
        ax = fig.add_subplot(111)
        self._ax_plot = ax

        x = self._scores[:, ix]
        y = self._scores[:, iy]
        if self._classes is None:
            ax.scatter(x, y, s=34, c="#4a5568", edgecolors="white", linewidths=0.6,
                       zorder=3)
        else:
            for colour, label in zip(CLASS_COLORS,
                                     dict.fromkeys(self._classes.tolist())):
                mask = self._classes == label
                ax.scatter(x[mask], y[mask], s=34, c=colour, edgecolors="white",
                           linewidths=0.6, label=str(label), zorder=3)
            legend = ax.legend(fontsize=7, loc="best")
            draggable(legend)

        # arrows: the strongest features, scaled so they sit inside the score cloud
        strength = np.linalg.norm(self._P[:, [ix, iy]], axis=1)
        order = np.argsort(-np.abs(strength))[:max(1, int(self.max_arrows))]
        span = max(float(np.abs(x).max()), float(np.abs(y).max()), 1e-12)
        loading_span = max(float(np.abs(self._P).max()), 1e-12)
        scale = float(self.arrow_scale) * span / loading_span
        selected = set(self._selected)
        labels = []
        for i in order:
            px, py = self._P[i, ix] * scale, self._P[i, iy] * scale
            chosen = self._feat_names[i] in selected
            ax.annotate("", xy=(px, py), xytext=(0, 0),
                        arrowprops=dict(arrowstyle="-|>", color=C_SEL if chosen
                                       else C_ARROW,
                                        lw=2.0 if chosen else 1.0,
                                        alpha=0.95 if chosen else 0.8),
                        zorder=4 if chosen else 2)
            if self.label_top:
                labels.append((px, py, self._feat_names[i], chosen))
        for px, py, name, chosen in labels:
            ax.text(px * 1.03, py * 1.03, name[:26], fontsize=6.5,
                    color=C_SEL if chosen else "#394150",
                    fontweight="bold" if chosen else "normal", zorder=5,
                    ha="left" if px >= 0 else "right")

        ax.axhline(0, color="#c9ced6", lw=0.8, zorder=1)
        ax.axvline(0, color="#c9ced6", lw=0.8, zorder=1)
        ax.set_xlabel(self._axis_label(self.scores.domain.attributes[ix]), fontsize=8)
        ax.set_ylabel(self._axis_label(self.scores.domain.attributes[iy]), fontsize=8)
        ax.set_title("Biplot - samples (points) and features (arrows)", fontsize=10)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.25)
        if self._cell is not None:
            row, name = self._cell
            ax.scatter([x[row]], [y[row]], s=90, facecolors="none",
                       edgecolors="#111111", linewidths=1.4, zorder=6)
        fig.tight_layout()
        self.canvas.after_draw(ax, new_data=True)
        self.canvas.draw_idle()

    @staticmethod
    def _axis_label(variable):
        parts = [variable.name]
        variance = (variable.attributes or {}).get("variance")
        if variance is not None:
            try:
                parts.append(f"({float(variance) * 100:.1f}%)")
            except (TypeError, ValueError):
                pass
        return " ".join(parts)

    # ------------------------------------------------------------- selection
    def _lasso_toggled(self):
        self.canvas.lasso_enabled = bool(self.lasso)
        self.canvas.on_lasso = self._lasso_select if self.lasso else None

    def _arrow_tips(self):
        """Arrow tip positions in data coordinates (what the user clicks)."""
        ix, iy = self.comp_x, self.comp_y
        span = max(float(np.abs(self._scores[:, [ix, iy]]).max()), 1e-12)
        loading_span = max(float(np.abs(self._P).max()), 1e-12)
        scale = float(self.arrow_scale) * span / loading_span
        return self._P[:, [ix, iy]] * scale

    def _nearest_arrow(self, x, y):
        tips = self._arrow_tips()
        if tips.size == 0:
            return None
        # only the drawn arrows can be picked
        strength = np.linalg.norm(tips, axis=1)
        order = np.argsort(-strength)[:max(1, int(self.max_arrows))]
        distance = np.hypot(tips[order, 0] - x, tips[order, 1] - y)
        best = order[int(np.argmin(distance))]
        xl, yl = self._ax_plot.get_xlim(), self._ax_plot.get_ylim()
        # within ~4 % of the visible span counts as a hit
        if distance.min() > 0.04 * max(abs(xl[1] - xl[0]), abs(yl[1] - yl[0])):
            return None
        return self._feat_names[best]

    def _on_click(self, ax, xdata, ydata):
        if ax is not self._ax_plot or self._P is None:
            return
        feature = self._nearest_arrow(xdata, ydata)
        if feature is None:
            # a click away from every arrow: pick a sample for its info
            self._select_sample(xdata, ydata)
            return
        if QApplication.keyboardModifiers() & Qt.ShiftModifier:
            self._selected = ([f for f in self._selected if f != feature]
                              if feature in self._selected
                              else self._selected + [feature])
        else:
            self._selected = [] if self._selected == [feature] else [feature]
        self._redraw()

    def _select_sample(self, xdata, ydata):
        """A click on the score cloud marks that sample (info only)."""
        x, y = self._scores[:, self.comp_x], self._scores[:, self.comp_y]
        distance = np.hypot(x - xdata, y - ydata)
        row = int(np.argmin(distance))
        xl, yl = self._ax_plot.get_xlim(), self._ax_plot.get_ylim()
        if distance.min() > 0.04 * max(abs(xl[1] - xl[0]), abs(yl[1] - yl[0])):
            self._cell = None
            self._selected = []
        else:
            self._cell = (row, self._row_label(row))
        self._redraw()

    def _row_label(self, row):
        """The sample name of a score row, from whichever table lines up."""
        for table in (self.scores, self.data):
            if table is None or len(table) != len(self._scores):
                continue
            for i, meta in enumerate(table.domain.metas):
                if meta.name == "sample" and meta.is_string:
                    return str(table.metas[row, i])
        return f"row {row}"

    def _lasso_select(self, ax, polygon):
        if ax is not self._ax_plot or self._P is None:
            return
        tips = self._arrow_tips()
        strength = np.linalg.norm(tips, axis=1)
        order = np.argsort(-strength)[:max(1, int(self.max_arrows))]
        inside = points_in_polygon(tips[order], polygon)
        if len(inside) == 0:
            return
        picked = [self._feat_names[order[i]] for i in inside]
        self._selected = list(dict.fromkeys(self._selected + picked))
        self._redraw()

    def _clear_selection(self):
        self._selected = []
        self._cell = None
        self._redraw()

    def _update_selection_label(self):
        if not self._selected:
            self.lbl_selected.setText("no feature selected")
            return
        shown = ", ".join(f[:18] for f in self._selected[:3])
        more = "…" if len(self._selected) > 3 else ""
        self.lbl_selected.setText(f"<b>{len(self._selected)}</b>: {shown}{more}")
        self.Information.marked(len(self._selected), shown + more)

    # ------------------------------------------------------------- outputs
    def _send_outputs(self):
        self.Outputs.selected_data.send(select_features(self.data, self._selected))
        self.Outputs.selected.send(self._selected_table())

    def _selected_table(self):
        """(feature, loading x, loading y, contribution) for the selection."""
        if not self._selected or self._P is None:
            return None
        ix, iy = self.comp_x, self.comp_y
        index = {name: i for i, name in enumerate(self._feat_names)}
        rows, names = [], []
        for feature in self._selected:
            i = index.get(feature)
            if i is None:
                continue
            rows.append([self._P[i, ix], self._P[i, iy],
                         float(np.linalg.norm(self._P[i, [ix, iy]]))])
            names.append([feature])
        if not rows:
            return None
        dom = Domain([ContinuousVariable(f"loading ({self._score_names[ix]})"),
                      ContinuousVariable(f"loading ({self._score_names[iy]})"),
                      ContinuousVariable("contribution")],
                     metas=[StringVariable("Feature")])
        table = Table.from_numpy(dom, X=np.asarray(rows, dtype=float),
                                 metas=np.asarray(names, dtype=object))
        table.name = "Biplot selection"
        return table

    def _export_png(self):
        from AnyQt.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(self, "Export PNG", "biplot.png",
                                              "PNG (*.png)")
        if path:
            self.canvas.fig.savefig(path, dpi=200, bbox_inches="tight")


if __name__ == "__main__":                       # pragma: no cover
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWBiplot).run()
