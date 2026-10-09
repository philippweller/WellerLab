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

Kanonischer Befehl — findet Oranges Python selbst und läuft mit *jedem* Python:

```bash
python3 run_tests.py                     # alle Suiten
python3 run_tests.py --python /pfad/zum/python
```

Die drei Suiten einzeln:

```bash
PY=/Applications/Orange.app/Contents/MacOS/python
$PY _test_opls_core.py      # Numerik: R2Y/Q2/VIP/Permutation
$PY _test_owoplsda.py       # Widget: Schwellen, Farben, Selektion, Ausgänge
$PY _test_suite.py          # Integration: alle 15 Widgets, Icons, Kategorie
```

> **macOS/Apple-Silicon-Falle:** Wird Oranges universeller Interpreter von einem
> x86_64-Python (Rosetta, z. B. einer Intel-conda-Installation) gestartet, läuft er
> selbst als x86_64 — dort scheitert der Import von Oranges arm64-only
> numpy-Extension („you should not try to import numpy from its source
> directory“). `run_tests.py` umgeht das automatisch mit `arch -arm64`; bei
> direkten Aufrufen nativ starten oder ebenfalls `arch -arm64` voranstellen.

## Lizenz

MIT · Philipp Weller · philipp.weller@googlemail.com
