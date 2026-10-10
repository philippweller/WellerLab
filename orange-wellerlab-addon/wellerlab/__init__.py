"""
WellerLab — the complete Orange3 tool suite of the Weller lab.

One distribution, one Orange category ("Weller Lab"):

    wellerlab.metabo  MetaboAnalyst-style feature-table statistics
                      (import, preprocess, filter, univariate, heatmap, volcano)
    wellerlab.plsda   PLS-DA and OPLS-DA (S-plot, VIP, Q2, permutation)
    wellerlab.pca     PCA Pro
    wellerlab.nmr     NMR preprocessing (baseline, binning, exclusion,
                      filter, normalization, reference)

The numerical cores (``metabo.metabo_core``, ``plsda.opls_core``) are free of
Qt/Orange and can be imported and tested headlessly.
"""

__version__ = "0.1.9"
