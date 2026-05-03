# AlgPred2 实测结果与场景分析

## 测试环境

- **平台**: macOS (Darwin)
- **Python**: 3.11.14
- **uv**: 已配置
- **验证日期**: 2026-04-24

## 功能验证结果

### 1. Python 导入测试

```bash
uv run python -c "import algpred2; print(dir(algpred2))"
```

**结果**: ✅ 成功

**输出**:
```
['__doc__', '__file__', '__loader__', '__name__', '__package__', '__path__', '__spec__']
```

**结论**: 顶层命名空间几乎为空，确认不适合作为 Python API 直接调用。

### 2. 子模块检查

```bash
uv run python scripts/inspect_submodules.py
```

**结果**: ✅ 成功

**发现**:
- `python_scripts` 子模块存在
- console script 入口: `algpred2 -> algpred2.python_scripts.algpred2:main`

### 3. 依赖版本验证

```bash
uv run python -c "import joblib, sklearn, numpy; print(f'joblib: {joblib.__version__}, sklearn: {sklearn.__version__}, numpy: {numpy.__version__}')"
```

**结果**: ✅ 成功

**版本**:
- joblib: 1.5.3
- scikit-learn: 1.2.2
- numpy: 1.26.4

### 4. 文本输入预测

**输入** (`test_input/test_lines.txt`):
```
ACDEFGHI
KKLLKLLKL
```

**命令**:
```python
from algpred2.python_scripts.algpred2 import main
import sys
sys.argv = ['algpred2', '-i', './test_input/test_lines.txt', '-o', './outputs/test_algpred2.csv', '-m', '1', '-d', '2']
main()
```

**结果**: ✅ 成功

**输出 CSV**:
```csv
ID,Sequence,ML_Score,Prediction
Seq_1,ACDEFGHI,0.458,Allergen
Seq_2,KKLLKLLKL,0.367,Allergen
```

### 5. FASTA 输入预测

**输入**: 100 条序列的 FASTA 文件

**命令**:
```python
from algpred2.python_scripts.algpred2 import main
import sys
sys.argv = ['algpred2', '-i', './test_input/test_peptides.fasta', '-o', './outputs/test_algpred2_fasta.csv', '-m', '1', '-d', '2']
main()
```

**结果**: ✅ 成功处理 100 条序列

## 批量能力评估

| 规模 | 结果 | 备注 |
| --- | --- | --- |
| 2 条 | ✅ 成功 | 文本输入测试 |
| 100 条 | ✅ 成功 | FASTA 文件测试 |

**结论**: 支持小到中等规模批量预测。

## 已知问题

### Shebang 路径错误

`.venv/bin/algpred2` 文件内容：

```bash
#!/Users/concerto391/Documents/GitHub/iGEM-Tools/from.Lehan/algpred2-risk-prediction/.venv/bin/python
```

**问题**: 路径中使用了 `from.Lehan`（句点），实际应为 `from-Lehan`（连字符）

**影响**: 直接运行 `algpred2` 命令会报 "bad interpreter" 错误

**规避方案**:
1. 使用 `uv run algpred2 ...`
2. 使用 Python import 方式调用

## 场景适用性分析

### ✅ 适合的场景

1. **过敏原性风险粗筛**: 对候选肽序列进行初步风险评估
2. **惩罚项来源**: `Prediction = Allergen` 或高 `ML_Score` 作为融合引擎惩罚信号
3. **批量文件处理**: 需要处理多条序列的离线分析

### ⚠️ 需注意的场景

1. **短肽 (< 10 aa)**: 可能不是最优选择
2. **融合肽**: 建议对各组分分别评估
3. **修饰肽**: 未针对化学修饰肽优化