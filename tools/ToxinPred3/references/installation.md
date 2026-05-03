# ToxinPred 3.0 安装详细指南

## 环境准备

### 使用 uv 管理虚拟环境（推荐）

```bash
# 在 ToxinPred3 目录下
cd ToxinPred3
uv venv .venv
source .venv/bin/activate
```

### 依赖安装

```bash
uv pip install numpy pandas scikit-learn
```

## toxinpred3 包安装（可选）

```bash
uv pip install toxinpred3
```

安装后验证：
```bash
uv run toxinpred3 -h
```

## 独立模块使用

将 `toxinpred_features.py` 复制到项目目录：

```bash
cp skills/toxinpred3/toxinpred_features.py /your/project/path/
```

## 常见问题

### 1. pip 安装被拒绝 (externally-managed-environment)

**解决方案：** 使用 uv 创建虚拟环境

```bash
uv venv .venv
source .venv/bin/activate
uv pip install <package>
```

### 2. 官方 CLI 报错 ValueError: bad delimiter

**原因：** pandas 版本兼容性问题

**解决方案：** 使用 standalone 模块

```python
from toxinpred_features import batch_predict_from_file
batch_predict_from_file("input.fa", "output.csv")
```

### 3. Python 3.14+ 模型加载问题

**解决方案：** 使用 standalone 模块，不依赖预训练模型

## 目录结构建议

```
your_project/
├── .venv/                 # 虚拟环境
├── pyproject.toml         # 项目配置
├── toxinpred_features.py   # 独立模块
├── peptides.fa            # 输入文件
└── predictions.csv        # 输出文件
```
