"""Find a Python that can import Orange, and run commands in it natively.

Orange lives in its own interpreter (on macOS inside Orange.app), and on Apple
Silicon an x86_64 parent (a Rosetta conda python) makes such a universal binary
pick the x86_64 slice, where Orange's arm64-only numpy extension fails to load
with the misleading "you should not try to import numpy from its source
directory". Both traps are handled here, once, for every tool that needs Orange:
`run_tests.py` and `tools/gen_widgets_md.py`.
"""
import os
import platform
import subprocess
import sys


def apple_silicon():
    try:
        return subprocess.run(["sysctl", "-n", "hw.optional.arm64"],
                              capture_output=True, text=True, timeout=10
                              ).stdout.strip() == "1"
    except (OSError, subprocess.SubprocessError):
        return False


def native(cmd):
    """Force native execution of a universal binary on Apple Silicon."""
    if platform.system() == "Darwin" and apple_silicon():
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


def reexec_if_needed(module="Orange", script=None):
    """Re-run *this* script under an interpreter that can import `module`.

    Called at the top of a tool that needs Orange, so `python3 tool.py` and
    `make <target>` work with whatever python3 is on PATH.
    """
    try:
        __import__(module)
        return
    except ImportError:
        pass
    exe = find_orange_python()
    if exe and os.path.realpath(exe) != os.path.realpath(sys.executable):
        sys.exit(subprocess.run(native([exe, script or sys.argv[0],
                                        *sys.argv[1:]])).returncode)
    sys.exit(f"Kein Python mit {module} gefunden ({exe or 'kein Kandidat'} kann es nicht "
             f"importieren) - auf macOS: /Applications/Orange.app/Contents/MacOS/python.")
