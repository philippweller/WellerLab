"""
Rnmr1D subprocess bridge for the NMR Peak Finding widget.

NMRProcFlow is an R/Shiny GUI; its computation core is the R package
``Rnmr1D`` (github INRA/Rnmr1D).  This module drives it headlessly:

    Orange Table (ppm-as-attribute-name + intensities)
        -> CSV (rows=samples, cols=ppm points)
        -> Rscript (builds a ``spec`` object, calls ``peakFinder``)
        -> peaks CSV (sample, ppm, amp, sigma, eta, asym, integral)
        -> Orange Table

Deliberately a subprocess (not rpy2): no binary linking between Orange's
embedded Python and R, no version triangle.  ``Rnmr1D`` is therefore a
system dependency, never an ``install_requires`` entry — the widget probes
availability and warns instead of crashing silently.
"""

import os
import shutil
import subprocess
import tempfile

import numpy as np

#: Standard install location of the Rnmr1D R-library (R user library).
#: Overridable via the WELLERLAB_R_LIBS environment variable (``;``-separated).
DEFAULT_R_LIBS = os.path.expanduser("~/Library/R/nmrprocflow")

#: Columns of the peaks output (Rnmr1D peakFinder, after the sample index).
PEAK_COLUMNS = ("ppm", "amp", "sigma", "eta", "asym", "integral")

_R_CODE = r"""
@LIBPATHS@
if (!requireNamespace("Rnmr1D", quietly=TRUE))
    stop("Rnmr1D not found in libPaths. Install it (github INRA/Rnmr1D) or set WELLERLAB_R_LIBS.")
suppressMessages(library(Rnmr1D))
d   <- read.csv("@IN@", header=FALSE)
ppm <- as.numeric(read.csv("@PPM@", header=FALSE, colClasses="numeric")[,1])
n <- nrow(d); m <- length(ppm)
dppm <- diff(ppm)[1]
rows <- list()
for (i in seq_len(n)) {
  sig  <- as.numeric(d[i, ])
  spec <- list(int=sig, ppm=ppm, pmin=ppm[1], pmax=ppm[m], dppm=dppm,
               B=stats::sd(sig, na.rm=TRUE), path=tempdir())
  mod <- peakFinder(spec, c(@LO@, @HI@),
                    params=list(optim=@OPTIM@, ratioPN=@RATIO@,
                                pvoigt=@PVOIGT@, eta=@ETA@), verbose=0)
  pk <- mod$peaks
  for (j in seq_len(nrow(pk))) {
    rows[[length(rows)+1]] <- c(i, pk$ppm[j], pk$amp[j], pk$sigma[j],
                                pk$eta[j], pk$asym[j], pk$integral[j])
  }
}
out <- if (length(rows)) do.call(rbind, rows) else matrix(numeric(0), 0, 7)
write.table(out, "@OUT@", row.names=FALSE, col.names=FALSE, quote=FALSE, sep=",")
cat("R-OK", nrow(out), "peaks from", n, "samples\n")
"""


def rscript_path():
    """Return the Rscript executable, or None."""
    return shutil.which("Rscript") or (
        "/usr/local/bin/Rscript" if os.path.exists("/usr/local/bin/Rscript") else None)


def _libpaths_line():
    """R statement adding WELLERLAB_R_LIBS / default lib to .libPaths().

    We run Rscript with ``--vanilla`` (see :func:`peak_finding`), which drops
    the home R library (``~``) — on this machine that is a stale R-3.x
    x86_64 library that would otherwise shadow the arm64 system packages.
    The system library is therefore added explicitly.
    """
    libs = [p for p in os.environ.get("WELLERLAB_R_LIBS", "").split(";") if p]
    if not libs:
        libs = [DEFAULT_R_LIBS]
    system_lib = "/Library/Frameworks/R.framework/Versions/Current/" \
                 "Resources/library"
    quoted = ", ".join('"%s"' % p for p in libs + [system_lib])
    # REPLACE the library list (do not append): --vanilla already drops the
    # home lib, and anything else (e.g. a stale ~/ R-3.x x86_64 lib via
    # Renviron) must not shadow the arm64 system packages.
    return '.libPaths(c(%s))' % quoted


#: probe result cache (None = not probed yet)
_PROBE_CACHE = {}


def rnmr1d_available(timeout=20, force=False):
    """True if Rscript exists and Rnmr1D loads. Cached per process."""
    if not force and "ok" in _PROBE_CACHE:
        return _PROBE_CACHE["ok"]
    exe = rscript_path()
    if not exe:
        _PROBE_CACHE["ok"] = False
        return False
    probe = ("%s\nif (requireNamespace('Rnmr1D', quietly=TRUE)) "
             "cat('OK\\n') else cat('NO\\n')") % _libpaths_line()
    try:
        r = subprocess.run([exe, "--vanilla", "--slave", "-e", probe],
                           capture_output=True, text=True, timeout=timeout)
        _PROBE_CACHE["ok"] = r.returncode == 0 and "OK" in r.stdout
    except (subprocess.TimeoutExpired, OSError):
        _PROBE_CACHE["ok"] = False
    return _PROBE_CACHE["ok"]


def peak_finding(spectra, ppm, ppm_lo=0.5, ppm_hi=8.0, ratio=5.0,
                 pvoigt=1, eta=0.7, optim=1, timeout=600):
    """Run Rnmr1D::peakFinder on all samples.

    Parameters
    ----------
    spectra : (n_samples, n_points) ndarray — intensity per ppm point.
    ppm     : (n_points,) ndarray — chemical shift axis.
    ppm_lo, ppm_hi : deconvolution window.
    ratio   : peak/noise ratio threshold (deconvParams ``ratioPN``).
    pvoigt, eta, optim : deconvolution model switches (Rnmr1D defaults 1, 0.7, 1).

    Returns
    -------
    peaks : (n_peaks, 7) ndarray — [sample_idx(1-based), ppm, amp, sigma,
            eta, asym, integral]  (matches :data:`PEAK_COLUMNS` + index).

    Raises
    ------
    RuntimeError with the R error text when Rscript fails.
    """
    exe = rscript_path()
    if not exe:
        raise RuntimeError("Rscript not found — R is required for NMR Peak Finding.")
    if not (ppm_lo < ppm_hi <= ppm[-1]):
        raise RuntimeError("Invalid ppm range: need lo < hi within the spectrum.")
    with tempfile.TemporaryDirectory() as td:
        f_in = os.path.join(td, "spectra.csv")
        f_ppm = os.path.join(td, "ppm.csv")
        f_out = os.path.join(td, "peaks.csv")
        f_code = os.path.join(td, "run.R")
        code = (_R_CODE
                .replace("@LIBPATHS@", _libpaths_line())
                .replace("@IN@", f_in).replace("@PPM@", f_ppm)
                .replace("@OUT@", f_out)
                .replace("@LO@", repr(float(ppm_lo)))
                .replace("@HI@", repr(float(ppm_hi)))
                .replace("@OPTIM@", str(int(optim)))
                .replace("@RATIO@", repr(float(ratio)))
                .replace("@PVOIGT@", str(int(pvoigt)))
                .replace("@ETA@", repr(float(eta))))
        np.savetxt(f_in, spectra, delimiter=",")
        np.savetxt(f_ppm, ppm, delimiter=",")
        with open(f_code, "w") as fh:
            fh.write(code)
        proc = subprocess.run([exe, "--vanilla", "--slave", f_code],
                              capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr).strip()[-800:]
            raise RuntimeError("Rnmr1D failed:\n" + tail)
        peaks = np.loadtxt(f_out, delimiter=",")
        return peaks.reshape(-1, 7) if peaks.size else np.zeros((0, 7))
