> English translation of [round04_report.md](round04_report.md). The Chinese original is kept unchanged as the source of truth.

# Round 4 Construct Enumeration + Scoring Report

## Design decisions

| Decision | Conclusion |
|------|------|
| His-tag duplication | The LEHHHHHH already present in silk.fasta has been removed; build_full_sequence appends it only once |
| AnOxPePred | skipped — truncation to 30 aa makes the C/Both positions unreliable |
| Enumeration scale | all 4,324 peptides × 6 combos = 25,944 constructs |
| Phase 1 screening | SoDoPE+TemStaPro composite score top 10% |
| Phase 2 | BepiPred3 runs only on the Phase 1 subset |

## Phase 1: Enumeration + SoDoPE + TemStaPro

Runtime: 23:24 → 23:40 (15.9 min)

| Item | Value |
|------|------|
| Input peptides | 4,324 (116 Top + 4,208 Bottom) |
| Enumerated constructs | 25,944 (Top 696 + Bottom 25,248) |
| SoDoPE + TemStaPro scoring | 25,944 ✅ |
| Composite score range | 0.0012 – 0.7218 (avg ~0.53) |
| Filtered to top 10% | 2,594 constructs |
| His-tag | scaffold deduplicated: 364aa (originally 372aa) ✅ |

SoDoPE is extremely fast (<3s); TemStaPro's actual throughput on 400aa sequences is ~5.5 seq/s (much slower than 166/s).

## Phase 2: BepiPred3 supplementary scoring

Runtime: 00:01 → 01:46 (104.8 min)

| Item | Value |
|------|------|
| Input constructs | 2,594 (Phase 1 top 10%) |
| BATCH_SIZE | 50 |
| Actual time | 6,285s (104.8 min) — close to the estimated 1.7h |
| BepiPred3 scores | **2,594/2,594 ✅ (100%)** |
| Score range | 0.1206 – 0.1625 |
| Mean | 0.1472 |
| Standard deviation | **0.0053** (extremely low discriminating power) |

### BepiPred3 discriminating power analysis

BepiPred3's discriminating power at the construct level is extremely low (SD=0.0053), far below the peptide level in Round 3 (SD=0.042).
The main reason: about 90% of the 400aa full-length sequence is shared scaffold + linker, and only ~10% is functional peptide.
B-cell epitope prediction is driven mainly by the scaffold sequence, and differences between constructs are swamped.

Conclusion: **BepiPred3 at the construct level is of limited help for screening**, and later rounds should consider using the Round 3 peptide-level BepiPred3 scores.

## Position distribution (the 2,594 constructs passing Phase 1)

| Position | Count | Share |
|------|------|------|
| Both | 2,249 | 86.7% |
| C | 265 | 10.2% |
| N | 80 | 3.1% |

Because of the double copy of the functional peptide, the "Both" position is significantly better on SoDoPE (solubility) and TemStaPro (thermal stability).

## Channel distribution

| Channel | Count |
|------|------|
| Top | 10 |
| Bottom | 2,584 |

The Bottom channel accounts for the overwhelming majority — consistent with the Round 3 ranking (the Bottom channel's composite_score reaches as high as 0.948, above Top's 0.870).

## Key findings

1. **His-tag fix successful**: scaffold deduplicated + uniformly appended, no duplication
2. **TemStaPro is slower than expected on long sequences** (5.5/s vs 166/s), but Phase 1 as a whole still finished in 16 min
3. **BepiPred3 discriminating power at the construct level is extremely low** (SD=0.005), so later rounds may consider skipping construct-level BepiPred3
4. **The "Both" position performs best on SoDoPE+TemStaPro** (86.7% of Top 10%)
