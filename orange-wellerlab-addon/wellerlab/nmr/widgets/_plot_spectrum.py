"""Spectrum canvas for the NMR widgets: plot, zoom, region selection.

Kept here rather than reusing the Metabo plot canvas - the NMR family draws a plain
line spectrum and should not depend on the Metabo package.

Interaction (chosen so that nothing competes for a button):
* **left drag**   - mark a region (used for referencing, e.g. the CHCl3 line)
* **wheel**       - zoom around the cursor
* **right drag**  - pan
* **reset_zoom()**- back to the range the widget asked for
"""
import numpy as np

from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import QSizePolicy

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg, NavigationToolbar2QT)
from matplotlib.figure import Figure
from matplotlib.widgets import SpanSelector

ZOOM_STEP = 0.8                     # per wheel notch


class SpectrumCanvas(FigureCanvasQTAgg):
    """Spectrum plot with a reference line, a region selection and zoom."""

    def __init__(self, figsize=(9, 3.4), dpi=100):
        self.fig = Figure(figsize=figsize, dpi=dpi)
        super().__init__(self.fig)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self.setFocusPolicy(Qt.StrongFocus)
        self._ax = None
        self._span = None
        self._home = None            # x limits the widget asked for
        self._press = None           # (x, y) while panning
        #: called with (low_ppm, high_ppm) whenever the user drags a region
        self.on_region = None
        self.setCursor(Qt.CrossCursor)

    # ------------------------------------------------------------------ drawing
    def draw_spectrum(self, ppm, intensity, title=None, reference_ppm=None,
                      region=None, view=None):
        """Draw one spectrum; `ppm`/`intensity` None clears the canvas.

        `view` is an (low, high) ppm tuple for the x axis - the widget's requested
        range (0 .. 10 ppm by default). `set_view` can change it later.
        """
        self.fig.clear()
        self._span = None
        ax = self.fig.add_subplot(111)
        self._ax = ax
        if ppm is None or intensity is None:
            ax.text(0.5, 0.5, "Pick a folder with Bruker or Varian/Agilent raw "
                              "data to see a preview.",
                    ha="center", va="center", fontsize=9, color="#6b7684")
            ax.axis("off")
            self._home = None
            self.draw_idle()
            return
        ax.plot(ppm, intensity, lw=0.6, color="#1f4e79")
        if region is not None and None not in region:
            lo, hi = sorted(float(v) for v in region)
            ax.axvspan(lo, hi, color="#ff9100", alpha=0.25, zorder=0)
        if reference_ppm is not None:
            ax.axvline(float(reference_ppm), color="#c62828", ls=":", lw=1.2,
                       label=f"reference {reference_ppm:.2f} ppm")
            ax.legend(fontsize=7, loc="upper right")
        ax.set_xlabel("ppm", fontsize=8)
        ax.set_ylabel("intensity", fontsize=8)
        ax.set_title((title or "")[:90], fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
        self._home = self._limits(ppm) if view is None else self._ordered(*view)
        ax.set_xlim(*self._home)
        self._install_span_selector(ax)
        self.fig.tight_layout()
        self.draw_idle()

    @staticmethod
    def _limits(ppm):
        """Full ppm window, drawn high-to-low (NMR convention)."""
        lo, hi = float(np.min(ppm)), float(np.max(ppm))
        return (hi, lo)

    @staticmethod
    def _ordered(low, high):
        """(low, high) -> the x limits tuple, high first."""
        lo, hi = sorted((float(low), float(high)))
        return (hi, lo)

    def _install_span_selector(self, ax):
        """Left drag marks a region (right drag and the wheel stay free)."""
        self._span = SpanSelector(
            ax, self._region_selected, "horizontal", useblit=False,
            props=dict(alpha=0.25, facecolor="#ff9100"), interactive=False,
            button=1)

    def _region_selected(self, xmin, xmax):
        if self.on_region is None:
            return
        lo, hi = sorted((float(xmin), float(xmax)))
        if hi - lo < 1e-6:
            return
        self.on_region(lo, hi)

    # ------------------------------------------------------------------ view
    @property
    def home(self):
        return self._home

    def set_view(self, low, high):
        """Set the x range (ppm) and remember it as the home view."""
        if self._ax is None:
            return
        self._home = self._ordered(low, high)
        self._ax.set_xlim(*self._home)
        self.draw_idle()

    def reset_zoom(self):
        """Back to the widget's range (0 .. 10 ppm by default)."""
        if self._ax is not None and self._home is not None:
            self._ax.set_xlim(*self._home)
            self.draw_idle()

    def zoom_at(self, x, y, steps):
        """Zoom around the data point (x, y) by `steps` wheel notches."""
        if self._ax is None or not steps:
            return
        k = ZOOM_STEP ** steps                     # wheel up (steps>0) zooms in
        xl = self._ax.get_xlim()
        self._ax.set_xlim(x + (xl[0] - x) * k, x + (xl[1] - x) * k)
        self.draw_idle()

    def pan_by(self, x0, x1):
        """Pan so the data point x0 follows the cursor to x1."""
        if self._ax is None:
            return
        delta = x0 - x1
        xl = self._ax.get_xlim()
        self._ax.set_xlim(xl[0] + delta, xl[1] + delta)
        self.draw_idle()

    # ------------------------------------------------------------------ events
    def wheelEvent(self, event):
        if self._ax is None:
            super().wheelEvent(event)
            return
        steps = event.angleDelta().y() / 120.0
        position = self.mouseEventCoords(event)
        if position is None:
            super().wheelEvent(event)
            return
        x, _y = position
        data_x = self._ax.transData.inverted().transform((x, _y))[0]
        self.zoom_at(data_x, 0.0, steps)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton and self._ax is not None:
            position = self.mouseEventCoords(event)
            if position is not None:
                self._press = (position[0], self._ax.transData.inverted()
                               .transform(position)[0])
            event.accept()
            super().mousePressEvent(event)
            return
        self._press = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and (event.buttons() & Qt.RightButton):
            position = self.mouseEventCoords(event)
            if position is not None:
                now = self._ax.transData.inverted().transform(position)[0]
                self.pan_by(self._press[1], now)
                self._press = (position[0], now)
            event.accept()
            super().mouseMoveEvent(event)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ helpers
    @property
    def has_span(self):
        return self._span is not None


def attach_spectrum_toolbar(box, canvas, parent):
    """A slim toolbar (home/save) for a SpectrumCanvas.

    Pan/zoom are done directly on the canvas (wheel / right drag) so that the left
    button stays free for the region selection - matplotlib's modal tools would
    swallow it.
    """
    toolbar = NavigationToolbar2QT(canvas, parent)
    actions = getattr(toolbar, "_actions", {})
    for key in ("back", "forward", "pan", "zoom", "configure_subplots",
                "edit_parameters", "subplots"):
        action = actions.get(key)
        if action is not None:
            toolbar.removeAction(action)
    box.layout().addWidget(toolbar)
    return toolbar
