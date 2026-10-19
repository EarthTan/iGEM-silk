> English translation of [round05_report.md](round05_report.md). The Chinese original is kept unchanged as the source of truth.

# Round 5: OmegaFold 3D Structure Prediction Report

## Scope

| Channel | Count | Screening criterion |
|------|------|---------|
| Top channel | 150 | highest SoDoPE+TemStaPro composite score |
| Bottom channel | 100 | highest SoDoPE+TemStaPro composite score |
| **Total** | **250** | no position restriction (N/C/Both), highest score first |

## Results

Runtime: 02:04 → 08:12 (6.13h)

| Item | Value |
|------|------|
| To predict | 250 |
| Succeeded | **250/250 (100%)** |
| Failed | 0 |
| Total time | 22,082s (368.0 min ≈ 6.13h) |
| Throughput | ~0.68 cons/min (90s/cons) |

### pLDDT distribution

| Metric | Value |
|------|------|
| Mean | 0.4205 |
| Min | 0.3742 |
| Max | 0.4950 |

## Analysis

1. **100% success rate**: all 250 constructs successfully produced a PDB + pLDDT score
2. **pLDDT range 0.37-0.50**: consistent with the expected behavior of OmegaFold on silk fusion proteins (~0.41 as recorded in CLAUDE.md), better than ESMFold (<0.30)
3. **6.13h total time**: within the 8h limit ✅, actual throughput matching the estimate (90s/cons)
4. **Limited pLDDT discriminating power**: the spread is only 0.12 (0.37-0.50), giving moderate ranking resolution across 250 candidates

## Follow-up

The Round 5 output serves as input to Round 6 (SASA + Aggrescan3D).
