#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Checks for the example workflows in examples/, opened the way Orange opens them.

    python3 run_tests.py        # runs this with the other suites

A workflow file is only useful if Orange reads it back and the wiring is right, so
that is what happens here: load with `Scheme.load_from`, compare the node/link
table, then push a table through the chain *following the links stored in the file*
and check the Biplot ends up with everything it needs.
"""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from AnyQt.QtWidgets import QApplication
from Orange.data import (Table, Domain, ContinuousVariable, DiscreteVariable,
                         StringVariable)

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from importlib import metadata as md                          # noqa: E402
from orangecanvas.registry.qt import QtWidgetRegistry         # noqa: E402
from orangewidget.workflow.discovery import WidgetDiscovery    # noqa: E402
from orangewidget.workflow.widgetsscheme import WidgetsScheme  # noqa: E402

EXAMPLES = os.path.join(HERE, "examples")
app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


def pump(condition, tries=100):
    for _ in range(tries):
        app.processEvents()
        if condition():
            return True
        time.sleep(0.01)
    return condition()


def link_table(scheme):
    return sorted((link.source_node.title, link.source_channel.name,
                   link.sink_node.title, link.sink_channel.name)
                  for link in scheme.links)


EXPECTED_PCA = sorted([
    ("Metabo Feature Table", "Feature Data", "Metabo Preprocess", "Feature Data"),
    ("Metabo Preprocess", "Preprocessed Data", "PCA", "Data"),
    ("Metabo Preprocess", "Preprocessed Data", "Biplot", "Data"),
    ("PCA", "Transformed Data", "Biplot", "Scores"),
    ("PCA", "Components", "Biplot", "Loadings"),
])
EXPECTED_OPLS = sorted([
    ("Metabo Feature Table", "Feature Data", "Metabo Preprocess", "Feature Data"),
    ("Metabo Preprocess", "Preprocessed Data", "OPLS-DA", "Data"),
    ("Metabo Preprocess", "Preprocessed Data", "Biplot", "Data"),
    ("OPLS-DA", "Scores", "Biplot", "Scores"),
    ("OPLS-DA", "Components", "Biplot", "Loadings"),
])


def orange_registry():
    """The registry Orange builds (own widgets + WellerLab) - needed for loading."""
    registry = QtWidgetRegistry()
    WidgetDiscovery(registry).run(md.entry_points(group="orange.widgets"))
    return registry


REGISTRY = orange_registry()


def load(name):
    path = os.path.join(EXAMPLES, name)
    check(f"{name} exists", os.path.isfile(path), path)
    # Exactly how Orange loads a workflow (Orange/canvas/run.py): a WidgetsScheme
    # plus the registry, otherwise the widget definitions cannot be resolved.
    scheme = WidgetsScheme()
    scheme.load_from(path, registry=REGISTRY)
    return scheme


# ---------------------------------------------------------------- the files
pca_scheme = load("biplot_pca.ows")
check("Orange reads the PCA workflow back",
      len(pca_scheme.nodes) == 4 and len(pca_scheme.links) == 5,
      f"{len(pca_scheme.nodes)} nodes, {len(pca_scheme.links)} links")
check("its wiring is the documented one", link_table(pca_scheme) == EXPECTED_PCA,
      f"{link_table(pca_scheme)}")
check("its title and description are set",
      pca_scheme.title == "Biplot from PCA" and bool(pca_scheme.description),
      str(pca_scheme.title))

opls_scheme = load("biplot_oplsda.ows")
check("Orange reads the OPLS-DA workflow back",
      len(opls_scheme.nodes) == 4 and len(opls_scheme.links) == 5,
      f"{len(opls_scheme.nodes)} nodes, {len(opls_scheme.links)} links")
check("its wiring is the documented one", link_table(opls_scheme) == EXPECTED_OPLS,
      f"{link_table(opls_scheme)}")

# ---------------------------------------------------------------- does it run?
# the same call Orange's batch runner uses (Orange/canvas/run.py)
widgets = {node.title: pca_scheme.widget_for_node(node) for node in pca_scheme.nodes}
check("every node of the PCA workflow instantiates a widget",
      all(widgets.values()), f"{sorted(widgets)}")


#: channel name -> handler method. Orange keeps the Input->handler mapping out of
#: reach (the decorated methods carry no reference to their signal), so the wiring
#: below is explicit - what comes from the FILE is which channel feeds which widget
#: (checked by the link-table assertions above).
HANDLERS = {"Data": "set_data", "Scores": "set_scores", "Loadings": "set_loadings",
            "Feature Data": "set_data", "Preprocessed Data": "set_data"}


def input_handler(widget, channel_name):
    method = HANDLERS.get(channel_name)
    if method is None or not hasattr(widget, method):
        raise KeyError(f"{widget.name} has no handler for {channel_name!r}")
    return getattr(widget, method)


def make_forwarder(scheme, widgets_):
    """value -> every widget the file wires to (source_title, source_channel)."""
    def forward(source_title, source_channel):
        targets = [(link.sink_node.title, link.sink_channel.name)
                   for link in scheme.links
                   if link.source_node.title == source_title
                   and link.source_channel.name == source_channel]

        def send(value):
            for title, channel in targets:
                input_handler(widgets_[title], channel)(value)
        return send
    return forward


forward = make_forwarder(pca_scheme, widgets)
prep, pca, biplot = (widgets["Metabo Preprocess"], widgets["PCA"], widgets["Biplot"])
preprocessed = []


def record_and_forward(value):
    """Forward along the file's links and keep the value for inspection."""
    preprocessed.append(value)
    forward("Metabo Preprocess", "Preprocessed Data")(value)


prep.Outputs.data.send = record_and_forward
pca.Outputs.transformed_data.send = forward("PCA", "Transformed Data")
pca.Outputs.components.send = forward("PCA", "Components")

rng = np.random.RandomState(11)
N, P, K = 18, 8, 3
codes = np.repeat(np.arange(K), N // K)
X = rng.normal(10, 1.0, (N, P))
for k in range(K):
    X[codes == k, k] += 3.0
data = Table.from_numpy(
    Domain([ContinuousVariable(f"f{i}") for i in range(P)],
           DiscreteVariable("grp", values=["A", "B", "C"]),
           [StringVariable("sample")]),
    X=X, Y=codes.reshape(-1, 1).astype(float),
    metas=np.array([[f"s{i}"] for i in range(N)], dtype=object))

prep.set_data(data)                       # -> PCA.Data and Biplot.Data
pump(lambda: biplot.data is not None)
pca.set_data(data)                        # -> Biplot.Scores and Biplot.Loadings
pump(lambda: biplot.scores is not None and biplot.loadings is not None)

check("Metabo Preprocess keeps the class variable (regression: from_numpy "
      "without Y crashed on tables that have one)",
      bool(preprocessed) and preprocessed[0] is not None
      and preprocessed[0].domain.class_var is not None
      and len(preprocessed[0]) == N,
      f"{None if not preprocessed else (len(preprocessed[0]), preprocessed[0].domain.class_var)}")

check("the chain from the file fills the biplot's three inputs",
      biplot.data is not None and biplot.scores is not None
      and biplot.loadings is not None,
      f"data={biplot.data is not None}, scores={biplot.scores is not None}, "
      f"loadings={biplot.loadings is not None}")
pump(lambda: biplot._ax_plot is not None)
check("the biplot from the workflow draws arrows",
      biplot._ax_plot is not None and len(biplot._arrow_tips()) > 0,
      f"{len(biplot._arrow_tips())} arrows")
check("its component selector offers the PCA components",
      len(biplot._score_names) >= 2, f"{biplot._score_names}")

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Workflows: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
