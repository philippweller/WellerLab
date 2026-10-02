"""
oranjenmr — NMR Preprocessing Widgets for Orange3.

Provides widgets for common preprocessing of 1D NMR spectra
prior to multivariate analysis (PCA, PLS-DA, etc.):
- Binning (bucket width reduction)
- Normalization (area, max, PQN)
- Baseline correction (polynomial, ALS)
- Savitzky-Golay smoothing & derivatives
- Spectral region exclusion
- Chemical shift referencing & alignment
"""

__version__ = "0.1.0"