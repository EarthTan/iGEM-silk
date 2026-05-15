# Stages3 数据库方案

> 版本: v1.0 — 2026-05-15
> 数据库: DuckDB（嵌入列式数据库）
> 文件: `output3/pipeline.db`

---

## 一、为什么选择 DuckDB

经过对多种方案的评估，DuckDB 是 stages3 最合适的选择：

| 特性 | DuckDB | SQLite | PostgreSQL |
|------|--------|--------|------------|
| 部署方式 | 嵌入，无服务进程 | 嵌入，无服务进程 | 需要服务进程 |
| 文件格式 | 单文件 | 单文件 | 需要数据目录 |
| 并行查询 | ✅ 自动多线程 | ❌ 单线程 | ✅ 但需配置 |
| 列式存储 | ✅ 分析型查询快 | ❌ 行式存储 | ❌ 行式存储 |
| 内存模式 | ✅ 全内存或磁盘 | ❌ 仅磁盘 | ❌ 仅磁盘 |
| JSON 支持 | ✅ 原生 | ⚠️ 扩展 | ✅ |
| 安装 | pip install duckdb | 内置 | 需要 apt install |

**对比结论**: DuckDB 是专为数据分析场景设计的嵌入式数据库。对于 stages3 的使用场景——写入数千万行数据、做聚合分析（AVG, STDDEV, PERCENTILE）、导出为 CSV——DuckDB 的性能比 SQLite 快 10-100 倍，同时保持了单文件、零部署的简便性。

SQLite 虽然是 Python 自带的行式数据库，但它的设计目标（事务型 OLTP）与我们的使用场景（分析型 OLAP）完全不匹配。数千万行的聚合查询在 SQLite 上需要数分钟，在 DuckDB 上只需数秒。

---

## 二、表结构总览

整个 pipeline 使用同一个 DuckDB 文件，包含以下表：

```
pipeline.db
├── candidates          ← Stage 0 输出: 预处理后的候选肽段池
├── stage1_scores       ← Stage 1 输出: 轻量初筛的分数
├── stage1_passed       ← Stage 1 通过者（视图或物化表）
├── stage2_scores       ← Stage 2 输出: 全量评分结果
├── stage2_ranking      ← Stage 2 排名
├── constructs          ← Stage 3 输出: 构造枚举
├── construct_scores    ← Stage 3 分数: SoDoPE + TemStaPro
├── structure_jobs      ← Stage 4 状态: 结构预测任务跟踪
├── structure_results   ← Stage 4 输出: 结构预测结果
├── pdb_eval            ← Stage 5 输出: SASA + Aggrescan3D
├── final_ranking       ← Stage 6 输出: 最终排名
├── score_distribution  ← 全局: 所有分数分布统计
├── weight_config       ← 全局: 方差感知权重的赋值记录
└── checkpoint          ← 全局: 检查点 / 断点续跑状态
```

---

## 三、各表详细设计

### candidates（候选肽段池）

这是整个 pipeline 的核心基础表，其他所有表都引用它的 `candidate_id`。

| 列 | 类型 | 说明 |
|----|------|------|
| candidate_id | BIGINT | 自增主键 |
| source | VARCHAR | "uniprot" 或 "mgy" |
| source_id | VARCHAR | 原始 FASTA ID |
| header | VARCHAR | 完整的 FASTA header（用于追溯） |
| sequence | VARCHAR | 氨基酸序列 |
| length | SMALLINT | 长度 |
| is_standard_aa | BOOLEAN | 是否只含 20 种标准氨基酸 |
| cluster_id | VARCHAR | CD-HIT 簇 ID |
| cluster_rep | BOOLEAN | 是否是 CD-HIT 簇的代表序列 |

**索引**: (source, source_id) 唯一索引，避免重复导入。
**分区策略**: 按 source 分区（uniprot / mgy），可以针对不同数据源单独处理。

### stage1_scores（轻量初筛分数）

| 列 | 类型 | 说明 |
|----|------|------|
| candidate_id | BIGINT | 关联 candidates |
| anoxpepred_score | FLOAT | AnOxPePred 预测值 |
| anoxpepred_success | BOOLEAN | 调用是否成功 |
| algpred2_score | FLOAT | AlgPred2 预测值 |
| algpred2_success | BOOLEAN | 调用是否成功 |
| scored_at | TIMESTAMP | 评分时间 |

**用途**: 记录 Stage 1 的原始分数。即使候选肽在 AlgPred2 上被淘汰，也保留其 AnOxPePred 分数用于事后分析。

### stage1_passed（Stage 1 通过者）

| 列 | 类型 | 说明 |
|----|------|------|
| candidate_id | BIGINT | 主键，关联 candidates |
| anoxpepred_score | FLOAT | 保留用于 Stage 2 |
| passed_reason | VARCHAR | "passed" 或淘汰原因 |

**筛选条件**: AlgPred2 < 0.30（非过敏原）。AnOxPePred 不做硬阈值，留在 Stage 2 中用相对排名处理。

### stage2_scores（全量评分结果）

| 列 | 类型 | 说明 |
|----|------|------|
| candidate_id | BIGINT | 关联 candidates |
| anoxpepred_score | FLOAT | |
| bepipred3_score | FLOAT | |
| plm4cpps_score | FLOAT | |
| graphcpp_score | FLOAT | |
| temstapro_score | FLOAT | |
| sodope_score | FLOAT | |
| mhcflurry_score | FLOAT | |
| toxinpred3_score | FLOAT | 用于绝对排除 |
| hemopi2_score | FLOAT | 用于绝对排除 |
| ..._success | BOOLEAN | 各服务的成功标志（每个列对应一个 *_success 列） |
| scored_at | TIMESTAMP | |

这个表会有大量列（~20 列），这是合理的——DuckDB 的列式存储对这种宽表处理得很好。

### score_distribution（分数分布统计）

这个表不是运行的必需数据，而是做**方差感知权重**的核心输入。

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGINT | 自增主键 |
| stage_name | VARCHAR | "stage1" 或 "stage2" 或 "final" |
| service_name | VARCHAR | 服务名，如 "anoxpepred" |
| count | BIGINT | 有效样本数 |
| mean | FLOAT | 均值 |
| stddev | FLOAT | **标准差（核心指标）** |
| min | FLOAT | 最小值 |
| p01 | FLOAT | 第 1 百分位（去极端值） |
| p05 | FLOAT | 第 5 百分位 |
| p25 | FLOAT | 下四分位 |
| p50 | FLOAT | 中位数 |
| p75 | FLOAT | 上四分位 |
| p95 | FLOAT | 第 95 百分位 |
| p99 | FLOAT | 第 99 百分位 |
| max | FLOAT | 最大值 |
| winsorized_stddev | FLOAT | **截尾后的标准差（更稳健）** |
| computed_weight | FLOAT | 基于方差分配的权重 |
| computed_at | TIMESTAMP | |

**winsorized_stddev 的计算**: 去掉上下 1% 极端值后计算的标准差。这是为了避免个别离群值放大或缩小某个服务的感知区分度。

### weight_config（权重配置记录）

记录每个阶段的权重赋值过程，保证**可复现性**和**可审计性**。

| 列 | 类型 | 说明 |
|----|------|------|
| id | BIGINT | 自增主键 |
| stage_name | VARCHAR | "stage2" 或 "stage6" |
| total_candidates | BIGINT | 参与权重计算的候选数 |
| weight_formula | VARCHAR | 使用的公式: "stddev_normalized" 或 "winsorized_stddev_normalized" |
| weights | JSON | 各服务权重的完整 JSON |
| distribution_snapshot | JSON | 各服务分布统计的完整 JSON |
| created_at | TIMESTAMP | |

### constructs（构造枚举表）

| 列 | 类型 | 说明 |
|----|------|------|
| construct_id | BIGINT | 自增主键 |
| candidate_id | BIGINT | 关联 candidates |
| linker | VARCHAR | 连接子类型: "flexible" 或 "rigid" |
| position | VARCHAR | 融合位置: "N", "internal", "C" |
| scaffold_seq | VARCHAR | 丝蛋白骨架序列 |
| linker_seq | VARCHAR | 连接子序列 |
| peptide_seq | VARCHAR | 功能肽段序列 |
| full_sequence | VARCHAR | 完整 construct 氨基酸序列 |

### checkpoint（检查点表）

断点续跑的核心。

| 列 | 类型 | 说明 |
|----|------|------|
| stage | VARCHAR | 阶段名 |
| step | VARCHAR | 子步骤名 |
| status | VARCHAR | "running" / "done" / "failed" |
| total_items | BIGINT | 本步骤总处理数 |
| processed_items | BIGINT | 已处理数 |
| error_message | VARCHAR | 失败时的错误信息 |
| started_at | TIMESTAMP | |
| completed_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

---

## 四、检查点与断点续跑机制

### 设计原则

1. **幂等性**: 每个阶段的输出只取决于输入数据，不受之前运行的影响
2. **细粒度**: 每处理完一批（如 10 万条）就更新一次 checkpoint
3. **可审计**: checkpoint 表中记录了每个阶段的开始、结束和错误信息

### 恢复流程

```
检查点系统:

阶段开始时:
  checkpoint.upsert(stage="stage1", status="running", started_at=now())

恢复运行时:
  status = checkpoint.get("stage1")?.status
  if status == "done":
      skip → 进入 Stage 2
  elif status == "running":
      查询已处理的最大 candidate_id
      从断点处继续
  elif status is None 或 status == "failed":
      重新开始 Stage 1

阶段完成时:
  checkpoint.upsert(stage="stage1", status="done", completed_at=now())
```

---

## 五、读写接口范式

所有数据库操作通过统一的接口模块 `main/stages3/db.py` 访问，Pipeline 脚本不直接构造 SQL 查询。

推荐的自然语言风格接口（说明用途，不列代码）：

- **初始化数据库**: 创建 pipeline.db 文件，运行所有 CREATE TABLE 语句
- **写入候选肽池**: 批量插入候选人记录，自动去重
- **记录分数**: 批量写入 stage 分数表，按 candidate_id 关联
- **读取待处理候选**: 查询尚未完成当前阶段的候选名单
- **更新检查点**: 记录当前处理进度到 checkpoint 表
- **计算分布统计**: 运行针对指定表的聚合查询，返回标准差和各百分位数
- **计算权重**: 根据分布统计表，读取标准差，计算归一化权重
- **生成排名**: 将权重应用到分数表，计算加权综合得分，排序输出

---

## 六、性能与空间估算

### 存储空间

| 表 | 预估行数 | 预估大小 |
|----|---------|---------|
| candidates | 2000-6000 万 | ~2-6 GB |
| stage1_scores | 2000-6000 万 | ~3-9 GB |
| stage2_scores | 200-600 万（通过 Stage 1 后） | ~1-3 GB |
| constructs | 2-5 万（Top 候选） | ~50 MB |
| 其他 + 索引 | — | ~1 GB |
| **总计** | | **~10-20 GB** |

DuckDB 的单文件设计以及列式压缩使得实际磁盘占用远小于行式数据库。

### 查询性能预期

| 操作 | 数据量 | 预期时间 |
|------|--------|---------|
| 写入 100 万条 | 100 万 | < 1s |
| 计算 5000 万条序列的 stddev | 5000 万 | ~2-5s |
| 按排名取 Top 1000 | 500 万 | < 1s |
| 导出 10 万条到 CSV | 10 万 | < 1s |
| 带 JOIN 的复合查询 | 500 万 | ~1-2s |

DuckDB 的列式存储意味着聚合计算（标准差、百分位数等）只读取需要的列，不扫描整行数据。
