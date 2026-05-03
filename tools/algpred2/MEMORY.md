# AlgPred2 Skill - 实践经验记录

## 验证日期
2026-04-24

## 验证者
Sisyphus

## 验证结论
**Skill 状态**: ✅ 真实可用

## 实践发现

### 1. Shebang 路径问题

**问题**: uv 创建的 venv 中 `.venv/bin/algpred2` 脚本的 shebang 包含错误路径
- 错误: `from.Lehan` (句点)
- 正确: `from-Lehan` (连字符)

**原因**: 可能是 uv 在解析包含连字符的路径时出现的问题

**解决方案**: 手动修正 shebang 或使用 Python import 方式调用

### 2. 依赖版本必须固定

实测发现以下版本组合有效：
- joblib: >=1.5.3
- scikit-learn: ==1.2.2 (必须固定)
- numpy: ==1.26.4 (必须固定)

不固定版本可能导致 pickle 兼容性问题。

### 3. CLI-first 定位准确

SKILL.md 对 AlgPred2 的定位描述准确：
- 顶层 Python API 几乎为空
- 功能通过 `algpred2.python_scripts.algpred2:main` 提供
- 适合文件输入场景，不适合嵌入为 Python API

### 4. 输入输出格式验证

- **输入**: FASTA ✅, 每行一条序列文本 ✅
- **输出**: CSV，包含 ID/Sequence/ML_Score/Prediction ✅
- **批量**: 100 条序列测试通过 ✅

## 使用建议

### 推荐调用方式

```bash
# 方式 1: 使用 uv run（推荐）
uv run algpred2 -i ./input.fasta -o ./output.csv -m 1 -d 2

# 方式 2: Python import
uv run python scripts/run_prediction.py -i ./input.txt -o ./output.csv
```

### 融合引擎集成

```python
# 惩罚逻辑示例
def apply_allergen_penalty(result):
    if result['Prediction'] == 'Allergen':
        return 1.0  # 完全排除
    elif result['ML_Score'] > 0.5:
        return 0.5  # 高风险降权
    return 0.0
```

## 文件结构

```
algpred2-risk-prediction/
├── SKILL.md              # 主入口（精简版）
├── MEMORY.md             # 本文件 - 实践经验
├── references/           # 详细参考文档
│   ├── installation.md   # 安装指南
│   ├── cli_usage.md      # CLI 详细用法
│   ├── methodology.md    # 方法论
│   └── test_results.md   # 实测结果
├── scripts/              # 可执行脚本
│   ├── inspect_submodules.py
│   ├── inspect_entrypoints.py
│   └── run_prediction.py
├── test_input/           # 测试数据
├── outputs/              # 输出目录
├── pyproject.toml        # uv 项目文件
└── .venv/                # 虚拟环境
```