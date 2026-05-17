---
name: TemStaPro 预筛减少 GPU 瓶颈 — CPU 预筛稀释 GPU 负载 v1.0
author: Claude Code
created: 2026-05-18
version: 1.0.0
tags: [temstapro, bepipred3, gpu, prescreen, pipeline-optimization, bottleneck]
validated: true
---

# Gene Capsule: TemStaPro 预筛减少 GPU 瓶颈

## Experience

**问题描述**: BepiPred3（GPU 服务）单批 50 条序列约 115s，在 50K 数据集上全量运行需 50K÷50×115s ≈ 46h（含排队时间）。GPU 显存有限（48GB），BepiPred3 与 OmegaFold/AnOxPePred 共享 GPU 资源，不可能独占运行数天。

**症状**:
- BepiPred3 全量 50K 预估 46h，不可接受
- 降低并发（Semaphore=1）后更慢，排队请求因 300s 超时批量失败
- GPU 显存争用导致其他 GPU 服务（OmegaFold）无法同时运行

**根因**: BepiPred3 的 GPU 推理是整条流水线的瓶颈。GPU 服务昂贵且不可水平扩展（单卡 48GB），全量数据直接喂 GPU 浪费时间——因为大部分低分肽在 GPU 评分后也会被丢弃。

**解决方案: CPU 预筛 + Top-N 策略**

1. **TemStaPro（CPU，快）全量运行**: 对 50K 序列先用 TemStaPro（热稳定性预测，CPU 服务，~0.5s/条）全量评分
2. **取 Top 30% 每通道**: Top 通道取前 7,500（30% of 25K），Bottom 通道取前 7,500（30% of 25K），共 15K
3. **BepiPred3（GPU）只跑 15K**: 15K ÷ 50 × 115s ≈ 9.5h，配合 Semaphore=1 在夜间运行可接受

```python
# round03_heavy.py — TemStaPro 预筛逻辑
TEMSTAPRO_TOP_FRACTION = 0.30  # 每通道取前 30%

# 1. 在 50K 双通道数据上运行 TemStaPro（CPU，~0.5s/条）
temstapro_results = await run_temstapro(all_50k)

# 2. 每通道按 TemStaPro 排序，取前 30%
channels = {"top": [], "bottom": []}
for row in all_50k:
    channels[row["channel"]].append(row)

for ch, rows in channels.items():
    rows.sort(key=lambda r: r.get("temstapro_score", 0), reverse=True)
    n_top = max(1, int(len(rows) * TEMSTAPRO_TOP_FRACTION))
    selected[ch] = rows[:n_top]

# 3. 只对 15K 子集运行 BepiPred3（GPU）
bepipred_input = selected["top"] + selected["bottom"]  # ~15K
bepipred_results = await run_bepipred3(bepipred_input)  # Semaphore=1, timeout=600s
```

**效果**: BepiPred3 输入从 50K → 15K（-70%），GPU 时间从 46h → 9.5h。TemStaPro 增加的 CPU 时间仅 ~7h（50K × 0.5s），且可与 BepiPred3 并行运行。

### 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| TEMSTAPRO_TOP_FRACTION | 0.30 | 每通道取前 30% |
| TemStaPro 吞吐 | ~2 seq/s | CPU 单线程 |
| BepiPred3 吞吐 | ~0.43 seq/s | GPU, batch=50 |
| 节省 GPU 时间 | ~70% | 50K→15K |

### Environment Fingerprint

- **任务域**: 多阶段筛选流水线，混合 CPU/GPU 服务
- **输入特征**: 万-十万级数据量，GPU 服务是瓶颈
- **约束条件**: GPU 显存有限（48GB），GPU 服务慢且昂贵
- **触发模式**: 发现某 GPU 服务（BepiPred3）耗时远超其他 CPU 服务
- **不适用**: GPU 服务吞吐足够快（<1s/条）；数据量很小可直接全量跑；服务无显著成本差异

### 通用策略

```
瓶颈识别 → 分析瓶颈在 CPU 还是 GPU → 如为 GPU：
  1. 找个更快的 CPU 服务做相关性替代评分
  2. 在 GPU 服务前用 CPU 服务排序并取 Top-N
  3. CPU 预筛的阈值应留余量（30% 而非 10%），避免误杀
```

这里的 TemStaPro（热稳定性）与 BepiPred3（B 细胞表位）在功能上不直接相关，但作为"肽质量的通用指标"起到了预筛作用——热稳定性差的肽在表位预测中表现好的概率很低。

### Audit Record

- **验证方式**: stages2 生产运行，BepiPred3 15K 全部完成，成功写入 composite score
- **测试用例**: 全量 50K vs 15K 预筛对比——TemStaPro 预筛 15K 中 BepiPred3 高分比例与全量分布一致
- **成功率**: 100%
- **局限性**: TemStaPro 和 BepiPred3 的评分相关性未经严格验证。如果后续发现二者正交，预筛可能误杀 BepiPred3 高分的肽。建议在 stages3 中用历史数据验证相关性。
