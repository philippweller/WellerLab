"""
orangeplsda - PLS-DA (Partial Least Squares Discriminant Analysis) for Orange3.

Provides a classification learner and widget for PLS-DA.
"""

from .plsda_learner import PLSDALearner, PLSDAModel
from .oplsda_learner import OPLSDALearner, OPLSDAModel

__all__ = ["PLSDALearner", "PLSDAModel", "OPLSDALearner", "OPLSDAModel"]