"""
NMR Peak Finding widget — deconvolution-based peak detection via Rnmr1D.

Wraps the NMRProcFlow computation core (R package ``Rnmr1D``,
github INRA/Rnmr1D, ``peakFinder`` / pseudo-Voigt deconvolution) as an
Orange preprocessing widget.  R is a system dependency; the widget probes
availability on input and warns (instead of failing silently) when R or
Rnmr1D are missing.  See ``rnmr1d_bridge`` for the subprocess contract.
"""

import time

import numpy as np
from AnyQt.QtCore import Qt

from Orange.data import ContinuousVariable, Domain, Table
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .nmr_utils import get_ppm_values
from .rnmr1d_bridge import (PEAK_COLUMNS, peak_finding, rnmr1d_available,
                            rscript_path)


class OWPeakFinding(OWWidget):
    name = "NMR Peak Finding"
    description = ("Deconvolution-based 1H-NMR peak detection (Rnmr1D, "
                   "NMRProcFlow core).")
    icon = "icons/NMRPeakFinding.svg"
    priority = 1060
    keywords = ["nmr", "peak", "finding", "deconvolution", "nmrprocflow",
                "rnmr1d"]

    class Inputs:
        data = Input("Spectra", Table)

    class Outputs:
        peaks = Output("Peaks", Table)

    class Warning(OWWidget.Warning):
        no_r = Msg("R / Rnmr1D not available — peak finding disabled. "
                   "Install R and the Rnmr1D package, or set WELLERLAB_R_LIBS.")
        failed = Msg("{error}")

    # deconvolution window
    ppm_lo = Setting(0.5)
    ppm_hi = Setting(8.0)
    # deconvolution parameters (Rnmr1D defaults: ratioPN=5, pvoigt=1, eta=0.7,
    # optim=1)
    ratio = Setting(5.0)
    pvoigt = Setting(1)
    eta = Setting(0.7)
    optim = Setting(1)
    auto_apply = Setting(True)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.data = None
        self._r_ok = None

        box = gui.vBox(self.controlArea, "Deconvolution window (ppm)")
        gui.doubleSpin(box, self, "ppm_lo", 0.0, 12.0, 0.1,
                       label="From:", controlWidth=80,
                       callback=self._range_changed, alignment=Qt.AlignRight)
        gui.doubleSpin(box, self, "ppm_hi", 0.0, 12.0, 0.1,
                       label="To:", controlWidth=80,
                       callback=self._range_changed, alignment=Qt.AlignRight)

        box = gui.vBox(self.controlArea, "Deconvolution parameters")
        gui.doubleSpin(box, self, "ratio", 1.0, 50.0, 0.5,
                       label="Peak/noise ratio:", controlWidth=80,
                       callback=self.apply, alignment=Qt.AlignRight)
        gui.checkBox(box, self, "pvoigt",
                     "Pseudo-Voigt (else pure Lorentzian)",
                     callback=self.apply)
        gui.doubleSpin(box, self, "eta", 0.0, 1.0, 0.05,
                       label="Voigt fraction (eta):", controlWidth=80,
                       decimals=2, callback=self.apply,
                       alignment=Qt.AlignRight)
        gui.checkBox(box, self, "optim", "Refine peak parameters",
                     callback=self.apply)

        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

    # -- UI helpers ------------------------------------------------------
    def _range_changed(self):
        if self.ppm_lo >= self.ppm_hi:
            # keep the window valid: shift the other bound by 0.1 ppm
            if self.ppm_lo > self.ppm_hi:
                self.ppm_hi = self.ppm_lo + 0.1
            else:
                self.ppm_lo = self.ppm_hi - 0.1
        self.apply()

    # -- input -----------------------------------------------------------
    @Inputs.data
    def set_data(self, data):
        self.data = data
        self._r_ok = None if data is None else rnmr1d_available()
        self.Warning.no_r.clear()
        self.Warning.failed.clear()
        if data is None:
            self.Outputs.peaks.send(None)
            return
        if not self._r_ok:
            self.Warning.no_r()
            self.Outputs.peaks.send(None)
            return
        self.apply()

    # -- computation -----------------------------------------------------
    def apply(self):
        if self.data is None:
            return
        if not self._r_ok:
            self.Warning.no_r()
            self.Outputs.peaks.send(None)
            return

        ppm = get_ppm_values(self.data)
        X = self.data.X
        if ppm.size != X.shape[1] or np.any(np.isnan(X)):
            # NaN columns break the R spec object — fall back to valid mask
            valid_cols = ~np.isnan(np.atleast_1d(np.nanmean(X, axis=0)))
            if not np.all(valid_cols):
                ppm, X = ppm[valid_cols], X[:, valid_cols]
        if ppm[-1] <= self.ppm_lo or ppm[0] >= self.ppm_hi:
            self.Warning.failed("Deconvolution window outside spectrum range "
                                f"({ppm[0]:.2f}–{ppm[-1]:.2f} ppm).")
            self.Outputs.peaks.send(None)
            return

        try:
            t0 = time.time()
            peaks = peak_finding(X, ppm, ppm_lo=self.ppm_lo,
                                 ppm_hi=self.ppm_hi, ratio=self.ratio,
                                 pvoigt=self.pvoigt, eta=self.eta,
                                 optim=self.optim)
        except Exception as e:  # noqa: BLE001 — surface any R failure
            self.Warning.failed(str(e)[:300])
            self.Outputs.peaks.send(None)
            return
        self.Warning.failed.clear()

        n = X.shape[0]
        # sample index (1-based) -> row index, then carry sample names as meta
        idx = np.asarray(peaks[:, 0] - 1, dtype=int).clip(0, n - 1) \
            if peaks.size else np.zeros(0, dtype=int)
        sample_meta = self.data.metas[idx, 0] \
            if self.data.metas is not None and self.data.metas.size \
            else np.arange(1, len(idx) + 1, dtype=float)

        dom = Domain(
            [ContinuousVariable(c) for c in PEAK_COLUMNS],
            metas=[ContinuousVariable("Sample")])
        out = Table.from_numpy(dom, X=peaks[:, 1:],
                               metas=sample_meta.reshape(-1, 1)) \
            if peaks.size else Table.from_numpy(dom, X=np.zeros((0, 6)),
                                                metas=np.zeros((0, 1)))
        out.name = f"{self.data.name} (peaks {self.ppm_lo:.1f}–{self.ppm_hi:.1f} ppm)"
        self.Outputs.peaks.send(out)
        if hasattr(self, "set_input_summary"):
            self.set_input_summary(f"{n} spectra",
                                   f"{peaks.shape[0]} peaks in "
                                   f"{time.time() - t0:.1f} s")

    def send_report(self):
        self.report_items("Peak Finding", [
            ("Window", f"{self.ppm_lo:.2f}–{self.ppm_hi:.2f} ppm"),
            ("Peak/noise ratio", self.ratio),
            ("Line shape", "pseudo-Voigt" if self.pvoigt else "Lorentzian"),
            ("Refine", "yes" if self.optim else "no"),
        ])
