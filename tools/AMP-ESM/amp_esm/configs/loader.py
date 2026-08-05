"""Config loading helpers.

Thin wrapper around :func:`yaml.safe_load` so the rest of the codebase can
talk about a single function (``load_config``) without depending on
PyYAML directly.
"""
from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: str | Path) -> dict:
    """Load a YAML config file and return it as a nested ``dict``.

    Args:
        path: Filesystem path (or path-like) to a YAML document.

    Returns:
        The deserialised config. Nested mappings are returned as
        ``dict``s, sequences as ``list``s, and scalars as their
        corresponding Python primitives.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        yaml.YAMLError: If the document cannot be parsed.
    """
    p = Path(path)
    with open(p, "r") as f:
        return yaml.safe_load(f)


__all__ = ["load_config"]
