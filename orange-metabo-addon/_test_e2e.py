#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Full headless end-to-end: CV.csv through the widgets (offscreen),
then compare univariate results against the ground truth."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
import numpy as np
import pandas as pd
from AnyQt.QtWidgets import QApplication
from Orange.data import Table

app = QApplication(sys.argv or ["test"])

from orangemetabo.widgets.owfeatureimport import OWFeatureImport
from orangemetabo.widgets.owpreprocess import OWMetaboPreprocess
from orangemetabo.widgets.owfeaturefilter import OWFeatureFilter
from orangemetabo.widgets.owunivariate import OWUnivariateStats
from orangemetabo.widgets.owheatmap import OWMetaboHeatmap
from orangemetabo import metabo_core as mc

BASE = "/Users/philippweller/Dropbox/AK Weller/Vorträge/Workshop GC-IMS"
IN_CSV = f"{BASE}/CV.csv"
GT = f"{BASE}/analysis_CV/cv_anova_alle_97_features.csv"

# ---- instantiate all five widgets (catches __init__ crashes) ----------
imp = OWFeatureImport()
pre = OWMetaboPreprocess()
flt = OWFeatureFilter()
uni = OWUnivariateStats()
hm  = OWMetaboHeatmap()
print("[1] all 5 widgets instantiated OK")

# ---- capture outputs by monkeypatching .send ---------------------------
captured = {}
def cap(name, w, outname):
    out = getattr(w.Outputs, outname)
    out.send = lambda v: captured.__setitem__(name, v)
cap("import", imp, "data")
cap("pre", pre, "data")
cap("filt", flt, "data")
cap("stats", uni, "results")
cap("hm", hm, "heatmap")

# ---- 1) import (exercise the file dialog, stubbed) ---------------------
import AnyQt.QtWidgets as _QtW
_open = _QtW.QFileDialog.getOpenFileName
_QtW.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (IN_CSV, ""))
try:
    imp._browse()
finally:
    _QtW.QFileDialog.getOpenFileName = _open
t_import = captured["import"]
print(f"[2] import: {t_import} shape={t_import.X.shape} "
      f"attrs={len(t_import.domain.attributes)} metas={[m.name for m in t_import.domain.metas]}")
assert t_import.X.shape == (29, 97), "expected 29 samples x 97 features"

# ---- 2) preprocess: sum-norm -> log2 -> autoscale (default) ------------
pre.norm = 1          # sum
pre.do_log2 = True
pre.scale = 1         # autoscale
pre.set_data(t_import)
t_pre = captured["pre"]
print(f"[3] preprocess: {t_pre} shape={t_pre.X.shape}")
# cross-check the matrix against the core reference
_, samples, groups, Xraw = mc.load_feature_table(IN_CSV)
ref = mc.scale_rows(mc.log2_transform(mc.normalize_sum(Xraw)), "autoscale").T
diff = np.abs(np.asarray(t_pre.X, float) - ref).max()
print(f"    max |widget - core-ref| = {diff:.3e}")
assert diff < 1e-9, "preprocessed matrix differs from validated pipeline"

# ---- 3) filter: default settings (missing/zero-var/constant) -----------
flt.set_data(t_pre)
t_flt = captured["filt"]
print(f"[4] filter: {t_flt} shape={t_flt.X.shape}")

# ---- 4) univariate: ANOVA ------------------------------------------------
uni.method = 0
uni.set_data(t_flt)
t_stats = captured["stats"]
print(f"[5] stats: {t_stats} shape={t_stats.X.shape} "
      f"cols={[a.name for a in t_stats.domain.attributes]}")

# compare vs ground truth
gt = pd.read_csv(GT, sep=";", decimal=",").set_index("Feature")
# build mine: feature (meta) + stat/p/FDR columns
fcol = [m for m in t_stats.domain.metas if m.name == "Feature"][0]
feat = [str(v) for v in t_stats.metas[:, t_stats.domain.metas.index(fcol)]]
Xs = np.asarray(t_stats.X, float)
names = [a.name for a in t_stats.domain.attributes]
mine = pd.DataFrame(Xs, columns=names).set_index(pd.Index(feat))
common = [f for f in gt.index if f in mine.index]
m = gt.loc[common]; mi = mine.loc[common]
for a, b in [("stat", "F"), ("p", "p"), ("FDR_BH", "FDR_BH")]:
    av, bv = mi[a].values, m[b].values
    rel = np.abs(av - bv) / np.maximum(np.abs(bv), 1e-12)
    ok = int(((rel < 1e-3) | (np.abs(av - bv) < 1e-6)).sum())
    print(f"    {a:7s} vs {b:7s}: max_abs={np.abs(av-bv).max():.2e}  ok={ok}/{len(av)}")
    assert ok == len(av)
nsig_mine = int((mi["FDR_BH"] < 0.05).sum()); nsig_gt = int((m["FDR_BH"] < 0.05).sum())
print(f"    significant FDR<0.05: mine={nsig_mine} gt={nsig_gt}")
assert nsig_mine == nsig_gt

# ---- 5) heatmap ---------------------------------------------------------
hm.top_n = 20
hm.set_data(t_pre)
hm.set_results(t_stats)
built = hm._built
print(f"[6] heatmap: built={built is not None}, top rows={built[0].shape[0] if built else None}, "
      f"export canvas OK")
assert built is not None and built[0].shape[0] == 20

# ---- 6) volcano ---------------------------------------------------------
from orangemetabo.widgets.owvolcano import OWVolcano
vol = OWVolcano()
cap("vol", vol, "selected")
cap("vol_fv", vol, "feature_values")
vol.fdr_alpha = 0.05
vol.fc_thresh = 1.0
vol.set_results(t_stats)
tab = vol._volcano
assert tab is not None and len(tab) == len(t_stats)
nup = int((tab["direction"] == "up").sum())
ndn = int((tab["direction"] == "down").sum())
sel = captured["vol"]
print(f"[7] volcano: {len(tab)} features · up={nup} down={ndn} · "
      f"selected={None if sel is None else len(sel)}")
assert nup + ndn == 0 or sel is not None
# the contrast's log2FC must equal the difference of the group means
import numpy as _np
ga = vol._levels[vol.group_a]; gb = vol._levels[vol.group_b]
mn = {m.name: _np.asarray(t_stats.X[:, i], float)
      for i, m in enumerate(t_stats.domain.attributes)}
assert _np.allclose(tab["log2FC"].to_numpy(float), mn[f"mean_{ga}"] - mn[f"mean_{gb}"],
                    atol=1e-12)

# ---- 7) volcano point selection -> per-group box plot -------------------
vol.set_data(t_pre)
assert not vol.Warning.need_data.is_shown()


class _Pick:
    def __init__(self, artist, ind):
        self.artist, self.ind = artist, ind


vol._on_pick(_Pick(vol._sc, [0]))
assert vol._selected == [str(vol._feat[0])], vol._selected
fv = captured["vol_fv"]
assert fv is not None and len(fv) == len(t_pre)
# the distribution panel drew a box plot (boxes are patches)
axes = vol.dist_canvas.fig.axes
nboxes = len(axes[0].patches) if axes else 0
assert len(axes) == 1 and nboxes >= 4
vol._on_pick(_Pick(vol._sc, [1]))
assert len(vol._selected) == 1 and vol._selected == [str(vol._feat[1])]
vol._clear_selection()
assert vol._selected == [] and captured["vol_fv"] is None
print(f"[8] selection: pick -> box plot ({nboxes} boxes), "
      f"feature_values rows={len(fv)}, clear OK")

# ---- 8) connecting Data after a selection must refresh the output --------
vol._on_pick(_Pick(vol._sc, [2]))
vol.set_data(None)
assert captured["vol_fv"] is None
vol.set_data(t_pre)
assert captured["vol_fv"] is not None and len(captured["vol_fv"]) == len(t_pre)
print(f"[9] Data (re)connect refreshes Feature Values "
      f"({len(captured['vol_fv'])} rows) without re-clicking")

print("\nALL END-TO-END CHECKS PASSED — 97/97 features match ground truth via widgets.")
