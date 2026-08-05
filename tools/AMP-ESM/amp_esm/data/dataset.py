"""AMPDataset: FASTA → tokenize → optional mask, returning ESM-2 inputs."""
from __future__ import annotations

import torch
from torch.utils.data import Dataset
from transformers import PreTrainedTokenizerBase

from amp_esm.utils.fasta import FastaRecord
from amp_esm.utils.mask_augment import random_mask_inputs

DEFAULT_MAX_LEN: int = 200
DEFAULT_MASK_TOKEN_ID: int = 32
DEFAULT_AUGMENT_CFG: dict = {
    "mask_prob": 0.15,
    "mask_random_prob": 0.1,
    "mask_keep_prob": 0.1,
}


class AMPDataset(Dataset):
    """ESM-2 inputs for AMP classification.

    Args:
        records: list of cleaned FastaRecord.
        labels: list of int in {0, 1}, same length as records.
        tokenizer: PreTrainedTokenizerBase for ESM-2 (typically
            ``AutoTokenizer.from_pretrained("facebook/esm2_t33_650M_UR50D")``
            which returns an ``EsmTokenizer``).
        max_len: padding / truncation length.
        augment: apply random masking in __getitem__.
        augment_cfg: dict with mask_prob / mask_random_prob / mask_keep_prob.
        mask_token_id: ESM-2 mask token id (default 32).
    """

    def __init__(
        self,
        records: list[FastaRecord],
        labels: list[int],
        tokenizer: PreTrainedTokenizerBase,
        max_len: int = DEFAULT_MAX_LEN,
        augment: bool = False,
        augment_cfg: dict | None = None,
        mask_token_id: int = DEFAULT_MASK_TOKEN_ID,
    ) -> None:
        assert len(records) == len(labels), (
            f"records ({len(records)}) and labels ({len(labels)}) length mismatch"
        )
        self.records = records
        self.labels = labels
        self.tokenizer = tokenizer
        self.max_len = max_len
        self.augment = augment
        self.augment_cfg = {**DEFAULT_AUGMENT_CFG, **(augment_cfg or {})}
        self.mask_token_id = mask_token_id

        # Pre-tokenize all sequences once.
        self._input_ids: list[torch.Tensor] = []
        self._attention_mask: list[torch.Tensor] = []
        for rec in records:
            enc = tokenizer(
                rec.sequence,
                padding="max_length",
                max_length=max_len,
                truncation=True,
                return_tensors="pt",
            )
            self._input_ids.append(enc["input_ids"].squeeze(0))
            self._attention_mask.append(enc["attention_mask"].squeeze(0))

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        input_ids = self._input_ids[idx]
        attention_mask = self._attention_mask[idx]
        if self.augment:
            input_ids = random_mask_inputs(
                input_ids,
                attention_mask,
                mask_token_id=self.mask_token_id,
                **self.augment_cfg,
            )
        label = torch.tensor([float(self.labels[idx])], dtype=torch.float32)
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "labels": label,
        }
