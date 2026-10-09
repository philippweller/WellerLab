"""
NMR Binning widget — reduce spectral resolution by averaging into wider buckets.

Spectral data points are grouped into bins of a specified width (in ppm).
Within each bin, values are aggregated via mean, sum, or max.
"""

from AnyQt.QtCore import Qt
import numpy as np

from Orange.data import Table, Domain, ContinuousVariable
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .nmr_utils import get_ppm_values, make_ppm_attributes, strip_nan_columns


class OWBinning(OWWidget):
    name = "NMR Binning (Bucketing)"
    description = "Reduce NMR spectral resolution by binning data points " \
                  "into wider buckets."
    icon = "icons/NMRBinning.svg"
    priority = 1000
    keywords = ["nmr", "binning", "bucketing", "bin", "bucket"]

    class Inputs:
        data = Input("Spectra", Table)

    class Outputs:
        data = Output("Binned Spectra", Table)

    class Warning(OWWidget.Warning):
        no_ppm = Msg("Could not parse ppm axis from attribute names.")
        too_few_bins = Msg("Bin width too large — only 1 bin remains.")

    auto_apply = Setting(True)
    bin_width = Setting(0.04)
    method_idx = Setting(0)
    _methods = ["Mean", "Sum", "Max"]
    _methods_fn = [np.mean, np.sum, np.max]

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.data = None

        box = gui.vBox(self.controlArea, "Binning")
        gui.label(box, self, "Bin width (ppm):")
        gui.doubleSpin(box, self, "bin_width", 1e-4, 1.0, 1e-3,
                 label="", decimals=4,
                 alignment=Qt.AlignRight, controlWidth=120,
                 callback=self._on_params_changed)
        gui.comboBox(box, self, "method_idx", label="Aggregation:",
                     items=self._methods,
                     callback=self._on_params_changed,
                     orientation=Qt.Horizontal)
        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

    @Inputs.data
    def set_data(self, data):
        self.data = data
        self.apply()

    def _on_params_changed(self):
        self.apply()

    def apply(self):
        if self.data is None:
            self.Outputs.data.send(None)
            return

        X = self.data.X
        ppm = get_ppm_values(self.data)

        if len(ppm) != X.shape[1]:
            self.Warning.no_ppm()
            self.Outputs.data.send(self.data)
            return
        self.Warning.no_ppm.clear()

        X, ppm = strip_nan_columns(X, ppm)

        bw = max(self.bin_width, 1e-4)
        n_bins = int(max(round((ppm.max() - ppm.min()) / bw), 1))
        if n_bins < 2:
            self.Warning.too_few_bins()
            n_bins = 2
        else:
            self.Warning.too_few_bins.clear()

        bin_edges = np.linspace(ppm.min(), ppm.max(), n_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_indices = np.digitize(ppm, bin_edges) - 1
        # clip to valid range
        bin_indices = np.clip(bin_indices, 0, n_bins - 1)

        fn = self._methods_fn[self.method_idx]
        X_binned = np.zeros((X.shape[0], n_bins), dtype=float)
        for b in range(n_bins):
            mask = bin_indices == b
            if mask.sum() == 0:
                X_binned[:, b] = np.nan
            else:
                X_binned[:, b] = fn(X[:, mask], axis=1)

        domain = Domain(
            make_ppm_attributes(bin_centers),
            self.data.domain.class_vars,
            self.data.domain.metas,
        )
        out = Table(domain, X_binned, self.data.Y,
                    metas=self.data.metas if self.data.domain.metas else None)
        out.name = f"{self.data.name} (binned {bw} ppm)"
        self.Outputs.data.send(out)

    def send_report(self):
        self.report_items("Binning",
                          [("Bin width", f"{self.bin_width:.4f} ppm"),
                           ("Method", self._methods[self.method_idx])])