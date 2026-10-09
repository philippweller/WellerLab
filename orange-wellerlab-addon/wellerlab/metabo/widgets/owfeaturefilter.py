"""Feature Filter — drop features by missing values, zero variance, or
below-detection threshold. Operates on the metabolomics orientation
(rows = samples, attributes = features) and keeps the surviving columns.
"""

import numpy as np

from Orange.data import Table, Domain
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Input, Output


class OWFeatureFilter(widget.OWWidget):
    name = "Metabo Feature Filter"
    description = ("Remove features with too many missing values, zero "
                   "variance, or below a detection threshold.")
    icon = "icons/FeatureFilter.svg"
    priority = 3130
    keywords = "filter, qc, missing, constant, threshold, feature selection"

    want_main_area = False
    resizing_enabled = False

    class Inputs:
        data = Input("Feature Data", Table)

    class Outputs:
        data = Output("Filtered Data", Table)

    # settings
    use_missing = Setting(True)
    max_missing_frac = Setting(0.20)   # fraction of samples allowed missing
    use_zero_var = Setting(True)
    use_constant = Setting(True)       # drop features that are all-equal
    use_threshold = Setting(False)
    threshold_val = Setting(0.0)       # absolute value below = "not detected"
    min_below_frac = Setting(0.50)     # drop if this fraction is below threshold
    auto_commit = Setting(True)

    def __init__(self):
        super().__init__()
        self.data = None

        box = gui.widgetBox(self.controlArea, "Filters")
        gui.checkBox(box, self, "use_missing",
                     "Drop features with too many missing values",
                     callback=self._recompute)
        self.miss_spin = gui.doubleSpin(
            box, self, "max_missing_frac", 0.0, 1.0, 0.05,
            label="Max missing fraction:", callback=self._recompute, decimals=2)
        gui.checkBox(box, self, "use_zero_var",
                     "Drop zero-variance features", callback=self._recompute)
        gui.checkBox(box, self, "use_constant",
                     "Drop constant features", callback=self._recompute)
        gui.checkBox(box, self, "use_threshold",
                     "Drop features mostly below threshold", callback=self._recompute)
        self.thr_spin = gui.doubleSpin(
            box, self, "threshold_val", 0.0, 1e9, 1.0,
            label="Detection threshold:", callback=self._recompute, decimals=0)
        self.below_spin = gui.doubleSpin(
            box, self, "min_below_frac", 0.0, 1.0, 0.05,
            label="Min fraction below threshold:", callback=self._recompute,
            decimals=2)

        gui.rubber(self.controlArea)
        gui.auto_apply(self.buttonsArea, self, "auto_commit")

    @Inputs.data
    def set_data(self, data):
        self.data = data
        if data is None or len(data) == 0 or not data.domain.attributes:
            self.error("No feature data supplied.")
            self.Outputs.data.send(None)
            return
        self.error()
        self._recompute()

    def _recompute(self):
        if self.data is None:
            return
        X = np.asarray(self.data.X, dtype=float)  # samples x features
        n, p = X.shape
        keep = np.ones(p, dtype=bool)
        stats = []

        if self.use_missing:
            miss_frac = np.isnan(X).mean(axis=0)
            keep &= miss_frac <= self.max_missing_frac
            stats.append(f"missing≤{self.max_missing_frac:.0%}: "
                         f"drop {int((miss_frac > self.max_missing_frac).sum())}")
        if self.use_zero_var:
            # variance ignoring NaN
            vv = np.nanstd(X, axis=0)
            zz = (vv < 1e-12) & np.isfinite(vv)
            keep &= ~zz
            stats.append(f"zero-var: drop {int(zz.sum())}")
        if self.use_constant:
            # constant = all non-NaN values equal
            const = np.zeros(p, dtype=bool)
            for j in range(p):
                col = X[:, j]
                col = col[~np.isnan(col)]
                const[j] = col.size > 0 and (col.max() - col.min()) < 1e-12
            keep &= ~const
            stats.append(f"constant: drop {int(const.sum())}")
        if self.use_threshold:
            below = (X < self.threshold_val).mean(axis=0)
            drop = below >= self.min_below_frac
            keep &= ~drop
            stats.append(f"below {self.threshold_val:g}: drop {int(drop.sum())}")

        self._keep = keep
        self.information(
            f"{int(keep.sum())}/{p} features kept · " +
            (" · ".join(stats) if stats else "no filters active"))
        self.commit.now() if self.auto_commit else self.commit.deferred()

    @gui.deferred
    def commit(self):
        if self.data is None or getattr(self, "_keep", None) is None:
            self.Outputs.data.send(None)
            return
        keep = self._keep
        dom = Domain(
            [self.data.domain.attributes[j] for j in range(len(keep)) if keep[j]],
            self.data.domain.class_vars, self.data.domain.metas)
        X = self.data.X[:, keep]
        out = Table.from_numpy(
            dom, X=X,
            metas=self.data.metas if self.data.domain.metas else None)
        out.name = "filtered"
        self.Outputs.data.send(out)

    def close(self):
        self.Outputs.data.send(None)
        super().close()
