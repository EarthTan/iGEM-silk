> English translation of [README.md](README.md). The Chinese original is kept unchanged as the source of truth.

# Round 2: Antioxidant Split + Additional Scoring — Report

**Time**: 2026-05-17 17:15:48
**Duration**: 3755 seconds
**Input**: all 1,055,116 scored entries from Round 1
**Output directory**: output2/

## Split Strategy

Sorted from high to low by pure antioxidant activity (raw AnOxPePred score):
- **Top 25K**: the 25,000 entries with the best antioxidant activity
- **Bottom 25K**: the 25,000 entries with the worst antioxidant activity (negative controls)

> ⚠️ Note: the weighted composite score from Round 1 (which mixed in AlgPred2) was discarded,
> and the split uses the pure anoxpepred score instead.

## Additional Scoring

Three safety services were run on the 50K set:

| Service | Purpose | Concurrency | Top 25K valid | Bottom 25K valid |
|------|------|------|-------------|----------------|
| ToxinPred3 | toxicity, negative | 2 | 25,000 | 25,000 |
| HemoPI2 | hemolysis, negative | 10 | | |
| MHCflurry | MHC-I, negative | 10 | | |

## Antioxidant Activity Ranges

- **Top 25K**: 0.6046 ~ 0.4291
- **Bottom 25K**: 0.1576 ~ 0.2485

## Output

| File | Description |
|------|------|
| `final/all_50k.csv` | all 50K (top25K + bottom25K, with channel labels) → Round 3 input |
| `final/top25k.csv` | Top 25K only |
| `final/bottom25k.csv` | Bottom 25K only |
| `scores/*_results.json` | raw responses from each service |
