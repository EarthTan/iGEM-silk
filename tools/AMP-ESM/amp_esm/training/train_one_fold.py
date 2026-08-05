"""Train a single fold of the 5-fold stratified ensemble.

This module is the per-fold entry point invoked by the stage-5 training
script. It builds the train / val ``AMPDataset`` + ``DataLoader``
pipeline, constructs the :class:`~amp_esm.models.amplify_esm.AmplifyESM`
LightningModule, configures the ``Trainer`` with the project's standard
callbacks (``EarlyStopping`` + ``ModelCheckpoint``) and runs
``trainer.fit()``.

Implementation notes:

- Seeds are set via :func:`pytorch_lightning.seed_everything` with
  ``workers=True`` so that any per-worker randomness (e.g. augmentation)
  is also deterministic.
- The default accelerator is ``"gpu"`` and the default precision is
  ``"16-mixed"`` to match the design's ~25-30 GB VRAM budget. Both
  fields are exposed on :class:`FoldConfig` so callers (or stage-5) can
  fall back to ``"cpu"`` for unit tests or dry runs.
- ``EarlyStopping`` and ``ModelCheckpoint`` both monitor ``val_loss``
  with ``mode="min"`` and ``patience=cfg.patience`` /
  ``save_top_k=1`` respectively — exactly the configuration in §7.2.
- The function returns the best checkpoint path recorded by Lightning
  (``trainer.checkpoint_callback.best_model_path``); if early stopping
  never triggers a better epoch than the initial one, Lightning still
  populates this with the best model it observed.

Stage-5 (the CLI driver) is responsible for running an additional
``compute_all_metrics`` pass on the test set after all 5 folds are
trained; this module's job is strictly "train one fold and save one
``.ckpt``".
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytorch_lightning as pl
import torch
from pytorch_lightning.callbacks import EarlyStopping, ModelCheckpoint
from pytorch_lightning.loggers import CSVLogger
from torch.utils.data import DataLoader
from transformers import AutoTokenizer

from amp_esm.data.collator import amplify_esm_collate
from amp_esm.data.dataset import AMPDataset
from amp_esm.models.amplify_esm import AmplifyESM
from amp_esm.utils.fasta import FastaRecord


@dataclass
class FoldConfig:
    """Configuration for a single training fold.

    Attributes:
        fold_idx: Zero-based fold index (used for logging + checkpoint
            naming).
        train_records / train_labels: AMP/non-AMP training samples.
        val_records / val_labels: held-out validation samples for this
            fold.
        esm2_name: HuggingFace id of the ESM-2 backbone.
        max_len: Tokeniser truncation length.
        batch_size: Train/val batch size (same for both, matching the
            design's training script).
        epochs: Maximum number of epochs. EarlyStopping may stop sooner.
        patience: EarlyStopping patience (epochs without ``val_loss``
            improvement before stopping).
        lr_backbone: Learning rate for the ESM-2 parameter group.
        lr_head: Learning rate for the head parameter group
            (MHA + ContextAttn + classifier).
        weight_decay: AdamW weight decay.
        warmup_ratio: Fraction of total steps spent in linear warmup
            before cosine decay.
        augment: Whether to apply random-mask augmentation to the
            training set. Validation is always augmentation-free.
        augment_cfg: Optional override for ``mask_prob``,
            ``mask_random_prob`` and ``mask_keep_prob``.
        num_workers: ``DataLoader`` workers. ``0`` is the safest default
            (avoids tokenizer pickling issues across forks); production
            scripts may raise this.
        precision: Lightning precision flag (``"16-mixed"`` by default).
        accelerator: Lightning accelerator (``"gpu"`` by default).
        devices: Number of devices per node (``1`` by default).
        seed: Seed for :func:`pytorch_lightning.seed_everything`.
    """

    fold_idx: int
    train_records: list[FastaRecord]
    train_labels: list[int]
    val_records: list[FastaRecord]
    val_labels: list[int]
    esm2_name: str = "facebook/esm2_t33_650M_UR50D"
    max_len: int = 200
    batch_size: int = 16
    epochs: int = 5
    patience: int = 2
    lr_backbone: float = 1e-5
    lr_head: float = 1e-3
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    augment: bool = True
    augment_cfg: dict | None = None
    num_workers: int = 0
    precision: str = "16-mixed"
    accelerator: str = "gpu"
    devices: int = 1
    seed: int = 50


def _build_loaders(
    cfg: FoldConfig,
    tokenizer,
) -> tuple[DataLoader, DataLoader]:
    """Build train and validation DataLoaders for the fold."""
    train_ds = AMPDataset(
        records=cfg.train_records,
        labels=cfg.train_labels,
        tokenizer=tokenizer,
        max_len=cfg.max_len,
        augment=cfg.augment,
        augment_cfg=cfg.augment_cfg,
    )
    val_ds = AMPDataset(
        records=cfg.val_records,
        labels=cfg.val_labels,
        tokenizer=tokenizer,
        max_len=cfg.max_len,
        augment=False,
    )
    pin_memory = torch.cuda.is_available()
    train_loader = DataLoader(
        train_ds,
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=cfg.num_workers,
        collate_fn=amplify_esm_collate,
        pin_memory=pin_memory,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=cfg.batch_size,
        shuffle=False,
        num_workers=cfg.num_workers,
        collate_fn=amplify_esm_collate,
        pin_memory=pin_memory,
    )
    return train_loader, val_loader


def train_one_fold(cfg: FoldConfig, ckpt_dir: Path | str) -> Path:
    """Train one fold and return the path to the best checkpoint.

    The pipeline follows the seven steps sketched in the design:

    1. Set seeds via ``pl.seed_everything``.
    2. Load the ESM-2 tokenizer.
    3. Build train / val ``AMPDataset`` instances (train applies
       random-mask augmentation when ``cfg.augment`` is ``True``).
    4. Build ``DataLoader``s with the project's collator.
    5. Construct the ``AmplifyESM`` LightningModule.
    6. Configure ``Trainer`` with ``EarlyStopping`` and
       ``ModelCheckpoint`` callbacks monitoring ``val_loss``.
    7. Run ``trainer.fit()`` and return the best checkpoint path.
    """
    ckpt_dir = Path(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # 1. Determinism.
    pl.seed_everything(cfg.seed, workers=True)

    # 2. Tokenizer.
    tokenizer = AutoTokenizer.from_pretrained(cfg.esm2_name)

    # 3 + 4. Datasets and DataLoaders.
    train_loader, val_loader = _build_loaders(cfg, tokenizer)

    # 5. Model.
    model = AmplifyESM(
        esm2_name=cfg.esm2_name,
        max_len=cfg.max_len,
        lr_backbone=cfg.lr_backbone,
        lr_head=cfg.lr_head,
        weight_decay=cfg.weight_decay,
        warmup_ratio=cfg.warmup_ratio,
    )

    # 6. Callbacks. The metric keys must match what ``AmplifyESM._shared_step``
    # logs: ``f"{prefix}/loss"``. Lightning would raise ``RuntimeError:
    # Early stopping conditioned on metric val_loss which is not available``
    # if the names diverge.
    early_stopping = EarlyStopping(
        monitor="val/loss",
        mode="min",
        patience=cfg.patience,
        verbose=True,
    )
    checkpoint = ModelCheckpoint(
        monitor="val/loss",
        mode="min",
        save_top_k=1,
        filename=f"fold-{cfg.fold_idx}-{{epoch:02d}}-{{val/loss:.4f}}",
        dirpath=str(ckpt_dir),
        auto_insert_metric_name=False,
    )

    # CSVLogger writes per-epoch metrics (loss / acc / roc_auc) to
    # ckpt_dir/csv/fold-N/version_0/metrics.csv so the user can
    # ``tail -f`` the file during a long run and load the history
    # afterwards with pandas (``pd.read_csv``).
    csv_logger = CSVLogger(
        save_dir=str(ckpt_dir),
        name="csv",
        version=f"fold-{cfg.fold_idx}",
    )

    trainer_kwargs: dict[str, Any] = {
        "max_epochs": cfg.epochs,
        "precision": cfg.precision,
        "accelerator": cfg.accelerator,
        "devices": cfg.devices,
        "callbacks": [early_stopping, checkpoint],
        "log_every_n_steps": 10,
        "enable_progress_bar": True,
        "logger": csv_logger,
    }

    trainer = pl.Trainer(**trainer_kwargs)

    # 7. Fit.
    trainer.fit(
        model=model,
        train_dataloaders=train_loader,
        val_dataloaders=val_loader,
    )

    best_ckpt = Path(trainer.checkpoint_callback.best_model_path)
    return best_ckpt


__all__ = ["FoldConfig", "train_one_fold"]
