"""
ProtTrans embedding generation using ProtT5-XL (T5EncoderModel).

Adapted from TemStaPro's prottrans_models.py (MIT license).
Generates per-protein mean embeddings (1024-dim) for thermostability prediction.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

# ProtT5-XL 下载到服务目录下的 models/prot_t5_xl/，而非系统缓存
_PROTT5_XL_MODEL_ID = "Rostlab/prot_t5_xl_half_uniref50-enc"


def _preprocess_sequence(seq: str) -> str:
    """Replace rare AAs, insert spaces between residues for T5 tokenizer."""
    seq = re.sub(r"[UZOB]", "X", seq)
    return " ".join(list(seq))


def _seq_hash(seq: str) -> str:
    """SHA-256 hex digest of a cleaned sequence string."""
    return hashlib.sha256(seq.encode()).hexdigest()


def _default_model_dir() -> Path:
    """models/prot_t5_xl/ 相对于本文件所在目录 (tools/TemStaPro/)。"""
    return Path(__file__).parent / "models" / "prot_t5_xl"


def load_prottrans(
    model_dir: str | None = None,
    on_status: Any | None = None,
) -> tuple[Any, Any]:
    """加载 ProtT5-XL 编码器和分词器。

    优先使用 model_dir 指定的路径（或环境变量 PROTTRANS_MODEL_DIR），
    否则默认下载到 tools/TemStaPro/models/prot_t5_xl/。

    若默认目录不存在，自动从 HuggingFace Hub 下载。
    on_status 可选回调，接收 dict 报告当前状态。
    """
    import torch
    from transformers import T5EncoderModel, T5Tokenizer

    if model_dir is None:
        model_dir = os.environ.get("PROTTRANS_MODEL_DIR", "")
    if not model_dir:
        model_dir = str(_default_model_dir())

    target = Path(model_dir)

    # 检查本地目录是否已有模型；没有则下载
    if _model_files_exist(target):
        _report(on_status, {"status": "local", "path": str(target), "size": _dir_size_str(target)})
    else:
        _report(on_status, {"status": "downloading", "detail": "从 HuggingFace Hub 获取…"})
        _download_prott5xl(target)
        _report(on_status, {"status": "local", "path": str(target), "size": _dir_size_str(target)})

    tokenizer = T5Tokenizer.from_pretrained(model_dir, do_lower_case=False)
    model = T5EncoderModel.from_pretrained(model_dir)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = model.to(device)
    model = model.eval()

    return model, tokenizer


def _report(callback: Any | None, data: dict) -> None:
    if callback:
        callback(data)


def _dir_size_str(path: Path) -> str:
    """人类可读的目录大小。"""
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    if total >= 1 << 30:
        return f"{total / (1 << 30):.1f} GB"
    return f"{total / (1 << 20):.0f} MB"


def _model_files_exist(model_dir: Path) -> bool:
    """检查目录中是否包含 ProtT5-XL 模型文件。"""
    return model_dir.is_dir() and (model_dir / "config.json").exists()


def _download_prott5xl(target_dir: Path) -> None:
    """从 HuggingFace Hub 下载 ProtT5-XL 到 target_dir。"""
    from huggingface_hub import snapshot_download

    print(f"[prottrans] 下载 ProtT5-XL 到 {target_dir} …")
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        _PROTT5_XL_MODEL_ID,
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,
    )
    print(f"[prottrans] 下载完成")


def generate_embeddings(
    model: Any,
    tokenizer: Any,
    sequences: list[str],
    device: torch.device,
    max_batch: int = 100,
    max_residues: int = 4000,
    max_seq_len: int = 2000,
) -> dict[str, torch.Tensor]:
    """Generate per-protein mean embeddings for a list of sequences.

    Batches sequences, sorts by length for efficient padding,
    and mean-pools the last hidden state over residues.

    Args:
        model: ProtT5EncoderModel (eval mode, on correct device).
        tokenizer: T5Tokenizer.
        sequences: List of amino acid sequences.
        device: torch device.
        max_batch: Max sequences per batch.
        max_residues: Max cumulative residues per batch.
        max_seq_len: Sequences longer than this are processed one-at-a-time.

    Returns:
        Dict mapping sequence → 1024-dim mean embedding tensor.
    """
    import torch

    if not sequences:
        return {}

    # Sort by length (descending) for efficient batching
    indexed = [(s, _preprocess_sequence(s)) for s in sequences]
    indexed.sort(key=lambda x: len(x[0]), reverse=True)

    results: dict[str, torch.Tensor] = {}
    batch: list[tuple[str, str]] = []
    batch_residues = 0

    def _process_batch(batch_items: list[tuple[str, str]]) -> None:
        nonlocal results
        seqs_in_batch = [item[1] for item in batch_items]
        orig_seqs = [item[0] for item in batch_items]

        ids = tokenizer(
            seqs_in_batch,
            add_special_tokens=True,
            padding=True,
            return_tensors="pt",
        ).to(device)

        with torch.no_grad():
            embedding_repr = model(
                input_ids=ids["input_ids"],
                attention_mask=ids["attention_mask"],
            )

        for i, orig_seq in enumerate(orig_seqs):
            seq_no_spaces = seqs_in_batch[i].replace(" ", "")
            s_len = len(seq_no_spaces)
            emb = embedding_repr.last_hidden_state[i, :s_len]
            # Mean pool over residues → (1024,)
            results[orig_seq] = emb.mean(dim=0).detach().cpu()

    for orig_seq, spaced_seq in indexed:
        seq_len = len(orig_seq)

        if seq_len > max_seq_len:
            # Process any accumulated batch first
            if batch:
                _process_batch(batch)
                batch = []
                batch_residues = 0
            # Long sequence: process alone
            _process_batch([(orig_seq, spaced_seq)])
            continue

        # Check if adding this sequence would exceed limits
        if (len(batch) >= max_batch or batch_residues + seq_len > max_residues):
            _process_batch(batch)
            batch = []
            batch_residues = 0

        batch.append((orig_seq, spaced_seq))
        batch_residues += seq_len

    # Process remaining batch
    if batch:
        _process_batch(batch)

    return results


def save_embeddings_cache(
    embeddings: dict[str, torch.Tensor], cache_dir: str
) -> None:
    """Save embeddings to disk keyed by SHA-256 sequence hash."""
    import torch
    os.makedirs(cache_dir, exist_ok=True)
    for seq, emb in embeddings.items():
        fname = f"{_seq_hash(seq)}.pt"
        torch.save({"sequence": seq, "mean_representations": emb.numpy()},
                   os.path.join(cache_dir, fname))


def load_embeddings_cache(
    sequences: list[str], cache_dir: str
) -> tuple[dict[str, torch.Tensor], list[str]]:
    """Load cached embeddings. Returns (loaded, missing) where missing
    is the list of sequences not found in cache."""
    import torch
    cached: dict[str, torch.Tensor] = {}
    missing: list[str] = []
    for seq in sequences:
        fpath = os.path.join(cache_dir, f"{_seq_hash(seq)}.pt")
        if os.path.exists(fpath):
            data = torch.load(fpath, map_location="cpu", weights_only=False)
            cached[seq] = torch.as_tensor(data["mean_representations"])
        else:
            missing.append(seq)
    return cached, missing
