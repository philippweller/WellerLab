"""
orangepca - chemometrics PCA widgets for Orange3.

Provides a PCA analysis widget with:
- preprocessing (none / center / pareto / autoscale)
- automatic component selection (Kaiser / fraction-of-variance)
- explained variance (%) on plot axes
- Hotelling T2 and Q-residual outlier diagnostics with filtering.

The analytics live in .pca_analysis (pure numpy/scipy, headless-testable);
the widget in .widgets.owpcawell.
"""

__all__ = ["pca_analysis"]

from . import pca_analysis  # noqa: E402