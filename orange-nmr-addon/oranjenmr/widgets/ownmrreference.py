"""
NMR Reference/Alignment widget — align spectra to a reference peak.

Shifts each spectrum so that the maximum peak in a reference region
aligns to a target ppm value. Corrects for small chemical shift
variations between samples.

Note: This performs a simple integer-index shift (constant offset
across the entire spectrum). For more advanced alignment (icoshift,
warping), use dedicated tools.
"""

from AnyQt.QtCore import Qt
import numpy as np

from Orange.data import Table, Domain
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .nmr_utils import get_ppm_values


class OWReference(OWWidget):
    name = "NMR Reference & Alignment"
    description = "Align NMR spectra by shifting so a reference peak " \
                  "matches a target chemical shift."
    icon = "icons/NMRReference.svg"
    priority = 1050
    keywords = ["nmr", "reference", "alignment", "calibration", "shift"]

    class Inputs:
        data = Input("Spectra", Table)

    class Outputs:
        data = Output("Aligned Spectra", Table)

    class Warning(OWWidget.Warning):
        no_peak = Msg("Could not find peak in reference region "
                      "for some spectra.")
        too_large_shift = Msg("Requested shift exceeds half a point "
                              "— alignment limited to integer-pixel shifts.")

    ref_lo = Setting(0.0)
    ref_hi = Setting(10.0)
    target_ppm = Setting(0.0)
    auto_apply = Setting(True)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.data = None

        box = gui.vBox(self.controlArea, "Reference Peak")
        gui.doubleSpin(box, self, "ref_lo", -100, 100, 0.01,
                       label="PPM search range — from:",
                       controlWidth=80, decimals=2,
                       callback=self.apply)
        gui.doubleSpin(box, self, "ref_hi", -100, 100, 0.01,
                       label="to:",
                       controlWidth=80, decimals=2,
                       callback=self.apply)
        gui.doubleSpin(box, self, "target_ppm", -100, 100, 0.01,
                       label="Target ppm:",
                       controlWidth=80, decimals=2,
                       callback=self.apply)

        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

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
        lo, hi = min(self.ref_lo, self.ref_hi), max(self.ref_lo, self.ref_hi)

        # find index range for reference region
        idx_range = np.where((ppm >= lo) & (ppm <= hi))[0]
        if len(idx_range) == 0:
            self.Warning.no_peak()
            self.Outputs.data.send(self.data)
            return

        # per spectrum: find max peak in region, compute shift
        n_spectra = X.shape[0]
        X_aligned = np.full_like(X, np.nan)
        n_warnings = 0

        for i in range(n_spectra):
            region = X[i, idx_range]
            valid = ~np.isnan(region)
            if valid.sum() == 0:
                n_warnings += 1
                X_aligned[i, :] = X[i, :]
                continue

            # Find maximum position
            peak_idx_in_region = np.argmax(np.abs(region[valid]))
            peak_idx = idx_range[valid][peak_idx_in_region]
            peak_ppm = ppm[peak_idx]

            # Desired shift in ppm
            shift_ppm = self.target_ppm - peak_ppm
            # Convert to index shift
            if len(ppm) > 1:
                delta_ppm = np.abs(ppm[1] - ppm[0])
                shift_idx = int(round(shift_ppm / delta_ppm))
            else:
                shift_idx = 0

            # Apply shift using integer indexing
            src = np.arange(len(ppm))
            dst = src + shift_idx
            in_bounds = (dst >= 0) & (dst < len(ppm))
            X_aligned[i, dst[in_bounds]] = X[i, src[in_bounds]]

            if shift_idx != 0:
                n_warnings += 1

        if n_warnings > 0 and n_warnings < n_spectra:
            pass  # some shifted, some not — no warning needed

        domain = Domain(self.data.domain.attributes,
                        self.data.domain.class_vars,
                        self.data.domain.metas)
        out = Table(domain, X_aligned, self.data.Y,
                    metas=self.data.metas if self.data.domain.metas else None)
        out.name = f"{self.data.name} (aligned)"
        self.Outputs.data.send(out)

    def send_report(self):
        self.report_items("Reference",
                          [("Search region", f"{self.ref_lo}–{self.ref_hi} ppm"),
                           ("Target", f"{self.target_ppm} ppm")])