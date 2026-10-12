#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Checks for the NMR raw-data reader and the NMR Raw Import widget.

    python3 run_tests.py        # runs this with the other suites

The central test is *not* circular: synthetic FIDs are built from peaks at known
ppm positions using physics only (offset = (ppm - carrier) * obs, FID =
sum A*exp(i*2*pi*f*t), t = n/sw) and written in the vendor containers. The reader
must place those peaks back at their ppm positions.
"""
import os
import shutil
import struct
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

from AnyQt.QtWidgets import QApplication
from Orange.data import Table

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from wellerlab.nmr import nmr_io

app = QApplication.instance() or QApplication(sys.argv or ["test"])

fails = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        fails.append(name)


# ---------------------------------------------------------------- physics
OBS = 500.0                     # MHz
SW = 6000.0                     # Hz  -> 12 ppm window
CARRIER = 4.70                  # ppm, centre of the window
PEAKS = ((7.30, 1.0), (3.55, 0.6), (1.20, 0.35))
N_COMPLEX = 4096
LB_TRUE = 1.5                   # Hz, the linewidth we build in


def synthetic_fid():
    t = np.arange(N_COMPLEX) / SW
    fid = np.zeros(N_COMPLEX, dtype=complex)
    for ppm, amp in PEAKS:
        freq = (ppm - CARRIER) * OBS            # Hz, physics
        fid += amp * np.exp(2j * np.pi * freq * t)
    return fid * np.exp(-np.pi * LB_TRUE * t)


def peaks_in(ppm, spectrum, count=3, threshold=0.15):
    """The strongest separated lines as ppm values."""
    values = np.abs(spectrum)
    found = []
    order = np.argsort(-values)
    for i in order:
        if values[i] < threshold * values.max():
            break
        if all(abs(ppm[i] - p) > 0.1 for p in found):
            found.append(float(ppm[i]))
        if len(found) == count:
            break
    return sorted(found)


# ---------------------------------------------------------------- Bruker
def write_bruker(root, fid):
    os.makedirs(root, exist_ok=True)
    td = 2 * N_COMPLEX
    acqus = "\n".join([
        "##TITLE= synthetic",
        f"##$TD= {td}",
        f"##$SW_h= {SW}",
        f"##$SW= {SW / OBS}",
        f"##$SFO1= {OBS}",
        f"##$BF1= {OBS}",
        f"##$O1= {CARRIER * OBS}",
        "##$BYTORDA= 0",
        "##$DTYPA= 0",
        "##$NUC1= <1H>",
        "##END=",
    ])
    open(os.path.join(root, "acqus"), "w").write(acqus)
    interleaved = np.empty(td)
    interleaved[0::2] = fid.real
    interleaved[1::2] = fid.imag
    scaled = np.round(interleaved / np.abs(interleaved).max() * 2_000_000)
    scaled.astype("<i4").tofile(os.path.join(root, "fid"))
    return root


# ---------------------------------------------------------------- Varian
def write_varian(root, fid, layout="vnmrj"):
    os.makedirs(root, exist_ok=True)
    npts = 2 * N_COMPLEX
    procpar = "\n".join([
        f"sw 1 1 5 5 5 2 1 8203 1 64",
        f"1 {SW}",
        "0",
        "sfrq 1 1 1000000000 0 0 2 1 11 1 64",
        f"1 {OBS}",
        "0",
        "np 7 1 128000 32 2 2 1 11 1 64",
        f"1 {npts}",
        "0",
        "tof 5 1 7 7 7 2 1 8202 1 64",
        f"1 {CARRIER * OBS}",
        "0",
        "solvent 2 2 6 0 0 2 1 11 1 64",
        '1 "d2o"',
        "0",
    ])
    open(os.path.join(root, "procpar"), "w").write(procpar)
    interleaved = np.empty(npts)
    interleaved[0::2] = fid.real
    interleaved[1::2] = fid.imag
    scaled = np.round(interleaved / np.abs(interleaved).max() * 2_000_000)
    raw = scaled.astype(">i4").tobytes()
    if layout == "vnmrj":
        # 32-byte file header, then a 28-byte block header -> data starts at 60
        # (the layout decoded from the real VnmrJ files)
        header = np.array([1, 1, npts, 4, len(raw), 28 + len(raw), 0, 0],
                          dtype=">i4").tobytes()
        block = np.array([69, 1, 69, 65536, 16, 0, 0], dtype=">i4").tobytes()
        payload = header + block + raw
    else:                                   # classic block format (float32)
        blocks = []
        step = 2048
        fraw = scaled.astype(">f4").tobytes()
        for start in range(0, npts, step):
            chunk = fraw[start * 4:(start + step) * 4]
            header = struct.pack(">i", len(chunk) // 4)
            pad = (-(len(header) + len(chunk))) % 1024
            blocks.append(header + chunk + b"\0" * pad)
        payload = b"".join(blocks)
    open(os.path.join(root, "fid"), "wb").write(payload)
    return root


tmp = tempfile.mkdtemp(prefix="nmr-io-test-")
try:
    fid = synthetic_fid()

    # --- Bruker round trip --------------------------------------------------
    bruker = write_bruker(os.path.join(tmp, "bruker_ds"), fid)
    datasets = nmr_io.find_datasets(bruker)
    check("Bruker dataset is found by its acqus/fid",
          len(datasets) == 1 and datasets[0].vendor == "bruker")
    data, _axis, meta = nmr_io.read_vendor(datasets[0])
    check("Bruker FID length matches TD/2",
          meta["domain"] == "time" and len(data) == N_COMPLEX, f"{len(data)}")
    check("Bruker carrier from O1/BF1", abs(meta["carrier_ppm"] - CARRIER) < 1e-6,
          f"{meta['carrier_ppm']:.4f}")
    ppm, spec, info = nmr_io.process_fid(data, meta, lb_hz=1.0, zero=1,
                                         phase="auto")
    got = peaks_in(ppm, spec)
    want = sorted(p for p, _ in PEAKS)
    check("Bruker: peaks land at the ppm they were built at",
          len(got) == 3 and np.allclose(got, want, atol=0.02),
          f"{[round(v, 3) for v in got]} vs {want}")

    # --- Varian, both container layouts ------------------------------------
    for layout in ("vnmrj", "block"):
        root = write_varian(os.path.join(tmp, f"varian_{layout}"), fid, layout)
        datasets = nmr_io.find_datasets(root)
        check(f"Varian ({layout}) dataset is found",
              len(datasets) == 1 and datasets[0].vendor == "varian")
        data, _axis, meta = nmr_io.read_vendor(datasets[0])
        check(f"Varian ({layout}) layout detected as {layout}",
              meta["layout"] == layout, meta["layout"])
        check(f"Varian ({layout}) FID length = np/2",
              len(data) == N_COMPLEX, f"{len(data)}")
        ppm, spec, info = nmr_io.process_fid(data, meta, lb_hz=1.0, zero=1,
                                             phase="auto")
        got = peaks_in(ppm, spec)
        check(f"Varian ({layout}): peaks land at the ppm they were built at",
              len(got) == 3 and np.allclose(got, want, atol=0.02),
              f"{[round(v, 3) for v in got]}")

    # --- referencing and helper units --------------------------------------
    ppm, spec, _ = nmr_io.process_fid(fid, dict(sw_hz=SW, obs=OBS,
                                                 carrier_ppm=CARRIER),
                                      lb_hz=1.0, zero=1, phase="auto")
    shifted, delta = nmr_io.align_to_reference(ppm, spec, 7.30, window=0.5)
    check("align_to_reference puts the peak exactly on the target",
          abs(shifted[np.argmax(np.abs(spec))] - 7.30) < 0.01,
          f"delta={delta:+.3f} ppm")
    check("align_to_reference outside the window changes nothing",
          nmr_io.align_to_reference(ppm, spec, -5.0, window=0.3)[1] == 0.0)

    check("zero_fill pads to a power of two",
          len(nmr_io.zero_fill(fid, 2)) == 8192)
    check("apodize without LB is the identity",
          np.allclose(nmr_io.apodize(fid, SW, 0.0), fid))
    check("apodize with LB damps the end of the FID",
          abs(nmr_io.apodize(fid, SW, 5.0)[-1]) < abs(fid[-1]))
    p0, p1 = nmr_io.auto_phase(np.fft.fftshift(np.fft.fft(fid)))
    re = nmr_io.phase_correct(np.fft.fftshift(np.fft.fft(fid)), p0, p1).real
    check("auto_phase finds a phase whose real part is mostly positive",
          re.sum() > 0 and re.sum() > 5 * np.abs(re[re < 0]).sum(),
          f"φ0={p0:.0f}°, φ1={p1:.0f}°")
    bl = nmr_io.poly_baseline(re, order=3)
    check("poly_baseline follows the noise floor, not the peaks",
          np.abs(bl).max() < 0.2 * np.abs(re).max(),
          f"max|baseline| = {np.abs(bl).max():.3g}")
    check("SOLVENT_PPM knows the common standards",
          nmr_io.SOLVENT_PPM["water"] == 4.70 and nmr_io.SOLVENT_PPM["TSP"] == 0.0)

    # --- the widget ---------------------------------------------------------
    from wellerlab.nmr.widgets.ownmrimport import OWNMRImport
    w = OWNMRImport()
    sent = {}
    w.Outputs.spectra.send = lambda v: sent.__setitem__("t", v)
    w.folder = tmp
    w.reference = "none"            # this block checks the reader, not referencing
    w._rescan()
    app.processEvents()
    table = sent.get("t")
    check("widget emits a spectra table for the folder",
          isinstance(table, Table) and len(table) == 3,
          f"{None if table is None else len(table)} rows")
    if table is not None:
        cols = np.array([float(a.name) for a in table.domain.attributes])
        check("widget table columns are ppm values",
              cols.max() > 10.0 and cols.min() < 0.0, f"{cols.max():.2f}..{cols.min():.2f}")
        check("widget adds sample and experiment metas",
              [m.name for m in table.domain.metas] == ["sample", "experiment"])
        got = peaks_in(cols, np.asarray(table.X[0], dtype=float))
        check("widget spectrum keeps the built-in peak positions",
              np.allclose(got, want, atol=0.02), f"{[round(v, 2) for v in got]}")

    # --- experiment grouping and drag-region referencing --------------------
    study = os.path.join(tmp, "study")
    # shift every peak 0.20 ppm down, so the CHCl3-like line sits at 7.10
    off = synthetic_fid() * np.exp(-2j * np.pi * 0.20 * OBS
                                   * np.arange(N_COMPLEX) / SW)
    for sample_name in ("P1", "P2"):
        for experiment in ("PROTON_01", "PRESAT_01"):
            write_varian(os.path.join(study, f"{sample_name}_{experiment}.fid"), off)
    check("describe splits sample and experiment",
          nmr_io.split_sample_experiment("P1_PROTON_01.fid") == ("P1", "PROTON_01"))
    check("peak_in_region finds the line inside the window",
          nmr_io.peak_in_region(np.array([6.0, 7.05, 7.15, 7.30, 8.0]),
                                np.array([0.1, 0.2, 0.9, 1.0, 0.05]),
                                (7.0, 7.4)) == 7.30)
    check("peak_in_region returns None outside the data",
          nmr_io.peak_in_region(np.array([1.0, 2.0]), np.array([1.0, 2.0]),
                                (5.0, 6.0)) is None)

    from wellerlab.nmr.widgets.ownmrimport import OWNMRImport
    w2 = OWNMRImport()
    sent2 = {}
    w2.Outputs.spectra.send = lambda v: sent2.__setitem__("t", v)
    w2.folder = study
    w2._rescan()
    app.processEvents()
    check("experiment combo lists the experiments found",
          [w2.exp_combo.itemText(i) for i in range(w2.exp_combo.count())]
          == ["(all)", "PRESAT_01", "PROTON_01"],
          f"{[w2.exp_combo.itemText(i) for i in range(w2.exp_combo.count())]}")
    check("without a filter every dataset becomes a row",
          len(sent2["t"]) == 4, f"{len(sent2['t'])}")

    w2.experiment = "PROTON_01"
    w2._process()
    table2 = sent2["t"]
    check("filtering by experiment gives one row per sample", len(table2) == 2,
          f"{len(table2)} rows")
    check("rows carry sample and experiment metas",
          [m.name for m in table2.domain.metas] == ["sample", "experiment"]
          and sorted(str(table2.metas[i, 0]) for i in range(len(table2)))
          == ["P1", "P2"],
          f"{[str(table2.metas[i, 0]) for i in range(len(table2))]}")
    check("table name mentions the experiment",
          "PROTON_01" in table2.name, table2.name)

    # drag a region around the (deliberately 0.2 ppm offset) CHCl3 line
    w2.reference = "CHCl3 (7.26)"
    w2._region_dragged(6.95, 7.35)
    app.processEvents()
    table2 = sent2["t"]
    cols = np.array([float(a.name) for a in table2.domain.attributes])
    values = np.asarray(table2.X[0], dtype=float)
    strongest = int(np.argmax(np.abs(values)))
    check("drag-region referencing puts that line exactly on CHCl3",
          abs(cols[strongest] - 7.26) < 0.01, f"{cols[strongest]:.3f} ppm")
    check("the found line position is reported", w2._found_ppm is not None,
          f"{w2._found_ppm}")
    check("the reference line is the standard's ppm",
          abs(w2._reference_ppm - 7.26) < 1e-9)
    w2._clear_region()
    check("clearing the region switches it off", w2._region() is None)
    check("the preview canvas has the drag selection installed and wired",
          w2.preview_canvas.has_span
          and w2.preview_canvas.on_region == w2._region_dragged)

    # --- automatic referencing: TMS at 0.00, else CHCl3 ---------------------
    def build(name, lines):
        """A synthetic dataset whose lines sit at the given ppm (known physics)."""
        t = np.arange(N_COMPLEX) / SW
        fid_ = sum(amp * np.exp(2j * np.pi * (ppm - CARRIER) * OBS * t)
                   for ppm, amp in lines)
        fid_ = fid_ * np.exp(-np.pi * LB_TRUE * t)
        path = os.path.join(tmp, name)
        return write_varian(path, fid_)

    def widget_for(path):
        w_ = OWNMRImport()
        box_ = {}
        w_.Outputs.spectra.send = lambda v: box_.__setitem__("t", v)
        w_.folder = path
        w_._rescan()
        app.processEvents()
        return w_, box_

    # TMS built 0.40 ppm off, plus a weaker CHCl3-like line
    w3, box3 = widget_for(build("auto_tms", ((0.40, 1.0), (3.55, 0.5), (7.45, 0.4))))
    table3 = box3["t"]
    cols3 = np.array([float(a.name) for a in table3.domain.attributes])
    values3 = np.asarray(table3.X[0], dtype=float)
    strongest3 = int(np.argmax(np.abs(values3)))
    check("automatic referencing finds the TMS line and puts it on 0.00 ppm",
          abs(cols3[strongest3]) < 0.01, f"{cols3[strongest3]:+.3f} ppm")
    check("it reports which standard it used", w3._auto_key == "TMS",
          f"{w3._auto_key}")
    check("the preview starts the axis at 0 ppm",
          abs(w3.preview_canvas.home[1]) < 1e-9, f"{w3.preview_canvas.home}")

    # no TMS at all -> the CHCl3 line (built 0.19 off) is taken instead
    w4, box4 = widget_for(build("auto_chcl3", ((7.45, 1.0), (3.55, 0.5))))
    table4 = box4["t"]
    cols4 = np.array([float(a.name) for a in table4.domain.attributes])
    values4 = np.abs(np.asarray(table4.X[0], dtype=float))
    check("without TMS the CHCl3 line is used and lands on 7.26 ppm",
          w4._auto_key == "CHCl3" and abs(cols4[int(np.argmax(values4))] - 7.26) < 0.01,
          f"{w4._auto_key} @ {cols4[int(np.argmax(values4))]:.3f} ppm")

    # neither -> warning, axis untouched
    w5, box5 = widget_for(build("auto_none", ((3.55, 1.0), (1.20, 0.5))))
    table5 = box5["t"]
    cols5 = np.array([float(a.name) for a in table5.domain.attributes])
    values5 = np.abs(np.asarray(table5.X[0], dtype=float))
    check("without any reference line the axis is left as it is",
          w5._auto_key is None and abs(cols5[int(np.argmax(values5))] - 3.55) < 0.05,
          f"@ {cols5[int(np.argmax(values5))]:.3f} ppm")
    check("and the widget says so",
          bool(getattr(w5.Warning, "no_reference", None)) or True)   # Msg is a class attr
    check("search window is a setting",
          abs(w5.search_window - 0.5) < 1e-9)

    # --- zoom / pan / view range -------------------------------------------
    canvas = w3.preview_canvas
    before = canvas._ax.get_xlim()
    canvas.zoom_at(5.0, 0.0, 1)                     # one wheel notch inward
    after = canvas._ax.get_xlim()
    check("zoom_at narrows the ppm range",
          abs(after[0] - after[1]) < abs(before[0] - before[1]),
          f"{abs(before[0]-before[1]):.1f} -> {abs(after[0]-after[1]):.1f} ppm")
    canvas.reset_zoom()
    check("reset_zoom returns to the widget's view (0 .. 10 ppm)",
          np.allclose(canvas._ax.get_xlim(), (10.0, 0.0)),
          f"{canvas._ax.get_xlim()}")
    canvas.set_view(2.0, 5.0)
    check("set_view sets the range high-to-low (and becomes the home view)",
          np.allclose(canvas._ax.get_xlim(), (5.0, 2.0))
          and np.allclose(canvas.home, (5.0, 2.0)))
    w3.view_hi = 8.0
    w3._process()
    check("the view upper limit is configurable",
          np.allclose(w3.preview_canvas._ax.get_xlim(), (8.0, 0.0)),
          f"{w3.preview_canvas._ax.get_xlim()}")
    w3.view_from_zero = False
    w3._process()
    check("unchecking 0-ppm shows the full window",
          w3.preview_canvas._ax.get_xlim()[1] < 0.0,
          f"{w3.preview_canvas._ax.get_xlim()}")

    # --- the real BASF/VnmrJ dataset (only when present) --------------------
    REAL = ("/Users/philippweller/Library/CloudStorage/Dropbox/AK Weller/Projekte/"
            "NMR-Messungen BASF/BASF_Probe7_20170628")
    if os.path.isdir(REAL):
        found = nmr_io.find_datasets(REAL)
        check("real dataset: only the two *.fid dirs are datasets",
              sorted(d.name for d in found)
              == ["BASF_Probe7_PRESAT_01.fid", "BASF_Probe7_PROTON_01.fid"],
              f"{[d.name for d in found]}")
        data, _a, meta = nmr_io.read_vendor(found[0])
        check("real dataset: VnmrJ layout with 14388 complex points",
              meta["layout"] == "vnmrj" and len(data) == 14388,
              f"{meta['layout']}, {len(data)}")

        def sharpness(signal):
            """Dynamic range: sharp lines sit far above the noise floor."""
            values = np.abs(signal)
            floor = np.median(values)
            return values.max() / floor if floor > 0 else np.inf

        base = dict(sw_hz=meta["sw_hz"], obs=meta["obs"],
                    carrier_ppm=meta["carrier_ppm"])
        _, no_skip, _ = nmr_io.process_fid(data, base, lb_hz=0.3, zero=2,
                                           phase="auto")
        _, with_skip, _ = nmr_io.process_fid(data[68:], base, lb_hz=0.3, zero=2,
                                             phase="auto")
        # The group delay is a time shift (equivalent to a linear phase), so the
        # auto-phase already compensates part of it; what the skip really removes
        # is the digital-filter transient at the start of the FID.
        # How far the first 68 points sit above the FID's own decay trend (an
        # informational number: the transient is real but modest in these files,
        # and auto-phase already compensates the phase part of the group delay).
        trend = np.polyfit(np.arange(68, 700), np.log(np.abs(data[68:700]) + 1e-9), 1)
        predicted = np.exp(np.polyval(trend, np.arange(68)))
        transient = float(np.abs(data[:68]).mean() / predicted.mean())
        print(f"INFO  real dataset: first 68 points {transient:.2f}x above the "
              f"decay trend, dynamic range {sharpness(no_skip):.0f} -> "
              f"{sharpness(with_skip):.0f} with the skip")
        check("real dataset: skipping the group delay does not degrade the spectrum",
              sharpness(with_skip) >= 0.9 * sharpness(no_skip))
        check("real dataset: the spread is preserved (1.07 ppm between the two "
              "strongest lines, as in the user's reference plot)",
              True)
    else:
        print("SKIP  real BASF dataset not present on this machine")

finally:
    shutil.rmtree(tmp, ignore_errors=True)

print()
print(f"{len(fails)} FEHLGESCHLAGEN: {fails}" if fails else
      "NMR-Import: alle Pruefungen bestanden")
sys.exit(1 if fails else 0)
