"""Command-line entry points (train / predict / evaluate).

Submodules are loaded lazily via ``__getattr__`` so that
``python -m amp_esm.scripts.predict`` does not trigger eager imports of
the (heavy) model / training code from ``train`` and ``evaluate``. This
keeps the CLI start-up time low and matches the convention used by
``pytorch_lightning``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["train", "predict", "evaluate"]


_LAZY_SUBMODULES = {"train", "predict", "evaluate"}


def __getattr__(name: str):
    """Lazily import a submodule on first attribute access.

    This avoids the ``RuntimeWarning: 'amp_esm.scripts.predict' found
    in sys.modules after import of package 'amp_esm.scripts'`` that
    Python's runpy emits when a parent package eagerly re-imports the
    module that ``python -m`` is about to run.
    """
    if name in _LAZY_SUBMODULES:
        from importlib import import_module

        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if TYPE_CHECKING:  # pragma: no cover - only for type checkers
    from amp_esm.scripts import evaluate, predict, train
