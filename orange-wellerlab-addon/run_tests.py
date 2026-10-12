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
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from orange_python import find_orange_python, native     # noqa: E402  (shared helper)
SUITES = ("_test_opls_core.py", "_test_owoplsda.py", "_test_suite.py",
          "_test_heatmap.py", "_test_volcano.py", "_test_selection.py",
          "_test_pca.py", "_test_tableutils.py", "_test_nmr_io.py",
          "_test_biplot.py", "_test_workflows.py")


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
