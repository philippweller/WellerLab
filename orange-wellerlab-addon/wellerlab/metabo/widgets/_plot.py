"""Compatibility shim: the matplotlib plot canvas moved to `wellerlab.plotcanvas`.

It is shared now - the Metabo widgets (Heatmap, Volcano) and the Biplot use it, and
the Biplot lives in the PCA family, so it cannot import from here. Existing imports
keep working through this re-export.
"""
from ...plotcanvas import (PlotCanvas, DRAG_THRESHOLD, attach_toolbar,  # noqa: F401
                           draggable)
from ...selection import points_in_polygon  # noqa: F401  (kept for callers)

__all__ = ["PlotCanvas", "attach_toolbar", "draggable", "DRAG_THRESHOLD",
           "points_in_polygon"]
