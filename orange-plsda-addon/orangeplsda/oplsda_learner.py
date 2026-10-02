"""
OPLS-DA (Orthogonal Partial Least Squares Discriminant Analysis)
learner and model.

OPLS-DA separates predictive (class-correlated) from orthogonal
(class-uncorrelated) variation in X, producing clearer interpretation
for biomarker discovery. Implements the Trygg & Wold (2002) algorithm.

The model fits orthogonal components via NIPALS-style deflation, then
extracts the predictive component. The S-Plot (Wiklund et al., 2008)
is derived from the predictive loadings and correlations.
"""

import numpy as np
from Orange.base import Learner
from Orange.classification.base_classification import (
    SklLearnerClassification, SklModelClassification,
)

__all__ = ["OPLSDAModel", "OPLDALearner"]


class OPLSDAModel(SklModelClassification):
    """OPLS-DA classification model.

    Wraps the fitted OPLS parameters (predictive + orthogonal) and
    provides predictions, projections, and S-Plot data.
    """
    supports_multiclass = True

    def __init__(self, skl_model):
        # The "skl_model" attribute is used by SklModel for domain
        # handling, but we don't use sklearn here — store it as None
        # and put our real parameters in custom attributes.
        super().__init__(skl_model)
        self.n_predictive = 0
        self.n_ortho = 0
        # predictive
        self.w_pred = None       # (n_features, 1)
        self.p_pred = None       # (n_features, 1)
        self.t_pred_mean = 0.0   # mean of training t_pred
        self.t_pred_std = 1.0
        # orthogonal per component
        self.w_ortho = []        # list of (n_features, 1) vectors
        self.p_ortho = []        # list of (n_features, 1) vectors
        # scaling
        self.x_mean = None
        self.x_std = None
        self.y_mean = None
        self.y_std = None
        self.scaled = False
        # class info
        self.classes = None
        self.n_classes = 0
        # raw Y predictions for probability computation
        self.y_pred_model = None  # PLS regression model (fitted on deflated X)

    def _deflate(self, X):
        """Apply orthogonal deflation to new X."""
        Xd = X.copy()
        for i in range(self.n_ortho):
            t_o = Xd @ self.w_ortho[i].ravel()
            Xd -= np.outer(t_o, self.p_ortho[i].ravel())
        return Xd

    def _predict_raw(self, X):
        """Compute raw Y scores (predictive Y response)."""
        if self.scaled and self.x_mean is not None:
            Xc = (X - self.x_mean) / self.x_std
        else:
            Xc = X.copy()
        # deflate
        Xd = self._deflate(Xc)
        # predictive score
        t_pred = Xd @ self.w_pred.ravel()
        # project through the PLS model
        y_pred = self.y_pred_model.predict(Xd)
        # unscale Y
        if self.scaled and self.y_std is not None:
            y_pred = y_pred * self.y_std + self.y_mean
        return y_pred

    def predict(self, X):
        """Predict class labels and probabilities.

        Returns a tuple (values, probs) where:
        - values: integer class indices (argmax of raw Y scores)
        - probs: softmax-transformed class probabilities
        """
        y_raw = self._predict_raw(X)
        if y_raw.ndim == 1:
            y_raw = y_raw.reshape(-1, 1)
        values = np.argmax(y_raw, axis=1).astype(float)
        # softmax for probabilities
        y_max = y_raw.max(axis=1, keepdims=True)
        exp_s = np.exp(y_raw - y_max)
        probs = exp_s / exp_s.sum(axis=1, keepdims=True)
        return values, probs

    def __str__(self):
        return f"OPLSDAModel(n_pred={self.n_predictive}, n_ortho={self.n_ortho})"

    def get_splot(self):
        """Return S-Plot coordinates (p and pcorr) for the predictive
        component.

        Returns
        -------
        p : ndarray (n_features,)
            Covariance loading (predictive loading p_pred)
        pcorr : ndarray (n_features,)
            Correlation loading: corr(X_j, t_pred)
        scores : ndarray (n_samples,)
            Predictive scores t_pred for the training data
        """
        p = self.p_pred.ravel().copy()
        # t_pred scores from training
        scores = None  # not stored by default, need to compute
        return p, scores

    def plot_data(self, X_train):
        """Compute complete S-Plot data from training X.

        Parameters
        ----------
        X_train : ndarray (n_samples, n_features)
            The training data (original scale)

        Returns
        -------
        p : ndarray (n_features,)
        pcorr : ndarray (n_features,)
        t_pred : ndarray (n_samples,)
        """
        if self.scaled and self.x_mean is not None:
            Xc = (X_train - self.x_mean) / self.x_std
        else:
            Xc = X_train.copy()
        Xd = self._deflate(Xc)
        t_pred = Xd @ self.w_pred.ravel()

        n = len(t_pred)
        sd_t = np.std(t_pred, ddof=1)
        sd_X = np.std(Xd, axis=0, ddof=1)

        p = self.p_pred.ravel().copy()
        # pcorr_j = p_j * sd(t_pred) / sd(X_j)
        pcorr = np.where(sd_X > 1e-15, p * sd_t / sd_X, 0.0)
        return p, pcorr, t_pred


class OPLSDALearner(SklLearnerClassification):
    """OPLS-DA (Orthogonal Partial Least Squares Discriminant Analysis)
    learner.

    Fits an OPLS model that separates predictive (class-correlated)
    variation from orthogonal (class-uncorrelated) variation.

    Parameters
    ----------
    n_components : int
        Number of predictive PLS components (typically 1 for OPLS)
    n_ortho : int
        Number of orthogonal components to remove
    scale : bool
        Whether to autoscale X (unit variance) before fitting
    max_iter : int
        Maximum NIPALS iterations
    """
    __wraps__ = object  # dummy — no sklearn model
    __returns__ = OPLSDAModel
    supports_multiclass = True

    def __init__(self, n_components=1, n_ortho=1, scale=True,
                 max_iter=500, preprocessors=None):
        super().__init__(preprocessors=preprocessors)
        # NOTE: must set self._params (NOT self.params) — SklLearner.params is
        # a property whose setter filters keys through __wraps__.__init__'s
        # signature. Since __wraps__ = object here (pure-numpy learner), that
        # filter drops every key, leaving params empty.
        self._params = {
            "n_components": n_components,
            "n_ortho": n_ortho,
            "scale": scale,
            "max_iter": max_iter,
        }

    def _pls_first(self, X, Y):
        """Compute the first PLS component of (X, Y) robustly.

        Uses sklearn's PLSRegression which handles multivariate Y (one-hot
        class indicators) correctly. Returns the weight, score, X-loading and
        Y-loading vectors for the first component.

        Returns
        -------
        w : ndarray (n_features,)
        t : ndarray (n_samples,)
        p : ndarray (n_features,)
        c : ndarray (n_class,)
        """
        from sklearn.cross_decomposition import PLSRegression
        pls = PLSRegression(n_components=1)
        pls.fit(X, Y)
        return (pls.x_weights_[:, 0].copy(),
                pls.x_scores_[:, 0].copy(),
                pls.x_loadings_[:, 0].copy(),
                pls.y_loadings_[:, 0].copy())

    def fit(self, X, Y, W=None):
        """Fit the OPLS-DA model.

        X : ndarray (n_samples, n_features)
        Y : ndarray (n_samples,)  — discrete class labels (0, 1, 2, ...)
        W : ignored
        """
        n_classes = len(np.unique(Y))
        n_comp = self.params["n_components"]
        n_ortho = self.params["n_ortho"]
        do_scale = self.params["scale"]

        # Clamp
        n_comp = max(min(n_comp, X.shape[1], X.shape[0] - 1, n_classes), 1)
        n_ortho = max(min(n_ortho, X.shape[1], X.shape[0] - 1), 0)

        # One-hot encode Y
        Y_enc = np.zeros((len(Y), n_classes))
        for i, l in enumerate(Y):
            Y_enc[i, int(l)] = 1.0

        # Center / scale
        x_mean = X.mean(axis=0)
        x_std = np.std(X, axis=0, ddof=1)
        x_std[x_std < 1e-15] = 1.0
        y_mean = Y_enc.mean(axis=0)
        y_std = np.std(Y_enc, axis=0, ddof=1)
        y_std[y_std < 1e-15] = 1.0

        Xc = (X - x_mean) / x_std if do_scale else X - x_mean
        Yc = (Y_enc - y_mean) / y_std if do_scale else Y_enc - y_mean

        model = OPLSDAModel(None)
        model.x_mean = x_mean
        model.x_std = x_std
        model.y_mean = y_mean
        model.y_std = y_std if do_scale else None
        model.scaled = do_scale
        model.classes = np.unique(Y)
        model.n_classes = n_classes
        model.n_predictive = n_comp
        model.n_ortho = n_ortho

        Xk = Xc.copy()
        Yk = Yc.copy()

        # For each orthogonal component: compute PLS direction, remove ortho
        for _ in range(n_ortho):
            w, t, p, c = self._pls_first(Xk, Yk)
            # Orthogonal weight: w_ortho is p with w component removed
            denom = w @ w + 1e-15
            w_o = p - w * (w @ p) / denom
            nw = np.linalg.norm(w_o)
            if nw < 1e-15:
                break
            w_o = w_o / nw
            t_o = Xk @ w_o
            t2_o = t_o @ t_o
            if t2_o < 1e-15:
                break
            p_o = Xk.T @ t_o / t2_o
            Xk -= np.outer(t_o, p_o)
            model.w_ortho.append(w_o)
            model.p_ortho.append(p_o)

        model.n_ortho = len(model.w_ortho)

        # Final predictive component
        w, t_pred, p, c = self._pls_first(Xk, Yk)
        model.w_pred = w.reshape(-1, 1)
        model.p_pred = p.reshape(-1, 1)

        # Store a simple PLS model for Y prediction (on deflated X)
        # We use the pseudo-inverse: B = (Xk'Xk)^{-1} Xk' Yk
        try:
            B = np.linalg.lstsq(Xk, Yk, rcond=None)[0]
        except np.linalg.LinAlgError:
            B = np.zeros((Xk.shape[1], Yk.shape[1]))
        model.y_pred_model = _PLSWrapper(B)

        # Training predictive scores (used for S-Plot)
        model.t_pred_mean = float(np.mean(t_pred))
        model.t_pred_std = float(np.std(t_pred, ddof=1))
        if model.t_pred_std < 1e-15:
            model.t_pred_std = 1.0

        return model

    def incompatibility_reason(self, domain):
        reason = None
        if not domain.has_discrete_class:
            reason = "Categorical (discrete) class variable expected.\n" \
                     "OPLS-DA requires a class variable, not numeric target."
        elif len(domain.class_vars) > 1:
            reason = "OPLS-DA supports only a single class variable."
        return reason

    @property
    def fitted_parameters(self) -> list[Learner.FittedParameter]:
        return [
            self.FittedParameter("n_components", "Predictive comp.", int, 1, None),
            self.FittedParameter("n_ortho", "Orthogonal comp.", int, 0, None),
        ]

    def __str__(self):
        return f"OPLDALearner(pred={self.params['n_components']}, ortho={self.params['n_ortho']})"


class _PLSWrapper:
    """Minimal wrapper so the model can predict Y from deflated X."""
    def __init__(self, B):
        self.B = B

    def predict(self, X):
        return X @ self.B