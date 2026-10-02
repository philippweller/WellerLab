"""
NMR Baseline Correction widget — fit and subtract baseline from NMR spectra.

Methods:
- Polynomial: fit nth-order polynomial to selected baseline points
- Asymmetric Least Squares (ALS): Whittaker smoother-based baseline
"""

from AnyQt.QtCore import Qt
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import spsolve

from Orange.data import Table, Domain
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .nmr_utils import get_ppm_values


class OWBaseline(OWWidget):
    name = "NMR Baseline Correction"
    description = "Remove baseline drift from NMR spectra using " \
                  "polynomial fitting or asymmetric least squares."
    icon = "icons/NMRBaseline.svg"
    priority = 1020
    keywords = ["nmr", "baseline", "correction", "subtract", "als"]

    class Inputs:
        data = Input("Spectra", Table)

    class Outputs:
        data = Output("Baseline-corrected Spectra", Table)

    method_idx = Setting(0)
    _methods = ["Polynomial", "Asymmetric Least Squares (ALS)"]

    # Polynomial
    poly_order = Setting(3)

    # ALS
    als_lambda = Setting(100_000.0)
    als_p = Setting(0.01)
    als_niter = Setting(10)
    auto_apply = Setting(True)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.data = None

        box = gui.vBox(self.controlArea, "Baseline Correction")
        gui.comboBox(box, self, "method_idx", label="Method:",
                     items=self._methods,
                     callback=self._on_method,
                     orientation=Qt.Horizontal)

        # Polynomial settings
        self.poly_box = gui.vBox(self.controlArea, "Polynomial", flat=True)
        gui.spin(self.poly_box, self, "poly_order", 1, 10, 1,
                 label="Polynomial order:", callback=self.apply,
                 alignment=Qt.AlignRight, controlWidth=80)

        # ALS settings
        self.als_box = gui.vBox(self.controlArea, "ALS Parameters", flat=True)
        self.als_box.setVisible(False)
        gui.doubleSpin(self.als_box, self, "als_lambda", 1e2, 1e9, 10_000,
                       label="Lambda (smoothness):", controlWidth=120,
                       callback=self.apply)
        gui.doubleSpin(self.als_box, self, "als_p", 0.001, 0.5, 0.005,
                       label="Asymmetry (p):", controlWidth=80, decimals=3,
                       callback=self.apply)
        gui.spin(self.als_box, self, "als_niter", 1, 50, 1,
                 label="Iterations:", alignment=Qt.AlignRight,
                 controlWidth=80, callback=self.apply)

        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

    def _on_method(self):
        self.poly_box.setVisible(self.method_idx == 0)
        self.als_box.setVisible(self.method_idx == 1)
        self.apply()

    @Inputs.data
    def set_data(self, data):
        self.data = data
        self.apply()

    def apply(self):
        if self.data is None:
            self.Outputs.data.send(None)
            return

        X = self.data.X.copy()
        ppm = get_ppm_values(self.data)
        n = X.shape[0]
        X_corr = X.copy()

        if self.method_idx == 0:    # Polynomial
            for i in range(n):
                valid = ~np.isnan(X[i, :])
                if valid.sum() < 2:
                    continue
                coef = np.polyfit(ppm[valid], X[i, valid], self.poly_order)
                baseline = np.polyval(coef, ppm)
                X_corr[i, :] = X[i, :] - baseline

        elif self.method_idx == 1:  # ALS
            L = self.als_lambda
            p = self.als_p
            niter = self.als_niter
            m = len(ppm)
            D = sparse.diags([1, -2, 1], [0, -1, -2], shape=(m, m - 2))
            for i in range(n):
                y = X[i, :]
                valid = ~np.isnan(y)
                if valid.sum() < 2:
                    continue
                yv = y[valid].copy()
                mv = valid.sum()
                Dv = sparse.diags([1, -2, 1], [0, -1, -2],
                                  shape=(mv, mv - 2))
                w = np.ones(mv)
                for _ in range(niter):
                    W = sparse.diags(w, 0, shape=(mv, mv))
                    A = W + L * (Dv @ Dv.T)
                    z = spsolve(A, w * yv)
                    w = p * (yv > z) + (1 - p) * (yv <= z)
                # expand back to full array
                z_full = np.full(m, np.nan)
                z_full[valid] = z
                X_corr[i, :] -= z_full

        domain = Domain(self.data.domain.attributes,
                        self.data.domain.class_vars,
                        self.data.domain.metas)
        out = Table(domain, X_corr, self.data.Y,
                    metas=self.data.metas if self.data.domain.metas else None)
        out.name = f"{self.data.name} (baseline)"
        self.Outputs.data.send(out)

    def send_report(self):
        self.report_items("Baseline Correction",
                          [("Method", self._methods[self.method_idx])])