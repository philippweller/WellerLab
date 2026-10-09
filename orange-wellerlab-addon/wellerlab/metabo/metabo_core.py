#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MetaboAnalyst-style univariate statistics core for GC-MS / GC-IMS
feature tables (Compound Discoverer exports).

This module is the analytics heart of the wellerlab.metabo add-on. It is
deliberately free of any Qt / Orange dependency so it can be unit-tested
headlessly with plain numpy/scipy. The widgets in `orangemetabo/widgets/`
are thin GUI wrappers around the functions here.

Pipeline (matches the validated ground truth `cv_anova_alle_97_features.csv`,
97/97 features on F, p and FDR_BH):

    load -> sum-normalise -> log2 -> autoscale (z-score per feature)
         -> univariate statistics (one-way ANOVA / Welch t / Kruskal-Wallis)
         -> Benjamini-Hochberg FDR

All functions are pure: they take arrays / lists and return DataFrames or
arrays. No file I/O except the optional `load_feature_table` reader.
"""
import csv
import numpy as np
import pandas as pd
from scipy import stats


# --------------------------------------------------------------------------
# Feature-table reader (Compound Discoverer 2-header semicolon CSV)
# --------------------------------------------------------------------------

def load_feature_table(path):
    """Read a Compound Discoverer feature-table CSV.

    Expected layout (semicolon-separated, UTF-8-BOM):
      row 0: "" , "Area: <sample>.raw", ...
      row 1: "" , "<group>",           ...
      row 2+: "<feature name>", values...

    Returns (feature_names: list[str], samples: list[str],
             groups: list[str], X: np.ndarray[features x samples]).
    """
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    samples = [h.replace("Area: ", "").replace(".raw", "").strip()
               for h in rows[0][1:]]
    groups = [g.strip() for g in rows[1][1:]]
    feat = [r[0].strip() for r in rows[2:]]
    X = np.array(
        [[float(v) for v in r[1:1 + len(samples)]] for r in rows[2:]],
        dtype=float,
    )
    return feat, samples, groups, X


# --------------------------------------------------------------------------
# Preprocessing
# --------------------------------------------------------------------------

def normalize_sum(X):
    """Total-area (sum) normalisation: rescale each sample column so that
    every column has the mean of the column totals."""
    col_sums = X.sum(axis=0)
    return X / col_sums * col_sums.mean()


def log2_transform(X):
    """log2 with a guard against non-positive values (clip to tiny eps)."""
    eps = np.finfo(float).tiny
    return np.log2(np.clip(X, eps, None))


def impute_low(X, threshold=0.05, method="knn", k=3):
    """Impute below-threshold values (fraction of column min or a hard cap).

    Methods:
      'constant' : replace with the column minimum (or 0).
      'min'      : replace with the column minimum.
      'knn'      : replace with the mean of the k nearest samples in the
                   Euclidean distance of the non-imputed rows.
    Returns (X_imputed, imputed_mask).
    """
    X = np.asarray(X, dtype=float).copy()
    col_min = X.min(axis=0)
    mask = X < (col_min * (1 + threshold))
    if not mask.any():
        return X, mask
    if method in ("constant", "min"):
        rows, cols = np.nonzero(mask)
        X[rows, cols] = col_min[cols]
        return X, mask
    # knn: distance between samples (columns) over all feature rows;
    # impute each flagged value with the mean of its k nearest samples.
    n_rows, n_cols = X.shape
    d = np.sqrt(((X[:, :, None] - X[:, None, :]) ** 2).sum(axis=0))  # c x c
    np.fill_diagonal(d, np.inf)
    order = d.argsort(axis=1)
    for c in range(n_cols):
        bad = np.nonzero(mask[:, c])[0]
        if bad.size == 0:
            continue
        for r in bad:
            # prefer samples that are not flagged on this same feature
            nb = order[c, :max(k, 1)]
            ok = [j for j in nb if not (mask[r, j] and j != c)]
            if not ok:
                X[r, c] = col_min[c]
            else:
                X[r, c] = X[r, ok].mean()
    return X, mask


def scale_rows(X, method="autoscale"):
    """Per-feature (row) scaling.

      'autoscale' : z-score (mean 0, std 1, ddof=1)
      'pareto'    : (x - mean) / sqrt(std)
      'none'      : unchanged
    Constant rows are returned as zeros (division guard).
    """
    X = np.asarray(X, dtype=float)
    mean = X.mean(axis=1, keepdims=True)
    if method == "none":
        return X
    std = X.std(axis=1, keepdims=True, ddof=1)
    denom = np.where(std > 0, np.sqrt(std) if method == "pareto" else std, 1.0)
    return (X - mean) / denom


# --------------------------------------------------------------------------
# Multiple-testing correction
# --------------------------------------------------------------------------

def bh_fdr(p):
    """Benjamini-Hochberg FDR for an array of p-values."""
    p = np.asarray(p, dtype=float)
    m = len(p)
    if m == 0:
        return p
    order = p.argsort()
    ranked = p[order]
    q = np.minimum.accumulate((ranked * m / np.arange(1, m + 1))[::-1])[::-1]
    qf = np.empty(m)
    qf[order] = np.clip(q, 0, 1)
    return qf


# --------------------------------------------------------------------------
# Univariate statistics
# --------------------------------------------------------------------------

def _groups_arrays(X, groups, levels):
    """Yield the per-group column slices for every feature row."""
    gi = {lv: np.array(groups) == lv for lv in levels}
    return [X[:, idx] for idx in gi.values()]


def univariate(X, groups, method="anova", base=None, treats=None,
               feature_names=None):
    """Run the selected univariate test for every feature row.

    method:
      'anova' : one-way ANOVA across all levels (>= 2 levels, >= 2 per level).
      'welch' : Welch two-sample t-test, `treats` combined vs `base`.
      'kruskal': one-way Kruskal-Wallis across all levels.

    feature_names: optional list of row labels (same length as X rows);
      when given, the `Feature` column holds these names, else row indices.

    Returns (DataFrame, levels). The DataFrame has columns
      Feature, stat, p, (log2FC for welch), FDR_BH,
      sorted by ascending p.
    """
    X = np.asarray(X, dtype=float)
    groups = list(groups)
    levels = list(dict.fromkeys(groups))
    n = X.shape[0]
    names = list(feature_names) if feature_names is not None else list(range(n))
    res = []
    if method in ("anova", "kruskal"):
        for i in range(n):
            cols = [X[i, np.array(groups) == lv] for lv in levels]
            if any(c.size < 2 for c in cols):
                stat, p = np.nan, np.nan
            elif method == "anova":
                stat, p = stats.f_oneway(*cols)
            else:
                stat, p = stats.kruskal(*cols)
            res.append(dict(Feature=names[i], stat=stat, p=p))
    elif method == "welch":
        if base not in levels or not treats:
            raise ValueError("Welch test needs `base` and non-empty `treats`.")
        b = np.array(groups) == base
        a = np.isin(np.array(groups), treats)
        for i in range(n):
            if X[i, a].size < 2 or X[i, b].size < 2:
                stat, p = np.nan, np.nan
                fc = np.nan
            else:
                stat, p = stats.ttest_ind(X[i, a], X[i, b], equal_var=False)
                fc = X[i, a].mean() - X[i, b].mean()
            res.append(dict(Feature=names[i], stat=stat, p=p, log2FC=fc))
    else:
        raise ValueError(f"unknown method {method!r}")

    df = pd.DataFrame(res)
    df["p"] = pd.Series(df["p"]).astype(float)
    df = df.sort_values("p", na_position="last").reset_index(drop=True)
    df["FDR_BH"] = bh_fdr(df["p"].values)
    return df, levels


def add_group_means(df, X, groups, levels, feature_names=None):
    """Append per-group mean columns (on the supplied, usually scaled, X).

    `df` must contain a `Feature` column. When `feature_names` is given it
    maps feature names to their row index in X; otherwise `Feature` values
    are assumed to already be row indices.
    """
    X = np.asarray(X, dtype=float)
    groups = np.asarray(groups)
    out = df.copy()
    if feature_names is not None:
        name_to_row = {n: i for i, n in enumerate(feature_names)}
    else:
        name_to_row = None
    for lv in levels:
        vals = []
        for f in out["Feature"]:
            i = name_to_row.get(f) if name_to_row is not None else f
            vals.append(
                X[i, groups == lv].mean() if (groups == lv).any() else np.nan)
        out[f"mean_{lv}"] = vals
    return out


def format_p(v):
    """Human-friendly p-value string (scientific below 1e-4)."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "NA"
    if v < 1e-4:
        return f"{v:.2e}"
    return f"{v:.4f}"


# --------------------------------------------------------------------------
# Volcano (contrast derived from per-group means)
# --------------------------------------------------------------------------

def volcano_table(df, group_a, group_b, fdr_col="FDR_BH", alpha=0.05, fc=1.0):
    """Build a volcano table for the contrast `group_a` vs `group_b`.

    Operates on a univariate results frame (as produced by `univariate` +
    `add_group_means`): it needs a `Feature` column, the two `mean_<group>`
    columns and an FDR column. Group means live in the (log2) space the data
    was supplied in, so the fold change is their difference:

        log2FC = mean_a - mean_b      (positive => higher in group_a)

    Returns a DataFrame with columns
      Feature, log2FC, FDR_BH, neglog10FDR, direction,
    where direction is "up"  (FDR < alpha and log2FC >=  fc),
                     "down"(FDR < alpha and log2FC <= -fc),
                     "ns"  otherwise.
    """
    ca, cb = f"mean_{group_a}", f"mean_{group_b}"
    for c in ("Feature", ca, cb, fdr_col):
        if c not in df.columns:
            raise ValueError(f"volcano needs column {c!r}")
    lfc = df[ca].to_numpy(float) - df[cb].to_numpy(float)
    fdr = df[fdr_col].to_numpy(float)
    out = pd.DataFrame({
        "Feature": df["Feature"].to_numpy(),
        "log2FC": lfc,
        "FDR_BH": fdr,
        "neglog10FDR": -np.log10(np.clip(fdr, np.finfo(float).tiny, None)),
    })
    sig = fdr < alpha
    out["direction"] = np.where(
        sig & (lfc >= fc), "up",
        np.where(sig & (lfc <= -fc), "down", "ns"))
    return out
