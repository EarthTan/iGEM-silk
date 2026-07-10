# iGEM-silk 微服务工具库

iGEM 竞赛项目沉淀下来的**蛋白质/肽预测微服务集合**：20 个 FastAPI 微服务，覆盖功能肽评分与三维结构生成。

每个服务可被其他业务**独立调用**。本仓库仅提供工具，不提供完整流程（主流程已废弃，参见下方说明）。

---

## 仓库定位

- **是什么**：一个可独立启动的微服务工具库（FastAPI + uv 管理）
- **不是什么**：完整的丝素蛋白设计流水线（主流程代码已移除，仅保留服务组件）

> 历史背景：本仓库曾承载 iGEM 丝素蛋白融合功能肽设计项目的完整流程（候选肽生成 → 逐级筛选 → 3D 结构评估）。
> 流程部分代码（`main/`、`data/`、`output*`、`docs/`）已删除；本仓库现在以「微服务工具库」形态被其他业务复用。

---

## 服务总览

按用途分为三类，端口在 8001–8205 区间。每行端口是默认 `PORT` 环境变量，可覆盖。

### ① Fasta Service — 序列 → 评分

| 服务 | 端口 | 默认环境 | 简介 |
|------|------|---------|------|
| `AnOxPePred` | 8001 | GPU | 抗氧化肽预测 |
| `BepiPred-3.0` | 8002 | GPU | B 细胞线性表位预测 |
| `ToxinPred3` | 8003 | CPU | 肽毒性预测 |
| `HemoPI2` | 8004 | GPU | 溶血肽预测 |
| `MHCflurry` | 8005 | GPU | MHC-I 抗原递呈预测 |
| `pLM4CPPs` | 8006 | GPU | 细胞穿膜肽预测 |
| `TIPred` | 8007 | CPU | 酪氨酸酶抑制肽预测 |
| `AlgPred2` | 8008 | CPU | 过敏原性风险预测 |
| `GraphCPP` | 8009 | GPU | 细胞穿膜肽预测（GraphSAGE） |
| `TemStaPro` | 8010 | GPU | 蛋白热稳定性预测（ProtT5-XL） |
| `SoDoPE` | 8012 | CPU | 溶解度预测（SWI 指数） |

### ② PDB Service — PDB 结构 → 评分

| 服务 | 端口 | 默认环境 | 简介 |
|------|------|---------|------|
| `SASA` | 8101 | CPU | 溶剂可及表面积分析（FreeSASA） |
| `Aggrescan3D` | 8102 | CPU | 3D 聚集倾向分析（**需调 Docker 调 `aggrescan` 二进制**） |

### ③ Structure Service — 序列 → 3D 结构

| 服务 | 端口 | 默认环境 | 简介 |
|------|------|---------|------|
| `AlphaFold3` | 8201 | GPU | AlphaFold3 预测（**需调 Docker 调 `alphafold3` 镜像**） |
| `PEP-FOLD4` | 8202 | CPU | PEP-FOLD4 肽从头预测（**需调 Docker 调 `pepfold4` 镜像**） |
| `ESMFold` | 8203 | GPU | ESMFold 快速结构预测 |
| `OmegaFold` | 8204 | GPU | OmegaFold 结构预测 |
| `Waveflow` | 8205 | CPU | Tamarind.bio 云端 API 代理（需 `TAMARIND_API_KEY`） |

完整使用手册（含启动命令、依赖、模型、API 字段）见 [`tools/README.md`](tools/README.md)。

---

## 快速开始：启动一个服务

每个服务独立管理 Python 环境（`uv`），互不干扰。

```bash
# 1) 进入服务目录
cd tools/SASA

# 2) 第一次：装依赖（仅在该目录下创建 .venv）
uv sync

# 3) 启动（默认端口见上表，可用 PORT=xxxx 覆盖）
.venv/bin/python service.py
# 或
uv run python service.py
```

启动后访问：

- `GET /` — 服务元信息
- `GET /health` — 健康检查
- `POST /predict` — 预测（具体字段见各服务 README 或 `service.py` 中的 `create_app`）

---

## 共享资源

部分大型模型权重在多个服务间共享，集中存放在 `tools/models/`：

```
tools/models/
├── fair-esm/                      ← ESM-2 权重（11 GB，多服务共享）
│   └── hub/checkpoints/
│       ├── esm2_t6_8M_UR50D.pt          (~29 MB)   pLM4CPPs
│       ├── esm2_t33_650M_UR50D.pt       (~2.5 GB)  BepiPred-3.0
│       ├── esm2_t36_3B_UR50D.pt         (~5.3 GB)  ESMFold
│       └── esmfold_3B_v1.pt             (~2.6 GB)  ESMFold
└── omegafold/                     ← OmegaFold 权重（3 GB）
    └── model.pt                          (~1.5 GB)  OmegaFold
```

**这些权重是 `untracked` 文件，删除后重新下载需数小时到一天（学校网络下载极慢）。**
请勿用 `git clean`、`git checkout -- .`、`git restore .`、`git reset --hard` 等命令清理。详见 `AGENTS.md` 安全规则。

服务专属模型（如 MHCflurry、TemStaPro）存放在 `tools/<name>/models/`。

---

## 架构要点

- **独立环境**：每个 `tools/<name>/` 自带 `pyproject.toml` + `uv.lock`，独立 `.venv`。依赖隔离，互不冲突。
- **跨包导入**：所有 `service.py` 在启动时通过 `sys.path.insert(0, PROJECT_ROOT)` 把仓库根加进 `sys.path`，然后 `from tools.template import ...` / `from tools.utils import ...`。
  - 跨包导入目标：`tools/__init__.py`、`tools/utils.py`、`tools/template/` — **这些不要删**。
- **三类服务模板**（`tools/template/`）：
  - `fasta_service.py` — 序列 → 评分
  - `pdb_service.py` — PDB → 评分
  - `structure_service.py` — 序列 → 3D 结构
- **入口模式**：每个 `service.py` 末尾 `if __name__ == "__main__": uvicorn.run(app, host=HOST, port=PORT)`。
- **端口**：`HOST`/`PORT` 从环境变量读，默认值写在源码里。

---

## 仓库目录结构

```
iGEM-silk/
├── tools/                              # 20 个微服务 + 共享资源
│   ├── <service-name>/
│   │   ├── service.py                  # FastAPI 入口
│   │   ├── pyproject.toml              # 独立依赖声明
│   │   ├── uv.lock                     # 锁定版本
│   │   ├── .venv/                      # uv 创建（gitignored）
│   │   ├── Dockerfile                  # 历史部署方式（不再使用）
│   │   ├── models/                     # 某些服务的专属模型
│   │   └── README.md                   # 部分服务有
│   ├── template/                       # 三类服务模板（fasta/pdb/structure）
│   ├── models/                         # 跨服务共享的模型权重（untracked）
│   ├── utils.py                        # 跨服务工具
│   ├── __init__.py                     # 把 tools/ 暴露为 Python 包
│   ├── README.md                       # 微服务使用手册
│   ├── test_all_services.py            # 批量健康检查脚本
│   ├── migrate_models.sh               # 模型迁移工具
│   ├── Docker.md                       # 历史 Docker 部署文档
│   └── docker-compose.yml              # 历史编排文件（已不再使用）
├── AGENTS.md                           # Agent 行为约束 + 安全规则
├── README.md                           # 本文件
├── .gitignore
├── .gitattributes
├── .github/
├── .vscode/
└── .claude/
```

---

## 配套脚本

- `tools/test_all_services.py` — 批量对所有服务做 `/health` 检查
- `tools/migrate_models.sh` — 把分散在各服务 `models/` 下的 ESM 权重统一迁移到 `tools/models/fair-esm/`
- `tools/Docker.md` — 历史 Docker 部署说明（仅供查阅，新部署不再使用）

---

## 给 AI Agent

本仓库服务对象包含 AI Agent（参见 `AGENTS.md`）。在 Agent 视角下：

- **不要**尝试跑主流程（已删除）
- **不要**用 `git clean` / `git reset --hard` 等危险命令
- **不要**把 `tools/models/**/*.pt` 当成可清理文件
- **要**根据「实际用途」判断文件可否删除，不要只看 `git tracked` 状态
- 子服务通过 `cd tools/<name> && uv sync && .venv/bin/python service.py` 启动

详细约束见 `AGENTS.md`。
