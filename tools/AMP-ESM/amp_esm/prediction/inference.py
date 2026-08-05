"""Predict AMP probability for FASTA sequences using the 5-fold ensemble.

Mirrors the original AMPlify CLI surface::

    amp_esm_predict -m {balanced,imbalanced} -s SEQS \
                    [-od OUT_DIR] [-of {txt,tsv}] \
                    [-sub {on,off}] [-att {on,off}]

The implementation follows design §8 / §8.4:

* Tokenize the input sequences with the ESM-2 tokenizer.
* Run the 5 fold checkpoints, average logits, apply sigmoid to get the
  ensemble probability ``P_ens``.
* Compute the AMPlify log-scaled score ``-10 * log10(1 - P_ens)``.
* If ``-sub on``, also record each fold's individual probability.
* If ``-att on``, select the fold whose probability is closest to the
  ensemble mean and re-run that single model with
  ``return_attention=True`` to get per-residue context attention.

Invalid sequences (length out of range, non-standard amino acids) are
preserved in the output with ``NA`` placeholders so users can see which
inputs were rejected.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import time
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import torch
from Bio import SeqIO
from transformers import AutoTokenizer

from amp_esm.evaluation.metrics import amply_score, proba_to_class_name
from amp_esm.training.ensemble import (
    ensemble_predict_logits,
    load_fold_checkpoints,
)
from amp_esm.utils.fasta import FastaRecord, charge, read_fasta


# Default checkpoint root: <repo>/models/amp_esm_<mode>/
DEFAULT_CKPT_ROOT = Path("models") / "amp_esm_{mode}"

# Result filename template (matches original AMPlify output naming).
RESULT_FILENAME_TPL = "AMPlify_{mode}_results_{ts}.{ext}"


# ---------------------------------------------------------------------------
# DataFrame schema
# ---------------------------------------------------------------------------


# Columns always present, in the order required by the design (§8.4).
_BASE_COLUMNS: list[str] = [
    "Sequence_ID",
    "Sequence",
    "Length",
    "Charge",
    "Probability_score",
    "AMPlify_log_scaled_score",
    "Prediction",
]

# Per-sub-model probability columns. Always included as columns in the
# DataFrame; the writer decides whether to surface them.
_SUB_MODEL_COLUMNS: list[str] = [f"Sub_model_{i + 1}_probability_score" for i in range(5)]


def _empty_dataframe() -> pd.DataFrame:
    """Return a DataFrame with the canonical column set and no rows."""
    return pd.DataFrame(columns=_BASE_COLUMNS + _SUB_MODEL_COLUMNS + ["Attention"])


def _resolve_target_device(map_location: str | torch.device | None) -> str | None:
    """Normalise ``map_location`` into the device string used for the
    forward inputs.

    ``map_location`` is plumbed all the way to ``EsmForMaskedLM`` /
    ``load_from_checkpoint`` and is allowed to be a string like
    ``"cpu"``, ``"cuda"``, ``"cuda:0"``, or ``None``. For our input
    tensor placement we only care whether the model landed on a CUDA
    device, so we collapse everything else (including CPU and ``None``)
    to ``None`` meaning "stay on CPU".
    """
    if map_location is None:
        return None
    s = str(map_location)
    if s.startswith("cuda"):
        return s
    return None


# ---------------------------------------------------------------------------
# FASTA reading with explicit preservation of skipped records
# ---------------------------------------------------------------------------


def _read_all_raw_records(fasta_path: str | Path) -> list[FastaRecord]:
    """Read every FASTA record verbatim, without validation.

    The downstream ``read_fasta`` pipeline enforces length / alphabet
    rules and skips bad entries. We need a parallel pass that preserves
    *all* ids (even those that will be skipped) so users can see which
    sequences were rejected. Stop-codon ``*`` is still stripped because
    that's a syntax-level normalisation, not a content-level check.
    """
    p = Path(fasta_path)
    records: list[FastaRecord] = []
    with open(p, "r") as handle:
        for rec in SeqIO.parse(handle, "fasta"):
            raw_id = rec.id or ""
            raw_seq = str(rec.seq).upper().rstrip("*")
            if not raw_id or raw_id == "unknown":
                continue
            records.append(FastaRecord(seq_id=raw_id, sequence=raw_seq))
    return records


def _load_ensemble(
    ckpt_paths: list[Path],
    esm2_name: str,
    map_location: str | torch.device,
) -> list:
    """Load the fold checkpoints into :class:`AmplifyESM` instances."""
    return load_fold_checkpoints(
        ckpt_paths, esm2_name=esm2_name, map_location=map_location
    )


def _resolve_default_ckpt_paths(
    mode: str,
    ckpt_dir_override: str | None,
) -> list[Path]:
    """Locate the 5 fold checkpoints for ``mode``.

    Order of precedence:

    1. ``--ckpt-dir`` (explicit user override) — looks for
       ``ensemble_ckpts.json`` or ``fold-*.ckpt`` inside.
    2. ``models/amp_esm_<mode>/ensemble_ckpts.json``.
    3. ``models/amp_esm_<mode>/fold-*.ckpt``.

    Raises:
        FileNotFoundError: If no manifest / ckpt files can be found.
    """
    if ckpt_dir_override is not None:
        root = Path(ckpt_dir_override)
        return _gather_ckpt_paths(root)

    root = Path(str(DEFAULT_CKPT_ROOT).format(mode=mode))
    return _gather_ckpt_paths(root)


def _gather_ckpt_paths(root: Path) -> list[Path]:
    """Gather 5 fold checkpoints from a directory.

    Looks for ``ensemble_ckpts.json`` first (the canonical list written
    by :mod:`amp_esm.training.run_kfold`) and falls back to a glob over
    ``fold-*.ckpt`` files. Raises ``FileNotFoundError`` if neither path
    yields any checkpoints.
    """
    if not root.exists():
        raise FileNotFoundError(
            f"checkpoint directory not found: {root.resolve()}"
        )

    manifest = root / "ensemble_ckpts.json"
    if manifest.exists():
        with open(manifest, "r") as f:
            data = json.load(f)
        paths = [Path(p) for p in data.get("checkpoints", [])]
        if not paths:
            raise FileNotFoundError(
                f"{manifest} exists but does not list any checkpoints"
            )
        return paths

    paths = sorted(root.glob("fold-*.ckpt"))
    if not paths:
        raise FileNotFoundError(
            f"no fold-*.ckpt files found under {root.resolve()}"
        )
    return paths


# ---------------------------------------------------------------------------
# Core prediction
# ---------------------------------------------------------------------------


def predict_records(
    records: list[FastaRecord],
    ckpt_paths: list[Path | str],
    esm2_name: str = "facebook/esm2_t33_650M_UR50D",
    max_len: int = 200,
    batch_size: int = 16,
    map_location: str | torch.device = "cpu",
    return_attention: bool = False,
) -> pd.DataFrame:
    """Run ensemble prediction over a list of :class:`FastaRecord`.

    Returns a DataFrame with the canonical column set. Invalid
    sequences (those skipped by :func:`read_fasta`) are *not* present in
    ``records``; callers that want to surface them as ``NA`` rows should
    pass the raw, unfiltered record list and then merge with the result
    of :func:`read_fasta` (see :func:`main`).

    Args:
        records: Validated FastaRecords. Order is preserved in the
            output DataFrame.
        ckpt_paths: One path per fold (order does not matter for
            averaging, but it *does* determine which sub-model is
            reported under which ``Sub_model_N`` column).
        esm2_name: HuggingFace id of the ESM-2 backbone used to build
            the models.
        max_len: ESM-2 tokeniser truncation length.
        batch_size: Forward batch size.
        map_location: Passed to ``load_from_checkpoint`` so inference
            can run on CPU / GPU as needed.
        return_attention: If ``True``, the closest-matching fold is
            re-run with ``return_attention=True`` and per-residue
            attention is added to the output.

    Returns:
        A :class:`pandas.DataFrame`. When ``return_attention=False``,
        the ``Attention`` column is present but always ``NA`` (so the
        writer schema is uniform regardless of CLI flags).
    """
    df = _empty_dataframe()
    if not records:
        return df

    ckpt_paths = [Path(p) for p in ckpt_paths]
    models = _load_ensemble(ckpt_paths, esm2_name=esm2_name, map_location=map_location)
    tokenizer = AutoTokenizer.from_pretrained(esm2_name)

    # Tokenise once; use the same padding/truncation scheme as training.
    enc = tokenizer(
        [r.sequence for r in records],
        padding="max_length",
        max_length=max_len,
        truncation=True,
        return_tensors="pt",
    )
    input_ids = enc["input_ids"]
    attention_mask = enc["attention_mask"]

    # If the ensemble was loaded on a GPU device, move the input batch
    # to the same device; otherwise keep on CPU. Without this, ESM-2
    # embedding lookup raises "Expected all tensors to be on the same
    # device" when ``map_location='cuda*'``.
    target_device = _resolve_target_device(map_location)
    if target_device is not None:
        input_ids = input_ids.to(target_device)
        attention_mask = attention_mask.to(target_device)

    # 1. Ensemble probability (logit averaging -> sigmoid).
    # Forward one batch at a time so the ESM-2 3-D attention mask
    # (B, L, H) does not blow past VRAM for large inputs.
    n = input_ids.shape[0]
    mean_logits = np.empty(n, dtype=np.float32)
    sub_logits: list[np.ndarray] = [np.empty(n, dtype=np.float32) for _ in models]
    for start in range(0, n, batch_size):
        end = min(start + batch_size, n)
        ids_b = input_ids[start:end]
        mask_b = attention_mask[start:end]
        if target_device is not None:
            ids_b = ids_b.to(target_device)
            mask_b = mask_b.to(target_device)
        with torch.inference_mode():
            per_model_logits = []
            for model in models:
                logits = model(input_ids=ids_b, attention_mask=mask_b)
                per_model_logits.append(logits.squeeze(-1))
            stacked_logits = torch.stack(per_model_logits, dim=0)
            batch_logits = stacked_logits.mean(dim=0).detach().cpu().numpy()
        mean_logits[start:end] = batch_logits
        for j, logits in enumerate(per_model_logits):
            sub_logits[j][start:end] = logits.detach().cpu().numpy()
    probs_ens = 1.0 / (1.0 + np.exp(-mean_logits))
    sub_probs = [1.0 / (1.0 + np.exp(-sl)) for sl in sub_logits]

    # 3. Per-residue attention (optional): select the fold closest to
    # the ensemble mean and re-run that one model with return_attention.
    attention_per_record: list[list[float] | str] = ["NA"] * len(records)
    if return_attention and len(records) > 0:
        # ``stack`` produces shape ``(N_folds, B)`` so the abs-diff
        # against ``probs_ens`` selects one fold per sample.
        stacked = np.stack(sub_probs, axis=0)
        diffs = np.abs(stacked - probs_ens[None, :])
        closest = np.argmin(diffs, axis=0)  # (B,)
        # For each unique closest fold, run that model once on the
        # rows that picked it, then dispatch per-row results. We keep
        # an explicit ``local_index`` per sample so we don't have to
        # linear-scan ``sel`` with ``.index()`` for every row.
        unique_folds = sorted(set(int(c) for c in closest))
        attn_by_fold: dict[int, np.ndarray] = {}
        local_index = np.empty(len(records), dtype=np.int64)
        for fold_idx in unique_folds:
            sel = np.where(closest == fold_idx)[0]
            for local, sample_idx in enumerate(sel.tolist()):
                local_index[sample_idx] = local
            model = models[fold_idx]
            with torch.inference_mode():
                attn = model(
                    input_ids=input_ids[sel],
                    attention_mask=attention_mask[sel],
                    return_attention=True,
                )
            attn_np = attn.detach().cpu().numpy()  # (n_sel, L)
            # Zero out attention on padding positions.
            mask_np = attention_mask[sel].detach().cpu().numpy()  # (n_sel, L)
            attn_np = attn_np * mask_np
            attn_by_fold[fold_idx] = attn_np
        # Dispatch results per sample; truncate to the actual sequence
        # length (sum of the attention mask) and store as list of floats.
        for sample_idx, fold_idx in enumerate(closest):
            real_len = int(attention_mask[sample_idx].sum().item())
            attn_row = attn_by_fold[int(fold_idx)][int(local_index[sample_idx])][:real_len]
            attention_per_record[sample_idx] = [float(x) for x in attn_row]

    # 4. Build the DataFrame.
    rows: list[dict] = []
    for i, rec in enumerate(records):
        p = float(probs_ens[i])
        rows.append(
            {
                "Sequence_ID": rec.seq_id,
                "Sequence": rec.sequence,
                "Length": len(rec.sequence),
                "Charge": charge(rec.sequence),
                "Probability_score": p,
                "AMPlify_log_scaled_score": amply_score(p),
                "Prediction": proba_to_class_name(p),
                **{f"Sub_model_{j + 1}_probability_score": float(sub_probs[j][i]) for j in range(len(sub_probs))},
                "Attention": attention_per_record[i],
            }
        )
    return pd.DataFrame(rows, columns=_BASE_COLUMNS + _SUB_MODEL_COLUMNS + ["Attention"])


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def _format_attention(value) -> str:
    """Render an attention row for the TXT format.

    Lists are rendered as ``[a, b, c, ...]`` to mirror the original
    AMPlify; anything else (e.g. ``"NA"``) is passed through as a
    string.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple, np.ndarray)):
        return "[" + ", ".join(f"{float(x):.6f}" for x in value) + "]"
    return str(value)


def write_output(
    df: pd.DataFrame,
    out_dir: Path | str,
    out_format: str = "tsv",
    show_sub_model: bool = False,
    show_attention: bool = False,
    mode: str = "balanced",
) -> Path:
    """Write ``df`` to a timestamped file. Returns the output path.

    The filename follows the original AMPlify convention:
    ``AMPlify_<mode>_results_<YYYYMMDDHHMMSS>.<ext>``.

    For ``out_format='tsv'`` we always emit the canonical column set;
    the ``show_sub_model`` / ``show_attention`` flags are *display*
    hints (sub-model columns are kept in the DataFrame but the writer
    surfaces them only when requested). For ``out_format='txt'`` the
    per-record block format mirrors the original AMPlify CLI.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = time.strftime("%Y%m%d%H%M%S")
    ext = "tsv" if out_format == "tsv" else "txt"
    out_path = out_dir / RESULT_FILENAME_TPL.format(mode=mode, ts=ts, ext=ext)

    if out_format == "tsv":
        columns = list(_BASE_COLUMNS)
        if show_sub_model:
            columns += _SUB_MODEL_COLUMNS
        if show_attention:
            columns += ["Attention"]
        # Coerce dtypes so TSV is well-formed even when attention is
        # a list of floats (pandas would otherwise emit repr(list)).
        out_df = df[columns].copy()
        if "Attention" in out_df.columns:
            out_df["Attention"] = out_df["Attention"].apply(
                lambda v: (
                    "[" + ",".join(f"{x:.6f}" for x in v) + "]"
                    if isinstance(v, (list, tuple, np.ndarray))
                    else v
                )
            )
        out_df.to_csv(out_path, sep="\t", index=False)
        return out_path

    # TXT: one block per record, fields in fixed order.
    lines: list[str] = []
    for _, row in df.iterrows():
        lines.append(f"Sequence ID: {row['Sequence_ID']}")
        lines.append(f"Sequence: {row['Sequence']}")
        lines.append(f"Length: {row['Length']}")
        lines.append(f"Charge: {row['Charge']}")
        if show_sub_model:
            sub_vals = ", ".join(
                f"{float(row[col]):.6f}"
                for col in _SUB_MODEL_COLUMNS
            )
            lines.append(f"Sub-model probability scores: {sub_vals}")
        lines.append(f"Probability score: {float(row['Probability_score']):.6f}")
        lines.append(
            f"AMPlify_log_scaled_score: {float(row['AMPlify_log_scaled_score']):.6f}"
        )
        lines.append(f"Prediction: {row['Prediction']}")
        if show_attention:
            lines.append(f"Attention: {_format_attention(row['Attention'])}")
        lines.append("")  # blank line between records

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="amp_esm_predict",
        description="AMPlify-ESM2: predict antimicrobial peptides.",
        usage=(
            "amp_esm_predict [-h] -m {balanced,imbalanced} -s SEQS "
            "[-od OUT_DIR] [-of {txt,tsv}] [-sub {on,off}] [-att {on,off}]"
        ),
    )
    parser.add_argument(
        "-m", "--model",
        choices=["balanced", "imbalanced"],
        required=True,
        help="Which model's 5-fold ensemble to use.",
    )
    parser.add_argument(
        "-s", "--seqs",
        required=True,
        help="Path to a FASTA file with peptide sequences.",
    )
    parser.add_argument(
        "-od", "--out_dir",
        default=os.getcwd(),
        help="Output directory (default: current working directory).",
    )
    parser.add_argument(
        "-of", "--out_format",
        choices=["txt", "tsv"],
        default="tsv",
        help="Output format (default: tsv).",
    )
    parser.add_argument(
        "-sub", "--sub_model",
        choices=["on", "off"],
        default="off",
        help="Include per-sub-model probabilities (default: off).",
    )
    parser.add_argument(
        "-att", "--attention",
        choices=["on", "off"],
        default="off",
        help="Include per-residue attention weights (default: off).",
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
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda", "cuda:0"],
        help="Device to load checkpoints and run inference on (default: auto).",
    )
    parser.add_argument(
        "--esm2-name",
        type=str,
        default="facebook/esm2_t33_650M_UR50D",
        help="HuggingFace id of the ESM-2 backbone (default: 650M).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Forward batch size (default: 16).",
    )
    parser.add_argument(
        "--max-len",
        type=int,
        default=200,
        help="ESM-2 tokeniser truncation length (default: 200).",
    )
    return parser


def main() -> None:
    """CLI entry point: ``amp_esm_predict``."""
    parser = _build_argparser()
    args = parser.parse_args()

    device_arg = args.device
    if device_arg == "auto":
        device_arg = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[amp_esm_predict] device={device_arg}", flush=True)

    show_sub = args.sub_model == "on"
    show_att = args.attention == "on"

    # 1. Locate the 5 fold checkpoints.
    ckpt_paths = _resolve_default_ckpt_paths(args.model, args.ckpt_dir)
    print(
        f"[amp_esm_predict] mode={args.model} "
        f"loaded {len(ckpt_paths)} fold checkpoints:",
        flush=True,
    )
    for p in ckpt_paths:
        print(f"  - {p}", flush=True)

    # 2. Read every raw record (for the NA placeholder rows) and the
    # validated subset that actually goes through the model.
    raw_records = _read_all_raw_records(args.seqs)
    valid_records = list(read_fasta(args.seqs))
    print(
        f"[amp_esm_predict] {len(valid_records)} valid / "
        f"{len(raw_records)} raw records",
        flush=True,
    )

    # 3. Run ensemble inference on the valid records (if any).
    if valid_records:
        df_valid = predict_records(
            valid_records,
            ckpt_paths=ckpt_paths,
            esm2_name=args.esm2_name,
            max_len=args.max_len,
            batch_size=args.batch_size,
            map_location=device_arg,
            return_attention=show_att,
        )
    else:
        df_valid = _empty_dataframe()

    # 4. Build NA rows for the skipped records.
    valid_ids = {r.seq_id for r in valid_records}
    na_rows: list[dict] = []
    for r in raw_records:
        if r.seq_id in valid_ids:
            continue
        row = {
            "Sequence_ID": r.seq_id,
            "Sequence": r.sequence,
            "Length": len(r.sequence),
            "Charge": charge(r.sequence) if r.sequence else 0,
            "Probability_score": "NA",
            "AMPlify_log_scaled_score": "NA",
            "Prediction": "NA",
        }
        for col in _SUB_MODEL_COLUMNS:
            row[col] = "NA"
        row["Attention"] = "NA"
        na_rows.append(row)

    df = pd.concat([df_valid, pd.DataFrame(na_rows)], ignore_index=True)
    # Re-order columns to the canonical layout.
    df = df.reindex(columns=_BASE_COLUMNS + _SUB_MODEL_COLUMNS + ["Attention"])

    # 5. Write the output.
    out_path = write_output(
        df,
        out_dir=args.out_dir,
        out_format=args.out_format,
        show_sub_model=show_sub,
        show_attention=show_att,
        mode=args.model,
    )
    print(f"[amp_esm_predict] wrote {len(df)} rows -> {out_path}", flush=True)


__all__ = [
    "predict_records",
    "write_output",
    "main",
    "DEFAULT_CKPT_ROOT",
    "RESULT_FILENAME_TPL",
]
