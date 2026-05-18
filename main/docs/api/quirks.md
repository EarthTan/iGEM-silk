# API 已知坑 & 处理方式

所有偏离模板标准行为的服务特性，以及 Pipeline 开发中遇到过的 bug。

---

## 1. SASA：Batch 响应评分在最顶层，不在 `result.score`

**现象**：SASA 单条端点返回 `{"success": true, "result": {"score": 0.76, ...}}`，但 Batch 端点返回 `{"success": true, "results": [{"peptide_id": "con_001", "score": 0.76, ...}]}`。Batch 结果里的 `score` 在顶层，**不是** `results[].result.score`。

**影响范围**：所有调用 `predict_pdb_batch("sasa", ...)` 的代码。

**处理方式**：解析 batch 结果时按 `r.get("score")` 取值，不是 `r["result"]["score"]`。

**验证**：`main/client.py` 的 `predict_pdb_batch` 返回原始 JSON，调用方自行适配。

---

## 2. SASA：缺少 `sequence` 参数返回 score=0

**现象**：SASA 需要知道功能肽的序列才能定位到 PDB 中的特定区域。不传 `sequence` 时，返回 `score=0.0`、`label="no_target"`。

**原因**：SASA 服务在 `score_pdb()` 中先用 FreeSASA 计算全结构逐残基 SASA，然后用 `sequence` 在 Biopython 解析的残基列表中定位肽区域，最后只统计肽区域的平均相对 SASA。没有 `sequence` 就无法定位，默认返回 0。

**处理方式**：调用 SASA 时必须在请求中包含 `sequence` 字段：
```json
{
  "pdb_content": "ATOM      1  N   ...",
  "sequence": "YVPLPNVPQG",
  "peptide_id": "con_001"
}
```

**验证**：调用 SASA `/predict/batch` 并传入 `sequence`，确认 `score > 0`。

---

## 3. OmegaFold：阻塞事件循环，必须 Semaphore(1)

**现象**：OmegaFold 的 `self.model(input_data)` 是同步 PyTorch CUDA 调用，在 `async def` 内会阻塞 uvicorn 事件循环。高于 1 的并发会导致请求排队超时或服务崩溃。

**处理方式**：客户端必须使用 `asyncio.Semaphore(1)` 串行化请求，每个请求设置 `timeout=14400`（4 小时，虽然实际只需 90-120s）。

**影响**：OmegaFold 是全管线吞吐量瓶颈（~120s/construct，强制串行）。

---

## 4. ToxinPred3：sklearn 线程不安全

**现象**：ToxinPred3 使用 sklearn ExtraTreesClassifier，其 C 扩展在并发请求时会挂起。高并发导致 socket 连接堆积，服务无法响应。

**处理方式**：
- 客户端并发限制到 Semaphore(2)
- 每次只发送单条序列（batch_size=1）
- 使用 socket 级别超时（httpx timeout=180s）
- 备选方案：5 次连续超时后调用 `POST /restart` 重启服务

**验证**：服务自身声明 `recommended_batch_size = 50`，但实际 pipeline 经验表明 batch_size=1 + Sem(2) 最稳定。

---

## 5. Waveflow：路径含工具名 `/predict/{tool}`

**现象**：Waveflow 的路由模式与其他结构服务不同：
- `POST /predict/esmfold`（不是 `/predict`）
- `POST /predict/batch/omegafold`
- `POST /predict/async/alphafold3`
- `GET /status/{job_id}` / `GET /result/{job_id}` — 这些是标准异步模式

同时兼容 `POST /predict`（使用 `WAVEFLOW_DEFAULT_TOOL` 环境变量，默认 `esmfold`）。

**处理方式**：直接调用 Waveflow 时注意 URL 路径格式。通过 `ServiceClient.predict_structure_async()` 调用时，指定服务名 `waveflow`，client 会自动拼接路径。

---

## 6. TemStaPro：GPU OOM 风险

**现象**：TemStaPro 两阶段架构——先 ProtT5-XL 编码（~11GB GPU），再 30 个 MLP 分类器并行推理。内部 `Semaphore(10)` 限制同时运行 10 组 × 30 MLP = 300 分类器，但仍可能在批量过大时导致 GPU OOM。

**处理方式**：
- 客户端并发限制到 Semaphore(2-5)
- 超时设为 300-600s
- 如遇到 OOM，重启容器并降低并发

---

## 7. Aggrescan3D：每请求启 Docker 子进程

**现象**：Aggrescan3D 在 Python 2.7 micromamba 容器内运行，每个预测通过 subprocess 启动独立进程。首次调用冷启动慢（~10s），并发过高会耗尽系统资源。

**处理方式**：
- 服务端内部 `Semaphore(2)` 限制同时运行的子进程数
- 客户端 `timeout=900s`（可配 `A3D_TIMEOUT` 环境变量）
- 批量发送 50 个/批，利用批处理减少冷启动开销

---

## 8. SASA 单条 vs Batch 响应结构不一致

| 端点 | 响应结构 |
|------|----------|
| `POST /predict` | `{"success": true, "peptide_id": "...", "result": {"score": 0.76, "label": "exposed", "details": {...}}}` |
| `POST /predict/batch` | `{"success": true, "results": [{"peptide_id": "...", "score": 0.76, "label": "exposed", "details": {...}}]}` |

注意 batch 结果没有 `result` 嵌套层。这是 PDB 服务模板的设计，FASTA 服务模板两端都使用 `result` 嵌套。

---

## 9. BetaFold / ESMFold：pLDDT 在丝绸融合蛋白上偏低

**现象**：ESMFold 对丝绸重复序列的 pLDDT < 0.30，不可用于下游 SASA/A3D 分析。OmegaFold pLDDT ~0.41 是可用的。

**原因**：ESM-2 训练数据中缺乏类似丝绸重复序列的结构。

**处理方式**：对丝绸融合蛋白优先使用 OmegaFold。ESMFold 只作为替补。

---

## 10. Docker Bridge IP 非 127.0.0.1

**现象**：通过 `127.0.0.1:PORT`（docker-proxy）访问容器时，长 HTTP 请求可能出现 httpx keep-alive 挂起。这是 docker-proxy 的已知问题。

**处理方式**：使用 `docker inspect` 获取容器 bridge IP，直接连接。已实现于 `s4_docker_utils.py` 的 `detect_bridge_ip()`。

---

## 11. asyncio.gather 异常安全

**现象**：`asyncio.gather(*tasks)` 不带 `return_exceptions=True` 时，任一任务失败会取消所有其他任务。

**处理方式**：批量处理时始终使用 `return_exceptions=True`，逐任务检查异常。
