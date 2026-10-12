"""Read and process 1D NMR raw data (Bruker and Varian/Agilent).

Qt- and Orange-free on purpose: the numerics and the file formats are testable
headlessly, and the widget only wraps them.

Supported containers
--------------------
* **Bruker**: a directory with ``acqus`` (FID) and optionally
  ``pdata/<n>/1r`` + ``procs``. The processed spectrum is preferred when present
  (Bruker's own processing already handles the digital filter); otherwise the FID
  is read (``fid``/``ser``, int32/float per ``BYTORDA``/``DTYPA``) and processed
  here.
* **Varian / Agilent**: a ``*.fid`` directory with ``procpar`` and ``fid``. Two
  container layouts are recognised: the classic block format (4-byte length word
  per block, 1024-byte aligned) and the VnmrJ 4.x 1D layout (32-byte file header
  + 28-byte block header, int32 big-endian). Both store interleaved complex data.

The ppm axis follows the documented convention that the carrier sits in the
centre of the acquisition window (``tof``/``O1`` relative to ``sfrq``/``SFO1``).
Instruments reference differently, so the widget offers a referencing step
(solvent presets or an explicit ppm) - that is what makes the axis absolute.
"""
import os
import re
import struct

import numpy as np

__all__ = [
    "Dataset", "find_datasets", "read_vendor", "read_procpar", "read_acqus",
 "apodize", "zero_fill", "auto_phase", "phase_correct", "poly_baseline",
 "process_fid", "ppm_axis", "align_to_reference", "peak_in_region",
 "align_region", "split_sample_experiment", "describe", "SOLVENT_PPM",
 ]

#: common referencing standards (ppm)
SOLVENT_PPM = {
    "TSP": 0.00, "DSS": 0.00, "TMS": 0.00,
    "water": 4.70, "HDO": 4.70,
    "DMSO": 2.50, "acetone": 2.05, "chloroform": 7.26, "CHCl3": 7.26,
    "methanol": 3.31, "acetonitrile": 1.94,
    "formate": 8.44, "imidazole": 8.16, "dioxane": 3.75,
}


class Dataset(object):
    """One raw dataset on disk."""

    def __init__(self, path, vendor, name, has_processed=False):
        self.path = path              # the dataset directory (Bruker) or *.fid dir
        self.vendor = vendor          # "bruker" | "varian"
        self.name = name
        self.has_processed = has_processed

    def __repr__(self):
        return f"Dataset({self.name!r}, {self.vendor})"


# --------------------------------------------------------------------------
# parameter files
# --------------------------------------------------------------------------

_NUM = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")


def read_acqus(path):
    """Bruker parameter file (acqus/procs) -> {name: value}.

    Lines look like ``##$TD= 32768``; arrays continue on the following lines.
    """
    params = {}
    name = None
    for line in open(path, "r", errors="replace"):
        line = line.rstrip("\n")
        if line.startswith("##$"):
            key, _, rest = line[3:].partition("=")
            name = key.strip()
            rest = rest.strip()
            if rest.startswith("("):
                params[name] = []
                continue
            # a scalar on the same line, followed by the "##$X= value" style
            params[name] = _coerce(rest) if rest else []
        elif name is not None and line.strip():
            value = line.strip()
            if value in ("##END=", "END"):
                name = None
            elif isinstance(params.get(name), list):
                params[name].append(_coerce(value))
    # a one-element list is a scalar
    return {k: (v[0] if isinstance(v, list) and len(v) == 1 else v)
            for k, v in params.items()}


def _coerce(text):
    text = text.strip().strip("<>")
    if _NUM.match(text):
        try:
            return float(text) if ("." in text or "e" in text.lower()) else int(text)
        except ValueError:
            return text
    return text


def read_procpar(path):
    """Varian/Agilent ``procpar`` -> {name: value or list}.

    Layout per parameter: a header line (name + numbers), then one value line per
    array element (prefixed by the 1-based index), then a terminator line.
    """
    params = {}
    lines = open(path, "r", errors="replace").read().splitlines()
    i = 0
    while i < len(lines):
        tokens = lines[i].split()
        if len(tokens) >= 2:
            name = tokens[0]
            subtype = tokens[2] if len(tokens) > 2 else "1"
            values = []
            i += 1
            while i < len(lines):
                parts = lines[i].split()
                if len(parts) < 2:
                    break
                if str(subtype) == "2":                 # string parameter
                    values.append(" ".join(parts[1:]).strip().strip('"'))
                else:
                    values.append(" ".join(parts[1:]).strip())
                i += 1
            params[name] = values[0] if len(values) == 1 else values
        i += 1
    return params


def _as_float(params, name, default=None):
    value = params.get(name, default)
    if isinstance(value, (list, tuple)):
        value = value[0] if value else default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------
# dataset discovery
# --------------------------------------------------------------------------

def _vendor_of(dirpath, filenames):
    """'bruker' | 'varian' | None for a directory, by the files present.

    The raw data file must be there too: VnmrJ writes extra `procpar` copies
    below `dirinfo/` that are not datasets.
    """
    if "acqus" in filenames and ("fid" in filenames or "ser" in filenames):
        return "bruker"
    if "procpar" in filenames and "fid" in filenames:
        return "varian"
    return None


def find_datasets(root):
    """Every raw dataset below `root` (a single dataset directory works too)."""
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        return []
    vendor = _vendor_of(root, os.listdir(root))
    if vendor == "bruker":
        return [Dataset(root, "bruker", os.path.basename(root),
                        _bruker_processed_path(root) is not None)]
    if vendor == "varian":
        return [Dataset(root, "varian", os.path.basename(root))]
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        vendor = _vendor_of(dirpath, filenames)
        if vendor:
            found.append(Dataset(dirpath, vendor, os.path.basename(dirpath),
                                 vendor == "bruker"
                                 and _bruker_processed_path(dirpath) is not None))
            dirnames[:] = []                       # do not descend into a dataset
    return sorted(found, key=lambda d: d.name)


def _bruker_processed_path(path):
    pdata = os.path.join(path, "pdata")
    if not os.path.isdir(pdata):
        return None
    for sub in sorted(os.listdir(pdata)):
        candidate = os.path.join(pdata, sub, "1r")
        if os.path.isfile(candidate):
            return candidate
    return None


# --------------------------------------------------------------------------
# reading the time-domain data
# --------------------------------------------------------------------------

def _read_bruker_fid(path):
    """(complex FID, acqus params) for a Bruker dataset directory."""
    acqus = read_acqus(os.path.join(path, "acqus"))
    raw_file = os.path.join(path, "fid")
    if not os.path.isfile(raw_file):
        raw_file = os.path.join(path, "ser")
    raw = open(raw_file, "rb").read()
    td = int(_as_float(acqus, "TD", len(raw) // 4))
    big = int(_as_float(acqus, "BYTORDA", 0))
    dtypa = int(_as_float(acqus, "DTYPA", 0))
    if dtypa == 0:
        dtype = ">i4" if big else "<i4"
    elif dtypa == 1:
        dtype = ">f8" if big else "<f8"
    else:
        dtype = ">f4" if big else "<f4"
    values = np.frombuffer(raw[:td * np.dtype(dtype).itemsize], dtype=dtype)
    data = values.astype(float)
    if len(data) % 2:                              # odd TD: drop the last point
        data = data[:-1]
    # interleaved real/imaginary pairs -> complex
    fid = data[0::2] + 1j * data[1::2]
    return fid, acqus


def _read_bruker_processed(spectrum_file):
    """(real spectrum, ppm axis, procs params) from a pdata/<n>/1r file."""
    params = read_acqus(os.path.join(os.path.dirname(spectrum_file), "procs"))
    raw = open(spectrum_file, "rb").read()
    size = int(_as_float(params, "SI", len(raw) // 4))
    big = int(_as_float(params, "BYTORDA", 0))
    dtype = (">i4" if big else "<i4") if len(raw) >= size * 4 else (
        ">f4" if big else "<f4")
    spectrum = np.frombuffer(raw[:size * np.dtype(dtype).itemsize],
                             dtype=dtype).astype(float)
    sw_p = _as_float(params, "SW_p")               # Hz
    sf = _as_float(params, "SF")                   # MHz
    offset = _as_float(params, "OFFSET", 0.0)      # ppm of the carrier
    if not (sw_p and sf):
        raise ValueError(f"{path}: procs without SW_p/SF - cannot build the axis")
    ppm = ppm_axis(len(spectrum), sw_p / sf, offset, decreasing=True)
    return spectrum, ppm, params


def _varian_meta(params):
    sw = _as_float(params, "sw")                   # Hz
    sfrq = _as_float(params, "sfrq")               # MHz
    tof = _as_float(params, "tof", 0.0)            # Hz
    if not (sw and sfrq):
        raise ValueError("procpar without sw/sfrq - cannot build the axis")
    return sw, sfrq, tof


def _read_varian_fid(path):
    """(complex FID, meta) for a Varian/Agilent *.fid directory.

    Two container layouts are handled: the classic block format and the VnmrJ 4.x
    1D layout (a 32-byte file header + 28-byte block header before the int32
    data, big-endian, verified against BASF/VnmrJ data).
    """
    params = read_procpar(os.path.join(path, "procpar"))
    raw = open(os.path.join(path, "fid"), "rb").read()
    if len(raw) < 8:
        raise ValueError(f"{path}/fid is empty")
    # --- layout B: VnmrJ 4.x 1D -------------------------------------------------
    head = np.frombuffer(raw[:24], dtype=">i4")
    if head[2] > 0 and head[3] in (4, 8) and len(raw) >= 60 + head[2] * head[3]:
        npts, itemsize = int(head[2]), int(head[3])
        dtype = ">i4" if itemsize == 4 else ">f8"
        data = np.frombuffer(raw[60:60 + npts * itemsize],
                             dtype=dtype).astype(float)
        return _to_complex(data), params, "vnmrj"
    # --- layout A: classic block format (4-byte length word per block) ----------
    npts = int(_as_float(params, "np", 0))
    values = []
    offset = 0
    while offset + 4 <= len(raw):
        count = struct.unpack(">i", raw[offset:offset + 4])[0]
        if count <= 0 or count > 1_000_000:
            break
        block = raw[offset + 4:offset + 4 + count * 4]
        if len(block) < count * 4:
            break
        values.append(np.frombuffer(block, dtype=">f4").astype(float))
        offset += 4 + count * 4
        offset += (-offset) % 1024                 # blocks are 1024-byte aligned
        if npts and sum(len(v) for v in values) >= npts:
            break
    if not values:
        raise ValueError(f"{path}/fid: unknown Varian container layout")
    data = np.concatenate(values)
    if npts:
        data = data[:npts]
    return _to_complex(data), params, "block"


def _to_complex(data):
    """Interleaved real/imaginary pairs -> complex (drop an odd last point)."""
    if len(data) % 2:
        data = data[:-1]
    return data[0::2] + 1j * data[1::2]


def read_vendor(dataset, processed=True):
    """Read one dataset.

    Returns ``(data, ppm, info)`` where `data` is a complex FID (time domain) or a
    real spectrum when `processed` data are available and used. `info` records the
    vendor, the layout, the parameters and whether the data are time or frequency
    domain.
    """
    if dataset.vendor == "bruker":
        if processed:
            path = _bruker_processed_path(dataset.path)
            if path is not None:
                spectrum, ppm, procs = _read_bruker_processed(path)
                return spectrum, ppm, dict(vendor="bruker", domain="frequency",
                                           layout="pdata", params=procs)
        fid, acqus = _read_bruker_fid(dataset.path)
        sw = _as_float(acqus, "SW_h")
        obs = _as_float(acqus, "BF1") or _as_float(acqus, "SFO1")
        carrier = (_as_float(acqus, "O1", 0.0) or 0.0) / obs if obs else 0.0
        return fid, None, dict(vendor="bruker", domain="time", layout="fid",
                               sw_hz=sw, obs=obs, carrier_ppm=carrier,
                               params=acqus)
    fid, params, layout = _read_varian_fid(dataset.path)
    sw, sfrq, tof = _varian_meta(params)
    return fid, None, dict(vendor="varian", domain="time", layout=layout,
                           sw_hz=sw, obs=sfrq, carrier_ppm=tof / sfrq,
                           params=params)


# --------------------------------------------------------------------------
# processing
# --------------------------------------------------------------------------

def apodize(fid, sw_hz, lb_hz=0.3, kind="exponential", gb=0.0):
    """Window function on the FID: exponential (LB in Hz) or Gaussian."""
    n = len(fid)
    if n == 0 or lb_hz <= 0:
        return fid
    t = np.arange(n) / float(sw_hz)
    if kind == "gaussian":
        # gb = line broadening at the Gaussian's maximum, in Hz
        return fid * np.exp(-((np.pi * lb_hz * t) ** 2) / (2.0 * max(gb, 1e-6)))
    return fid * np.exp(-np.pi * lb_hz * t)


def zero_fill(fid, factor=1):
    """Pad the FID with zeros; `factor` = 1 keeps the length."""
    factor = max(1, int(factor))
    n = len(fid) * factor
    n = int(2 ** np.ceil(np.log2(max(n, 2))))      # power of two
    out = np.zeros(n, dtype=complex)
    out[:len(fid)] = fid
    return out


def ppm_axis(n, sw_ppm, carrier_ppm, decreasing=True):
    """ppm axis for `n` points spanning `sw_ppm` around `carrier_ppm`."""
    step = sw_ppm / float(n)
    if decreasing:
        return carrier_ppm + sw_ppm / 2.0 - np.arange(n) * step
    return carrier_ppm - sw_ppm / 2.0 + np.arange(n) * step


def phase_correct(spectrum, p0=0.0, p1=0.0):
    """Apply a zero- (p0) and first-order (p1) phase in degrees."""
    n = len(spectrum)
    x = (np.arange(n) - n / 2.0) / (n / 2.0)
    return spectrum * np.exp(1j * np.deg2rad(p0 + p1 * x))


def auto_phase(spectrum, coarse=2.0):
    """Best (p0, p1) by maximising the positive area and penalising negatives.

    A grid search, cheap and predictable - good enough for a first look; the
    widget lets the user refine both angles by hand.
    """
    n = len(spectrum)
    x = (np.arange(n) - n / 2.0) / (n / 2.0)
    best = None
    for p0 in np.arange(0.0, 360.0, 15.0):
        for p1 in np.arange(-180.0, 180.1, coarse * 5):
            re = (spectrum * np.exp(1j * np.deg2rad(p0 + p1 * x))).real
            score = re.sum() - 3.0 * np.abs(re[re < 0]).sum()
            if best is None or score > best[0]:
                best = (score, p0, p1)
    return float(best[1]), float(best[2])


def poly_baseline(spectrum, order=5, iterations=6, keep=0.6):
    """Iterative polynomial baseline on the real part (returns the baseline).

    Points are accepted for the fit in the lowest `keep` fraction of the
    distribution; repeating this converges on the noise floor instead of the
    peaks.
    """
    y = np.real(spectrum)
    x = np.linspace(-1.0, 1.0, len(y))
    mask = np.ones(len(y), dtype=bool)
    baseline = np.zeros_like(y)
    for _ in range(max(1, iterations)):
        if mask.sum() <= order + 2:
            break
        coeffs = np.polyfit(x[mask], y[mask], order)
        baseline = np.polyval(coeffs, x)
        resid = y - baseline
        threshold = np.quantile(resid, keep)
        mask = resid <= threshold
    return baseline


def align_to_reference(ppm, spectrum, target_ppm, window=0.5):
    """Shift the axis so the strongest peak near `target_ppm` sits exactly there.

    Returns ``(ppm, delta)`` with `delta` the applied correction (old - new), so
    a caller can report it. Without a peak in the window nothing is shifted.
    """
    ppm = np.asarray(ppm, dtype=float)
    mask = (ppm >= target_ppm - window) & (ppm <= target_ppm + window)
    if not mask.any():
        return ppm, 0.0
    values = np.asarray(spectrum, dtype=float)[mask]
    found = ppm[mask][int(np.argmax(np.abs(values)))]
    delta = float(found - target_ppm)
    return ppm - delta, delta


def peak_in_region(ppm, spectrum, region):
    """ppm of the strongest peak inside `region`, or None.

    `region` is a (low, high) tuple in ppm - what the user drags in the preview.
    """
    ppm = np.asarray(ppm, dtype=float)
    low, high = sorted(float(v) for v in region)
    mask = (ppm >= low) & (ppm <= high)
    if not mask.any():
        return None
    values = np.asarray(spectrum, dtype=float)[mask]
    return float(ppm[mask][int(np.argmax(np.abs(values)))])


def align_region(ppm, spectrum, region, target_ppm):
    """Shift the axis so the strongest peak inside `region` lands on `target_ppm`.

    This is the interactive referencing route: the user marks the signal (CHCl3,
    TSP, ...) with the mouse and names the standard, no assumption about where the
    peak *should* be is needed. Returns ``(ppm, delta, found)``; `found` is None
    when the region holds no data.
    """
    found = peak_in_region(ppm, spectrum, region)
    if found is None:
        return np.asarray(ppm, dtype=float), 0.0, None
    delta = float(found - float(target_ppm))
    return np.asarray(ppm, dtype=float) - delta, delta, found


def split_sample_experiment(name):
    """('BASF_Probe7_PROTON_01.fid') -> ('BASF_Probe7', 'PROTON_01').

    The trailing one or two underscore-separated tokens are the experiment; what
    is left is the sample. A name without an obvious experiment keeps the whole
    stem as the sample.
    """
    stem = name[:-4] if name.lower().endswith(".fid") else name
    parts = [p for p in stem.split("_") if p]
    if len(parts) >= 3:
        return "_".join(parts[:-2]), "_".join(parts[-2:])
    if len(parts) == 2:
        return parts[0], parts[1]
    return stem, stem


def describe(dataset):
    """(sample, experiment) for a dataset, for grouping a study into a matrix.

    Varian/Agilent: from the `*.fid` folder name. Bruker: the dataset folder is the
    experiment number and its parent is the sample.
    """
    if dataset.vendor == "varian":
        return split_sample_experiment(dataset.name)
    parent = os.path.basename(os.path.dirname(dataset.path))
    return (parent or dataset.name, dataset.name)


def process_fid(fid, meta, lb_hz=0.3, window="exponential", zero=1, phase="auto",
                p0=0.0, p1=0.0, baseline_order=0):
    """Full pipeline: window -> zero fill -> FFT -> phase -> baseline.

    Returns ``(ppm, spectrum, info)``; `info` carries the phase angles used.
    Referencing is a separate step (`align_to_reference`), because the absolute
    axis is a choice rather than part of the transform.
    """
    sw_hz = meta.get("sw_hz")
    carrier = meta.get("carrier_ppm", 0.0)
    if not sw_hz:
        raise ValueError("no spectral width - cannot process the FID")
    acc = apodize(np.asarray(fid), sw_hz, lb_hz, window)
    acc = zero_fill(acc, zero)
    n = len(acc)
    spec = np.fft.fftshift(np.fft.fft(acc, n=n))[::-1]
    sw_ppm = sw_hz / float(meta.get("obs") or 1.0) if meta.get("obs") else None
    if not sw_ppm:
        raise ValueError("no spectrometer frequency - cannot build the ppm axis")
    ppm = ppm_axis(n, sw_ppm, carrier, decreasing=True)

    info = {}
    if phase == "auto":
        p0, p1 = auto_phase(spec)
    if p0 or p1:
        spec = phase_correct(spec, p0, p1)
    info["phase"] = (p0, p1)
    spec = spec.real

    if baseline_order:
        spec = spec - poly_baseline(spec, order=int(baseline_order))

    return ppm, spec, info
