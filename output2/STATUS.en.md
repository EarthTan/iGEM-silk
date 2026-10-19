> English translation of [STATUS.md](STATUS.md). The Chinese original is kept unchanged as the source of truth.

# output2 Pipeline Status

> Last updated: 2026-05-17 20:35

## Current Progress

| Stage | Status | Notes |
|------|------|------|
| Step 0: data integration | ✅ complete | 1,055,116 entries cleaned |
| Round 1: lightweight scoring | ✅ complete | AnOxPePred + AlgPred2, 886s |
| Round 2: split + safety scoring | ✅ complete | top25K+bottom25K, all 5 services, 3755s |
| Round 3: heavy-service scoring | ✅ complete | TemStaPro 50K + BepiPred3 15K, 7 services, 3891s |
| Round 4: enumeration + constructs | ✅ complete | 150 constructs (90 Top + 60 Bottom), all 5 services |
| Round 5: 3D structure | ✅ complete | OmegaFold 150/150, pLDDT avg=0.4105, 210min |
| Round 6: PDB evaluation | ✅ complete | SASA+A3D 150/150, SASA(0.40)+Agg(0.40)+pLDDT(0.20) |
| Round 7: final output | ✅ complete | 90 Top + 60 Bottom, dual-channel ranking, per-construct folders |

## Pipeline Change Log

Key v2 changes (vs the original stages2):
- Round 1 does not run ToxinPred3 (1.05 million entries would be too slow, ~22h); it is deferred to Round 2 on the 50K set
- Round 2 splits by pure anoxpepred into top25K + bottom25K, not a weighted composite score
- Round 3 runs on the 50K set and preserves the channel labels
- The whole pipeline is dual-channel (top/bottom), each producing its own final ranking

See `main/stages2/PLAN2.md` for details.

## Output Directory Structure

```
output2/
├── STATUS.md
├── step00_integrate/       ← data integration
│   └── final/cleaned.csv
├── round01_lightweight/    ← AnOxPePred + AlgPred2
│   └── final/
│       ├── all_scored.csv  ← full scoring of 1.05 million entries
│       └── top50k.csv      ← weighted-score ranking (for reference only)
├── round02_scoring/        ← split + safety scoring
│   └── final/
│       ├── all_50k.csv     ← 50K entries (5 service scores + composite score + channel)
│       ├── top25k.csv
│       └── bottom25k.csv
└── round03_heavy/          ← TemStaPro pre-screen + BepiPred3
    └── final/
        ├── all_scored.csv  ← 50K entries (7 service scores + channel)
        ├── top80.csv       ← top 80 of the Top channel
        ├── bottom10.csv    ← negative controls of the Bottom channel
        ├── danger_list.csv ← 201 high-risk peptides
        └── trajectory.csv  ← cross-round ranking trajectory
```
