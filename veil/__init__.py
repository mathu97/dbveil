from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .config import Config
from .guard import check_query
from .pipeline import Pipeline, QueryOutcome

try:
    __version__ = version("dbveil")
except PackageNotFoundError:
    __version__ = "0.0.0+local"

__all__ = ["Config", "Pipeline", "QueryOutcome", "check_query", "__version__"]
