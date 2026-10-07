"""Univariate Statistics — MetaboAnalyst-style one-way ANOVA, Welch t-test,
or Kruskal-Wallis per feature, with Benjamini-Hochberg FDR and log2FC.

Reads an Orange Table (rows = samples, attributes = features, meta "group"),
runs the selected test on every feature, and emits a results Table (one row
per feature) sorted by p-value.
"""

import numpy as np

from Orange.data import Table, Domain, ContinuousVariable, StringVariable
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output

from .. import metabo_core as mc


class OWUnivariateStats(widget.OWWidget):
    name = "Metabo Univariate Stats"
    description = ("One-way ANOVA, Welch t-test, or Kruskal-Wallis per "
                   "feature with Benjamini-Hochberg FDR and log2FC.")
    icon = "icons/UnivariateStats.svg"
    priority = 3140
    keywords = "anova, t-test, welch, kruskal, fdr, biomarker, univariate"

    want_main_area = False
    resizing_enabled = False

    METHODS = ("anova", "welch", "kruskal")
    METHOD_LABELS = ("One-way ANOVA", "Welch two-sample t-test",
                     "Kruskal-Wallis")

    class Inputs:
        data = Input("Preprocessed Data", Table)

    class Outputs:
        results = Output("Results", Table, default=True)

    # settings
    method = Setting(0)          # index into METHODS
    base_group = Setting(0)      # index into available groups (for welch)
    treat_groups = Setting("")   # comma-separated group names (for welch)
    fdr_alpha = Setting(0.05)
    auto_commit = Setting(True)

    def __init__(self):
        super().__init__()
        self.data = None
        self._groups = []
        self._groups_list = []

        box = gui.widgetBox(self.controlArea, "Test")
        gui.comboBox(box, self, "method", items=self.METHOD_LABELS,
                     label="Method:", callback=self._recompute)
        # base + treat only meaningful for welch
        from AnyQt.QtWidgets import QLineEdit
        self.base_box = gui.widgetBox(box, "Contrast (Welch)")
        self.base_combo = gui.comboBox(
            self.base_box, self, "base_group", label="Base group:",
            callback=self._recompute)
        self.treat_edit = QLineEdit(self.base_box)
        self.treat_edit.setPlaceholderText("test groups, comma-separated")
        self.treat_edit.textChanged.connect(self._on_treat_text)
        gui.label(self.base_box, self,
                  "Test groups (comma-separated):")
        gui.doubleSpin(box, self, "fdr_alpha", 0.001, 0.5, 0.005,
                       label="FDR threshold:", callback=self._recompute,
                       decimals=3)

        gui.rubber(self.controlArea)
        gui.auto_apply(self.buttonsArea, self, "auto_commit")

    # ------------------------------------------------------------------ input
    @Inputs.data
    def set_data(self, data):
        self.data = data
        if data is None or len(data) == 0 or not data.domain.attributes:
            self.error("No data supplied.")
            self.Outputs.results.send(None)
            return
        self.error()
        self._read_groups()
        self._recompute()

    def _read_groups(self):
        from AnyQt.QtGui import QStandardItem, QStandardItemModel
        gvar = self.data.domain["group"] if "group" in self.data.domain else None
        if gvar is None:
            self._groups = []
            self._groups_list = []
            return
        vals = self.data.metas[:, self.data.domain.metas.index(gvar)]
        self._groups = [str(v) for v in vals]
        self._groups_list = list(dict.fromkeys(self._groups))
        # populate the base combo
        model = QStandardItemModel()
        for g in self._groups_list:
            model.appendRow(QStandardItem(g))
        self.base_combo.setModel(model)
        if 0 <= self.base_group < len(self._groups_list):
            self.base_combo.setCurrentIndex(self.base_group)
        else:
            self.base_group = 0
            self.base_combo.setCurrentIndex(0)
        # treat default: all other groups
        if self.base_group < len(self._groups_list):
            others = [g for g in self._groups_list
                      if g != self._groups_list[self.base_group]]
            self.treat_groups = ",".join(others)
        self.treat_edit.blockSignals(True)
        self.treat_edit.setText(self.treat_groups or "")
        self.treat_edit.blockSignals(False)

    def _on_treat_text(self, text):
        self.treat_groups = text
        self._recompute()

    # ------------------------------------------------------------------ core
    def _recompute(self):
        if self.data is None:
            return
        X_sf = np.asarray(self.data.X, dtype=float)   # samples x features
        X_f = X_sf.T                                  # features x samples
        feat = [a.name for a in self.data.domain.attributes]
        method = self.METHODS[self.method] if 0 <= self.method < len(self.METHODS) else "anova"

        base = treat = None
        if method == "welch":
            if self._groups_list and 0 <= self.base_group < len(self._groups_list):
                base = self._groups_list[self.base_group]
            treats = [t.strip() for t in (self.treat_groups or "").split(",") if t.strip()]
            if not treats:
                self.error("Welch: pick a base and at least one test group.")
                self.Outputs.results.send(None)
                return
            treat = treats

        try:
            df, levels = mc.univariate(
                X_f, self._groups, method=method,
                base=base, treats=treat, feature_names=feat)
            # per-group means (in the supplied/log2 space)
            df = mc.add_group_means(df, X_f, self._groups, levels,
                                    feature_names=feat)
        except Exception as exc:
            self.error(f"Statistics failed: {exc}")
            self.Outputs.results.send(None)
            return
        self._df = df
        self._levels = levels
        nsig = int((df["FDR_BH"] < self.fdr_alpha).sum())
        self.information(
            f"{len(df)} features · {len(levels)} groups ({', '.join(levels)}) · "
            f"{nsig} significant at FDR<{self.fdr_alpha:g}")
        self.commit.now() if self.auto_commit else self.commit.deferred()

    # ------------------------------------------------------------------ output
    @gui.deferred
    def commit(self):
        df = getattr(self, "_df", None)
        if df is None or df.empty:
            self.Outputs.results.send(None)
            return
        cols = ["Feature", "stat", "p", "FDR_BH"]
        if "log2FC" in df.columns:
            cols.insert(3, "log2FC")
        for lv in getattr(self, "_levels", []):
            if f"mean_{lv}" in df.columns:
                cols.append(f"mean_{lv}")
        # group means (log2-space, i.e. on the supplied data)
        if self.data is not None and self._groups:
            if "log2FC" in df.columns and "mean_" not in "".join(cols[2:]):
                pass
        attrs = [ContinuousVariable(c) for c in cols[1:]]
        dom = Domain(attrs, metas=[StringVariable("Feature")])
        X = df[cols[1:]].to_numpy(dtype=float)
        m = df["Feature"].to_numpy(dtype=object).reshape(-1, 1)
        out = Table.from_numpy(dom, X=X, metas=m)
        out.name = "univariate results"
        self.Outputs.results.send(out)

    def close(self):
        self.Outputs.results.send(None)
        super().close()
