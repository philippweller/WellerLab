"""Shared Orange Table helpers for the Metabo widgets.

Kept out of `metabo_core` on purpose: the core stays free of Orange so it can be
tested headlessly, while this module needs the Orange data classes.
"""

import numpy as np

from Orange.data import Table, Domain, ContinuousVariable

__all__ = ["select_features"]


def select_features(table, feature_names):
    """`table` restricted to `feature_names`, as sample x feature.

    Unlike Orange's own column selection this KEEPS the class variable and the
    metas (sample/group), which downstream widgets need for grouping/colouring.
    Returns None when nothing can be selected.
    """
    if table is None or not len(feature_names):
        return None
    names = [a.name for a in table.domain.attributes]
    keep = [f for f in feature_names if f in names]
    if not keep:
        return None
    cols = [names.index(f) for f in keep]
    X = np.asarray(table.X, dtype=float)[:, cols]
    domain = Domain([ContinuousVariable(f) for f in keep],
                    table.domain.class_vars, table.domain.metas)
    out = Table.from_numpy(domain, X=X, Y=table.Y, metas=table.metas)
    out.name = "selected data"
    return out
