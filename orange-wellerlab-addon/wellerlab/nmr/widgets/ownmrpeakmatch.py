"""
NMR Peak Match widget — annotate peak positions against reference DBs.

Wraps the NMRProcFlow computation core (R package ``Rnmr1D``,
github INRA/Rnmr1D, ``peakMatching``): each peak position is matched to the
compound(s) in a built-in 1D-HM reference database (dbref6, hmdb110) and the
best candidate (compound name, HMDB id + link, match score) is joined back to
the input peak table.  Designed to follow the *NMR Peak Finding* widget.  R is
a system dependency; the widget probes availability and warns instead of
crashing silently.
"""

import time

import numpy as np
from AnyQt.QtCore import Qt

from Orange.data import ContinuousVariable, Domain, Table
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .rnmr1d_bridge import MATCH_LIBS, peak_matching, rnmr1d_available


class OWPeakMatch(OWWidget):
    name = "NMR Peak Match"
    description = ("Annotate peak ppm positions against a reference "
                   "compound database (Rnmr1D, NMRProcFlow core).")
    icon = "icons/NMRPeakMatch.svg"
    priority = 1080
    keywords = ["nmr", "peak", "matching", "annotation", "metabolite",
                "hmdb", "nmrprocflow", "rnmr1d"]

    class Inputs:
        peaks = Input("Peaks", Table)

    class Outputs:
        annotated = Output("Annotated Peaks", Table)

    class Warning(OWWidget.Warning):
        no_r = Msg("R / Rnmr1D not available — peak matching disabled. "
                   "Install R and the Rnmr1D package, or set WELLERLAB_R_LIBS.")
        failed = Msg("{error}")
        no_ppm = Msg("No 'ppm' column found — the input should be the "
                     "output of NMR Peak Finding.")

    _LIB_NAMES = {lib: {"dbref6": "dbref6 (82 metabolites)",
                        "hmdb110": "HMDB 110"}[lib] for lib in MATCH_LIBS}

    lib_idx = Setting(0)
    tol = Setting(0.02)
    auto_apply = Setting(True)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.peaks = None
        self._r_ok = None

        box = gui.vBox(self.controlArea, "Reference database")
        gui.comboBox(box, self, "lib_idx", label="Database:",
                     items=[self._LIB_NAMES[l] for l in MATCH_LIBS],
                     callback=self.apply, orientation=Qt.Horizontal)
        gui.doubleSpin(box, self, "tol", 0.001, 0.2, 0.001,
                       label="Tolerance (ppm):", controlWidth=80, decimals=3,
                       callback=self.apply, alignment=Qt.AlignRight)

        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

    # -- input -----------------------------------------------------------
    @Inputs.peaks
    def set_peaks(self, peaks):
        self.peaks = peaks
        self._r_ok = None if peaks is None else rnmr1d_available()
        self.Warning.no_r.clear()
        self.Warning.failed.clear()
        self.Warning.no_ppm.clear()
        if peaks is None:
            self.Outputs.annotated.send(None)
            return
        if not self._r_ok:
            self.Warning.no_r()
            self.Outputs.annotated.send(None)
            return
        self.apply()

    # -- computation -----------------------------------------------------
    def apply(self):
        if self.peaks is None or not self._r_ok:
            return

        # locate the ppm column (first attribute named like a ppm value)
        ppm = self._find_ppm()
        if ppm is None:
            self.Warning.no_ppm()
            self.Outputs.annotated.send(None)
            return
        self.Warning.no_ppm.clear()

        lib = MATCH_LIBS[self.lib_idx]
        try:
            t0 = time.time()
            ann = peak_matching(ppm, lib=lib, tol=self.tol)
        except Exception as e:  # noqa: BLE001 — surface any R failure
            self.Warning.failed(str(e)[:300])
            self.Outputs.annotated.send(None)
            return
        self.Warning.failed.clear()

        # best (highest-score) annotation per query ppm
        best = {}
        for r in ann:
            q = round(float(r[0]), 6)
            score = 0.0 if str(r[4]) in ("", "NA") else float(r[4])
            row = (str(r[1]), str(r[2]), str(r[3]),
                   score, float(r[5]) if str(r[5]) not in ("", "NA")
                   else float("nan"))
            if q not in best or score > best[q][3]:
                best[q] = row

        n = len(ppm)
        names = np.full(n, "unknown", dtype=object)
        dbids = np.full(n, "unknown", dtype=object)
        links = np.full(n, "—", dtype=object)
        scores = np.full(n, np.nan)
        db_ppm = np.full(n, np.nan)
        for i, p in enumerate(ppm):
            hit = best.get(round(float(p), 6))
            if hit:
                names[i], dbids[i], links[i], scores[i], db_ppm[i] = hit

        base = self.peaks
        # keep the input peak table untouched; append the annotation as new
        # metas (strings -> StringVariable, numbers -> continuous). Orange's
        # meta matrix is a single 2-D array; build it object-typed so the
        # string columns stay literal AND the numeric columns stay numeric
        # (a U-dtype string column would upcast the floats to strings).
        from Orange.data import StringVariable
        str_cols = (("Compound", names), ("HMDB id", dbids),
                    ("HMDB link", links))
        new_metas = ([StringVariable(nm) for nm, _ in str_cols]
                     + [ContinuousVariable("score"),
                        ContinuousVariable("DB ppm")])
        added = np.empty((n, 5), dtype=object)
        for j, (_, col) in enumerate(str_cols):
            added[:, j] = col.astype(object)
        added[:, 3] = scores
        added[:, 4] = db_ppm

        base_metas = list(base.domain.metas)
        metas = base_metas + new_metas
        dom = Domain(list(base.domain.attributes), base.domain.class_vars,
                     metas)
        base_meta_mx = base.metas if (base.domain.metas and
                                      base.metas.size) else np.zeros((n, 0))
        meta_mx = np.column_stack([base_meta_mx.astype(object), added]) \
            if base_meta_mx.size else added
        out = Table.from_numpy(dom, X=base.X.copy(),
                               Y=base.Y if base.Y.size else None,
                               metas=meta_mx)
        out.name = f"{base.name} ({self._LIB_NAMES[lib]} annotation)"
        n_hit = int(np.sum(~np.isnan(scores)))
        self.Outputs.annotated.send(out)
        if hasattr(self, "set_input_summary"):
            self.set_input_summary(f"{n} peaks",
                                   f"{n_hit} annotated in "
                                   f"{time.time() - t0:.1f} s")

    def _find_ppm(self):
        """Return the ppm ndarray, or None if no attribute is a ppm axis."""
        for attr in self.peaks.domain.attributes:
            if attr.name in ("ppm", "chemical shift"):
                return self.peaks.X[:,
                                    self.peaks.domain.attributes.index(attr)]
        # fall back: first numeric attribute whose values look like ppm
        for i, attr in enumerate(self.peaks.domain.attributes):
            col = self.peaks.X[:, i]
            if col.size and np.nanmax(np.abs(col)) < 12.0:
                return col
        return None

    def send_report(self):
        self.report_items("Peak Match", [
            ("Database", self._LIB_NAMES[MATCH_LIBS[self.lib_idx]]),
            ("Tolerance", f"{self.tol:.3f} ppm"),
        ])
