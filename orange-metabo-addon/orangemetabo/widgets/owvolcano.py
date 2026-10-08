"""Metabo Volcano — volcano plot of a two-group contrast.

Consumes the univariate results Table (one row per feature, with the
per-group `mean_<group>` columns) and plots

    x = log2 fold change (mean_group_a - mean_group_b)
    y = -log10 (FDR)

for a chosen pair of groups, with the FDR and fold-change thresholds drawn
as dashed lines. Features beyond both thresholds are coloured by direction
(up in group A = red, up in group B = blue) and the top hits are labelled.
Emits the significant features as a Table so the plot can be chained into
Metabo Heatmap.
"""

import numpy as np
import pandas as pd

from Orange.data import Table, Domain, ContinuousVariable, StringVariable
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from .. import metabo_core as mc

NS_COLOUR = "#9e9e9e"
UP_COLOUR = "#d62728"
DOWN_COLOUR = "#1f77b4"


class _Canvas(FigureCanvasQTAgg):
    """Matplotlib canvas as a Qt widget (FigureCanvasQTAgg IS a QWidget)."""
    def __init__(self):
        self.fig = Figure(figsize=(8, 6), dpi=100)
        super().__init__(self.fig)


class OWVolcano(widget.OWWidget):
    name = "Metabo Volcano"
    description = ("Volcano plot (log2 fold change vs. -log10 FDR) for a "
                   "two-group contrast from the univariate results; "
                   "PNG/SVG export.")
    icon = "icons/Volcano.svg"
    priority = 3160
    keywords = "volcano, fold change, fdr, contrast, biomarker, differential"

    resizing_enabled = True

    class Inputs:
        results = Input("Results", Table)

    class Outputs:
        selected = Output("Selected Features", Table, default=True)

    group_a = Setting(0)          # index into the mean_<group> columns
    group_b = Setting(1)
    fdr_alpha = Setting(0.05)
    fc_thresh = Setting(1.0)
    label_top = Setting(10)
    auto_commit = Setting(True)

    def __init__(self):
        super().__init__()
        self.results = None
        self._levels = []
        self._volcano = None

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

        gui.rubber(self.controlArea)
        gui.auto_apply(self.buttonsArea, self, "auto_commit")

        self.canvas = _Canvas()
        box2 = gui.vBox(self.mainArea, "Volcano")
        box2.layout().addWidget(self.canvas)
        gui.button(self.mainArea, self, "Export PNG…", callback=self._export_png)
        gui.button(self.mainArea, self, "Export SVG…", callback=self._export_svg)

    # ------------------------------------------------------------------ input
    @Inputs.results
    def set_results(self, results):
        self.results = results
        self._levels = self._read_levels(results)
        self._populate_combos()
        self._redraw()

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
    def _table(self):
        """Return (volcano DataFrame, group_a name, group_b name) or None."""
        if self.results is None or len(self._levels) < 2:
            return None
        res = self.results
        fcol = next((i for i, m in enumerate(res.domain.metas)
                     if m.name == "Feature"), None)
        if fcol is None:
            return None
        data = {"Feature": [str(res.metas[i, fcol]) for i in range(len(res))]}
        for i, a in enumerate(res.domain.attributes):
            data[a.name] = np.asarray(res.X[:, i], dtype=float)
        ga = self._levels[min(self.group_a, len(self._levels) - 1)]
        gb = self._levels[min(self.group_b, len(self._levels) - 1)]
        try:
            tab = mc.volcano_table(pd.DataFrame(data), ga, gb,
                                   alpha=self.fdr_alpha, fc=self.fc_thresh)
        except ValueError:
            return None
        return tab, ga, gb

    # ------------------------------------------------------------------ draw
    def _redraw(self):
        self.fig = self.canvas.fig
        self.fig.clear()
        built = self._table()
        if built is None:
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, "Waiting for results with per-group means\n"
                              "(Metabo Univariate Stats)…",
                    ha="center", va="center", fontsize=10)
            ax.axis("off")
            self.canvas.draw_idle()
            self._volcano = None
            self.information()
            self.commit.now() if self.auto_commit else self.commit.deferred()
            return
        tab, ga, gb = built
        self._volcano = tab
        lfc = tab["log2FC"].to_numpy(float)
        neg = tab["neglog10FDR"].to_numpy(float)
        d = tab["direction"].to_numpy()
        feat = tab["Feature"].to_numpy()

        ax = self.fig.add_subplot(111)
        ns = d == "ns"
        ax.scatter(lfc[ns], neg[ns], s=16, c=NS_COLOUR, alpha=0.6,
                   edgecolors="none", label=f"ns ({int(ns.sum())})")
        for mask, colour, lab in (
                (d == "up", UP_COLOUR, f"up in {ga}"),
                (d == "down", DOWN_COLOUR, f"up in {gb}")):
            if mask.any():
                ax.scatter(lfc[mask], neg[mask], s=28, c=colour,
                           edgecolors="none", label=f"{lab} ({int(mask.sum())})")
        ax.axvline(self.fc_thresh, color="#888", ls="--", lw=1)
        ax.axvline(-self.fc_thresh, color="#888", ls="--", lw=1)
        ax.axhline(-np.log10(self.fdr_alpha), color="#888", ls="--", lw=1)
        # label the top hits, significant features first
        if self.label_top:
            sig = d != "ns"
            order = np.argsort(-neg, kind="stable")
            order = np.concatenate([order[sig[order]], order[~sig[order]]])
            for i in order[:self.label_top]:
                ax.annotate(_short(str(feat[i])), (lfc[i], neg[i]),
                            fontsize=6.5, xytext=(3, 2),
                            textcoords="offset points")
        ax.set_xlabel(f"log2 fold change ({ga} − {gb})", fontsize=9)
        ax.set_ylabel("−log10 (FDR)", fontsize=9)
        ax.set_title(f"Volcano — {ga} vs {gb}", fontsize=10)
        ax.legend(fontsize=7, loc="upper left", framealpha=0.9)
        ax.grid(alpha=0.2)
        self.fig.tight_layout()
        self.canvas.draw_idle()

        nup, ndn = int((d == "up").sum()), int((d == "down").sum())
        self.information(
            f"{len(tab)} features · {ga} vs {gb} · {nup} up, {ndn} down "
            f"at FDR<{self.fdr_alpha:g}, |log2FC|≥{self.fc_thresh:g}")
        self.commit.now() if self.auto_commit else self.commit.deferred()

    # ------------------------------------------------------------------ output
    @gui.deferred
    def commit(self):
        tab = self._volcano
        if tab is None:
            self.Outputs.selected.send(None)
            return
        sel = tab[tab["direction"] != "ns"]
        if sel.empty:
            self.Outputs.selected.send(None)
            return
        dom = Domain([ContinuousVariable("log2FC"), ContinuousVariable("FDR_BH")],
                     metas=[StringVariable("Feature"), StringVariable("direction")])
        out = Table.from_numpy(
            dom,
            X=sel[["log2FC", "FDR_BH"]].to_numpy(float),
            metas=sel[["Feature", "direction"]].to_numpy(dtype=object))
        out.name = "volcano selected"
        self.Outputs.selected.send(out)

    # ------------------------------------------------------------------ export
    def _export_png(self):
        from ._dialogs import save_figure
        save_figure(self, self.fig, "PNG")

    def _export_svg(self):
        from ._dialogs import save_figure
        save_figure(self, self.fig, "SVG")

    def close(self):
        self.Outputs.selected.send(None)
        super().close()


def _short(name, n=22):
    return name if len(name) <= n else name[:n - 1] + "…"
