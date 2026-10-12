# wellerlab — WellerLab Orange3 Suitepack

Alle Werkzeuge des Weller-Labors in **einem** Orange3-Add-on und **einer**
Kategorie: **Weller Lab**.

| Familie | Widgets | Inhalt |
|---|---|---|
| `wellerlab.metabo` | Metabo Feature Table, Preprocess, Feature Filter, Univariate Stats, Heatmap, Volcano | MetaboAnalyst-artige Statistik für GC-MS/GC-IMS-Feature-Tables (Compound Discoverer). Qt-freier Kern `metabo_core`. |
| `wellerlab.plsda` | PLS-DA, OPLS-DA | Multivariate Klassifikation; OPLS-DA mit S-Plot (p1/p(corr)), Schwellen, Farbcodierung, Klick/Shift-Klick-Selektion, VIP + orthoVIP, R2X/R2Y/Q2 (7-fach-CV) und Permutationstest. Qt-freier Kern `opls_core`. |
| `wellerlab.pca` | PCA Pro | Chemometrische PCA: Scaling (none/center/Pareto/autoscale), Komponentenwahl (Kaiser, Varianzanteil, feste Zahl), Hotelling-T²- und Q-Residuen-Diagnostik. |
| `wellerlab.nmr` | NMR Baseline Correction, Binning (Bucketing), Region Exclusion, Filter (Savitzky-Golay), Normalization, Reference & Alignment, Peak Finding, Calibration, Peak Match (Rnmr1D/NMRProcFlow) | Vorverarbeitung von NMR-Spektren; die letzten drei nutzen den R-Paket-Kern Rnmr1D (NMRProcFlow) per Rscript-Subprocess. |

## Installation

```bash
# aus dem Monorepo (empfohlen): findet Oranges eigenes Python
python orange-install.py wellerlab

# oder direkt - ohne Versionsangabe, damit die neueste Version kommt
/Applications/Orange.app/Contents/MacOS/python -m pip install --no-user --upgrade --no-deps wellerlab
```

`--no-deps` ist Absicht: Orange bringt numpy/scipy/matplotlib/scikit-learn/pandas
und sich selbst schon mit. Löst pip die Abhängigkeiten dagegen neu auf, kann es auf
Apple Silicon die nativen arm64-Pakete gegen x86_64-Wheels tauschen - Orange startet
danach nicht mehr. **Nie** `--force-reinstall` verwenden.

Beim ersten Start danach erscheint die Kategorie **Weller Lab** mit allen
Widgets.

### Wenn pip die Version nicht findet

`ERROR: No matching distribution found for wellerlab==<version>` direkt nach einem
Release ist fast immer der **PyPI-Index-Lag**: die JSON-API kennt eine Version
Minuten früher als der Simple-Index, den pip abfragt. Dann:

```bash
# ohne Pin installieren (holt die neueste sichtbare Version)
/Applications/Orange.app/Contents/MacOS/python -m pip install --no-user --upgrade --no-deps wellerlab
# hartnäckiger Fall: pip-Cache umgehen und direkt PyPI abfragen
/Applications/Orange.app/Contents/MacOS/python -m pip install --no-cache-dir \
    --index-url https://pypi.org/simple/ --no-user --upgrade --no-deps wellerlab
# welchen Index benutzt pip überhaupt? (Spiegel/Proxy an der Uni!)
/Applications/Orange.app/Contents/MacOS/python -m pip install -v wellerlab 2>&1 | grep -i "Looking in indexes"
```

Alternativ über die Oberfläche: *Options → Add-ons → Add more…* → `wellerlab`
(der Dialog installiert die neueste Version von PyPI). Wichtig: frühere Einzelpakete (`orangemetabo`, `orangeplsda`,
`orangepca`, `orangenmr`) müssen entfernt sein, sonst erscheinen die Widgets
doppelt.

## Icons

Ein generiertes, konsistentes Set: gleiche Kachelform und Strichstärke,
Familienfarbe und -glyphe (Chromatogramm = Metabo, Multiplett = NMR,
latente Ellipsen = PLS/OPLS, Score-Plot = PCA) plus Kurzlabel.
Erzeugt von `tools/gen_icons.py` im Monorepo (inkl. Kategorie-Icon
`widgets/icons/WellerLab.svg`).

### Warum ein `widget_discovery`-Hook?

Orange scannt bei einem Entry-Point-**Paket** nur die Module, die *direkt* darin
liegen. Unsere Widgets stecken in vier Familien-Unterpaketen, ein reiner
Paket-Scan findet also nichts — die Kategorie bliebe leer. Deshalb definiert
`wellerlab/widgets/__init__.py` denselben Hook, den auch `Orange.widgets` nutzt:
Er schiebt die vier Familienpakete explizit in die eine Kategorie „Weller Lab"
(inklusive Farbe und Icon). `_test_suite.py` prüft das über Oranges **echte**
Discovery (`orangewidget.workflow.discovery`), nicht über die Legacy-Variante.

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
$PY _test_suite.py          # Integration: alle 18 Widgets, Icons, Kategorie
```

> **macOS/Apple-Silicon-Falle:** Wird Oranges universeller Interpreter von einem
> x86_64-Python (Rosetta, z. B. einer Intel-conda-Installation) gestartet, läuft er
> selbst als x86_64 — dort scheitert der Import von Oranges arm64-only
> numpy-Extension („you should not try to import numpy from its source
> directory“). `run_tests.py` umgeht das automatisch mit `arch -arm64`; bei
> direkten Aufrufen nativ starten oder ebenfalls `arch -arm64` voranstellen.

## Lizenz

MIT · Philipp Weller · philipp.weller@googlemail.com
