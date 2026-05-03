这是一个**序列位置 → PDB 残基编号**的映射问题，逻辑很清晰，代码也不复杂。

------

## 核心逻辑

```
全长 FASTA 序列
  → 找功能肽的起止位置（字符串匹配）→ 得到 start_idx, end_idx
  → AlphaFold/ESMFold 输出的 PDB 文件，残基编号默认就是 1-indexed 的序列位置
  → 按残基编号过滤 PDB → 得到功能肽对应的 3D 坐标
```

因为 ESMFold/AlphaFold 输出的 PDB 残基编号（`ATOM` 行的第 5/6 列）直接对应 FASTA 的位置，所以不需要额外对齐，找到序列位置就找到了结构位置。

------

## 完整代码

```python
import re
from Bio import PDB
from Bio.PDB import PDBIO, Select
import numpy as np

# ─── 输入 ───────────────────────────────────────────────
FULL_SEQUENCE  = "MAAAAAGGAGAGAGAGAGAGAGAGYWDHINNPEVYFGGAGAGAGAGAGAGAGAGAAAAM"
PEPTIDE_SEQ    = "YWDHINNPEVYF"     # 功能肽序列
PDB_FILE       = "predicted.pdb"   # ESMFold/AlphaFold 输出
CHAIN_ID       = "A"

# ─── Step 1: 在全长序列中定位功能肽 ─────────────────────
match = re.search(PEPTIDE_SEQ, FULL_SEQUENCE)
if not match:
    raise ValueError(f"功能肽 {PEPTIDE_SEQ} 在序列中未找到")

# 转成 1-indexed（PDB 残基编号从 1 开始）
pep_start = match.start() + 1
pep_end   = match.end()       # inclusive
pep_residue_ids = list(range(pep_start, pep_end + 1))

print(f"功能肽位于序列第 {pep_start}–{pep_end} 位，共 {len(pep_residue_ids)} 个残基")

# ─── Step 2: 解析 PDB，提取功能肽残基 ───────────────────
parser   = PDB.PDBParser(QUIET=True)
structure = parser.get_structure("fusion", PDB_FILE)
model    = structure[0]
chain    = model[CHAIN_ID]

peptide_residues = []
for res in chain:
    if res.id[1] in pep_residue_ids:
        peptide_residues.append(res)

print(f"在 PDB 中找到 {len(peptide_residues)} 个对应残基")

# ─── Step 3: 计算 Cα 坐标（用于后续 SASA / 可视化）──────
ca_coords = []
for res in peptide_residues:
    if "CA" in res:
        ca_coords.append(res["CA"].get_vector().get_array())
        print(f"  残基 {res.resname} {res.id[1]}: CA = {res['CA'].get_vector()}")

ca_coords = np.array(ca_coords)

# ─── Step 4: 把功能肽区域单独保存为 PDB（供 A3D 等工具使用）
class PeptideSelect(Select):
    def accept_residue(self, res):
        return res.id[1] in pep_residue_ids

io = PDBIO()
io.set_structure(structure)
io.save("peptide_region.pdb", PeptideSelect())
print("功能肽区域已保存为 peptide_region.pdb")
```

------

## 拿到坐标之后，算 SASA（暴露性）

这是你们真正要的指标，用 `freesasa` 库可以直接算：

```python
import freesasa

# 对全长融合蛋白算 SASA
struct_fs = freesasa.Structure(PDB_FILE)
result    = freesasa.calc(struct_fs)

# 只看功能肽残基的 SASA
total_peptide_sasa = 0
per_residue = []

for res_id in pep_residue_ids:
    sel_str = f"resi {res_id} and chain {CHAIN_ID}"
    sel = freesasa.selectArea([("pep", sel_str)], struct_fs, result)
    sasa_val = sel.get("pep", 0)
    total_peptide_sasa += sasa_val
    per_residue.append((res_id, round(sasa_val, 2)))

print(f"\n功能肽总 SASA: {total_peptide_sasa:.2f} Å²")
print("逐残基 SASA:")
for rid, sval in per_residue:
    bar = "█" * int(sval / 10)
    print(f"  残基 {rid:3d}: {sval:7.2f} Å²  {bar}")
```

------

## 输出示例

```
功能肽位于序列第 24–35 位，共 12 个残基
在 PDB 中找到 12 个对应残基
  残基 TYR 24: CA = <Vector 12.3, 5.1, 8.9>
  残基 TRP 25: CA = <Vector 14.1, 5.8, 7.2>
  ...

功能肽总 SASA: 847.32 Å²
逐残基 SASA:
  残基  24:   92.10 Å²  █████████
  残基  25:   43.50 Å²  ████
  残基  26:  110.20 Å²  ███████████
  ...
```

------

## 一个需要注意的边界情况

如果你们的功能肽序列在全长 FASTA 中**出现多次**（比如你们设计了多拷贝插入），`re.search` 只会找第一个。换成 `re.finditer` 就能拿到所有位置：

```python
all_matches = [(m.start()+1, m.end()) for m in re.finditer(PEPTIDE_SEQ, FULL_SEQUENCE)]
print(f"功能肽出现 {len(all_matches)} 次，位置：{all_matches}")
```

这套逻辑可以直接插进你们的 P0 流程里——ESMFold 跑完之后，自动提取功能肽区域 SASA，输出一个数字用于构建体比较。