"""Metabo Heatmap — top-N biomarker heatmap with optional Ward row dendrogram,
a configurable group legend and clickable cells.

Inputs:
  Data    — the (preprocessed) sample×feature Table.  Required.
  Results — the univariate results Table (one row per feature, with p/FDR).
The widget takes the top-N features by p and draws the autoscaled, row-clustered
heatmap.  Without a Results connection it ranks the features itself - one-way
ANOVA over the 'group' meta, or by variance if the table has no group column -
so it also works directly after Preprocess / Feature Filter (like the Volcano
widget).  The status line reports which ranking was used.

Interaction: click a cell to select its feature — the cell is highlighted, the
"Selection" panel shows the feature's statistics, group means and the clicked
sample's value.  Wheel zooms, drag pans (see `_plot.PlotCanvas`).
"""

import numpy as np

from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import QApplication, QLabel

from Orange.data import (Table, Domain, ContinuousVariable, DiscreteVariable,
                         StringVariable)
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output, Msg
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch, Rectangle
from scipy.cluster.hierarchy import linkage, dendrogram

from .. import metabo_core as mc
from ._plot import PlotCanvas, attach_toolbar, draggable, points_in_polygon
from ...selection import select_features

CMAP = LinearSegmentedColormap.from_list(
    "rdbu_r",
    ["#053061", "#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b", "#67001f"])

GROUP_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]

#: group display modes (MetaboAnalyst-style group bar plus optional legend)
AGGREGATIONS = ("Mean", "Median", "Sum")   # per-group summary in the distribution plot

GROUP_MODES = ("bar + legend", "bar + names", "bar only", "none")
LEGEND_POSITIONS = ("right", "below")


class OWMetaboHeatmap(widget.OWWidget):
    name = "Metabo Heatmap"
    description = ("Top-N biomarker heatmap with Ward row clustering, optional "
                   "dendrogram, configurable group legend and clickable cells; "
                   "ranks by Results, or by ANOVA/variance computed from Data "
                   "when no Results are connected. PNG/SVG export.")
    icon = "icons/Heatmap.svg"
    priority = 3150
    keywords = ("heatmap, clustering, ward, dendrogram, biomarker, top-n, "
                "legend, groups")

    resizing_enabled = True
    graph_name = "canvas"

    class Inputs:
        data = Input("Data", Table)
        results = Input("Results", Table)

    class Outputs:
        heatmap = Output("Heatmap Data", Table)
        selected_data = Output("Selected Data", Table)

    class Information(widget.OWWidget.Information):
        ranked_from_data = Msg(
            "No Results connected - top features ranked by {} computed from Data.")

    class Warning(widget.OWWidget.Warning):
        no_data = Msg("Connect a preprocessed feature table to 'Data'.")

    # ------------------------------------------------------------- settings
    top_n = Setting(20)
    cluster = Setting(True)
    vlim = Setting(2.5)
    show_dendrogram = Setting(False)
    group_mode = Setting(GROUP_MODES[0])
    legend_pos = Setting(LEGEND_POSITIONS[0])
    show_samples = Setting(True)
    agg = Setting("Mean")               # Mean | Median | Sum per group
    lasso = Setting(False)        # left-drag lasso selection instead of panning

    def __init__(self):
        super().__init__()
        self.data = None
        self.results = None
        self._new_view = True
        self._built = None
        self._selected = []              # selected feature names (multi-select)
        self._cell = None                # (row, col) of the last clicked cell

        box = gui.widgetBox(self.controlArea, "Display")
        gui.spin(box, self, "top_n", 1, 500, label="Top N features:", callback=self._redraw)
        gui.checkBox(box, self, "cluster", "Cluster rows (Ward / Euclidean)",
                     callback=self._redraw)
        gui.checkBox(box, self, "show_dendrogram", "Show row dendrogram",
                     callback=self._redraw)
        gui.doubleSpin(box, self, "vlim", 0.5, 10.0, 0.5, label="Colour scale (±):",
                       callback=self._redraw, decimals=1)
        gui.checkBox(box, self, "show_samples", "Sample names",
                     callback=self._redraw)

        lbox = gui.widgetBox(self.controlArea, "Legend")
        gui.comboBox(lbox, self, "group_mode", items=GROUP_MODES,
                     label="Groups:", callback=self._redraw,
                     sendSelectedValue=True)   # store the STRING, not the index
        self.legend_pos_control = gui.comboBox(
            lbox, self, "legend_pos", items=LEGEND_POSITIONS,
            label="Legend position:", callback=self._redraw,
            sendSelectedValue=True)
        gui.label(lbox, self, "<i>Legends can be dragged inside the plot.</i>")
        self._sync_legend_controls()

        sbox = gui.widgetBox(self.controlArea, "Selection")
        gui.checkBox(sbox, self, "lasso", "Lasso select (drag in the plot)",
                     callback=self._lasso_toggled,
                     tooltip="Left-drag draws a polygon; the features of all "
                             "cells inside are added to the selection.")
        gui.button(sbox, self, "Clear selection", callback=self._clear_selection)
        self.sel_lbl = gui.label(sbox, self, "No feature selected.")
        gui.comboBox(sbox, self, "agg", items=AGGREGATIONS,
                     label="Distribution:", callback=self._draw_distribution,
                     sendSelectedValue=True,
                     tooltip="How the per-sample values are summarised per group "
                             "in the distribution plot below the heatmap.")

        gui.rubber(self.controlArea)

        self.canvas = PlotCanvas((9, 7))
        self.canvas.on_click = self._on_canvas_click
        box2 = gui.vBox(self.mainArea, "Heatmap")
        box2.layout().addWidget(self.canvas)
        attach_toolbar(box2, self.canvas, self)
        row = gui.hBox(box2)
        gui.button(row, self, "Reset view", callback=self.canvas.reset_view)
        gui.button(row, self, "Export PNG…", callback=self._export_png)
        gui.button(row, self, "Export SVG…", callback=self._export_svg)

        ibox = gui.vBox(self.mainArea, "Selection")
        # NOTE: not `self.info` - Orange's OWWidget keeps that name for the
        # legacy input-summary widget (see orangewidget.widget back-compat shim).
        self.details = QLabel("Click a heatmap cell to see the feature's details.")
        self.details.setWordWrap(True)
        self.details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ibox.layout().addWidget(self.details)

        # distribution of the selected feature over the samples, per group
        dbox = gui.vBox(self.mainArea, "Distribution")
        self.dist_canvas = PlotCanvas((9, 2.4))
        dbox.layout().addWidget(self.dist_canvas)
        attach_toolbar(dbox, self.dist_canvas, self)

    # ------------------------------------------------------------------ inputs
    @Inputs.data
    def set_data(self, data):
        self.data = data
        self._new_view = True
        self._selected = []
        self._cell = None
        self._redraw()

    @Inputs.results
    def set_results(self, results):
        self.results = results
        self._new_view = True
        self._redraw()

    def _update_input_summary(self):
        """Report the inputs via Orange's current API.

        Careful with the name: `_update_summary` is internal to Orange's signal
        machinery (orangewidget.utils.signals) and `self.info` is the legacy
        input-summary widget.
        """
        if not hasattr(self, "set_input_summary"):
            return
        if self.data is None:
            self.set_input_summary(self.inputs.NoInput)
            return
        n_samp = len(self.data)
        n_feat = len(self.data.domain.attributes)
        detail = (f"{n_samp} samples x {n_feat} features"
                  + (", Results connected" if self.results is not None else ""))
        self.set_input_summary(f"{n_samp} samples", detail)

    def _sync_legend_controls(self):
        """The legend position only matters when a legend is drawn."""
        pos_widget = getattr(self, "legend_pos_control", None)
        if pos_widget is not None:
            pos_widget.setEnabled(self._legend_is_box())

    # ------------------------------------------------------------------ data
    def _labels_of(self, var):
        """Per-sample labels for a variable, resolving discrete CODES to names."""
        d = self.data.domain
        if var in d.metas:
            vals = self.data.metas[:, d.metas.index(var)]
        elif var in d.class_vars:
            Y = np.asarray(self.data.Y)
            # Orange stores Y 1-D for a single class variable
            vals = Y if Y.ndim == 1 else Y[:, d.class_vars.index(var)]
        else:
            vals = np.asarray(self.data.X)[:, d.attributes.index(var)]
        if isinstance(var, DiscreteVariable):
            return [str(var.values[int(v)])
                    if np.isfinite(v) and 0 <= int(v) < len(var.values) else "?"
                    for v in vals]
        return [str(v) for v in vals]

    def _read_groups(self):
        """(per-sample group labels, levels) for the colour bar / legend.

        A 'group' column often arrives as numeric CODES (a discrete variable
        stored in metas/Y keeps codes, so `str(v)` gives "0.0", "2.0", …) - that
        produced a bar labelled with numbers instead of names. Resolve discrete
        codes to their value names and, if the group column is still purely
        numeric, fall back to a discrete class variable, which usually carries
        the study group.
        """
        if self.data is None or "group" not in self.data.domain:
            return None, []
        labels = self._labels_of(self.data.domain["group"])

        def numeric(vals):
            for v in vals:
                try:
                    float(v)
                except (TypeError, ValueError):
                    return False
            return True

        if numeric(labels):
            for cv in self.data.domain.class_vars:
                if isinstance(cv, DiscreteVariable):
                    alt = self._labels_of(cv)
                    if not numeric(alt):
                        labels = alt
                        break
        return labels, list(dict.fromkeys(labels))

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
            p = {f: float(v) for f, v in zip(df["Feature"], df["p"])}
            self._p_by_feature = {f: p[f] for f in feat if f in p and np.isfinite(p[f])}
            return [(self._p_by_feature[f], f) for f in self._p_by_feature]
        self._ranking_kind = "variance"
        self._p_by_feature = {}
        var = X_f.var(axis=1, ddof=1)
        return [(-float(var[i]), feat[i]) for i in range(len(feat))]

    def _ranking(self):
        """(rows, source) - rows are (score, feature) with ascending score."""
        rows = self._rows_from_results()
        if rows is not None:
            self._p_by_feature = {f: p for p, f in rows}
            return rows, "results"
        rows = self._rows_from_data()
        return rows, ("data" if rows is not None else None)

    def _build(self):
        """Assemble everything the drawing needs, or None when nothing can be drawn."""
        if self.data is None:
            return None
        X_f = np.asarray(self.data.X, dtype=float).T          # features x samples
        feat_all = [a.name for a in self.data.domain.attributes]
        samples = None
        if "sample" in self.data.domain:
            sv = self.data.domain["sample"]
            samples = [str(v) for v in
                       self.data.metas[:, self.data.domain.metas.index(sv)]]
        groups, levels = self._read_groups()

        rows, self._ranking_source = self._ranking()
        if rows is None:
            return None
        rows.sort(key=lambda t: t[0])
        top_feats = [f for _, f in rows[:self.top_n]]
        name_to_row = {n: i for i, n in enumerate(feat_all)}
        top_idx = [name_to_row[f] for f in top_feats if f in name_to_row]
        if not top_idx:
            return None
        top_feats = [feat_all[i] for i in top_idx]

        raw = X_f[top_idx]
        mu = raw.mean(axis=1, keepdims=True)
        sd = raw.std(axis=1, keepdims=True, ddof=1)
        sd[sd == 0] = 1.0
        Z = (raw - mu) / sd

        lk, order = None, list(range(len(top_idx)))
        if self.cluster and len(top_idx) > 2:
            try:
                lk = linkage(Z, method="ward", metric="euclidean")
                order = list(dendrogram(lk, no_plot=True)["leaves"])
            except Exception:
                lk = None
        Z = Z[order]
        return dict(Z=Z, feats=[top_feats[i] for i in order], raw=raw[order],
                    samples=samples, groups=groups, levels=levels, linkage=lk)

    # ------------------------------------------------------------------ draw
    def _redraw(self):
        self._new_view = True
        self._draw()

    def _draw(self):
        self.Information.clear()
        self._sync_legend_controls()
        self.fig = self.canvas.fig
        self.fig.clear()
        self._built = self._build()
        if self._built is None:
            self.Warning.clear()
            if self.data is None:
                self.Warning.no_data()
            hint = ("Connect a preprocessed feature table to 'Data'."
                    if self.data is None else "No features to show.")
            ax = self.fig.add_subplot(111)
            ax.text(0.5, 0.5, hint, ha="center", va="center", fontsize=11)
            ax.axis("off")
            self.details.setText(self._info_text())
            self._update_input_summary()
            self.canvas.draw_idle()
            self.Outputs.heatmap.send(None)
            self.Outputs.selected_data.send(None)
            self._update_sel_label()
            self._draw_distribution()
            return
        self.Warning.clear()
        if self._ranking_source == "data":
            self.Information.ranked_from_data(self._ranking_kind)

        b = self._built
        Z, feats = b["Z"], b["feats"]
        nR, nC = Z.shape
        left, bottom, width, height = self._layout()

        ax = self.fig.add_axes([left, bottom, width, height])
        im = ax.imshow(Z, aspect="auto", cmap=CMAP, vmin=-self.vlim,
                       vmax=self.vlim, interpolation="nearest")
        ax.set_xticks(range(nC))
        labels = b["samples"] if (self.show_samples and b["samples"]) \
            else [str(j) for j in range(nC)]
        ax.set_xticklabels(labels, rotation=90, fontsize=6.5)
        ax.set_yticks(range(nR))
        ax.set_yticklabels([_short(f, 22 if self.show_dendrogram else 30)
                            for f in feats], fontsize=7)
        ax.set_xticks(np.arange(-.5, nC, 1), minor=True)
        ax.set_yticks(np.arange(-.5, nR, 1), minor=True)
        ax.grid(which="minor", color="white", linewidth=0.6)
        ax.tick_params(which="minor", length=0)
        self._ax_heat = ax

        cbar = self.fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label("z-score", fontsize=8)

        self._draw_group_bar(ax, b, nC)
        if self.show_dendrogram and b["linkage"] is not None:
            self._draw_dendrogram(b["linkage"], bottom, height)
        self._draw_selection(ax)
        self._legend(b, ax)

        self.fig.suptitle(f"Top {nR} features (Ward cluster, ±{self.vlim:g})",
                          fontsize=10)
        self.details.setText(self._info_text())
        self._update_sel_label()
        self._update_input_summary()
        self.canvas.after_draw(ax, new_data=self._new_view)
        self._new_view = False
        self.canvas.draw_idle()
        self._send_output(Z, feats, b["samples"], b["groups"])
        self.Outputs.selected_data.send(self._selected_data_table())
        self._draw_distribution()

    # --------------------------------------------------------------- elements
    def _layout(self):
        """(left, bottom, width, height) for the heatmap axes.

        Reserves room for the row dendrogram on the left (with enough space for
        the feature labels between dendrogram and heatmap) and for the legend on
        the right, so long compound names cannot collide with either.
        """
        legend_right = self._legend_is_box() and self._legend_pos() == "right"
        left = 0.40 if self.show_dendrogram else 0.14
        right = 0.62 if legend_right else 0.93
        height = 0.64 if self._legend_below() else 0.70
        return left, 0.14, max(0.20, right - left), height

    def _group_mode(self):
        """Group display mode as a string.

        Orange's combo box stores the item INDEX (int) unless sendSelectedValue
        is set. A workflow saved with an earlier build can still hold an int, so
        normalise here instead of assuming a string.
        """
        mode = self.group_mode
        if isinstance(mode, int) and 0 <= mode < len(GROUP_MODES):
            return GROUP_MODES[mode]
        return mode if mode in GROUP_MODES else GROUP_MODES[0]

    def _legend_pos(self):
        """Legend position as a string (same int/str caveat as _group_mode)."""
        pos = self.legend_pos
        if isinstance(pos, int) and 0 <= pos < len(LEGEND_POSITIONS):
            return LEGEND_POSITIONS[pos]
        return pos if pos in LEGEND_POSITIONS else LEGEND_POSITIONS[0]

    def _legend_is_box(self):
        return self._group_mode() == "bar + legend"

    def _legend_below(self):
        return self._legend_is_box() and self._legend_pos() == "below"

    def _draw_group_bar(self, ax, b, nC):
        """Colour bar above the heatmap, optionally with the group names on it."""
        if self._group_mode() == "none" or b["groups"] is None:
            return
        ax_bar = self.fig.add_axes(
            [ax.get_position().x0, ax.get_position().y1 + 0.01,
             ax.get_position().width, 0.035])
        for j, g in enumerate(b["groups"]):
            ax_bar.add_patch(Rectangle((j - 0.5, 0.15), 1, 0.7,
                                       facecolor=_color_for(g, b["levels"]),
                                       edgecolor="none"))
        ax_bar.set_xlim(-0.5, nC - 0.5)
        ax_bar.set_ylim(0, 1)
        if self._group_mode() == "bar + names" and nC <= 30:
            for j, g in enumerate(b["groups"]):
                ax_bar.text(j, 0.5, _short(g, 6), ha="center", va="center",
                            fontsize=5.5, color="white", rotation=90)
            ax_bar.set_xticks([])
        ax_bar.axis("off")

    def _draw_dendrogram(self, lk, bottom, height):
        """Row dendrogram in its own axes, aligned with the heatmap rows."""
        n = len(self._built["feats"])
        ax_den = self.fig.add_axes([0.03, bottom, 0.09, height])
        dendrogram(lk, orientation="left", no_labels=True, ax=ax_den,
                   color_threshold=0, above_threshold_color="#7f8c9b")
        # scipy places leaf k at y = 10k + 5 on a 0..10n axis. Inverting that
        # range lines leaf k up with imshow row k (whose range is n-0.5 .. -0.5);
        # using the row range here clipped the tree to its first ~10 %.
        ax_den.set_ylim(10 * n, 0)
        ax_den.set_xticks([])
        ax_den.tick_params(left=False)
        for side in ("top", "right", "bottom"):
            ax_den.spines[side].set_visible(False)

    def _draw_selection(self, ax):
        """Frame the row of every selected feature; mark the last clicked cell."""
        if self._built is None:
            return
        nR, nC = self._built["Z"].shape
        feats = self._built["feats"]
        for feat in self._selected:
            if feat in feats:
                row = feats.index(feat)
                ax.add_patch(Rectangle((-0.5, row - 0.5), nC, 1, fill=False,
                                       edgecolor="#111", linewidth=2.0))
        if self._cell is not None:
            row, col = self._cell
            if 0 <= row < nR and 0 <= col < nC:
                ax.add_patch(Rectangle((col - 0.5, row - 0.5), 1, 1, fill=False,
                                       edgecolor="#111", linewidth=1.0, ls=":"))

    def _legend(self, b, ax):
        """MetaboAnalyst-style legend listing the groups with their colours."""
        if not self._legend_is_box() or b["groups"] is None:
            return
        handles = [Patch(facecolor=_color_for(lv, b["levels"]), edgecolor="none",
                         label=str(lv)) for lv in b["levels"]]
        # de-duplicate while keeping the level order
        seen, uniq = set(), []
        for h in handles:
            if h.get_label() not in seen:
                seen.add(h.get_label())
                uniq.append(h)
        if self._legend_pos() == "below":
            leg = ax.legend(handles=uniq, loc="upper center",
                            bbox_to_anchor=(0.5, -0.32), ncol=min(4, len(uniq)),
                            frameon=False, fontsize=7.5, title="Group",
                            title_fontsize=8)
        else:
            leg = ax.legend(handles=uniq, loc="upper left",
                            bbox_to_anchor=(1.02, 1.0), frameon=False,
                            fontsize=8, title="Group", title_fontsize=8)
        draggable(leg)

    # ------------------------------------------------------------- selection
    def _on_canvas_click(self, ax, xdata, ydata):
        """Select the clicked cell's feature; shift-click adds/removes."""
        if self._built is None or ax is not self._ax_heat:
            return
        nR, nC = self._built["Z"].shape
        row, col = int(round(ydata)), int(round(xdata))
        if not (0 <= row < nR and 0 <= col < nC):
            self._selected = []                   # clicked empty space
            self._cell = None
        else:
            feat = self._built["feats"][row]
            if QApplication.keyboardModifiers() & Qt.ShiftModifier:
                self._selected = ([f for f in self._selected if f != feat]
                                  if feat in self._selected
                                  else self._selected + [feat])
            else:
                self._selected = [] if self._selected == [feat] else [feat]
            self._cell = (row, col)
        self._new_view = False        # keep the current zoom
        self._draw()                  # sends the outputs (no deferred commit here)

    # ------------------------------------------------------------ lasso / sel
    def _lasso_toggled(self):
        self.canvas.lasso_enabled = bool(self.lasso)
        self.canvas.on_lasso = self._lasso_select if self.lasso else None

    def _lasso_select(self, ax, polygon):
        """Add the features of every cell inside the lasso polygon."""
        if self._built is None or ax is not self._ax_heat:
            return
        nR, nC = self._built["Z"].shape
        ys, xs = np.mgrid[0:nR, 0:nC]
        cells = np.column_stack([xs.ravel(), ys.ravel()])      # (x, y) = (col, row)
        idx = points_in_polygon(cells, polygon)
        if len(idx) == 0:
            return
        rows = sorted({int(i) // nC for i in idx})
        feats = [self._built["feats"][r] for r in rows]
        self._selected = list(dict.fromkeys(self._selected + feats))
        self._cell = (rows[0], int(idx[0]) % nC)
        self._draw()

    def _clear_selection(self):
        self._selected = []
        self._cell = None
        self._draw()

    def _update_sel_label(self):
        if not self._selected:
            self.sel_lbl.setText("No feature selected.")
        else:
            self.sel_lbl.setText(f"<b>{len(self._selected)}</b> selected: "
                                 + ", ".join(_short(f, 14)
                                             for f in self._selected[:4])
                                 + ("…" if len(self._selected) > 4 else ""))

    def _selected_data_table(self):
        """The original data restricted to the selected features (samples x
        features, class and metas kept) - ready for the Data Table widget."""
        return select_features(self.data, self._selected)

    def _feature_of_interest(self):
        """The feature the details and distribution panels describe."""
        b = self._built
        if b is None:
            return None
        if self._cell is not None:
            row, _col = self._cell
            if 0 <= row < len(b["feats"]):
                return b["feats"][row]
        return self._selected[0] if self._selected else None

    def _draw_distribution(self, *_):
        """Distribution of the selected feature over the individual samples.

        Bars: the chosen aggregate per group (Mean / Median / Sum). Dots: the
        single samples, jittered, so the spread within a group stays visible.
        Values are on the input scale (whatever the upstream widget delivered,
        e.g. log2 peak areas) - NOT z-scores.
        """
        c = self.dist_canvas
        c.fig.clear()
        ax = c.fig.add_subplot(111)
        b, feat = self._built, self._feature_of_interest()

        if b is None or feat is None or b["groups"] is None:
            ax.axis("off")
            ax.text(0.5, 0.5, "Click a heatmap cell to see the distribution of "
                              "its feature over the samples.",
                    ha="center", va="center", fontsize=9, color="#6b7684")
            c.after_draw(ax, new_data=True)
            c.draw_idle()
            return

        y = np.asarray(b["raw"][b["feats"].index(feat)], dtype=float)
        groups, levels = b["groups"], b["levels"]
        order = [lv for lv in levels if lv in set(groups)]
        vals = [[v for v, g in zip(y, groups) if g == lv] for lv in order]
        agg = {"Mean": np.mean, "Median": np.median, "Sum": np.sum}[self.agg]

        x = np.arange(len(order))
        ax.bar(x, [float(agg(v)) for v in vals],
               color=[_color_for(lv, levels) for lv in order],
               alpha=0.55, edgecolor="none", zorder=1)
        rng = np.random.RandomState(7)                 # stable jitter
        for i, v in enumerate(vals):
            ax.scatter(i + (rng.rand(len(v)) - 0.5) * 0.34, v, s=16,
                       c="#2b2b2b", linewidths=0, zorder=3)
        ax.set_xticks(x)
        ax.set_xticklabels([_short(lv, 16) for lv in order], fontsize=8)
        ax.set_ylabel(f"{self.agg.lower()} per group", fontsize=8)
        ax.set_title(_short(feat, 80), fontsize=9)
        ax.tick_params(labelsize=7)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        leg = ax.legend(handles=[Patch(facecolor=_color_for(lv, levels),
                                       alpha=0.55, label=lv) for lv in order],
                        loc="best", fontsize=7)
        draggable(leg)
        c.fig.tight_layout()
        c.after_draw(ax, new_data=True)
        c.draw_idle()

    def _info_text(self):
        b, cell = self._built, self._cell
        if b is None or cell is None:
            return "Click a heatmap cell to see the feature's details."
        row, col = cell
        feat = b["feats"][row]
        z = b["Z"][row, col]
        raw = b["raw"][row, col]
        sample = (b["samples"][col] if b["samples"] else f"sample {col}")
        group = (b["groups"][col] if b["groups"] else "-")
        parts = [f"<b>{feat}</b>"]
        rank = f"ranked by {self._ranking_source}"
        p = (self._p_by_feature or {}).get(feat)
        if p is not None:
            rank += f", p = {p:.2e}"
            if self._ranking_source == "results":
                rank += " (Results)"
        parts.append(f"<span style='color:#555'>{rank}</span>")
        parts.append(f"Cell: <b>{sample}</b> · group {group} · "
                     f"z = {z:+.2f} · value = {raw:.4g}")
        means = []
        if b["groups"] is not None:
            for lv in b["levels"]:
                idx = [j for j, g in enumerate(b["groups"]) if g == lv]
                if idx:
                    means.append(f"{lv}: {b['raw'][row, idx].mean():.4g}")
        if means:
            parts.append("<span style='color:#555'>group means (value space): "
                         + " · ".join(means) + "</span>")
        return "<br>".join(parts)

    # ------------------------------------------------------------------ output
    def _send_output(self, Z, top_feats, sample_names, groups):
        if self.data is None:
            self.Outputs.heatmap.send(None)
            return
        attrs = [ContinuousVariable(f) for f in top_feats]
        metas = []
        if sample_names:
            metas.append(StringVariable("sample"))
        if groups is not None:
            metas.append(StringVariable("group"))
        dom = Domain(attrs, metas=metas)
        if metas:
            rows = []
            for i in range(Z.shape[1]):
                row = []
                if sample_names:
                    row.append(sample_names[i])
                if groups is not None:
                    row.append(groups[i])
                rows.append(row)
            m = np.array(rows, dtype=object)
        else:
            m = None
        out = Table.from_numpy(dom, X=Z.T, metas=m)
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
        self.Outputs.selected_data.send(None)
        super().close()


def _short(name, n=30):
    return name if len(name) <= n else name[:n - 1] + "…"


def _color_for(group, levels):
    try:
        i = levels.index(group)
    except ValueError:
        i = 0
    return GROUP_COLORS[i % len(GROUP_COLORS)]
