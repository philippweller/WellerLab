"""Minimal spectrum canvas for the NMR widgets (matplotlib, no pyqtgraph).

Kept here rather than reusing the Metabo plot canvas: the NMR family draws a plain
line spectrum, needs nothing interactive, and should not depend on the Metabo
package.
"""
import numpy as np

from AnyQt.QtCore import Qt
from AnyQt.QtWidgets import QSizePolicy

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg, NavigationToolbar2QT)
from matplotlib.figure import Figure


class SpectrumCanvas(FigureCanvasQTAgg):
    """A spectrum plot with an optional reference line."""

    def __init__(self, figsize=(9, 3.4), dpi=100):
        self.fig = Figure(figsize=figsize, dpi=dpi)
        super().__init__(self.fig)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(200)
        self._ax = None

    def draw_spectrum(self, ppm, intensity, title=None, reference_ppm=None):
        """Draw one spectrum; `ppm`/`intensity` None clears the canvas."""
        self.fig.clear()
        ax = self.fig.add_subplot(111)
        self._ax = ax
        if ppm is None or intensity is None:
            ax.text(0.5, 0.5, "Pick a folder with Bruker or Varian/Agilent raw "
                              "data to see a preview.",
                    ha="center", va="center", fontsize=9, color="#6b7684")
            ax.axis("off")
            self.draw_idle()
            return
        ax.plot(ppm, intensity, lw=0.6, color="#1f4e79")
        if reference_ppm is not None:
            ax.axvline(float(reference_ppm), color="#c62828", ls=":", lw=1,
                       label=f"reference {reference_ppm:.2f} ppm")
            ax.legend(fontsize=7, loc="upper right")
        ax.set_xlabel("ppm", fontsize=8)
        ax.set_ylabel("intensity", fontsize=8)
        ax.set_title((title or "")[:80], fontsize=9)
        ax.tick_params(labelsize=7)
        ax.grid(alpha=0.3)
        lo, hi = float(np.min(ppm)), float(np.max(ppm))
        if lo < hi:
            ax.set_xlim(hi, lo)                  # NMR convention: ppm decreasing
        self.fig.tight_layout()
        self.draw_idle()


def attach_spectrum_toolbar(box, canvas, parent):
    """A slim toolbar (home/save) for a SpectrumCanvas."""
    toolbar = NavigationToolbar2QT(canvas, parent)
    actions = getattr(toolbar, "_actions", {})
    for key in ("back", "forward", "pan", "zoom", "configure_subplots",
                "edit_parameters", "subplots"):
        action = actions.get(key)
        if action is not None:
            toolbar.removeAction(action)
    box.layout().addWidget(toolbar)
    return toolbar
