# 微服务

微服务大致分为三类：

- fasta评分服务 (fasta_service)：输入fasta，输出针对肽的评分结果
- 3D结构生成 (structure_service)：输入fasta，输出三维结构模型（PDB）
- PDB评分服务 (pdb_service)：输入PDB文件（和其他信息），输入评分结果

### 微服务设计原则

1. **原作优先**。优先使用工具原作者的代码、设计思路、模型和实现方法，做到原汁原味。这代表了项目的学术背景，以及避免AI幻觉和搪塞工作。（不能偷工减料！）
2. **环境兼容。**本项目的主要开发环境是最新版MacOS，但是实际使用的时候有高性能 Ubuntu（RTX5880）可以使用。因此，（仅仅）对于 **可以进行 CUDA 等加速的工具**：配置dockerfile，以方便在有GPU的设备上快速配置合适环境；代码本身做到自动检测系统和环境，在检测到存在可用环境的时候使用GPU加速；而在GPU环境不可用的时候，也能普通运行；如果真的只能在GPU上运行，则在CPU环境下自动报错。
3. **模型文件集中管理**：所有模型文件必须落在各工具的 `tools/<name>/models/` 下，统一 `.gitignore`。无论本地开发还是 Docker 部署，模型都从同一位置读写。

   四种来源类型：

   | 类型 | 标记 | 说明 | 例子 |
   |------|------|------|------|
   | **Git 随仓库** | `✅ 随仓库` | 小文件 (< 5 MB)，直接 git 追踪 | CNN ckpt, GCN 权重, scaler |
   | **首次启动下载** | `⬇ 首次下载` | 大文件 (> 10 MB)，`load_model()` 中自动下载到 `models/` 并 gitignored | ESM-2, ProtT5-XL, MHCflurry |
   | **pip 包自带** | `📦 pip 包` | 随 pip install 装在 `.venv/` 里，无需额外管理 | sklearn pkl, hemopi2 模型 |
   | **无需模型** | `—` | 纯算法或合成训练 | FreeSASA, TIPred |

   Docker 全部通过 volume 挂载 `models/`，模型从不打进镜像。
4. **统一接口**。使用统一的接口，和 `main/` 下的核心框架相衔接，保证 `main/` 能够正常调用。
5. **并发与高通量**。尽量做到高性能高速度预测，提高可处理数量级的范围。

### 启动方法

单个启动

```bash
# 以 MHCflurry (8005) 为例
cd tools/MHCflurry
source .venv/bin/activate
python service.py              # 默认端口
```

脚本启动

```bash
./tools/start_all.sh           # 一键启动全部
./tools/start_all.sh status    # 查看状态
./tools/start_all.sh stop      # 停止全部
# 日志: tools/logs/<name>.log
```

docker启动

```bash
cd tools && docker compose --profile gpu --profile cpu up -d
```

### 端口分配表

##### Fasta Service  (8001+)

| 服务 | 范围 | 作用 | 环境 | 模型依赖 | 端口 |
|------|------|------|------|------|------|
| AnOxPePred | 短肽（2~30，CNN 最优）/ 中肽（31~50，截断） | 基于深度学习模型预测肽序列的抗氧化活性 | 可 GPU 加速（TensorFlow，可选，已配置dockerfile） | ✅ CNN (~1.3 MB)<br>`anoxpepred_data/` — 随仓库 | 8001 |
| BepiPred-3.0 | 短肽（≥5，灵敏度较低）/ 蛋白质（≤5000） | 线性 B 细胞表位预测工具 | 可 GPU 加速（PyTorch，可选，已配置dockerfile） | ⬇ ESM-2 t33 (~2.5 GB)<br>`models/torch/hub/checkpoints/` — gitignored, Docker 挂载 | 8002 |
| ToxinPred3 | 短肽（≥2）/ 蛋白质（无上限） | 毒性预测工具 | CPU | 📦 ExtraTrees pkl (~2 MB)<br>pip 包内 `toxinpred3/model/` | 8003 |
| HemoPI2 | 短肽（≤40，超出截断为前40位） | 溶血性预测工具 | 可 GPU 加速（PyTorch，可选，已配置dockerfile） | 📦 ESM-2 t6 fine-tuned (~600 MB)<br>pip 包内 `hemopi2/Model/` | 8004 |
| MHCflurry | MHC-I 肽（8~15，针对此范围优化） | MHC I类肽结合亲和力预测工具 | 可 GPU 加速（PyTorch，可选，已配置dockerfile） | ⬇ MHCflurry 预训练模型 (~100 MB)<br>`models/` — gitignored, Docker 挂载 | 8005 |
| pLM4CPPs | 短肽（≥5）/ 蛋白质（无上限） | 细胞穿膜肽预测工具 | 可 GPU 加速（PyTorch，可选，已配置dockerfile） | ✅ CNN+scaler (~2 MB) `pLM4CPPs-main/models/`<br>⬇ ESM-2 t6 (~8 MB) `models/torch/hub/checkpoints/` — gitignored | 8006 |
| TIPred | 短肽（≥3）/ 蛋白质（无上限） | 预测酪氨酸酶抑制肽(TIP)活性 | CPU | — 无外部模型<br>sklearn 集成，启动时合成训练 | 8007 |
| AlgPred2 | 中肽 ~ 蛋白质（针对较长序列优化） | 过敏原性风险预测工具 - 基于随机森林模型的蛋白过敏原性预测 | CPU | 📦 RandomForest pkl (~1 MB)<br>pip 包内 `algpred2/model/` | 8008 |
| GraphCPP | 短肽（5~40 最优，>100 精度下降） | 基于图神经网络(GraphSAGE)的细胞穿透肽(CPP)预测工具 | 可 GPU 加速（PyTorch，可选，已配置dockerfile） | ✅ GCN ckpt (~200 KB) + RDKit<br>`model/checkpoints/` — 随仓库 | 8009 |
| TemStaPro | 短肽 ~ 蛋白质（全范围） | 蛋白质热稳定性预测 — ProtT5-XL 嵌入 + MLP 集成，预测 40–65°C 区间热稳定性 | 可 GPU 加速（PyTorch，可选，已配置dockerfile） | ⬇ ProtT5-XL (~3 GB) `models/prot_t5_xl/`<br>⬇ 30 MLP (~80 MB) `models/classifiers/`<br>均 gitignored, Docker 挂载 | 8010 |

##### PDB Service （8101+）
| 服务 | 范围 | 作用 | 环境 | 速度 | 模型依赖 | 端口 |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| SASA | 蛋白质 / 肽 （无上限） | 溶剂可及表面积分析 — FreeSASA Lee-Richards 算法，逐残基暴露度量化 | CPU（Python 原生） | ms/条 | 无 (FreeSASA 解析算法，不依赖 ML 模型) | 8101 |
| Aggrescan3D | 蛋白质 / 肽 PDB 结构 | 结构聚集倾向分析 — 原版 Aggrescan3D CLI，逐残基 A3D score 与聚集热点 | CPU（Docker 封装，需 `lcbio/a3d_server`） | 秒~分/条 | Docker 镜像内置 | 8102 |

##### Structure Service (8201+)
| 服务 | 范围 | 作用 | 环境 | 速度 | 模型依赖 | 端口 |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| AlphaFold3 | 蛋白质（无上限）/ 肽 / DNA / RNA / 配体 | 3D 生物分子结构预测 (Google DeepMind) | GPU 必需（NVIDIA，Docker 封装，仅 Ubuntu） | 分钟~小时/条 | AF3 模型参数 + 遗传数据库 (~TB 级)<br>需预先下载并通过 `-v` 挂载到容器 | 8201 |
| PEP-FOLD4 | 短肽（5~40 aa） | 肽从头结构预测 — sOPEP 力场 + 蒙特卡洛采样 | CPU（只有Docker 封装） | 分钟/条 | 无 (sOPEP 力场，Docker 镜像内置) | 8202 |
