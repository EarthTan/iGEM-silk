"""Stratified K-Fold splitting (preserved from original AMPlify)."""
from __future__ import annotations

from sklearn.model_selection import StratifiedKFold

from amp_esm.utils.fasta import FastaRecord


def make_kfold(
    records: list[FastaRecord],
    labels: list[int],
    n_splits: int = 5,
    random_state: int = 50,
) -> StratifiedKFold:
    """Return a configured StratifiedKFold splitter.

    Caller iterates splitter.split(records, labels) to obtain
    (train_indices, val_indices) for each fold.
    """
    assert len(records) == len(labels)
    return StratifiedKFold(
        n_splits=n_splits, shuffle=True, random_state=random_state,
    )
