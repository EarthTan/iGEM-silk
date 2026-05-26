# Stages2 Pipeline Review — iGEM-silk 抗氧化肽融合蛋白设计

**生成日期**: 2026-05-18
**状态**: 全流程完成
**输出目录**: `output2/`

---

## 1. 做了什么

完成了 stages2 全流程 8 轮（Step 0 ~ Round 7）的端到端重新运行，从 108 万条候选肽筛选至最终 90 个 Top 候选 construct + 60 个 Bottom 对照，输出包含：3D 结构（OmegaFold PDB）、表面评估（SASA + Aggrescan3D）、全流水线评分聚合、双通道独立排名的完整结果包。

### Pipeline 总览

| 阶段 | 耗时 | 数据量变化 |
|------|------|-----------|
| Step 0: 数据整合 | ~30s | 1,081,772 → **1,055,116** |
| Round 1: 轻量评分 (AnOxPePred+AlgPred2) | ~15min | 1,055,116 → 全量评分 |
| Round 2: 分选+安全评分 (5 服务) | ~63min | 1,055,116 → **50,000** (top25K+bottom25K) |
| Round 3: 重服务评分 (7 服务) | ~65min | 50,000 → Top 80 + Bottom 60 |
| Round 4: 枚举+Construct (5 服务) | ~13min | → **150 constructs** |
| Round 5: 3D 结构 (OmegaFold) | ~210min | 150 → 150 OmegaFold PDB |
| Round 6: PDB 评估 (SASA+A3D) | ~6min | 150 PDB → 150 评分 |
| Round 7: 最终输出 | ~1min | → 90 Top + 60 Bottom 排名 |
| **总计** | **~6.5h** | **1,081,772 → 150 candidates** |

### 最终 Top 5

| Rank | Construct | Peptide | round6 | SASA | Agg | pLDDT |
|------|-----------|---------|--------|------|-----|-------|
| #1 | con_0215 | ERELPYYPGAHPMHPPK | 0.7794 | 0.8143 | 0.3515 | 0.4522 |
| #2 | con_0199 | GTHWHPEHF | 0.7684 | 0.7996 | 0.3291 | 0.4460 |
| #3 | con_0226 | EPTMYGEILSPNYPQAYPSEV | 0.7345 | 0.7697 | 0.3488 | 0.4398 |
| #4 | con_0201 | GTHWHPEHF (Both) | 0.7224 | 0.7633 | 0.3564 | 0.4369 |
| #5 | con_0095 | PAFELHYPHMVER | 0.7142 | 0.7212 | 0.3318 | 0.4364 |

---

## 2. 背后的思路

### 为什么重跑 stages2？

原 stages2（`output/`）存在设计缺陷：多个脚本间的文件名、断点续跑、并发控制等不一致，且部分服务（如 ToxinPred3）的资源开销预估不足。与其在原脚本上打补丁，不如新建 `output2/` 目录完整重跑，同时引入 `common.py` 统一工具函数。

### 为什么双通道？

不只要找"抗氧化性最好的肽"，也需要检验那些**抗氧化性差但其他安全指标通过的肽**作为阴性对照。因此设计了 Top/Bottom 双通道并行贯穿全流程，两边的数据各自独立排名。

### 为什么 Round 1 不跑 ToxinPred3？

原始计划在 105 万条上跑 ToxinPred3，但 sklearn ExtraTrees 是单线程 CPU 密集任务，估算需 ~22h。改为 Round 2 在 50K 子集上跑，仅需 ~48min，合理。

### 为什么 Round 2 按纯 AnOxPePred 分选，而非加权分？

早期的 pipeline 使用加权综合分分选，但不同服务的量纲和区分度不同，提前混合会掩盖抗氧化性本身的质量。改用**纯 AnOxPePred（直接测量抗氧化活性）** 分选，再对选中的 25K+25K 补跑安全服务。

### 为什么 Round 5 只用 OmegaFold，不用 ESMFold？

测试数据表明 ESMFold 对 silk 融合蛋白（重复序列）的 pLDDT 普遍 <0.30，置信度过低，对下游 SASA/A3D 评估没有参考价值。而 OmegaFold 的 pLDDT 均值 0.41，且对重复序列的处理更优。最终从 2 服务并行改为纯 OmegaFold，节省了 ~50% 的 GPU 时间。

### 为什么 Round 6 去掉了 construct_composite 权重？

见第 3 节权重设置。

---

## 3. 权重设置

### Round 1 权重（仅评分，不分选）

| 服务 | 权重 | 理由 |
|------|------|------|
| AnOxPePred | 0.50 | 直接测量抗氧化活性，核心指标 |
| AlgPred2 | 0.10 | 过敏性筛查，低权重 |

ToxinPred3 延后到 Round 2。

### Round 2-3 综合分

| 服务 | 权重 | 理由 |
|------|------|------|
| AnOxPePred | 0.45 | 抗氧化核心指标，最高权重 |
| ToxinPred3 | 0.13 | 毒性过滤，高风险否决项 |
| AlgPred2 | 0.09 | 过敏性筛查 |
| HemoPI2 | 0.09 | 溶血性 |
| MHCflurry | 0.05 | 免疫原性 |
| BepiPred3 | 0.10 | B 细胞表位 |
| TemStaPro | 0.09 | 热稳定性 |

### Round 4 Construct 综合分

| 服务 | 权重 | 理由 |
|------|------|------|
| Peptide weighted | 0.40 | 肽级综合分（包含 7 服务信息） |
| SoDoPE | 0.25 | 物理化学性质 |
| construct_AnOxPePred | 0.20 | 全长背景下的抗氧化 |
| construct_BepiPred3 | 0.10 | 全长 B 细胞表位 |
| TemStaPro | 0.05 | 热稳定性 |

### Round 6 综合分（最终评分公式）

| 服务 | 权重 | 理由 |
|------|------|------|
| SASA | 0.40 | 肽暴露在蛋白表面的程度，越高越好 |
| (1 - Aggrescan3D) | 0.40 | 聚集风险反转，越低越好的指标反转为越高 |
| pLDDT_norm | 0.20 | 结构置信度归一化，作为质量控制 |

**注意**: construct_composite 曾经占 0.50 权重，但在 Top 90 中这些分值高度集中（P25-P75 spread 仅 0.011），加上权重后几乎决定了排名，SASA 和 Aggrescan3D 被稀释到无意义。**因此移除 construct_composite，让 3D 层面的评估真正决定最终排名。**

---

## 4. Top N 选取

| 阶段 | 选取数量 | 依据 |
|------|---------|------|
| Round 2 分选 | Top 25,000 + Bottom 25,000 | 25K 足以覆盖高分肽的多样性，同时控制下游服务耗时在可接受范围 |
| Round 3 Top 通道 | 前 80 个 construct | 80 个覆盖不同肽序列和位置的组合，过少会丢失多样性 |
| Round 3 Bottom 通道 | 10 个肽 × 2 Linker | 作为阴性对照足够，不需要太多 |
| Round 4 枚举 | 30 种肽 × 3 位置 (Top) + 10 种肽 × 2 Linker × 3 位置 (Bottom) | 每 3 个位置（N/C/Both）× 2 Linker 的组合够用 |
| **最终输出** | **Top 90 + Bottom 60** | 全量输出，推荐选取 Top 5-10 进行 wet-lab 验证 |

---

## 5. 数据量变化趋势

```
1,081,772  ┐
           │ Step 0 (清洗去重)
1,055,116  ┘
           │ Round 1 (全量评分)
1,055,116  ┘
           │ Round 2 (双通道分选)
    50,000 ┘  ┌─ Top 25,000 (抗氧化最好)
              └─ Bottom 25,000 (抗氧化最差)
           │ Round 3 (重服务评分 + TemStaPro 前 30% 预筛)
    ~150   ┘  ┌─ Top 80 肽 → 枚举 → 90 constructs
              └─ Bottom 10 肽 → 枚举 → 60 constructs
           │ Round 5 (3D)
     150   ┘
           │ Round 6-7 (评估+排名)
     150   ┘  ┌─ Top 90 constructs
              └─ Bottom 60 constructs
```

筛选漏斗：**1,081,772 → 150**，淘汰率 **99.986%**。

### 关键数据特征

| 维度 | 均值 | 范围 |
|------|------|------|
| Top channel construct_composite | 0.5285 | 0.5097–0.5482 (spread 仅 0.039) |
| SASA score | 0.702 | 0.501–0.831 |
| Aggrescan3D risk | 0.348 | 0.289–0.398 |
| OmegaFold pLDDT | 0.4105 | 0.3666–0.4547 |
| Round6 final score | 0.642 | 0.523–0.779 |

---

## 6. 信息流变化

### v1 → v2 关键变更

| 变更 | v1 | v2 |
|------|----|----|
| 输出目录 | `output/` | `output2/` |
| 分选依据 | 加权综合分 | **纯 AnOxPePred** |
| ToxinPred3 时机 | Round 1 (105 万) | **Round 2 (5 万)** |
| Round 3 输入 | 10K (单通道) | **50K (双通道)** |
| Round 4 BepiPred3 | 全量 300 constructs | **串行 1 并发** 修复超时 |
| Round 5 服务 | ESMFold + OmegaFold | **仅 OmegaFold** |
| Round 6 权重 | construct(0.50)+pLDDT(0.15)+SASA(0.20)+A3D(0.15) | **SASA(0.40)+A3D(0.40)+pLDDT(0.20)** |
| 工具函数 | 脚本内复制粘贴 | `common.py` 统一管理 |
| 异常处理 | 部分缺 `return_exceptions` | 双层隔离（`safe_gather`） |
| 断点续跑 | 无 | `checkpoint.json` 机制 |
| 服务并发 | 固定 `CONCURRENT_CHUNKS=10` | 按服务特性调整 |

### Round 5 的重大路径修正

最初设计 ESMFold + OmegaFold 双服务并行，实际运行发现：
1. ESMFold 对 silk 融合蛋白 pLDDT 极低（<0.30），不可靠
2. ESMFold 消耗 17GB GPU 显存，与 OmegaFold 争抢资源
3. 去掉 ESMFold 后，纯 OmegaFold 并发 1 反而更稳定（OmegaFold 同步推理阻塞事件循环，无法真正并行）

---

## 7. 用户反馈

### 关键决策点

| 反馈 | 影响 |
|------|------|
| "BepiPred 太慢了，先用快的跑一遍，取前 30% 跑 BepiPred" | 引入了 TemStaPro 预筛机制，将 BepiPred3 的 50K 输入降为 15K |
| "ESMFold 用处不大，我认为可以只跑 OmegaFold" | Round 5 从双服务改为纯 OmegaFold，节省 ~50% GPU 时间 |
| "看 construct 分能不能拉开差距，不能就直接忽略" | 移除了 construct_composite 的 0.50 权重，改用纯 SASA+A3D 排名 |
| "强制使用 Docker" | 所有服务 Docker 化，解决了原生执行的环境漂移问题 |

### 用户关注的核心问题

1. **效率优先**: 多次要求优化执行顺序（TemStaPro 预筛、去掉 ESMFold）
2. **数据驱动决策**: 要求先看数据分布再定权重，而非预设加权
3. **双通道合规性**: 始终关注 Top/Bottom 两套输出

---

## 8. 技术性困难

### 并发与超时

| 问题 | 根因 | 解决 |
|------|------|------|
| BepiPred3 量子超时 | GPU 服务单请求约 115s/50-seq 批，Semaphore=5 让排队请求超过 300s 超时 | 改为 Semaphore=1，超时 600s |
| ToxinPred3 挂死 | sklearn ExtraTrees 单线程，asyncio.wait_for 不能中断 C 扩展 | batch_size ≤ 10 + socket 超时 |
| OmegaFold 阻塞事件循环 | 同步 PyTorch CUDA 推理在 async def 中阻塞 uvicorn | 客户端 Semaphore=1 串行化 |
| asyncio.gather 全部取消 | 单任务异常导致 gather 取消其他任务 | `return_exceptions=True` + 每个 task 独立 try/except |

### Docker 代理间歇性挂死

**问题**: httpx 通过 docker-proxy（127.0.0.1:PORT）访问容器时，长耗时请求间歇性挂死。服务端在处理请求，但客户端收不到响应。

**诊断**: `ss -tnp | grep 8002` 显示连接建立但无数据传输。容器内 curl 正常，宿主机 127.0.0.1 挂死。

**解决**: 使用 `docker inspect` 获取容器桥接 IP（172.18.0.x），绕过 docker-proxy 直连。通过 `{SERVICE}_HOST` 环境变量注入。

### GPU 显存争用

同时运行多个 GPU 服务（ESMFold 17GB + BepiPred3 6GB + OmegaFold 11GB）超过 48GB 显存上限。解决方案：
- 按需启动，只启动当前阶段需要的服务
- AnOxPePred 的 PyTorch CUDA 缓存占用 34GB 显存，需停掉释放
- ESMFold 的 `.cuda()` 在显存不足时静默挂死（而非抛出异常）

---

## 9. Docker 问题修复

### Docker Hub 国内不可达

| 问题 | 影响 | 解决方案 |
|------|------|---------|
| `registry-1.docker.io` 超时 | 所有 Docker 构建失败 | 配置 Daocloud 镜像加速器 (`docker.m.daocloud.io`) |
| `continuumio/miniconda2` 403 禁止 | Aggrescan3D 无法构建 | 改用 `ghcr.io/mamba-org/micromamba` (GitHub Container Registry，国内可访问) |
| `python:2.7-slim` 仓库归档 | Debian Buster apt 源返回 404 | 使用基于 `micromamba` 的镜像（自动管理 Python 环境） |
| `mambaorg/micromamba` 不在白名单 | Daocloud 镜像拒绝 | 从 `ghcr.io/mamba-org/micromamba` 直接拉取 |

### 最终 Docker 服务清单

共 12 个微服务 Docker 镜像构建并运行：

| 服务 | 端口 | 类型 | 备注 |
|------|------|------|------|
| anoxpepred | 8001 | CPU | 抗氧化预测 |
| bepipred3 | 8002 | GPU | B 细胞表位预测 |
| toxinpred3 | 8003 | CPU | 毒性预测 |
| hemopi2 | 8004 | CPU | 溶血性预测 |
| algpred2 | 8005 | CPU | 过敏性预测 |
| mhcflurry | 8006 | CPU | MHC 结合预测 |
| temstapro | 8007 | CPU | 热稳定性预测 |
| sodope | 8008 | CPU | 物理化学性质 |
| omegafold | 8204 | GPU | 3D 结构预测 |
| esmfold | 8203 | GPU | 3D 结构预测（未用于最终结果） |
| sasa | 8101 | CPU | 溶剂可及表面积 |
| aggrescan3d | 8102 | CPU | 聚集倾向性 |

### 关键经验

1. **Docker 构建必须在 tools/ 目录下执行**（`cd tools && docker compose ...`），否则找不到 compose 配置
2. **GPU 服务必须按需启动**，一次性启动全部 4 个 GPU 服务会导致显存溢出
3. **Docker 桥接 IP 直连** 比 localhost 端口映射更可靠，尤其是长耗时请求
4. **镜像加速器有限制**：Daocloud 镜像有白名单，不在白名单的镜像需从 GHCR 或其他源拉取
5. **Python 2.7 的 conda 包** 在现代 Docker 环境中的兼容性问题是最大障碍，`micromamba` 是最轻量的解决方案

---

*Generated by Claude Code — iGEM-silk pipeline review*
