"""PCA analytics - pure numpy/scipy, headless-testable.

Preprocessing, PCA fit/transform, explained variance, Hotelling T2 and
Q-residual diagnostics (Nomikos & MacGregor style moment-based chi2 limits),
and inlier/outlier masks.

All functions take/return plain numpy arrays (or an Orange Table optionally);
no Qt, no Orange widget imports - so this module can be unit-tested without a
display.
"""

from __future__ import annotations

import numpy as np
from scipy import stats

# ---- residual statistics same as nominal component naming used in the widget


class Preprocess:
    """Parameterized centering/scaling, applied as `scaler(X)` -> (Z, params).

    scale : 'none' | 'center' | 'pareto' | 'auto'
        - 'none'  : raw (no centering, no scaling)
        - 'center': mean-center only  (A=0)
        - 'pareto': center + divide by sqrt(std) (Pareto scaling)
        - 'auto'  : center + divide by std (unit-variance / autoscaling)
    """

    SCALES = ("none", "center", "pareto", "auto")

    def __init__(self, scale: str = "auto"):
        if scale not in self.SCALES:
            raise ValueError(f"scale must be one of {self.SCALES}, got {scale!r}")
        self.scale = scale

    def fit(self, X: np.ndarray):
        X = np.asarray(X, dtype=float)
        n, _ = X.shape
        self.mean_ = X.mean(axis=0)
        d = np.ones(X.shape[1])
        if self.scale != "none":
            std = X.std(axis=0, ddof=1)
            if self.scale == "auto":
                d = np.where(std > 1e-12, std, 1.0)
            elif self.scale == "pareto":
                d = np.where(std > 1e-12, np.sqrt(std), 1.0)
            else:  # center
                d = np.ones(X.shape[1])
        self.scale_ = d
        self._n = n
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=float)
        Z = (X - self.mean_) / self.scale_
        Z[:, self.scale_ <= 0] = 0.0  # guard constant cols after scaling
        return Z


def fit_pca(X: np.ndarray, scale: str = "auto", n_components=None,
            random_state=0):
    """Fit PCA with preprocessing.

    Parameters
    ----------
    X : (n_samples, n_features) ndarray
    scale : Preprocess.SCALES member
    n_components : int, None, or a fractional threshold.
        - int > 1      : keep exactly that many components
        - 0 < float < 1 : keep components until cumulative variance >= that
        - None          : keep all (min(n, p)) components
    random_state : int

    Returns
    -------
    dict with keys: preprocess, loadings (p x c), scores (n x c), eigvals,
        explained_variance_ratio (c,), cumulative (c,), n_components, mean of
        raw X per feature.
    """
    from sklearn.decomposition import PCA

    X = np.asarray(X, dtype=float)
    n, p = X.shape
    if n == 0 or p == 0:
        raise ValueError("PCA needs at least one sample and one feature")

    prep = Preprocess(scale)
    prep.fit(X)
    Z = prep.transform(X)

    max_comp = min(n - 1, p) if n > 1 else 1

    if n_components is None:
        n_comp = max_comp
    elif n_components == "kaiser":
        # need all eigenvalues to evaluate the Kaiser criterion -> fit all,
        # then trim below
        n_comp = max_comp
    elif isinstance(n_components, (int, np.integer)) and n_components > 1:
        n_comp = int(min(n_components, max_comp))
    elif isinstance(n_components, float) and 0 < n_components < 1:
        # resolve after fitting all: pick until cumulative variance threshold
        n_comp = max_comp
    else:
        n_comp = max_comp

    model = PCA(n_components=n_comp, random_state=random_state).fit(Z)
    scores = model.transform(Z)
    loadings = model.components_.T          # p x c   (sklearn rows are directions)
    eigvals = model.explained_variance_     # c,      per-component variance of scores
    ratio = model.explained_variance_ratio_  # c,
    cum = np.cumsum(ratio)

    if n_components == "kaiser":
        # Kaiser (1960): keep components whose eigenvalue exceeds the mean
        # eigenvalue; for autoscaled/correlation PCA this equals the common
        # rule "eigenvalue > 1". Always at least 1 component.
        eig_full = eigvals
        mean_eig = float(eig_full.mean())
        n_keep = int(np.searchsorted(-eig_full, -mean_eig))  # # > mean
        n_keep = int(np.clip(n_keep, 1, n_comp))
        n_comp = n_keep
        scores = scores[:, :n_comp]
        loadings = loadings[:, :n_comp]
        eigvals = eigvals[:n_comp]
        ratio = ratio[:n_comp]
        cum = cum[:n_comp]

    if isinstance(n_components, float) and 0 < n_components < 1:
        # round up to first component reaching the threshold
        n_keep = int(np.searchsorted(cum, n_components)) + 1
        n_keep = int(np.clip(n_keep, 1, n_comp))
        n_comp = n_keep
        scores = scores[:, :n_comp]
        loadings = loadings[:, :n_comp]
        eigvals = eigvals[:n_comp]
        ratio = ratio[:n_comp]
        cum = cum[:n_comp]

    out = {
        "preprocess": prep,
        "loadings": loadings,
        "scores": scores,
        "eigvals": eigvals,
        "explained_variance_ratio": ratio,
        "cumulative": cum,
        "n_components": int(n_comp),
        "y_": None,
    }
    # store full transform for residual reconstruction
    out["model"] = model
    out["_Z"] = Z
    return out


def project(model_fit, X_new: np.ndarray) -> np.ndarray:
    """Project new (already raw) X onto the fitted model -> scores (n x c)."""
    Z = model_fit["preprocess"].transform(np.asarray(X_new, dtype=float))
    return model_fit["model"].transform(Z)


def residual_Q(model_fit, X: np.ndarray, n_components=None) -> np.ndarray:
    """Q residual per sample: squared sum of the reconstruction error.

    Uses `n_components` retained columns of the loadings (default: model's).
    Returns array of length n.
    """
    c = n_components or int(model_fit["n_components"])
    Z = model_fit["preprocess"].transform(np.asarray(X, dtype=float))
    Pc = model_fit["loadings"][:, :c]
    Tc = Z @ Pc                    # (n x c) scores
    rec = Tc @ Pc.T                # reconstruction
    resid = Z - rec
    return np.sum(resid ** 2, axis=1)


def hotelling_T2(model_fit, X: np.ndarray, n_components=None) -> np.ndarray:
    """Hotelling T2 per sample: sum_k score_k^2 / eigenvalue_k."""
    c = n_components or int(model_fit["n_components"])
    eig = model_fit["eigvals"][:c]
    Tc = model_fit["model"].transform(model_fit["preprocess"].transform(
        np.asarray(X, dtype=float)))[:, :c]
    eig_safe = np.where(eig > 1e-15, eig, 1.0)
    return np.sum(Tc ** 2 / eig_safe, axis=1)


# ---- confidence limits -------------------------------------------------------


def t2_limit(n_samples, n_components, alpha=0.05) -> float:
    """Hotelling T2 control limit via F-distribution (Nomikos & MacGregor)."""
    k = n_components
    n = n_samples
    if n - k - 1 <= 0:
        return np.inf
    F = stats.f.ppf(1 - alpha, k, n - k)
    return k * (n - 1) / (n - k) * F


def q_limit_from_Q(Q: np.ndarray, alpha=0.05) -> float:
    """Moment-based scaled chi2 limit for Q residuals (Box/Julier approach).

    Fits Q ~ g * chi2(df) with
        g  = var(Q) / (2 * mean(Q))
        df = 2 * mean(Q)^2 / var(Q)
    then limit = g * chi2.ppf(1-alpha, df). Returns inf if degenerate.
    """
    Q = np.asarray(Q, dtype=float)
    m = Q.mean()
    v = Q.var(ddof=1)
    if not (np.isfinite(m) and np.isfinite(v)) or v <= 1e-30 or m <= 1e-30:
        return float("inf")
    g = v / (2 * m)
    df = 2 * m * m / v
    if df <= 0:
        return float("inf")
    return float(g * stats.chi2.ppf(1 - alpha, df))


class PCAOutliers:
    """Compute T2/Q stats + inlier masks, and refit-on-inliers support."""

    def __init__(self, X: np.ndarray, scale: str = "auto", n_components=None,
                 alpha=0.05, random_state=0):
        self.alpha = alpha
        self.X = X
        self.result = fit_pca(X, scale=scale, n_components=n_components,
                              random_state=random_state)
        self.update_stats()

    def update_stats(self):
        r = self.result
        n = self.X.shape[0]
        self.T2 = hotelling_T2(r, self.X)
        self.Q = residual_Q(r, self.X)
        self.T2_lim = t2_limit(n, r["n_components"], self.alpha)
        self.Q_lim = q_limit_from_Q(self.Q, self.alpha)

    def inlier_mask(self, use_T2=True, use_Q=True) -> np.ndarray:
        m = np.ones(len(self.X), dtype=bool)
        if use_T2 and np.isfinite(self.T2_lim):
            m &= self.T2 <= self.T2_lim
        if use_Q and np.isfinite(self.Q_lim):
            m &= self.Q <= self.Q_lim
        return m