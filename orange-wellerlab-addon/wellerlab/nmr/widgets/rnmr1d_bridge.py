"""
Rnmr1D subprocess bridge for the NMR Peak Finding / Calibration / Peak Matching
widgets.

NMRProcFlow is an R/Shiny GUI; its computation core is the R package
``Rnmr1D`` (github INRA/Rnmr1D).  This module drives it headlessly:

    Orange Table (ppm-as-attribute-name + intensities)
        -> CSV (rows=samples, cols=ppm points)
        -> Rscript (builds a ``spec`` object, calls Rnmr1D)
        -> result CSV
        -> Orange Table

Three operations are exposed:

* :func:`peak_finding`   -- ``peakFinder`` (pseudo-Voigt deconvolution)
* :func:`calibrate`      -- ``calibSpectrum`` (reference-peak shift)
* :func:`peak_matching`  -- ``peakMatching`` (DB annotation, dbref6/hmdb110)

Deliberately a subprocess (not rpy2): no binary linking between Orange's
embedded Python and R, no version triangle.  ``Rnmr1D`` is therefore a
system dependency, never an ``install_requires`` entry — the widget probes
availability and warns instead of crashing silently.

Rnmr1D 1.6.6 quirks worked around here (verified empirically):

* ``calibSpectrum`` assumes a *descending* ppm axis (index 1 = pmax, the
  Bruker convention).  Our tables are ascending, so the bridge reverses
  each spectrum, calibrates, and reverses back.
* ``peakMatching(method="all")`` crashes on an empty candidate
  intersection (``for (i in 1:length(results))`` -> ``1:0``).  The bridge
  uses ``method="one"`` and pre-filters the query peaks against the DB
  file with the identical tolerance, so the result can never be empty.
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


# ----------------------------------------------------------------------------
# Calibration (calibSpectrum)
# ----------------------------------------------------------------------------

#: Built-in reference-compound suggestions (name, ppm, zone hint).
REFERENCES = (
    ("TSP (0.00)", 0.000),
    ("DSS (0.00)", 0.000),
    ("DMSO (2.50)", 2.500),
    ("Tris (3.00)", 3.000),
    ("Choline (3.22)", 3.220),
    ("Formate (8.46)", 8.460),
)

_CALIB_CODE = r"""
@LIBPATHS@
if (!requireNamespace("Rnmr1D", quietly=TRUE))
    stop("Rnmr1D not found in libPaths.")
suppressMessages(library(Rnmr1D))
d   <- read.csv("@IN@", header=FALSE)
ppm <- as.numeric(read.csv("@PPM@", header=FALSE, colClasses="numeric")[,1])
n <- nrow(d); m <- length(ppm)
dppm <- diff(ppm)[1]
set.seed(42)   # calibSpectrum pads the shifted edge with rnorm() -> deterministic
# calibSpectrum assumes a DESCENDING ppm axis (index 1 = pmax). Our table is
# ascending, so reverse -> calibrate -> reverse the corrected signal back.
rows <- list(); Xcal <- d
for (i in seq_len(n)) {
  sig   <- as.numeric(d[i, ])
  sig_d <- rev(sig)
  ppm_d <- rev(ppm)
  spec  <- list(int=sig_d, ppm=ppm_d, pmin=ppm_d[m], pmax=ppm_d[1],
                dppm=dppm, B=max(1e-6, stats::sd(sig, na.rm=TRUE)),
                size=m, path=tempdir())
  res   <- calibSpectrum(spec, c(@ZLO@, @ZHI@), @PREF@)
  # corrected spectrum on the original (ascending) grid
  Xcal[i, ] <- rev(res$int)
  # position of the reference peak after calibration: argmax INSIDE the
  # reference zone (the tallest peak overall is usually NOT the reference).
  inzone <- res$ppm >= @ZLO@ & res$ppm <= @ZHI@
  i_pk   <- which.max(inzone * res$int)
  pkppm  <- res$ppm[i_pk]
  shift  <- pkppm - @PREF@
  rows[[length(rows)+1]] <- c(i, round(shift, 6), round(pkppm, 6))
}
out <- if (length(rows)) do.call(rbind, rows) else matrix(numeric(0), 0, 3)
write.table(out, "@OUT@", row.names=FALSE, col.names=FALSE, quote=FALSE, sep=",")
write.table(Xcal, "@XOUT@", row.names=FALSE, col.names=FALSE, quote=FALSE, sep=",")
cat("R-OK", nrow(out), "samples calibrated\n")
"""


def calibrate(spectra, ppm, zone_lo, zone_hi, ref_ppm, timeout=300):
    """Run Rnmr1D::calibSpectrum on all samples.

    Finds the highest peak inside ``[zone_lo, zone_hi]`` and shifts each
    spectrum so it lands on ``ref_ppm`` (the reference-compound chemical
    shift).  ``calibSpectrum`` shifts the intensity vector by whole points
    (zero-filling the exposed edge), so the ppm axis is preserved and the
    corrected reference peak lands on ``ref_ppm``.

    Parameters
    ----------
    spectra : (n_samples, n_points) ndarray.
    ppm     : (n_points,) ndarray (ascending).
    zone_lo, zone_hi : ppm range searched for the reference peak.
    ref_ppm : chemical shift the reference peak is moved to.

    Returns
    -------
    (X_cal, shifts, peak_after)
        X_cal     : (n_samples, n_points) ndarray — calibrated spectra.
        shifts    : (n_samples,) ndarray — residual shift after the integer
                    point shift (peak_after - ref_ppm, ≈ 0).
        peak_after: (n_samples,) ndarray — the reference peak's position in
                    the calibrated spectrum.
    """
    exe = rscript_path()
    if not exe:
        raise RuntimeError("Rscript not found — R is required for NMR Calibration.")
    if not (ppm[0] <= zone_lo < zone_hi <= ppm[-1]):
        raise RuntimeError("Reference zone outside spectrum range "
                           f"({ppm[0]:.2f}–{ppm[-1]:.2f} ppm).")
    with tempfile.TemporaryDirectory() as td:
        f_in = os.path.join(td, "spectra.csv")
        f_ppm = os.path.join(td, "ppm.csv")
        f_out = os.path.join(td, "shifts.csv")
        f_x = os.path.join(td, "calib.csv")
        f_code = os.path.join(td, "run.R")
        code = (_CALIB_CODE
                .replace("@LIBPATHS@", _libpaths_line())
                .replace("@IN@", f_in).replace("@PPM@", f_ppm)
                .replace("@OUT@", f_out).replace("@XOUT@", f_x)
                .replace("@ZLO@", repr(float(zone_lo)))
                .replace("@ZHI@", repr(float(zone_hi)))
                .replace("@PREF@", repr(float(ref_ppm))))
        np.savetxt(f_in, spectra, delimiter=",")
        np.savetxt(f_ppm, ppm, delimiter=",")
        with open(f_code, "w") as fh:
            fh.write(code)
        proc = subprocess.run([exe, "--vanilla", "--slave", f_code],
                              capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr).strip()[-800:]
            raise RuntimeError("Rnmr1D failed:\n" + tail)
        n = spectra.shape[0]
        X_cal = np.loadtxt(f_x, delimiter=",").reshape(n, -1)
        arr = np.loadtxt(f_out, delimiter=",")
        if not arr.size:
            shifts = np.zeros(n)
            peak_after = np.full(n, ref_ppm)
        else:
            arr = arr.reshape(n, 3)
            shifts = arr[:, 1]
            peak_after = arr[:, 2]
        return X_cal, shifts, peak_after


# ----------------------------------------------------------------------------
# Peak matching / annotation (peakMatching)
# ----------------------------------------------------------------------------

#: Columns of the annotation output (after the query ppm).
MATCH_COLUMNS = ("name", "dbid", "dblink", "score")

#: Rnmr1D ships two built-in 1D-HM-DBs (package extra/ directory).
MATCH_LIBS = ("dbref6", "hmdb110")

_MATCH_CODE = r"""
@LIBPATHS@
if (!requireNamespace("Rnmr1D", quietly=TRUE))
    stop("Rnmr1D not found in libPaths.")
suppressMessages(library(Rnmr1D))
query <- c(@PPMS@)
# pre-filter the query against the DB file with the SAME tolerance Rnmr1D
# uses, so peakMatching() can never return an empty result (1.6.6 cannot
# handle that: `for (i in 1:length(results))` -> `1:0` -> crash).
DBfile <- file.path(system.file("extra", package="Rnmr1D"),
                   paste0(toupper("@LIB@"), "_NMR_peaklist.txt"))
if (!file.exists(DBfile)) stop(paste0(DBfile, " does not exist"))
db <- read.table(DBfile, sep="\t", header=TRUE)
dbppm <- as.numeric(unlist(strsplit(as.character(db[["peaks"]]), ",")))
tol <- @TOL@
keep <- query[sapply(query, function(p) any(abs(dbppm - p) <= tol))]
if (length(keep)) {
  res  <- peakMatching(keep, lib="@LIB@", ppmtol=tol, method="one")
  rows <- list()
  for (nm in names(res)) {
    e <- res[[nm]]
    s <- if (length(e$score)) e$score[1] else NA   # score is per compound, not per ppm
    # one row per (query peak, compound): pick the closest db ppm
    for (u in unique(e$pkquery)) {
      sel <- which(e$pkquery == u)
      j   <- sel[which.min(as.numeric(e$distance[sel]))]
      rows[[length(rows)+1]] <- c(u, e$name, e$dbid, e$dblink, s, e$ppm[j])
    }
  }
} else rows <- list()
out <- if (length(rows)) do.call(rbind, rows) else matrix(numeric(0), 0, 6)
write.table(out, "@OUT@", row.names=FALSE, col.names=FALSE, quote=FALSE, sep=",")
cat("R-OK", nrow(out), "annotations\n")
"""


def _run_script(code, timeout):
    """Write *code* to a temp .R, run Rscript --vanilla --slave on it.

    Raises RuntimeError with the R output tail on non-zero exit; returns
    the process stdout otherwise.  The temp directory (and any files the
    script wrote into it) is removed before returning.
    """
    exe = rscript_path()
    if not exe:
        raise RuntimeError("Rscript not found — R is required for Rnmr1D.")
    with tempfile.TemporaryDirectory() as td:
        f_code = os.path.join(td, "run.R")
        with open(f_code, "w") as fh:
            fh.write(code)
        proc = subprocess.run([exe, "--vanilla", "--slave", f_code],
                              capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            tail = (proc.stdout + proc.stderr).strip()[-800:]
            raise RuntimeError("Rnmr1D failed:\n" + tail)
        return proc.stdout


def peak_matching(ppms, lib="dbref6", tol=0.02, timeout=300):
    """Annotate a list of peak ppm values against an Rnmr1D reference DB.

    Parameters
    ----------
    ppms : array-like of float — the peak positions to annotate.
    lib  : "dbref6" or "hmdb110" (built-in 1D-HM DBs).
    tol  : matching tolerance in ppm (``ppmtol``).

    Returns
    -------
    object ndarray (n_annotations, 6) — one row per (peak, candidate) pair,
    in Rnmr1D's per-peak score order:
    [query_ppm, name, dbid, dblink, score, db_ppm].
    """
    ppms = np.asarray(ppms, dtype=float).ravel()
    if not ppms.size:
        return np.zeros((0, 6))
    lib = lib if lib in MATCH_LIBS else "dbref6"
    rppms = ",".join(repr(float(p)) for p in ppms)
    fd, f_out = tempfile.mkstemp(prefix="wellerlab_match_", suffix=".csv")
    os.close(fd)
    try:
        code = (_MATCH_CODE
                .replace("@LIBPATHS@", _libpaths_line())
                .replace("@LIB@", lib)
                .replace("@TOL@", repr(float(tol)))
                .replace("@PPMS@", rppms)
                .replace("@OUT@", f_out))
        _run_script(code, timeout)
        if not os.path.exists(f_out) or os.path.getsize(f_out) == 0:
            return np.zeros((0, 6))
        arr = np.loadtxt(f_out, delimiter=",", dtype=str, ndmin=2)
        return arr.reshape(-1, 6)
    finally:
        if os.path.exists(f_out):
            os.unlink(f_out)
