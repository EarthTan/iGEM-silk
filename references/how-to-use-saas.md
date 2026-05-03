## 整体方案

```
输入: FASTA序列 + 功能肽序列
  → ESMFold API（或本地） → PDB文件
  → FreeSASA → 逐残基SASA值
  → 输出: JSON报告
```

技术栈：**FastAPI + FreeSASA + Biopython**，Docker 打包，单容器微服务。

------

## 目录结构

```
sasa-service/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── esm_fold.py      # 结构预测模块
│   ├── sasa_calc.py     # SASA 计算核心
│   └── models.py        # Pydantic 数据模型
```

------

## 代码实现

### `models.py`

```python
from pydantic import BaseModel
from typing import List, Optional

class SASARequest(BaseModel):
    full_sequence: str          # 全长融合蛋白 FASTA 序列
    peptide_sequence: str       # 功能肽序列
    chain_id: str = "A"
    pdb_content: Optional[str] = None  # 可选：直接传 PDB 文本，跳过结构预测

class ResidueSASA(BaseModel):
    residue_id: int
    residue_name: str
    sasa: float                 # Å²
    relative_sasa: float        # 0~1，相对于标准暴露值的比例
    is_exposed: bool            # 相对 SASA > 0.25 视为暴露

class SASAResponse(BaseModel):
    peptide_sequence: str
    peptide_start: int
    peptide_end: int
    total_sasa: float           # 功能肽区域总 SASA Å²
    mean_relative_sasa: float   # 平均相对暴露度
    exposure_ratio: float       # 暴露残基占比
    residues: List[ResidueSASA]
    pdb_content: str            # 返回使用的 PDB（便于前端可视化）
    warning: Optional[str] = None
```

------

### `esm_fold.py`

```python
import httpx
import tempfile, os

ESMFOLD_API = "https://api.esmatlas.com/foldSequence/v1/pdb/"

async def predict_structure(sequence: str) -> str:
    """
    调用 ESMFold 公开 API，返回 PDB 文本字符串。
    本地部署时替换 URL 为 localhost:8080 即可。
    """
    if len(sequence) > 400:
        raise ValueError("序列过长（>400aa），ESMFold 公开API限制，建议截断或本地部署")
    
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            ESMFOLD_API,
            content=sequence,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.text  # PDB 格式字符串
```

> 本地部署 ESMFold 时，换成 `http://localhost:8080` 的 docker 服务即可，接口格式相同。

------

### `sasa_calc.py`

```python
import re
import tempfile
import numpy as np
import freesasa
from Bio import PDB
from Bio.PDB import PDBIO, Select
from io import StringIO

# 标准最大 SASA 参考值（Å²），用于计算相对暴露度
MAX_SASA = {
    "ALA": 121, "ARG": 265, "ASN": 187, "ASP": 187, "CYS": 148,
    "GLN": 214, "GLU": 214, "GLY": 97,  "HIS": 216, "ILE": 195,
    "LEU": 191, "LYS": 230, "MET": 203, "PHE": 228, "PRO": 154,
    "SER": 143, "THR": 163, "TRP": 264, "TYR": 255, "VAL": 165,
}

class _PeptideSelect(Select):
    def __init__(self, residue_ids):
        self.ids = set(residue_ids)
    def accept_residue(self, res):
        return res.id[1] in self.ids

def locate_peptide(full_seq: str, peptide_seq: str):
    """返回所有匹配位置（1-indexed），支持多拷贝"""
    return [(m.start() + 1, m.end()) for m in re.finditer(peptide_seq, full_seq)]

def calc_sasa(pdb_text: str, full_sequence: str, peptide_sequence: str, chain_id: str):
    # ── 1. 定位功能肽 ──────────────────────────────────────
    positions = locate_peptide(full_sequence, peptide_sequence)
    if not positions:
        raise ValueError(f"功能肽 '{peptide_sequence}' 未在序列中找到")
    
    # 取第一个位置（多拷贝时可扩展为循环）
    pep_start, pep_end = positions[0]
    pep_residue_ids = list(range(pep_start, pep_end + 1))
    warning = f"功能肽出现 {len(positions)} 次，当前分析第一个" if len(positions) > 1 else None

    # ── 2. 解析 PDB ───────────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".pdb", mode="w", delete=False) as f:
        f.write(pdb_text)
        tmp_path = f.name

    try:
        parser = PDB.PDBParser(QUIET=True)
        structure = parser.get_structure("fusion", tmp_path)
        chain = structure[0][chain_id]

        # ── 3. FreeSASA 计算全蛋白 SASA ───────────────────
        fs_struct = freesasa.Structure(tmp_path)
        fs_result = freesasa.calc(fs_struct)

        # ── 4. 逐残基提取功能肽 SASA ──────────────────────
        residues_out = []
        total_sasa = 0.0

        for res in chain:
            rid = res.id[1]
            if rid not in pep_residue_ids:
                continue

            sel = freesasa.selectArea(
                [("r", f"resi {rid} and chain {chain_id}")],
                fs_struct, fs_result
            )
            sasa_val = sel.get("r", 0.0)
            total_sasa += sasa_val

            resname = res.resname.upper()
            max_ref = MAX_SASA.get(resname, 200)
            rel_sasa = min(sasa_val / max_ref, 1.0)

            residues_out.append({
                "residue_id": rid,
                "residue_name": resname,
                "sasa": round(sasa_val, 3),
                "relative_sasa": round(rel_sasa, 3),
                "is_exposed": rel_sasa > 0.25,
            })

    finally:
        import os; os.unlink(tmp_path)

    # ── 5. 汇总统计 ───────────────────────────────────────
    rel_sasas = [r["relative_sasa"] for r in residues_out]
    mean_rel  = float(np.mean(rel_sasas)) if rel_sasas else 0.0
    exp_ratio = sum(r["is_exposed"] for r in residues_out) / len(residues_out) if residues_out else 0.0

    return {
        "peptide_sequence": peptide_sequence,
        "peptide_start": pep_start,
        "peptide_end": pep_end,
        "total_sasa": round(total_sasa, 3),
        "mean_relative_sasa": round(mean_rel, 3),
        "exposure_ratio": round(exp_ratio, 3),
        "residues": residues_out,
        "pdb_content": pdb_text,
        "warning": warning,
    }
```

------

### `main.py`

```python
from fastapi import FastAPI, HTTPException
from .models import SASARequest, SASAResponse
from .esm_fold import predict_structure
from .sasa_calc import calc_sasa

app = FastAPI(title="SASA Microservice", version="1.0")

@app.post("/analyze", response_model=SASAResponse)
async def analyze(req: SASARequest):
    try:
        # 如果没传 PDB，先做结构预测
        pdb_text = req.pdb_content or await predict_structure(req.full_sequence)
        result   = calc_sasa(pdb_text, req.full_sequence, req.peptide_sequence, req.chain_id)
        return SASAResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health():
    return {"status": "ok"}
```

------

### `requirements.txt`

```
fastapi
uvicorn[standard]
httpx
biopython
freesasa
numpy
pydantic
```

------

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

# freesasa 需要编译依赖
RUN apt-get update && apt-get install -y gcc libxml2-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

------

## 启动与调用

```bash
# 构建并启动
docker build -t sasa-service .
docker run -p 8000:8000 sasa-service

# 调用示例
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "full_sequence": "MAAAAAGGAGAGAGAGYWDHINNPEVYFGGAGAGAGAGAAAAM",
    "peptide_sequence": "YWDHINNPEVYF"
  }'
```

返回：

```json
{
  "peptide_sequence": "YWDHINNPEVYF",
  "peptide_start": 17,
  "peptide_end": 28,
  "total_sasa": 847.32,
  "mean_relative_sasa": 0.61,
  "exposure_ratio": 0.83,
  "residues": [
    {"residue_id": 17, "residue_name": "TYR", "sasa": 92.1, "relative_sasa": 0.36, "is_exposed": true},
    ...
  ],
  "pdb_content": "ATOM  ...",
  "warning": null
}
```

------

## 关键指标怎么解读

| 指标                 | 含义                    | 你们的判断逻辑             |
| -------------------- | ----------------------- | -------------------------- |
| `mean_relative_sasa` | 功能肽平均暴露度（0~1） | > 0.3 认为暴露较好         |
| `exposure_ratio`     | 暴露残基占比            | > 0.6 说明大多数残基在表面 |
| `total_sasa`         | 绝对暴露面积 Å²         | 用于横向比较不同设计方案   |

这三个数字可以直接进入你们构建体比较的表格，作为"结构兼容性评分"的量化依据。