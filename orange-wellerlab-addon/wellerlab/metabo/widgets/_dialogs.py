"""Small Qt dialog helpers shared by the Metabo widgets.

Orange's ``Orange.widgets.utils.filedialogs`` API is not stable across
releases: the ``OpenFileDialog`` / ``SaveFileDialog`` classes used by older
widgets no longer exist in current Orange (they were replaced by the
``open_filename_dialog`` / ``open_filename_dialog_save`` functions). To stay
working on every Orange version the widgets call plain ``QFileDialog``
directly through these two helpers — one idiom, no version-specific imports.
"""


def open_feature_table(parent, start_dir=""):
    """Ask for a feature-table CSV/TXT. Returns a path or None (cancelled)."""
    from AnyQt.QtWidgets import QFileDialog
    path, _ = QFileDialog.getOpenFileName(
        parent, "Open feature table", start_dir or "",
        "Feature table (*.csv *.txt *.tsv);;All files (*)")
    return path or None


def save_figure(parent, fig, kind="PNG"):
    """Ask for a path and write figure `fig` as PNG (dpi 300) or SVG.

    `kind` is 'PNG' or 'SVG' (case-insensitive). Returns the path written,
    or None if the user cancelled.
    """
    from AnyQt.QtWidgets import QFileDialog
    kind = kind.upper()
    ext = ".png" if kind == "PNG" else ".svg"
    path, _ = QFileDialog.getSaveFileName(
        parent, f"Save figure ({kind})", "", f"{kind} (*{ext});;All files (*)")
    if not path:
        return None
    if not path.lower().endswith(ext):
        path += ext
    fig.savefig(path, dpi=300 if kind == "PNG" else None, facecolor="white")
    return path
