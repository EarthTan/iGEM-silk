"""5-fold stratified ensemble training driver.

Reads the configured AMP / non-AMP FASTA files, builds a
``StratifiedKFold`` splitter, and trains each fold sequentially. One
``.ckpt`` is written per fold under the configured output directory, and
the list of best checkpoints is also serialised to
``out_dir/ensemble_ckpts.json`` so the prediction CLI can locate the
ensemble without globbing for ``fold-*.ckpt`` files.

Design references: §7.3 (5-fold sequential training, one ckpt per fold,
no nested parallelism) and §8 (inference-time ensemble over those 5
checkpoints).
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pytorch_lightning as pl

from amp_esm.configs.loader import load_config
from amp_esm.training.kfold import make_kfold
from amp_esm.training.train_one_fold import FoldConfig, train_one_fold
from amp_esm.utils.fasta import read_labeled_fasta


# Default non-AMP training file per mode. Resolved by :func:`main`; the
# AMP training file is shared across both modes.
DEFAULT_NON_AMP_TRAIN = {
    "balanced": "data/AMPlify_non_AMP_train_balanced.fa",
    "imbalanced": "data/AMPlify_non_AMP_train_imbalanced.fa",
}
DEFAULT_AMP_TRAIN = "data/AMPlify_AMP_train_common.fa"


@dataclass
class KFoldRunConfig:
    """Top-level configuration for the 5-fold training run.

    Combines a small amount of data-routing info (the AMP / non-AMP
    FASTA paths and the output directory) with the model + training
    hyperparameters consumed by :class:`FoldConfig`. Defaults match
    ``amp_esm/configs/default.yaml`` and the original AMPlify script.
    """

    # Data paths.
    amp_fa: str
    non_amp_fa: str
    out_dir: str
    # Model + training hyperparameters.
    esm2_name: str = "facebook/esm2_t33_650M_UR50D"
    max_len: int = 200
    batch_size: int = 16
    epochs: int = 5
    patience: int = 2
    lr_backbone: float = 1e-5
    lr_head: float = 1e-3
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    augment_cfg: dict = field(
        default_factory=lambda: {
            "mask_prob": 0.15,
            "mask_random_prob": 0.1,
            "mask_keep_prob": 0.1,
        }
    )
    augment: bool = True
    precision: str = "16-mixed"
    accelerator: str = "gpu"
    devices: int = 1
    num_workers: int = 0
    # Ensemble / split.
    n_folds: int = 5
    random_state: int = 50
    seed: int = 50
    # If True, skip folds whose ``fold-{N}-*.ckpt`` already exists in
    # ``out_dir`` and merge those ckpts into the final manifest. Useful
    # for resuming an interrupted 5-fold run.
    resume: bool = False


def _resolve_ckpt_paths(out_dir: Path) -> list[Path]:
    """Return the 5 fold checkpoints recorded by this run, if present.

    Looks for ``ensemble_ckpts.json`` first (the canonical list) and
    falls back to a glob over ``fold-*.ckpt``. Returns an empty list
    if neither is found.
    """
    manifest = out_dir / "ensemble_ckpts.json"
    if manifest.exists():
        with open(manifest, "r") as f:
            data = json.load(f)
        paths = [Path(p) for p in data.get("checkpoints", [])]
        if paths:
            return paths
    return sorted(out_dir.glob("fold-*.ckpt"))


def _detect_completed_folds(out_dir: Path, n_folds: int) -> set[int]:
    """Return the set of fold indices that already have a ckpt on disk.

    Used by ``run_kfold`` with ``resume=True`` to skip already-completed
    folds. For each fold index, picks the best (lowest val_loss) ckpt
    among any ``fold-{N}-*.ckpt`` files in ``out_dir``.
    """
    completed: set[int] = set()
    for fold_idx in range(n_folds):
        matches = list(out_dir.glob(f"fold-{fold_idx}-*.ckpt"))
        if matches:
            completed.add(fold_idx)
    return completed


def _best_ckpt_for_fold(out_dir: Path, fold_idx: int) -> Path | None:
    """Return the ckpt with the lowest val_loss for ``fold_idx``, if any."""
    matches = list(out_dir.glob(f"fold-{fold_idx}-*.ckpt"))
    if not matches:
        return None
    # Filename pattern: fold-{idx}-{epoch:02d}-{val_loss:.4f}.ckpt
    def parse_loss(p: Path) -> float:
        try:
            stem = p.stem  # 'fold-0-02-0.2101'
            return float(stem.rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            return float("inf")
    return min(matches, key=parse_loss)


def run_kfold(cfg: KFoldRunConfig) -> list[Path]:
    """Run 5-fold training. Returns list of best ckpt paths, one per fold.

    Each fold:

    1. Sets ``pl.seed_everything(cfg.seed + fold_idx)`` so that the
       per-fold seeds are deterministic but differ across folds.
    2. Materialises the train / val split for that fold and calls
       :func:`train_one_fold` with its own ``FoldConfig``.
    3. Records the best checkpoint path and the wall-clock duration of
       the fold.

    The list of best checkpoint paths is also serialised to
    ``out_dir/ensemble_ckpts.json`` for later consumption by the
    prediction CLI.
    """
    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load the labelled FASTA records. ``read_labeled_fasta`` skips
    # invalid entries (non-standard amino acids, length out of range,
    # empty id / sequence) with a UserWarning; the remaining records are
    # what the splitter operates on.
    amp_records, non_amp_records = read_labeled_fasta(cfg.amp_fa, cfg.non_amp_fa)
    records = amp_records + non_amp_records
    labels = [1] * len(amp_records) + [0] * len(non_amp_records)
    if not records:
        raise ValueError(
            f"run_kfold: no valid records loaded from {cfg.amp_fa!r} and "
            f"{cfg.non_amp_fa!r}"
        )

    splitter = make_kfold(
        records, labels, n_splits=cfg.n_folds, random_state=cfg.random_state
    )

    best_ckpts: list[Path] = []
    fold_durations: list[float] = []
    completed_folds: set[int] = set()
    t_start = time.time()

    # When resuming, pre-populate ``best_ckpts`` with the best existing
    # ckpt for each completed fold so that the final manifest has the
    # right ordering. The indices we skip below must match this.
    if cfg.resume:
        completed_folds = _detect_completed_folds(out_dir, cfg.n_folds)
        if completed_folds:
            print(
                f"[run_kfold] resume=True; found {len(completed_folds)}/"
                f"{cfg.n_folds} completed folds: {sorted(completed_folds)}",
                flush=True,
            )
            for fold_idx in sorted(completed_folds):
                ckpt = _best_ckpt_for_fold(out_dir, fold_idx)
                if ckpt is not None:
                    best_ckpts.append(ckpt)

    for fold_idx, (train_idx, val_idx) in enumerate(splitter.split(records, labels)):
        if fold_idx in completed_folds:
            print(
                f"[run_kfold] === Fold {fold_idx + 1}/{cfg.n_folds} === "
                f"resuming; ckpt already exists, skipping.",
                flush=True,
            )
            continue
        print(
            f"[run_kfold] === Fold {fold_idx + 1}/{cfg.n_folds} === "
            f"train={len(train_idx)} val={len(val_idx)} ===",
            flush=True,
        )
        # Per-fold seed: deterministic within a fold, but differs across
        # folds so the 5 ckpts end up exploring different parts of the
        # loss surface.
        pl.seed_everything(cfg.seed + fold_idx, workers=True)

        fold_cfg = FoldConfig(
            fold_idx=fold_idx,
            train_records=[records[i] for i in train_idx],
            train_labels=[labels[i] for i in train_idx],
            val_records=[records[i] for i in val_idx],
            val_labels=[labels[i] for i in val_idx],
            esm2_name=cfg.esm2_name,
            max_len=cfg.max_len,
            batch_size=cfg.batch_size,
            epochs=cfg.epochs,
            patience=cfg.patience,
            lr_backbone=cfg.lr_backbone,
            lr_head=cfg.lr_head,
            weight_decay=cfg.weight_decay,
            warmup_ratio=cfg.warmup_ratio,
            augment=cfg.augment,
            augment_cfg=cfg.augment_cfg,
            num_workers=cfg.num_workers,
            precision=cfg.precision,
            accelerator=cfg.accelerator,
            devices=cfg.devices,
            seed=cfg.seed + fold_idx,
        )
        fold_t0 = time.time()
        best_ckpt = train_one_fold(fold_cfg, ckpt_dir=out_dir)
        fold_dt = time.time() - fold_t0
        fold_durations.append(fold_dt)
        best_ckpts.append(Path(best_ckpt))
        print(
            f"[run_kfold] fold {fold_idx} done in {fold_dt:.1f}s; "
            f"best ckpt = {best_ckpt}",
            flush=True,
        )

    total_dt = time.time() - t_start

    # Persist the ensemble manifest so the prediction CLI can find the
    # 5 ckpts without guessing. After a ``--resume`` run, ``best_ckpts``
    # may already contain ckpts from the previous attempt; we keep them
    # and append newly trained ones.
    manifest = {
        "mode": cfg.amp_fa,  # placeholder, overridden by main() if known
        "esm2_name": cfg.esm2_name,
        "n_folds": cfg.n_folds,
        "random_state": cfg.random_state,
        "seed": cfg.seed,
        "checkpoints": [str(p) for p in best_ckpts],
        "fold_durations_sec": fold_durations,
        "total_duration_sec": total_dt,
    }
    with open(out_dir / "ensemble_ckpts.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(
        f"[run_kfold] {len(best_ckpts)} ckpts registered in manifest "
        f"(this session trained {len(fold_durations)} folds in {total_dt:.1f}s); "
        f"manifest -> {out_dir / 'ensemble_ckpts.json'}",
        flush=True,
    )
    return best_ckpts


def _build_argparser() -> argparse.ArgumentParser:
    """Construct the ``amp_esm_train`` CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Train the AMPlify-ESM2 5-fold ensemble. "
            "Sequentially trains StratifiedKFold(5) splits and writes one "
            ".ckpt per fold under the configured output directory."
        )
    )
    parser.add_argument(
        "--config",
        type=str,
        default="amp_esm/configs/default.yaml",
        help="YAML config file path (relative to repo root).",
    )
    parser.add_argument(
        "--amp-fa",
        type=str,
        default=None,
        help=(
            "Path to AMP training FASTA. Overrides config.data.train_amp_fa. "
            f"Defaults to {DEFAULT_AMP_TRAIN!r}."
        ),
    )
    parser.add_argument(
        "--non-amp-fa",
        type=str,
        default=None,
        help=(
            "Path to non-AMP training FASTA. Overrides config.data.train_non_amp_fa. "
            "When omitted, resolved from --mode (balanced/imbalanced)."
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default=None,
        help=(
            "Output directory for checkpoints. Defaults to "
            "models/amp_esm_<mode>_<timestamp>/."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["balanced", "imbalanced"],
        default="balanced",
        help="Which non-AMP training set to use (selects --non-amp-fa).",
    )
    parser.add_argument("--epochs", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--accelerator", type=str, default=None)
    parser.add_argument("--precision", type=str, default=None)
    parser.add_argument(
        "--no-augment",
        action="store_true",
        help="Disable random masking augmentation (default: enabled).",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help=(
            "Resume an interrupted run: scan ``--out-dir`` for "
            "``fold-{N}-*.ckpt`` files and skip those folds. Newly "
            "trained ckpts are appended to the same ``--out-dir``."
        ),
    )
    return parser


def main() -> None:
    """CLI entry point: ``amp_esm_train``."""
    parser = _build_argparser()
    args = parser.parse_args()

    # Load YAML config (may be missing in ad-hoc invocations, so fall back
    # to an empty dict).
    cfg_yaml: dict = {}
    try:
        cfg_yaml = load_config(args.config)
    except FileNotFoundError:
        print(
            f"[amp_esm_train] config not found at {args.config!r}; "
            "falling back to built-in defaults.",
            flush=True,
        )

    model_cfg = cfg_yaml.get("model", {})
    train_cfg = cfg_yaml.get("training", {})
    aug_cfg = cfg_yaml.get("augment", {})
    ens_cfg = cfg_yaml.get("ensemble", {})

    # Resolve FASTA paths: explicit CLI > config.data > mode-based default.
    data_cfg = cfg_yaml.get("data", {})
    amp_fa = (
        args.amp_fa
        or data_cfg.get("train_amp_fa")
        or DEFAULT_AMP_TRAIN
    )
    non_amp_fa = (
        args.non_amp_fa
        or data_cfg.get("train_non_amp_fa")
        or DEFAULT_NON_AMP_TRAIN[args.mode]
    )

    # Resolve output directory: explicit CLI > timestamped default.
    out_dir = args.out_dir
    if out_dir is None:
        ts = time.strftime("%Y%m%d%H%M%S")
        out_dir = f"models/amp_esm_{args.mode}_{ts}"

    # Build the KFoldRunConfig. CLI flags win over YAML.
    augment_cfg = {
        "mask_prob": aug_cfg.get("mask_prob", 0.15),
        "mask_random_prob": aug_cfg.get("mask_random_prob", 0.1),
        "mask_keep_prob": aug_cfg.get("mask_keep_prob", 0.1),
    }
    cfg = KFoldRunConfig(
        amp_fa=str(amp_fa),
        non_amp_fa=str(non_amp_fa),
        out_dir=str(out_dir),
        esm2_name=model_cfg.get("esm2_name", "facebook/esm2_t33_650M_UR50D"),
        max_len=int(model_cfg.get("max_len", 200)),
        batch_size=int(args.batch_size or train_cfg.get("batch_size", 16)),
        epochs=int(args.epochs or train_cfg.get("epochs", 5)),
        patience=int(train_cfg.get("patience", 2)),
        lr_backbone=float(train_cfg.get("lr_backbone", 1e-5)),
        lr_head=float(train_cfg.get("lr_head", 1e-3)),
        weight_decay=float(train_cfg.get("weight_decay", 0.01)),
        warmup_ratio=float(train_cfg.get("warmup_ratio", 0.1)),
        augment_cfg=augment_cfg,
        augment=bool(aug_cfg.get("enabled", True)) and not args.no_augment,
        precision=str(args.precision or train_cfg.get("precision", "16-mixed")),
        accelerator=str(args.accelerator or train_cfg.get("accelerator", "gpu")),
        devices=int(train_cfg.get("devices", 1)),
        num_workers=int(train_cfg.get("num_workers", 0)),
        n_folds=int(ens_cfg.get("n_folds", 5)),
        random_state=int(ens_cfg.get("random_state", 50)),
        seed=int(train_cfg.get("seed", 50)),
        resume=args.resume,
    )

    print(
        f"[amp_esm_train] mode={args.mode} amp_fa={cfg.amp_fa} "
        f"non_amp_fa={cfg.non_amp_fa} out_dir={cfg.out_dir} "
        f"epochs={cfg.epochs} batch_size={cfg.batch_size} "
        f"accelerator={cfg.accelerator} precision={cfg.precision} "
        f"augment={cfg.augment}",
        flush=True,
    )
    print(f"[amp_esm_train] KFoldRunConfig:\n{json.dumps(asdict(cfg), indent=2)}", flush=True)

    best_ckpts = run_kfold(cfg)
    print(
        f"[amp_esm_train] {len(best_ckpts)} checkpoints written under "
        f"{cfg.out_dir!r}:",
        flush=True,
    )
    for p in best_ckpts:
        print(f"  - {p}", flush=True)


__all__ = ["KFoldRunConfig", "run_kfold", "main"]
