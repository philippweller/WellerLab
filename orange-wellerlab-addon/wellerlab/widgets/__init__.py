"""All WellerLab widgets — the single Orange entry point target.

Orange discovers the widget classes in a module's namespace, so aggregating the
four families here lets one category ("Weller Lab") hold every widget from this
one distribution.
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
