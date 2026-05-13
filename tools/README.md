# 微服务

微服务分为三类：

- **Fasta 评分服务** (`fasta_service`)：输入 FASTA 序列，输出评分结果
- **3D 结构生成** (`structure_service`)：输入 FASTA 序列，输出三维结构模型（PDB）
- **PDB 评分服务** (`pdb_service`)：输入 PDB 结构，输出评分结果

### 微服务设计原则

1. **原作优先**。优先使用工具原作者的代码、设计思路、模型和实现方法，做到原汁原味。这代表了项目的学术背景，避免 AI 幻觉和搪塞工作。

2. **环境兼容**。本项目主要开发环境为最新版 macOS，实际部署使用 Ubuntu + RTX5880。对可 CUDA 加速的工具：配置 Dockerfile 方便 GPU 环境部署；代码自动检测 GPU 可用性并 fallback 到 CPU；仅 GPU 可运行的服务在 CPU 环境下明确报错。在Ubuntu上实际生产部署的时候，统一使用`docker compose`一键启动所有微服务。

3. **模型文件集中管理**。模型文件落在 `tools/<name>/models/`（服务专属）或 `tools/models/`（跨服务共享）。四种来源类型（Git 随仓库 / 首次下载 / pip 包 / 无需模型）详见下方「模型管理」章节。

4. **统一接口**。使用统一的 API 契约，与 `main/` 核心框架衔接。

5. **并发与高通量**。尽量做到高性能高速度预测，提高可处理数量级的范围。

### 启动方法

单个启动：

```bash
# 以 MHCflurry (8005) 为例
cd tools/MHCflurry
source .venv/bin/activate
python service.py
```

脚本启动：

```bash
./tools/start_all.sh           # 一键启动全部
./tools/start_all.sh status    # 查看状态
./tools/start_all.sh stop      # 停止全部
# 日志: tools/logs/<name>.log
```

Docker 启动：

```bash
cd tools && docker compose --profile gpu --profile cpu up -d
```

### 端口分配表

##### Fasta Service（8001+）

| 服务 | 端口 | 范围 | 作用 | 环境 | 模型 |
|------|------|------|------|------|------|
| AnOxPePred | 8001 | 短肽 2~30（CNN）/ 中肽 31~50（截断） | 抗氧化活性预测 | GPU/CPU | [Git] CNN · 1.3 MB |
| BepiPred-3.0 | 8002 | 短肽 ≥5 / 蛋白质 ≤5000 | B 细胞表位预测 | GPU/CPU | [共享] ESM-2 t33 · 2.5 GB |
| ToxinPred3 | 8003 | 短肽 ≥2 / 蛋白质（无上限） | 毒性预测 | CPU | [pip] ExtraTrees · 2 MB |
| HemoPI2 | 8004 | 短肽 ≤40（超出截断） | 溶血性预测 | GPU/CPU | [pip] ESM-2 t6 微调 · 30 MB |
| MHCflurry | 8005 | MHC-I 肽 8~15 | MHC-I 结合亲和力预测 | GPU/CPU | [下载] MHCflurry · 100 MB |
| pLM4CPPs | 8006 | 短肽 ≥5 / 蛋白质（无上限） | 细胞穿膜肽预测 | GPU/CPU | [共享] ESM-2 t6 · 30 MB + [Git] CNN+scaler · 2 MB |
| TIPred | 8007 | 短肽 ≥3 / 蛋白质（无上限） | 酪氨酸酶抑制肽预测 | CPU | [—] 启动时合成训练 |
| AlgPred2 | 8008 | 中肽~蛋白质（长序列优化） | 过敏原性预测 | CPU | [pip] RandomForest · 1 MB |
| GraphCPP | 8009 | 短肽 5~40（>100 精度下降） | 细胞穿膜肽预测（GNN） | GPU/CPU | [Git] GraphSAGE ckpt · 200 KB |
| TemStaPro | 8010 | 全范围 | 热稳定性预测（40–65°C） | GPU/CPU | [下载] ProtT5-XL · 2.3 GB + MLP×30 · 80 MB |
| SoDoPE | 8012 | 全范围 | 溶解度预测（SWI） | CPU | [—] 纯查表+数学运算 |

##### PDB Service（8101+）

| 服务 | 端口 | 范围 | 作用 | 环境 | 模型 |
|------|------|------|------|------|------|
| SASA | 8101 | 蛋白质/肽（无上限） | 溶剂可及表面积分析 | CPU | [—] FreeSASA 算法 |
| Aggrescan3D | 8102 | PDB 结构 | 结构聚集倾向分析 | CPU（Docker） | [Docker] A3D 镜像内置 |

##### Structure Service（8201+）

| 服务 | 端口 | 范围 | 作用 | 环境 | 模型 |
|------|------|------|------|------|------|
| AlphaFold3 | 8201 | 蛋白质/肽/DNA/RNA/配体 | 3D 生物分子结构预测 | GPU 必需（Docker，仅 Ubuntu） | [Docker] AF3 参数 + 遗传数据库 · TB 级 |
| PEP-FOLD4 | 8202 | 短肽 5~40 aa | 肽从头结构预测 | CPU（Docker） | [Docker] sOPEP 力场内置 |

### 模型管理

每个服务的模型文件通过以下四种方式之一获取：

| 来源 | 标签 | 位置 | 示例 |
|------|------|------|------|
| **Git 随仓库** | `[Git]` | `tools/<name>/` 下，直接 git 追踪（< 50 MB） | AnOxPePred CNN、GraphCPP GCN |
| **首次启动下载** | `[下载]` | `tools/<name>/models/`，`load_model()` 自动下载并 gitignored | MHCflurry、TemStaPro |
| **pip 包自带** | `[pip]` | `.venv/` 内，随 pip install 安装 | ToxinPred3、HemoPI2、AlgPred2 |
| **无需模型** | `[—]` | 纯算法或启动时合成训练 | TIPred、SoDoPE、SASA |
| **Docker 内置** | `[Docker]` | Docker 镜像内，不暴露到宿主机 | PEP-FOLD4、Aggrescan3D、AlphaFold3 |

**共享模型缓存：** `tools/models/` 存放被多个服务共用的模型，避免重复下载。当前共享内容：

```
tools/models/
  fair-esm/                     ← ESM-2 checkpoints（torch.hub 缓存）
    hub/checkpoints/
      esm2_t6_8M_UR50D.pt       ← pLM4CPPs + 未来其他服务
      esm2_t33_650M_UR50D.pt    ← BepiPred-3.0 + 未来其他服务
```

BepiPred-3.0 和 pLM4CPPs 均设置 `TORCH_HOME=tools/models/fair-esm/`，模型只下载一次。首次部署可用 `./tools/migrate_models.sh` 迁移已有文件。

共享池**仅存放被 ≥2 个服务使用的模型**。独有模型留在各自 `models/` 目录下，不提前搬入——按需扩容。

Docker 部署通过 volume 挂载 `tools/models/` 到容器内对应路径，模型不进入镜像。
