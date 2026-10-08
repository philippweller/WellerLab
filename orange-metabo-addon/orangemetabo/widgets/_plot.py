"""Shared matplotlib-canvas helpers for the Metabo widgets.

Orange's own plots are pyqtgraph based, so they get zoom/pan for free; the
Metabo heatmap and volcano are matplotlib canvases and need it explicitly.
`PlotCanvas` provides the interaction users expect from an Orange plot widget:

  * a navigation toolbar (zoom-to-rectangle, pan, home, save),
  * wheel zoom around the cursor,
  * draggable legends (`draggable()`).
"""

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg, NavigationToolbar2QT)
from matplotlib.figure import Figure


class PlotCanvas(FigureCanvasQTAgg):
    """FigureCanvasQTAgg with wheel zoom around the cursor.

    Scrolling zooms the axes under the pointer (wheel up = zoom in); dragging
    with the toolbar's pan/zoom tools works as usual.
    """

    def __init__(self, figsize=(8, 5), dpi=100):
        self.fig = Figure(figsize=figsize, dpi=dpi)
        super().__init__(self.fig)
        self.mpl_connect("scroll_event", self._on_scroll)

    def _on_scroll(self, event):
        ax = getattr(event, "inaxes", None)
        if ax is None or event.xdata is None or event.ydata is None:
            return
        k = 0.8 if event.step > 0 else 1.25      # wheel up = zoom in
        for get, set_, val in ((ax.get_xlim, ax.set_xlim, event.xdata),
                               (ax.get_ylim, ax.set_ylim, event.ydata)):
            lo, hi = get()
            set_(val + (lo - val) * k, val + (hi - val) * k)
        self.draw_idle()


def attach_toolbar(box, canvas, parent):
    """Add a matplotlib navigation toolbar (zoom/pan/home/save) to `box`."""
    toolbar = NavigationToolbar2QT(canvas, parent)
    box.layout().addWidget(toolbar)
    return toolbar


def draggable(legend):
    """Make a matplotlib legend movable by dragging."""
    if legend is not None:
        legend.set_draggable(True)
    return legend
