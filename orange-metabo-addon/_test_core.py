#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless smoke test of metabo_core against the CV ground truth."""
import numpy as np
import pandas as pd
import sys
sys.path.insert(0, "/Users/philippweller/WellerLab/orange-metabo-addon")
from orangemetabo import metabo_core as mc

BASE = "/Users/philippweller/Dropbox/AK Weller/Vorträge/Workshop GC-IMS"
IN_CSV = f"{BASE}/CV.csv"
GT = f"{BASE}/analysis_CV/cv_anova_alle_97_features.csv"

feat, samples, groups, X = mc.load_feature_table(IN_CSV)
print("shape:", X.shape, "| groups:", {g: groups.count(g) for g in dict.fromkeys(groups)})

Xn = mc.normalize_sum(X)
Xl = mc.log2_transform(Xn)
Xs = mc.scale_rows(Xl, "autoscale")
df, levels = mc.univariate(Xs, groups, method="anova", feature_names=feat)

gt = pd.read_csv(GT, sep=";", decimal=",").set_index("Feature")
mine = df.set_index("Feature")
common = [f for f in gt.index if f in mine.index]
m = gt.loc[common]; mi = mine.loc[common]

for a, b, tol in [("stat", "F", 1e-3), ("p", "p", 1e-3), ("FDR_BH", "FDR_BH", 1e-3)]:
    av, bv = mi[a].values, m[b].values
    rel = np.abs(av - bv) / np.maximum(np.abs(bv), 1e-12)
    ok = int(((rel < tol) | (np.abs(av - bv) < 1e-6)).sum())
    print(f"{a:7s} vs {b:7s}: max_abs={np.abs(av-bv).max():.2e}  ok={ok}/{len(av)}")

print("sig FDR<0.05  mine=%d gt=%d" % ((mi["FDR_BH"] < 0.05).sum(), (m["FDR_BH"] < 0.05).sum()))
print("\nTop-5 mine:"); print(mi.head(5)[["stat", "p", "FDR_BH"]].to_string())
print("\nTop-5 GT:  ");  print(m.head(5)[["F", "p", "FDR_BH"]].to_string())
