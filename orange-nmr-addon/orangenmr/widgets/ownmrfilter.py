"""
NMR Filter widget — Savitzky-Golay smoothing and derivatives.

Applies Savitzky-Golay convolution to each spectrum:
- Window length (odd, in data points)
- Polynomial order
- Derivative order (0 = smooth only, 1 = 1st derivative, 2 = 2nd)
"""

import numpy as np
from scipy.signal import savgol_filter
from AnyQt.QtCore import Qt

from Orange.data import Table, Domain
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .nmr_utils import get_ppm_values, make_ppm_attributes


class OWFilter(OWWidget):
    name = "NMR Filter (Savitzky-Golay)"
    description = "Smooth and/or differentiate NMR spectra " \
                  "using Savitzky-Golay convolution."
    icon = "icons/NMRFilter.svg"
    priority = 1030
    keywords = ["nmr", "filter", "savitzky-golay", "smooth", "derivative"]

    class Inputs:
        data = Input("Spectra", Table)

    class Outputs:
        data = Output("Filtered Spectra", Table)

    class Warning(OWWidget.Warning):
        window_too_large = Msg("Window length exceeds data length — clamped.")
        odd_window = Msg("Window length adjusted to odd value.")

    window_length = Setting(11)
    poly_order = Setting(2)
    deriv_order = Setting(0)
    auto_apply = Setting(True)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.data = None

        box = gui.vBox(self.controlArea, "Savitzky-Golay")
        gui.spin(box, self, "window_length", 3, 101, 2,
                 label="Window length (points):",
                 alignment=Qt.AlignRight, controlWidth=80,
                 callback=self._on_changed)
        gui.spin(box, self, "poly_order", 1, 10, 1,
                 label="Polynomial order:",
                 alignment=Qt.AlignRight, controlWidth=80,
                 callback=self._on_changed)
        gui.spin(box, self, "deriv_order", 0, 2, 1,
                 label="Derivative order:",
                 alignment=Qt.AlignRight, controlWidth=80,
                 callback=self._on_changed)
        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

    def _on_changed(self):
        # ensure odd window
        if self.window_length % 2 == 0:
            self.window_length += 1
            self.Warning.odd_window()
        else:
            self.Warning.odd_window.clear()
        self.apply()

    @Inputs.data
    def set_data(self, data):
        self.data = data
        self.apply()

    def apply(self):
        if self.data is None:
            self.Outputs.data.send(None)
            return

        X = self.data.X
        n_cols = X.shape[1]
        ppm = get_ppm_values(self.data)

        wl = min(self.window_length, n_cols)
        if wl != self.window_length:
            self.Warning.window_too_large()
        else:
            self.Warning.window_too_large.clear()

        if wl % 2 == 0:
            wl += 1

        X_filt = np.full_like(X, np.nan)
        for i in range(X.shape[0]):
            valid = ~np.isnan(X[i, :])
            if valid.sum() < wl:
                continue
            X_filt[i, valid] = savgol_filter(
                X[i, valid], wl, self.poly_order, deriv=self.deriv_order
            )

        # For derivatives, the x-axis changes (ppm units become
        # intensity/ppm, etc.) but we keep the original ppm axis for
        # simplicity
        domain = Domain(self.data.domain.attributes,
                        self.data.domain.class_vars,
                        self.data.domain.metas)
        out = Table(domain, X_filt, self.data.Y,
                    metas=self.data.metas if self.data.domain.metas else None)
        label = "smooth" if self.deriv_order == 0 else f"deriv{self.deriv_order}"
        out.name = f"{self.data.name} (SG-{label})"
        self.Outputs.data.send(out)

    def send_report(self):
        self.report_items("SG Filter",
                          [("Window", f"{self.window_length} pts"),
                           ("Poly order", self.poly_order),
                           ("Derivative", self.deriv_order)])