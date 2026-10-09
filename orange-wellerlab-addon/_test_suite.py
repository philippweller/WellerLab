#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Integration checks for the merged WellerLab add-on (offscreen).

    /Applications/Orange.app/Contents/MacOS/python _test_suite.py

Verifies the merge itself:
  1. the single entry point loads one module exposing all 15 widgets
  2. widget names are right, including the "PCA Pro" rename
  3. every widget's icon file exists inside the package
  4. the two Qt-free cores import without Orange
  5. the metadata declares exactly one Orange category, "Weller Lab"
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import importlib
import importlib.metadata as md

from AnyQt.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# 1) entry point -> one module with all widgets
eps = [e for e in md.entry_points(group="orange.widgets") if "wellerlab" in e.value]
check("1 exactly one entry point for wellerlab", len(eps) == 1,
      f"{[f'{e.name} -> {e.value}' for e in eps]}")
mod = importlib.import_module(eps[0].value) if eps else None
if mod is None:
    print("kein Entry Point -> Abbruch")
    sys.exit(1)
classes = {n: getattr(mod, n) for n in getattr(mod, "__all__", [])
           if hasattr(getattr(mod, n), "name")}
check("2 all 15 widgets aggregated", len(classes) == 15, f"{len(classes)} Widgets")

names = {c.name for c in classes.values()}
expect = {"PCA Pro", "PLS-DA", "OPLS-DA",
          "Metabo Feature Table", "Metabo Preprocess", "Metabo Feature Filter",
          "Metabo Univariate Stats", "Metabo Heatmap", "Metabo Volcano",
          "NMR Baseline Correction", "NMR Binning (Bucketing)",
          "NMR Region Exclusion", "NMR Filter (Savitzky-Golay)",
          "NMR Normalization", "NMR Reference & Alignment"}
check("3 widget names correct including 'PCA Pro'", names == expect,
      f"fehlend={sorted(expect - names)} unerwartet={sorted(names - expect)}")
check("3b no family still carries its old name",
      not any(n.startswith("PCA Weller") for n in names))

# 3) icons resolvable inside the package
missing = []
for n, cls in classes.items():
    icon = getattr(cls, "icon", None)
    if not icon:
        missing.append(f"{n}: kein icon")
        continue
    pkg_dir = os.path.dirname(importlib.import_module(cls.__module__).__file__)
    if not os.path.exists(os.path.join(pkg_dir, icon)):
        missing.append(f"{n}: {icon}")
check("4 every widget icon exists on disk", not missing, "; ".join(missing[:3]))

# 4) Qt-free cores
cores = []
for target in ("wellerlab.metabo.metabo_core", "wellerlab.plsda.opls_core"):
    try:
        importlib.import_module(target)
        cores.append(target)
    except Exception as e:
        check(f"5 core {target} imports", False, f"{type(e).__name__}")
check("5 both numerical cores import", len(cores) == 2, f"{cores}")

# 5) category
cats = {e.name for e in md.entry_points(group="orange.widgets")
        if "wellerlab" in e.value}
check("6 single category 'Weller Lab'", cats == {"Weller Lab"}, f"{cats}")

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Integration: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
