"""Table helpers shared by the WellerLab widgets: reading a table's variables.

Separate from `selection.py` (points/cells) and from `metabo_core` (Qt-free
numerics), so the intent of each module stays readable.

The recurring trap these helpers exist for: a **categorical column often arrives
with CODES in the data array**. `metas`/`Y` hold floats - e.g. after
`Table.from_numpy(..., metas=codes)` or a merge - so `str(v)` yields "0.0",
"1.0", … and every legend/axis built from it is labelled with numbers instead of
the group names (reported for the Volcano, Heatmap and Univariate widgets).
"""

import numpy as np

from Orange.data import DiscreteVariable

__all__ = ["variable_of", "labels_of", "looks_numeric", "group_labels"]


def variable_of(table, name):
    """The variable called `name` in `table` (metas, class vars or attributes)."""
    if table is None or name not in table.domain:
        return None
    return table.domain[name]


def labels_of(table, var):
    """Per-row labels for `var`, resolving discrete CODES to their value names."""
    domain = table.domain
    if var in domain.metas:
        vals = table.metas[:, domain.metas.index(var)]
    elif var in domain.class_vars:
        Y = np.asarray(table.Y)
        # Orange stores Y 1-D when the table has a single class variable
        vals = Y if Y.ndim == 1 else Y[:, domain.class_vars.index(var)]
    else:
        vals = np.asarray(table.X)[:, domain.attributes.index(var)]
    if isinstance(var, DiscreteVariable):
        out = []
        for v in vals:
            if isinstance(v, str):
                # Orange stores the value itself in some paths, the code in others
                out.append(v)
            elif np.isfinite(v) and 0 <= int(v) < len(var.values):
                out.append(str(var.values[int(v)]))
            else:
                out.append("?")
        return out
    return [str(v) for v in vals]


def looks_numeric(labels):
    """True when every label parses as a number (i.e. is probably a code)."""
    for label in labels:
        try:
            float(label)
        except (TypeError, ValueError):
            return False
    return True


def group_labels(table, name="group"):
    """(per-row labels, levels) for the column `name`, or (None, []).

    When the named column is purely numeric - i.e. it carries codes with no
    names to resolve - a discrete class variable is used instead: the class
    normally holds the study group, while the stray numeric column does not.
    """
    var = variable_of(table, name)
    if var is None:
        return None, []
    labels = labels_of(table, var)
    if looks_numeric(labels):
        for cv in table.domain.class_vars:
            if isinstance(cv, DiscreteVariable):
                alt = labels_of(table, cv)
                if not looks_numeric(alt):
                    labels = alt
                    break
    return labels, list(dict.fromkeys(labels))
