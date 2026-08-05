"""Inference and CLI entry point: ensemble prediction on new sequences."""
from __future__ import annotations

from amp_esm.prediction.inference import (
    DEFAULT_CKPT_ROOT,
    RESULT_FILENAME_TPL,
    main,
    predict_records,
    write_output,
)

__all__ = [
    "predict_records",
    "write_output",
    "main",
    "DEFAULT_CKPT_ROOT",
    "RESULT_FILENAME_TPL",
]
