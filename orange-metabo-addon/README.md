# orangemetabo — MetaboAnalyst-Style Statistics for Orange3

Add-on for **Orange3** that reproduces the **MetaboAnalyst** univariate
workflow for GC-MS / GC-IMS **feature tables** (Compound Discoverer exports),
as used in the coffee-fermentation study (AK Weller).

## Pipeline

```
Feature Table CSV ──> Preprocess ──> [Filter] ──> Univariate Stats ──> Heatmap
 (2-header, ;)       (Sum-Norm,       (QC)         (ANOVA / Welch /     (Top-N,
                       log2, Imputation,             Kruskal + BH-FDR     Ward cluster,
                       Autoscale/Pareto)             + log2FC + means)     PNG/SVG export)
```

## Widgets (category *Metabo Weller*)

| Widget | Function |
|--------|----------|
| Metabo Feature Table | Load Compound Discoverer 2-header semicolon CSV; sample×feature Table with `group`/`sample` metas; pseudo-replicate (<3 replicates) hint |
| Metabo Preprocess | Optional imputation (min / k-NN) → sum-normalisation → log2 → autoscale (z) / Pareto |
| Metabo Feature Filter | Drop features by missing fraction, zero variance, constant, or below-detection threshold |
| Metabo Univariate Stats | One-way ANOVA, Welch two-sample t-test, or Kruskal-Wallis per feature + Benjamini-Hochberg FDR + log2FC + group means |
| Metabo Heatmap | Top-N features by p, Ward/Euclidean row clustering, group bar, PNG/SVG export |

## Correctness

`orangemetabo/metabo_core.py` is the headless, Qt-free analytics core.
The default pipeline (sum-normalise → log2 → autoscale → one-way ANOVA →
BH-FDR) **reproduces the validated ground truth**
`analysis_CV/cv_anova_alle_97_features.csv` exactly: **97/97 features** on
F, p, and FDR (max abs diff < 5e-5). Reproduce with `_test_core.py`
(core) and `_test_e2e.py` (all five widgets, offscreen) — both run against the
Dropbox ground truth and print 97/97.

## Installation

```bash
cd orange-metabo-addon
/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -m pip install -e .
```
Or from the monorepo: `python ../orange-install.py metabo`.
