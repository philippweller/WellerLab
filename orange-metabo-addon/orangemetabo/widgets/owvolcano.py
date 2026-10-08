"""Metabo Volcano — volcano plot of a two-group contrast, with point selection.

Consumes the univariate results Table (one row per feature, with the
per-group `mean_<group>` columns) and plots

    x = log2 fold change (mean_group_a - mean_group_b)
    y = -log10 (FDR)

for a chosen pair of groups, with the FDR and fold-change thresholds drawn
as dashed lines. Features beyond both thresholds are coloured by direction
(up in group A = red, up in group B = blue) and the top hits are labelled.

Click a point to select that feature; shift-click adds/removes features from
the selection. The distribution of the selected feature(s) across the groups
of the Data input is drawn as a box plot with overlaid sample points below
the volcano. Emits the significant features (for the heatmap) and the
per-sample values of the selected feature(s).
"""

import numpy as np
import pandas as pd

from Orange.data import Table, Domain, ContinuousVariable, StringVariable
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output, Msg
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from .. import metabo_core as mc
from .owheatmap import GROUP_COLORS

NS_COLOUR = "#9e9e9e"
UP_COLOUR = "#d62728"
DOWN_COLOUR = "#1f77b4"
MAX_BOXPLOTS = 6                  # cap the selected-feature grid


class _Canvas(FigureCanvasQTAgg):
    """Matplotlib canvas as a Qt widget (FigureCanvasQTAgg IS a QWidget)."""
    def __init__(self, figsize):
        self.fig = Figure(figsize=figsize, dpi=100)
        super().__init__(self.fig)


class OWVolcano(widget.OWWidget):
    name = "Metabo Volcano"
    description = ("Volcano plot (log2 fold change vs. -log10 FDR) for a "
                   "two-group contrast; click points to see the per-group "
                   "distribution as a box plot.")
    icon = "icons/Volcano.svg"
    priority = 3160
    keywords = "volcano, fold change, fdr, contrast, biomarker, boxplot, selection"

    resizing_enabled = True

    class Inputs:
        results = Input("Results", Table)
        data = Input("Data", Table)

    class Outputs:
        selected = Output("Selected Features", Table, default=True)
        feature_values = Output("Feature Values", Table)

    class Warning(widget.OWWidget.Warning):
        need_data = Msg("Connect Data to inspect the distribution of a feature.")

    group_a = Setting(0)          # index into the mean_<group> columns
    group_b = Setting(1)
    fdr_alpha = Setting(0.05)
    fc_thresh = Setting(1.0)
    label_top = Setting(10)
    auto_commit = Setting(True)

    def __init__(self):
        super().__init__()
        self.results = None
        self.data = None
        self._levels = []          # groups from the results (mean_*)
        self._volcano = None
        self._source = None        # 'results' | 'data' | None
        self._feat = np.array([])  # feature names in scatter order
        self._selected = []        # clicked feature names

        box = gui.widgetBox(self.controlArea, "Contrast")
        self.a_combo = gui.comboBox(box, self, "group_a",
                                    label="Group A (up):", callback=self._redraw)
        self.b_combo = gui.comboBox(box, self, "group_b",
                                    label="Group B (down):", callback=self._redraw)

        thr = gui.widgetBox(self.controlArea, "Thresholds")
        gui.doubleSpin(thr, self, "fdr_alpha", 0.001, 0.5, 0.005,
                       label="FDR:", callback=self._redraw, decimals=3)
        gui.doubleSpin(thr, self, "fc_thresh", 0.0, 10.0, 0.5,
                       label="|log2FC| ≥:", callback=self._redraw, decimals=1)
        gui.spin(thr, self, "label_top", 0, 100,
                 label="Label top N:", callback=self._redraw)

        sel = gui.widgetBox(self.controlArea, "Selection")
        gui.button(sel, self, "Clear selection", callback=self._clear_selection)
        self.sel_lbl = gui.label(sel, self, "No feature selected.")

        gui.rubber(self.controlArea)
        gui.auto_apply(self.buttonsArea, self, "auto_commit")

        box2 = gui.vBox(self.mainArea, "Volcano")
        self.canvas = _Canvas((8, 5))
        box2.layout().addWidget(self.canvas)
        self.canvas.mpl_connect("pick_event", self._on_pick)
        gui.button(self.mainArea, self, "Export PNG…", callback=self._export_png)
        gui.button(self.mainArea, self, "Export SVG…", callback=self._export_svg)

        box3 = gui.vBox(self.mainArea, "Distribution of selected feature")
        self.dist_canvas = _Canvas((8, 3))
        box3.layout().addWidget(self.dist_canvas)

        self._redraw()          # draw the initial hint (no results yet)

    # ------------------------------------------------------------------ input
    @Inputs.results
    def set_results(self, results):
        self.results = results
        self._refresh_levels()
        # drop selections that no longer exist
        if results is not None:
            names = set(str(results.metas[i, self._feat_meta(results)])
                        for i in range(len(results))) if self._feat_meta(results) is not None else set()
            self._selected = [f for f in self._selected if f in names]
        self._populate_combos()
        self._redraw()

    @Inputs.data
    def set_data(self, data):
        self.data = data
        self._refresh_levels()
        self._populate_combos()
        self._redraw()

    def _refresh_levels(self):
        """Groups for the contrast: the results' mean_* columns if present,
        otherwise the Data's group column."""
        lv = self._read_levels(self.results)
        if not lv:
            _, lv = self._groups_of_data()
        self._levels = lv

    def _sel_groups(self):
        n = len(self._levels)
        return (self._levels[min(self.group_a, n - 1)],
                self._levels[min(self.group_b, n - 1)])

    @staticmethod
    def _feat_meta(results):
        for i, m in enumerate(results.domain.metas):
            if m.name == "Feature":
                return i
        return None

    @staticmethod
    def _read_levels(results):
        if results is None:
            return []
        return [a.name[len("mean_"):] for a in results.domain.attributes
                if a.name.startswith("mean_")]

    def _populate_combos(self):
        from AnyQt.QtGui import QStandardItem, QStandardItemModel
        levels = self._levels
        for combo, attr in ((self.a_combo, "group_a"), (self.b_combo, "group_b")):
            combo.blockSignals(True)
            model = QStandardItemModel()
            for g in levels:
                model.appendRow(QStandardItem(g))
            combo.setModel(model)
            # only write the Setting while the combo has items, else Orange
            # warns "combo box '<x>' is empty"
            if levels:
                idx = getattr(self, attr)
                if not (0 <= idx < len(levels)):
                    idx = 0
                combo.setCurrentIndex(idx)
                setattr(self, attr, idx)
            combo.blockSignals(False)
        # sensible default: A = first, B = second (when both exist)
        if len(levels) >= 2 and self.group_a == self.group_b:
            self.group_b = 1 if self.group_a == 0 else 0
            self.b_combo.blockSignals(True)
            self.b_combo.setCurrentIndex(self.group_b)
            self.b_combo.blockSignals(False)

    # ------------------------------------------------------------------ core
    def _results_dataframe(self):
        """DataFrame built from the results Table (Feature + attributes)."""
        res = self.results
        fcol = self._feat_meta(res) if res is not None else None
        if fcol is None:
            return None
        d = {"Feature": [str(res.metas[i, fcol]) for i in range(len(res))]}
        for i, a in enumerate(res.domain.attributes):
            d[a.name] = np.asarray(res.X[:, i], dtype=float)
        return pd.DataFrame(d)

    def _computed_dataframe(self, ga, gb):
        """Contrast computed from the Data input: Welch two-sample t-test of
        ga vs gb per feature + Benjamini-Hochberg FDR, plus the two group means.
        Returns None when Data has no usable group column."""
        if self.data is None or "group" not in self.data.domain:
            return None
        groups, levels = self._groups_of_data()
        if ga not in levels or gb not in levels:
            return None
        feat = [a.name for a in self.data.domain.attributes]
        X_f = np.asarray(self.data.X, dtype=float).T          # features x samples
        df, _ = mc.univariate(X_f, groups, "welch", base=gb, treats=[ga],
                              feature_names=feat)
        return mc.add_group_means(df, X_f, groups, [ga, gb], feature_names=feat)

    def _table(self):
        """Return (volcano DataFrame, group_a, group_b) or None.

        Uses the Metabo Univariate Stats results when they are connected;
        otherwise the contrast (Welch t-test + BH-FDR over all features) is
        computed from the Data input, so Preprocess -> Volcano already plots.
        Sets self._source to 'results' / 'data' / None.
        """
        self._source = None
        if len(self._levels) < 2:
            return None
        ga, gb = self._sel_groups()
        if ga == gb:
            return None
        df = self._results_dataframe()
        self._source = "results"
        if df is None or f"mean_{ga}" not in df.columns \
                or f"mean_{gb}" not in df.columns:
            df = self._computed_dataframe(ga, gb)
            self._source = "data"
        if df is None:
            self._source = None
            return None
        try:
            tab = mc.volcano_table(df, ga, gb, alpha=self.fdr_alpha,
                                   fc=self.fc_thresh)
        except ValueError:
            self._source = None
            return None
        return tab, ga, gb

    # ------------------------------------------------------------------ draw
    def _redraw(self):
        built = self._table()
        self.fig = self.canvas.fig
        self.fig.clear()
        if built is None:
            ax = self.fig.add_subplot(111)
            msg = ("Connect the Data output of “Metabo Preprocess” (its group\n"
                   "column and feature values are enough to compute the\n"
                   "contrast), or the Results output of “Metabo Univariate\n"
                   "Stats” for an ANOVA/Kruskal-based analysis.")
            ax.text(0.5, 0.5, msg, ha="center", va="center", fontsize=10)
            ax.axis("off")
            self.canvas.draw_idle()
            self._volcano = None
            self._feat = np.array([])
            self.information()
            self.commit.now() if self.auto_commit else self.commit.deferred()
            self._draw_dist()
            return
        tab, ga, gb = built
        self._volcano = tab
        lfc = tab["log2FC"].to_numpy(float)
        neg = tab["neglog10FDR"].to_numpy(float)
        d = tab["direction"].to_numpy()
        self._feat = tab["Feature"].to_numpy()

        ax = self.fig.add_subplot(111)
        # one scatter so a picked point maps directly to a feature index
        colours = np.where(d == "ns", NS_COLOUR,
                           np.where(d == "up", UP_COLOUR, DOWN_COLOUR))
        sizes = np.where(d == "ns", 16, 28)
        self._sc = ax.scatter(lfc, neg, s=sizes, c=list(colours),
                              edgecolors="none", picker=6)
        # highlight the selected features on top
        if self._selected:
            mask = np.isin(self._feat, self._selected)
            if mask.any():
                ax.scatter(lfc[mask], neg[mask], s=90, facecolors="none",
                           edgecolors="black", linewidths=1.4)
        ax.axvline(self.fc_thresh, color="#888", ls="--", lw=1)
        ax.axvline(-self.fc_thresh, color="#888", ls="--", lw=1)
        ax.axhline(-np.log10(self.fdr_alpha), color="#888", ls="--", lw=1)
        if self.label_top:
            sig = d != "ns"
            order = np.argsort(-neg, kind="stable")
            order = np.concatenate([order[sig[order]], order[~sig[order]]])
            for i in order[:self.label_top]:
                ax.annotate(_short(str(self._feat[i])), (lfc[i], neg[i]),
                            fontsize=6.5, xytext=(3, 2),
                            textcoords="offset points")
        ax.set_xlabel(f"log2 fold change ({ga} − {gb})", fontsize=9)
        ax.set_ylabel("−log10 (FDR)", fontsize=9)
        ax.set_title(f"Volcano — {ga} vs {gb}  (click a point)", fontsize=10)
        handles = [
            Line2D([], [], marker="o", ls="", color=NS_COLOUR,
                   label=f"ns ({int((d == 'ns').sum())})"),
            Line2D([], [], marker="o", ls="", color=UP_COLOUR,
                   label=f"up in {ga} ({int((d == 'up').sum())})"),
            Line2D([], [], marker="o", ls="", color=DOWN_COLOUR,
                   label=f"up in {gb} ({int((d == 'down').sum())})"),
        ]
        ax.legend(handles=handles, fontsize=7, loc="upper left", framealpha=0.9)
        ax.grid(alpha=0.2)
        self.fig.tight_layout()
        self.canvas.draw_idle()

        nup, ndn = int((d == "up").sum()), int((d == "down").sum())
        src = {"data": "computed from Data (Welch + BH-FDR; fold change in the "
                       "data's space — feed sum+log2, not autoscaled, for a "
                       "true log2FC)",
               "results": "from Univariate Stats"}.get(self._source or "", "")
        self.information(
            f"{len(tab)} features · {ga} vs {gb} · {nup} up, {ndn} down "
            f"at FDR<{self.fdr_alpha:g}, |log2FC|≥{self.fc_thresh:g}"
            + (f" · {src}" if src else ""))
        self._update_sel_label()
        self.commit.now() if self.auto_commit else self.commit.deferred()
        self._draw_dist()

    # ------------------------------------------------------------------ pick
    def _on_pick(self, event):
        if event.artist is not self._sc or not getattr(event, "ind", None):
            return
        feat = str(self._feat[event.ind[0]])       # topmost picked point
        from AnyQt.QtWidgets import QApplication
        from AnyQt.QtCore import Qt
        additive = bool(QApplication.keyboardModifiers() & Qt.ShiftModifier)
        if additive:
            self._selected = ([f for f in self._selected if f != feat]
                              if feat in self._selected
                              else self._selected + [feat])
        else:
            self._selected = [] if self._selected == [feat] else [feat]
        self._redraw()

    def _clear_selection(self):
        self._selected = []
        self._redraw()

    def _update_sel_label(self):
        if not self._selected:
            self.sel_lbl.setText("No feature selected.")
        else:
            self.sel_lbl.setText(f"<b>{len(self._selected)}</b> selected: "
                                 + ", ".join(_short(f, 18) for f in self._selected))

    # ------------------------------------------------------------------ dist
    def _groups_of_data(self):
        if self.data is None or "group" not in self.data.domain:
            return None, []
        gvar = self.data.domain["group"]
        vals = [str(v) for v in
                self.data.metas[:, self.data.domain.metas.index(gvar)]]
        return vals, list(dict.fromkeys(vals))

    def _draw_dist(self):
        fig = self.dist_canvas.fig
        fig.clear()
        if not self._selected:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Click a volcano point to see its per-group "
                              "distribution (box plot).",
                    ha="center", va="center", fontsize=9)
            ax.axis("off")
            self.dist_canvas.draw_idle()
            return
        if self.data is None:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Connect Data to see the distributions.",
                    ha="center", va="center", fontsize=9)
            ax.axis("off")
            self.dist_canvas.draw_idle()
            self.Warning.need_data()
            return
        self.Warning.clear()
        names = [a.name for a in self.data.domain.attributes]
        groups, levels = self._groups_of_data()
        groups = np.asarray(groups)
        sel = [f for f in self._selected if f in names][:MAX_BOXPLOTS]
        if not sel:
            ax = fig.add_subplot(111)
            ax.text(0.5, 0.5, "Selected feature(s) not present in Data.",
                    ha="center", va="center", fontsize=9)
            ax.axis("off")
            self.dist_canvas.draw_idle()
            return
        ncols = min(3, len(sel))
        nrows = int(np.ceil(len(sel) / ncols))
        rng = np.random.default_rng(0)      # reproducible jitter
        for k, feat in enumerate(sel):
            ax = fig.add_subplot(nrows, ncols, k + 1)
            col = np.asarray(self.data.X[:, names.index(feat)], dtype=float)
            data_per_group = [col[groups == g] for g in levels]
            bp = ax.boxplot(data_per_group, labels=levels, showfliers=False,
                            patch_artist=True, widths=0.6)
            for i, patch in enumerate(bp["boxes"]):
                patch.set_facecolor(GROUP_COLORS[i % len(GROUP_COLORS)])
                patch.set_alpha(0.5)
            for i, vals in enumerate(data_per_group):
                if vals.size:
                    ax.scatter(i + 1 + rng.normal(0, 0.05, vals.size), vals,
                               s=12, color=GROUP_COLORS[i % len(GROUP_COLORS)],
                               edgecolors="none", alpha=0.85, zorder=3)
            ax.set_title(_short(feat, 26), fontsize=8)
            ax.tick_params(labelsize=7)
            ax.grid(alpha=0.2, axis="y")
        fig.suptitle("Distribution per group (values in the supplied/log2 space)",
                     fontsize=9)
        fig.tight_layout()
        self.dist_canvas.draw_idle()

    # ------------------------------------------------------------------ output
    @gui.deferred
    def commit(self):
        tab = self._volcano
        if tab is None:
            self.Outputs.selected.send(None)
        else:
            sel = tab[tab["direction"] != "ns"]
            if sel.empty:
                self.Outputs.selected.send(None)
            else:
                dom = Domain(
                    [ContinuousVariable("log2FC"), ContinuousVariable("FDR_BH")],
                    metas=[StringVariable("Feature"),
                           StringVariable("direction")])
                out = Table.from_numpy(
                    dom, X=sel[["log2FC", "FDR_BH"]].to_numpy(float),
                    metas=sel[["Feature", "direction"]].to_numpy(dtype=object))
                out.name = "volcano selected"
                self.Outputs.selected.send(out)
        self.Outputs.feature_values.send(self._feature_values_table())

    def _feature_values_table(self):
        if self.data is None or not self._selected:
            return None
        names = [a.name for a in self.data.domain.attributes]
        sel = [f for f in self._selected if f in names]
        if not sel:
            return None
        groups, _ = self._groups_of_data()
        samples = None
        if "sample" in self.data.domain:
            sv = self.data.domain["sample"]
            samples = [str(v) for v in
                       self.data.metas[:, self.data.domain.metas.index(sv)]]
        rows, X = [], []
        for feat in sel:
            col = np.asarray(self.data.X[:, names.index(feat)], dtype=float)
            for r in range(len(self.data)):
                X.append([col[r]])
                rows.append([samples[r] if samples else "", groups[r] if groups else "", feat])
        dom = Domain([ContinuousVariable("value")],
                     metas=[StringVariable("sample"), StringVariable("group"),
                            StringVariable("feature")])
        out = Table.from_numpy(dom, X=np.asarray(X, dtype=float),
                               metas=np.asarray(rows, dtype=object))
        out.name = "feature values"
        return out

    # ------------------------------------------------------------------ export
    def _export_png(self):
        from ._dialogs import save_figure
        save_figure(self, self.fig, "PNG")

    def _export_svg(self):
        from ._dialogs import save_figure
        save_figure(self, self.fig, "SVG")

    def close(self):
        self.Outputs.selected.send(None)
        self.Outputs.feature_values.send(None)
        super().close()


def _short(name, n=22):
    return name if len(name) <= n else name[:n - 1] + "…"
