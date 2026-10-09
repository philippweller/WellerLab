"""
wellerlab.plsda - PLS-DA and OPLS-DA for Orange3.

Kept deliberately minimal (same convention as orangemetabo/__init__.py): the
learners need Orange, the numerical core (`opls_core`, `plsda_learner` maths)
does not. Eager imports here would make `import wellerlab.plsda.opls_core` fail
outside Orange and break headless tests.
"""

__version__ = "0.2.0"

# Lazily resolved public names (PEP 562) - `from wellerlab.plsda import OPLSDALearner`
# still works, but importing the package no longer requires Orange.
_LAZY = {
    "PLSDALearner": (".plsda_learner", "PLSDALearner"),
    "PLSDAModel": (".plsda_learner", "PLSDAModel"),
    "OPLSDALearner": (".oplsda_learner", "OPLSDALearner"),
    "OPLSDAModel": (".oplsda_learner", "OPLSDAModel"),
}

__all__ = list(_LAZY)


def __getattr__(name):
    if name in _LAZY:
        import importlib
        module_name, attr = _LAZY[name]
        return getattr(importlib.import_module(module_name, __name__), attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
