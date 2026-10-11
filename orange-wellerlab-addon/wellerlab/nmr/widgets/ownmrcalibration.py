"""
NMR Calibration widget — reference-peak calibration via Rnmr1D.

Wraps the NMRProcFlow computation core (R package ``Rnmr1D``,
github INRA/Rnmr1D, ``calibSpectrum``): the highest peak inside a user-
chosen reference zone is shifted onto the reference compound's chemical
shift (TSP/DSS, DMSO, Tris, ...), physically translating the spectrum so
that downstream peak positions are on an absolute scale.  R is a system
dependency; the widget probes availability on input and warns (instead of
failing silently) when R or Rnmr1D are missing.
"""

import time

import numpy as np
from AnyQt.QtCore import Qt

from Orange.data import Table, Domain
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .nmr_utils import get_ppm_values
from .rnmr1d_bridge import REFERENCES, calibrate, rnmr1d_available


class OWCalibration(OWWidget):
    name = "NMR Calibration"
    description = ("Shift spectra so a reference compound (TSP, DSS, DMSO, "
                   "Tris, ...) sits at its absolute ppm (Rnmr1D, NMRProcFlow "
                   "core).")
    icon = "icons/NMRCalibration.svg"
    priority = 1070
    keywords = ["nmr", "calibration", "calibrate", "reference", "tsp", "dss",
                "nmrprocflow", "rnmr1d"]

    class Inputs:
        data = Input("Spectra", Table)

    class Outputs:
        data = Output("Calibrated Spectra", Table)

    class Warning(OWWidget.Warning):
        no_r = Msg("R / Rnmr1D not available — calibration disabled. "
                   "Install R and the Rnmr1D package, or set WELLERLAB_R_LIBS.")
        failed = Msg("{error}")

    _CUSTOM = "Custom zone"

    ref_idx = Setting(0)
    zone_lo = Setting(0.0)
    zone_hi = Setting(0.5)
    ref_ppm = Setting(0.0)
    auto_apply = Setting(True)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.data = None
        self._r_ok = None

        box = gui.vBox(self.controlArea, "Reference compound")
        self.ref_combo = gui.comboBox(box, self, "ref_idx",
                                      label="Reference:",
                                      items=[r[0] for r in REFERENCES]
                                      + [self._CUSTOM],
                                      callback=self._on_ref,
                                      orientation=Qt.Horizontal)

        box = gui.vBox(self.controlArea, "Reference zone (ppm)", flat=True)
        gui.doubleSpin(box, self, "zone_lo", 0.0, 12.0, 0.05,
                       label="From:", controlWidth=80, decimals=3,
                       callback=self._zone_changed, alignment=Qt.AlignRight)
        gui.doubleSpin(box, self, "zone_hi", 0.0, 12.0, 0.05,
                       label="To:", controlWidth=80, decimals=3,
                       callback=self._zone_changed, alignment=Qt.AlignRight)

        box = gui.vBox(self.controlArea, "Target ppm", flat=True)
        gui.doubleSpin(box, self, "ref_ppm", 0.0, 12.0, 0.001,
                       label="Move reference to:", controlWidth=90,
                       decimals=3, callback=self.apply,
                       alignment=Qt.AlignRight)

        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

    # -- UI helpers ------------------------------------------------------
    def _on_ref(self):
        if self.ref_idx < len(REFERENCES):
            _, ref = REFERENCES[self.ref_idx]
            half = 0.25
            lo, hi = max(0.0, ref - half), min(12.0, ref + half)
            if hi - lo < 0.1:
                hi = min(12.0, lo + 0.1)
            self.ref_ppm = ref
            self.zone_lo, self.zone_hi = lo, hi
        self.apply()

    def _zone_changed(self):
        if self.zone_lo >= self.zone_hi:
            if self.zone_lo > self.zone_hi:
                self.zone_hi = min(12.0, self.zone_lo + 0.1)
            else:
                self.zone_lo = max(0.0, self.zone_hi - 0.1)
        self.apply()

    # -- input -----------------------------------------------------------
    @Inputs.data
    def set_data(self, data):
        self.data = data
        self._r_ok = None if data is None else rnmr1d_available()
        self.Warning.no_r.clear()
        self.Warning.failed.clear()
        if data is None:
            self.Outputs.data.send(None)
            return
        if not self._r_ok:
            self.Warning.no_r()
            self.Outputs.data.send(None)
            return
        self.apply()

    # -- computation -----------------------------------------------------
    def apply(self):
        if self.data is None or not self._r_ok:
            return
        ppm = get_ppm_values(self.data)
        X = self.data.X
        if ppm.size != X.shape[1]:
            self.Warning.failed("Spectrum grid does not match the attribute "
                                "count — check the input table.")
            self.Outputs.data.send(None)
            return

        try:
            t0 = time.time()
            X_cal, shifts, peak_after = calibrate(
                X, ppm, zone_lo=self.zone_lo, zone_hi=self.zone_hi,
                ref_ppm=self.ref_ppm)
        except Exception as e:  # noqa: BLE001 — surface any R failure
            self.Warning.failed(str(e)[:300])
            self.Outputs.data.send(None)
            return
        self.Warning.failed.clear()

        dom = Domain(self.data.domain.attributes,
                     self.data.domain.class_vars, self.data.domain.metas)
        out = Table(dom, X_cal, self.data.Y,
                    metas=self.data.metas if self.data.domain.metas else None)
        out.name = (f"{self.data.name} (calibrated {self.zone_lo:.2f}–"
                    f"{self.zone_hi:.2f} → {self.ref_ppm:.3f} ppm)")
        self.Outputs.data.send(out)
        if hasattr(self, "set_input_summary"):
            mean_res = float(np.mean(np.abs(peak_after - self.ref_ppm)))
            self.set_input_summary(f"{X.shape[0]} spectra",
                                   f"residual {mean_res * 1000:.1f} µppm in "
                                   f"{time.time() - t0:.1f} s")

    def send_report(self):
        self.report_items("Calibration", [
            ("Reference",
             self._CUSTOM if self.ref_idx >= len(REFERENCES)
             else REFERENCES[self.ref_idx][0]),
            ("Zone", f"{self.zone_lo:.3f}–{self.zone_hi:.3f} ppm"),
            ("Target ppm", f"{self.ref_ppm:.3f}"),
        ])
