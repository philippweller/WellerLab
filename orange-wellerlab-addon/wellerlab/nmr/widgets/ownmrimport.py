"""NMR Raw Import: Bruker and Varian/Agilent raw data -> spectra table.

Reads every dataset below a folder, processes it (window, zero filling, FFT,
phase, baseline, referencing) and emits one table whose columns are the ppm values
- the convention the other NMR widgets here expect (`nmr_utils.get_ppm_values`
parses the attribute names). Several spectra of the same kind end up as one row
per sample, ready for a multivariate analysis.

Reading and numerics live in `wellerlab/nmr/nmr_io.py` (Qt-free, testable); this
widget drives them.

Three things that matter in practice, all explicit controls:
* **experiment filter** - a study folder holds several experiments per sample
  (PROTON, PRESAT, ...). Pick one and you get a proper matrix (samples x ppm)
  instead of every experiment mixed together.
* **group delay** - Varian/Agilent FIDs start with the digital-filter transient
  (68 points); dropping it turns the broad envelope into sharp lines.
* **referencing** - the axis from the acquisition parameters is not absolute.
  Either drag the signal in the preview (e.g. CHCl3) and name the standard, or
  let it look for the strongest peak within +/-0.5 ppm of the standard.
"""
import os

import numpy as np

from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import QAbstractItemView, QFileDialog

from Orange.data import Table, Domain, ContinuousVariable, StringVariable
from Orange.widgets import gui, widget
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Output, Msg

from .. import nmr_io
from ._plot_spectrum import SpectrumCanvas, attach_spectrum_toolbar

WINDOWS = ("exponential", "gaussian", "none")
ZERO_FILLS = ("1", "2", "4", "8")
PHASES = ("auto", "manual")
ALL_EXPERIMENTS = "(all)"
#: label -> standard key in nmr_io.SOLVENT_PPM
REFERENCE_CHOICES = (("none", None),
                     ("auto: TMS (0.00), else CHCl3 (7.26)", "auto"),
                     ("TMS (0.00)", "TMS"), ("DSS (0.00)", "DSS"),
                     ("CHCl3 (7.26)", "CHCl3"), ("CHCl3 (7.24)", "CHCl3_724"),
                     ("water (4.70)", "water"), ("DMSO (2.50)", "DMSO"),
                     ("acetone (2.05)", "acetone"), ("formate (8.44)", "formate"),
                     ("manual shift", "manual"))
#: ppm for the extra CHCl3 entry (the value the user asked for)
CHCL3_724_PPM = 7.24

_MANUAL = "manual shift"


class OWNMRImport(widget.OWWidget):
    name = "NMR Raw Import"
    description = ("Import 1D NMR raw data (Bruker, Varian/Agilent), pick one "
                   "experiment, process it (window, zero fill, FFT, phase, "
                   "baseline, referencing - also by dragging a signal) and emit "
                   "a spectra table for multivariate analysis.")
    icon = "icons/NMRImport.svg"
    priority = 60
    keywords = ["nmr", "import", "bruker", "varian", "agilent", "fid", "raw",
                "metabolomics", "preprocessing", "spectra", "batch"]

    class Outputs:
        spectra = Output("Spectra", Table, default=True)

    class Information(widget.OWWidget.Information):
        loaded = Msg("Imported {} {} spectrum(s) from {}")
        found_region = Msg("Strongest line in the marked region: {:.3f} ppm "
                           "(now at {:.3f} ppm)")
        referenced_on = Msg("Automatically referenced on {} at {:.3f} ppm")

    class Warning(widget.OWWidget.Warning):
        no_datasets = Msg("No NMR raw data found below that folder.")
        failed = Msg("{} dataset(s) could not be read: {}")
        no_region_peak = Msg("No data inside the marked region ({:.2f} .. "
                             "{:.2f} ppm).")
        no_reference = Msg("No TMS (0.00) or CHCl3 line within +/-{:.2f} ppm - "
                           "the axis was left as it is. Mark the signal with the "
                           "mouse instead.")

    # ------------------------------------------------------------- settings
    folder = Setting("")
    selected = Setting([])              # indices into self.datasets (listBox)
    experiment = Setting(ALL_EXPERIMENTS)
    window_apodization = Setting("exponential")
    lb_hz = Setting(0.3)
    zero = Setting("2")
    skip = Setting(0)                   # 0 = automatic (68 Varian, 0 Bruker)
    phase = Setting("auto")
    p0 = Setting(0.0)
    p1 = Setting(0.0)
    baseline_order = Setting(0)
    reference = Setting("auto: TMS (0.00), else CHCl3 (7.26)")
    manual_shift = Setting(0.0)
    search_window = Setting(0.5)        # ppm window of the automatic peak search
    view_from_zero = Setting(True)      # x axis starts at 0 ppm
    view_hi = Setting(10.0)             # ... and ends here
    region_lo = Setting(0.0)
    region_hi = Setting(0.0)
    region_active = Setting(False)

    want_main_area = True
    resizing_enabled = True
    graph_name = "preview_canvas"

    def __init__(self):
        super().__init__()
        self.datasets = []
        self._spectra = []              # [(name, sample, experiment, ppm, curve)]
        self._reference_ppm = None      # the target of the chosen standard
        self._found_ppm = None          # peak position used for referencing
        self._auto_key = None           # standard the automatic search picked
        self.auto_commit = True

        box = gui.vBox(self.controlArea, "Source")
        gui.lineEdit(box, self, "folder", label="Folder: ",
                     orientation=Qt.Horizontal, callback=self._rescan)
        gui.button(box, self, "Browse…", callback=self._browse)
        gui.button(box, self, "Rescan", callback=self._rescan)
        self.lbl_found = gui.label(box, self, "—")

        ebox = gui.vBox(self.controlArea, "Experiment")
        self.exp_combo = gui.comboBox(ebox, self, "experiment", items=[ALL_EXPERIMENTS],
                                      label="Import: ", sendSelectedValue=True,
                                      callback=self._process)
        gui.label(ebox, self, "<i>One row per sample - what a multivariate "
                              "analysis needs.</i>")

        dbox = gui.vBox(self.controlArea, "Datasets")
        self.list = gui.listBox(
            dbox, self, "selected",
            selectionMode=QAbstractItemView.SelectionMode.ExtendedSelection,
            callback=self._process)
        self.list.setMinimumHeight(90)

        pbox = gui.vBox(self.controlArea, "Processing")
        gui.comboBox(pbox, self, "window_apodization", items=WINDOWS,
                     label="Window: ", sendSelectedValue=True, callback=self._process)
        gui.doubleSpin(pbox, self, "lb_hz", 0.0, 10.0, 0.05, label="LB (Hz): ",
                       decimals=2, callback=self._process)
        gui.comboBox(pbox, self, "zero", items=ZERO_FILLS, label="Zero fill: ",
                     sendSelectedValue=True, callback=self._process)
        gui.spin(pbox, self, "skip", 0, 512, 1, label="Skip points: ",
                 callback=self._process,
                 tooltip="Points dropped before the FFT (digital-filter group "
                         "delay). 0 = automatic: 68 for Varian/Agilent, 0 for "
                         "Bruker. Dropping them is what sharpens the lines.")
        gui.comboBox(pbox, self, "phase", items=PHASES, label="Phase: ",
                     sendSelectedValue=True, callback=self._process)
        gui.doubleSpin(pbox, self, "p0", -360.0, 360.0, 5.0, label="φ0 (°): ",
                       decimals=1, callback=self._process)
        gui.doubleSpin(pbox, self, "p1", -360.0, 360.0, 5.0, label="φ1 (°): ",
                       decimals=1, callback=self._process)
        gui.spin(pbox, self, "baseline_order", 0, 9, 1,
                 label="Baseline (order, 0 = off): ", callback=self._process)

        rbox = gui.vBox(self.controlArea, "Referencing")
        gui.comboBox(rbox, self, "reference", items=[c[0] for c in REFERENCE_CHOICES],
                     label="Reference: ", sendSelectedValue=True,
                     callback=self._process)
        gui.doubleSpin(rbox, self, "manual_shift", -20.0, 20.0, 0.01,
                       label="Manual shift (ppm): ", decimals=3,
                       callback=self._process)
        gui.separator(rbox)
        gui.label(rbox, self, "<b>Mark a signal with the mouse</b> (drag in the "
                              "preview) and it becomes the reference:")
        gui.checkBox(rbox, self, "region_active", "Use the marked region",
                     callback=self._process)
        gui.doubleSpin(rbox, self, "region_lo", -20.0, 30.0, 0.01,
                       label="Region from (ppm): ", decimals=3,
                       callback=self._region_typed)
        gui.doubleSpin(rbox, self, "region_hi", -20.0, 30.0, 0.01,
                       label="Region to (ppm): ", decimals=3,
                       callback=self._region_typed)
        gui.button(rbox, self, "Clear region", callback=self._clear_region)
        gui.doubleSpin(rbox, self, "search_window", 0.05, 2.0, 0.05,
                       label="Search window (± ppm): ", decimals=2,
                       callback=self._process,
                       tooltip="Half width of the automatic search around TMS "
                               "(0.00) and CHCl3 (7.26). Wider covers a "
                               "referencing offset, but can catch an unrelated "
                               "line (e.g. grease at 0.07 ppm).")
        self.lbl_region = gui.label(rbox, self, "no region marked")

        vbox = gui.vBox(self.controlArea, "View")
        gui.checkBox(vbox, self, "view_from_zero", "x axis starts at 0 ppm",
                     callback=self._process)
        gui.doubleSpin(vbox, self, "view_hi", 1.0, 30.0, 0.5, label="… up to (ppm): ",
                       decimals=1, callback=self._process)
        gui.button(vbox, self, "Reset zoom", callback=self._reset_zoom)
        gui.label(vbox, self, "<i>Wheel = zoom, right drag = pan.</i>")

        gui.rubber(self.controlArea)
        gui.auto_apply(self.buttonsArea, self, "auto_commit")

        pvbox = gui.vBox(self.mainArea, "Preview")
        self.preview_canvas = SpectrumCanvas((9, 3.4))
        self.preview_canvas.on_region = self._region_dragged
        pvbox.layout().addWidget(self.preview_canvas)
        attach_spectrum_toolbar(pvbox, self.preview_canvas, self)

    # ------------------------------------------------------------- source
    def _browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "NMR raw data folder", self.folder or os.path.expanduser("~"))
        if path:
            self.folder = path
            self._rescan()

    def _rescan(self):
        self.datasets = nmr_io.find_datasets(self.folder) if self.folder else []
        count = len(self.datasets)
        self.selected = [i for i in self.selected if 0 <= i < count] \
            or list(range(count))

        experiments = []
        for dataset in self.datasets:
            name = nmr_io.describe(dataset)[1]
            if name not in experiments:
                experiments.append(name)
        items = [ALL_EXPERIMENTS] + sorted(experiments)
        self.exp_combo.blockSignals(True)
        self.exp_combo.clear()
        self.exp_combo.addItems(items)
        wanted = self._experiment()
        self.exp_combo.setCurrentIndex(items.index(wanted) if wanted in items else 0)
        self.exp_combo.blockSignals(False)

        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems([f"{d.name}   [{nmr_io.describe(d)[1]}]"
                            for d in self.datasets])
        for i in range(count):
            self.list.item(i).setSelected(i in self.selected)
        self.list.blockSignals(False)

        self.lbl_found.setText(f"{count} dataset(s) found" if count
                               else "no dataset found")
        if not count:
            self.Warning.no_datasets()
            self._spectra = []
            self.preview_canvas.draw_spectrum(None, None, None)
            self.Outputs.spectra.send(None)
            return
        self.Warning.no_datasets.clear()
        self._process()

    def _experiment(self):
        """The chosen experiment name, or '' for all."""
        value = self.experiment
        if isinstance(value, int):                     # an older workflow
            return "" if value in (0, -1) else str(value)
        return "" if value in ("", ALL_EXPERIMENTS) else str(value)

    def _chosen(self):
        indices = [i for i in self.selected if 0 <= i < len(self.datasets)]
        if not indices:
            indices = list(range(len(self.datasets)))
        chosen = [self.datasets[i] for i in indices]
        wanted = self._experiment()
        if wanted:
            chosen = [d for d in chosen if nmr_io.describe(d)[1] == wanted]
        return chosen

    # ------------------------------------------------------------- region
    def _region(self):
        """(low, high) of the marked region, or None."""
        if not self.region_active:
            return None
        lo, hi = float(self.region_lo), float(self.region_hi)
        if abs(hi - lo) < 1e-6:
            return None
        return tuple(sorted((lo, hi)))

    def _region_dragged(self, lo, hi):
        """A drag in the preview marks the region and re-references at once."""
        self.region_lo, self.region_hi = round(lo, 3), round(hi, 3)
        self.region_active = True
        self._process()

    def _region_typed(self):
        self.region_active = True
        self._process()

    def _clear_region(self):
        self.region_active = False
        self.region_lo = self.region_hi = 0.0
        self._process()

    # ------------------------------------------------------------- processing
    def _zero_fill_factor(self):
        value = self.zero
        if isinstance(value, int):
            return (1, 2, 4, 8)[min(max(value, 0), 3)]
        return int(value) if str(value) in ZERO_FILLS else 2

    def _standard(self):
        """(label, standard key or None) for the chosen reference."""
        choice = self.reference
        if isinstance(choice, int):
            choice = REFERENCE_CHOICES[min(max(choice, 0),
                                           len(REFERENCE_CHOICES) - 1)][0]
        for label, key in REFERENCE_CHOICES:
            if label == choice:
                return label, key
        return "none", None

    def _standard_ppm(self, key):
        """The ppm of a standard key (the 7.24 variant is not in SOLVENT_PPM)."""
        if key == "CHCl3_724":
            return CHCL3_724_PPM
        return nmr_io.SOLVENT_PPM.get(key)

    def _reset_zoom(self):
        self.preview_canvas.reset_zoom()

    def _process(self):
        chosen = self._chosen()
        if not chosen:
            self._spectra = []
            self.preview_canvas.draw_spectrum(None, None, None)
            self.Outputs.spectra.send(None)
            return

        self.Warning.no_region_peak.clear()
        _, standard = self._standard()
        self._reference_ppm = (self._standard_ppm(standard)
                               if standard not in (None, "manual", "auto") else None)
        self._found_ppm = None
        self._auto_key = None
        self.Warning.no_reference.clear()

        spectra, failed = [], []
        for dataset in chosen:
            try:
                sample, experiment = nmr_io.describe(dataset)
                ppm, curve = self._process_one(dataset)
                spectra.append((dataset.name, sample, experiment, ppm, curve))
            except Exception as exc:                    # keep the rest usable
                failed.append(f"{dataset.name}: {exc}")

        self._spectra = spectra
        self.Warning.failed.clear()
        if failed:
            self.Warning.failed(len(failed), "; ".join(failed[:2])[:140])
        if not spectra:
            self.preview_canvas.draw_spectrum(None, None, None)
            self.Outputs.spectra.send(None)
            return

        experiment = self._experiment() or "all experiments"
        self.Information.loaded(len(spectra), experiment, self.folder or "-")
        if self._found_ppm is not None and self._reference_ppm is not None:
            self.Information.found_region(self._found_ppm, self._reference_ppm)
        if self._auto_key is not None:
            self.Information.referenced_on(self._auto_key, self._reference_ppm)
        name, _sample, _exp, ppm, curve = spectra[0]
        self.preview_canvas.draw_spectrum(
            ppm, curve, name, reference_ppm=self._reference_ppm,
            region=self._region(),
            view=(0.0, float(self.view_hi)) if self.view_from_zero else None)
        self.lbl_region.setText(
            "no region marked" if self._region() is None else
            f"region {self._region()[0]:.2f} .. {self._region()[1]:.2f} ppm"
            + (f" - line at {self._found_ppm:.3f} ppm"
               if self._found_ppm is not None else ""))
        self.commit.now() if self.auto_commit else self.commit.deferred()

    def _process_one(self, dataset):
        """Read + process one dataset -> (ppm, intensity)."""
        data, axis, meta = nmr_io.read_vendor(dataset, processed=True)
        if meta["domain"] == "frequency":               # Bruker pdata/1r: ready
            curve = np.real(data)
        else:
            skip = self.skip or (68 if meta["vendor"] == "varian" else 0)
            axis, curve, _info = nmr_io.process_fid(
                np.asarray(data)[skip:], meta,
                lb_hz=self.lb_hz if self.window_apodization != "none" else 0.0,
                window=self.window_apodization, zero=self._zero_fill_factor(),
                phase=self.phase, p0=self.p0, p1=self.p1,
                baseline_order=self.baseline_order)
            curve = np.real(curve)
        return self._apply_reference(axis, curve), curve

    def _apply_reference(self, ppm, curve):
        """Reference on the marked region, on the standard, or automatically."""
        ppm = np.asarray(ppm, dtype=float)
        region = self._region()
        target = self._reference_ppm
        _, standard = self._standard()
        window = float(self.search_window)

        if region is not None:
            found = nmr_io.peak_in_region(ppm, curve, region)
            if found is None:
                self.Warning.no_region_peak(*region)
            else:
                self._found_ppm = found
                if target is None and standard == "auto":
                    # the marked signal tells us which standard it is about
                    key = "TMS" if abs(found) <= abs(found - CHCL3_724_PPM) else "CHCl3"
                    target = self._standard_ppm(key)
                    self._reference_ppm = target
                    self._auto_key = key
                if target is not None:
                    ppm, _delta, _found = nmr_io.align_region(ppm, curve, region,
                                                              target)
        elif standard == "auto":
            key, target, found = nmr_io.find_reference_peak(ppm, curve,
                                                            window=window)
            if key is None:
                self.Warning.no_reference(window)
            else:
                self._reference_ppm = target
                self._auto_key = key
                self._found_ppm = found
                ppm, _delta = nmr_io.align_to_reference(ppm, curve, target,
                                                        window=window)
        elif target is not None:
            ppm, _delta = nmr_io.align_to_reference(ppm, curve, target,
                                                    window=window)
        if abs(self.manual_shift) > 1e-9:
            ppm = ppm + float(self.manual_shift)
        return ppm

    # ------------------------------------------------------------- outputs
    @gui.deferred
    def commit(self):
        if not self._spectra:
            self.Outputs.spectra.send(None)
            return
        ppm = np.asarray(self._spectra[0][3], dtype=float)
        attrs = tuple(ContinuousVariable(f"{p:.4f}") for p in ppm)
        dom = Domain(attrs, metas=[StringVariable("sample"),
                                   StringVariable("experiment")])
        rows, metas = [], []
        for _name, sample, experiment, _ppm, curve in self._spectra:
            values = np.asarray(curve, dtype=float)
            if len(values) != len(ppm):                 # different FFT lengths
                values = np.interp(np.linspace(0, 1, len(ppm)),
                                   np.linspace(0, 1, len(values)), values)
            rows.append(values)
            metas.append([sample, experiment])
        table = Table.from_numpy(dom, X=np.vstack(rows),
                                 metas=np.array(metas, dtype=object))
        experiment = self._experiment()
        table.name = f"NMR spectra ({experiment})" if experiment else "NMR spectra"
        self.Outputs.spectra.send(table)


if __name__ == "__main__":                       # pragma: no cover
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWNMRImport).run()
