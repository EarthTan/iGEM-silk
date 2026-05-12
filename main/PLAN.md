# Pipeline 设计方案

## 一、总体架构

Pipeline 是一个**自适应漏斗式**筛选流程，核心原则：
1. **便宜的放前面，贵的放后面**
2. **不写死数字** — 每一步根据上一步的实际结果动态调整下一步的参数
3. **每个阶段可独立运行** — 各阶段输出到 `output/`，可断点续跑

```
Phase 0: 初始化
    ├── 加载配置 (.env / pipeline_config.py)
    ├── 加载数据 (scaffold, linkers, function_peptides)
    └── 启动微服务（按需，分阶段）

Phase 1: 肽级筛选 (25,000 → ~50)
    ├── 硬过滤 (ToxinPred3, HemoPI2, AlgPred2)  ← 绝对，不可调
    ├── 功能评分 + 排序                          ← 自适应
    └── 加权综合评分 → 选 Top                    ← 自适应

Phase 1.5: 枚举构建 + 预筛选
    ├── 枚举所有 construct 组合
    └── 预筛选至 ≤目标值 进入 3D                 ← 自适应

Phase 2: 3D 结构预测
    ├── 释放 GPU 资源（关停非结构服务）
    ├── AlphaFold3 / PEP-FOLD4 / ACP4 预测
    └── 缓存 PDB/mmCIF 文件

Phase 3: PDB 最终评估
    ├── SASA (溶剂可及表面积)
    ├── Aggrescan3D (聚集倾向)
    └── 综合排名 → 输出报告
```

各阶段顺序可灵活调整（可以先排序再过滤，或多个交叉回合），但总数据量必须递减。

---

## 二、自适应漏斗设计（核心创新点）

**关键思路**：不预设 `TOP_PEPTIDES=50` 这类硬编码值，而是给每个环节一个**目标范围**和**调整规则**。

### 示例流程

```
初始数据: 25,000 条功能肽

Step A: 硬过滤 (toxinpred3 / hemopi2 / algpred2)
  → 剩余 8,000 条（预期 8K–12K，在范围内，继续）

Step B: 功能评分 + 排序
  设定目标：保留 30% 或上限 3,000 条
  → 剩余 2,400 条（取 30%）

Step C: 加权综合评分
  目标：进入枚举的肽不超过 50 条
  实际仍有 2,400 条：
    - 方案 1：取 score 分布的自然拐点（如肘部法则）
    - 方案 2：取 Top X%，使得枚举后 construct ≤ 目标值
  → 剩余 8～50 条肽（取决于 score 分布）
```

### 调整规则

| 上一步结果 | 下一步行为 |
|-----------|-----------|
| 远少于预期 | 放宽下一步的筛选比例（如从 30% → 50%） |
| 符合预期 | 按原计划执行 |
| 远多于预期 | 收紧下一步的筛选比例（如从 30% → 15%） |
| **硬过滤** | **绝不调整**（毒性/溶血/过敏是绝对排除） |

### 配置方式

```ini
# .env — 设置的是"目标"和"策略"，不是"硬数字"
PHASE1_TARGET_PEPTIDES=50             # Phase 1 期望保留的肽数
PHASE1_FILTER_MODE=percent            # percent 或 absolute
PHASE1_FILTER_VALUE=30                # 保留前 30%
PHASE1_ADAPTIVE=true                  # 自适应调整
PHASE1_ADAPTIVE_RANGE="500-5000"     # 可接受的浮动范围

TARGET_CONSTRUCTS_3D=50               # 3D 阶段最多处理数
```

---

## 三、Phase 0: 初始化

### 3.1 配置系统

```
.env / pipeline_config.py
    FUNCTION_TYPE=antioxidcat         # 功能类型
    TEST_MODE=true                    # 测试模式
    PEPTIDE_SAMPLE_SIZE=100           # 测试模式加载条数
    CACHE_DIR=./cache                 # 缓存根目录
    PIPELINE_OUTPUT=./output          # 输出目录

    # 自适应筛选参数
    PHASE1_TARGET_PEPTIDES=50
    PHASE1_FILTER_MODE=percent
    PHASE1_FILTER_VALUE=30
    PHASE1_ADAPTIVE=true
    TARGET_CONSTRUCTS_3D=50

    # 枚举配置
    ENUM_SAME_PEPTIDE=true            # (c) 方案两端是否用同一肽
    ENUM_SAME_LINKER=true             # 同一 construct 是否统一 linker 类型

    # 评分权重（可选，不设则用默认值）
    # WEIGHT_ANOXPEPRED=0.35
    # WEIGHT_TIPRED=0.30

    # 微服务生命周期
    AUTO_MANAGE_SERVICES=true         # pipeline 自动管理微服务启停
    SERVICES_DIR=./tools              # 微服务代码根目录
```

`config.py` 保持不动（只保留微服务地址）。新增 `pipeline_config.py` 专门管理 pipeline 参数，其默认值可以被 `.env` 覆盖。

### 3.2 数据加载

沿用 `main/data_loader.py` 现有代码，加载逻辑由 `.env` 控制：

```python
config = load_config()
df = load_function_peptides()

# 按 FUNCTION_TYPE 过滤
switch config.function_type:
    case "antioxidant":    df = df[df["is_antioxidant"] == 1]
    case "antimicrobial":  df = df[df["is_antimicrobial"] == 1]
    # ...

# 测试模式取子集
if config.test_mode:
    df = df.head(config.peptide_sample_size)
```

### 3.3 Service Manager（微服务生命周期管理）

核心组件：`main/service_manager.py`，**作为本分支的 pipeline 重构的一部分来实现**。

```python
class ServiceManager:
    """
    微服务进程管理。
    自动启动/停止每个微服务进程（subprocess），通过 /health 端点确认就绪。
    支持按 group 批量操作，GPU 感知。
    """

    async def start(self, name: str, timeout: float = 120.0) -> bool
    async def stop(self, name: str) -> bool
    async def restart(self, name: str) -> bool

    async def start_group(self, group: str) -> dict[str, bool]
    async def stop_group(self, group: str) -> dict[str, bool]
    async def stop_all(self) -> None

    async def ensure_services(self, names: list[str]) -> dict[str, bool]
    async def ensure_groups(self, groups: list[str]) -> dict[str, bool]

    async def get_health(self) -> dict
    async def wait_for_ready(self, name: str, timeout: float) -> bool

    async def shutdown(self) -> None
```

#### 启动流程

1. `cd tools/<name> && .venv/bin/python service.py`（`asyncio.create_subprocess_exec`）
2. 轮询 `GET /health` 直到 `model_loaded: true`（超时 120s，间隔 0.5s）
3. 超时则标记为不可用

#### 启动/停止策略

| 服务 | 启动时机 | 关闭时机 | 原因 |
|------|----------|----------|------|
| AnOxPePred | Phase 1 开始 | Phase 2 前 | GPU 可释放 |
| ToxinPred3 | Phase 1 开始 | 全程结束 | CPU 轻量，无影响 |
| HemoPI2 | Phase 1 开始 | Phase 2 前 | GPU |
| BepiPred-3.0 | Phase 1 开始 | Phase 2 前 | 大模型，释放 4GB+ |
| AlgPred2 | Phase 1 开始 | 全程结束 | CPU 轻量 |
| pLM4CPPs | Phase 1 开始 | Phase 2 前 | GPU |
| TIPred | Phase 1 开始 | 全程结束 | CPU 轻量 |
| GraphCPP | Phase 1 开始 | Phase 2 前 | GPU |
| TemStaPro | Phase 1 开始 | Phase 2 前 | 大模型，释放 6GB+ |
| SoDoPE | Phase 1 开始 | 全程结束 | CPU 轻量 |
| MHCflurry | Phase 1 开始 | Phase 2 前 | GPU |
| **AlphaFold3** | **Phase 2 开始** | **Phase 2 结束** | 独占 GPU |
| PEP-FOLD4 | Phase 2 开始 | Phase 2 结束 | Docker CPU |
| SASA | Phase 3 开始 | 全程结束 | CPU |
| Aggrescan3D | Phase 3 开始 | 全程结束 | Docker CPU |

#### GPU 显存管理

- Phase 1 结束后，关停所有 GPU 加速服务
- Phase 2（3D 预测）开始前，确认 GPU 可用 >20GB
- Phase 2 结束后、Phase 3 开始前，**不需要重新启动 GPU 服务**（SASA 和 Aggrescan3D 都是 CPU-only）

#### 错误处理

- 启动失败 → 记录错误，跳过依赖该服务的步骤
- 运行中崩溃 → 自动尝试重启一次
- 连续失败 → 标记不可用，不阻塞其他服务

---

## 四、Phase 1: 肽级筛选

### 4.1 硬过滤（Hard Filters）

调用三个 filter 组服务，**一票否决，不可调整**：

```python
filter_services = ["toxinpred3", "hemopi2", "algpred2"]
results = await client.evaluate_peptides(peptides, service_names=filter_services)

surviving = []
for pep in peptides:
    scores = results["peptide_scores"][pep["peptide_id"]]
    if scores.get("toxinpred3", {}).get("label") == "Toxin": continue
    if scores.get("hemopi2", {}).get("label") == "Hemolytic": continue
    if scores.get("algpred2", {}).get("label") == "Allergen": continue
    surviving.append(pep)
```

输出：`output/phase1_filtered.json`

### 4.2 功能评分 + 排序

调用与 FUNCTION_TYPE 对应的核心评分服务，按 score 降序排列：

| FUNCTION_TYPE | 核心评分服务 |
|---------------|-------------|
| antioxidant | AnOxPePred |
| cell_penetrating | pLM4CPPs, GraphCPP |
| ... | ... |

**自适应截断**：保留前 `PHASE1_FILTER_VALUE`%（默认 30%），但根据上一步实际剩余量动态调整。

输出：`output/phase1_ranked.json`

### 4.3 加权综合评分

对剩余肽计算加权综合分：

```python
WEIGHTS = {
    "anoxpepred": 0.35,     # 核心功能
    "tipred": 0.30,         # 抗黑色素
    "bepipred3": 0.15,      # 表面暴露度代理
    "plm4cpps": 0.10,       # 细胞穿膜
    "sodope": 0.05,         # 溶解度
    "mhcflurry": -0.05,     # 免疫原性（越低越好）
    "graphcpp": 0.05,       # 细胞穿膜（辅助）
}

# 综合分 = Σ(weight × adjusted_score) / Σ|weight|
```

**自适应选 Top**：目标是选出不超过 50 条肽进入枚举，选择方式取决于 score 分布：
- 有明显拐点 → 取拐点以上的
- 无明显拐点 → 取 Top N，使得后续枚举数 ≤ `TARGET_CONSTRUCTS_3D`

输出：`output/phase1_scored.json`

---

## 五、Phase 1.5: 构建枚举 + 预筛选

### 5.1 枚举逻辑

对 Phase 1 筛选出的肽进行枚举：

```python
for peptide in top_peptides:
    for linker in linkers:            # 6 种 Linker
        for position in positions:     # 3 种位置方案
            seq = build_construct(peptide, linker, scaffold, position, his6=True)
            constructs.append({...})
```

### 5.2 三种位置方案的序列拼接

```
(a) N-term: [Func] + [Linker] + [Silk] + [His6]
(b) C-term: [Silk] + [Linker] + [Func] + [Linker] + [His6]
(c) Both:   [Func] + [Linker] + [Silk] + [Linker] + [Func] + [Linker] + [His6]
```

由 `.env` 控制：
- `ENUM_SAME_PEPTIDE=true` → (c) 两端用同一个肽
- `ENUM_SAME_PEPTIDE=false` → (c) 两端用不同肽（50选2）
- `ENUM_SAME_LINKER=true` → 同一 construct 中所有 Linker 统一用一种

### 5.3 Construct 预筛选

当 construct 总数超过 `TARGET_CONSTRUCTS_3D` 时，按策略筛选：

| 策略 | 做法 |
|------|------|
| 按肽得分截断 | 保留得分最高的肽，使 construct ≤ 目标值 |
| 按位置优先 | 优先保留某个位置的 construct（如 C-term 更稳定） |
| 混合 | 先选最优位置，再截断肽数 |

### 5.4 枚举缓存

```
cache/pipeline/enumeration.json
```

同参数枚举直接从缓存读取。

输出：`output/constructs.json`

---

## 六、Phase 2: 3D 结构预测

### 6.1 GPU 资源释放

进入本阶段前，`ServiceManager` 关停所有 GPU 服务：
- BepiPred-3.0（ESM-2 650M, ~4GB）
- TemStaPro（ProtT5-XL, ~6GB）
- HemoPI2、pLM4CPPs、GraphCPP、MHCflurry

### 6.2 结构预测

按 construct 序列长度选择工具：

| 序列长度 | 选用工具 | 环境 | 耗时 |
|----------|----------|------|------|
| 5–40 aa | PEP-FOLD4 | CPU Docker | 10–30 分钟 |
| > 40 aa 或全长 | AlphaFold3 / ACP4 | GPU Docker | 5–60 分钟（ACP4 预计更快） |

### 6.3 结构缓存

```
cache/structures/{md5(sequence)}.pdb     # PEP-FOLD4
cache/structures/{md5(sequence)}.mmcif   # AlphaFold3
cache/structures/{md5(sequence)}.meta.json
```

**相同序列跳过预测**。

### 6.4 执行模式

construct 的 3D 预测串行执行（资源限制）。串行队列的情况下实测耗时待评估。

输出：`output/structures/` 目录

---

## 七、Phase 3: PDB 最终评估

### 7.1 启动 PDB 评分服务

关停 structure 服务后，启动 SASA（CPU, 1–5 秒/个）和 Aggrescan3D（Docker CPU, 1–15 分钟/个）。

### 7.2 SASA

评估功能肽的溶剂可及性：
- **exposed** → 功能肽在表面 ✅
- **buried** → 功能肽包埋在内部 ❌

### 7.3 Aggrescan3D

评估整条融合蛋白的聚集风险。分数越高风险越大。

### 7.4 最终排名

```python
final_score = α × weighted_peptide_score + β × pdb_composite_score
# α, β 可配置，默认 α=0.7, β=0.3
```

输出：`output/final_report.json` / `output/final_report.csv`

---

## 八、各阶段输入输出总览

| 阶段 | 输入 | 输出 | 可独立运行 |
|------|------|------|-----------|
| Phase 0 | `.env`, `data/*` | `config`, loaded data | 否 |
| Phase 1 | 加载的肽数据 | `phase1_filtered.json`, `phase1_scored.json` | ✅ 可以 |
| Phase 1.5 | Phase 1 output | `constructs.json` | ✅ 可以 |
| Phase 2 | constructs + PDB 缓存 | `structures/*.pdb` | ✅ 可以 |
| Phase 3 | PDB 文件 | `final_report.*` | ✅ 可以 |

每个阶段写 `output/` 目录，下次运行先检测是否存在可用缓存。

---

## 九、缓存系统设计

### 9.1 三层缓存结构

```
cache/
  services/                     # 微服务调用结果缓存（按序列哈希）
    anoxpepred/                 #   → Docker 中通过 volume mount 共享
      {md5(sequence)}.json
    toxinpred3/
      {md5(sequence)}.json
    ...
  structures/                   # 3D 结构文件（体积大）
    {md5(sequence)}.pdb
    {md5(sequence)}.mmcif
    {md5(sequence)}.meta.json
  pipeline/                     # 中间结果缓存（小文件 JSON）
    phase1_filtered.json
    enumeration.json
    ...
```

### 9.2 缓存操作

```python
class Cache:
    def get(self, key: str) -> Any | None
    def set(self, key: str, value: Any) -> None
    def has(self, key: str) -> bool
    def key(self, *parts: str) -> str
```

序列 → key：`md5(sequence.encode()).hexdigest()`。不引入 Redis。

### 9.3 Docker 部署下的缓存策略

生产环境所有微服务以 Docker 容器运行，缓存通过 **volume mount** 共享：

```yaml
# docker-compose.yml
services:
  anoxpepred:
    volumes:
      - ./cache/services:/app/cache/services   # 共享缓存目录
  # ...所有服务挂载同一路径

  pipeline:
    volumes:
      - ./cache:/app/cache                    # pipeline 访问全部缓存
```

这意味着缓存路径设计必须**跨容器一致**，并且不与任何微服务内部逻辑冲突。

### 9.4 缓存的边界

微服务本身的缓存由各微服务自行管理（如模型加载缓存）。
Pipeline 缓存只管理**调用结果缓存**和**中间结果缓存**，不干预微服务内部状态。

---

## 十、文件结构规划

### 新增文件

```
main/
  plan.md                  ← 本文档
  pipeline.py              ← Pipeline 主编排逻辑
  pipeline_config.py       ← 参数配置（权重、阈值、路径），读取 .env
  service_manager.py       ← 微服务进程生命周期管理
  cache.py                 ← 文件系统缓存
  enumeration.py           ← construct 快速序列构建枚举
  output/                  ← 运行输出目录
```

### 不动文件

```
main/__init__.py     ← 不动
main/__main__.py     ← 不动
main/config.py       ← 不动（只保留 SERVICE + service_url）
main/data_loader.py  ← 不动
main/client.py       ← 不动
```

---

## 十一、实现路线图

### Step 1: 基础设施
1. `pipeline_config.py` — 配置系统
2. `cache.py` — 缓存系统
3. `service_manager.py` — 微服务生命周期

### Step 2: 核心流程
4. `enumeration.py` — Construct 枚举构建
5. `pipeline.py` Phase 1 — 加载 → 过滤 → 评分 → 自适应选 Top

### Step 3: 完整流程
6. `pipeline.py` Phase 1.5 — 枚举 + 预筛选
7. `pipeline.py` Phase 2 — 3D 结构预测
8. `pipeline.py` Phase 3 — PDB 评估 + 报告

### Step 4: 打磨
9. `.env` 完整配置 + 多 FUNCTION_TYPE 支持
10. 测试
11. 性能优化
