"""Metabo Preprocess — normalisation, imputation, log2, scaling.

Pipeline order (MetaboAnalyst-style):
    raw -> [imputation] -> sum-normalise -> log2 -> scaling
With all toggles off (default) this exactly reproduces the validated
ground-truth pipeline (sum-normalise -> log2 -> autoscale).

Input/Output are Orange Tables in the metabolomics orientation:
  rows = samples, columns (attributes) = features, metas = sample/group.
"""

import numpy as np

from Orange.data import Table, Domain, ContinuousVariable
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output

from .. import metabo_core as mc


class OWMetaboPreprocess(widget.OWWidget):
    name = "Metabo Preprocess"
    description = ("MetaboAnalyst-style preprocessing: sum-normalisation, "
                   "imputation, log2, and autoscale/pareto scaling.")
    icon = "icons/Preprocess.svg"
    priority = 3120
    keywords = "preprocess, normalise, log2, autoscale, pareto, imputation"

    want_main_area = False
    resizing_enabled = False

    NORMS = ("none", "sum")
    NORM_LABELS = ("None", "Sum (total area)")
    IMPUTES = ("none", "min", "knn")
    IMPUTE_LABELS = ("None", "Column minimum", "k-NN (mean of k nearest)")
    SCALES = ("none", "autoscale", "pareto")
    SCALE_LABELS = ("None", "Autoscale (z-score)", "Pareto")

    class Inputs:
        data = Input("Feature Data", Table)

    class Outputs:
        data = Output("Preprocessed Data", Table)

    # settings (integer indices into the tuples above)
    norm = Setting(0)
    do_log2 = Setting(True)
    impute = Setting(0)
    impute_threshold = Setting(0.05)
    impute_k = Setting(3)
    scale = Setting(0)
    auto_commit = Setting(True)

    def __init__(self):
        super().__init__()
        self.data = None

        box = gui.widgetBox(self.controlArea, "Normalisation")
        gui.comboBox(box, self, "norm", items=self.NORM_LABELS,
                     label="Method:", callback=self._recompute)
        gui.checkBox(box, self, "do_log2", "Apply log2 transform",
                     callback=self._recompute)

        ibox = gui.widgetBox(self.controlArea, "Imputation")
        gui.comboBox(ibox, self, "impute", items=self.IMPUTE_LABELS,
                     label="Method:", callback=self._recompute)
        self.thr_spin = gui.doubleSpin(
            ibox, self, "impute_threshold", 0.001, 0.5, 0.005,
            label="Low-value fraction:", callback=self._recompute, decimals=3)
        self.k_spin = gui.spin(ibox, self, "impute_k", 1, 20,
                               label="k:", callback=self._recompute)

        sbox = gui.widgetBox(self.controlArea, "Scaling")
        gui.comboBox(sbox, self, "scale", items=self.SCALE_LABELS,
                     label="Method:", callback=self._recompute)

        gui.rubber(self.controlArea)
        gui.auto_apply(self.buttonsArea, self, "auto_commit")
        self._recalc_enabled()

    def _recalc_enabled(self):
        im = self.IMPUTES[self._i(self.impute)] if 0 <= self.impute < len(self.IMPUTES) else "none"
        on = im != "none"
        for w in (self.thr_spin, self.k_spin):
            try:
                w.setEnabled(on)
            except Exception:
                pass

    def _i(self, idx, n=None):
        if n is None:
            n = 1
        return idx if 0 <= idx < n else 0

    def _norm(self):
        return self.NORMS[self._i(self.norm, len(self.NORMS))]

    def _impute(self):
        return self.IMPUTES[self._i(self.impute, len(self.IMPUTES))]

    def _scale(self):
        return self.SCALES[self._i(self.scale, len(self.SCALES))]

    # ------------------------------------------------------------------ input
    @Inputs.data
    def set_data(self, data):
        self.data = data
        if data is None or len(data) == 0 or not data.domain.attributes:
            self.error("No feature data supplied.")
            self.Outputs.data.send(None)
            return
        self.error()
        self._recompute()

    # ------------------------------------------------------------------ core
    def _recompute(self):
        if self.data is None:
            return
        X_sf = np.asarray(self.data.X, dtype=float)   # samples x features
        X_f = X_sf.T                                  # features x samples
        # 1. imputation (on raw, before normalisation/log2)
        im = self._impute()
        n_imp = 0
        if im != "none":
            X_f, mask = mc.impute_low(X_f, self.impute_threshold, im, self.impute_k)
            n_imp = int(mask.sum())
        # 2. normalisation
        if self._norm() == "sum":
            X_f = mc.normalize_sum(X_f)
        # 3. log2
        if self.do_log2:
            X_f = mc.log2_transform(X_f)
        # 4. scaling
        X_f = mc.scale_rows(X_f, self._scale())
        self._processed = X_f
        self._n_imp = n_imp

        self.information(
            f"{self.data.X.shape[0]} samples × {self.data.X.shape[1]} features"
            + (f" · imputed {n_imp} low values" if n_imp else ""))

        self.commit.now() if self.auto_commit else self.commit.deferred()

    # ------------------------------------------------------------------ output
    @gui.deferred
    def commit(self):
        if getattr(self, "_processed", None) is None or self.data is None:
            self.Outputs.data.send(None)
            return
        X_f = self._processed                # features x samples
        X_sf = X_f.T                         # samples x features
        dom = Domain(list(self.data.domain.attributes),
                     self.data.domain.class_vars,
                     self.data.domain.metas)
        out = Table.from_numpy(
            dom, X=X_sf,
            metas=self.data.metas if self.data.domain.metas else None)
        out.name = "preprocessed"
        self.Outputs.data.send(out)

    def close(self):
        self.Outputs.data.send(None)
        super().close()
