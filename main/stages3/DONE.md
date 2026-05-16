# Stages3 Pipeline — 完成记录

> 最后更新: 2026-05-16

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
