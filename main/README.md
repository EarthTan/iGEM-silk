# main — 融合蛋白设计流水线

## 概述

`main/` 是 iGEM-silk 项目的编排层，负责：

1. 从 `data/` 加载丝素蛋白骨架、linker、功能肽数据
2. 按理化性质预筛选功能肽
3. 超级枚举所有插入位点 × 肽 × linker 的 construct
4. 根据结构规则（禁入区）预过滤 construct
5. 调用 `tools/` 下的微服务对肽/construct 进行评分
6. 硬过滤（毒性/过敏原/溶血） + 综合评分排序

所有步骤的输出写入 `output/`，每一步可独立追溯验证。

## 运行

```bash
# 根目录下
python main.py
```

无 CLI 参数，直接运行。默认读取 `data/silk.fasta`、`data/linker.fasta`、`data/function.csv`。

微服务未启动时，Step 1–4 正常运行（枚举 + 预过滤），Step 5–7 自动跳过。

## 模块

| 文件 | 职责 |
|------|------|
| `config.py` | 所有可调参数集中管理：微服务端口/URL、过滤阈值、评分权重 |
| `data_loader.py` | 解析 `data/` 下的 FASTA 和 CSV 文件 |
| `enumeration.py` | 肽理化性质计算、预筛选、禁入区扫描、construct 枚举、CSV/JSON 输出 |
| `client.py` | 异步 HTTP 客户端，调用微服务的 `/predict/batch` 接口 |
| `pipeline.py` | 7 步流水线编排，每步输出到 `output/` |

## 配置要点

编辑 `config.py` 即可调整：

- **微服务地址**：`SERVICE_HOST`（默认 127.0.0.1）和各服务端口（8001–8010）
- **肽预筛选**：`PEPTIDE_MIN_LENGTH` / `PEPTIDE_MAX_LENGTH`、`PEPTIDE_MAX_GRAVY`、电荷范围
- **硬过滤阈值**：`HARD_FILTERS` 中每个服务的 threshold
- **评分权重**：`SCORE_WEIGHTS`，`SCORE_INVERT` 标记反向指标（如 MHCflurry）
- **禁入区规则**：`POLY_ALA_MIN_LEN`、`CYS_CLUSTER_WINDOW`、`HYDROPHOBIC_CORE_THRESHOLD`
- **输出数量**：`TOP_N`（默认 20）

## 输出文件

运行后 `output/` 下的文件：

```
step01_loaded_data.json           # 加载数据摘要
step02_prefilter_peptides.json    # 肽预筛选结果（每条肽的理化性质+通过/淘汰+原因）
step03_enumeration_summary.json   # 枚举统计
step03_enumerated_constructs.csv  # 全部 construct 列表
step04_prefilter_summary.json     # 禁入区过滤统计
step04_passed_constructs.csv      # 通过预过滤的 construct
step04_failed_constructs.csv      # 淘汰的 construct + 淘汰原因
step05_service_scores_summary.json# 微服务评分摘要（需微服务运行）
step05_peptide_scores.json        # 每条肽在各服务的分数
step05_scored_constructs.csv      # 带评分的 construct
step06_hard_filter_summary.json   # 硬过滤统计
step06_passed_constructs.csv      # 通过硬过滤的 construct
step06_failed_constructs.csv      # 硬过滤淘汰 + 原因
step07_final_ranking.json         # 最终 Top-N 排名
step07_all_ranked.csv             # 全部 construct 排名
```

## 扩展

- **新增微服务**：在 `config.py` 的 `SERVICES` 中添加，并归入 `score` 或 `filter` 组
- **新增过滤规则**：在 `enumeration.py` 的 `filter_peptides()` 或 `find_forbidden_zones()` 中添加
- **新增枚举模式**（如双肽组合）：扩展 `generate_constructs()` 的 mode 参数
