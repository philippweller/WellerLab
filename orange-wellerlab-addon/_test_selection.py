#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Headless checks for the shared selection helpers (offscreen).

    python3 run_tests.py        # runs this with the other suites

Covers `wellerlab.selection.points_in_polygon` and `LassoPlotWidget`, i.e. the
lasso mechanics used by the pyqtgraph-based OPLS-DA S-plot (the matplotlib
widgets use the equivalent code in metabo/widgets/_plot.py).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from AnyQt.QtCore import QPoint, QPointF, Qt
from AnyQt.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wellerlab.selection import LassoPlotWidget, points_in_polygon

app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


from AnyQt.QtCore import QEvent
from AnyQt.QtGui import QMouseEvent

LB = Qt.MouseButton.LeftButton
NB = Qt.MouseButton.NoButton
NM = Qt.KeyboardModifier.NoModifier


def press(pos):
    """A real QMouseEvent - pyqtgraph's slots reject stand-in objects."""
    p = QPointF(pos)
    return QMouseEvent(QEvent.Type.MouseButtonPress, p, p, LB, LB, NM)


def move(pos):
    p = QPointF(pos)
    return QMouseEvent(QEvent.Type.MouseMove, p, p, NB, LB, NM)


def release(pos):
    p = QPointF(pos)
    return QMouseEvent(QEvent.Type.MouseButtonRelease, p, p, LB, NB, NM)


# --- points_in_polygon ------------------------------------------------------
sq = [(-1, -1), (3, -1), (3, 3), (-1, 3)]
pts = np.array([[0, 0], [5, 5], [2, 2], [1, 2]])
check("points_in_polygon picks exactly the enclosed points",
      list(points_in_polygon(pts, sq)) == [0, 2, 3])
check("points_in_polygon tolerates empty/None input",
      len(points_in_polygon(None, sq)) == 0
      and len(points_in_polygon(pts, None)) == 0
      and len(points_in_polygon(np.zeros((0, 2)), sq)) == 0)
check("points_in_polygon ignores degenerate polygons",
      len(points_in_polygon(pts, [(0, 0), (1, 1)])) == 0)

# --- LassoPlotWidget --------------------------------------------------------
w = LassoPlotWidget()
w.resize(400, 300)
w.show()
w.setXRange(0, 10, padding=0)
w.setYRange(0, 10, padding=0)
app.processEvents()

check("lasso is off by default", not w.lasso_enabled)
w.mousePressEvent(press(QPoint(10, 10)))
check("a press with lasso off does not start a polygon", w._polygon is None)

# coordinate chain: the widget centre must map to the centre of the view range
cx, cy = w.width() // 2, w.height() // 2
x, y = w._view_pos(move(QPoint(cx, cy)))
check("view position maps pixels to data coordinates",
      abs(x - 5.0) < 0.6 and abs(y - 5.0) < 0.6, f"centre -> ({x:.2f}, {y:.2f})")

captured = []
w.on_lasso = captured.append
w.lasso_enabled = True
w.mousePressEvent(press(QPoint(10, 10)))
w.mouseMoveEvent(move(QPoint(300, 10)))
w.mouseMoveEvent(move(QPoint(300, 250)))
w.mouseMoveEvent(move(QPoint(10, 250)))
check("dragging accumulates a polygon", w._polygon is not None
      and len(w._polygon) == 4, f"{0 if w._polygon is None else len(w._polygon)} points")
w.mouseReleaseEvent(release(QPoint(10, 250)))
check("release hands the polygon to on_lasso",
      len(captured) == 1 and len(captured[0]) == 4)
check("a drawn polygon is not left on the plot",
      w._polygon is None and w._artist is None)

captured.clear()
w.mousePressEvent(press(QPoint(10, 10)))
w.mouseMoveEvent(move(QPoint(12, 11)))
w.mouseReleaseEvent(release(QPoint(12, 11)))
check("a click-like drag (<3 points) selects nothing",
      not captured and w._polygon is None)

# the painted polygon uses data coordinates
captured.clear()
w.mousePressEvent(press(QPoint(10, 10)))
w.mouseMoveEvent(move(QPoint(300, 250)))
w.mouseMoveEvent(move(QPoint(20, 250)))
w._show_polygon()
xs, ys = w._artist.getData()
check("the live polygon follows the cursor in data coordinates",
      len(xs) == 4 and xs[0] == xs[-1], f"x={list(np.round(xs, 2))}")
w.mouseReleaseEvent(release(QPoint(20, 250)))

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "Selection-Helpers: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
