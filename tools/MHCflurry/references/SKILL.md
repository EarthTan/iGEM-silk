---
name: mhcflurry
description: 当用户需要预测MHC I类肽结合亲和力时触发此技能。它基于深度学习模型预测肽与MHC分子的结合强度，支持多种等位基因和批量处理。
created: 2026-04-18
version: 1.0.0
last_updated: 2026-04-25
---

# MHCflurry

## What It Is
MHCflurry 是一个基于深度学习的MHC I类肽结合亲和力预测工具。它使用预训练的神经网络模型来预测肽与主要组织相容性复合体（MHC）分子的结合强度，为疫苗设计和免疫原性评估提供关键信息。

## When to Use
- **疫苗设计**：识别潜在的T细胞表位
- **免疫原性评估**：预测肽的MHC结合能力
- **癌症免疫治疗**：筛选肿瘤新抗原
- **自身免疫病研究**：识别自身反应性肽
- **高通量筛选**：批量分析蛋白质组中的潜在表位

## Methodology
MHCflurry 使用以下方法进行预测：
1. **深度学习模型**：基于神经网络的结合亲和力预测
2. **等位基因特异性**：支持超过14000种MHC等位基因
3. **亲和力评分**：提供IC50值（半数抑制浓度）和百分位数排名
4. **结合分类**：基于阈值将肽分类为结合剂或非结合剂（强结合≤50nM，弱结合50-500nM，非结合>500nM）

## Operations

### 安装

使用 uv 创建虚拟环境并安装依赖：

```bash
cd MHCflurry/
uv sync
```

### 下载预训练模型

首次使用前需要下载预训练模型：

```python
import sys

# Python 3.14 兼容性补丁
if sys.version_info >= (3, 13):
    import shutil
    class FakePipes:
        @staticmethod
        def quote(s):
            import shlex
            return shlex.quote(s)
    sys.modules['pipes'] = FakePipes()

from mhcflurry.downloads_command import run
run()
```

或者使用 subprocess：

```python
import subprocess
import sys

wrapper_code = '''
import sys
import shutil
class FakePipes:
    @staticmethod
    def quote(s):
        import shlex
        return shlex.quote(s)
sys.modules['pipes'] = FakePipes()
from mhcflurry.downloads_command import run
run()
'''

subprocess.run([sys.executable, '-c', wrapper_code, 'fetch', 'models_class1_pan'])
```

### 快速开始

```python
from mhcflurry import Class1AffinityPredictor

# 加载预测器
predictor = Class1AffinityPredictor.load()

# 预测单个肽
peptides = ["SIINFEKL"]
alleles = ["HLA-A*02:01"]
predictions = predictor.predict(peptides=peptides, alleles=alleles)

print(f"预测结果: {predictions[0]:.2f} nM")

# 手动创建结果表格
import pandas as pd
results = []
for i, peptide in enumerate(peptides):
    for allele in alleles:
        results.append({
            "peptide": peptide,
            "allele": allele,
            "affinity_nM": predictions[i] if len(predictions) == len(peptides) else predictions[0]
        })

df = pd.DataFrame(results)
print(df)
```

### 批量预测

```python
from mhcflurry import Class1AffinityPredictor
import pandas as pd

predictor = Class1AffinityPredictor.load()

# 批量预测多个肽
peptides = ["SIINFEKL", "NLVPMVATV", "GILGFVFTL"]
alleles = ["HLA-A*02:01", "HLA-A*01:01"]

# 由于 predict_to_dataframe 有兼容性问题，使用循环方式
results = []
for peptide in peptides:
    for allele in alleles:
        affinity = predictor.predict(peptides=[peptide], alleles=[allele])[0]
        results.append({
            "peptide": peptide,
            "allele": allele,
            "affinity_nM": round(affinity, 2)
        })

df = pd.DataFrame(results)
print(df)

# 筛选强结合子（≤50 nM）
strong_binders = [r for r in results if r['affinity_nM'] <= 50]
print(f"\n强结合子数量: {len(strong_binders)}")
```

## Inputs and Outputs

- **输入**：
  - 肽序列列表（字符串格式，通常为8-15个氨基酸）
  - MHC等位基因列表（如"HLA-A*02:01"）
- **输出**：
  - 预测亲和力值（nM，越低表示结合越强）
  - 百分位排名（0-1之间，越低表示结合越强）
  - DataFrame包含peptide, allele, prediction, percentile_rank等字段

## Examples

1. **检查支持的等位基因**：
```python
predictor = Class1AffinityPredictor.load()
print(f"支持 {len(predictor.supported_alleles)} 个等位基因")
print("前5个:", predictor.supported_alleles[:5])
```

2. **疫苗候选筛选**：
```python
# 从FASTA读取肽序列
from Bio import SeqIO
peptides = [str(record.seq) for record in SeqIO.parse("vaccines.fasta", "fasta")]

# 批量预测（使用循环workaround）
predictor = Class1AffinityPredictor.load()
results = []
for peptide in peptides:
    for allele in ["HLA-A*02:01", "HLA-B*07:02"]:
        affinity = predictor.predict(peptides=[peptide], alleles=[allele])[0]
        results.append({
            "peptide": peptide,
            "allele": allele,
            "affinity_nM": affinity
        })

import pandas as pd
df = pd.DataFrame(results)

# 筛选强结合子
strong = [r for r in results if r['affinity_nM'] <= 50]
print(f"强结合子数量: {len(strong)}")
```

## References Index

| File | Contents |
|------|----------|
| `references/mhcflurry_guide.md` | 详细的使用指南、API参考、性能优化和故障排除 |
| `references/allele_support.md` | 支持的MHC等位基因列表和选择指南 |
| `references/threshold_explanation.md` | 结合阈值解释和自定义方法 |