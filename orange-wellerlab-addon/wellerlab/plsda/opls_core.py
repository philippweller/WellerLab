#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OPLS-DA numerical core — Qt-free / Orange-free, so it can be unit-tested
headlessly with plain numpy/scipy (same architecture as orangemetabo.metabo_core).

Provides what MetaboAnalyst(R) reports for OPLS-DA (`R/stats_opls.R`, engine
= ropls by Thevenot et al.):

    fit OPLS (predictive + orthogonal components, Trygg & Wold 2002)
      -> R2X(cum), R2Y(cum), Q2(cum) via k-fold cross-validation
      -> VIP and orthoVIP        (ropls formula, taken from stats_opls.R)
      -> S-plot coordinates p1 (predictive loading) and p(corr)
      -> optional permutation test (Szymanska et al. 2012)

Algorithm note (this is the part that is easy to get wrong): orthogonal
components must be orthogonal to the PREDICTIVE score, not principal components
of X. Removing plain PCs of X deletes the class signal and collapses R2X/R2Y.
Correct procedure:
  1. first PLS component of (X, Y) -> t_pred, p_pred, w_pred, c
  2. repeat n_ortho times:
       t_o = first PC of the residual X
       t_o -= T_pred @ (T_pred'T_pred)^-1 T_pred't_o      (orthogonalise)
       p_o  = X_res't_o / (t_o't_o);  w_o = p_o/||p_o||
       X_res -= t_o p_o'
  3. final PLS component(s) on the deflated X_res

References
  Trygg J., Wold S. (2002) J. Chemometrics 16:119-128.
  Wiklund S. et al. (2008) Anal. Chem. 80:115-122.        (S-plot)
  Thevenot E.A. et al. (2015) J. Proteome Res. 14:3322.   (ropls)
"""
import numpy as np

__all__ = ["OPLSModel", "fit_opls", "opls_vip", "cross_validated_q2", "permutation_test"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _pca_first(X):
    """First NIPALS component of X -> (t, p), p unit-norm."""
    X = np.asarray(X, dtype=float)
    t = X[:, int(np.argmax(np.sum(X ** 2, axis=0)))].copy()
    p = np.zeros(X.shape[1])
    for _ in range(500):
        p_new = X.T @ t / (t @ t + 1e-300)
        n = np.linalg.norm(p_new)
        if n < 1e-15:
            break
        p_new /= n
        t_new = X @ p_new
        if np.linalg.norm(t_new - t) <= 1e-12 * (np.linalg.norm(t_new) + 1e-300):
            t, p = t_new, p_new
            break
        t, p = t_new, p_new
    return t, p


def _pls(X, Y, n_comp):
    """PLS regression -> (w, t, p, c) for the first n_comp components."""
    from sklearn.cross_decomposition import PLSRegression
    n_comp = max(1, min(n_comp, X.shape[1], X.shape[0] - 1))
    pls = PLSRegression(n_components=n_comp, scale=False)
    pls.fit(X, Y)
    return (pls.x_weights_, pls.x_scores_, pls.x_loadings_, pls.y_loadings_)


def _one_hot(y, classes):
    Y = np.zeros((len(y), len(classes)))
    for i, c in enumerate(classes):
        Y[y == c, i] = 1.0
    return Y


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

class OPLSModel:
    """Fitted OPLS model — everything the widgets need for display."""

    def __init__(self):
        self.classes = np.array([])
        self.n_pred = 0
        self.n_ortho = 0
        # scaling
        self.x_mean = None
        self.x_std = None
        self.y_mean = None
        self.y_std = None
        self.scaled = True
        # predictive part (S-plot uses component 0)
        self.w_pred = None        # (p, n_pred)
        self.p_pred = None        # (p, n_pred)
        self.c_pred = None        # (n_class, n_pred)
        self.t_pred = None        # (n, n_pred)
        self.p1 = None            # (p,)   S-plot x-axis
        self.pcorr = None         # (p,)   S-plot y-axis
        # orthogonal part
        self.w_ortho = []         # list of (p,)
        self.p_ortho = []         # list of (p,)
        self.t_ortho = []         # list of (n,)
        # fit quality
        self.r2x = 0.0            # R2X(cum) incl. orthogonal components
        self.r2y = 0.0            # R2Y(cum) of the predictive part
        self.q2 = None            # Q2(cum) via k-fold CV
        self.rmsee = None
        # importance / validation
        self.vip = None
        self.ortho_vip = None
        self.perm = None
        # sums of squares (kept for the VIP formula)
        self.ssx_tot = 1.0
        self.ssy_tot = 1.0
        self.sxp = np.zeros(1)
        self.syp = np.zeros(1)
        self.sxo = np.zeros(0)
        self.syo = np.zeros(0)

    # ------------------------------------------------------------- transforms
    def _scale_x(self, X):
        X = np.asarray(X, dtype=float)
        if not self.scaled or self.x_mean is None:
            return X - (self.x_mean if self.x_mean is not None else 0.0)
        return (X - self.x_mean) / self.x_std

    def deflate(self, Xs):
        """Remove the fitted orthogonal directions (sequentially)."""
        Xd = np.asarray(Xs, dtype=float).copy()
        for w, p in zip(self.w_ortho, self.p_ortho):
            Xd = Xd - np.outer(Xd @ w, p)
        return Xd

    def transform(self, X):
        """Predictive scores (n, n_pred) for new X."""
        return self.deflate(self._scale_x(X)) @ self.w_pred

    def predict(self, X):
        """Class indices + softmax probabilities."""
        Xd = self.deflate(self._scale_x(X))
        y_raw = Xd @ self.w_pred @ self.c_pred.T
        if self.scaled and self.y_std is not None:
            y_raw = y_raw * self.y_std + self.y_mean
        values = np.argmax(y_raw, axis=1).astype(float)
        e = np.exp(y_raw - y_raw.max(axis=1, keepdims=True))
        return values, e / e.sum(axis=1, keepdims=True)

    def __str__(self):
        q = f", Q2={self.q2:.3f}" if self.q2 is not None else ""
        return (f"OPLSModel(pred={self.n_pred}, ortho={self.n_ortho}, "
                f"R2X={self.r2x:.3f}, R2Y={self.r2y:.3f}{q})")


# --------------------------------------------------------------------------
# core fit
# --------------------------------------------------------------------------

def _fit_core(X, y, n_pred=1, n_ortho=0, scale=True, max_ortho=0):
    """Fit OPLS for a FIXED number of orthogonal components."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y)
    classes = np.unique(y)
    Y = _one_hot(y, classes)

    m = OPLSModel()
    m.classes = classes
    m.scaled = bool(scale)
    m.x_mean = X.mean(axis=0)
    m.x_std = X.std(axis=0, ddof=1)
    m.x_std[m.x_std < 1e-15] = 1.0
    m.y_mean = Y.mean(axis=0)
    m.y_std = Y.std(axis=0, ddof=1)
    m.y_std[m.y_std < 1e-15] = 1.0

    Xs = (X - m.x_mean) / m.x_std if scale else X - m.x_mean
    Yc = (Y - m.y_mean) / m.y_std if scale else Y - m.y_mean

    n_pred = max(1, min(int(n_pred), Xs.shape[1], Xs.shape[0] - 1, len(classes)))

    # 1) initial predictive components -> defines the predictive subspace
    w0, t0, p0, c0 = _pls(Xs, Yc, n_pred)
    T = t0                                     # (n, n_pred) kept fixed for ortho

    # 2) orthogonal components, orthogonal to the predictive subspace
    Xres = Xs.copy()
    n_target = max_ortho if max_ortho else n_ortho
    for _ in range(n_target):
        to, _po = _pca_first(Xres)
        # orthogonalise against the predictive scores
        try:
            to = to - T @ np.linalg.solve(T.T @ T + 1e-12 * np.eye(T.shape[1]), T.T @ to)
        except np.linalg.LinAlgError:
            to = to - T @ (np.linalg.pinv(T.T @ T) @ (T.T @ to))
        t2 = to @ to
        if t2 < 1e-12:
            break
        po = Xres.T @ to / t2
        n_po = np.linalg.norm(po)
        if n_po < 1e-15:
            break
        m.w_ortho.append(po / n_po)
        m.p_ortho.append(po)
        m.t_ortho.append(to)
        Xres = Xres - np.outer(to, po)

    # 3) final predictive components on the deflated matrix
    w, t, p, c = _pls(Xres, Yc, n_pred)
    m.w_pred, m.p_pred = w, p               # (p, n_pred)
    m.t_pred = t
    m.c_pred = c.T if c.shape[0] == n_pred else c   # (n_class, n_pred)
    m.n_pred = n_pred
    m.n_ortho = len(m.w_ortho)

    # 4) fit quality
    ssx_tot = float((Xs ** 2).sum())
    ssy_tot = float((Yc ** 2).sum())
    m.ssx_tot, m.ssy_tot = ssx_tot or 1.0, ssy_tot or 1.0
    m.sxp = np.array([(t[:, a] @ t[:, a]) * (p[:, a] @ p[:, a]) for a in range(n_pred)])
    m.syp = np.array([(t[:, a] @ t[:, a]) * (m.c_pred[:, a] @ m.c_pred[:, a])
                      for a in range(n_pred)])
    m.sxo = np.array([(to @ to) * (po @ po) for to, po in zip(m.t_ortho, m.p_ortho)]) \
        if m.t_ortho else np.zeros(0)
    m.syo = np.zeros_like(m.sxo)
    m.r2x = float((m.sxp.sum() + m.sxo.sum()) / m.ssx_tot)
    m.r2y = float(m.syp.sum() / m.ssy_tot)

    # 5) S-plot from predictive component 0: p1 = loading, p(corr) = p1*sd(t)/sd(X)
    m.p1 = m.p_pred[:, 0].copy()
    Xd = m.deflate(m._scale_x(X))
    sd_t = float(np.std(t[:, 0], ddof=1))
    sd_x = np.std(Xd, axis=0, ddof=1)
    m.pcorr = np.where(sd_x > 1e-15, m.p1 * sd_t / sd_x, 0.0)

    # 6) RMSEE
    Yhat = np.outer(t[:, 0], m.c_pred[:, 0]) if n_pred >= 1 else np.zeros_like(Yc)
    y_hat = Yhat * (m.y_std if scale else 1.0) + m.y_mean
    m.rmsee = float(np.sqrt(np.mean((Y - y_hat) ** 2)))

    # 7) importance
    m.vip = opls_vip(m)
    m.ortho_vip = opls_vip(m, ortho=True)
    return m


def fit_opls(X, y, n_pred=1, n_ortho=None, scale=True, auto_ortho=True,
             max_ortho=5, q2_folds=7, seed=0):
    """Fit an OPLS-DA model.

    n_ortho=None/0 with auto_ortho=True -> the number of orthogonal components
    is chosen by cross-validated Q2 (MetaboAnalyst/ropls optimise this too).
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y)
    max_ortho = max(0, int(max_ortho))

    if n_ortho is None and not auto_ortho:
        n_ortho = 0

    if n_ortho is not None and (n_ortho > 0 or not auto_ortho):
        m = _fit_core(X, y, n_pred=n_pred, n_ortho=int(n_ortho or 0), scale=scale)
        m.q2 = cross_validated_q2(m, X, y, folds=q2_folds, seed=seed)
        return m

    # choose the orthogonal count that maximises Q2
    best, best_q2 = None, -np.inf
    for k in range(max_ortho + 1):
        cand = _fit_core(X, y, n_pred=n_pred, n_ortho=k, scale=scale)
        cand.q2 = cross_validated_q2(cand, X, y, folds=q2_folds, seed=seed)
        score = cand.q2 if cand.q2 is not None else -np.inf
        if score > best_q2:
            best, best_q2 = cand, score
    if best is None:
        best = _fit_core(X, y, n_pred=n_pred, n_ortho=0, scale=scale)
        best.q2 = cross_validated_q2(best, X, y, folds=q2_folds, seed=seed)
    return best


# --------------------------------------------------------------------------
# Q2 (MetaboAnalyst/ropls default: 7-fold cross-validation)
# --------------------------------------------------------------------------

def cross_validated_q2(model, X, y, folds=7, seed=0):
    """Q2(cum) = 1 - PRESS/SS, Y in the centred/scaled space, one-hot columns summed."""
    X = np.asarray(X, dtype=float)
    y = np.asarray(y)
    n = len(y)
    if folds is None or folds < 2 or n < folds * 2:
        return None
    rng = np.random.RandomState(seed)
    chunks = np.array_split(rng.permutation(n), folds)

    Yc = _one_hot(y, model.classes)
    Yc = (Yc - model.y_mean) / (model.y_std if model.scaled else 1.0)
    ss = float((Yc ** 2).sum())
    if ss < 1e-300:
        return None
    press = 0.0
    for k in range(folds):
        te = chunks[k]
        tr = np.concatenate([chunks[j] for j in range(folds) if j != k])
        mm = _fit_core(X[tr], y[tr], n_pred=model.n_pred, n_ortho=model.n_ortho, scale=model.scaled)
        Yh = mm.deflate(mm._scale_x(X[te])) @ mm.w_pred @ mm.c_pred.T
        if mm.scaled:
            Yh = Yh * mm.y_std + mm.y_mean
        Yh_c = (Yh - model.y_mean) / (model.y_std if model.scaled else 1.0)
        press += float(((Yc[te] - Yh_c) ** 2).sum())
    return float(1.0 - press / ss)


# --------------------------------------------------------------------------
# VIP — exact ropls formula as used by MetaboAnalystR stats_opls.R
# --------------------------------------------------------------------------

def opls_vip(model, ortho=False):
    """VIP of the predictive (default) or orthogonal components.

    ropls:  pn = p / ||p||  per component
            k  = n_features / (sxpCum/ssxCum + sypCum/ssyCum)
            VIP_j = sqrt(k * ( sum_a pn_ja^2 sxp_a / ssxCum
                             + sum_a pn_ja^2 syp_a / ssyCum ))
    """
    if ortho:
        if not model.p_ortho:
            return None
        P = np.column_stack(model.p_ortho)          # (p, n_ortho)
        sxp, syp = model.sxo, model.syo
        ssx = float(model.sxo.sum()) or 1.0
        ssy = float(model.syo.sum()) or float(model.ssy_tot)
    else:
        P = model.p_pred
        sxp, syp = model.sxp, model.syp
        ssx = float(model.ssx_tot)
        ssy = float(model.ssy_tot)

    norms = np.sqrt((P ** 2).sum(axis=0))
    norms[norms < 1e-300] = 1.0
    Pn = P / norms
    k = P.shape[0] / ((sxp.sum() / ssx) + (syp.sum() / ssy) if (ssx and ssy) else 1.0)
    v = (Pn ** 2 * sxp).sum(axis=1) / ssx + (Pn ** 2 * syp).sum(axis=1) / ssy
    return np.sqrt(np.maximum(k * v, 0.0))


# --------------------------------------------------------------------------
# permutation test (Szymanska et al. 2012, as in stats_opls.R)
# --------------------------------------------------------------------------

def permutation_test(X, y, n_perm=20, n_pred=1, n_ortho=None, max_ortho=5,
                     folds=7, seed=0):
    """Permute the class labels, refit, compare R2Y/Q2 with the observed model."""
    X = np.asarray(X, float)
    y = np.asarray(y)
    obs = fit_opls(X, y, n_pred=n_pred, n_ortho=n_ortho, max_ortho=max_ortho,
                   q2_folds=folds, seed=seed)
    r2y = [obs.r2y]
    q2 = [obs.q2 if obs.q2 is not None else np.nan]
    rng = np.random.RandomState(seed + 1)
    for i in range(int(n_perm)):
        yp = rng.permutation(y)
        try:
            mm = fit_opls(X, yp, n_pred=n_pred, n_ortho=n_ortho, max_ortho=max_ortho,
                          q2_folds=folds, seed=seed + 2 + i)
        except Exception:
            continue
        r2y.append(mm.r2y)
        q2.append(mm.q2 if mm.q2 is not None else np.nan)
    r2y = np.array(r2y, float); q2 = np.array(q2, float)
    p_r2y = float((1 + np.sum(r2y[1:] >= r2y[0])) / (1 + len(r2y) - 1))
    ok = ~np.isnan(q2)
    p_q2 = None
    if ok[0] and ok[1:].sum() > 0:
        p_q2 = float((1 + np.sum(q2[1:][ok[1:]] >= q2[0])) / (1 + int(ok[1:].sum())))
    return dict(r2y=r2y, q2=q2, r2y_obs=float(r2y[0]), q2_obs=float(q2[0]),
                r2y_perm_mean=float(np.nanmean(r2y[1:])),
                q2_perm_mean=float(np.nanmean(q2[1:])) if ok[1:].any() else None,
                p_r2y=p_r2y, p_q2=p_q2)
