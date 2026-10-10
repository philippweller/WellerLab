"""Selection helpers shared by the WellerLab widgets.

Two flavours, because the widgets draw with different backends:

* `points_in_polygon` — pure geometry (matplotlib's Path), used by the
  matplotlib widgets (Metabo Heatmap, Volcano) and by the pyqtgraph-based
  OPLS-DA S-plot alike.
* `LassoPlotWidget` — a pyqtgraph PlotWidget with a drag-lasso. The matplotlib
  widgets have their lasso in ``metabo.widgets._plot.PlotCanvas``; pyqtgraph
  widgets get it here so the interaction feels the same in both.
"""

import numpy as np

import pyqtgraph as pg
from AnyQt.QtCore import Qt
from AnyQt.QtGui import QColor

__all__ = ["points_in_polygon", "LassoPlotWidget"]


def points_in_polygon(offsets, polygon):
    """Indices of the points (offsets, data coords) inside the lasso polygon."""
    from matplotlib.path import Path
    if offsets is None or len(offsets) == 0 or polygon is None or len(polygon) < 3:
        return np.array([], dtype=int)
    inside = Path(np.asarray(polygon, dtype=float)).contains_points(
        np.asarray(offsets, dtype=float))
    return np.nonzero(inside)[0]


class LassoPlotWidget(pg.PlotWidget):
    """PlotWidget whose left button can draw a lasso polygon.

    Set `lasso_enabled` and connect `on_lasso(polygon)`, where `polygon` is a
    list of (x, y) in view coordinates - the same contract as the matplotlib
    PlotCanvas, so widgets can share the selection code.  While the lasso is
    active the left button does not pan; the wheel still zooms.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lasso_enabled = False
        self.on_lasso = None            # callable(list[(x, y)])
        self._polygon = None            # [(x, y), ...] while drawing
        self._artist = None

    # ------------------------------------------------------------------ events
    def mousePressEvent(self, ev):
        if self.lasso_enabled and ev.button() == Qt.LeftButton:
            self._polygon = [self._view_pos(ev)]
            self._show_polygon()
            ev.accept()
            return
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev):
        if self._polygon is not None:
            self._polygon.append(self._view_pos(ev))
            self._show_polygon()
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev):
        if self._polygon is not None and ev.button() == Qt.LeftButton:
            polygon, self._polygon = self._polygon, None
            self._clear_polygon()
            if len(polygon) >= 3 and self.on_lasso is not None:
                self.on_lasso(polygon)
            ev.accept()
            return
        super().mouseReleaseEvent(ev)

    # ------------------------------------------------------------------ drawing
    def _view_pos(self, ev):
        """Event position in view (data) coordinates.

        QPointF is not iterable, so unpack x/y explicitly instead of tuple().
        """
        scene = self.mapToScene(ev.position().toPoint())
        p = self.getViewBox().mapSceneToView(scene)
        return float(p.x()), float(p.y())

    def _show_polygon(self):
        pts = self._polygon + [self._polygon[0]] if self._polygon else []
        if self._artist is None:
            self._artist = self.plot([p[0] for p in pts], [p[1] for p in pts],
                                     pen=pg.mkPen(QColor("#111111"), width=1.5,
                                                  style=Qt.DashLine))
        else:
            self._artist.setData([p[0] for p in pts], [p[1] for p in pts])

    def _clear_polygon(self):
        if self._artist is not None:
            try:
                self.removeItem(self._artist)
            except (ValueError, KeyError):
                pass
        self._artist = None
