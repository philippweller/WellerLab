#!/usr/bin/env python3
"""Orange3 Add-on Installer - cross-platform (macOS / Windows / Linux).

Finds Orange's OWN embedded Python (not /usr/bin/python3), then installs an
Orange3 add-on from the WellerLab monorepo INTO that Python's site-packages,
avoiding the classic Windows "silent user-site" trap.

Installs sub-packages from the WellerLab monorepo via pip's `#subdirectory=`
specifier, so one repo holds all tools and each stays independently installable.

Usage
-----
    python orange-install.py                 # install PLS-DA (default)
    python orange-install.py nmr             # install NMR add-on
    python orange-install.py <name>          # any addon listed in ADDONS
    python orange-install.py all             # install the ENTIRE WellerLab suite
    python orange-install.py --all           # same as 'all'
    python orange-install.py --python PATH   # force a specific python
    python orange-install.py --show          # just locate Orange's python, no install
    python orange-install.py --check plsda   # verify an existing install
    python orange-install.py --check all     # verify every tool in the suite

Runs with ANY python (stdlib only). Install details are printed step by step.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys

# Monorepo source
MONOREPO = "philippweller/WellerLab"
BRANCH = "main"

# name -> (subdirectory, import package, widget category line for final hint)
ADDONS = {
    "plsda": ("orange-plsda-addon", "orangeplsda",
              "PLS-DA   -> PLS-DA / OPLS-DA"),
    "pls-da": ("orange-plsda-addon", "orangeplsda",
               "PLS-DA   -> PLS-DA / OPLS-DA"),
    "nmr": ("orange-nmr-addon", "orangenmr",
            "NMR      -> NMR Preprocessing"),
    "orange-nmr": ("orange-nmr-addon", "orangenmr",
                   "NMR      -> NMR Preprocessing"),
    "pca": ("orange-pca-addon", "orangepca",
            "PCA Weller -> PCA Weller (chemometrics PCA + T2/Q)"),
    "pca-well": ("orange-pca-addon", "orangepca",
                 "PCA Weller -> PCA Weller (chemometrics PCA + T2/Q)"),
}


def candidate_orange_pythons():
    """Return ordered list of (python_exe, description) for this OS."""
    system = platform.system().lower()
    cands = []

    if system == "darwin":
        base = "/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions"
        if os.path.isdir(base):
            version_dirs = ["Current"] + sorted(
                (d for d in os.listdir(base)
                 if d.startswith("3") and os.path.isdir(os.path.join(base, d))),
                reverse=True)
            seen = set()
            for vd in version_dirs:
                b = os.path.join(base, vd, "bin")
                for name in ("python3.13", "python3.12", "python3.12-intel64",
                             "python3.11", "python3.10", "python3"):
                    p = os.path.join(b, name)
                    if os.path.isfile(p) and os.access(p, os.X_OK) and p not in seen:
                        seen.add(p)
                        cands.append((p, f"macOS Orange.app ({vd})"))
    elif system == "windows":
        bases = [os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Orange"),
                 r"C:\Program Files\Orange",
                 r"C:\Program Files (x86)\Orange",
                 os.path.expanduser(r"~\AppData\Local\Programs\Orange")]
        for base in bases:
            p = os.path.join(base, "python.exe")
            if os.path.isfile(p):
                cands.append((p, f"Windows Orange ({base})"))
        # last resort: any 'python' already on the PATH
        exe = shutil.which("python")
        if exe:
            cands.append((exe, "python found on PATH"))
    else:  # linux / conda
        exe = shutil.which("python")
        if exe:
            conda = os.environ.get("CONDA_PREFIX")
            desc = f"conda env ({os.path.basename(conda)})" if conda else "python on PATH"
            cands.append((exe, desc))
    return cands


def find_orange_python(force=None):
    """Return (python_exe, description) or raise SystemExit on failure."""
    if force:
        if os.path.isfile(force):
            return force, f"forced ({force})"
        raise SystemExit(f"error: --python path not found: {force}")

    # validate each candidate really runs and identifies itself
    good = []
    for exe, desc in candidate_orange_pythons():
        try:
            pr = subprocess.run([exe, "-c", "import sys; print(sys.executable)"],
                                capture_output=True, text=True, timeout=15)
            if pr.returncode == 0 and pr.stdout.strip():
                good.append((exe, desc))
        except Exception:
            pass
    if good:
        return good[0]
    raise SystemExit(
        "\nCould not locate an Orange.app Python automatically.\n"
        "Please run with:  --python /full/path/to/orange/python\n"
        "  macOS example : --python /Applications/Orange.app/Contents/Frameworks/\n"
        "                   Python.framework/Versions/Current/bin/python3.12\n"
        "  Windows example: --python \"C:\\Program Files\\Orange\\python.exe\"\n")


def is_user_site(path):
    """Heuristic: is the given install path under the per-user site-packages?"""
    low = path.lower()
    return ("appdata\\roaming\\python" in low
            or "/.local/lib/python" in low
            or "library/python/" in low)


def show_location(exe, pkg):
    """Print where `pkg` is installed for `exe`. Return True if OK (not user-site)."""
    code = ("from importlib.metadata import distribution;"
            f"end=distribution({pkg!r}).locate_file('');print(end)")
    try:
        r = subprocess.run([exe, "-c", code], capture_output=True, text=True, timeout=30)
        loc = r.stdout.strip() or r.stderr.strip()
        print(f"\n[check] {pkg} installed at:\n    {loc}")
        if is_user_site(loc):
            print("  !! user-site install detected - the Orange GUI may not see it.\n"
                  "  Reinstall as administrator (Windows) so pip can write to Program Files,\n"
                  "  or force the system site with --no-user.")
            return False
        return True
    except Exception as e:
        print(f"\n[check] could not inspect {pkg}: {e}")
        return False


def suite_items():
    """Ordered list of unique tools (subdir, pkg, category), deduped by subdir.

    ADDONS maps several aliases (plsda/pls-da, ...) to the same subdir; this
    collapses them so 'all' installs each tool exactly once, in ADDONS order.
    """
    seen = set()
    items = []
    for key in ADDONS:
        subdir, pkg, category = ADDONS[key]
        if subdir not in seen:
            seen.add(subdir)
            items.append((subdir, pkg, category))
    return items


def install_one(exe, subdir, pkg, category, upgrade_no_deps=True):
    """Install a single tool (pip '#subdirectory=' from the monorepo).

    Deliberately does NOT use a bare `--force-reinstall`: on Orange's bundled
    universal2/arm64 Python, forcing a full reinstall makes pip re-resolve ALL
    dependencies (scipy, scikit-learn, pandas, matplotlib ...) and can pull
    x86_64 wheels, breaking Orange (see 2026-10 incident). We instead install
    normally, and only upgrade the add-on package itself with --no-deps so the
    bundled dependency versions are left untouched.
    """
    spec = f"git+https://github.com/{MONOREPO}.git@{BRANCH}#subdirectory={subdir}"
    cmd = [exe, "-m", "pip", "install", "--no-user"]
    if upgrade_no_deps:
        cmd += ["--upgrade", "--no-deps"]   # refresh the add-on, keep deps intact
    cmd.append(spec)
    print(f"\n[{pkg}] Installing from : {spec}")
    print("    (--no-user prevents the silent per-user-site fallback; on Windows run this\n"
          "     terminal with ADMIN rights so pip can write to Program Files)")
    print("    (uses --upgrade --no-deps: updates only the WellerLab package and leaves\n"
          "     Orange's bundled dependencies untouched, so it cannot break arm64 Python)")
    rc = subprocess.call(cmd)
    if rc != 0:
        sys.exit(f"[{pkg}] pip install failed (exit {rc}). See output above. "
                 "If it is a permissions error, re-run as administrator.")

    try:
        ver_code = ("from importlib.metadata import version;"
                    f"print('installed', {pkg!r}, version({pkg!r}))")
        vr = subprocess.run([exe, "-c", ver_code], capture_output=True, text=True, timeout=30)
        if vr.returncode == 0 and vr.stdout.strip():
            print("\n" + vr.stdout.strip())
    except Exception:
        pass
    show_location(exe, pkg)
    print(f"\n    [DONE {pkg}] Fully quit Orange (Cmd/Ctrl+Q) and restart - widget under:")
    print(f"    {category}")


def main():
    ap = argparse.ArgumentParser(description="Install Orange3 add-ons from the WellerLab monorepo")
    ap.add_argument("addon", nargs="?", default="plsda",
                    help="addon key, or 'all' to install the whole suite (default: plsda)")
    ap.add_argument("--all", dest="install_all", action="store_true",
                    help="install the entire WellerLab suite (same as 'all')")
    ap.add_argument("--python", default=None, help="explicit Orange python path")
    ap.add_argument("--show", action="store_true", help="only locate Orange python, no install")
    ap.add_argument("--check", action="store_true", help="verify install(s) and exit")
    args = ap.parse_args()

    addon = (args.addon or "plsda").lower()
    install_all = args.install_all or addon == "all"

    print(f"Platform      : {platform.system()} {platform.machine()}")
    exe, desc = find_orange_python(args.python)
    print(f"Using Orange Python:\n    {exe}   [{desc}]")

    if args.show:
        print("\nDone (--show). Pass this path to --python if auto-detect fails.")
        return

    if install_all:
        items = suite_items()
        print(f"\nSuite install: {len(items)} tool(s)\n" +
              "\n".join(f"  - {pkg}  ({subdir})" for subdir, pkg, _ in items))
        if args.check:
            results = [show_location(exe, pkg) for _, pkg, _ in items]
            sys.exit(0 if all(results) else 1)
        for subdir, pkg, category in items:
            install_one(exe, subdir, pkg, category)
        print("\nSUITE INSTALL COMPLETE. Fully quit Orange (Cmd/Ctrl+Q) and restart "
              "- all WellerLab widgets will be available under their categories.")
        return

    if addon not in ADDONS:
        sys.exit(f"unknown addon '{addon}'. Known: {', '.join(ADDONS)} or 'all'.")
    subdir, pkg, category = ADDONS[addon]

    if args.check:
        sys.exit(0 if show_location(exe, pkg) else 1)
    install_one(exe, subdir, pkg, category)


if __name__ == "__main__":
    main()