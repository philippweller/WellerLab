#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Integration checks for the merged WellerLab add-on (offscreen).

    python3 run_tests.py          # runs this together with the other suites

Uses Orange's REAL widget discovery (`orangewidget.workflow.discovery`), which is
what the GUI uses. This is the check that catches a layout in which the category
exists but stays empty - the default package scan only looks at the modules
directly inside the entry-point package.
"""
import importlib
import importlib.metadata as md
import inspect
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from AnyQt.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

app = QApplication.instance() or QApplication(sys.argv or ["test"])

from orangecanvas.registry.qt import QtWidgetRegistry      # noqa: E402
from orangewidget.workflow.discovery import WidgetDiscovery  # noqa: E402

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# --- run the discovery exactly like Orange's canvas does ---------------------
eps = [e for e in md.entry_points(group="orange.widgets") if "wellerlab" in e.value]
check("exactly one entry point for the suite", len(eps) == 1,
      "; ".join(f"{e.name} -> {e.value}" for e in eps))

registry = QtWidgetRegistry()
WidgetDiscovery(registry).run(eps)

discovered = registry.widgets()
check("Orange discovers 15 widgets", len(discovered) == 15, f"{len(discovered)}")

cats = [c for c in registry.categories() if c.name == "Weller Lab"]
check("exactly one 'Weller Lab' category", len(cats) == 1, f"{len(cats)}")

if cats:
    in_cat = registry.widgets(category=cats[0])
    check("the category is NOT empty", len(in_cat) == 15, f"{len(in_cat)} Widgets")
    names = {w.name for w in in_cat}
    expect = {"PCA Pro", "PLS-DA", "OPLS-DA",
              "Metabo Feature Table", "Metabo Preprocess", "Metabo Feature Filter",
              "Metabo Univariate Stats", "Metabo Heatmap", "Metabo Volcano",
              "NMR Baseline Correction", "NMR Binning (Bucketing)",
              "NMR Region Exclusion", "NMR Filter (Savitzky-Golay)",
              "NMR Normalization", "NMR Reference & Alignment"}
    check("all expected widget names present", names == expect,
          f"fehlend={sorted(expect - names)} unerwartet={sorted(names - expect)}")
    check("'PCA Pro' renamed, no 'PCA Weller' left",
          "PCA Pro" in names and not any("PCA Weller" in n for n in names))
    check("category carries colour and icon",
          cats[0].background == "#1F4E79" and cats[0].icon == "icons/WellerLab.svg",
          f"bg={cats[0].background!r} icon={cats[0].icon!r}")
else:
    check("the category is NOT empty", False)
    check("all expected widget names present", False)
    check("'PCA Pro' renamed, no 'PCA Weller' left", False)
    check("category carries colour and icon", False)

# --- icons exist inside the package with one shared geometry ----------------
missing, families = [], {}
for w in discovered:
    module_name, cls_name = w.qualified_name.rsplit(".", 1)
    mod = importlib.import_module(module_name)
    icon = getattr(getattr(mod, cls_name), "icon", None)
    if not icon:
        missing.append(f"{w.name}: kein icon")
        continue
    path = os.path.join(os.path.dirname(inspect.getfile(mod)), icon)
    if not os.path.exists(path):
        missing.append(f"{w.name}: {icon}")
        continue
    svg = open(path, encoding="utf-8").read()
    if 'width="48" height="48"' not in svg or 'rx="8"' not in svg:
        missing.append(f"{w.name}: Geometrie")
    families.setdefault(svg.split('fill="')[1].split('"')[0], []).append(w.name)
check("every widget icon exists with the shared geometry", not missing,
      "; ".join(missing[:3]))
check("one colour per family (metabo/plsda/pca/nmr)", len(families) == 4,
      " | ".join(f"{k}:{len(v)}" for k, v in families.items()))

# --- Qt-free cores stay importable ------------------------------------------
cores = []
for target in ("wellerlab.metabo.metabo_core", "wellerlab.plsda.opls_core"):
    try:
        importlib.import_module(target)
        cores.append(target)
    except Exception as e:
        check(f"core {target} imports", False, type(e).__name__)
check("both numerical cores import", len(cores) == 2)

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Integration: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
