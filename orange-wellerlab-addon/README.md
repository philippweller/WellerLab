# wellerlab — WellerLab Orange3 Suitepack

Alle Werkzeuge des Weller-Labors in **einem** Orange3-Add-on und **einer**
Kategorie: **Weller Lab**.

| Familie | Widgets | Inhalt |
|---|---|---|
| `wellerlab.metabo` | Metabo Feature Table, Preprocess, Feature Filter, Univariate Stats, Heatmap, Volcano | MetaboAnalyst-artige Statistik für GC-MS/GC-IMS-Feature-Tables (Compound Discoverer). Qt-freier Kern `metabo_core`. |
| `wellerlab.plsda` | PLS-DA, OPLS-DA | Multivariate Klassifikation; OPLS-DA mit S-Plot (p1/p(corr)), Schwellen, Farbcodierung, Klick/Shift-Klick-Selektion, VIP + orthoVIP, R2X/R2Y/Q2 (7-fach-CV) und Permutationstest. Qt-freier Kern `opls_core`. |
| `wellerlab.pca` | PCA Pro | Chemometrische PCA: Scaling (none/center/Pareto/autoscale), Komponentenwahl (Kaiser, Varianzanteil, feste Zahl), Hotelling-T²- und Q-Residuen-Diagnostik. |
| `wellerlab.nmr` | NMR Baseline Correction, Binning (Bucketing), Region Exclusion, Filter (Savitzky-Golay), Normalization, Reference & Alignment | Vorverarbeitung von NMR-Spektren. |

## Installation

```bash
# aus dem Monorepo (empfohlen): findet Oranges eigenes Python
python orange-install.py wellerlab

# oder direkt
/Applications/Orange.app/Contents/MacOS/python -m pip install wellerlab
```

Beim ersten Start danach erscheint die Kategorie **Weller Lab** mit allen
Widgets. Wichtig: frühere Einzelpakete (`orangemetabo`, `orangeplsda`,
`orangepca`, `orangenmr`) müssen entfernt sein, sonst erscheinen die Widgets
doppelt.

## Icons

Ein generiertes, konsistentes Set: gleiche Kachelform und Strichstärke,
Familienfarbe und -glyphe (Chromatogramm = Metabo, Multiplett = NMR,
latente Ellipsen = PLS/OPLS, Score-Plot = PCA) plus Kurzlabel.
Erzeugt von `tools/gen_icons.py` im Monorepo.

## Tests (headless, offscreen)

```bash
PY=/Applications/Orange.app/Contents/MacOS/python
$PY _test_opls_core.py      # Numerik: R2Y/Q2/VIP/Permutation
$PY _test_owoplsda.py       # Widget: Schwellen, Farben, Selektion, Ausgänge
$PY _test_suite.py          # Integration: alle 15 Widgets, Icons, Kategorie
```

## Lizenz

MIT · Philipp Weller · philipp.weller@googlemail.com
