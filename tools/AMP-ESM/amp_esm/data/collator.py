"""Collate function for AMPDataset outputs."""
from __future__ import annotations

import torch


def amplify_esm_collate(
    batch: list[dict[str, torch.Tensor]],
) -> dict[str, torch.Tensor]:
    """Stack dataset items into (B, L) tensors."""
    return {
        "input_ids": torch.stack([item["input_ids"] for item in batch], dim=0),
        "attention_mask": torch.stack(
            [item["attention_mask"] for item in batch], dim=0
        ),
        "labels": torch.stack([item["labels"] for item in batch], dim=0),
    }
