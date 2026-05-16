# Stages3 架构文档 (As-Built)

> 版本: v1.0 — 2026-05-16
> 本文档记录 stages3 的实际实现，与 `plan/` 中的规划文档并列对照。

---

## 一、目录结构

```
main/stages3/
├── __init__.py              # 包初始化
├── DONE.md                  # 进度记录（持续更新）
├── ARCHITECTURE_AS_BUILT.md # ← 本文档（实际架构）
│
├── plan/                    # ← 规划文档（原始设计意图）
│   ├── PLAN.md              # 总体路线图
│   ├── ARCHITECTURE.md      # 三层架构设计
│   ├── DB_SCHEMA.md         # 数据库设计
│   ├── DATA_PREP.md         # 数据预处理方案
│   └── TECH_REQUIREMENTS.md # 技术强制规范
│
├── db.py                    # DuckDB 接口
├── docker_utils.py          # 按需启动 Docker
├── service_map.py           # 服务依赖地图
├── analytics.py             # 方差感知权重引擎
│
├── fasta_parser.py          # 超大 FASTA 流式读取
├── cdhit_wrapper.py         # CD-HIT 封装（已测试，实际跳过）
├── sample_fasta.py          # FASTA 蓄水池抽样
└── stage00_preprocess.py    # Step 0: 数据预处理

output3/
├── pipeline.db              # DuckDB 数据库
├── STATUS.md                # 环境状态
├── reports/                 # 各阶段报告
├── pdb/                     # Step 4 PDB 文件
├── logs/                    # 运行日志
└── final/                   # 最终输出
```

---

## 二、模块职责

### db.py — DuckDB 接口

数据库操作的唯一入口，所有 stage 脚本不直接构造 SQL。

| 方法 | 用途 |
|------|------|
| `init_schema()` | 创建全部 14 张表（幂等） |
| `insert_candidates()` | 批量插入候选肽（10k/批，自动 ID） |
| `insert_stage1_scores()` | 写入 Step 1 评分 |
| `mark_stage1_passed()` | 记录 Step 1 通过者 |
| `compute_distribution()` | 计算单列分布统计 |
| `set_checkpoint()` / `get_checkpoint()` | 检查点读写 |
| `get_last_processed_id()` | 断点续跑查询 |
| `row_count()` | 行数统计 |

**性能关键决策**：使用单条 `INSERT INTO ... VALUES (...), (...)` 而非 `executemany`。DuckDB 的 executemany 仅 200 条/秒，VALUES 批处理达 20k 条/秒（100x 提升）。

### docker_utils.py — 按需启动 Docker

每个 step 执行前只启动自己依赖的微服务。

| 函数 | 用途 |
|------|------|
| `ensure_services(names, profiles)` | 主入口：启动 → 健康检查 → 缓存 |
| `check_docker_daemon()` | 检查 Docker daemon 是否运行 |
| `start_services(profiles, services)` | `docker compose up -d` 指定服务 |
| `detect_bridge_ip(container)` | 检测容器 bridge IP |
| `wait_for_services()` | 轮询 `/health` 直到就绪 |
| `clear_cache()` | step 切换时清空缓存 |

**幂等性**：同一服务连续调用 `ensure_services` 直接返回缓存结果。

### service_map.py — 服务依赖地图

```
step0: []                               # 纯本地
step1: [anoxpepred, algpred2]           # 抗氧化 + 过敏原
step2: [anoxpepred, bepipred3, ...]     # 全量 9 服务评分
step3: [sodope, temstapro]              # 溶解度 + 稳定性
step4: [omegafold]                      # 3D 结构
step5: [sasa, aggrescan3d]              # PDB 评估
step6: []                               # 纯本地（最终排名）
```

⚠️ **实际 profile 分布与规划不同**：（详见 `plan/PLAN.md` vs `tools/docker-compose.yml`）
- 规划假设大多数评分服务是 CPU，实际只有 `toxinpred3`/`sodope`/`tipred`/`algpred2` 是 CPU
- `anoxpepred`/`bepipred3`/`plm4cpps`/`graphcpp`/`temstapro`/`mhcflurry`/`hemopi2` 全部是 GPU profile
- 导致大部分 step 需要同时启动 `gpu` 和 `cpu` 两个 profile

### analytics.py — 方差感知权重引擎

stages3 的核心创新。详见下文第五部分。

---

## 三、Step 0 实现细节

### 流程

```
原始 FASTA (102G + 120G)
    │  流式扫描 (fasta_iter_lines, 290k 条/秒)
    ▼
3-30aa 长度筛选
    │
    ▼
标准氨基酸过滤 (20 种标准 AA)
    │
    ▼
批量写入 DuckDB (10k 条/批, 20k 条/秒)
    │
    ▼
生成统计报告 → reports/stage0_report.md
```

### CD-HIT 参数实验

对两个数据库的短肽样本做参数扫描，结论：**跳过 CD-HIT**。

| 参数 | MGnify 聚类率 | UniProt 聚类率 |
|------|-------------|---------------|
| -c 0.90 | 0.2% | ~5% |
| -c 0.95 | 0.0% | ~3% |
| -c 1.00 | 0.0% | ~3% |

短肽（3-30 aa）天然多样性极高，即使在 90% 相似度下也几乎不形成簇。CD-HIT 带来的收益不足以抵消其复杂性。

### 实际通过率

| 数据源 | 预估通过率 | 实际通过率 | 说明 |
|--------|-----------|-----------|------|
| UniProt (225M) | 1-3% | **0.25%** | 全长蛋白为主，短肽极少 |
| MGnify (624M) | 10-20% | **2.7%** | 宏基因组短序列多于 UniProt，但仍有限 |
| **合计** | **30M-100M** | **~17.5M** | 远低于预估 |

---

## 四、按需启动原则（与 plan/ 的差异）

### 规划 vs 实现

| 维度 | 规划中的设计 | 实际实现 |
|------|------------|---------|
| Docker 启动 | 一次性启动全部 | 每个 step 按需启动 |
| 服务分组 | 假设 score = cpu, structure = gpu | 实际大部分 score 也在 gpu 下 |
| Bridge IP | 需手动检测 | `docker_utils.py` 自动检测 |
| 健康检查 | 启动后统一检查 | 每个 step 独立检查，幂等缓存 |

### 启动协议

每个 step 脚本标准入口：

```python
from main.stages3.docker_utils import ensure_services
from main.stages3.service_map import get_step_services

info = get_step_services("step1")
health = ensure_services(info["services"], info["profiles"])
unavailable = [s for s, h in health.items() if not h["available"]]
if unavailable:
    sys.exit(f"服务不可用: {unavailable}")
```

---

## 五、方差感知权重（Variance-Aware Weighting）

### 算法

```
1. 读取所有候选的每项评分
2. 对每项评分计算 winsorized 标准差（截尾 1% 极端值）
3. 权重 w_i = σ_i_winsorized / Σσ_j_winsorized
4. 综合得分 = Σ(w_i × score_i_normalized)
5. 按综合得分排名
```

### 验证结果（模拟数据）

| 服务 | 标准差 | Winsorized σ | 权重 |
|------|-------|-------------|------|
| anoxpepred | 0.25 | 0.249 | **0.557** |
| sodope | 0.15 | 0.149 | **0.333** |
| bepipred3 | 0.05 | 0.049 | **0.110** |

区分度好的服务自动获得更高权重。权重比 ≈ 标准差比。

### 与 stages2 的对比

| 方面 | stages2（固定权重） | stages3（方差感知） |
|------|------------------|------------------|
| 权重来源 | 人工设定 | 数据驱动 |
| 区分度处理 | 所有服务固定权重 | 自动降噪 |
| 极端值处理 | 无 | Winsorization |
| 可审计性 | CSV 中手动记录 | `weight_config` 表 |

---

## 六、数据库 Schema（实际实现）

### 表清单（14 张）

| 表 | 用途 | 行数预估 |
|----|------|---------|
| `candidates` | 候选肽段池 | 17.5M |
| `stage1_scores` | Step 1 评分 | 17.5M |
| `stage1_passed` | Step 1 通过者 | ~5M |
| `stage2_scores` | Step 2 全量评分 | ~0.5M |
| `stage2_ranking` | Step 2 排名 | ~0.5M |
| `constructs` | 构造枚举 | ~50K |
| `construct_scores` | 构造评分 | ~50K |
| `structure_jobs` | 结构预测任务 | ~500 |
| `structure_results` | 结构预测结果 | ~500 |
| `pdb_eval` | PDB 评估 | ~500 |
| `final_ranking` | 最终排名 | ~100 |
| `score_distribution` | 分布统计 | ~20 |
| `weight_config` | 权重配置 | ~5 |
| `checkpoint` | 检查点 | ~20 |

### 与 DB_SCHEMA.md 规划的差异

| 内容 | 规划 | 实际 |
|------|------|------|
| 唯一索引 | `(source, source_id) UNIQUE` | 改为普通索引（写入性能考量） |
| 自增 ID | DEFAULT nextval | 保留，用于大规模写入 |
| 内存限制 | 32GB | 保留 |

---

## 七、与规划文档的偏差汇总

| 规划内容 | 实际状态 | 原因 |
|---------|---------|------|
| CD-HIT 聚类 | **跳过** | 短肽多样性极高，聚类无效 |
| Stage 0 分 4 步 | **合并为 2 步** | 长度筛选 → AA 过滤 → 直接写入 |
| ~3000 万-1 亿候选 | **~1750 万** | 实际通过率远低于预估 |
| 大部分服务为 CPU | **大部分为 GPU** | docker-compose.yml 实际配置 |
| 技术债 5 项 | **待处理** | 运行时遇到再修，不阻塞开发 |

---

## 八、命令速查

```bash
# Step 0: 数据预处理
uv run python -m main.stages3.stage00_preprocess

# Step 0 (抽样模式)
uv run python -m main.stages3.stage00_preprocess --sample 10000

# 仅 UniProt
uv run python -m main.stages3.stage00_preprocess --uniprot-only

# 仅 MGnify
uv run python -m main.stages3.stage00_preprocess --mgy-only

# 测试 Docker 服务启动
uv run python -m main.stages3.docker_utils anoxpepred algpred2
```
