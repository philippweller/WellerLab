# Veröffentlichen der WellerLab-Addons auf PyPI

So werden die Addons installierbar **im Orange-Add-ons-Dialog** (nativ, ohne
Kommandozeile auf den Zielrechnern). Der Dialog installiert Pakete von PyPI
über *Options → Add-ons → "Add add-on by name"*.

## Warum PyPI

Oranges Add-ons-Dialog (`orange-canvas-core` `addons.py`) sucht Pakete
ausschließlich auf **PyPI** (`query_pypi`) und installiert sie per
`pip install <name>`. GitHub-Repos sind dort nicht auffindbar. Einen Git-URL
kann der Dialog nicht installieren. → **Die vier Pakete müssen auf PyPI
veröffentlicht werden.**

| Paketname | Inhalt | Orange-Kategorie |
|---|---|---|
| `orangeplsda` | PLS-DA + OPLS-DA | PLS-DA |
| `orangenmr` | NMR-Preprocessing | NMR Preprocessing |
| `orangepca` | PCA Weller | WellerLab PCA |
| `orangemetabo` | MetaboAnalyst-Stil Feature-Table-Statistik | Metabo Weller |

## Voraussetzungen

1. Die `publish-pypi.sh` wird mit **Oranges eigenem Python** ausgeführt.
2. Du brauchst einen **PyPI-API-Token**:
   - Erstellen: pypi.org → Account settings → API tokens → "Add token"
     (Scope: jeden der vier Projekte einzeln, oder ein Account-Scoped Token).

## Veröffentlichen (einmalig)

```bash
cd /Users/philippweller/WellerLab
export ORANGEPY=/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3

export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-...dein-api-token

# Alles bauen (wheel + sdist) und auf PyPI hochladen:
./publish-pypi.sh

# Nur zur Kontrolle zuerst auf TestPyPI:
./publish-pypi.sh --test
```

Das Skript legt die Artefakte in `dist-pypi/` und führt
`build` (wheel + sdist) und `twine upload` aus.

> Env-Vars mit Token sind nur transient in der Shell — nie ins Git.

## Installieren per Add-ons-Dialog (auf jedem Gruppenrechner)

Nach der Veröffentlichung, in einer laufenden Orange:

1. **Options → Add-ons…**
2. **"Add add-on by name"** klicken
3. Paketname tippen: `orangepca` (bzw. `orangeplsda`, `orangenmr`, `orangemetabo`)
4. **Add** → Installieren
5. Orange neu starten (Cmd/Ctrl+Q) → Widget unter seiner Kategorie

> Die bereits installierten Addons erscheinen im Dialog auch ohne PyPI als
> "installed"; über PyPI werden sie zusätzlich **updatebar** und auf frischen
> Rechnern per Namenssuche installierbar.

## Versionskontrolle

- Vor jedem erneuten Upload die `version=` in `setup.py` des betroffenen
  Pakets **erhöhen** (z.B. `0.1.1 → 0.1.2`), sonst akzeptiert PyPI den Upload
  nicht (gleiche Version wird abgelehnt).
- Der `orange-install.py` (git-basiert) bleibt für schnelle Dev-Installationen
  bestehen; PyPI ist der Weg für den Orange-Bord-Dialog.