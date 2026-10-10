"""All WellerLab widgets — the single Orange entry point target.

Orange discovers widgets by scanning the modules *directly inside* the
entry-point package. Our widgets live in four family subpackages
(``metabo/``, ``plsda/``, ``pca/``, ``nmr/``), so a plain package scan finds
nothing and the category would stay empty. We therefore provide the same
``widget_discovery`` hook that Orange's own ``Orange.widgets`` package uses:
the discovery calls it and we drive the four family packages explicitly into
one category.

The ``import *`` re-exports remain for programmatic access/tests.
"""
from ..metabo.widgets import *          # noqa: F401,F403
from ..plsda.widgets import *           # noqa: F401,F403
from ..pca.widgets import *             # noqa: F401,F403
from ..nmr.widgets import *             # noqa: F401,F403

from ..metabo.widgets import __all__ as _metabo
from ..plsda.widgets import __all__ as _plsda
from ..pca.widgets import __all__ as _pca
from ..nmr.widgets import __all__ as _nmr

__all__ = [*_metabo, *_plsda, *_pca, *_nmr]

#: Orange category shown in the widget toolbox
CATEGORY = "Weller Lab"

#: widget packages, in toolbox order
WIDGET_PACKAGES = (
    "wellerlab.metabo.widgets",
    "wellerlab.plsda.widgets",
    "wellerlab.pca.widgets",
    "wellerlab.nmr.widgets",
)


def widget_discovery(discovery):
    """Orange discovery hook (see ``Orange/widgets/__init__.py``).

    Called by Orange instead of the default package scan; registers every
    widget package into the single "Weller Lab" category.
    """
    from orangecanvas.registry import CategoryDescription

    # register the styled category FIRST: register_category ignores later
    # descriptions with the same name, so the styling must come before the
    # family packages register the category themselves
    discovery.handle_category(CategoryDescription(
        name=CATEGORY,
        priority=3000,
        background="#1F4E79",
        icon="icons/WellerLab.svg",
        package=__package__,
    ))
    for package in WIDGET_PACKAGES:
        discovery.process_category_package(package, name=CATEGORY)
