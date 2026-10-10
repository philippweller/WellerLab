"""Shared matplotlib-canvas helpers for the Metabo widgets.

Orange's own plots are pyqtgraph based and get pan/zoom/reset for free; the
Metabo heatmap and volcano are matplotlib canvases, so the interaction is
implemented here explicitly — and, importantly, it survives redraws (a plain
matplotlib canvas autoscales on every draw, which silently discards the user's
zoom).

Interaction provided by `PlotCanvas`:

  * wheel over the plot zooms around the cursor,
  * dragging with the left button pans,
  * a left click (no drag) calls `on_click(axes, xdata, ydata)` — used by the
    volcano for point selection, with a pixel tolerance so edge points work,
  * with `lasso_enabled` a left drag draws a polygon and calls
    `on_lasso(axes, [(x, y), ...])` on release (panning is off while it is on),
  * `reset_view()` restores the automatic view; `after_draw()` keeps the
    user's zoom across redraws.

`attach_toolbar()` adds matplotlib's navigation toolbar (save / home / zoom
rect / pan) and `draggable()` makes a legend movable.
"""

import numpy as np
from typing import Callable, Optional
from AnyQt.QtCore import Qt
from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg, NavigationToolbar2QT)
from matplotlib.figure import Figure

CLICK_TOLERANCE = 12        # px radius for click selection
DRAG_THRESHOLD = 3          # px before a press counts as a pan drag


class PlotCanvas(FigureCanvasQTAgg):
    def __init__(self, figsize=(8, 5), dpi=100):
        self.fig = Figure(figsize=figsize, dpi=dpi)
        super().__init__(self.fig)
        self.setFocusPolicy(Qt.StrongFocus)
        self.main_axes = None      # the axes the view is kept for
        self.home = None           # (xlim, ylim) of the automatic view
        self.view = None           # the user's current view (None = home)
        self.on_click: Optional[Callable] = None   # callback(axes, xdata, ydata)
        self.on_lasso: Optional[Callable] = None   # callback(axes, [(x, y), ...])
        self.lasso_enabled = False
        self.toolbar = None
        self._press = None
        self._lasso = None                         # (axes, [data points])
        self._lasso_artist = None

    # ------------------------------------------------------------------ view
    def after_draw(self, ax, new_data=False):
        """Call after every redraw. Keeps the user's zoom unless data changed."""
        axis = ax or (self.fig.axes[0] if self.fig.axes else None)
        if axis is None:
            return
        self.main_axes = axis
        if new_data or self.home is None:
            self.home = (axis.get_xlim(), axis.get_ylim())
            self.view = None
        if self.view is not None:
            axis.set_xlim(*self.view[0])
            axis.set_ylim(*self.view[1])

    def reset_view(self):
        """Back to the automatic (home) view; also clears any toolbar mode."""
        if self.toolbar is not None:
            self.toolbar.mode = ""
            try:
                self.toolbar._update_buttons_checked()
            except Exception:
                pass
        self.view = None
        if self.home is not None and self.main_axes is not None:
            self.main_axes.set_xlim(*self.home[0])
            self.main_axes.set_ylim(*self.home[1])
        self.draw_idle()

    def _remember(self, ax):
        if ax is self.main_axes:
            self.view = (ax.get_xlim(), ax.get_ylim())

    # --------------------------------------------------------------- helpers
    def _axes_at(self, x, y):
        for ax in reversed(self.fig.axes):
            if ax.bbox.contains(x, y):
                return ax
        return None

    @staticmethod
    def _steps(event):
        if not event.pixelDelta().isNull():
            return event.pixelDelta().y()
        return event.angleDelta().y() / 120.0

    # ------------------------------------------------------------ wheel zoom
    def zoom_at(self, ax, x, y, steps):
        """Zoom `ax` around the display point (x, y) by `steps` wheel notches."""
        cx, cy = ax.transData.inverted().transform((x, y))
        k = 0.8 ** steps                       # wheel up (steps>0) zooms in
        xl, yl = ax.get_xlim(), ax.get_ylim()
        ax.set_xlim(cx + (xl[0] - cx) * k, cx + (xl[1] - cx) * k)
        ax.set_ylim(cy + (yl[0] - cy) * k, cy + (yl[1] - cy) * k)
        self._remember(ax)

    def wheelEvent(self, event):
        x, y = self.mouseEventCoords(event)
        ax = self._axes_at(x, y)
        steps = self._steps(event)
        if ax is None or not steps:
            super().wheelEvent(event)
            return
        self.zoom_at(ax, x, y, steps)
        self.draw_idle()
        event.accept()                          # don't let a parent scroll

    # ------------------------------------------------- pan drag / click sel
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            x, y = self.mouseEventCoords(event)
            ax = self._axes_at(x, y)
            if ax is not None:
                if self.lasso_enabled and self.on_lasso is not None:
                    self._start_lasso(ax, x, y)
                else:
                    self._press = (x, y, ax, ax.get_xlim(), ax.get_ylim(), False)
        super().mousePressEvent(event)

    def pan_by(self, ax, x0, y0, x1, y1, xl0, yl0):
        """Pan `ax` so the display point (x0, y0) follows the cursor to (x1, y1)."""
        inv = ax.transData.inverted()
        dx = inv.transform((x0, y0))[0] - inv.transform((x1, y1))[0]
        dy = inv.transform((x0, y0))[1] - inv.transform((x1, y1))[1]
        ax.set_xlim(xl0[0] + dx, xl0[1] + dx)
        ax.set_ylim(yl0[0] + dy, yl0[1] + dy)
        self._remember(ax)

    def mouseMoveEvent(self, event):
        if self._lasso is not None and (event.buttons() & Qt.LeftButton):
            ax = self._lasso[0]
            x, y = self.mouseEventCoords(event)
            self._lasso[1].append(ax.transData.inverted().transform((x, y)))
            self._update_lasso()
            self.draw_idle()
            super().mouseMoveEvent(event)
            return
        if self._press is not None and (event.buttons() & Qt.LeftButton):
            x0, y0, ax, xl0, yl0, moved = self._press
            x, y = self.mouseEventCoords(event)
            if moved or abs(x - x0) + abs(y - y0) > DRAG_THRESHOLD:
                self.pan_by(ax, x0, y0, x, y, xl0, yl0)
                self._press = (x0, y0, ax, xl0, yl0, True)
                self.draw_idle()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._lasso is not None and event.button() == Qt.LeftButton:
            ax, pts = self._lasso
            self._lasso = None
            self._clear_lasso_artist()
            self.draw_idle()
            if len(pts) >= 3 and self.on_lasso is not None:
                self.on_lasso(ax, list(pts))
            super().mouseReleaseEvent(event)
            return
        press, self._press = self._press, None
        if (event.button() == Qt.LeftButton and press is not None
                and not press[5] and self.on_click is not None):
            ax = press[2]
            x, y = self.mouseEventCoords(event)
            self._remember(ax)
            self.on_click(ax, *ax.transData.inverted().transform((x, y)))
        super().mouseReleaseEvent(event)

    # -------------------------------------------------------------- lasso
    def _start_lasso(self, ax, x, y):
        self._lasso = (ax, [ax.transData.inverted().transform((x, y))])
        self._lasso_artist, = ax.plot([], [], color="#111", lw=1.2, ls="--",
                                      alpha=0.9, zorder=10)

    def _update_lasso(self):
        if self._lasso is None or self._lasso_artist is None:
            return
        pts = self._lasso[1]
        self._lasso_artist.set_data([p[0] for p in pts] + [pts[0][0]],
                                    [p[1] for p in pts] + [pts[0][1]])

    def _clear_lasso_artist(self):
        if self._lasso_artist is not None:
            try:
                self._lasso_artist.remove()
            except (ValueError, AttributeError):
                pass
        self._lasso_artist = None

    # ------------------------------------------------------- nearest feature
    def nearest_point(self, ax, xdata, ydata, offsets):
        """Index of the scatter point nearest to (xdata, ydata), or None when
        nothing is within CLICK_TOLERANCE pixels (so edge points are clickable)."""
        if offsets is None or len(offsets) == 0:
            return None
        px, py = ax.transData.transform((xdata, ydata))
        disp = ax.transData.transform(np.asarray(offsets, dtype=float))
        d = np.hypot(disp[:, 0] - px, disp[:, 1] - py)
        i = int(np.argmin(d))
        return i if d[i] <= CLICK_TOLERANCE else None


def points_in_polygon(offsets, polygon):
    """Indices of the points (offsets, data coords) inside the lasso polygon."""
    from matplotlib.path import Path
    if offsets is None or len(offsets) == 0 or len(polygon) < 3:
        return np.array([], dtype=int)
    inside = Path(np.asarray(polygon, dtype=float)).contains_points(
        np.asarray(offsets, dtype=float))
    return np.nonzero(inside)[0]


def attach_toolbar(box, canvas, parent):
    """Add a slim matplotlib toolbar to `box`: Home (= reset view) and Save.

    The pan/zoom/back/forward/subplots actions are removed: panning and zooming
    are done directly on the canvas (`PlotCanvas`), and matplotlib's modal
    tools would swallow the left button, so point selection became impossible
    until the user figured out how to leave the mode again.
    """
    toolbar = NavigationToolbar2QT(canvas, parent)
    acts = getattr(toolbar, "_actions", {})
    for key in ("back", "forward", "pan", "zoom",
                "configure_subplots", "edit_parameters"):
        action = acts.get(key)
        if action is not None:
            toolbar.removeAction(action)
    home = acts.get("home")
    if home is not None:
        home.setToolTip("Reset view")
        try:
            home.triggered.disconnect()
        except (TypeError, RuntimeError):
            pass
        home.triggered.connect(lambda *_: canvas.reset_view())
    box.layout().addWidget(toolbar)
    canvas.toolbar = toolbar
    return toolbar


def draggable(legend):
    """Make a matplotlib legend movable by dragging."""
    if legend is not None:
        legend.set_draggable(True)
    return legend