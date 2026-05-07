---
name: algpred2-risk-prediction
description: 当用户需要在本地预测肽/蛋白序列的过敏原性风险，并将结果作为融合引擎的筛选惩罚项或保守过滤层时，触发此 skill。Also use when allergenicity risk screening is needed for candidate peptides and the result will serve as a penalty signal in a fusion engine.
created: 2026-04-16
version: 1.4
last_updated: 2026-04-24
---

# AlgPred2 过敏原性风险预测

## What It Is

**AlgPred2** 是 CLI-first 过敏原性风险预测工具，通过机器学习模型评估肽/蛋白序列的过敏原性概率。

在融合引擎中承担**风险筛查层**角色：
- 输出 `ML_Score` (0-1) 和 `Prediction` (Allergen/Non-Allergen)
- 高风险序列可作为惩罚项或过滤信号

## When to Use

- 需要对候选肽做过敏原性风险粗筛
- 希望把"可能为过敏原"作为融合引擎的惩罚项
- 需要本地可运行、批量文件处理的预测工具

**不适合**: 开箱即用、零调参、或直接 Python API 调用场景

## Methodology

1. **Treat as CLI-first**: 不假设有 Python API，直接使用命令行
2. **Fix dependencies first**: 安装后需手动补装 `joblib` 并固定 scikit-learn/numpy 版本
3. **Validate output format**: 确认 CSV 列名和结果含义后再接入下游流程

## Operations

### 快速开始

```bash
# 1. 安装依赖
uv add algpred2
uv add joblib
uv add "scikit-learn==1.2.2" "numpy==1.26.4"

# 2. 文本输入预测
uv run algpred2 -i ./input.txt -o ./output.csv -m 1 -d 2

# 3. FASTA 输入预测
uv run algpred2 -i ./input.fasta -o ./output.csv -m 1 -d 2
```

### CLI 参数

| 参数 | 说明 | 默认 |
| --- | --- | --- |
| `-i INPUT` | 输入文件 (FASTA 或纯序列文本) | **必需** |
| `-o OUTPUT` | 输出 CSV | outfile.csv |
| `-t THRESHOLD` | 阈值 (0-1) | 0.3 |
| `-m {1,2}` | 1=Allergen, 2=Non-Allergen | 1 |
| `-d {1,2}` | 1=仅过敏原, 2=所有肽 | 1 |

## Inputs and Outputs

- **输入**: FASTA 文件 或 每行一条序列的文本文件
- **输出**: CSV 文件

| 列名 | 说明 |
| --- | --- |
| ID | 序列标识符 |
| Sequence | 肽序列 |
| ML_Score | 机器学习评分 (0-1) |
| Prediction | Allergen / Non-Allergen |

## Examples

### 示例 1: 批量预测并过滤高风险序列

```bash
# 预测
uv run algpred2 -i ./candidates.fasta -o ./risk_results.csv -m 1 -d 2

# 提取高风险序列 (ML_Score > 0.5)
# 使用其他工具过滤或人工审查
```

### 示例 2: 接入融合引擎作为惩罚项

```python
# 伪代码 - 融合引擎中的惩罚逻辑
if prediction == "Allergen":
    apply_penalty(1.0)  # 完全排除
elif ml_score > 0.5:
    apply_penalty(0.5)  # 高风险降权
```

## Known Issue

`.venv/bin/algpred2` shebang 路径可能有错误。如直接运行失败，使用 Python import 方式：

```python
from algpred2.python_scripts.algpred2 import main
import sys
sys.argv = ['algpred2', '-i', './input.txt', '-o', './output.csv', '-m', '1', '-d', '2']
main()
```

## Limitations

- 不是开箱即用，需手动修复依赖
- 顶层 Python API 不可用
- 主要针对蛋白设计，短肽效果可能有限
- 未完成大规模压力测试 (1000+ 条)

## References Index

| File | Contents |
| --- | --- |
| `references/installation.md` | 详细安装指南与依赖版本 |
| `references/cli_usage.md` | CLI 参数详解与调用方式 |
| `references/methodology.md` | 算法原理与融合引擎集成建议 |
| `references/test_results.md` | 实测结果与场景分析 |