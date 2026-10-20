---
name: Pipeline Stage Orchestration and Checkpoint Recovery v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [pipeline, orchestration, checkpoint, recovery, workflow]
validated: true
---

> **English** | [中文](gep-pipeline-stage-orchestration.zh.md)

# Gene Capsule: Pipeline Stage Orchestration and Checkpoint Recovery

## Experience

**Problem type**: Orchestration design for a multi-stage computational pipeline — each stage runs independently, supports interrupt recovery, and avoids redundant computation.

**Core strategy**:
1. **Independent script architecture**: Each stage is a self-contained Python script that does not depend on the in-memory state of preceding stages. Input is read from `output/`, output is written to `output/`
2. **Checkpoint mechanism**: Long-running stages (3D prediction) write a checkpoint JSON every N items processed, recording the IDs that completed successfully. On restart, completed items are skipped
3. **Output directory convention**: `output/stage<XX>_<name>/final/` holds the stage's final results, `output/stage<XX>_<name>/scores/` holds raw service responses. Each stage writes a README.md report
4. **STATUS.md global pointer**: Always points to the latest stage, the number passed, and key metrics. Makes it easy to quickly restore context
5. **Independently re-entrant**: Any stage can be rerun in place after a fix, reading input from the same directory and overwriting output

**Key parameters**:

| Element | Implementation | Example |
|------|----------|------|
| Checkpoint | JSON file + `completed_ids` set | `checkpoint.json: {"completed": ["con_0001", ...], "timestamp": "..."}` |
| Concurrency control | `asyncio.Semaphore(N)` | Structure prediction N=3, PDB scoring N=10 |
| Inter-stage transfer | CSV files | `stage4/final/top90.csv` → `stage5` → `stage6/final/all_ranked.csv` |
| State tracking | output/STATUS.md | Human-readable progress summary |

**Output directory structure**:
```
output/
├── STATUS.md                  ← global progress pointer
├── stage01_filter/final/      ← hard filtering results
│   ├── passed.csv
│   └── eliminated.csv
├── stage05_esmfold/           ← 3D prediction
│   ├── checkpoint.json        ← checkpoint
│   ├── pdb/                   ← PDB files
│   └── final/summary.csv      ← pLDDT summary
└── stage06_pdb_eval/final/    ← PDB evaluation
    └── all_ranked.csv
```

## Environment Fingerprint

- **Task domain**: Computational biology screening pipeline, multi-service/multi-step data processing
- **Input characteristics**: Large data volumes (thousands to tens of thousands of items), concurrent calls to multiple microservices, several hours of runtime
- **Constraints**: Interrupt recovery required (network outage, service crash, user intervention); each stage can run in a different session; incomplete stages do not block later ones
- **Not applicable**:
  - Real-time / low-latency tasks (checkpoint I/O overhead is high)
  - Simple single-step tasks (no need for multi-stage decomposition)
  - Tasks that strongly depend on shared in-memory state

## Audit Record

- **Validation method**: Complete 6-stage iGEM-silk run validation + ESMFold rerun recovery validation
- **Test cases**:
  1. The ESMFold stage ran 90 constructs and was interrupted midway → the checkpoint had saved what was completed; the rerun skipped the 45 already finished and ran only the remaining 45
  2. After Stage 2 scoring, the user asked to adjust the weights → only `stage02_score.py` was modified and rerun, triggering no other stage
  3. After fixing the ESMFold bug in Stage 5, rerun → cleared the PDB directory and reran, fully overwriting the old results
- **Success rate**: 100% (full 6-stage run + 2 partial reruns all normal)
- **Limitations**: The checkpoint records only the "completed" set, not the "in progress" state — items being processed at crash time are lost, which needs to be tolerated by the previous stage ("wastes at most one concurrency slot")

## Usage

- **Trigger conditions**: When designing a new computational pipeline; when an existing pipeline needs interrupt recovery
- **How to invoke**:
  1. One independent script per stage, with an `if __name__ == "__main__":` entry point
  2. Use a JSON checkpoint for long-running stages (write every N items or every time interval)
  3. At startup, `load_checkpoint()` → filter out completed inputs → process only the remainder
  4. After each item completes, `append_checkpoint()` appends a record
- **Caveats**: Checkpoints suit "idempotent" tasks (reruns produce identical results). If task results differ each time (random seeds, nondeterministic models), the checkpoint can only skip based on completed items and must not assume reruns are consistent
