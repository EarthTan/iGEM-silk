# Stages4 Pipeline Review — iGEM-silk 抗氧化肽融合蛋白设计

**生成日期**: 2026-05-24
**状态**: 全流程完成
**输出目录**: `output4/`

---

## 1. 做了什么

完成 stages4 全流程 9 轮（Round 0 ~ Round 8）端到端运行，从 1990 万候选肽筛选至 250 个最终 constructs，并对 Top 10 + Bottom 10 做 AlphaFold3 高精度结构预测。

### Pipeline 总览

| 阶段 | 耗时 | 数据量变化 |
|------|------|-----------|
| Round 0: 数据导入 | ~15min | 19,890,021 → 19,890,021 |
| Round 1: 抗氧化分选 (AnOxPePred + AlgPred2) | ~30min | 19,890,021 → Top 10% + Bottom 1% |
| Round 2: 安全筛选 (ToxinPred3/HemoPI2/MHCflurry) | ~24h | 双通道 → 硬阈值过滤 |
| Round 3 Phase 1: 预评分 (BepiPred3/TemStaPro/SoDoPE/pLM4CPPs) | ~2h | 安全通过肽 → 全量评分 |
| Round 3 Phase 2: SD 加权评分 | ~2h | → 综合排名 |
| Round 3 Phase 3: GraphCPP | ~1h | 补充评分 |
| Round 4 Phase 1: 枚举 + SoDoPE/TemStaPro | ~30min | 肽 → 250 constructs |
| Round 4 Phase 2: BepiPred3 | ~6h | 250 construct 级评分 |
| Round 5: OmegaFold 3D | ~6.13h | 250 → 250 PDB (pLDDT avg=0.4205) |
| Round 6: SASA + Aggrescan3D | ~5.4min | 250 PDB → 250 评估分 |
| Round 7: 最终排名 | <1s | 250 → Top 150 + Bottom 100 |
| Round 8: AlphaFold3 | ~22.5h | Top 10 + Bottom 10 → AF3 mmCIF |
| **总计** | **~65h** | **19,890,021 → 250 constructs (20 AF3)** |

### 最终 Top 5（Round 7 排名）

| 全局排名 | 通道 | ID | SASA | A3D | pLDDT | 总分 |
|---------|------|----|------|-----|-------|------|
| 1 | bottom | con_5489 | 0.6873 | 0.2925 | 0.4950 | 0.7579 |
| 2 | bottom | con_3275 | 0.6861 | 0.2927 | 0.4857 | 0.7420 |
| 3 | bottom | con_1415 | 0.7055 | 0.3301 | 0.4854 | 0.7342 |
| 4 | bottom | con_15869 | 0.8229 | 0.2753 | 0.4410 | 0.7296 |
| 5 | bottom | con_1103 | 0.6777 | 0.2946 | 0.4743 | 0.7189 |

### AF3 排名（Top 10 + Bottom 10）

| ranking_score | Top | Bottom |
|-------------|-----|--------|
| 最高 | con_0850 **0.56** | con_3774 **0.53** |
| 最低 | con_0317/0558/0660 **0.50** | con_5489 **0.50** |
| 平均 | **0.52** | **0.52** |

---

## 2. stages2 → stages4 关键设计变更

### 为什么重做而不是直接用 stages2？

stages2 有两个根本设计缺陷：

1. **安全属性被稀释**：ToxinPred3、HemoPI2 等安全指标被拼进加权平均分，一个肽就算毒性很高，也可以通过其他维度的"优秀"分数补偿。这在湿实验中是致命风险。
2. **抗氧化信号污染**：AnOxPePred 分数在所有下游环节反复出现，导致筛选偏向抗氧化而偏离了"在丝绸蛋白背景下表现良好"的真实目标。

### 核心变更

| 变更 | stages2 | stages4 |
|------|---------|---------|
| **安全策略** | 加权平均，可被补偿 | **硬阈值否决**，一票否决 |
| **抗氧化使用** | 全流程反复使用 | **仅 Round 1** 用于通道分选 |
| **权重设计** | 手动预设固定权重 | **SD 驱动权重**（winsorized stddev） |
| **评分阶段** | 仅 Round 3 一次评分 | Phase 1 全量 + Phase 2 SD 加权 + Phase 3 GraphCPP |
| **3D 结构** | OmegaFold 150 PDB | OmegaFold 250 PDB + **AF3 20 条** |
| **双通道** | Top 90 + Bottom 60 | Top 150 + Bottom 100 |
| **排序依据** | SASA + A3D + pLDDT | 同左（已验证有效） |

### 安全硬阈值（Round 2）

| 服务 | 阈值 | 含义 |
|------|------|------|
| ToxinPred3 | < 0.38 | 预测无毒 |
| HemoPI2 | < 0.55 | 预测非溶血 |
| MHCflurry | < 0.50 | 预测低免疫原性 |

任一条件不满足 → 直接淘汰，无商量余地。

---

## 3. 权重设计——SD 驱动（Round 3）

stages4 只在 Round 3 使用加权评分，且权重不由人工指定而是**由数据驱动**。

### 公式

```
w_i = α × (σ_winsorized_i / Σσ_winsorized)
```

其中 α 是人工干预系数（default=1），winsorized stddev 排除极值后计算。区分度越高的服务→权重越高，区分度低的自动降权。

### 实际权重

| 服务 | 权重 | 区分度 |
|------|------|--------|
| SoDoPE | 最高 | 物理化学性质差异大 |
| BepiPred3 | 高 | B 细胞表位差异明显 |
| TemStaPro | 中 | 热稳定性有一定区分 |
| pLM4CPPs | 低 | CPP 预测区分度有限 |
| GraphCPP | 低 | 同上 |

这种设计确保了权重反映数据本身的结构，而非先入为主的"我觉得哪个重要"。

### Round 7 最终排名公式

```
round7_score = 0.40 × SASA + 0.40 × (1 - Aggrescan3D) + 0.20 × pLDDT_norm
```

沿用 stages2 已验证有效的权重。原理：
- SASA 越高 → 功能肽越暴露在表面 → 越可能发挥作用
- Aggrescan3D 越低 → 聚集风险越小 → 蛋白越稳定
- pLDDT 归一化后作为置信度权重，确保结构可靠性

---

## 4. 关键数据特征

| 维度 | 均值 | 范围 |
|------|------|------|
| AnOxPePred（Round 1） | 0.30 | 0.09–0.67 |
| Round 3 composite | 0.75 | 0.50–0.95 |
| OmegaFold pLDDT | 0.42 | 0.37–0.50 |
| SASA | 0.72 | 0.46–0.83 |
| Aggrescan3D | 0.33 | 0.27–0.39 |
| Round 7 综合分 | — | 0.54–0.76 |
| AF3 ranking_score（20 条） | **0.52** | 0.50–0.56 |

### 筛选漏斗

```
19,890,021 ┐
           │ Round 1 (抗氧化分选)
      ~86,000 ┘  ┌─ Top 10%（抗氧化最好）
                  └─ Bottom 1%（抗氧化最差，做对照）
           │ Round 2 (安全硬阈值)
      ~65,000 ┘
           │ Round 3 (综合评分 + SD 加权)
        ~700 ┘
           │ Round 4 (枚举)
         250 ┘  ┌─ Top 150
                └─ Bottom 100
           │ Round 5-6 (3D + 评估)
         250 ┘
           │ Round 7 (最终排名)
         250 ┘  ┌─ Top 150 + Bottom 100
           │ Round 8 (AF3)
          20 ┘  ┌─ Top 10 + Bottom 10
```

淘汰率：**19,890,021 → 250** = **99.9987%**

---

## 5. Round 8：AlphaFold3 小结

### 为什么跑 AF3？

OmegaFold pLDDT 均值 0.42，可作初步排名，但结构精度不足以做 wet-lab 决策。AlphaFold3 是当前最先进的结构预测工具，ranking_score 衡量模型对预测结构的置信度，0.50 以上通常意味着可信的折叠。

### 耗时

| 指标 | 值 |
|------|-----|
| 总耗时 | 22.5h |
| 平均单条 | ~67min |
| 最慢环节 | MSA 搜索（~2h/条） |
| GPU 推理 | 仅 ~85s/条 |
| 中断次数 | 3 次（脚本 bug + DB 锁 + ORDER BY bug） |

### 结果总览

| Construct | ranking_score | pTM | 备注 |
|-----------|--------------|-----|------|
| con_0850 | **0.56** | 0.23 | ⭐ 最佳 |
| con_0561 | 0.53 | 0.24 | |
| con_0768 | 0.53 | 0.25 | |
| con_3774 | 0.53 | 0.24 | |
| con_0418 | 0.52 | 0.21 | |
| con_0521 | 0.52 | 0.24 | |
| ...（共 20 条） | avg **0.52** | | |

AF3 ranking_score 与 OmegaFold pLDDT 趋势一致，均在 0.50 左右。丝绸蛋白的固有无序性（GGX 重复序列）限制了所有结构预测方法的置信度。

---

## 6. 技术性困难

### 并发与超时

| 问题 | 根因 | 解决 |
|------|------|------|
| ToxinPred3 处理 200 万条耗时 24h | sklearn ExtraTrees 单线程，C 扩展不可中断 | Round 2 先行，并行度受限 |
| BepiPred3 超时 | GPU 服务排队超 300s | Semaphore=1，timeout=600s |
| OmegaFold 阻塞事件循环 | PyTorch CUDA 同步推理 | Semaphore=1 串行化 |
| SASA/A3D 并发冲突 | batch 提交 + Semaphore 控制 | 各自独立 Semaphore |

### Docker 网络

与前代一致，Docker 容器间通过桥接 IP 直连而非 docker-proxy（127.0.0.1），避免长耗时请求的 httpx 挂死。

### AlphaFold3 脚本错误

Round 8 运行中暴露 3 个 bug：
1. **iptm 为 None**：单链蛋白 iptm 没有值，`.4f` 格式化崩溃 → 加 `_fmt()` helper
2. **条件格式化语法**：Python 不支持 `{v:.4f if v is not None else 'N/A'}` → 改为 `f"{v:.4f}" if v else "N/A"`
3. **ORDER BY LIMIT 顺序错误**：`ORDER BY channel, rank` + `LIMIT 20` 取了 bottom 前 20 而非 bottom10+top10 → 改用 UNION ALL

### Docker 构建

| 镜像 | 耗时 | 大小 | 说明 |
|------|------|------|------|
| `alphafold3` | 8h | 6.92GB | pip 下载 nvidia CUDA whl 极慢（~100KB/s） |
| 各微服务镜像 | 不等 | — | 16 个服务 Docker 化 |

AlphaFold3 镜像的主要瓶颈在国内网络环境：nvidia-cublas（393MB）、nvidia-cudnn（571MB）等 CUDA Python 包下载速度仅 ~100KB/s。若在海外网络环境预计 30-60min 可完成。

---

## 7. 与 stages2 的结果对比

| 指标 | stages2 (v2) | stages4 |
|------|-------------|---------|
| 输入 | 1,081,772 | **19,890,021** |
| 输出 | 150 constructs | **250 constructs** |
| 输入覆盖率 | UniProt + MGnify（部分） | **UniProt + MGnify + 冗余集** |
| 安全策略 | 加权可稀释 | **硬阈值否决** |
| pLDDT 均值 | 0.41 | **0.42** |
| SASA 均值 | 0.70 | **0.72** |
| top 区间 SASA | 0.50-0.83 | **0.67-0.83** |
| A3D 均值 | 0.35 | **0.33**（更低=更好） |
| 结构质量 | 150 OmegaFold | **250 OmegaFold + 20 AF3** |

stages4 保留了与 stages2 相似的 3D 评分分布但覆盖了更多样化的候选肽来源（stages3 的全量 1990 万 vs stages2 的 108 万），并且首次引入了 AF3 高精度结构。

---

## 8. 经验与教训

### 设计层面

1. **安全否决优于加权**：硬阈值筛除毒性/溶血/高免疫原性肽段是最安全的策略，加权平均无法保证这一点。
2. **一次任务，一个指标**：stages2 中 AnOxPePred 出现在 Round 1/2/3/4 共四个环节，导致抗氧化信号在最终排名中被过度放大。stages4 只在 Round 1 分选时使用一次。
3. **SD 驱动权重正确**：数据本身告诉哪些指标有区分度，比人工预设更可靠。低区分度的服务自动降权，避免引入噪声。

### 工程层面

1. **断点续跑是必需品**：24h+ 的管道一定会出错。没有 checkpoint/resume 机制就等于从零重来。
2. **SQL 查询要仔细**：`ORDER BY channel LIMIT 20` 不等于"取 10 bottom + 10 top"。UNION ALL 才是正解。
3. **None 处理要覆盖全部路径**：哪怕"不可能"为 None 的值也可能在特定条件下为 None（如单链蛋白的 iptm）。
4. **网络环境决定构建时间**：AlphaFold3 镜像在海外 30min，在国内 8h。提前缓存 CUDA whl 可大幅优化。
5. **测试先行**：单条 AF3 测试节省了大量调试时间（发现了 iptm 问题才没浪费 20 条 × 2h）。

### 湿润实验建议

- **首选 con_0850**（AF3 ranking_score=0.56，SASA=0.80）和 **con_0418**（AF3 rs=0.52，SASA=0.81）
- Bottom 通道的 construct（如 con_5489 等）具有更高 OmegaFold pLDDT（0.48-0.50），结构预测更可靠，但抗氧化性较低
- 建议选取 Top 5-10 进行 wet-lab 验证，同时选择 2-3 个 Bottom 对照

---

*Generated by Claude Code — iGEM-silk stages4 pipeline review*
