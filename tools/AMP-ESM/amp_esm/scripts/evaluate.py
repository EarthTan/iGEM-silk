"""Evaluate the 5-fold ensemble on the held-out test set.

Reports the five §9 metrics — accuracy, sensitivity, specificity, F1,
ROC-AUC — on the concatenated AMP / non-AMP test split.

Usage::

    amp_esm_eval -m balanced
    amp_esm_eval -m imbalanced --ckpt-dir /path/to/ckpts
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer

from amp_esm.evaluation.metrics import compute_all_metrics
from amp_esm.training.ensemble import (
    ensemble_predict_logits,
    load_fold_checkpoints,
)
from amp_esm.utils.fasta import FastaRecord, read_labeled_fasta


# Default test-set paths. The AMP test file is shared across modes; the
# non-AMP test file is selected by ``--mode``.
DEFAULT_TEST_AMP = "data/AMPlify_AMP_test_common.fa"
DEFAULT_TEST_NON_AMP = {
    "balanced": "data/AMPlify_non_AMP_test_balanced.fa",
    "imbalanced": "data/AMPlify_non_AMP_test_imbalanced.fa",
}
DEFAULT_CKPT_ROOT = Path("models") / "amp_esm_{mode}"


def _resolve_ckpt_paths(mode: str, ckpt_dir_override: str | None) -> list[Path]:
    """Locate the 5 fold checkpoints (mirrors ``inference.py``)."""
    root = (
        Path(ckpt_dir_override)
        if ckpt_dir_override is not None
        else Path(str(DEFAULT_CKPT_ROOT).format(mode=mode))
    )
    if not root.exists():
        raise FileNotFoundError(f"checkpoint directory not found: {root.resolve()}")

    manifest = root / "ensemble_ckpts.json"
    if manifest.exists():
        with open(manifest, "r") as f:
            data = json.load(f)
        paths = [Path(p) for p in data.get("checkpoints", [])]
        if paths:
            return paths

    paths = sorted(root.glob("fold-*.ckpt"))
    if not paths:
        raise FileNotFoundError(
            f"no fold-*.ckpt files (and no ensemble_ckpts.json) under {root.resolve()}"
        )
    return paths


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amp_esm_eval",
        description=(
            "Evaluate the AMPlify-ESM2 5-fold ensemble on the held-out test "
            "set (5 metrics: accuracy, sensitivity, specificity, F1, ROC-AUC)."
        ),
    )
    parser.add_argument(
        "-m", "--model",
        choices=["balanced", "imbalanced"],
        default="balanced",
        help="Which model's 5-fold ensemble to evaluate (default: balanced).",
    )
    parser.add_argument(
        "--ckpt-dir",
        type=str,
        default=None,
        help=(
            "Override default checkpoint directory. By default, looks for "
            "models/amp_esm_<model>/ensemble_ckpts.json or "
            "models/amp_esm_<model>/fold-*.ckpt"
        ),
    )
    parser.add_argument(
        "--amp-test-fa",
        type=str,
        default=None,
        help=f"AMP test FASTA (default: {DEFAULT_TEST_AMP!r}).",
    )
    parser.add_argument(
        "--non-amp-test-fa",
        type=str,
        default=None,
        help=(
            "non-AMP test FASTA. Defaults to "
            f"{DEFAULT_TEST_NON_AMP['balanced']!r} for balanced mode and "
            f"{DEFAULT_TEST_NON_AMP['imbalanced']!r} for imbalanced mode."
        ),
    )
    parser.add_argument(
        "--esm2-name",
        type=str,
        default="facebook/esm2_t33_650M_UR50D",
        help="HuggingFace id of the ESM-2 backbone (default: 650M).",
    )
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--max-len", type=int, default=200)
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda", "cuda:0"],
        help="Device to load checkpoints and run inference on (default: auto).",
    )
    parser.add_argument(
        "--report-json",
        type=str,
        default=None,
        help="Optional path to also dump the metrics dict as JSON.",
    )
    return parser


def main() -> None:
    """CLI entry point: ``amp_esm_eval``."""
    parser = _build_argparser()
    args = parser.parse_args()

    # 1. Resolve FASTA paths.
    amp_fa = args.amp_test_fa or DEFAULT_TEST_AMP
    non_amp_fa = args.non_amp_test_fa or DEFAULT_TEST_NON_AMP[args.model]
    print(
        f"[amp_esm_eval] mode={args.model} amp_fa={amp_fa} "
        f"non_amp_fa={non_amp_fa}",
        flush=True,
    )

    # 2. Load checkpoints.
    ckpt_paths = _resolve_ckpt_paths(args.model, args.ckpt_dir)
    print(
        f"[amp_esm_eval] loaded {len(ckpt_paths)} fold checkpoints:",
        flush=True,
    )
    for p in ckpt_paths:
        print(f"  - {p}", flush=True)
    # Resolve device: auto → cuda if available else cpu.
    device_arg = args.device
    if device_arg == "auto":
        device_arg = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[amp_esm_eval] device={device_arg}", flush=True)

    models = load_fold_checkpoints(
        ckpt_paths, esm2_name=args.esm2_name, map_location=device_arg
    )
    if device_arg.startswith("cuda"):
        models = [m.to(device_arg) for m in models]

    # 3. Load test records.
    amp_records, non_amp_records = read_labeled_fasta(amp_fa, non_amp_fa)
    records: list[FastaRecord] = amp_records + non_amp_records
    labels: list[int] = [1] * len(amp_records) + [0] * len(non_amp_records)
    if not records:
        raise ValueError(
            f"amp_esm_eval: no valid test records loaded from {amp_fa!r} "
            f"and {non_amp_fa!r}"
        )
    print(
        f"[amp_esm_eval] {len(amp_records)} AMP / {len(non_amp_records)} "
        f"non-AMP test records",
        flush=True,
    )

    # 4. Tokenise once and run ensemble inference in batches.
    tokenizer = AutoTokenizer.from_pretrained(args.esm2_name)
    enc = tokenizer(
        [r.sequence for r in records],
        padding="max_length",
        max_length=args.max_len,
        truncation=True,
        return_tensors="pt",
    )
    input_ids = enc["input_ids"]
    attention_mask = enc["attention_mask"]
    if device_arg.startswith("cuda"):
        input_ids = input_ids.to(device_arg)
        attention_mask = attention_mask.to(device_arg)

    mean_logits: list[np.ndarray] = []
    t0 = time.time()
    with torch.inference_mode():
        for start in range(0, len(records), args.batch_size):
            end = min(start + args.batch_size, len(records))
            batch_logits = ensemble_predict_logits(
                models,
                input_ids=input_ids[start:end],
                attention_mask=attention_mask[start:end],
            )
            mean_logits.append(batch_logits)
    probs = 1.0 / (1.0 + np.exp(-np.concatenate(mean_logits, axis=0)))
    print(
        f"[amp_esm_eval] ensemble inference done in {time.time() - t0:.1f}s",
        flush=True,
    )

    # 5. Metrics.
    metrics = compute_all_metrics(np.asarray(labels), probs)
    print(
        "[amp_esm_eval] metrics: "
        + ", ".join(f"{k}={v:.4f}" for k, v in metrics.items()),
        flush=True,
    )

    if args.report_json is not None:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(
                {
                    "mode": args.model,
                    "n_amp": len(amp_records),
                    "n_non_amp": len(non_amp_records),
                    "esm2_name": args.esm2_name,
                    "max_len": args.max_len,
                    "metrics": metrics,
                },
                f,
                indent=2,
            )
        print(f"[amp_esm_eval] wrote JSON report -> {report_path}", flush=True)


__all__ = ["main"]


if __name__ == "__main__":
    main()
