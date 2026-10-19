---
name: TemStaPro Prescreening to Reduce the GPU Bottleneck — CPU Prescreening Dilutes GPU Load v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [temstapro, bepipred3, gpu, prescreen, pipeline-optimization, bottleneck]
validated: true
---

> English translation of [gep-temstapro-prescreen-gpu-bottleneck.md](gep-temstapro-prescreen-gpu-bottleneck.md). The Chinese original is kept unchanged as the source of truth.

# Gene Capsule: TemStaPro Prescreening to Reduce the GPU Bottleneck

## Experience

**Problem description**: BepiPred3 (a GPU service) takes about 115s per batch of 50 sequences; running it over the full 50K dataset takes 50K÷50×115s ≈ 46h (including queueing time). GPU memory is limited (48GB), and BepiPred3 shares GPU resources with OmegaFold/AnOxPePred, so running it exclusively for days is impossible.

**Symptoms**:
- Full 50K run of BepiPred3 estimated at 46h, unacceptable
- Lowering concurrency (Semaphore=1) makes it even slower, and queued requests fail en masse due to the 300s timeout
- GPU memory contention prevents other GPU services (OmegaFold) from running at the same time

**Root cause**: BepiPred3's GPU inference is the bottleneck of the whole pipeline. GPU services are expensive and cannot scale horizontally (a single 48GB card), so feeding all data straight to the GPU wastes time — most low-scoring peptides would be discarded anyway after GPU scoring.

**Solution: CPU prescreening + Top-N strategy**

1. **Run TemStaPro (CPU, fast) over everything**: Score all 50K sequences first with TemStaPro (thermostability prediction, a CPU service, ~0.5s/item)
2. **Take the top 30% of each channel**: The Top channel takes the first 7,500 (30% of 25K), the Bottom channel takes the first 7,500 (30% of 25K), 15K in total
3. **Run BepiPred3 (GPU) on only 15K**: 15K ÷ 50 × 115s ≈ 9.5h, acceptable when run overnight with Semaphore=1

```python
# round03_heavy.py — TemStaPro prescreen logic
TEMSTAPRO_TOP_FRACTION = 0.30  # take the top 30% of each channel

# 1. run TemStaPro on the 50K dual-channel data (CPU, ~0.5s/item)
temstapro_results = await run_temstapro(all_50k)

# 2. sort each channel by TemStaPro and take the top 30%
channels = {"top": [], "bottom": []}
for row in all_50k:
    channels[row["channel"]].append(row)

for ch, rows in channels.items():
    rows.sort(key=lambda r: r.get("temstapro_score", 0), reverse=True)
    n_top = max(1, int(len(rows) * TEMSTAPRO_TOP_FRACTION))
    selected[ch] = rows[:n_top]

# 3. run BepiPred3 (GPU) only on the 15K subset
bepipred_input = selected["top"] + selected["bottom"]  # ~15K
bepipred_results = await run_bepipred3(bepipred_input)  # Semaphore=1, timeout=600s
```

**Effect**: BepiPred3 input goes from 50K → 15K (-70%), and GPU time from 46h → 9.5h. The extra CPU time added by TemStaPro is only ~7h (50K × 0.5s), and it can run in parallel with BepiPred3.

### Key Parameters

| Parameter | Value | Description |
|------|-----|------|
| TEMSTAPRO_TOP_FRACTION | 0.30 | Take the top 30% of each channel |
| TemStaPro throughput | ~2 seq/s | CPU single-threaded |
| BepiPred3 throughput | ~0.43 seq/s | GPU, batch=50 |
| GPU time saved | ~70% | 50K→15K |

### Environment Fingerprint

- **Task domain**: Multi-stage screening pipeline with mixed CPU/GPU services
- **Input characteristics**: Data volumes in the tens of thousands to hundreds of thousands; the GPU service is the bottleneck
- **Constraints**: Limited GPU memory (48GB); GPU services are slow and expensive
- **Trigger pattern**: Discovering that a GPU service (BepiPred3) takes far longer than the other CPU services
- **Not applicable**: A GPU service with sufficiently fast throughput (<1s/item); very small data volumes that can be run in full directly; services with no significant cost difference

### General Strategy

```
Bottleneck identification → analyze whether the bottleneck is CPU or GPU → if GPU:
  1. Find a faster CPU service to provide a correlated proxy score
  2. Rank with the CPU service and take the Top-N before the GPU service
  3. The CPU prescreen threshold should leave margin (30% rather than 10%) to avoid false eliminations
```

Here TemStaPro (thermostability) and BepiPred3 (B-cell epitopes) are not directly related functionally, but as a "general indicator of peptide quality" TemStaPro played a prescreening role — a peptide with poor thermostability has a very low probability of performing well in epitope prediction.

### Audit Record

- **Validation method**: stages2 production run; all 15K BepiPred3 jobs completed and the composite score was written successfully
- **Test cases**: Full 50K vs. 15K prescreen comparison — the proportion of high BepiPred3 scores within the 15K TemStaPro prescreen matches the full-data distribution
- **Success rate**: 100%
- **Limitations**: The score correlation between TemStaPro and BepiPred3 has not been rigorously validated. If they are later found to be orthogonal, prescreening could falsely eliminate peptides that score high on BepiPred3. It is recommended to validate the correlation with historical data in stages3.
