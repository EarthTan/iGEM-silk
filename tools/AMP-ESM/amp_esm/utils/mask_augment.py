"""Random amino acid masking (ESM-2 80/10/10 MLM strategy as augmentation)."""
from __future__ import annotations

import torch

# ESM-2 special token ids (roberta-style):
#   <cls>=0, <pad>=1, </s>=2, <unk>=3, <mask>=32 (for esm2_t33_650M_UR50D)
SPECIAL_TOKEN_IDS: frozenset[int] = frozenset({0, 1, 2, 3, 32})
ESM2_VOCAB_SIZE: int = 33  # esm2_t33_650M_UR50D alphabet size


def random_mask_inputs(
    input_ids: torch.Tensor,
    attention_mask: torch.Tensor,
    mask_token_id: int = 32,
    vocab_size: int = ESM2_VOCAB_SIZE,
    mask_prob: float = 0.15,
    mask_random_prob: float = 0.1,
    mask_keep_prob: float = 0.1,
    special_token_ids: frozenset[int] = SPECIAL_TOKEN_IDS,
) -> torch.Tensor:
    """Apply 80/10/10 MLM-style masking to input_ids (training only).

    Args:
        input_ids: LongTensor of shape (B, L). NOT modified.
        attention_mask: (B, L); 1 = real token, 0 = padding. Padding
            tokens are NEVER masked.
        mask_token_id: replacement for the 80% group (ESM-2 mask = 32).
        vocab_size: random replacement samples from [0, vocab_size).
        mask_prob: probability a non-special, non-padding token is
            selected for masking.
        mask_random_prob: among selected, fraction → random id.
        mask_keep_prob: among selected, fraction kept unchanged.
        special_token_ids: ids that are NEVER masked.

    Returns:
        New LongTensor with same shape as input_ids.
    """
    assert mask_random_prob + mask_keep_prob <= 1.0 + 1e-6, (
        f"mask_random_prob ({mask_random_prob}) + mask_keep_prob "
        f"({mask_keep_prob}) must be <= 1.0"
    )

    # Never mutate the caller's tensor.
    out = input_ids.clone()
    real = attention_mask.bool()

    # Build the "special token" mask via vectorized torch.isin.
    special_tensor = torch.tensor(
        list(special_token_ids), dtype=input_ids.dtype, device=input_ids.device
    )
    is_special = torch.isin(input_ids, special_tensor)

    # Candidate positions = real tokens that are also non-special.
    candidate = real & ~is_special

    if not candidate.any():
        return out

    # Bernoulli selection on candidates.
    selected = (
        torch.bernoulli(
            torch.full(candidate.shape, mask_prob, dtype=torch.float, device=input_ids.device)
        ).bool()
        & candidate
    )

    if not selected.any():
        return out

    # Bucket the selected positions into 80/10/10.
    rand = torch.rand(input_ids.shape, dtype=torch.float, device=input_ids.device)

    mask_rand_mask = selected & (rand < mask_random_prob)
    mask_keep_mask = (
        selected & (rand >= mask_random_prob) & (rand < mask_random_prob + mask_keep_prob)
    )
    mask_token_mask = selected & ~mask_rand_mask & ~mask_keep_mask

    # Apply the three replacements via torch.where.
    if mask_rand_mask.any():
        rand_tokens = torch.randint(
            0, vocab_size, input_ids.shape, dtype=input_ids.dtype, device=input_ids.device
        )
        out = torch.where(mask_rand_mask, rand_tokens, out)

    if mask_token_mask.any():
        out = torch.where(
            mask_token_mask,
            torch.tensor(mask_token_id, dtype=out.dtype, device=out.device),
            out,
        )

    # mask_keep_mask positions are left as-is (out already equals input_ids there).
    return out
