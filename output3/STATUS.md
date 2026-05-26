# Stages3 Pipeline 状态

> 最后更新: 2026-05-17 03:00

## 环境

| 项目 | 值 |
|------|-----|
| Python | 3.13.13 |
| DuckDB | 1.5.2 |
| CD-HIT | v4.8.1 |
| GPU | NVIDIA RTX 5880 Ada (49GB) |
| 磁盘 | 876G 可用 (估计) |
| DB 路径 | `output3/pipeline.db` (2.6G) |

## Pipeline 进展

| Step | 状态 | 输出 |
|------|------|------|
| **Step 0** | ✅ **完成** | 19,890,021 candidates, 98.7 min |
| **Step 1** | 🔄 **运行中** | AnOxPePred(抗氧化) + AlgPred2(过敏原排除) |
| Step 2 | ⏳ 待开始 | — |
| Step 3 | ⏳ 待开始 | — |
| Step 4 | ⏳ 待开始 | — |
| Step 5 | ⏳ 待开始 | — |
| Step 6 | ⏳ 待开始 | — |

## 候选池统计

| Source | 计数 |
|--------|------|
| uniprot | 733,573 |
| mgy | 19,156,448 |
| **合计** | **19,890,021** |

## Step 0 运行参数

```
命令: PYTHONUNBUFFERED=1 uv run python -m main.stages3.stage00_preprocess
DB:    output3/pipeline.db
筛选:  3-30 aa, 20 种标准氨基酸
写入:  VALUES 批处理 (10k/条SQL), BATCH_SIZE=100k
```
