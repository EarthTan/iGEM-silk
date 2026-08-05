"""5-fold ensemble: checkpoint loading and inference-time averaging.

Design §8.2 specifies the canonical ensemble recipe:

    - Load all 5 fold checkpoints into :class:`AmplifyESM` instances.
    - Forward each model on the input batch.
    - Average the logits, then apply the sigmoid.

We expose two averaging strategies because the underlying
``ensemble_predict_logits`` ("average logits, then sigmoid") and
``ensemble_predict_proba`` ("average sigmoid probabilities") are
mathematically different operations:

    - Logit averaging corresponds to a Bayesian model average in log-
      space and is the design's default.
    - Probability averaging corresponds to a Bayesian model average in
      probability space and is sometimes preferred for thresholded
      downstream metrics.

Both helpers return a 1-D ``numpy.ndarray`` of shape ``(B,)`` to keep
the public interface uniform with the per-fold
``compute_all_metrics`` helper in ``amp_esm.evaluation.metrics``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from amp_esm.models.amplify_esm import AmplifyESM


def load_fold_checkpoints(
    ckpt_paths: list[Path | str],
    esm2_name: str = "facebook/esm2_t33_650M_UR50D",
    map_location: str | torch.device = "cpu",
    strict: bool = True,
) -> list[AmplifyESM]:
    """Load ``.ckpt`` files into a list of ``AmplifyESM`` in eval mode.

    Each model is constructed with the default :class:`AmplifyESM`
    hyperparameter set (matching the values used during training) and
    then has its state dict restored from the corresponding checkpoint.
    The ``esm2_name`` is forwarded to ``load_from_checkpoint`` so that
    the underlying ``ESM2Backbone`` is rebuilt with the same HuggingFace
    id used at training time.

    Args:
        ckpt_paths: One path per fold. Order is preserved.
        esm2_name: HuggingFace id used to rebuild the backbone. Should
            match the value used during training.
        map_location: Passed straight to ``load_from_checkpoint`` /
            ``torch.load`` so checkpoints can be restored on machines
            without a GPU.
        strict: Forwarded to :func:`torch.nn.Module.load_state_dict`;
            set to ``False`` only when deliberately loading partial
            weights for fine-tuning experiments.

    Returns:
        List of :class:`AmplifyESM` instances, each in ``eval()`` mode
        with gradients disabled via :func:`torch.no_grad` at the call
        sites in :func:`ensemble_predict_logits` /
        :func:`ensemble_predict_proba`.
    """
    models: list[AmplifyESM] = []
    for path in ckpt_paths:
        path = Path(path)
        model = AmplifyESM.load_from_checkpoint(
            str(path),
            esm2_name=esm2_name,
            map_location=map_location,
            strict=strict,
        )
        model.eval()
        models.append(model)
    return models


@torch.no_grad()
def ensemble_predict_logits(
    models: list[AmplifyESM],
    input_ids: torch.Tensor,
    attention_mask: torch.Tensor,
) -> np.ndarray:
    """Average logits across the ensemble, then return the mean.

    This is the design-§8.2 default: each fold produces a ``(B, 1)``
    logit tensor, we ``torch.stack`` them into ``(N, B, 1)``, take the
    mean over ``N`` and squeeze the trailing singleton dimension. The
    sigmoid is intentionally **not** applied here — callers decide
    whether to convert to a probability (e.g. via
    :func:`torch.sigmoid` / ``np``-side) or use the logit for an
    additional logit-based metric.

    Args:
        models: List of :class:`AmplifyESM` in eval mode (typically
            produced by :func:`load_fold_checkpoints`).
        input_ids: ``(B, L)`` token ids.
        attention_mask: ``(B, L)`` padding mask (1 = real, 0 = pad).

    Returns:
        ``numpy.ndarray`` of shape ``(B,)`` with averaged logits.
    """
    if not models:
        raise ValueError("ensemble_predict_logits: 'models' is empty")

    per_fold_logits: list[torch.Tensor] = []
    for model in models:
        logits = model(input_ids=input_ids, attention_mask=attention_mask)
        # ``logits`` is ``(B, 1)``; flatten to ``(B,)`` for stacking.
        per_fold_logits.append(logits.squeeze(-1))

    stacked = torch.stack(per_fold_logits, dim=0)  # (N, B)
    mean_logits = stacked.mean(dim=0)  # (B,)
    return mean_logits.detach().cpu().numpy()


@torch.no_grad()
def ensemble_predict_proba(
    models: list[AmplifyESM],
    input_ids: torch.Tensor,
    attention_mask: torch.Tensor,
) -> np.ndarray:
    """Average probabilities (post-sigmoid) across the ensemble.

    Each fold applies its own sigmoid, the resulting probabilities are
    averaged, and a single ``(B,)`` array is returned in ``[0, 1]``.

    Note:
        Averaging probabilities and averaging logits then applying
        sigmoid are **not** equivalent: logit averaging is the design's
        recommended default (see module docstring); this helper exists
        for callers that explicitly need the probability-space average
        (e.g. for thresholded metrics where prob-averaging is
        marginally friendlier numerically).

    Returns:
        ``numpy.ndarray`` of shape ``(B,)`` with averaged probabilities.
    """
    if not models:
        raise ValueError("ensemble_predict_proba: 'models' is empty")

    per_fold_probs: list[torch.Tensor] = []
    for model in models:
        logits = model(input_ids=input_ids, attention_mask=attention_mask)
        probs = torch.sigmoid(logits).squeeze(-1)
        per_fold_probs.append(probs)

    stacked = torch.stack(per_fold_probs, dim=0)  # (N, B)
    mean_probs = stacked.mean(dim=0)  # (B,)
    return mean_probs.detach().cpu().numpy()


__all__ = [
    "load_fold_checkpoints",
    "ensemble_predict_logits",
    "ensemble_predict_proba",
]
