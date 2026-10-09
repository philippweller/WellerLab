"""
Shared utilities for NMR preprocessing widgets.

Follows the Spectroscopy addon convention: spectral data is stored in a
regular Orange Table where each attribute represents a chemical shift point
and the attribute *name* encodes the ppm value as a float.

Functions
---------
get_ppm_from_attrs(data)
    Parse attribute names as float ppm values. Returns a 1D ndarray.
get_ppm_values(data)
    Alias; tries spectroscopy getx first, falls back to parsing attr names.
"""

import numpy as np


def get_ppm_values(data):
    """Return the ppm axis from an Orange Table.

    Attempts to use orangecontrib.spectroscopy.util.getx() if available,
    otherwise parses attribute names as floats.

    Parameters
    ----------
    data : Orange.data.Table

    Returns
    -------
    ppm : np.ndarray of shape (n_attributes,)
    """
    try:
        from orangecontrib.spectroscopy.util import getx
        return getx(data)
    except (ImportError, Exception):
        return _parse_ppm(data)


def _parse_ppm(data):
    """Parse attribute names as float ppm values."""
    ppm = np.zeros(len(data.domain.attributes), dtype=float)
    for i, attr in enumerate(data.domain.attributes):
        try:
            ppm[i] = float(attr.name)
        except ValueError:
            ppm[i] = i
    return ppm


def make_ppm_attributes(ppm_values):
    """Create Orange ContinuousVariable list with ppm values as names.

    Parameters
    ----------
    ppm_values : array-like of float

    Returns
    -------
    list of Orange.data.ContinuousVariable
    """
    from Orange.data import ContinuousVariable
    return [ContinuousVariable(f"{v:.4f}") for v in ppm_values]


def strip_nan_columns(X, ppm):
    """Remove columns where ALL spectra have NaN.

    Returns
    -------
    X_clean, ppm_clean
    """
    mask = ~np.all(np.isnan(X), axis=0)
    return X[:, mask], ppm[mask]