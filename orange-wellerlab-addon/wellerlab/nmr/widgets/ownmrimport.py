"""NMR Raw Import: Bruker and Varian/Agilent raw data -> spectra table.

Reads every dataset below a folder, processes it (window, zero filling, FFT,
phase, baseline, referencing) and emits a table whose columns are the ppm values
- the convention the other NMR widgets here expect (`nmr_utils.get_ppm_values`
parses the attribute names).

Reading and numerics live in `wellerlab/nmr/nmr_io.py` (Qt-free, testable); this
widget drives them.

Two things that matter in practice and are therefore explicit controls:
* **group delay** - Varian/Agilent FIDs start with the digital-filter transient
  (68 points); dropping it is what turns the broad envelope into sharp lines.
* **referencing** - the axis comes from the acquisition parameters (carrier in
  the window centre). Instruments reference differently, so the axis is made
  absolute here: align a standard (TSP/DSS/water/...) or shift by hand.
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
REFERENCE_CHOICES = ("none", "TSP (0.00)", "DSS (0.00)", "water (4.70)",
                     "DMSO (2.50)", "chloroform (7.26)", "manual shift")
_REFERENCE_KEY = {"TSP (0.00)": "TSP", "DSS (0.00)": "DSS", "water (4.70)": "water",
                  "DMSO (2.50)": "DMSO", "chloroform (7.26)": "chloroform"}


class OWNMRImport(widget.OWWidget):
    name = "NMR Raw Import"
    description = ("Import 1D NMR raw data (Bruker acqus/fid/fid, Varian/Agilent "
                   "procpar/fid), process it (window, zero fill, FFT, phase, "
                   "baseline, referencing) and emit a spectra table.")
    icon = "icons/NMRImport.svg"
    priority = 60
    keywords = ["nmr", "import", "bruker", "varian", "agilent", "fid", "raw",
                "metabolomics", "preprocessing", "spectra"]

    class Outputs:
        spectra = Output("Spectra", Table, default=True)

    class Information(widget.OWWidget.Information):
        loaded = Msg("Imported {} dataset(s): {}")

    class Warning(widget.OWWidget.Warning):
        no_datasets = Msg("No NMR raw data found below that folder.")
        failed = Msg("{} dataset(s) could not be read: {}")
        no_peak = Msg("No peak within {:.2f} ppm of the reference - axis unchanged.")

    # ------------------------------------------------------------- settings
    folder = Setting("")
    selected = Setting([])              # indices into self.datasets (listBox)
    # NOTE: not `window` - that would shadow QWidget.window() and break Orange's
    # status-bar layout with "'str' object is not callable".
    apodization = Setting("exponential")
    lb_hz = Setting(0.3)
    zero = Setting("2")
    skip = Setting(0)                   # 0 = automatic (68 for Varian, 0 Bruker)
    phase = Setting("auto")
    p0 = Setting(0.0)
    p1 = Setting(0.0)
    baseline_order = Setting(0)
    reference = Setting("none")
    manual_shift = Setting(0.0)

    want_main_area = True
    resizing_enabled = True
    graph_name = "preview_canvas"

    def __init__(self):
        super().__init__()
        self.datasets = []
        self._spectra = []              # [(name, ppm, intensity)]
        self.auto_commit = True

        box = gui.vBox(self.controlArea, "Source")
        gui.lineEdit(box, self, "folder", label="Folder: ",
                     orientation=Qt.Horizontal, callback=self._rescan)
        gui.button(box, self, "Browse…", callback=self._browse)
        gui.button(box, self, "Rescan", callback=self._rescan)
        self.lbl_found = gui.label(box, self, "—")

        dbox = gui.vBox(self.controlArea, "Datasets")
        self.list = gui.listBox(
            dbox, self, "selected",
            selectionMode=QAbstractItemView.SelectionMode.ExtendedSelection,
            callback=self._process)
        self.list.setMinimumHeight(110)

        pbox = gui.vBox(self.controlArea, "Processing")
        gui.comboBox(pbox, self, "apodization", items=WINDOWS, label="Window: ",
                     sendSelectedValue=True, callback=self._process)
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
        gui.comboBox(rbox, self, "reference", items=REFERENCE_CHOICES,
                     label="Reference: ", sendSelectedValue=True,
                     callback=self._process)
        gui.doubleSpin(rbox, self, "manual_shift", -20.0, 20.0, 0.01,
                       label="Manual shift (ppm): ", decimals=3,
                       callback=self._process)
        gui.label(rbox, self, "<i>Align a standard, or shift by hand.</i>")

        gui.rubber(self.controlArea)
        gui.auto_apply(self.buttonsArea, self, "auto_commit")

        pvbox = gui.vBox(self.mainArea, "Preview")
        self.preview_canvas = SpectrumCanvas((9, 3.4))
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
        self.list.blockSignals(True)
        self.list.clear()
        self.list.addItems([d.name for d in self.datasets])
        for i in range(count):
            self.list.item(i).setSelected(i in self.selected)
        self.list.blockSignals(False)
        self.lbl_found.setText(f"{count} dataset(s) found" if count
                               else "no dataset found")
        if not self.datasets:
            self.Warning.no_datasets()
            self._spectra = []
            self.preview_canvas.draw_spectrum(None, None, None)
            self.Outputs.spectra.send(None)
            return
        self.Warning.no_datasets.clear()
        self._process()

    def _chosen(self):
        """The ticked datasets (the list box stores row indices)."""
        indices = [i for i in self.selected if 0 <= i < len(self.datasets)]
        if not indices:
            indices = list(range(len(self.datasets)))
        return [self.datasets[i] for i in indices]

    # ------------------------------------------------------------- processing
    def _zero_fill_factor(self):
        value = self.zero
        if isinstance(value, int):                      # an older workflow
            value = ZERO_FILLS[min(max(value, 0), len(ZERO_FILLS) - 1)]
        return int(value) if str(value) in ZERO_FILLS else 2

    def _process(self):
        chosen = self._chosen()
        if not chosen:
            self._spectra = []
            self.preview_canvas.draw_spectrum(None, None, None)
            self.Outputs.spectra.send(None)
            return

        self.Warning.no_peak.clear()
        spectra, failed = [], []
        for dataset in chosen:
            try:
                spectra.append(self._process_one(dataset))
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
        self.Information.loaded(len(spectra),
                               ", ".join(name for name, _, _ in spectra[:3]))
        name, ppm, curve = spectra[0]
        self.preview_canvas.draw_spectrum(ppm, curve, name,
                                          reference_ppm=self._reference_ppm())
        self.commit.now() if self.auto_commit else self.commit.deferred()

    def _process_one(self, dataset):
        """Read + process one dataset -> (name, ppm, intensity)."""
        data, axis, meta = nmr_io.read_vendor(dataset, processed=True)
        if meta["domain"] == "frequency":               # Bruker pdata/1r: ready
            curve = np.real(data)
        else:
            skip = self.skip or (68 if meta["vendor"] == "varian" else 0)
            axis, curve, _info = nmr_io.process_fid(
                np.asarray(data)[skip:], meta,
                lb_hz=self.lb_hz if self.apodization != "none" else 0.0,
                window=self.apodization, zero=self._zero_fill_factor(),
                phase=self.phase, p0=self.p0, p1=self.p1,
                baseline_order=self.baseline_order)
            curve = np.real(curve)
        axis = self._apply_reference(axis, curve)
        return dataset.name, axis, curve

    def _reference_ppm(self):
        """The target ppm of the chosen standard, or None."""
        choice = self.reference
        if isinstance(choice, int):
            choice = REFERENCE_CHOICES[min(max(choice, 0), len(REFERENCE_CHOICES) - 1)]
        key = _REFERENCE_KEY.get(choice)
        return nmr_io.SOLVENT_PPM.get(key) if key else None

    def _apply_reference(self, ppm, curve):
        """Align a standard peak, or apply the manual shift."""
        target = self._reference_ppm()
        if target is not None:
            ppm, delta = nmr_io.align_to_reference(ppm, curve, target)
            if not delta:
                self.Warning.no_peak(0.5)
            return ppm
        if abs(self.manual_shift) > 1e-9:
            return np.asarray(ppm, dtype=float) + float(self.manual_shift)
        return ppm

    # ------------------------------------------------------------- outputs
    @gui.deferred
    def commit(self):
        if not self._spectra:
            self.Outputs.spectra.send(None)
            return
        ppm = np.asarray(self._spectra[0][1], dtype=float)
        attrs = tuple(ContinuousVariable(f"{p:.4f}") for p in ppm)
        dom = Domain(attrs, metas=[StringVariable("sample")])
        rows = []
        for _name, _ppm, curve in self._spectra:
            values = np.asarray(curve, dtype=float)
            if len(values) != len(ppm):                 # different FFT lengths
                values = np.interp(np.linspace(0, 1, len(ppm)),
                                   np.linspace(0, 1, len(values)), values)
            rows.append(values)
        metas = np.array([[name] for name, _, _ in self._spectra], dtype=object)
        table = Table.from_numpy(dom, X=np.vstack(rows), metas=metas)
        table.name = "NMR spectra"
        self.Outputs.spectra.send(table)


if __name__ == "__main__":                       # pragma: no cover
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWNMRImport).run()
