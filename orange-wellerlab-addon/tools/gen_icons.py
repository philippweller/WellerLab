#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Generate one consistent icon set for all WellerLab widgets.

Design system (identical for every icon, only colour/glyph/label change):
  48x48 canvas, rounded tile (r=8) in the FAMILY colour, white glyph
  (stroke 2, no fill), small white label at the bottom.
Family glyphs: chromatogram peaks (metabo), multiplet spectrum (NMR),
latent-space ellipses (PLS-DA/OPLS-DA), score plot with axes (PCA).

Keeping the existing file names means no widget code has to change.
"""
import os

ROOT = "/Users/philippweller/WellerLab/orange-wellerlab-addon/wellerlab"

FAMILY = {                       # family -> (tile colour, glyph)
    "metabo": ("#1F4E79", "peaks"),
    "plsda": ("#6A1B9A", "ellipses"),
    "pca": ("#00838F", "scores"),
    "nmr": ("#2E7D32", "multiplet"),
}

GLYPH = {
    # chromatogram: baseline with three peaks
    "peaks": '<polyline points="7,32 13,32 15,20 18,32 24,32 26,14 29,32 34,32 36,24 39,32 41,32" '
             'fill="none" stroke="#fff" stroke-width="2" stroke-linejoin="round"/>'
             '<line x1="7" y1="36" x2="41" y2="36" stroke="#fff" stroke-width="1.5" opacity="0.7"/>',
    # NMR multiplet with one tall reference singlet
    "multiplet": '<polyline points="7,33 11,33 12,26 13,33 17,33 18,28 19,33 22,33 23,10 24,33 25,33 '
                 '27,27 28,33 32,33 33,29 34,33 38,33 39,31 41,33" fill="none" stroke="#fff" '
                 'stroke-width="2" stroke-linejoin="round"/>',
    # PLS-DA: two overlapping clusters with a separating line
    "ellipses": '<ellipse cx="18" cy="22" rx="8" ry="5.5" transform="rotate(-20 18 22)" fill="none" '
                'stroke="#fff" stroke-width="2"/>'
                '<ellipse cx="32" cy="30" rx="8" ry="5.5" transform="rotate(-20 32 30)" fill="none" '
                'stroke="#fff" stroke-width="2"/>'
                '<line x1="11" y1="36" x2="39" y2="15" stroke="#fff" stroke-width="1.5" opacity="0.8"/>',
    # PCA: axes plus a score cloud
    "scores": '<polyline points="10,10 10,38 40,38" fill="none" stroke="#fff" stroke-width="2" '
              'stroke-linejoin="round"/>'
              '<circle cx="17" cy="30" r="2.2" fill="#fff"/><circle cx="22" cy="25" r="2.2" fill="#fff"/>'
              '<circle cx="27" cy="27" r="2.2" fill="#fff"/><circle cx="33" cy="20" r="2.2" fill="#fff"/>'
              '<circle cx="21" cy="34" r="2.2" fill="#fff"/><circle cx="30" cy="33" r="2.2" fill="#fff"/>',
}

# family -> [(subdir-relative icon name without .svg, label)]
ICONS = {
    "metabo": [("FeatureImport", "IMP"), ("Preprocess", "PRE"), ("FeatureFilter", "FIL"),
               ("UnivariateStats", "UNI"), ("Heatmap", "HM"), ("Volcano", "VOL")],
    "plsda": [("PLSDA", "PLS"), ("OPLSDA", "OPLS")],
    "pca": [("PCAPro", "PRO")],
    "nmr": [("NMRBaseline", "BASE"), ("NMRBinning", "BIN"), ("NMRExclude", "EXCL"),
            ("NMRFilter", "FILT"), ("NMRNormalize", "NORM"), ("NMRReference", "REF")],
}

# category icon: the four family colours as a 2x2 tile
CATEGORY_ICON = """<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
  <rect width="48" height="48" rx="8" fill="#1F4E79"/>
  <rect x="9" y="9" width="13" height="13" rx="3" fill="#1F4E79" stroke="#fff" stroke-width="1.5"/>
  <rect x="26" y="9" width="13" height="13" rx="3" fill="#6A1B9A" stroke="#fff" stroke-width="1.5"/>
  <rect x="9" y="26" width="13" height="13" rx="3" fill="#00838F" stroke="#fff" stroke-width="1.5"/>
  <rect x="26" y="26" width="13" height="13" rx="3" fill="#2E7D32" stroke="#fff" stroke-width="1.5"/>
</svg>
"""

TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">
  <rect width="48" height="48" rx="8" fill="{colour}"/>
  <g>{glyph}</g>
  <text x="24" y="45" font-family="Helvetica,Arial,sans-serif" font-size="7" fill="#fff"
        fill-opacity="0.85" text-anchor="middle">{label}</text>
</svg>
"""

written = []
for family, items in ICONS.items():
    colour, glyph_key = FAMILY[family]
    out_dir = os.path.join(ROOT, family, "widgets", "icons")
    os.makedirs(out_dir, exist_ok=True)
    for name, label in items:
        path = os.path.join(out_dir, f"{name}.svg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(TEMPLATE.format(colour=colour, glyph=GLYPH[glyph_key], label=label))
        written.append(f"{family}/{name}.svg")

# category icon for the umbrella "wellerlab.widgets" package
cat_dir = os.path.join(ROOT, "widgets", "icons")
os.makedirs(cat_dir, exist_ok=True)
with open(os.path.join(cat_dir, "WellerLab.svg"), "w", encoding="utf-8") as fh:
    fh.write(CATEGORY_ICON)
written.append("widgets/WellerLab.svg (Kategorie)")

print(f"{len(written)} Icons erzeugt:")
for w in written:
    print("  ", w)
