# WellerLab

Monorepo für **allen selbstgebauten Tooling rund um Orange3**, das die Gruppe baut.
Die Werkzeuge werden als **ein Paket** (`wellerlab`) ausgeliefert und erscheinen in Orange in
der gemeinsamen Kategorie **Weller Lab**. Ein gemeinsamer, plattformübergreifender Installer
installiert das Paket direkt aus diesem Repo.

> Hinweis: Dieses Repo ersetzt die früher getrennten Repos `orange-plsda-addon` und
> `orange-nmr-addon` (archiviert). Die Install-URLs haben sich geändert — siehe unten.

## 📦 Enthaltene Tools

| Unterordner | Paket | Orange-Kategorie | Widgets |
|---|---|---|---|
| `orange-wellerlab-addon/` | `wellerlab` | **Weller Lab** | alle 15 (siehe unten) |

Das Paket `wellerlab` enthält vier Familien als Unterpakete:

| Unterpaket | Widgets |
|---|---|
| `wellerlab.metabo` | Metabo Feature Table, Preprocess, Feature Filter, Univariate Stats, Heatmap, Volcano |
| `wellerlab.plsda` | PLS-DA, OPLS-DA (S-Plot mit Schwellen, Farbcodierung, Selektion; VIP/orthoVIP, R2X/R2Y/Q2, Permutation) |
| `wellerlab.pca` | PCA Pro (Scaling, Varianz % an Achsen, Hotelling-T2/Q) |
| `wellerlab.nmr` | Baseline, Binning, Region Exclusion, Filter, Normalization, Reference & Alignment |

Icons werden zentral erzeugt: `orange-wellerlab-addon/tools/gen_icons.py`.
Die früheren Einzelpakete (`orangeplsda`, `orangenmr`, `orangepca`, `orangemetabo`) sind darin
aufgegangen; ihre alten Ordner bleiben als Historie im Repo, werden aber nicht mehr installiert.

## ⚡ Automatischer Installer (empfohlen)

`orange-install.py` findet **Oranges eigenes Python** automatisch und installiert korrekt
(macOS / Windows / Linux), inkl. Vermeidung der Windows-User-Site-Falle:

```bash
# Zuerst den Installer holen (einmalig, bleibt lokal):
curl -fsSL https://raw.githubusercontent.com/philippweller/WellerLab/main/orange-install.py -o orange-install.py

# Dann installieren (ein Paket, eine Kategorie):
python3 orange-install.py            # = wellerlab (alle 15 Widgets)
python3 orange-install.py wellerlab  # dasselbe, explizit
python3 orange-install.py all        # die gesamte Suite

# Die früheren Einzelnamen (metabo, plsda, pca, pca-pro, nmr) funktionieren als
# Aliase weiter und installieren dasselbe Paket.

# sonst:
python3 orange-install.py --show     # findet Oranges Python, installiert nicht
python3 orange-install.py --check wellerlab   # prüft bestehende Installation
python3 orange-install.py --python /pfad/zum/orange/python   # Erkennung überschreiben
```

Klappt die Auto-Erkennung auf einem Rechner nicht, liefere `--python <pfad>` an.

## 📦 Installation über Oranges Add-ons-Dialog (PyPI)

Oranges eigener Add-ons-Dialog (`Options → Add-ons`) installiert Pakete von
**PyPI**. Sind die Pakete dort veröffentlicht, kann die Gruppe sie direkt im
Dialog suchen und installieren:

1. **Options → Add-ons… → "Add add-on by name"**
2. Paketnamen eintippen: `orangeplsda`, `orangenmr`, `orangepca` oder `orangemetabo`
3. **Add** → installieren → Orange neu starten

| Paketname | Inhalt |
|---|---|
| `orangeplsda` | PLS-DA + OPLS-DA |
| `orangenmr` | NMR Preprocessing |
| `orangepca` | PCA Weller |
| `orangemetabo` | Metabo Weller |

> **Veröffentlichen:** die Pakete werden mit `./publish-pypi.sh` (benötigt
> einen PyPI-API-Token) auf PyPI hochgeladen — siehe `pypi-publish.md`.
> Solange sie nicht auf PyPI sind, findet der Dialog sie nicht; dann den
> `orange-install.py`-Weg oben verwenden.

## 🔧 Manuelle Installation (je Paket)

Jedes Paket installiert per pip-`subdirectory`-Spezifikation, ganz auf eigenem
`<paket>`-Namespace:

```bash
# macOS (Orange.app — Oranges eigenes Python verwenden):
/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.12 \
  -m pip install "git+https://github.com/philippweller/WellerLab.git@main#subdirectory=orange-plsda-addon"

# Windows (als Administrator, damit pip nach Program Files schreiben kann):
python -m pip install --no-user "git+https://github.com/philippweller/WellerLab.git@main#subdirectory=orange-plsda-addon"
```

Ersetze `#subdirectory=orange-plsda-addon` durch `#subdirectory=orange-nmr-addon` für NMR.

## ❓ Fehlerbehebung / Diagnose

Ausführlich in jeder Tool-README im `Fehlerbehebung`-Abschnitt und in der Skill
`orange3-addon-installer`. Kernpunkte:

- **Immer Oranges eigenes Python, nie `/usr/bin/python3`.**
- Version abhängig: Binary heißt `python3`, `python3.11`, `python3.12` oder
  (Intel-Mac) `python3.12-intel64`. Finder:
  ```bash
  find /Applications/Orange.app -name "python3*" -type f 2>/dev/null | grep -i bin
  ```
- **Windows-User-Site**: Landet die Location unter `AppData\Roaming\Python`, siehe Orange
  sie nicht → mit `--no-user` und als Admin neu installieren.

## Development

```bash
git clone git@github.com:philippweller/WellerLab.git
cd WellerLab
# Editable-Install eines Teilpakets mit Oranges Python:
ORANGEPY=/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.12
$ORANGEPY -m pip install -e ./orange-plsda-addon
```

## Lizenz

MIT © Philipp Weller