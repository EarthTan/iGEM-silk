# tools/ — 微服务使用手册

`tools/` 下是 21 个 FastAPI 微服务 + 共享资源。本手册说明每个服务的**启动方式、依赖、模型来源、API 端点**。

顶层仓库介绍见 [`README.md`](../README.md)，Agent 行为约束见 [`AGENTS.md`](../AGENTS.md)。

---

## 启动方式（通用）

```bash
cd tools/<service-name>
uv sync                              # 第一次：装依赖
.venv/bin/python service.py          # 启动
# 或
uv run python service.py
```

环境变量：

- `PORT`：覆盖默认端口
- `HOST`：覆盖默认 host（默认 `0.0.0.0`）

启动后用 `curl http://localhost:<port>/health` 验证健康。

---

## 服务清单

### ① Fasta Service（8001+）— FASTA 序列 → 评分

| 服务 | 端口 | 默认环境 | 模型来源 | 范围 | 作用 |
|------|------|---------|---------|------|------|
| `AnOxPePred` | 8001 | GPU/CPU | [Git] CNN · 1.3 MB | 短肽 2–30 / 中肽 31–50（截断） | 抗氧化活性预测 |
| `BepiPred-3.0` | 8002 | GPU/CPU | [共享] ESM-2 t33 · 2.5 GB | 短肽 ≥5 / 蛋白质 ≤5000 | B 细胞表位预测 |
| `ToxinPred3` | 8003 | CPU | [pip] ExtraTrees · 2 MB | 短肽 ≥2 / 蛋白质（无上限） | 毒性预测 |
| `HemoPI2` | 8004 | GPU/CPU | [pip] ESM-2 t6 微调 · 30 MB | 短肽 ≤40（超出截断） | 溶血性预测 |
| `MHCflurry` | 8005 | GPU/CPU | [下载] MHCflurry · 100 MB | MHC-I 肽 8–15 | MHC-I 结合亲和力预测 |
| `pLM4CPPs` | 8006 | GPU/CPU | [共享] ESM-2 t6 · 30 MB + [Git] CNN+scaler · 2 MB | 短肽 ≥5 / 蛋白质（无上限） | 细胞穿膜肽预测 |
| `TIPred` | 8007 | CPU | [—] 启动时合成训练 | 短肽 ≥3 / 蛋白质（无上限） | 酪氨酸酶抑制肽预测 |
| `AlgPred2` | 8008 | CPU | [pip] RandomForest · 1 MB | 中肽~蛋白质（长序列优化） | 过敏原性预测 |
| `GraphCPP` | 8009 | GPU/CPU | [Git] GraphSAGE ckpt · 200 KB | 短肽 5–40（>100 精度下降） | 细胞穿膜肽预测（GNN） |
| `TemStaPro` | 8010 | GPU/CPU | [下载] ProtT5-XL · 2.3 GB + MLP×30 · 80 MB | 全范围 | 热稳定性预测（40–65°C） |
| `AMP-ESM` | 8011 | GPU/CPU | [移植] v0.1.0 TF/Keras h5 · 300 MB + [移植] 5×fold ckpt ×2 · 74 GB（imbalanced + balanced） + [下载] ESM-2 t33 · 2.5 GB | 短肽 2–200（两版本一致，超出拒绝） | 抗菌肽预测（v0.1.0 AMPlify / v0.2.0 ESM-2 双版本，balanced / imbalanced 都可用） |
| `SoDoPE` | 8012 | CPU | [—] 纯查表 + 数学运算 | 全范围 | 溶解度预测（SWI） |

**AMP-ESM 双版本说明**：默认 `v0.1.0`（原 AMPlify TF/Keras 基线，用户指定优先使用；balanced/imbalanced 均可），用 `AMP_ESM_VERSION=v0.2.0` 切换 ESM-2 版（balanced/imbalanced 也均可）。`AMP_ESM_MODE` 覆盖模式（两版本默认均为 imbalanced）。v0.2.0 权重约 74 GB 随服务提供（imbalanced + balanced 两组 5×fold ckpt，每组 ~37 GB）；v0.1.0 权重约 300 MB 随服务提供。v0.1.0 走 GPU（按 2026-08-05 部署，CUDA 12.6 toolkit + `tensorflow[and-cuda]==2.16.*` 装在 `.venv`，启动需 `export CUDA_HOME=/usr/local/cuda-12.6 PATH="$CUDA_HOME/bin:$PATH" LD_LIBRARY_PATH="$CUDA_HOME/lib64:$LD_LIBRARY_PATH"`）。

### ② PDB Service（8101+）— PDB 结构 → 评分

| 服务 | 端口 | 默认环境 | 模型来源 | 范围 | 作用 |
|------|------|---------|---------|------|------|
| `SASA` | 8101 | CPU | [—] FreeSASA 算法 | 蛋白质/肽（无上限） | 溶剂可及表面积分析 |
| `Aggrescan3D` | 8102 | CPU | [Docker] A3D 镜像内置（通过 `subprocess` 调 `aggrescan`） | PDB 结构 | 结构聚集倾向分析 |

### ③ Structure Service（8201+）— FASTA 序列 → 3D 结构

| 服务 | 端口 | 默认环境 | 模型来源 | 范围 | 作用 |
|------|------|---------|---------|------|------|
| `AlphaFold3` | 8201 | GPU 必需（Linux + Docker 运行时） | [Docker] AF3 参数 + 遗传数据库 · TB 级 | 蛋白质/肽/DNA/RNA/配体 | 3D 生物分子结构预测 |
| `PEP-FOLD4` | 8202 | CPU（Docker 运行时） | [Docker] sOPEP 力场内置 | 短肽 5–40 aa | 肽从头结构预测 |
| `ESMFold` | 8203 | GPU 必需 | [下载][共享] ESMFold 3B · 8 GB + ESM-2 t36 · 6 GB | 短肽~蛋白质（无上限） | 快速 3D 结构预测（~60× AF2） |
| `OmegaFold` | 8204 | GPU/CPU/MPS | [下载] OmegaFold ~3 GB（AWS S3 自动下载） | 短肽~蛋白质（无上限） | PLM + 几何变换器结构预测 |
| `Waveflow` | 8205 | CPU | [—] 纯远程 API，无需本地模型 | 全范围 | Tamarind.bio 云端代理（需 `TAMARIND_API_KEY`） |

---

## 模型来源（5 种）

| 来源 | 标签 | 位置 | 示例 |
|------|------|------|------|
| **Git 随仓库** | `[Git]` | `tools/<name>/` 下，直接 git 追踪（< 50 MB） | AnOxPePred CNN、GraphCPP GCN |
| **首次启动下载** | `[下载]` | `tools/<name>/models/`，`load_model()` 自动下载并 gitignored | MHCflurry、TemStaPro |
| **pip 包自带** | `[pip]` | `.venv/` 内，随 pip install 安装 | ToxinPred3、HemoPI2、AlgPred2 |
| **无需模型** | `[—]` | 纯算法或启动时合成训练 | TIPred、SoDoPE、SASA |
| **Docker 内置** | `[Docker]` | Docker 镜像内，不暴露到宿主机；wrapper 服务通过 `subprocess` 调用 | PEP-FOLD4、Aggrescan3D、AlphaFold3 |

**共享模型缓存**：`tools/models/` 存放被多个服务共用的模型权重，避免重复下载。当前共享内容：

```
tools/models/
├── fair-esm/                          # ESM 系列权重（torch.hub 缓存，约 11 GB）
│   └── hub/
│       ├── checkpoints/               # 权重文件（.pt）
│       │   ├── esm2_t6_8M_UR50D.pt
│       │   ├── esm2_t33_650M_UR50D.pt
│       │   ├── esm2_t36_3B_UR50D.pt
│       │   ├── esmfold_3B_v1.pt
│       │   └── *-contact-regression.pt
│       └── facebookresearch_esm_main/ # torch.hub 自动克隆的 fair-esm 源码
└── omegafold/
    └── model.pt                       # OmegaFold release1 权重（约 3 GB）
```

**模型清单**（大小为本次实测）：

| 文件 | 实测大小 | 归属服务 | 获取方式 |
|------|---------:|---------|---------|
| `fair-esm/hub/checkpoints/esm2_t36_3B_UR50D.pt` | ~5.3 GiB | ESMFold（3B 主干） | 首次启动自动下载 |
| `fair-esm/hub/checkpoints/esmfold_3B_v1.pt` | ~2.6 GiB | ESMFold（结构头） | 首次启动自动下载 |
| `fair-esm/hub/checkpoints/esm2_t33_650M_UR50D.pt` | ~2.4 GiB | BepiPred-3.0 | 首次启动自动下载 |
| `fair-esm/hub/checkpoints/esm2_t6_8M_UR50D.pt` | ~29 MiB | pLM4CPPs | Git 跟踪 |
| `fair-esm/hub/checkpoints/*-contact-regression.pt` | 数 KB | 各 ESM 模型配套 contact 预测头 | 随主权重一起下载 |
| `omegafold/model.pt` | ~3.0 GiB | OmegaFold（model_idx=1） | 首次启动自动下载 |

> `model_idx=2` 的权重会落盘为同目录 `model2.pt`，当前未下载；HemoPI2 使用的 ESM-2 t6 与 AMP-ESM 使用的 ESM-2 t33（transformers 格式）都来自 HuggingFace 缓存，**不在** `tools/models/` 内（`tools/models/fair-esm/` 下的是 fair-esm/torch.hub 格式，二者不通用）。

BepiPred-3.0、pLM4CPPs 和 ESMFold 均设置 `TORCH_HOME=tools/models/fair-esm/`，OmegaFold 通过 `OMEGAFOLD_CACHE` 默认指向 `tools/models/omegafold/`，各模型只下载一次。首次部署可用 `./tools/migrate_models.sh` 迁移已有文件。

**注意事项**：

- `tools/models/` 下的权重体积大、下载成本高（学校网络下重新下载需数小时到一天），**请勿删除**；如确需清理，先列出清单并人工确认，禁止 `git clean` / `git checkout -- .` / `git reset --hard` 等命令波及此目录。
- 该目录若由 root 用户创建，属主可能为 `root`，普通用户启动的服务将无法写入缓存；遇到"模型无法落盘"时，先检查 `ls -ld tools/models tools/models/*`。

**共享池**仅存放被 ≥2 个服务使用的模型，或者体积较大的模型。独有且体积较小模型留在各自 `models/` 目录下，不提前搬入——按需扩容。

---

## 模型下载与镜像源配置

以下模型在首次启动时从海外 CDN 自动下载，在中国大陆网络环境可能失败。可通过设置环境变量覆盖下载地址（指向镜像或本地路径）：

| 服务 | 自动下载的模型 | 大小 | 默认源 | 覆盖环境变量 |
|------|---------------|------|--------|-------------|
| `ESMFold` | `esmfold_3B_v1.pt` | ~2.6 GB | `dl.fbaipublicfiles.com/fair-esm/` (Meta CDN) | `ESMFOLD_MODEL_URL` |
| `BepiPred-3.0` | `esm2_t33_650M_UR50D.pt` | ~2.5 GB | 同上 | `ESM2_URL` |
| `TemStaPro` | ProtT5-XL | ~3 GB | HuggingFace `Rostlab/prot_t5_xl_half_uniref50-enc` | `HF_ENDPOINT=https://hf-mirror.com` |
| `OmegaFold` | `release1.pt` | ~3 GB | `helixon.s3.amazonaws.com` (AWS S3) | `OMEGAFOLD_WEIGHTS_URL` |
| `HemoPI2` | ESM-2 t6（通过 pip） | ~29 MB | HuggingFace | `HF_ENDPOINT=https://hf-mirror.com` |
| `AMP-ESM` | ESM-2 t33 650M（transformers 格式） | ~2.5 GB | HuggingFace | `HF_ENDPOINT=https://hf-mirror.com` |

镜像源配置示例：

```bash
# 使用 HuggingFace 镜像（适用于 ProtT5-XL、HemoPI2 的 ESM-2）
export HF_ENDPOINT=https://hf-mirror.com

# 使用自定义模型 URL（适用于 ESMFold、BepiPred-3.0 的 fair-esm 模型）
export ESMFOLD_MODEL_URL=https://internal-mirror.example.com/models/esmfold_3B_v1.pt
export ESM2_URL=https://internal-mirror.example.com/models/esm2_t33_650M_UR50D.pt

# 使用自定义 OmegaFold 权重 URL
export OMEGAFOLD_WEIGHTS_URL=https://internal-mirror.example.com/omegafold/release1.pt

# 预下载方式：手动下载后放到共享缓存
# wget -P tools/models/fair-esm/hub/checkpoints/ \
#   https://dl.fbaipublicfiles.com/fair-esm/models/esmfold_3B_v1.pt
```

---

## GPU vs CPU 兼容性

以下服务在 docker-compose 中被标记为 `gpu` profile，但**代码本身有完整 fallback**，CPU 可跑（更慢）：

- `AnOxPePred`（TensorFlow 自动设备选择，缺模型时降级为规则）
- `HemoPI2` / `MHCflurry` / `pLM4CPPs` / `GraphCPP` / `TemStaPro`（PyTorch 自动设备选择）
- `OmegaFold`（CUDA > MPS > CPU 三档 fallback）

**GPU 强必需**：

- `ESMFold`（3B 模型需大显存）
- `AlphaFold3`（需 NVIDIA Docker + Linux）

---

## 必须 Docker 运行的服务（wrapper 调外部镜像）

以下 3 个服务**本身是 FastAPI 服务可以本地启动**，但它们的预测逻辑通过 `subprocess.run("docker run …")` **调用外部 Docker 镜像**——这是工具原作者定的接口，不是部署方式。

- **`AlphaFold3`** — 调 `docker run alphafold3`（NVIDIA Docker + Linux 必需）
- **`PEP-FOLD4`** — 调 `docker run pepfold4`（CPU 即可）
- **`Aggrescan3D`** — 调 conda Python 2.7 环境的 `aggrescan` 命令（推荐 Docker，因为 Python 2.7 + 原版 aggrescan3d 配环境较繁琐）

宿主环境需先安装对应外部镜像：

```bash
docker pull alphafold3
docker pull pepfold4
```

---

## 外部 API 服务

- **`Waveflow`** — 纯远程 API 代理。需在环境变量中提供 `TAMARIND_API_KEY`，否则会 401。
  ```bash
  cd tools/Waveflow
  uv sync
  TAMARIND_API_KEY=your_key_here .venv/bin/python service.py
  ```

---

## 配套脚本

### `tools/test_all_services.py`

批量对所有服务做 `/health` 检查。需要先按端口逐个启动服务。

### `tools/migrate_models.sh`

把分散在各服务 `models/` 下的 ESM 权重统一迁移到共享目录 `tools/models/fair-esm/`。**仅在迁移旧环境时使用**，新部署不需要。

```bash
./tools/migrate_models.sh        # 执行迁移
./tools/migrate_models.sh --dry-run  # 仅预览
```

---

## 跨包导入路径

所有 `service.py` 启动时自动把仓库根加进 `sys.path`：

```python
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
```

然后 `from tools.template import …` / `from tools.utils import …` 跨包引用。

**不要删除这些跨包导入目标**：

- `tools/__init__.py`
- `tools/utils.py`
- `tools/template/`（含三类服务模板）

---

## 调试技巧

```bash
# 1) 检查某个服务的健康
curl -v http://localhost:8101/health

# 2) 查看服务日志（前台启动时直接看 stdout）
cd tools/SASA
.venv/bin/python service.py

# 3) 用 PORT 启动多个实例
cd tools/ToxinPred3
PORT=8003 .venv/bin/python service.py &
PORT=8013 .venv/bin/python service.py &
PORT=8014 .venv/bin/python service.py &
```

---

## 历史与已废弃文件

- `tools/docker-compose.yml` — 历史 Docker 编排文件。仓库角色转为工具库后不再使用，但保留作为参考。
- `tools/<name>/Dockerfile` — 历史单服务 Docker 镜像。新部署不走 Docker（除 3 个调外部镜像的服务外）。
- `tools/Docker.md` — 历史 Docker 部署说明。

如果某个服务的 Dockerfile 与当前 pyproject.toml 不一致，以 pyproject.toml 为准（Dockerfile 可能已过时）。