# Skill 验收报告（Specification-Driven）

## 基本信息

| 字段         | 内容                              |
| ------------ | --------------------------------- |
| Skill 名称   | MLCPP / mlcpp                     |
| Skill 创建者 | Wenxuan                           |
| 验收标准     | Specification-driven（规范驱动）  |
| 验证 Agent   | Sisyphus                          |
| 验证日期     | 2026-04-25                        |
| 执行环境     | macOS + Python 3.13 (via uv venv) |

---

## Skill 声明抽取（Claims Extraction）

从 Skill 文档中提取所有"明确声明的能力或特性"。

| 编号 | 声明内容 | 来源（章节/位置） |
| ---- | -------- | ----------------- |
| 1 | MLCPP 是基于机器学习的细胞穿透肽预测工具，使用预训练模型 | SKILL.md - "What It Is" |
| 2 | 提供 `MLCPPIntegration` 类作为核心 API | SKILL.md - "快速开始" |
| 3 | 支持在线 API 与离线双模式运行 | SKILL.md - "Methodology" |
| 4 | 输出细胞穿透概率（0-1）、预测类别（CPP/非CPP）与置信度 | SKILL.md - "Methodology/Inputs and Outputs" |
| 5 | 支持批量预测（predict_batch）和结果导出（CSV/JSON） | SKILL.md - "批量预测/Inputs and Outputs" |
| 6 | 提供 `tools.mlcpp_integration` 模块供导入 | SKILL.md 及所有代码示例 |
| 7 | 通过 `pip install requests pandas numpy` 安装依赖 | SKILL.md - "安装" |
| 8 | 配套提供 `references/mlcpp_guide.md` 详细使用指南 | SKILL.md - "References Index" |
| 9 | 配套提供 `scripts/cpp_screening_pipeline.py` 筛选管道 | SKILL.md - "References Index" |

---

## 实际执行记录（Execution Trace）

记录验证 Agent 按照流程执行时的真实情况。

| 步骤 | 操作 | 结果 | 备注 |
| ---- | ---- | ---- | ---- |
| 1 | 读取 SKILL.md，理解技能定位 | 成功 | 技能定位：基于机器学习的细胞穿透肽预测 |
| 2 | 识别环境需求：Python 3.13+, requests, pandas, numpy | 成功 | pyproject.toml 指定 Python>=3.13，但 dependencies=[] 为空 |
| 3 | 检查 .venv 是否存在 | 成功 | venv 已创建于 MLCPP/.venv |
| 4 | 验证 `tools.mlcpp_integration` 模块 | **失败** | `ModuleNotFoundError: No module named 'tools'` |
| 5 | 验证 `MLCPPIntegration` 类 | **失败** | 该类不存在，所有引用它的代码均无法运行 |
| 6 | 尝试运行 `cpp_screening_pipeline.py` | 成功（降级） | 脚本报错"MLCPP集成模块未找到，使用模拟模式"，回退到 MockPredictor |
| 7 | 检查 references 目录文件 | 成功 | mlcpp_guide.md 存在且内容详尽 |
| 8 | 检查 scripts 目录文件 | 成功 | cpp_screening_pipeline.py 存在且完整 |
| 9 | 验证依赖包是否已安装 | 成功 | requests, pandas, numpy 已在 venv 中安装 |

---

## 关键发现

### 🔴 严重问题：`tools.mlcpp_integration` 模块缺失

**问题描述：**
SKILL.md 及所有关联文档、脚本均引用 `from tools.mlcpp_integration import MLCPPIntegration`，但该模块**完全不存在**于技能文件夹中。

**证据：**
```python
# 执行命令
.venv/bin/python -c "from tools.mlcpp_integration import MLCPPIntegration"

# 报错
ModuleNotFoundError: No module named 'tools'
```

**影响范围：**
- SKILL.md 中所有"快速开始"代码示例无法运行
- mlcpp_guide.md 中所有 API 调用示例无法运行
- scripts/cpp_screening_pipeline.py 启动即报错，回退到 MockPredictor

**根本原因：**
技能创建者编写了围绕 `MLCPPIntegration` 类的完整文档和代码框架，但**从未实际创建**该模块文件 (`tools/mlcpp_integration.py`)。

### ⚠️ Skill 设计问题

即使 `tools.mlcpp_integration` 模块存在，其设计也有问题：

1. **导入路径不合理**：`tools.mlcpp_integration` 不是标准 pip 包路径，用户无法通过 `pip install` 安装
2. **pyproject.toml 依赖为空**：SKILL.md 声称需要 `requests, pandas, numpy`，但 pyproject.toml 中 `dependencies=[]`
3. **使用 pip 而非 uv**：SKILL.md 中使用 `pip install`，但 AGENTS.md 标准要求使用 `uv` 和 `pyproject.toml` 管理依赖
4. **无真实 API 端点**：在线模式使用 `http://mlcpp-api.example.com` 作为示例 URL，这不是真实可用的端点

### ✅ 有效部分：MockPredictor 可用

经验证，cpp_screening_pipeline.py 脚本中的 MockPredictor 类可正常运行：

```python
$ .venv/bin/python scripts/cpp_screening_pipeline.py --sequence "RKKRRQRRR" --verbose
警告: MLCPP集成模块未找到，使用模拟模式
使用模拟模式 (MLCPP集成模块未找到)
分析单个肽序列: RKKRRQRRR
预测肽序列: single_peptide
序列: RKKRRQRRR
长度: 9 个氨基酸
细胞穿透概率: 0.468
预测类别: Non-CPP
置信度: 0.801
结果已保存到: mlcpp_results.csv
```

但这是**模拟结果**，不是真实机器学习模型的预测结果。

---

## 改进建议

### 必须修复（Blocker）

1. **创建 `tools/mlcpp_integration.py` 模块**
   - 实现 `MLCPPIntegration` 类
   - 实现 `PredictionResult` 数据类
   - 实现 `predict_single()`, `predict_batch()`, `predict_from_fasta()`, `predict_from_csv()`, `export_results()` 等方法
   - 如果没有真实在线 API，应实现完整的离线预测功能

2. **或者：修改文档使用标准包结构**
   - 如果想保留包装模块，应在 pyproject.toml 中配置 `[tool.setuptools.packages]` 或 `[project.urls]` 来说明包结构
   - 更新所有示例为实际可运行的导入路径

### 建议改进（Should）

1. **修复 pyproject.toml 依赖**
   - 添加 `requests`, `pandas`, `numpy` 到 dependencies
   - 或者移除这些依赖说明，统一使用 uv 管理

2. **补充测试代码**
   - 添加 `tests/` 目录
   - 提供可执行的单元测试验证功能

3. **明确 API 端点**
   - 如果是在线模式，提供真实可用的 API URL
   - 或者明确说明这是一个本地模型预测工具

---

## 最终评定

| 维度 | 评定 | 说明 |
| ---- | ---- | ---- |
| 功能完整性 | ❌ 不合格 | 声称的 `MLCPPIntegration` 类不存在 |
| 文档一致性 | ❌ 不合格 | 文档与实际代码严重不符 |
| 可运行性 | ❌ 不合格 | 核心示例代码无法执行 |
| 环境配置 | ⚠️ 部分合格 | venv 存在但 pyproject.toml dependencies 为空 |
| 底层技术 | ✅ 合格 | MockPredictor 可运行，依赖包已安装 |

**综合结论：Skill 存在但不可用。**

该 Skill 的问题属于"纸面技能"——文档和代码框架都写好了，但核心实现完全缺失。技能创建者需要么补充 `tools/mlcpp_integration.py` 的实现，要么修改所有文档改用实际存在的 API。与之前验证的 Biopython ProtParam skill 问题完全相同。

---

## 附录：验证命令记录

```bash
# 检查 venv 是否存在
ls -la "/Users/concerto391/Documents/GitHub/iGEM-Tools/from-Wenxuan/MLCPP/.venv"
# 输出：venv 目录存在

# 验证 Skill 声称的 API 不可用
cd "/Users/concerto391/Documents/GitHub/iGEM-Tools/from-Wenxuan/MLCPP"
.venv/bin/python -c "from tools.mlcpp_integration import MLCPPIntegration"
# 报错：ModuleNotFoundError: No module named 'tools'

# 验证 cpp_screening_pipeline.py 脚本（降级运行）
.venv/bin/python scripts/cpp_screening_pipeline.py --sequence "RKKRRQRRR" --verbose
# 输出：警告: MLCPP集成模块未找到，使用模拟模式
#       细胞穿透概率: 0.468，预测类别: Non-CPP（随机模拟值）

# 检查 pyproject.toml 依赖
cat pyproject.toml
# 输出：dependencies = []（空数组）

# 检查 tools 目录是否存在
ls -la /Users/concerto391/Documents/GitHub/iGEM-Tools/from-Wenxuan/MLCPP/tools/
# 输出：No such file or directory
```