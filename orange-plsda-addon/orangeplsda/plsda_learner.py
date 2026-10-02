"""
PLS-DA (Partial Least Squares Discriminant Analysis) learner and model.

PLSDALearner wraps sklearn's PLSRegression for classification:
1. One-hot encodes class targets (Y)
2. Fits PLSRegression on the encoded targets
3. Predicts by taking the argmax of regression outputs
4. Provides probabilities via softmax transformation
"""

import numpy as np
from sklearn.cross_decomposition import PLSRegression as SKLPLSRegression

from Orange.base import Learner, SklLearner
from Orange.classification.base_classification import (
    SklLearnerClassification, SklModelClassification,
)
from Orange.data import DiscreteVariable


__all__ = ["PLSDALearner", "PLSDAModel"]


class PLSDAModel(SklModelClassification):
    """PLS-DA classification model.

    Wraps a fitted sklearn PLSRegression model. Prediction is done by taking
    the argmax of the continuous regression outputs. Probabilities are
    derived via softmax.
    """

    supports_multiclass = True

    def predict(self, X):
        """Predict class labels and probabilities.

        Returns a tuple (values, probs) where:
        - values: integer class indices (argmax of regression outputs)
        - probs: softmax-transformed class probabilities
        """
        # PLSRegression predict returns n_samples x n_classes
        raw_scores = self.skl_model.predict(X)

        if raw_scores.ndim == 1:
            raw_scores = raw_scores.reshape(-1, 1)

        # Class predictions: argmax over classes
        values = np.argmax(raw_scores, axis=1).astype(float)

        # Probabilities via softmax
        exp_scores = np.exp(raw_scores - raw_scores.max(axis=1, keepdims=True))
        probs = exp_scores / exp_scores.sum(axis=1, keepdims=True)

        return values, probs

    def __str__(self):
        return f"PLSDAModel(n_components={self.skl_model.n_components})"


class PLSDALearner(SklLearnerClassification):
    """PLS-DA (Partial Least Squares Discriminant Analysis) learner.

    Uses sklearn's PLSRegression internally. For classification, the
    discrete target is one-hot encoded into indicator variables, and the
    regression is performed on those. Predictions are decoded back to class
    labels via argmax.
    """

    __wraps__ = SKLPLSRegression
    __returns__ = PLSDAModel
    supports_multiclass = True

    def fit(self, X, Y, W=None):
        """Fit the PLS-DA model.

        One-hot encodes the discrete class labels Y into indicator variables,
        fits PLSRegression, and returns a PLSDAModel.
        """
        params = self.params.copy()
        # Clamp n_components to feasible range
        n_classes = len(np.unique(Y))
        params["n_components"] = min(
            X.shape[1], X.shape[0] - 1, n_classes, params["n_components"]
        )
        params["n_components"] = max(params["n_components"], 1)

        # One-hot encode Y: n_samples x n_classes indicator matrix
        Y_encoded = np.zeros((len(Y), n_classes))
        for i, label in enumerate(Y):
            Y_encoded[i, int(label)] = 1.0

        clf = self.__wraps__(**params)
        clf.fit(X, Y_encoded)
        return self.__returns__(clf)

    def __init__(self, n_components=2, scale=True, max_iter=500,
                 preprocessors=None):
        super().__init__(preprocessors=preprocessors)
        self.params = vars()

    def incompatibility_reason(self, domain):
        """Check if the domain is compatible with PLS-DA."""
        reason = None
        if not domain.has_discrete_class:
            reason = "Categorical (discrete) class variable expected.\n" \
                     "PLS-DA requires a class variable, not a numeric target."
        elif len(domain.class_vars) > 1:
            reason = "PLS-DA supports only a single class variable."
        return reason

    @property
    def fitted_parameters(self) -> list[Learner.FittedParameter]:
        return [
            self.FittedParameter(
                "n_components", "Components", int, 1, None
            )
        ]

    def __str__(self):
        return f"PLSDALearner(n_components={self.params.get('n_components', 2)})"