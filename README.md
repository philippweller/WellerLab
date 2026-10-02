# WellerLab

Monorepo für **allen selbstgebauten Tooling rund um Orange3**, das die Gruppe baut.
Jedes Tool ist ein eigenständig installierbares Paket in einem eigenen Unterordner mit eigenem
`setup.py`. Ein gemeinsamer, plattformübergreifender Installer installiert jedes Paket direkt
aus diesem Repo.

> Hinweis: Dieses Repo ersetzt die früher getrennten Repos `orange-plsda-addon` und
> `orange-nmr-addon` (archiviert). Die Install-URLs haben sich geändert — siehe unten.

## 📦 Enthaltene Tools

| Unterordner | Paket | Orange-Kategorie | Beschreibung |
|---|---|---|---|
| `orange-plsda-addon/` | `orangeplsda` | **PLS-DA** | PLS-DA + OPLS-DA-Klassifikation (inkl. S-Plot) |
| `orange-nmr-addon/` | `oranjenmr` | **NMR Preprocessing** | NMR-Binning, -Normalisierung, -Baseline, -Filter, Regionen, Alignment |
| `orange-pca-addon/` | `orangepca` | **PCA Well** | Chemometrie-PCA: Scaling, Varianz % an Achsen, Hotelling-T2/Q-Ausreißer-Diagnostik + Filter |

Neue Tools kommen als eigener Unterordner mit eigenem `setup.py` dazu (Muster siehe
`orange-plsda-addon/`). Danach einen Eintrag in `ADDONS` in `orange-install.py` ergänzen.

## ⚡ Automatischer Installer (empfohlen)

`orange-install.py` findet **Oranges eigenes Python** automatisch und installiert korrekt
(macOS / Windows / Linux), inkl. Vermeidung der Windows-User-Site-Falle:

```bash
# Zuerst den Installer holen (einmalig, bleibt lokal):
curl -fsSL https://raw.githubusercontent.com/philippweller/WellerLab/main/orange-install.py -o orange-install.py

# Dann ein Tool installieren:
python3 orange-install.py plsda      # PLS-DA + OPLS-DA
python3 orange-install.py nmr        # NMR Preprocessing
python3 orange-install.py pca        # PCA Well (chemometrics PCA + T2/Q)

# sonst:
python3 orange-install.py --show     # findet Oranges Python, installiert nicht
python3 orange-install.py --check plsda   # prüft bestehende Installation
python3 orange-install.py --python /pfad/zum/orange/python   # Erkennung überschreiben
```

Klappt die Auto-Erkennung auf einem Rechner nicht, liefere `--python <pfad>` an.

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