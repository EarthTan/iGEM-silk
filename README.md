# iGEM-silk: 丝素蛋白融合功能肽设计平台

**iGEM 竞赛项目** — 计算筛选平台，用于设计融合功能肽的丝素蛋白（silk fibroin）重组蛋白。
通过 16 个微服务（ML 预测器 + 结构工具 + 远程 API 代理），从数亿条候选序列中逐级筛选最优功能肽。

---

## 目录

1. [项目概述](#1-项目概述)
2. [快速入门](#2-快速入门)
3. [Pipeline 版本总览](#3-pipeline-版本总览)
4. [微服务清单](#4-微服务清单)
5. [核心文档索引](#5-核心文档索引)
6. [知识库与学习记录](#6-知识库与学习记录)
7. [参考资料](#7-参考资料)

---

## 1. 项目概述

### 科学目标

以丝素蛋白为骨架，将具有特定功能（抗氧化、抗黑色素等）的短肽通过基因融合的方式插入/连接至骨架上，使重组蛋白兼具丝素蛋白的自组装/成膜能力与功能肽的生物活性，适用于护肤等外用场景。

### Pipeline 核心哲学

- **漏斗式筛选**：从海量候选序列（8.5 亿 → 最终 Top 100），逐轮收紧
- **轻者先行**：吞吐高的服务先跑，重服务留给少数候选
- **安全优先**：毒性/溶血/致敏等安全属性使用硬阈值独立淘汰
- **数据驱动权重**：基于分数分布的标准差计算权重，区分度好的指标自动获得高权重

### 技术栈

- **语言**：Python 3.11+（`from __future__ import annotations`）
- **包管理**：`uv` + `pyproject.toml`（根项目 + 每个微服务独立环境）
- **微服务**：FastAPI，Docker Compose 部署（GPU + CPU 双 profile）
- **状态管理**：DuckDB（stages3/4）、CSV 接力（stages2）
- **3D 结构**：OmegaFold（主力）、ESMFold、AlphaFold3

---

## 2. 快速入门

```bash
# 安装根项目依赖
uv sync

# 启动所有微服务（Docker）
cd tools
docker compose --profile gpu --profile cpu up -d

# 或按需启动单个服务
docker compose --profile cpu up -d anoxpepred algpred2

# 运行 Pipeline 阶段
uv run python -m main.stages2.round01_lightweight   # stages2
uv run python -m main.stages3.stage00_preprocess     # stages3

# 检查微服务健康状态
uv run python -c "from main.client import ServiceClient; import asyncio; print(asyncio.run(ServiceClient().check_health()))"
```

---

## 3. Pipeline 版本总览

项目经历了四个 Pipeline 迭代，各有不同的设计目标和数据规模。

### stages（初版）

| 项目 | 内容 |
|------|------|
| **数据量** | 1,843 条抗氧化肽 |
| **状态** | 7 阶段全部编写完成，部分运行 |
| **核心文档** | [`main/stages/PLAN.md`](main/stages/PLAN.md) — 漏斗设计哲学、微服务成本分析、GPU 显存管理 |

### stages2（生产版，已完成 ✅）

**1,081,772 → 90 Top + 60 Bottom 候选**，全流程 8 轮约 6.5 小时。

| 轮次 | 脚本 | 说明 | 耗时 |
|------|------|------|------|
| 0 | `step00_integrate.py` | 数据清洗（3-30aa 过滤、去重） | ~30s |
| 1 | `round01_lightweight.py` | AnOxPePred + AlgPred2 全量评分 | ~15min |
| 2 | `round02_scoring.py` | 纯 AnOxPePred 分选 Top 25K + Bottom 25K + ToxinPred3/HemoPI2/MHCflurry | ~63min |
| 3 | `round03_heavy.py` | +BepiPred3/TemStaPro → Top 80 + Bottom 10 | ~65min |
| 4 | `round04_enumerate.py` | 双通道枚举 + 360 constructs → 150 | ~13min |
| 5 | `round05_3d.py` | OmegaFold 3D 预测（150 PDB） | ~210min |
| 6 | `round06_pdb_eval.py` | SASA + Aggrescan3D 评估 | ~6min |
| 7 | `round07_final.py` | 双通道独立排名 → 90 Top + 60 Bottom | ~1min |

**复盘文档**：[`output2/REVIEW.md`](output2/REVIEW.md) — 完整回顾、权重设置、技术困难、Docker 问题修复

**设计文档**：
- [`main/stages2/PLAN.md`](main/stages2/PLAN.md) — 三轮递进评分、安全标记系统、Construct 级再评分
- [`main/stages2/PLAN2.md`](main/stages2/PLAN2.md) — 备选方案

### stages3（亿级扩展版，开发中 🚧）

**849M → 19.9M 候选**，使用 DuckDB + 方差感知权重。

| 阶段 | 脚本 | 说明 | 状态 |
|------|------|------|------|
| 0 | `stage00_preprocess.py` | FASTA 流式扫描 → 3-30aa 过滤 → AA 过滤 → DuckDB | ✅ 完成 |
| 1 | `stage01_lightweight.py` | AnOxPePred + AlgPred2 分批评分 | ✅ 代码就绪 |
| 2 | 待实现 | 全量 9 服务评分 + 方差感知定权 | ⏳ |
| 3-6 | 待实现 | 枚举 → 3D → PDB 评估 → 最终排名 | ⏳ |

**关键创新**：
- **方差感知权重**：用 winsorized 标准差计算权重，区分度好的指标自动获得高权重
- **按需启动 Docker**：每 stage 只启动实际依赖的微服务
- **DuckDB 统一状态**：14 张表管理所有中间数据

**规划文档**（`main/stages3/plan/`）：
| 文档 | 内容 |
|------|------|
| [`PLAN.md`](main/stages3/plan/PLAN.md) | 总体路线图：六阶段漏斗、方差感知权重工作流、时间估算 |
| [`ARCHITECTURE.md`](main/stages3/plan/ARCHITECTURE.md) | 三层架构（编排层/执行层/服务层） |
| [`DB_SCHEMA.md`](main/stages3/plan/DB_SCHEMA.md) | 15 张表设计、DuckDB 选型理由 |
| [`DATA_PREP.md`](main/stages3/plan/DATA_PREP.md) | 数据源分析（UniProt 225M + MGnify 624M）、预处理策略 |
| [`TECH_REQUIREMENTS.md`](main/stages3/plan/TECH_REQUIREMENTS.md) | Docker 强制规范、asyncio 安全、并发控制 |

**实际架构**：[`main/stages3/ARCHITECTURE_AS_BUILT.md`](main/stages3/ARCHITECTURE_AS_BUILT.md) — 记录实际实现与规划的所有偏差

**完成记录**：[`main/stages3/DONE.md`](main/stages3/DONE.md) — Stage 0 全量运行报告（19.9M 候选写入，98.7min）

### stages4（层级筛选版，开发中 🚧)

**19.9M → Top 100 + Bottom 100**，stages2 问题的针对性修复版本。

**四个核心原则变更**：
1. **层级筛选，绝不跨属性加权平均** — 每轮使用单一标准
2. **安全属性硬阈值** — 毒性/溶血/致敏一票否决
3. **抗氧化只用一次** — 仅 Round 1 分选使用，后续轮次不参与
4. **可变权重（SD 驱动 + 手动系数 α）** — 唯一加权位置在 Round 3

| 轮次 | 脚本 | 说明 |
|------|------|------|
| 0 | `s4_round00_preprocess.py` | 数据预处理（复用 stages3） |
| 1 | `s4_round01_antioxidant_split.py` | AnOxPePred 排序 → Top 10% + Bottom 1% |
| 2 | `s4_round02_safety_screen.py` | ToxinPred3/HemoPI2/MHCflurry 硬阈值 |
| 3 | `s4_round03_deep_scoring.py` | SD 驱动 + 手动系数 α（唯一加权位置） |
| 4 | `s4_round04_enumerate.py` | Construct 枚举 + SoDoPE/TemStaPro |
| 5 | `s4_round05_3d.py` | OmegaFold 3D 预测 |
| 6 | `s4_round06_pdb_eval.py` | SASA + Aggrescan3D |
| 7 | `s4_round07_final.py` | 双通道独立排名 |

**设计文档**：[`main/stages4/PLAN.md`](main/stages4/PLAN.md) — 与 stages2 的对比、八轮漏斗设计、可变权重详解

---

## 4. 微服务清单

共 16 个微服务 + 3 个辅助服务，三类模板（FASTA 评分 / Structure 结构预测 / PDB 评分）。

### FASTA 评分服务（端口 8001-8012）

| 服务 | 端口 | 作用 | 环境 | 模型来源 | 模型大小 |
|------|------|------|------|---------|---------|
| **AnOxPePred** | 8001 | 抗氧化活性预测 | GPU/CPU | Git 跟踪 | 1.3 MB |
| **BepiPred-3.0** | 8002 | B 细胞表位预测 | GPU/CPU | 首次下载 | 2.5 GB |
| **ToxinPred3** | 8003 | 毒性预测 | CPU | pip 包 | 2 MB |
| **HemoPI2** | 8004 | 溶血性预测 | GPU/CPU | pip 包 | 30 MB |
| **MHCflurry** | 8005 | MHC-I 结合亲和力 | GPU/CPU | 首次下载 | 100 MB |
| **pLM4CPPs** | 8006 | 细胞穿膜肽预测 | GPU/CPU | 共享 ESM-2 + Git | 30 MB |
| **TIPred** | 8007 | 酪氨酸酶抑制肽预测 | CPU | 启动时合成训练 | — |
| **AlgPred2** | 8008 | 致敏原预测 | CPU | pip 包 | 1 MB |
| **GraphCPP** | 8009 | 细胞穿膜肽 GNN | GPU/CPU | Git 跟踪 | 200 KB |
| **TemStaPro** | 8010 | 热稳定性预测 | GPU/CPU | 首次下载 | 2.3 GB |
| **SoDoPE** | 8012 | 溶解度预测 | CPU | 纯算法 | — |

### PDB 评分服务（端口 8101-8102）

| 服务 | 端口 | 作用 | 环境 |
|------|------|------|------|
| **SASA** | 8101 | 溶剂可及表面积（FreeSASA） | CPU |
| **Aggrescan3D** | 8102 | 聚集倾向分析 | CPU Docker |

### 结构预测服务（端口 8201-8205）

| 服务 | 端口 | 作用 | 环境 |
|------|------|------|------|
| **AlphaFold3** | 8201 | 高精度结构预测 | GPU Docker |
| **PEP-FOLD4** | 8202 | 短肽从头结构预测（5-40 aa） | CPU Docker |
| **ESMFold** | 8203 | 快速结构预测（~60x AF2） | GPU |
| **OmegaFold** | 8204 | PLM+几何变换器结构预测 | GPU/CPU |
| **Waveflow** | 8205 | Tamarind.bio 云端 API 代理 | CPU |

### 微服务参考文档

| 服务 | 文档 |
|------|------|
| AnOxPePred | [`tools/AnOxPePred/references/anoxpepred_guide.md`](tools/AnOxPePred/references/anoxpepred_guide.md) |
| BepiPred-3.0 | [`tools/BepiPred-3.0/references/`](tools/BepiPred-3.0/references/) (4 篇) |
| ToxinPred3 | [`tools/ToxinPred3/references/`](tools/ToxinPred3/references/) (3 篇) |
| HemoPI2 | [`tools/HemoPI2/SKILL.md`](tools/HemoPI2/SKILL.md) |
| MHCflurry | [`tools/MHCflurry/references/`](tools/MHCflurry/references/) (3 篇) |
| GraphCPP | [`tools/GraphCPP/references/`](tools/GraphCPP/references/) (3 篇) |
| pLM4CPPs | [`tools/pLM4CPPs/references/SKILL.md`](tools/pLM4CPPs/references/SKILL.md) |
| AlgPred2 | [`tools/algpred2/references/`](tools/algpred2/references/) (4 篇) |
| TIPred | [`tools/Tipred/references/SKILL.md`](tools/Tipred/references/SKILL.md) |
| SoDoPE | [`tools/SoDoPE_paper_2020/references/SKILL.md`](tools/SoDoPE_paper_2020/references/SKILL.md) |
| TemStaPro | — |
| SASA | [`references/how-to-use-saas.md`](references/how-to-use-saas.md) |
| Aggrescan3D | [`tools/Aggrescan3D/README.md`](tools/Aggrescan3D/README.md) |

---

## 5. 核心文档索引

### 项目级文档

| 文件 | 说明 |
|------|------|
| [`CLAUDE.md`](CLAUDE.md) | 项目指令：开发命令、微服务部署、架构、Pipeline 状态 |
| [`AGENTS.md`](AGENTS.md) | **生产安全规则**：git 操作禁令（`git clean`/`checkout`/`reset --hard` 绝对禁止） |

### 设计理念

| 文件 | 说明 |
|------|------|
| [`main/docs/IDEA.md`](main/docs/IDEA.md) | Pipeline 设计哲学：漏斗筛选、三步走策略、微服务生命周期、缓存机制 |
| [`docs/PROGRAM 0.md`](docs/PROGRAM 0.md) | 探索性方案：科学背景（丝素蛋白结构、插入位点策略）、Dry Lab 工程架构 |
| [`main/stages/PLAN.md`](main/stages/PLAN.md) | 首版 Pipeline 设计：15 个微服务成本表、四阶段编排、GPU 显存管理、自适应逻辑 |

### API 规范

| 文件 | 说明 |
|------|------|
| [`main/docs/api/conventions.md`](main/docs/api/conventions.md) | API 规范手册：三种模板（FASTA/PDB/Structure）端点和响应格式、label 对照表、并发参数速查 |
| [`main/docs/api/quirks.md`](main/docs/api/quirks.md) | API 已知坑：SASA batch 响应格式差异、OmegaFold 阻塞事件循环、ToxinPred3 线程不安全 |
| [`main/docs/threshold.md`](main/docs/threshold.md) | 安全阈值：ToxinPred3 ≥0.38、AlgPred2 ≥0.30、HemoPI2 HC50 ≤100μM、TemStaPro |

### Docker 运维

| 文件 | 说明 |
|------|------|
| [`tools/Docker.md`](tools/Docker.md) | Docker 完全操作指南：23 个经验胶囊整合、构建/部署/监控/故障排查全流程 |
| [`tools/README.md`](tools/README.md) | 微服务目录：服务清单、端口分配表、模型管理策略、模型下载与镜像源配置 |

### 人工分析工具（面向湿实验研究者）

| 文件 | 说明 |
|------|------|
| [`docs/HUMAN.md`](docs/HUMAN.md) | 人工分析工具：Binding ddG 功能肽关键残基扫描、GROMACS MD 模拟 |
| [`references/how-to-use-saas.md`](references/how-to-use-saas.md) | SASA 服务使用指南：FastAPI + FreeSASA + Biopython |
| [`references/identify_the_embedded_sequence.md`](references/identify_the_embedded_sequence.md) | 序列位置到 PDB 残基编号的映射方法 |
| [`references/what-is-GROMACS.md`](references/what-is-GROMACS.md) | GROMACS 分子动力学模拟简介 |
| [`references/Inclusion body → Refolding.md`](references/Inclusion%20body%20→%20Refolding：核心问题与应对（简版）.md) | 包涵体复性核心问题 |

### 其他学术参考

| 文件 | 说明 |
|------|------|
| [`references/how_to_use_esm.md`](references/how_to_use_esm.md) | ESM 模型使用指南 |
| [`references/how-to-use-Alphafolw.md`](references/how-to-use-Alphafolw.md) | AlphaFlow 使用指南 |
| [`references/PROGRAM Old.md`](references/PROGRAM%20Old.md) | 原 OxidShield 计划存档 |

### Pipeline 输出报告

| 文件 | 说明 |
|------|------|
| [`output2/REVIEW.md`](output2/REVIEW.md) | stages2 全流程复盘：权重配置、数据漏斗、技术困难、Docker 问题修复 |
| [`output2/STATUS.md`](output2/STATUS.md) | stages2 进度指针 |
| [`output3/STATUS.md`](output3/STATUS.md) | stages3 环境状态 |
| [`output3/reports/stage0_report.md`](output3/reports/stage0_report.md) | stages3 Stage 0 处理报告 |

---

## 6. 知识库与学习记录

### 经验胶囊（`.agents/learnings/`）

**索引文件**：[`.agents/learnings/MEMORY.md`](.agents/learnings/MEMORY.md) — 全部 30+ 条经验记录的索引

**Docker 专项**（[`.agents/learnings/docker/`](.agents/learnings/docker/)）：

| 主题 | 文件 |
|------|------|
| Docker Hub 国内不可达（DaoCloud 镜像加速） | `docker/docker-hub-china-mirror.md` |
| Compose 构建原子性缺陷 | `docker/compose-atomic-build.md` |
| 容器内 Docker CLI 安装 | `docker/docker-cli-in-container.md` |
| Docker-outside-Docker 路径问题 | `docker/docker-outside-docker-paths.md` |
| Python 命名空间遮蔽 | `docker/python-namespace-shadowing.md` |
| slim 镜像缺少 C 编译依赖 | `docker/slim-image-build-deps.md` |
| Linux 大小写敏感 | `docker/linux-case-sensitivity.md` |
| latest 标签版本不确定性 | `docker/latest-tag-pinning.md` |
| Dockerfile COPY 遗漏审计 | `docker/dockerfile-copy-audit.md` |
| Dockerfile 路径一致性 | `docker/dockerfile-path-compose.md` |
| 批量故障审计 | `docker/batch-failure-audit.md` |

**Pipeline 工程**：

| 主题 | 文件 |
|------|------|
| asyncio.gather 异常传播 | `gep-asyncio-gather-exception-safety.md` |
| 双通道 Top/Bottom 设计 | `gep-dual-channel-top-bottom-pipeline.md` |
| 流水线阶段编排与检查点 | `gep-pipeline-stage-orchestration.md` |
| 结构预测置信度级联 | `gep-pipeline-confidence-cascade.md` |
| 权重迭代与数据驱动决策 | `gep-weight-iteration-data-driven.md` |
| Docker 桥接 IP 直连 | `gep-docker-container-bridge-ip.md` |
| 微服务网络绑定策略 | `microservice-host-binding.md` |

**GPU 与性能**：

| 主题 | 文件 |
|------|------|
| GPU 显存争用 | `gpu-memory-contention.md` |
| PyTorch CUDA 缓存残留 | `gep-pytorch-cuda-cache-gpu-memory-leak.md` |
| BepiPred3 GPU 超时调优 | `gep-bepipred3-gpu-timeout-tuning.md` |
| OmegaFold 同步推理阻塞 | `gep-omegafold-sync-inference-blocking.md` |
| ESMFold 依赖版本矩阵 | `gep-esmfold-dependency-matrix.md` |
| ToxinPred3 单线程挂死 | `gep-toxinpred3-concurrency-limit.md` |
| TemStaPro 预筛减少 GPU 瓶颈 | `gep-temstapro-prescreen-gpu-bottleneck.md` |

**结构预测**：

| 主题 | 文件 |
|------|------|
| ESMFold Docker 三层构建 | `gep-esmfold-docker-build.md` |
| Waveflow 远程 API 代理 | `gep-waveflow-remote-api-service.md` |
| Structure Service 模式 | `structure-service-pattern.md` |

---

## 7. 参考资料

### 学术论文（工具引用）

各微服务的学术出处可在对应 `tools/<name>/references/` 目录中找到：

- **ToxinPred3**: Rathore et al., 2024, *Computers in Biology and Medicine*
- **HemoPI2**: Rathore et al., 2025, *Communications Biology*
- **AlgPred2**: Sharma et al., 2021, *Briefings in Bioinformatics*
- **TemStaPro**: Pudžiuvelytė et al., 2024, *Bioinformatics*
- **SoDoPE**: 溶解度预测（SWI 方法）

### 丝素蛋白背景

- Heidebrecht & Scheibel, 2013 — 重组丝素蛋白表达
- Wohlrab et al., 2012 — RGD 功能化蜘蛛丝蛋白
- Xia et al., 2010 — E. coli 中丝素蛋白表达
