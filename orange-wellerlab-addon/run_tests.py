#!/usr/bin/env python3
"""Run the WellerLab test suites headlessly (offscreen Qt).

    python3 run_tests.py                      # finds Orange's own Python
    python3 run_tests.py --python /path/to/python

Exit code 0 only if every suite passes. This is the canonical test command for
the add-on; the suites themselves just need *some* Python that can import Orange,
which on macOS means Orange.app's embedded interpreter rather than /usr/bin/python3.
"""
import argparse
import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = ("_test_opls_core.py", "_test_owoplsda.py", "_test_suite.py",
          "_test_heatmap.py", "_test_volcano.py", "_test_selection.py")


def _apple_silicon():
    try:
        return subprocess.run(["sysctl", "-n", "hw.optional.arm64"],
                              capture_output=True, text=True, timeout=10
                              ).stdout.strip() == "1"
    except (OSError, subprocess.SubprocessError):
        return False


def native(cmd):
    """Force native execution of an universal binary on Apple Silicon.

    An x86_64 parent (a Rosetta conda python) makes universal children pick the
    x86_64 slice, where Orange's arm64-only numpy extension fails to load with
    "you should not try to import numpy from its source directory".
    """
    if platform.system() == "Darwin" and _apple_silicon():
        return ["/usr/bin/arch", "-arm64", *cmd]
    return list(cmd)


def imports_orange(exe):
    try:
        return subprocess.run(native([exe, "-c", "import Orange"]),
                              capture_output=True, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_orange_python():
    """Best-effort lookup of an interpreter that can import Orange."""
    if imports_orange(sys.executable):
        return sys.executable
    system = platform.system().lower()
    cands = []
    if system == "darwin":
        base = "/Applications/Orange.app/Contents/Frameworks/Python.framework/Versions"
        if os.path.isdir(base):
            for v in sorted(os.listdir(base), reverse=True):
                cands += [os.path.join(base, v, "bin", "python3"),
                          os.path.join(base, v, "bin", "python")]
        cands += ["/Applications/Orange.app/Contents/MacOS/python"]
    elif system == "windows":
        cands += [r"C:\Program Files\Orange\python.exe",
                  os.path.expandvars(r"%LOCALAPPDATA%\Programs\Orange\python.exe")]
    cands += ["/usr/bin/python3", "python3"]
    return next((c for c in cands if os.path.exists(c) and imports_orange(c)), None)


def main():
    ap = argparse.ArgumentParser(description="Run the WellerLab test suites headlessly")
    ap.add_argument("--python", default=None, help="interpreter to use")
    args = ap.parse_args()

    exe = args.python or find_orange_python()
    if not exe:
        sys.exit("Kein Python mit Orange gefunden - --python <pfad> angeben "
                 "(auf macOS: /Applications/Orange.app/Contents/MacOS/python).")
    print(f"Interpreter: {exe}\n")

    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    failed = []
    for suite in SUITES:
        r = subprocess.run(native([exe, suite]), cwd=HERE, capture_output=True, text=True,
                           env=env, timeout=900)
        tail = next((l for l in reversed(r.stdout.splitlines()) if l.strip()), "")
        print(f"{'PASS' if r.returncode == 0 else 'FAIL'}  {suite:<22} {tail[:70]}")
        if r.returncode != 0:
            failed.append(suite)
            print(r.stdout[-1500:], r.stderr[-800:])

    print()
    if failed:
        sys.exit(f"{len(failed)} Suite(n) fehlgeschlagen: {', '.join(failed)}")
    print(f"alle {len(SUITES)} Suiten bestanden")


if __name__ == "__main__":
    main()
