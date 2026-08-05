"""Evaluation metrics for AMP binary classification.

Implements the five metrics reported by design §9:
    - Accuracy
    - Sensitivity (recall on the positive class, AMP)
    - Specificity (recall on the negative class, non-AMP)
    - F1 score
    - ROC-AUC

All thresholded metrics accept a probability-like ``y_score`` and a
``threshold`` (default 0.5). ``roc_auc`` is threshold-independent and
therefore consumes the raw probabilities directly.

The five scalar metrics are thin wrappers around ``scikit-learn``
implementations (a dependency declared in design §12). The wrappers
exist so that:

1. The public API is uniform (every metric takes ``y_true`` and
   ``y_score``; the thresholded ones additionally take ``threshold``).
2. ``sensitivity`` and ``specificity`` are unambiguous: we never rely
   on ``recall_score(average='binary')`` (whose behaviour depends on
   which label is positive) — instead we always pass ``pos_label=1``
   or ``pos_label=0`` explicitly.
3. The ``compute_all_metrics`` helper returns a flat ``dict`` that
   the prediction / evaluation scripts can pass straight to
   ``pandas.DataFrame`` for tabular reporting.
"""
from __future__ import annotations

import math
from typing import Sequence

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    recall_score,
    roc_auc_score,
)


# ---------------------------------------------------------------------------
# Per-metric implementations
# ---------------------------------------------------------------------------


def accuracy(
    y_true: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray,
    threshold: float = 0.5,
) -> float:
    """Classification accuracy at ``threshold``.

    ``y_score`` may be probabilities or any real-valued scores; only the
    comparison against ``threshold`` matters.
    """
    y_true_arr = np.asarray(y_true).astype(int)
    y_pred = (np.asarray(y_score) >= threshold).astype(int)
    return float(accuracy_score(y_true_arr, y_pred))


def sensitivity(
    y_true: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray,
    threshold: float = 0.5,
) -> float:
    """Sensitivity = TP / (TP + FN), i.e. recall on the positive (AMP) class."""
    y_true_arr = np.asarray(y_true).astype(int)
    y_pred = (np.asarray(y_score) >= threshold).astype(int)
    # ``pos_label=1`` makes the intent explicit: AMP is the positive class.
    return float(
        recall_score(y_true_arr, y_pred, pos_label=1, zero_division=0)
    )


def specificity(
    y_true: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray,
    threshold: float = 0.5,
) -> float:
    """Specificity = TN / (TN + FP), i.e. recall on the negative (non-AMP) class."""
    y_true_arr = np.asarray(y_true).astype(int)
    y_pred = (np.asarray(y_score) >= threshold).astype(int)
    # ``pos_label=0`` flips recall: we now measure how many of the actual
    # non-AMP samples we recover. This is the only correct way to get
    # specificity from sklearn without writing the confusion matrix by hand.
    return float(
        recall_score(y_true_arr, y_pred, pos_label=0, zero_division=0)
    )


def f1(
    y_true: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray,
    threshold: float = 0.5,
) -> float:
    """F1 score of the positive (AMP) class at ``threshold``."""
    y_true_arr = np.asarray(y_true).astype(int)
    y_pred = (np.asarray(y_score) >= threshold).astype(int)
    return float(f1_score(y_true_arr, y_pred, zero_division=0))


def roc_auc(
    y_true: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray,
) -> float:
    """ROC-AUC using raw probability-like scores.

    Threshold-independent: do not threshold ``y_score`` before passing it
    in. ``roc_auc_score`` requires both classes to be present in
    ``y_true``; a ``ValueError`` is raised otherwise (we deliberately do
    not swallow it — degenerate test sets are a programming error).
    """
    y_true_arr = np.asarray(y_true).astype(int)
    y_score_arr = np.asarray(y_score).astype(float)
    return float(roc_auc_score(y_true_arr, y_score_arr))


# ---------------------------------------------------------------------------
# Convenience: compute every metric at once
# ---------------------------------------------------------------------------


def compute_all_metrics(
    y_true: Sequence[int] | np.ndarray,
    y_score: Sequence[float] | np.ndarray,
    threshold: float = 0.5,
) -> dict[str, float]:
    """Compute the five §9 metrics in a single call.

    Returns a dict with keys ``accuracy``, ``sensitivity``, ``specificity``,
    ``f1`` and ``roc_auc``. The dict is JSON-serialisable (every value is
    a Python ``float``) so it can be dropped straight into a logging
    payload, a ``pandas.DataFrame`` row, or a YAML report.
    """
    y_true_arr = np.asarray(y_true).astype(int)
    y_score_arr = np.asarray(y_score).astype(float)
    return {
        "accuracy": accuracy(y_true_arr, y_score_arr, threshold),
        "sensitivity": sensitivity(y_true_arr, y_score_arr, threshold),
        "specificity": specificity(y_true_arr, y_score_arr, threshold),
        "f1": f1(y_true_arr, y_score_arr, threshold),
        "roc_auc": roc_auc(y_true_arr, y_score_arr),
    }


# ---------------------------------------------------------------------------
# Helpers used by the prediction pipeline (design §8, §10.5)
# ---------------------------------------------------------------------------


def amply_score(prob: float) -> float:
    """Convert a probability to the AMPlify log-scaled score.

    Formula (matches the original ``src/AMPlify.py``):

        score = -10 * log10(1 - prob)

    The argument is clamped to ``1 - 1e-8`` to avoid ``log10(0)``. The
    score is monotonically increasing in ``prob`` and goes to ``+inf``
    as ``prob`` approaches 1, mirroring the original implementation.
    """
    p = min(float(prob), 1.0 - 1e-8)
    return -10.0 * math.log10(1.0 - p)


def proba_to_class_name(prob: float, threshold: float = 0.5) -> str:
    """Map a probability to a human-readable class label.

    Returns ``"AMP"`` when ``prob > threshold`` and ``"non-AMP"``
    otherwise. The strict ``>`` matches the original AMPlify CLI
    behaviour, where ``prob == threshold`` is treated as the negative
    class.
    """
    return "AMP" if float(prob) > threshold else "non-AMP"


__all__ = [
    "accuracy",
    "sensitivity",
    "specificity",
    "f1",
    "roc_auc",
    "compute_all_metrics",
    "amply_score",
    "proba_to_class_name",
]
