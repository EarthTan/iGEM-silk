# Tool → Microservice 转换工作流

> 基于 `tools/AnOxPePred` 实践总结的标准化流程。

---

## 一、转换原则

1. **最小化干扰**：只改必要的文件，保留原有的 `tools/` 核心逻辑
2. **接口标准化**：所有工具必须暴露统一的 HTTP 接口（`/predict`、`/predict/batch`、`/health`、`/info`）
3. **独立环境**：每个工具保持独立的 `.venv` 和 `pyproject.toml`
4. **可逆性**：转换后如果需要，可以回退到 CLI 模式

---

## 二、标准流程（6 步）

### Step 1：分析现有结构

**目标**：理解现有工具的代码组织，找到预测逻辑入口。

**检查清单**：

| 文件/目录 | 作用 | 是否必要 |
|-----------|------|---------|
| `pyproject.toml` | 依赖管理 | ✅ 保留，需更新 |
| `main.py` | CLI 入口 | ❌ 重写为服务启动器 |
| `tools/*.py` | 核心预测逻辑 | ✅ 保留，service.py 会调用 |
| `SKILL.md` | AI 技能文档 | ✅ 保留，工具说明 |
| `anoxpepred_data/` | 模型文件 | ✅ 保留，预测所需 |
| `*.csv` | 测试结果 | ❌ 删除（清理） |
| `verification.md` | 验收报告 | ❌ 删除（清理） |
| `scripts/` | 辅助脚本 | ❌ 删除（清理） |

**关键动作**：
```bash
# 查看工具目录结构
ls -la tools/<TOOL_NAME>/

# 找到预测逻辑入口（如 anoxpepred_integration.py）
ls tools/<TOOL_NAME>/tools/

# 查看 pyproject.toml 了解现有依赖
cat tools/<TOOL_NAME>/pyproject.toml
```

---

### Step 2：创建 `service.py`

**目标**：创建微服务入口文件，继承 `BioToolService` 模板。

**文件位置**：`tools/<TOOL_NAME>/service.py`

**标准模板**：

```python
"""
service.py - <TOOL_NAME> 微服务入口

使用方式：
    cd tools/<TOOL_NAME>
    source .venv/bin/activate
    python service.py
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# 将项目根目录添加到路径（用于导入 services.template）
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 将 tools/ 目录添加到路径（用于导入预测逻辑）
TOOLS_DIR = Path(__file__).parent / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from services.template.tool_service import BioToolService, create_app, ToolResult


class <ToolName>Service(BioToolService):
    """<工具描述>"""

    tool_name = "<tool_id>"           # 必须与 registry.py 中的 name 一致
    version = "<version>"            # 例如 "1.0.0"
    description = "<工具描述>"
    recommended_batch_size = 50      # 推荐批量大小

    async def load_model(self):
        """加载模型（启动时调用一次，之后常驻内存）"""
        from tools.<integration_module> import <IntegrationClass>
        self.model = <IntegrationClass>(verbose=True)
        print(f"[{self.tool_name}] Model loaded, ready to predict")

    async def predict_impl(self, sequence: str) -> ToolResult:
        """核心预测逻辑（每次请求调用）"""
        result = self.model.predict_single(sequence)

        return ToolResult(
            score=result.<score_field>,       # 0-1 分数
            label=result.<label_field>,       # 分类标签
            details={
                "<detail_key>": result.<detail_value>,
                # ... 其他详细信息
            }
        )


# 创建 FastAPI 应用
app = create_app(<ToolName>Service)


# 本地启动入口
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "<default_port>"))
    print(f"Starting <tool_name> service on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
```

**关键点**：
- `PROJECT_ROOT` 必须指向项目根目录（`tools/<TOOL_NAME>/../../`），用于导入 `services.template`
- `TOOLS_DIR` 指向 `tools/<TOOL_NAME>/tools/`，用于导入原有的预测逻辑
- `tool_name` 必须与 `services/orchestrator/registry.py` 中的配置一致

---

### Step 3：更新 `pyproject.toml`

**目标**：添加微服务所需的 HTTP 框架依赖。

**更新内容**：

```toml
[project]
name = "<tool-name>"
version = "<version>"
description = "<工具名称> 微服务"
requires-python = ">=3.11"
dependencies = [
    "numpy>=2.0.0",
    "pandas>=2.0.0",
    "httpx>=0.27.0",        # ⚠️ 必须添加（services/__init__.py 依赖）
]

[project.optional-dependencies]
ml = [
    # 原有 ML 依赖，如 tensorflow, biopython
]
service = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "pydantic>=2.0.0",
]
all = [
    # 全部依赖
]
```

**为什么需要 `httpx`**：
`services/__init__.py` 会导入 `orchestrator/core.py`，而 `core.py` 导入了 `httpx`。
如果不添加 `httpx`，服务启动时会报 `ModuleNotFoundError: No module named 'httpx'`。

---

### Step 4：重写 `main.py`

**目标**：将 CLI 入口重写为服务启动器。

**标准模板**：

```python
"""
main.py - <TOOL_NAME> 微服务启动器

Usage:
    python main.py                    # 启动服务（默认端口）
    PORT=8002 python main.py          # 指定端口
"""

import os
import uvicorn


def main():
    port = int(os.environ.get("PORT", "<default_port>"))

    print(f"""
╔══════════════════════════════════════════════════════╗
║  <TOOL_NAME> 微服务                                   ║
║  <工具描述>                                            ║
║                                                      ║
║  端口: {port}                                        ║
║  API 文档: http://localhost:{port}/docs              ║
╚══════════════════════════════════════════════════════╝
    """)

    # 直接导入 app 对象（不是字符串）
    from service import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )


if __name__ == "__main__":
    main()
```

**关键点**：
- 使用 `from service import app` 而不是 `uvicorn.run("service:app", ...)`
- 直接传 `app` 对象可以让 uvicorn 正常工作

---

### Step 5：清理不必要文件

**删除清单**：

| 文件类型 | 示例 | 删除原因 |
|---------|------|---------|
| 测试结果 | `test_results.csv`, `fixed_test.csv` | 只用于验证，不需要 |
| 验收报告 | `verification.md` | 开发文档，不需要 |
| 辅助脚本 | `scripts/*.py` | 如果不是核心功能，删除 |
| 备份文件 | `.backup/` | 开发产物，不需要 |

**命令**：
```bash
cd tools/<TOOL_NAME>
rm -f test_results.csv fixed_test.csv anoxpepred_results.csv
rm -rf scripts/
rm -rf .backup/
```

**保留清单**：

| 文件/目录 | 保留原因 |
|-----------|---------|
| `tools/*.py` | 核心预测逻辑 |
| `anoxpepred_data/` | 模型文件 |
| `SKILL.md` | AI 技能文档 |
| `references/` | 技术参考文档 |

---

### Step 6：验证服务

**目标**：确保服务可以正常启动并响应请求。

**执行步骤**：

```bash
# 1. 进入工具目录
cd tools/<TOOL_NAME>

# 2. 安装依赖（包含 service 模式）
rm -rf .venv uv.lock
uv sync --extra service

# 3. 后台启动服务
nohup uv run python main.py > /tmp/<tool_name>.log 2>&1 &
sleep 5

# 4. 检查健康状态
curl -s http://localhost:<PORT>/health
# 预期输出: {"status":"healthy","tool_name":"...","version":"...","model_loaded":true}

# 5. 测试单序列预测
curl -s -X POST http://localhost:<PORT>/predict \
  -H "Content-Type: application/json" \
  -d '{"sequence": "<TEST_SEQ>", "peptide_id": "test"}'
# 预期输出: {"success": true, "result": {"score": ..., "label": ...}}

# 6. 测试批量预测
curl -s -X POST http://localhost:<PORT>/predict/batch \
  -H "Content-Type: application/json" \
  -d '{"sequences": [{"sequence": "<SEQ1>"}, {"sequence": "<SEQ2>"}]}'
# 预期输出: {"success": true, "total": 2, "results": [...]}

# 7. 查看工具信息
curl -s http://localhost:<PORT>/info

# 8. 停止服务（测试完毕后）
pkill -f "uvicorn.*<PORT>"
```

**验证检查清单**：

| 接口 | URL | 预期响应 |
|------|-----|---------|
| 健康检查 | `GET /health` | `{"status": "healthy", ...}` |
| 根路径 | `GET /` | 服务信息 |
| 工具信息 | `GET /info` | 工具元数据 |
| 单序列预测 | `POST /predict` | `{"success": true, "result": {...}}` |
| 批量预测 | `POST /predict/batch` | `{"success": true, "total": N, "results": [...]}` |

---

## 三、端口分配规范

参考 `services/orchestrator/registry.py`：

| 端口 | 工具 | 用途 |
|------|------|------|
| 8000 | orchestrator | 调度中心 API |
| 8001 | anoxpepred | 抗氧化预测 |
| 8002 | bepipred3 | B 细胞表位 |
| 8003 | toxipred3 | 毒性检测 |
| 8004 | hemopi2 | 溶血检测 |
| 8005 | mhcflurry | MHC 结合 |
| 8006 | plm4cpps | 细胞穿膜 |
| 8007 | tipred | 酪氨酸酶抑制 |
| 8008 | algpred2 | 过敏原性 |
| 8009 | graphcpp | CPP 图网络 |
| 8010 | mlcpp | CPP 机器学习 |

---

## 四、转换优先级

```
P0（必须，先做）：
  1. anoxpepred   ✓ 已完成
  2. toxipred3
  3. hemopi2

P1（推荐，然后做）：
  4. mhcflurry
  5. plm4cpps
  6. tipred
  7. algpred2

P2（可选，最后做）：
  8. bepipred3   ← 需要 GPU
  9. graphcpp    ← 图神经网络较复杂
 10. mlcpp
```

---

## 五、常见问题排查

### 1. `ModuleNotFoundError: No module named 'httpx'`

**原因**：`services/__init__.py` 导入了 `orchestrator/core.py`，而 `core.py` 需要 `httpx`。

**解决**：在工具的 `pyproject.toml` 中添加 `httpx>=0.27.0` 到 dependencies。

### 2. `ModuleNotFoundError: No module named 'services'`

**原因**：`service.py` 无法找到项目根目录下的 `services/` 模块。

**解决**：确保 `sys.path` 中包含项目根目录：
```python
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
```

### 3. `uvicorn.run("service:app", ...)` 报错

**原因**：字符串方式 `"service:app"` 需要正确的 import 路径。

**解决**：直接导入 `app` 对象：
```python
from service import app
uvicorn.run(app, host="0.0.0.0", port=8001)
```

### 4. 服务启动后立即关闭

**排查**：
1. 检查日志：`tail -50 /tmp/<tool_name>.log`
2. 常见原因：模型加载失败、依赖缺失

---

## 六、模板文件清单

转换完成后，每个工具目录应包含：

```
tools/<TOOL_NAME>/
├── service.py          ← 微服务入口（新建）
├── main.py             ← 服务启动器（重写）
├── pyproject.toml     ← 依赖配置（更新）
├── SKILL.md           ← AI 技能文档（保留）
├── tools/              ← 核心预测逻辑（保留）
│   ├── __init__.py
│   └── <integration>.py
├── anoxpepred_data/   ← 模型文件（保留）
└── references/         ← 技术文档（保留）
```

---

*本文档基于 AnOxPePred 工具的微服务化实践总结。*
*如遇其他工具的特殊情况，请补充此文档。*