---
name: Waveflow 远程 API 代理微服务模式 v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [tamarind, remote-api, microservice, structure-prediction, esmfold, api-proxy, waveflow]
validated: true
---

# Gene Capsule: 远程 API 代理微服务模式

## Experience

**问题类型**: 将第三方云端 API（tamarind.bio）包装成本地微服务，使之与其他本地微服务（ESMFold、OmegaFold 等）使用相同的 API 契约和调用方式。

**核心策略**:

1. **工具类型在 URL 路径中指定**: `POST /predict/{tool}` 而非通过环境变量或请求体指定。一个服务实例可代理 esmfold、omegafold、alphafold 等多种工具，无需多实例部署。

2. **不使用模板 `create_app`**：远程 API 代理的服务逻辑（提交→轮询→下载）与本地模型运行的模板差异过大，应自定义 FastAPI 应用而非继承 `StructureService` 模板的 `create_app`。但仍复用 `StructureResult` 等数据模型保持接口一致。

3. **API 密钥管理**: `TAMARIND_API_KEY` 通过 `tools/.env` 统一管理，Docker Compose 通过 `environment:` 中 `${VAR:-}` 语法注入。本地开发需显式 `export`。

4. **异步 HTTP 客户端**: 使用 `httpx.AsyncClient` 管理到 tamarind 的 HTTP 连接池，设置合理的超时（连接 10s，请求 30s）。

5. **ZIP 结果处理**: tamarind 的 `/result` 返回预签名 ZIP 包下载 URL（字符串），需下载后解压提取 `model.pdb`。使用 `io.BytesIO` + `zipfile.ZipFile` 在内存中处理，不写临时文件。

### Tamarind REST API 响应格式备忘

| 端点 | 输入 | 输出格式 | 说明 |
|------|------|----------|------|
| `POST /submit-job` | `{ jobName, type, settings: { sequence } }` | `"<jobName> submitted to queue."`（字符串） | 不是 JSON！需 `resp.text.strip().strip('"')` |
| `GET /jobs?jobName=X` | 查询参数 | `{"0": {"JobName":"...", "JobStatus":"Complete|Running|In Queue", ...}, "statuses": {...}}` | 编号索引字典，非数组 |
| `POST /result` | `{ jobName }` | `"https://presigned-url/result-xxx.zip"`（JSON 字符串） | 必须去掉外层引号得到 URL |
| `POST /result` (batch) | `{ jobName, pdbsOnly: true }` | 同上 | `pdbsOnly` 仅适用于 batch 任务 |
| `POST /submit-batch` | `{ tool, batchName, jobs: [{ jobName, settings }] }` | 字符串 | 批量提交 |

### 关键参数

- 基础 URL: `https://app.tamarind.bio/api/`（末尾斜杠，代码中保证）
- 认证头: `x-api-key: <key>`
- 轮询间隔: 15s（可配置 `TAMARIND_POLL_INTERVAL`）
- 超时: 3600s（1 小时，可配置 `TAMARIND_TIMEOUT`）
- 结果 ZIP 内包含: `model.pdb`, `output.log`, `metrics.csv`, `metrics.parquet`, `ptm*.png`, `ptm*.pae.txt`

## Environment Fingerprint

- **任务域**: 将第三方云端生物学 API 包装为本地微服务，提供统一接口
- **输入特征**: FastAPI + httpx 异步 HTTP 客户端；无本地模型/GPU
- **约束条件**: 
  - tamarind API 响应格式非标准（字符串/特殊 JSON 结构），需逐个端点适配
  - 需要网络连接和有效 API key
  - 受远程排队和网络延迟影响（417aa ESMFold 约 200s）
- **不适用**:
  - 本地 GPU 推理的服务（应使用 `StructureService` 模板）
  - 需要低延迟/离线运行的生产环境
  - 未获取 tamarind API key 的场景

## Audit Record

- **验证方式**: iGEM-silk Waveflow 服务实际调用 tamarind ESMFold 预测 417aa 融合蛋白
- **测试用例**:
  1. 提交短序列 `MGRGGSGGY` → 提交确认字符串 → 轮询完成 → 下载 ZIP → 提取 `model.pdb` → 验证 PDB 格式 ✔
  2. 提交 417aa 全长 construct（con_0009）→ 201 秒完成 → 226 KB PDB 文件 ✔
  3. 无 API key 启动 → `/health` 返回 `status: "loading"` 和错误信息 ✔
- **成功率**: 100%（单次测试通过）
- **局限性**: 未测试 batch 端点；未测试非 ESMFold 工具类型；未测试超时/API 错误场景

## Usage

- **触发条件**: 需要将远程 API 包装为本地微服务，且该 API 是异步提交+轮询模式
- **调用方式**: 
  - 开发：`cd tools/Waveflow && TAMARIND_API_KEY=xxx uv run python service.py`
  - Docker：在 `tools/.env` 设置 `TAMARIND_API_KEY`，`docker compose --profile cpu up -d waveflow`
  - 请求：`curl -X POST http://localhost:8205/predict/esmfold -d '{"sequence":"..."}'`
- **注意事项**:
  - 每个 tamarind 端点的响应格式不同，实现前必须手动测试确认
  - `/submit-job` 返回字符串而非 JSON，`resp.json()` 会抛异常
  - `/jobs` 的 `JobStatus` 字段值：`Complete`、`Running`、`In Queue`、`Failed`、`Stopped`
  - `/result` 返回的 URL 是 JSON 字符串（带引号），需 `resp.text.strip().strip('"')`
  - 结果 ZIP 中找 `model.pdb`，不是 `structure.pdb` 或其他名字
  - `pdbsOnly` 参数仅适用于 batch 任务，单任务传此参数会报错
  - Docker Compose 中通过 `environment` + `${VAR:-}` 从 `.env` 注入变量，但仅对 `docker compose up` 有效，本地 `uv run` 需手动 export
