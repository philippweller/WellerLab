# orange-pca-addon — PCA Weller (Chemometrie-PCA für Orange3)

**Autor:** Philipp Weller (AK Weller) · philipp.weller@googlemail.com

Erweitertes PCA-Widget für **Orange3** mit Fokus auf chemometrische
Anwendungen (NMR, Spektroskopie, Biomarker). Ziel: **mehr Kontrolle über
Preprocessing und Ausreißer als das eingebaute Orange-PCA-Widget.**

## 🎯 Was es zusätzlich zum regulären PCA-Widget kann

| Feature | Details |
|---|---|
| **Preprocessing** | `auto` (Autoscaling), `pareto`, `center`, `none` — wählbar vor dem Fit |
| **Komponenten-Wahl** | Kaiser-Kriterium (automatisch) *oder* erklärte-Varianz-Schwellwert *oder* feste Anzahl |
| **Varianz % an den Achsen** | Score-Plot-Achsen zeigen `PC1 (72.8%)`, `PC2 (23.0%)` usw. |
| **T²/Q-Ausreißer-Diagnostik** | Hotelling-T²- und Q-Restdual-Plot mit statistischen Kontrollgrenzen |
| **Ausreißer entfernen** | Button filtert Samples jenseits der Limits und **refittet** das Modell auf den Inliers |
| **Scores-Plot** | Klassen-Farbcodierung, Punktgröße optional proportional zum Q-Restdual |

## 📐 Statistik

- **Hotelling-T²** pro Sample: `T2_i = Σ_k t_ik² / λ_k`, Kontrollgrenze via
  F-Verteilung (Nomikos & MacGregor):
  `T2_lim = k·(n−1)/(n−k) · F(α, k, n−k)`.
- **Q-Residual** pro Sample: Quadratsumme des Rekonstruktionsfehlers.
  Kontrollgrenze über momentbasierte skalierte χ²-Näherung (g · χ²(df)).
- **Kaiser-Kriterium** (Kaiser 1960): behalte Komponenten, deren Eigenwert
  den Mittelwert der Eigenwerte übersteigt (= bei Autoscaling: Eigenwert > 1).

## 📦 Installation

Teil des **WellerLab**-Monorepos (`github.com/philippweller/WellerLab`). Mit
dem gemeinsamen Installer (Oranges eigenes Python wird automatisch gefunden):

```bash
# Installer holen (einmalig):
curl -fsSL https://raw.githubusercontent.com/philippweller/WellerLab/main/orange-install.py -o orange-install.py
# PCA Weller installieren:
python3 orange-install.py pca
```

Manuell per pip-`subdirectory`-Spezifikation:

```bash
/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3.12 \
  -m pip install "git+https://github.com/philippweller/WellerLab.git@main#subdirectory=orange-pca-addon"
```

Orange beenden (Cmd/Ctrl+Q) und neu starten → Widget unter **PCA Weller** suchen.

## 🧭 Bedienung (im Widget)

1. **Preprocessing–Scaling** wählen (Standard: `auto`).
2. **Komponenten-Methode** wählen:
   - *Kaiser criterion (automatic)* — Anzahl automatisch
   - *Explained variance fraction* — bis kumulative Varianz ≥ Schwellwert
   - *Fixed number* — feste Komponentenzahl
3. Score-Plot prüfen (Varianz % an den Achsen, Klassenfarben, Größe ∝ Q).
4. **Unterer T²-vs-Q-Plot**: Punkte außerhalb der roten Limits sind Ausreißer.
   Mit `Significance (alpha)` die Grenzen justieren (Default 0.05).
5. **Remove outliers & refit**: entfernt die Ausreißer und rechnet das Modell
   auf den verbliebenen Samples neu.

### Ausgänge

- **Transformed Data** — Scores der gewählten Komponenten (PCs), inkl.
  `variance`-Attribut je Spalte
- **Components (loadings)** — Loadings als Tabelle (Zeilen = Komponenten)
- **Scores** — Scores inkl. `T2`- und `Q_residual`-Meta-Spalten
- **Data** — Originaldaten erweitert um `T2`- und `Q_residual`-Spalten
- **Outliers** / **Inliers** — Daten unterteilt nach den aktiven Limits

## 🧪 Schnelltest (Entwickler)

```bash
python -c "
from Orange.data import Table
from orangepca import pca_analysis as pa
t = Table('iris')
r = pa.fit_pca(t.X, scale='auto', n_components='kaiser')
print('Kaiser-Komponenten:', r['n_components'])
print('erkl.Varianz:', [round(float(x),3) for x in r['explained_variance_ratio']])
o = pa.PCAOutliers(t.X, scale='auto', n_components=2)
print('T2-Limit:', round(o.T2_lim,3), ' Q-Limit:', round(o.Q_lim,3))
"
```

## ❓ Fehlerbehebung

- **Widget erscheint nicht** → Oranges eigenes Python benutzt (nicht
  `/usr/bin/python3`); Orange vollständig neu starten.
- **Windows: Widget fehlt in der GUI** → Paket landete evtl. in der
  User-Site (`AppData\Roaming`). Installer nutzt `--no-user`; als
  Administrator ausführen (siehe WellerLab-Haupt-README).

## 📄 Lizenz

MIT © Philipp Weller