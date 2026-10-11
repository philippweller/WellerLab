"""Widget definitions for wellerlab.nmr (NMR Preprocessing)."""

from .ownmrbinning import OWBinning
from .ownmrnormalize import OWNormalization
from .ownmrbaseline import OWBaseline
from .ownmrfilter import OWFilter
from .ownmrexclude import OWExclusion
from .ownmrreference import OWReference
from .ownmrpeakfinding import OWPeakFinding
from .ownmrcalibration import OWCalibration
from .ownmrpeakmatch import OWPeakMatch

__all__ = [
    "OWBinning",
    "OWNormalization",
    "OWBaseline",
    "OWFilter",
    "OWExclusion",
    "OWReference",
    "OWPeakFinding",
    "OWCalibration",
    "OWPeakMatch",
]
