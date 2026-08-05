"""FASTA parsing and validation utilities."""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from Bio import SeqIO

STANDARD_AA: frozenset[str] = frozenset("ACDEFGHIKLMNPQRSTVWY")
MIN_LEN: int = 3
MAX_LEN: int = 200


@dataclass(frozen=True)
class FastaRecord:
    """A single validated FASTA record (cleaned, no trailing '*')."""

    seq_id: str
    sequence: str

    @property
    def length(self) -> int:
        return len(self.sequence)


def read_fasta(path: str | Path) -> Iterator[FastaRecord]:
    """Yield FastaRecord, skipping invalid entries with a UserWarning.

    Validation:
    1. Empty sequence → skip.
    2. Strip a single trailing '*' (FASTA stop codon indicator).
    3. Length must be in [MIN_LEN, MAX_LEN].
    4. All chars must be in STANDARD_AA.
    """
    p = Path(path)
    # Use a context-managed file handle so Biopython closes the file
    # promptly. Without this, the generator holds the handle until the
    # caller exhausts it (and pytest reports ResourceWarning).
    with open(p, "r") as handle:
        records = list(SeqIO.parse(handle, "fasta"))
    for rec in records:
        raw_id = rec.id or ""
        if not raw_id or raw_id == "unknown":
            warnings.warn(
                f"read_fasta: skipping record with empty id", UserWarning, stacklevel=2
            )
            continue

        raw_seq = str(rec.seq).upper()
        # FASTA '*' is only used as a trailing stop-codon indicator; strip it
        # before length / alphabet validation.
        stripped = raw_seq.rstrip("*")
        if not stripped:
            warnings.warn(
                f"read_fasta: skipping record {raw_id!r} (empty after stripping '*')",
                UserWarning,
                stacklevel=2,
            )
            continue
        if len(stripped) < MIN_LEN or len(stripped) > MAX_LEN:
            warnings.warn(
                f"read_fasta: skipping record {raw_id!r} "
                f"(length {len(stripped)} outside [{MIN_LEN}, {MAX_LEN}])",
                UserWarning,
                stacklevel=2,
            )
            continue
        if any(c not in STANDARD_AA for c in stripped):
            warnings.warn(
                f"read_fasta: skipping record {raw_id!r} (non-standard amino acid)",
                UserWarning,
                stacklevel=2,
            )
            continue

        yield FastaRecord(seq_id=raw_id, sequence=stripped)


def read_labeled_fasta(
    amp_path: str | Path,
    non_amp_path: str | Path,
) -> tuple[list[FastaRecord], list[FastaRecord]]:
    """Read AMP (label=1) and non-AMP (label=0) FASTA files.

    Returns (amp_records, non_amp_records) as lists, materializing the
    underlying generator so downstream code can index and len() the results.
    """
    amp_records = list(read_fasta(amp_path))
    non_amp_records = list(read_fasta(non_amp_path))
    return amp_records, non_amp_records


def charge(sequence: str) -> int:
    """Peptide charge at pH ~7: +K, +R, -D, -E.

    Matches original AMPlify src/AMPlify.py implementation.
    """
    return (
        sequence.count("K")
        + sequence.count("R")
        - sequence.count("D")
        - sequence.count("E")
    )
