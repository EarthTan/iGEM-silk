# Stages3 Pipeline — 完成记录

> 最后更新: 2026-05-17

## 环境搭建 (2026-05-16)

| 项目 | 状态 | 备注 |
|------|------|------|
| CD-HIT | ✅ v4.8.1 | `/usr/bin/cd-hit` |
| DuckDB | ✅ v1.5.2 | `uv add duckdb` |
| output3/ | ✅ 目录结构 | `pdb/`, `logs/`, `reports/`, `final/`, `pipeline.db` |
| 数据库 | ✅ 14 张表 | `db.py` 中的完整 schema，含 `candidates` + `checkpoint` |
| STATUS.md | ✅ 环境快照 | `output3/STATUS.md` |
| CLAUDE.md | ✅ 更新 | 追加"按需启动原则" |

## 新增文件

| 文件 | 说明 |
|------|------|
| `main/stages3/__init__.py` | 包初始化 |
| `main/stages3/db.py` | DuckDB 接口（schema、批量写入、分布统计、检查点） |
| `main/stages3/sample_fasta.py` | FASTA 蓄水池抽样工具 |
| `main/stages3/fasta_parser.py` | 超大 FASTA 流式读取器 |
| `main/stages3/cdhit_wrapper.py` | CD-HIT 命令行封装 |
| `main/stages3/stage00_preprocess.py` | Stage 0 预处理主脚本 |
| `main/stages3/service_map.py` | 服务依赖地图（step 命名） |
| `main/stages3/docker_utils.py` | 按需启动 Docker |
| `main/stages3/analytics.py` | 方差感知权重引擎 |
| `main/stages3/ARCHITECTURE_AS_BUILT.md` | 实际架构文档 |
| `output3/STATUS.md` | 环境状态记录 |

## Stage 0 开发 (2026-05-16)

### CD-HIT 参数实验

从两个 FASTA 源各提取 100k 短肽（3-30aa），用 `-c 0.90/0.95/0.98/1.00` 测试聚类效果。

**结论：短肽天然多样性极高，CD-HIT 基本无效。**
- MGnify: 3.67M 扫描 → 100k 短肽（2.72%），任何阈值下几乎 100% 单序列簇
- UniProt: 39M 扫描 → 100k 短肽（0.25%），-c 0.90 仅合并 5% 序列

**决定：跳过 CD-HIT，改用精确去重（100% 相同去重），由 DuckDB 的索引天然保证。**

### DuckDB 性能优化

发现 `executemany` 写入仅 200 条/秒（41 小时/17M 条），改为单条 INSERT + VALUES 批处理（20k 条/秒），提速 100 倍。

### 抽样测试结果

```
uv run python -m main.stages3.stage00_preprocess --sample 10000
```

| 数据源 | 扫描 | 写入 | 耗时 |
|--------|------|------|------|
| UniProt | 5.3M 条 | 10,000 条 | 20s |
| MGnify | 370k 条 | 10,000 条 | 2s |

- 通过率: UniProt ≈0.25%, MGnify ≈2.7%
- DB 随机读: 10k 条 / 0.01s
- 报告自动生成: `output3/reports/stage0_report.md`

## 基础设施搭建 (2026-05-16)

### service_map.py
- 使用 "step" 命名（step0-step6），非 "stage"
- 基于 `tools/docker-compose.yml` 的实际 profile 配置
- 发现规划假设与实际的重大差异：大部分评分服务实际上是 GPU profile

### docker_utils.py
- `ensure_services()` 是主入口，幂等（多次调用返回缓存）
- 自动检查 Docker daemon → 按需启动 → 轮询 /health 等待就绪
- 自动检测 bridge IP（为后续网络优化准备）
- 支持 `skip_docker=True` 参数用于开发调试

### analytics.py
- 方差感知权重引擎：读取分数 → 计算分布 → winsorization → 归一化权重 → 应用排名
- 验证通过: 区分度好的服务自动获得更高权重（5 倍差距验证）
- 完整记录到 `score_distribution` + `weight_config` 表，全链路可审计

### ARCHITECTURE_AS_BUILT.md
- 记录实际实现的架构，与 `plan/` 中的规划文档并列对照
- 涵盖：目录结构、模块职责、数据库 schema、按需启动协议、权重算法
- 明确标注与规划文档的所有偏差及其原因

## Stage 0 全量运行 (2026-05-17)

| 项目 | 状态 | 备注 |
|------|------|------|
| UniProt 处理 | ✅ 完成 | 225.6M 扫描 → 733,573 写入 (0.33%) |
| MGnify 处理 | ✅ 完成 | 623.8M 扫描 → 19,156,448 写入 (3.07%) |
| 候选池总计 | ✅ **19,890,021** | 849M 序列总扫描 |
| 总耗时 | ✅ 98.7 min | 5,924s |
| DB 文件 | ✅ 2.6 GB | `output3/pipeline.db` |
| 自动报告 | ✅ | `output3/reports/stage0_report.md` |
| Step 0 README | ✅ | `output3/step0/README.md` |
| DONE.md | ✅ 已更新 | 本文件 |

### 关键发现

- **实际通过率**: UniProt 0.33%, MGnify 3.07%（与抽样测试高度一致）
- **总候选数**: 19.9M（低于规划的 30M-100M，但远高于 stages2 的 1M）
- **扫描速度**: 批写入前 290k seq/s，DB 增长到 1GB 后降至 120k seq/s
- **DB 大小**: 19.9M 条 / 2.6GB，约 7.6M 条/GB

## Step 1 开发 (2026-05-17)

### 新增/修改文件

| 文件 | 说明 |
|------|------|
| `main/stages3/stage01_lightweight.py` | Step 1 主脚本 |
| `main/stages3/db.py` | `insert_stage1_scores` 改为 VALUES 批处理（替代慢速 executemany） |

### 设计概要

Step 1 对 19.9M 候选肽运行两个轻量评分服务：
- **AnOxPePred** (gpu profile, port 8001): 抗氧化活性预测，核心筛选信号
- **AlgPred2** (cpu profile, port 8008): 过敏原预测，硬阈值 ≥0.30 淘汰

### 技术决策

1. **分批流式处理**：每次从 DuckDB 读取 100k 条，避免 19.9M 全量加载到内存
2. **双服务并发**：两个服务通过 `asyncio.gather` 并行调用，互不阻塞
3. **每服务 Semaphore(5)**：控制 GPU 服务并发负载，防止显存 OOM
4. **断点续跑**：通过 `stage1_scores` 表的 `MAX(candidate_id)` 和 `checkpoint` 表支持
5. **AlgPred2 硬过滤**：`score ≥ 0.30` 淘汰，score IS NULL 放行（服务故障宽容）
6. **DB 写入优化**：弃用 `executemany`，改用 VALUES 批处理（预期 100x 加速）
