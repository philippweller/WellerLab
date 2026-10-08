# orange-plsda-addon

**Autor:** Philipp Weller (AK Weller) · philipp.weller@googlemail.com

PLS-DA & OPLS-DA für **Orange3** — Leistungsstarke Klassifikations-Widgets für
die multivariate Analyse (Chemometrie, Biomarker-Findung).

- **PLS-DA** (Partial Least Squares Discriminant Analysis) — Klassifikation
  mittels `PLSRegression` mit One-hot-kodiertem Ziel
- **OPLS-DA** (Orthogonal PLS-DA, Trygg & Wold 2002) — trennt prädiktive von
  orthogonaler (klassen-unabhängiger) Variation

Beide Widgets erscheinen in Orange unter der Kategorie **PLS-DA**, direkt
neben dem eingebauten PLS-R.

---

## ⚡ Automatischer Installer (empfohlen)

Dieses Paket ist Teil des **WellerLab**-Monorepos
(`github.com/philippweller/WellerLab`). Der gemeinsame Installer
`orange-install.py` (auf Repo-Ebene) findet **Oranges eigenes Python**
automatisch und installiert das Paket korrekt (macOS / Windows / Linux). Kein
manuelles Pfad-Raten mehr:

```bash
# PLS-DA installieren:
python orange-install.py plsda

# NMR-Add-on installieren:
python orange-install.py nmr

# nur zeigen, welches Python erkannt wurde:
python orange-install.py --show

# bestehende Installation prüfen:
python orange-install.py --check plsda
```

Läuft mit **jedem** Python (nur Standardbibliothek). Klappt die
Auto-Erkennung ausnahmsweise nicht:

```bash
python orange-install.py --python /pfad/zum/orange/python
```

> ▶️ **Direkt ausführen ohne Clone** (das Add-on wird trotzdem via GitHub
> installiert):
> ```bash
> curl -fsSL https://raw.githubusercontent.com/philippweller/WellerLab/main/orange-install.py -o orange-install.py && python3 orange-install.py plsda
> ```

Das Tool bedient auch den **Windows-`--no-user`-Fall** automatisch, sodass
das Add-on in Oranges eigene `site-packages` landet statt in die unsichtbare
User-Site.

---

## 📋 Voraussetzungen

| Voraussetzung | Hinweis |
|---|---|
| Orange3 ≥ 3.40 installiert | Unter **Hilfe → Über** die Version prüfen |
| Internet-Zugriff auf GitHub | zum Herunterladen des Repos |

> ⚠️ **Wichtig:** Es muss immer **Oranges eigenes Python** verwendet werden,
> nicht `/usr/bin/python3`! Sonst wird das Add-on in der falschen Python-Umgebung
> installiert und Orange findet es nicht.

---

## 🔍 Oranges eingebettetes Python finden (wichtig!)

Der Pfad zu Oranges Python **hängt von der Orange-Version ab**. Je nachdem
ob Orange mit Python 3.11 oder 3.12 gebaut wurde, heißt das Binary
`python3`, `python3.11` oder `python3.12`.

**Sichere Methode — das echte Python-Binary lokalisieren:**

```bash
ls /Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/
# zeigt z.B.:  3.12   und   Current -> 3.12

# Dann das echte Binary finden:
find /Applications/Orange.app -name "python3*" -type f 2>/dev/null | grep -i bin
```

Typische gültige Pfade (je nach Version):

| Orange mit | Python-Binary |
|---|---|
| Python 3.11 | `.../Versions/Current/bin/python3` |
| Python 3.11 (nur versioniert) | `.../Versions/Current/bin/python3.11` |
| Python 3.12 | `.../Versions/Current/bin/python3.12` |
| Intel-Mac mit 3.12 | `.../Versions/Current/bin/python3.12-intel64` |

> `Current` ist ein Symlink zur installierten Version (`Current -> 3.12`),
> funktioniert also in allen Fällen. Ersetze in den Befehlen unten
> `ORANGEPY` durch **den** gefundenen Pfad.

---

## 🚀 Installation (Schritt für Schritt)

### macOS (Orange.app als `.app` installiert)

**Schritt 1 — Oranges eingebettetes Python prüfen:**

Öffne einen Terminal und führe aus (nutze den Pfad aus dem Abschnitt
[Oranges eingebettetes Python finden](#-oranges-eingebettetes-python-finden-wichtig);
je nach Orange-Version heißt das Binary `python3`, `python3.11` oder `python3.12`):

```bash
/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.12 --version
```

Es sollte eine Python-3.x-Version ausgeben. Notiere dir diesen Pfad — er wird
in den nächsten Schritten gebraucht (im Folgenden abgekürzt als `ORANGEPY`).

**Schritt 2 — Add-on von GitHub installieren:**

```bash
ORANGEPY=/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.12
$ORANGEPY -m pip install git+https://github.com/philippweller/WellerLab.git@main#subdirectory=orange-plsda-addon
```

**Schritt 3 — Installation prüfen (optional, empfohlen):**

```bash
$ORANGEPY -c "from orangeplsda import PLSDALearner; print('OK')"
```

Wenn `OK` erscheint, ist das Paket korrekt installiert.

**Schritt 4 — In Orange öffnen:**

Orange starten. Die Widgets **PLS-DA** und **OPLS-DA** erscheinen in der
Widget-Leiste unter **PLS-DA**. Du musst Orange nicht neu starten — es reicht,
das Canvas-Fenster erneut zu öffnen.

---

### Windows (Orange über den "Orange Command Prompt")

**Schritt 1 — Orange Command Prompt öffnen:**

Startmenü → *Orange* → *Orange Command Prompt* (bzw. *Qt Console*).

**Schritt 2 — Installieren:**

```cmd
python -m pip install git+https://github.com/philippweller/WellerLab.git@main#subdirectory=orange-plsda-addon
```

**Schritt 3 — Prüfen:**

```cmd
python -c "from orangeplsda import PLSDALearner; print('OK')"
```

**Schritt 4 — Orange öffnen** und unter **PLS-DA** nachschauen.

---

### Linux / Conda / Venv

**Schritt 1 — Umgebung aktivieren:**

```bash
conda activate orange    # oder: source .venv/bin/activate
```

**Schritt 2 — Installieren:**

```bash
pip install git+https://github.com/philippweller/WellerLab.git@main#subdirectory=orange-plsda-addon
```

**Schritt 3 — Prüfen:**

```bash
python -c "from orangeplsda import PLSDALearner; print('OK')"
```

**Schritt 4 — Orange starten** und das Widget suchen.

---

## 🔄 Updates einspielen (bei neuen Versionen)

Auf **jedem** Rechner, auf dem das Add-on installiert ist:

**Schritt 1 — aktuelle Version installieren (Überschreibt die alte):**

```bash
# macOS
$ORANGEPY -m pip install --upgrade --force-reinstall git+https://github.com/philippweller/WellerLab.git@main#subdirectory=orange-plsda-addon
```

```bash
# Windows / Linux / Conda
python -m pip install --upgrade --force-reinstall git+https://github.com/philippweller/WellerLab.git@main#subdirectory=orange-plsda-addon
```

**Schritt 2 — Orange neu starten**, damit die neuen Widget-Versionen geladen werden.

> Hinweis: `--force-reinstall` wird empfohlen, da Orange die Widgets beim
> Canvas-Öffnen zwischenspeichert.

---

## 🗑️ Deinstallation

```bash
# macOS
$ORANGEPY -m pip uninstall orangeplsda -y
```

```bash
# Windows / Linux / Conda
python -m pip uninstall orangeplsda -y
```

Danach Orange neu starten — die Widgets sind verschwunden.

---

## 🧪 Kurzer Funktionstest (Entwickler)

Mit Oranges Python auf einem der mitgelieferten Datensätze:

```bash
python -c "
from Orange.data import Table
from Orange.base import Model
from orangeplsda import PLSDALearner
from orangeplsda.oplsda_learner import OPLSDALearner
for L, kw in [(PLSDALearner, dict(n_components=2)),
              (OPLSDALearner, dict(n_components=1, n_ortho=1))]:
    t = Table('iris'); m = L(**kw)(t)
    p, pr = m(t, ret=Model.ValueProbs)
    print(L.__name__, round(float((p == t.Y.flatten()).mean()), 3), pr.shape)
"
```

Erwartete Ausgabe (beispielhaft, kann leicht abweichen):

```
PLSDALearner 0.813 (150, 3)
OPLSDALearner 0.8 (150, 3)
```

---

## 🛠️ Fehlerbehebung

| Problem | Lösung |
|---|---|
| "`python3` ist nicht vorhanden" / Datei nicht gefunden | Das Binary heißt je nach Orange-Version `python3`, `python3.11` oder `python3.12` (z.B. Orange mit Python 3.12). Mit `find /Applications/Orange.app -name "python3*" -type f` den echten Namen ermitteln. |
| `from orangeplsda import ...` schlägt fehl | Du hast `/usr/bin/python3` statt Oranges Python benutzt. Siehe Schritt 1 oben. |
| Widget erscheint nicht in Orange | Gelöschte `*.egg-info`/`__pycache__` prüfen; Orange vollständig neu starten; `pip show orangeplsda` ausführen. |
| `Host key verification failed` beim pip install | Läuft nur bei einem gepushten SSH-Workflow, nicht bei `git+https://`. Nutze die https-URL. |
| alte Version bleibt | `pip install --force-reinstall` verwenden (siehe Updates). |

---

## 📦 Entwicklung / Repo lokal ausprobieren

```bash
git clone git@github.com:philippweller/orange-plsda-addon.git
cd orange-plsda-addon
# Editable-Install mit Oranges Python:
$ORANGEPY -m pip install -e .
```

---

## 📄 Lizenz

MIT © Philipp Weller