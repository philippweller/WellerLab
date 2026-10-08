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
                                                                           └─> Volcano
                                                                              (log2FC vs -log10 FDR)
```

## Widgets (category *Metabo Weller*)

| Widget | Function |
|--------|----------|
| Metabo Feature Table | Load Compound Discoverer 2-header semicolon CSV; sample×feature Table with `group`/`sample` metas; pseudo-replicate (<3 replicates) hint |
| Metabo Preprocess | Optional imputation (min / k-NN) → sum-normalisation → log2 → autoscale (z) / Pareto |
| Metabo Feature Filter | Drop features by missing fraction, zero variance, constant, or below-detection threshold |
| Metabo Univariate Stats | One-way ANOVA, Welch two-sample t-test, or Kruskal-Wallis per feature + Benjamini-Hochberg FDR + log2FC + group means |
| Metabo Volcano | Volcano plot (log2FC vs. −log10 FDR) for a two-group contrast — taken from the Univariate Stats results, **or computed from Data alone** (Welch t-test + BH-FDR) so Preprocess → Volcano already plots; FDR/\|log2FC\| thresholds, direction colours, top-N labels, PNG/SVG export; **click a point to select a feature** (shift-click to add) to see its per-group distribution as a box plot; emits the significant features and the selected features' sample values |
| Metabo Heatmap | Top-N features by p, Ward/Euclidean row clustering, group bar, PNG/SVG export |

## Correctness

`orangemetabo/metabo_core.py` is the headless, Qt-free analytics core.
The default pipeline (sum-normalise → log2 → autoscale → one-way ANOVA →
BH-FDR) **reproduces the validated ground truth**
`analysis_CV/cv_anova_alle_97_features.csv` exactly: **97/97 features** on
F, p, and FDR (max abs diff < 5e-5). Reproduce with `_test_core.py`
(core) and `_test_e2e.py` (all six widgets, offscreen) — both run against the
Dropbox ground truth and print 97/97. The volcano contrast is checked to equal
the Welch log2FC and the ground-truth `log2FC_ANF_vs_WILD` column.

> **Note on the volcano's fold change:** it is the difference of the per-group
> means *in the space of the data you feed in*. For a real log2 fold change,
> preprocess with **Sum normalisation + log2 and no scaling** (Metabo
> Preprocess → Method "Sum (total area)", log2 on, Scaling "None"). With
> autoscaled/Pareto data the x-axis is a scaled mean difference (the p-values
> are unaffected, since the t-test is scale-invariant per feature).

## Plot interaction

The plot widgets (Metabo Volcano, Metabo Heatmap) behave like any Orange plot
widget:

- **Zoom / pan / home / save** via the matplotlib navigation toolbar above each
  canvas; **wheel over the plot zooms around the cursor**.
- The **volcano legend is draggable** (grab and move it).
- The volcano/box-plot split has a **draggable divider**.
- Orange's **Save graph / copy-to-clipboard / report** entries work
  (`graph_name` is set), and the widget window is resizable.

> Implementation: `orangemetabo/widgets/_plot.py` (`PlotCanvas`, wheel zoom,
> toolbar, draggable legend). Orange's own plots are pyqtgraph based and get
> this for free; the Metabo plots are matplotlib, hence the helper.

## Installation

```bash
cd orange-metabo-addon
/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 -m pip install -e .
```
Or from the monorepo: `python ../orange-install.py metabo`.
