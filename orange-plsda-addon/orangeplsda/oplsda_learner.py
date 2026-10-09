"""
OPLS-DA (Orthogonal Partial Least Squares Discriminant Analysis) learner.

Thin Orange wrapper around `orangeplsda.opls_core`, which holds the actual
numerics (Qt-/Orange-free and therefore headlessly testable). The attributes and
methods that the widget relies on (w_pred, p_pred, p_ortho, w_ortho, x_mean,
x_std, scaled, classes, _predict_raw, plot_data) are kept for compatibility.

New in this version, matching what MetaboAnalyst reports:
    r2x, r2y, q2 (7-fold CV), vip, ortho_vip, perm (permutation test),
    p1 / pcorr (S-plot), n_ortho chosen automatically by Q2.
"""
import numpy as np

from Orange.base import Learner
from Orange.classification.base_classification import (
    SklLearnerClassification, SklModelClassification,
)

from . import opls_core

__all__ = ["OPLSDAModel", "OPLDALearner"]


class OPLSDAModel(SklModelClassification):
    """OPLS-DA classification model (wraps an opls_core.OPLSModel)."""

    supports_multiclass = True

    def __init__(self, skl_model=None):
        super().__init__(skl_model)
        self.core = None            # opls_core.OPLSModel

    # ------------------------------------------------------------ properties
    # convenience read-only views used by the widget
    @property
    def classes(self):
        return self.core.classes if self.core is not None else np.array([])

    @property
    def n_pred(self):
        return int(self.core.n_pred) if self.core is not None else 0

    @property
    def n_ortho(self):
        return int(self.core.n_ortho) if self.core is not None else 0

    @property
    def n_predictive(self):
        return self.n_pred

    @property
    def scaled(self):
        return bool(self.core.scaled) if self.core is not None else False

    @property
    def x_mean(self):
        return self.core.x_mean

    @property
    def x_std(self):
        return self.core.x_std

    @property
    def w_pred(self):
        return self.core.w_pred

    @property
    def p_pred(self):
        return self.core.p_pred

    @property
    def p1(self):
        return self.core.p1

    @property
    def pcorr(self):
        return self.core.pcorr

    @property
    def w_ortho(self):
        return [w.reshape(-1, 1) for w in self.core.w_ortho] if self.core else []

    @property
    def p_ortho(self):
        return [p.reshape(-1, 1) for p in self.core.p_ortho] if self.core else []

    # ------------------------------------------------------------ prediction
    def _deflate(self, X):
        if self.core is None:
            return X
        Xs = (X - self.core.x_mean) / self.core.x_std if self.core.scaled \
            else X - self.core.x_mean
        return self.core.deflate(Xs)

    def _predict_raw(self, X):
        """Raw Y response in the original Y space (n_samples, n_classes)."""
        Xd = self._deflate(np.asarray(X, dtype=float))
        y = Xd @ self.core.w_pred @ self.core.c_pred.T
        if self.core.scaled:
            y = y * self.core.y_std + self.core.y_mean
        return y

    def predict(self, X):
        if self.core is None:
            raise ValueError("model is not fitted")
        return self.core.predict(X)

    def __str__(self):
        if self.core is None:
            return "OPLSDAModel(unfitted)"
        return f"OPLSDAModel({self.core})"

    def plot_data(self, X_train):
        """S-plot coordinates (p1, p(corr), t_pred) for the given data."""
        if self.core is None:
            return None, None, None
        Xd = self._deflate(np.asarray(X_train, dtype=float))
        t_pred = Xd @ self.core.w_pred
        return (self.core.p1, self.core.pcorr,
                t_pred[:, 0] if t_pred.ndim > 1 else t_pred)

    # ------------------------------------------------------------ diagnostics
    def quality(self):
        c = self.core
        if c is None:
            return {}
        return dict(r2x=c.r2x, r2y=c.r2y, q2=c.q2, n_pred=c.n_pred,
                    n_ortho=c.n_ortho, rmsee=c.rmsee)


class OPLSDALearner(SklLearnerClassification):
    """OPLS-DA learner.

    Parameters
    ----------
    n_components : predictive components (MetaboAnalyst/ropls default 1)
    n_ortho : orthogonal components; None or 0 with auto_ortho -> chosen by Q2
    auto_ortho : optimise the orthogonal count via cross-validated Q2
    scale : autoscale X (unit variance); otherwise only centre
    cv_folds : folds for Q2 (ropls/MetaboAnalyst default 7)
    n_perm : permutation tests for R2Y/Q2 (0 = skip, default 0 for speed)
    """
    __wraps__ = object
    __returns__ = OPLSDAModel
    supports_multiclass = True

    def __init__(self, n_components=1, n_ortho=None, scale=True, max_iter=500,
                 auto_ortho=True, cv_folds=7, n_perm=0, max_ortho=5, seed=0,
                 preprocessors=None):
        super().__init__(preprocessors=preprocessors)
        # NOTE: must set self._params (NOT self.params) - SklLearner.params is a
        # property whose setter filters keys through __wraps__.__init__, which is
        # `object` here, so it would drop every key.
        self._params = {
            "n_components": n_components,
            "n_ortho": n_ortho,
            "scale": scale,
            "max_iter": max_iter,
            "auto_ortho": auto_ortho,
            "cv_folds": cv_folds,
            "n_perm": n_perm,
            "max_ortho": max_ortho,
            "seed": seed,
        }

    def fit(self, X, Y, W=None):
        """X (n_samples, n_features), Y (n_samples,) class indices."""
        p = self.params
        core = opls_core.fit_opls(
            np.asarray(X, dtype=float), np.asarray(Y),
            n_pred=p["n_components"],
            n_ortho=p["n_ortho"],
            scale=p["scale"],
            auto_ortho=p["auto_ortho"],
            max_ortho=p["max_ortho"],
            q2_folds=p["cv_folds"],
            seed=p["seed"],
        )
        if p["n_perm"] and p["n_perm"] > 0:
            core.perm = opls_core.permutation_test(
                np.asarray(X, dtype=float), np.asarray(Y),
                n_perm=p["n_perm"], n_pred=p["n_components"],
                n_ortho=p["n_ortho"], max_ortho=p["max_ortho"],
                folds=p["cv_folds"], seed=p["seed"],
            )
        model = OPLSDAModel(None)
        model.core = core
        return model

    def incompatibility_reason(self, domain):
        reason = None
        if not domain.has_discrete_class:
            reason = ("Categorical (discrete) class variable expected.\n"
                      "OPLS-DA requires a class variable, not a numeric target.")
        elif len(domain.class_vars) > 1:
            reason = "OPLS-DA supports only a single class variable."
        return reason

    @property
    def fitted_parameters(self) -> list:
        return [
            self.FittedParameter("n_components", "Predictive comp.", int, 1, None),
            self.FittedParameter("n_ortho", "Orthogonal comp.", int, 0, None),
        ]

    def __str__(self):
        p = self.params
        return f"OPLDALearner(pred={p['n_components']}, ortho={p['n_ortho']})"
