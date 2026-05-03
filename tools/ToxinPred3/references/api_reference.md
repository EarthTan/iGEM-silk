# ToxinPred 3.0 API 参考

## 主要函数

### extract_features(sequences)

提取完整的 AAC + DPC 特征集。

**参数：**
- `sequences`: `List[str]` 或 `str`
  - 肽序列列表，或 FASTA 文件路径

**返回：**
- `pd.DataFrame`: 420 列特征矩阵

**示例：**
```python
from toxinpred_features import extract_features

# 从序列列表
features = extract_features(["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG"])

# 从文件
features = extract_features("peptides.fa")
```

---

### aac_composition(sequences)

计算氨基酸组成 (AAC)。

**参数：**
- `sequences`: `List[str]` - 肽序列列表

**返回：**
- `pd.DataFrame`: 20 列 (AAC_A, AAC_C, ... AAC_Y)

---

### dpc_composition(sequences, step=1)

计算二肽组成 (DPC)。

**参数：**
- `sequences`: `List[str]` - 肽序列列表
- `step`: `int` (默认 1) - 步长，连续二肽为 1

**返回：**
- `pd.DataFrame`: 400 列 (DPC_AA, DPC_AC, ... DPC_WY)

---

### predict_toxicity(sequences, threshold=0.38)

预测肽序列的毒性。

**参数：**
- `sequences`: `List[str]` 或 `str` - 肽序列或文件路径
- `threshold`: `float` (默认 0.38) - 毒性阈值

**返回：**
- `pd.DataFrame` 包含：
  - `Name`: 序列名称
  - `Sequence`: 肽序列
  - `Length`: 序列长度
  - `Toxicity_Score`: 毒性评分 (0-1)
  - `Prediction`: "Toxin" 或 "Non-Toxin"

---

### batch_predict_from_file(input_file, output_file='toxinpred_results.csv', threshold=0.38)

从文件批量预测并保存结果。

**参数：**
- `input_file`: `str` - 输入文件路径 (FASTA 或单序列每行)
- `output_file`: `str` (默认 "toxinpred_results.csv") - 输出 CSV 路径
- `threshold`: `float` (默认 0.38) - 毒性阈值

**返回：**
- `pd.DataFrame` - 预测结果

---

### read_fasta(file_path)

读取 FASTA 格式文件。

**参数：**
- `file_path`: `str` - FASTA 文件路径

**返回：**
- `Tuple[List[str], List[str]]`: (序列名称列表, 序列列表)

---

### calculate_toxicity_score(sequence)

基于序列组成计算简化毒性评分。

**参数：**
- `sequence`: `str` - 肽序列

**返回：**
- `float`: 毒性评分 (0-1)

**注意：** 这是简化的基于规则的评分，不是 ML 模型。
