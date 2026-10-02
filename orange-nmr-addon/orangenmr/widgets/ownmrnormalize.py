"""
NMR Normalization widget — scale NMR spectra to a common intensity level.

Methods:
- Total Area: scale so sum(intensity) = 1
- Maximum: scale so max(intensity) = 1
- Unit Length: scale so sum(intensity²) = 1 (L2 norm)
- Reference Region: scale so mean intensity of a user-specified region = 1
"""

from AnyQt.QtCore import Qt
import numpy as np

from Orange.data import Table, Domain
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .nmr_utils import get_ppm_values


class OWNormalization(OWWidget):
    name = "NMR Normalization"
    description = "Scale NMR spectra to a common intensity level " \
                  "(total area, maximum, unit length, or reference region)."
    icon = "icons/NMRNormalize.svg"
    priority = 1010
    keywords = ["nmr", "normalization", "normalize", "area", "pqn"]

    class Inputs:
        data = Input("Spectra", Table)

    class Outputs:
        data = Output("Normalized Spectra", Table)

    class Warning(OWWidget.Warning):
        all_nan = Msg("Normalization failed — spectrum is all NaN.")
        zero_region = Msg("Reference region has zero intensity.")

    method_idx = Setting(0)
    _methods = ["Total Area (sum=1)", "Maximum (max=1)",
                "Unit Length (L2=1)", "Reference Region"]
    norm_ref_low = Setting(0.0)
    norm_ref_high = Setting(10.0)
    auto_apply = Setting(True)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.data = None

        box = gui.vBox(self.controlArea, "Normalization")
        gui.comboBox(box, self, "method_idx", label="Method:",
                     items=self._methods,
                     callback=self._on_changed,
                     orientation=Qt.Horizontal)

        self.ref_box = gui.vBox(self.controlArea, "Reference Region",
                                flat=True)
        self.ref_box.setVisible(False)
        gui.label(self.ref_box, self, "PPM range for reference scaling:")
        hb = gui.hBox(self.ref_box)
        gui.doubleSpin(hb, self, "norm_ref_low", -100, 100, 0.01,
                       label="From: ", controlWidth=80, decimals=2,
                       callback=self._on_changed)
        gui.doubleSpin(hb, self, "norm_ref_high", -100, 100, 0.01,
                       label="To: ", controlWidth=80, decimals=2,
                       callback=self._on_changed)

        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

    def _on_changed(self):
        self.ref_box.setVisible(self.method_idx == 3)
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

        method = self.method_idx
        scale = np.ones(X.shape[0])

        if method == 0:          # Total Area
            s = np.nansum(np.abs(X), axis=1)
            s[s == 0] = np.nan
            scale = 1.0 / s
        elif method == 1:        # Maximum
            s = np.nanmax(np.abs(X), axis=1)
            s[s == 0] = np.nan
            scale = 1.0 / s
        elif method == 2:        # Unit Length (L2)
            s = np.sqrt(np.nansum(X ** 2, axis=1))
            s[s == 0] = np.nan
            scale = 1.0 / s
        elif method == 3:        # Reference Region
            lo, hi = min(self.norm_ref_low, self.norm_ref_high), \
                     max(self.norm_ref_low, self.norm_ref_high)
            mask = (ppm >= lo) & (ppm <= hi)
            if mask.sum() == 0:
                self.Warning.zero_region()
                self.Outputs.data.send(self.data)
                return
            s = np.nanmean(np.abs(X[:, mask]), axis=1)
            s[s == 0] = np.nan
            scale = 1.0 / s

        scale = np.nan_to_num(scale, nan=1.0).reshape(-1, 1)
        X_norm = X * scale
        self.Warning.all_nan.clear()

        domain = Domain(self.data.domain.attributes,
                        self.data.domain.class_vars,
                        self.data.domain.metas)
        out = Table(domain, X_norm, self.data.Y,
                    metas=self.data.metas if self.data.domain.metas else None)
        out.name = f"{self.data.name} (norm)"
        self.Outputs.data.send(out)

    def send_report(self):
        self.report_items("Normalization",
                          [("Method", self._methods[self.method_idx])])