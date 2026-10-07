"""Feature Table Import — read a Compound Discoverer feature table.

Expects the 2-header semicolon CSV layout:
    row 0:  "",  "Area: <sample>.raw", ...
    row 1:  "",  "<group>",            ...
    row 2+: "<feature name>", values ...

Outputs an Orange Table in the standard metabolomics orientation:
  - one continuous attribute per FEATURE (feature name = attribute name)
  - one row per SAMPLE
  - metas: "group" (string) and "sample" (string)
"""

from collections import Counter

import numpy as np

from Orange.data import Table, Domain, ContinuousVariable, StringVariable
from Orange.widgets import widget, gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import Output

from .. import metabo_core as mc


class OWFeatureImport(widget.OWWidget):
    name = "Metabo Feature Table"
    description = ("Import a Compound Discoverer feature table "
                   "(2-header semicolon CSV) with groups per sample.")
    icon = "icons/FeatureImport.svg"
    priority = 3110
    keywords = ("feature table, compound discoverer, gc-ims, gc-ms, "
                "metabolomics")

    want_main_area = False
    resizing_enabled = False

    class Outputs:
        data = Output("Feature Data", Table, default=True)

    # settings
    use_group_meta = Setting(True)

    def __init__(self):
        super().__init__()
        self.file_path = ""
        self._feat = []
        self._samples = []
        self._groups = []
        self._X = None  # features x samples

        box = gui.widgetBox(self.controlArea, "File")
        self.path_lbl = gui.label(box, self, "No file loaded.")
        gui.button(box, self, "Load file…", callback=self._browse)
        gui.checkBox(self.controlArea, self, "use_group_meta",
                     "Include group as meta column",
                     callback=self._reload)
        gui.rubber(self.controlArea)

    # ------------------------------------------------------------------ file
    def _browse(self):
        from Orange.widgets.utils.filedialogs import OpenFileDialog
        fd = OpenFileDialog(
            file_format_filter="Feature table (*.csv);;All files (*)")
        if fd.exec_():
            self.file_path = fd.selectedFiles()[0]
            self._load()

    def _load(self):
        try:
            feat, samples, groups, X = mc.load_feature_table(self.file_path)
        except Exception as exc:
            self.error(f"Could not read file: {exc}")
            self._feat, self._samples, self._groups, self._X = [], [], [], None
            self.path_lbl.setText(f"<b>Error:</b> {exc}")
            self.Outputs.data.send(None)
            return
        self._feat, self._samples, self._groups, self._X = \
            feat, samples, groups, X
        cnt = Counter(groups)
        self.path_lbl.setText(
            f"<b>{len(feat)}</b> features × <b>{len(samples)}</b> samples "
            f"· <b>{len(cnt)}</b> groups")
        dup = {k: v for k, v in cnt.items() if v < 3}
        self.information(
            f"Groups with <3 replicates (pseudo-replication risk): "
            f"{dup if dup else 'none'}")
        self.error()
        self._emit()

    def _reload(self):
        if self.file_path:
            self._load()

    # ------------------------------------------------------------------ output
    def _emit(self):
        if self._X is None:
            self.Outputs.data.send(None)
            return
        X = self._X  # features x samples
        attrs = [ContinuousVariable(n) for n in self._feat]
        meta_vars = [StringVariable("sample")]
        if self.use_group_meta:
            meta_vars.append(StringVariable("group"))
        dom = Domain(attrs, metas=meta_vars)
        X_t = X.T  # samples x features
        if self.use_group_meta:
            m = np.array(
                [[s, g] for s, g in zip(self._samples, self._groups)],
                dtype=object)
        else:
            m = np.array([[s] for s in self._samples], dtype=object)
        table = Table.from_numpy(dom, X=X_t, metas=m)
        table.name = "feature table"
        self.Outputs.data.send(table)

    def close(self):
        self.Outputs.data.send(None)
        super().close()
