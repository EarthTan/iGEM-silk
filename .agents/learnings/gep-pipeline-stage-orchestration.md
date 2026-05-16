---
name: 流水线阶段编排与检查点恢复 v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [pipeline, orchestration, checkpoint, recovery, workflow]
validated: true
---

# Gene Capsule: 流水线阶段编排与检查点恢复

## Experience

**问题类型**: 多阶段计算流水线的编排设计——每个阶段独立可运行、支持中断恢复、避免重复计算。

**核心策略**:
1. **独立脚本架构**：每个阶段是一个自包含的 Python 脚本，不依赖前序阶段的内存状态。输入从 `output/` 读取，输出写入 `output/`
2. **检查点 (checkpoint) 机制**：长时间运行的阶段（3D 预测）每处理 N 个条目写入一次 checkpoint JSON，记录已成功完成的 ID。重启时跳过已完成条目
3. **输出目录约定**：`output/stage<XX>_<name>/final/` 放阶段最终结果，`output/stage<XX>_<name>/scores/` 放原始服务响应。每个阶段写 README.md 报告
4. **STATUS.md 全局指针**：始终指向最新阶段、已通过数量、关键指标。便于快速恢复上下文
5. **独立可重入**：任何阶段修复后可原地重跑，读取同目录输入，覆盖输出

**关键参数**:

| 要素 | 实现方式 | 示例 |
|------|----------|------|
| 检查点 | JSON 文件 + `completed_ids` 集合 | `checkpoint.json: {"completed": ["con_0001", ...], "timestamp": "..."}` |
| 并发控制 | `asyncio.Semaphore(N)` | 结构预测 N=3，PDB 评分 N=10 |
| 阶段间传递 | CSV 文件 | `stage4/final/top90.csv` → `stage5` → `stage6/final/all_ranked.csv` |
| 状态追踪 | output/STATUS.md | 人工可读的进度摘要 |

**输出目录结构**:
```
output/
├── STATUS.md                  ← 全局进度指针
├── stage01_filter/final/      ← 硬过滤结果
│   ├── passed.csv
│   └── eliminated.csv
├── stage05_esmfold/           ← 3D 预测
│   ├── checkpoint.json        ← 检查点
│   ├── pdb/                   ← PDB 文件
│   └── final/summary.csv      ← pLDDT 汇总
└── stage06_pdb_eval/final/    ← PDB 评估
    └── all_ranked.csv
```

## Environment Fingerprint

- **任务域**: 计算生物学筛选流水线，多服务/多步骤数据处理
- **输入特征**: 大量数据（千-万级条目），多微服务并发调用，耗时数小时
- **约束条件**: 需要中断恢复（断网、服务崩溃、用户干预）；每个阶段可在不同会话中运行；未完成阶段不阻塞后续
- **不适用**:
  - 实时/低延迟任务（检查点 IO 开销大）
  - 单步骤简单任务（不需要多阶段分解）
  - 强依赖共享内存状态的任务

## Audit Record

- **验证方式**: iGEM-silk 6 阶段完整运行验证 + ESMFold 重跑恢复验证
- **测试用例**:
  1. ESMFold 阶段运行 90 construct，中途中断 → 检查点保存已完成，重跑跳过已完成的 45 个，只跑剩余 45 个
  2. 阶段二评分后用户要求调整权重 → 只修改 `stage02_score.py` 重跑，不触发其他阶段
  3. 阶段五修复 ESMFold bug 后重跑 → 清空 PDB 目录重跑，完全覆盖旧结果
- **成功率**: 100%（6 阶段全量运行 + 2 次部分重跑均正常）
- **局限性**: 检查点只记录"已完成"集合，不记录"处理中"状态——崩溃时正在处理的条目会丢失，需要上一阶段的容许（"最多浪费一个并发槽"）

## Usage

- **触发条件**: 设计新计算流水线时；现有流水线需要中断恢复能力时
- **调用方式**:
  1. 每阶段独立脚本，`if __name__ == "__main__":` 入口
  2. 长时间运行阶段用 JSON 检查点（每 N 条目或每时间间隔写入）
  3. 启动时 `load_checkpoint()` → 过滤已完成的输入 → 只处理剩余
  4. 每完成一个条目 `append_checkpoint()` 追加写入
- **注意事项**: 检查点适合"幂等"任务（重跑结果不变）。如果任务结果每次不同（随机种子、非确定性模型），检查点只能基于已完成条目跳过，不能假设重跑结果一致
