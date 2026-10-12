#!/usr/bin/env python
"""Write the example workflows in ``examples/`` from the widget registry.

    "/Applications/Orange.app/Contents/MacOS/python" tools/make_workflows.py

The nodes and channels are looked up in the same registry Orange's canvas builds,
so a workflow cannot reference a widget or a signal that does not exist. The files
are plain ``.ows`` - open them with File -> Open (or double-click) in Orange, then
pick the feature table in the "Metabo Feature Table" widget.
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# needs Orange's interpreter: re-runs itself when started with a plain python3, so
# `make workflows` works with whatever python3 is on PATH
from orange_python import reexec_if_needed          # noqa: E402

reexec_if_needed("AnyQt")

from importlib import metadata as md                 # noqa: E402

from AnyQt.QtWidgets import QApplication             # noqa: E402

app = QApplication.instance() or QApplication(sys.argv or ["gen"])

from orangecanvas.registry.qt import QtWidgetRegistry          # noqa: E402
from orangecanvas.scheme import (SchemeLink, SchemeNode,      # noqa: E402
                                 SchemeTextAnnotation)
from orangewidget.workflow.discovery import WidgetDiscovery    # noqa: E402
from orangewidget.workflow.widgetsscheme import WidgetsScheme  # noqa: E402

OUT = os.path.join(ROOT, "examples")

#: how the biplot gets fed, as a note inside every workflow
NOTE = ("Biplot: 'Data' = the (preprocessed) feature table, 'Scores' and "
        "'Loadings' come from the model widget.\n"
        "PCA: Transformed Data -> Scores, Components -> Loadings.\n"
        "OPLS-DA: set 'Predictive components' to 2 or more.\n"
        "Then zoom (wheel), drag a region to reference, "
        "click / shift-click / lasso the arrows to select features,\n"
        "and send 'Selected Data' on to a Data Table, Heatmap or Volcano.")

WORKFLOWS = {
    "biplot_pca.ows": dict(
        title="Biplot from PCA",
        description="Feature table -> preprocess -> PCA -> biplot, features selectable.",
        nodes=[("table", "Metabo Feature Table", (60, 180)),
               ("prep", "Metabo Preprocess", (320, 180)),
               ("pca", "PCA", (580, 120)),
               ("biplot", "Biplot", (860, 100))],
        links=[("table", "Feature Data", "prep", "Feature Data"),
               ("prep", "Preprocessed Data", "pca", "Data"),
               ("prep", "Preprocessed Data", "biplot", "Data"),
               ("pca", "Transformed Data", "biplot", "Scores"),
               ("pca", "Components", "biplot", "Loadings")],
    ),
    "biplot_oplsda.ows": dict(
        title="Biplot from OPLS-DA",
        description=("Feature table -> preprocess -> OPLS-DA -> biplot for a "
                     "two-class contrast."),
        nodes=[("table", "Metabo Feature Table", (60, 180)),
               ("prep", "Metabo Preprocess", (320, 180)),
               ("opls", "OPLS-DA", (580, 120)),
               ("biplot", "Biplot", (860, 100))],
        links=[("table", "Feature Data", "prep", "Feature Data"),
               ("prep", "Preprocessed Data", "opls", "Data"),
               ("prep", "Preprocessed Data", "biplot", "Data"),
               ("opls", "Scores", "biplot", "Scores"),
               ("opls", "Components", "biplot", "Loadings")],
    ),
}


def registry_by_name():
    """Every widget Orange would show - Orange's own plus the WellerLab suite.

    No filtering: the workflows wire Orange's built-in PCA to our Biplot, so both
    entry points must be discovered.
    """
    registry = QtWidgetRegistry()
    WidgetDiscovery(registry).run(md.entry_points(group="orange.widgets"))
    return {widget.name: widget for widget in registry.widgets()}


def output_of(description, name):
    signal = next((s for s in description.outputs if s.name == name), None)
    if signal is None:
        raise KeyError(f"{description.name} has no output {name!r}")
    return signal


def input_of(description, name):
    signal = next((s for s in description.inputs if s.name == name), None)
    if signal is None:
        raise KeyError(f"{description.name} has no input {name!r}")
    return signal


def build(by_name, spec):
    scheme = WidgetsScheme(title=spec["title"], description=spec["description"])
    nodes = {}
    for key, widget_name, position in spec["nodes"]:
        description = by_name.get(widget_name)
        if description is None:
            raise KeyError(f"widget {widget_name!r} not found in the registry")
        node = SchemeNode(description, title=widget_name, position=position)
        scheme.add_node(node)
        nodes[key] = node
    for src, src_name, dst, dst_name in spec["links"]:
        source, sink = nodes[src], nodes[dst]
        scheme.add_link(SchemeLink(
            source, output_of(source.description, src_name),
            sink, input_of(sink.description, dst_name)))
    try:
        scheme.add_annotation(SchemeTextAnnotation((60, 330, 1000, 120), NOTE))
    except Exception as exc:                        # annotation API differences
        print(f"  (annotation skipped: {exc})")
    return scheme


def main():
    os.makedirs(OUT, exist_ok=True)
    by_name = registry_by_name()
    print(f"registry: {len(by_name)} widgets")
    for filename, spec in WORKFLOWS.items():
        scheme = build(by_name, spec)
        path = os.path.join(OUT, filename)
        scheme.save_to(path)
        print(f"  wrote {path}  ({len(scheme.nodes)} nodes, "
              f"{len(scheme.links)} links)")


if __name__ == "__main__":
    main()
