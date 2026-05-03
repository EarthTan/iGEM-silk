# AlgPred2 安装与环境配置

## 环境要求

- **平台**: macOS / Linux / Windows (via WSL)
- **Python**: >= 3.11
- **包管理器**: uv (必须使用，非 pip)

## 安装步骤

### 1. 初始化项目

```bash
cd algpred2-risk-prediction
uv init --no-readme
```

### 2. 安装 AlgPred2 及依赖

```bash
uv add algpred2
uv add joblib
uv add "scikit-learn==1.2.2" "numpy==1.26.4"
```

> ⚠️ **重要**: 必须固定 `scikit-learn==1.2.2` 和 `numpy==1.26.4` 版本，否则可能出现模型 pickle 兼容性或二进制兼容性问题。

### 3. 验证安装

```bash
# 验证 Python 导入
uv run python -c "import algpred2; print(dir(algpred2))"

# 验证 CLI 入口
uv run python -c "from algpred2.python_scripts.algpred2 import main; print('CLI OK')"
```

## 依赖版本信息

| 包 | 版本 | 说明 |
| --- | --- | --- |
| algpred2 | >=1.4 | 核心预测工具 |
| joblib | >=1.5.3 | 模型加载必需 |
| scikit-learn | ==1.2.2 | **必须固定版本** |
| numpy | ==1.26.4 | **必须固定版本** |

## 已知问题

### Shebang 路径错误

`.venv/bin/algpred2` 脚本的 shebang 可能包含错误路径。

**临时解决方案**: 使用 Python import 方式调用 CLI

```bash
# 直接运行（可能失败）
algpred2 -h

# Python import 方式（推荐）
uv run python -c "from algpred2.python_scripts.algpred2 import main; import sys; sys.argv = ['algpred2', '-h']; main()"
```

### 依赖不完整

AlgPred2 安装后**不是开箱即用**，必须手动安装额外依赖。

## pyproject.toml 示例

```toml
[project]
name = "algpred2-risk-prediction"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "algpred2>=1.4",
    "joblib>=1.5.3",
    "numpy==1.26.4",
    "scikit-learn==1.2.2",
]
```