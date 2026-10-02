"""Widget definitions for orangenmr (NMR Preprocessing)."""

from .ownmrbinning import OWBinning
from .ownmrnormalize import OWNormalization
from .ownmrbaseline import OWBaseline
from .ownmrfilter import OWFilter
from .ownmrexclude import OWExclusion
from .ownmrreference import OWReference

__all__ = [
    "OWBinning",
    "OWNormalization",
    "OWBaseline",
    "OWFilter",
    "OWExclusion",
    "OWReference",
]