"""Metabo Heatmap — top-N biomarker heatmap with row clustering (Ward/Euclidean)
and a group bar. Uses matplotlib (FigureCanvasQTAgg) embedded in the main area.

Inputs:
  Data    — the (preprocessed) sample×feature Table.  Required.
  Results — the univariate results Table (one row per feature, with p/FDR).
The widget takes the top-N features by p and draws the autoscaled, row-clustered
heatmap.  Without a Results connection it ranks the features itself - one-way
ANOVA over the 'group' meta, or by variance if the table has no group column -
so it also works directly after Preprocess / Feature Filter (like the Volcano
widget).  The status line reports which ranking was used.
"""

import numpy as np

from Orange.data import Table
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output, Msg
from matplotlib.colors import LinearSegmentedColormap
from scipy.cluster.hierarchy import linkage, dendrogram

from .. import metabo_core as mc

from ._plot import PlotCanvas, attach_toolbar

CMAP = LinearSegmentedColormap.from_list(
    "rdbu_r",
    ["#053061", "#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b", "#67001f"])

GROUP_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


class OWMetaboHeatmap(widget.OWWidget):
    name = "Metabo Heatmap"
    description = ("Top-N biomarker heatmap with Ward row clustering and a group "
                   "bar; ranks by Results, or by ANOVA/variance computed from "
                   "Data when no Results are connected. PNG/SVG export.")
    icon = "icons/Heatmap.svg"
    priority = 3150
    keywords = "heatmap, clustering, ward, biomarker, top-n"

    resizing_enabled = True
    graph_name = "canvas"      # enables Orange's Save graph / clipboard / report

    class Inputs:
        data = Input("Data", Table)
        results = Input("Results", Table)

    class Outputs:
        heatmap = Output("Heatmap Data", Table)

    class Information(widget.OWWidget.Information):
        ranked_from_data = Msg(
            "No Results connected - top features ranked by {} computed from Data.")

    class Warning(widget.OWWidget.Warning):
        no_data = Msg("Connect a preprocessed feature table to 'Data'.")

    top_n = Setting(20)
    cluster = Setting(True)
    vlim = Setting(2.5)

    def __init__(self):
        super().__init__()
        self.data = None
        self.results = None
        self._new_view = True

        box = gui.widgetBox(self.controlArea, "Display")
        gui.spin(box, self, "top_n", 1, 500, label="Top N features:",
                 callback=self._draw)
        gui.checkBox(box, self, "cluster", "Cluster rows (Ward / Euclidean)",
                     callback=self._draw)
        gui.doubleSpin(box, self, "vlim", 0.5, 10.0, 0.5,
                       label="Colour scale (±):", callback=self._draw, decimals=1)
        gui.rubber(self.controlArea)

        self.canvas = PlotCanvas((9, 7))
        box2 = gui.vBox(self.mainArea, "Heatmap")
        box2.layout().addWidget(self.canvas)
        attach_toolbar(box2, self.canvas, self)
        row = gui.hBox(box2)
        gui.button(row, self, "Reset view", callback=self.canvas.reset_view)
        gui.button(row, self, "Export PNG…", callback=self._export_png)
        gui.button(row, self, "Export SVG…", callback=self._export_svg)

    @Inputs.data
    def set_data(self, data):
        self.data = data
        self._new_view = True
        self._draw()

    @Inputs.results
    def set_results(self, results):
        self.results = results
        self._new_view = True
        self._draw()

    # ------------------------------------------------------------------ data
    def _read_groups(self):
        if self.data is None:
            return None, []
        if "group" not in self.data.domain:
            return None, []
        gvar = self.data.domain["group"]
        vals = self.data.metas[:, self.data.domain.metas.index(gvar)]
        return [str(v) for v in vals], list(dict.fromkeys(str(v) for v in vals))

    def _build(self):
        """Return (X_sub [features x samples], feature_names, sample_names,
        groups, levels, stats_by_feature)."""
        if self.data is None:
            return None
        X_sf = np.asarray(self.data.X, dtype=float)          # samples x features
        X_f = X_sf.T                                         # features x samples
        feat_all = [a.name for a in self.data.domain.attributes]
        # sample names from the 'sample' meta
        sample_names = None
        if "sample" in self.data.domain:
            sv = self.data.domain["sample"]
            sample_names = [str(v) for v in
                            self.data.metas[:, self.data.domain.metas.index(sv)]]
        groups, levels = self._read_groups()
        # map results feature name -> row index in X_f
        name_to_row = {n: i for i, n in enumerate(feat_all)}
        # ranking: use the univariate Results when connected, otherwise compute
        # it from Data (like the Volcano widget does), so the widget also works
        # directly after Preprocess/Feature Filter.
        self._ranking_source = self._ranking_kind = None
        rows = self._rows_from_results()
        if rows is None:
            rows = self._rows_from_data()
            self._ranking_source = "data" if rows is not None else None
        else:
            self._ranking_source = "results"
        if rows is None:
            return None
        rows.sort(key=lambda t: t[0])
        top = rows[:self.top_n]
        top_feats = [f for _, f in top]
        top_idx = [name_to_row[f] for f in top_feats if f in name_to_row]
        if not top_idx:
            return None
        Z = X_f[top_idx]
        # autoscale per feature for display
        mu = Z.mean(axis=1, keepdims=True)
        sd = Z.std(axis=1, keepdims=True, ddof=1)
        sd[sd == 0] = 1.0
        Z = (Z - mu) / sd
        # cluster rows
        order = list(range(len(top_idx)))
        if self.cluster and len(top_idx) > 2:
            try:
                lk = linkage(Z, method="ward", metric="euclidean")
                order = list(dendrogram(lk, no_plot=True)["leaves"])
            except Exception:
                order = list(range(len(top_idx)))
        top_idx = [top_idx[i] for i in order]
        Z = Z[order]
        top_feats = [top_feats[i] for i in order]
        return Z, top_feats, sample_names, groups, levels

    def _rows_from_results(self):
        """(score, feature) pairs from the Results table (ascending p), or None."""
        if self.results is None:
            return None
        res = self.results
        pcol = next((i for i, c in enumerate(res.domain.attributes)
                     if c.name == "p"), None)
        feat_col = next((i for i, mv in enumerate(res.domain.metas)
                         if mv.name == "Feature"), None)
        if pcol is None or feat_col is None:
            return None
        return [(float(res[i, pcol]), str(res.metas[i, feat_col]))
                for i in range(len(res))]

    def _rows_from_data(self):
        """Rank features without a Results table: one-way ANOVA over the 'group'
        meta, or by variance when no usable group column is present."""
        if self.data is None:
            return None
        feat = [a.name for a in self.data.domain.attributes]
        X_f = np.asarray(self.data.X, dtype=float).T
        groups, levels = self._read_groups()
        if groups and len(levels) >= 2 and min(groups.count(lv) for lv in levels) >= 2:
            self._ranking_kind = "one-way ANOVA"
            df, _ = mc.univariate(X_f, groups, "anova", feature_names=feat)
            p = dict(zip(df["Feature"], (float(v) for v in df["p"])))
            return [(p[f], f) for f in feat
                    if f in p and np.isfinite(p[f])]
        self._ranking_kind = "variance"
        var = X_f.var(axis=1, ddof=1)
        return [(-float(var[i]), feat[i]) for i in range(len(feat))]

    # ------------------------------------------------------------------ draw
    def _draw(self):
        self.fig = self.canvas.fig
        self.fig.clear()
        self.Information.clear()
        built = self._build()
        if built is None:
            self.Warning.clear()
            hint = ("Connect a preprocessed feature table to 'Data'."
                    if self.data is None else "No features to show.")
            if self.data is None:
                self.Warning.no_data()
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, hint, ha="center", va="center", fontsize=11)
            ax.axis("off")
            self.canvas.draw_idle()
            self.Outputs.heatmap.send(None)
            return
        self.Warning.clear()
        if self._ranking_source == "data":
            self.Information.ranked_from_data(self._ranking_kind)
        Z, top_feats, sample_names, groups, levels = built
        nR, nC = Z.shape
        # group bar on top
        ax_bar = self.fig.add_axes([0.14, 0.86, 0.78, 0.03])
        if groups is not None:
            for j, g in enumerate(groups):
                ax_bar.add_patch(
                    _rect(j - 0.5, 0.2, 1, 0.6,
                          _color_for(g, levels)))
        ax_bar.set_xlim(-0.5, nC - 0.5)
        ax_bar.set_ylim(0, 1)
        ax_bar.axis("off")
        # heatmap
        ax = self.fig.add_axes([0.14, 0.12, 0.78, 0.70])
        im = ax.imshow(Z, aspect="auto", cmap=CMAP,
                       vmin=-self.vlim, vmax=self.vlim,
                       interpolation="nearest")
        ax.set_xticks(range(nC))
        lab_c = (sample_names if sample_names is not None
                 else [str(j) for j in range(nC)])
        ax.set_xticklabels(lab_c, rotation=90, fontsize=6.5)
        ax.set_yticks(range(nR))
        ax.set_yticklabels([_short(f, 30) for f in top_feats], fontsize=7)
        ax.set_xticks(np.arange(-.5, nC, 1), minor=True)
        ax.set_yticks(np.arange(-.5, nR, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.6)
        ax.tick_params(which="minor", length=0)
        cbar = self.fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("z-score", fontsize=8)
        self.fig.suptitle(
            f"Top {nR} features (Ward cluster, ±{self.vlim:g})", fontsize=10)
        self._built = built
        self.canvas.after_draw(ax, new_data=self._new_view)
        self._new_view = False
        self.canvas.draw_idle()
        self._send_output(Z, top_feats, sample_names, groups)

    def _send_output(self, Z, top_feats, sample_names, groups):
        if self.data is None:
            self.Outputs.heatmap.send(None)
            return
        from Orange.data import Domain, ContinuousVariable, StringVariable
        attrs = [ContinuousVariable(f) for f in top_feats]
        metas = []
        if sample_names:
            metas.append(StringVariable("sample"))
        if groups is not None:
            metas.append(StringVariable("group"))
        dom = Domain(attrs, metas=metas)
        X_out = Z.T  # samples x top_features
        if metas:
            if groups is not None:
                m = np.array([[s, g] for s, g in
                              zip(sample_names or [""] * len(groups), groups)],
                             dtype=object)
            else:
                m = np.array([[s] for s in sample_names], dtype=object)
        else:
            m = None
        out = Table.from_numpy(dom, X=X_out, metas=m)
        out.name = "heatmap data"
        self.Outputs.heatmap.send(out)

    # ------------------------------------------------------------------ export
    def _export_png(self):
        from ._dialogs import save_figure
        save_figure(self, self.fig, "PNG")

    def _export_svg(self):
        from ._dialogs import save_figure
        save_figure(self, self.fig, "SVG")

    def close(self):
        self.Outputs.heatmap.send(None)
        super().close()


def _short(name, n=30):
    return name if len(name) <= n else name[:n - 1] + "…"


def _color_for(group, levels):
    try:
        i = levels.index(group)
    except ValueError:
        i = 0
    return GROUP_COLORS[i % len(GROUP_COLORS)]


def _rect(x, y, w, h, fc):
    from matplotlib.patches import Rectangle
    return Rectangle((x, y), w, h, facecolor=fc, edgecolor="none")
