"""
NMR Region Exclusion widget — remove spectral regions by ppm range.

Common uses:
- Suppress solvent peaks (water ~4.7 ppm, DMSO ~2.5 ppm, MeOH ~3.3)
- Remove noisy edge regions
- Exclude specific artifacts between a start and end ppm value
"""

from AnyQt.QtCore import Qt
import numpy as np

from Orange.data import Table, Domain, ContinuousVariable
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.utils.signals import Input, Output
from Orange.widgets.widget import OWWidget, Msg

from .nmr_utils import get_ppm_values, make_ppm_attributes


class OWExclusion(OWWidget):
    name = "NMR Region Exclusion"
    description = "Remove spectral regions by specifying ppm ranges " \
                  "(solvent suppression, edge noise removal)."
    icon = "icons/NMRExclude.svg"
    priority = 1040
    keywords = ["nmr", "exclude", "remove", "solvent", "water suppression"]

    class Inputs:
        data = Input("Spectra", Table)

    class Outputs:
        data = Output("Cleaned Spectra", Table)

    class Warning(OWWidget.Warning):
        no_regions = Msg("No exclusion regions defined.")

    regions_text = Setting("")
    auto_apply = Setting(True)

    want_main_area = False
    resizing_enabled = False

    def __init__(self):
        super().__init__()
        self.data = None
        self.regions = []  # list of (lo, hi) tuples

        box = gui.vBox(self.controlArea, "Exclusion Regions")
        gui.label(box, self,
                  "One range per line: start_ppm, end_ppm\n"
                  "Example:\n"
                  "  4.50, 5.00\n"
                  "  2.40, 2.60")
        self.regions_edit = gui.lineEdit(
            box, self, "regions_text",
            label="",
            orientation=Qt.Horizontal,
            callback=self._parse_regions,
            placeholderText="4.50,5.00  (one per line)"
        )

        btn_box = gui.hBox(box)
        gui.button(btn_box, self, "Add preset: Water",
                   callback=lambda: self._add_preset(4.5, 5.0))
        gui.button(btn_box, self, "DMSO",
                   callback=lambda: self._add_preset(2.4, 2.6))

        gui.separator(box)
        gui.auto_apply(box, self, "auto_apply", commit=self.apply)

    def _add_preset(self, lo, hi):
        lines = self.regions_text.strip()
        new_line = f"{lo:.1f},{hi:.1f}"
        if lines:
            lines += "\n" + new_line
        else:
            lines = new_line
        self.regions_text = lines
        self._parse_regions()

    def _parse_regions(self):
        parsed = []
        for line in self.regions_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) == 2:
                try:
                    lo, hi = float(parts[0].strip()), float(parts[1].strip())
                    parsed.append((min(lo, hi), max(lo, hi)))
                except ValueError:
                    pass
        self.regions = parsed
        self.apply()

    @Inputs.data
    def set_data(self, data):
        self.data = data
        self.apply()

    def apply(self):
        # Re-parse in case it was called externally
        self._parse_regions()

        if self.data is None:
            self.Outputs.data.send(None)
            return

        ppm = get_ppm_values(self.data)

        if self.regions_text == "" or not self.regions:
            self.Warning.no_regions()
            self.Outputs.data.send(self.data)
            return
        self.Warning.no_regions.clear()

        keep = np.ones(len(ppm), dtype=bool)
        for lo, hi in self.regions:
            keep &= ~((ppm >= lo) & (ppm <= hi))

        if keep.sum() == 0:
            self.Warning.no_regions()
            self.Outputs.data.send(self.data)
            return

        X_clean = self.data.X[:, keep]
        ppm_clean = ppm[keep]

        domain = Domain(
            make_ppm_attributes(ppm_clean),
            self.data.domain.class_vars,
            self.data.domain.metas,
        )
        out = Table(domain, X_clean, self.data.Y,
                    metas=self.data.metas if self.data.domain.metas else None)
        out.name = f"{self.data.name} (excluded)"
        self.Outputs.data.send(out)

    def send_report(self):
        self.report_items("Exclusion",
                          [("Regions", ", ".join(
                              f"{lo:.2f}-{hi:.2f}" for lo, hi in self.regions))])