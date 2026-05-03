# AlgPred2 CLI 详细用法

## CLI 参数说明

```
algpred2 [-h] -i INPUT [-o OUTPUT] [-t THRESHOLD] [-m {1,2}] [-d {1,2}]
```

| 参数 | 全称 | 说明 | 默认值 |
| --- | --- | --- | --- |
| `-i` | `--input` | 输入文件 (FASTA 或每行一条序列的文本) | **必需** |
| `-o` | `--output` | 输出 CSV 文件 | outfile.csv |
| `-t` | `--threshold` | 阈值 (0-1) | 0.3 |
| `-m` | `--model` | 模型: 1=Allergen, 2=Non-Allergen | 1 |
| `-d` | `--display` | 显示: 1=Allergen, 2=所有肽 | 1 |

## 调用方式

由于 shebang 路径问题，推荐使用以下方式调用：

### 方式 1: 使用 uv run（推荐）

```bash
# 文本输入
uv run algpred2 -i ./input.txt -o ./output.csv -m 1 -d 2

# FASTA 输入
uv run algpred2 -i ./input.fasta -o ./output.csv -m 1 -d 2
```

### 方式 2: Python import（备选）

```python
from algpred2.python_scripts.algpred2 import main
import sys

# 设置参数
sys.argv = ['algpred2', '-i', './input.txt', '-o', './output.csv', '-m', '1', '-d', '2']
main()
```

## 输入格式

### 文本格式（每行一条序列）

```
ACDEFGHI
KKLLKLLKL
ACDEFGHIKLMNPQRSTVWY
```

### FASTA 格式

```
>SEQ_001
ATCGATCGA
>SEQ_002
GCTAGCTAG
```

## 输出格式

CSV 文件，包含以下列：

| 列名 | 说明 | 示例 |
| --- | --- | --- |
| ID | 序列标识符 | Seq_1, SEQ_001 |
| Sequence | 肽序列 | ACDEFGHI |
| ML_Score | 机器学习评分 (0-1) | 0.264 |
| Prediction | 预测结果 | Allergen / Non-Allergen |

## 示例输出

```csv
ID,Sequence,ML_Score,Prediction
Seq_1,ACDEFGHI,0.264,Non-Allergen
Seq_2,KKLLKLLKL,0.367,Allergen
```

## 批量处理

### 处理多条序列

```bash
# 准备输入文件（每行一条序列）
echo -e "ACDEFGHI\nKKLLKLLKL\nMKWVTFISLLFLFSSAYSR" > sequences.txt

# 运行预测
uv run algpred2 -i ./sequences.txt -o ./batch_results.csv -m 1 -d 2
```

### 处理 FASTA 文件

```bash
uv run algpred2 -i ./test_peptides.fasta -o ./fasta_results.csv -m 1 -d 2
```

## 注意事项

1. **阈值调整**: 默认阈值 0.3 较宽松，可根据需求调整为更保守的 0.5 或更高
2. **模型选择**: `-m 1` 预测过敏原，`-m 2` 预测非过敏原
3. **显示模式**: `-d 2` 显示所有肽结果，`-d 1` 仅显示预测为过敏原的肽