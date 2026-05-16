# Aggrescan3D 微服务

Aggrescan3D 是基于 PDB 结构的蛋白聚集倾向分析工具。原工具是 Python 2.7
standalone/CLI，本服务通过 conda 环境调用 aggrescan 命令。

## 类型

- 微服务类别：`pdb_service`
- 输入：PDB 文本
- 输出：结构整体聚集风险分数、链级统计、逐残基 A3D score
- 默认端口：`8102`

## 环境准备

Aggrescan3D 依赖 Python 2.7。通过 conda 创建独立环境：

```bash
# 创建 Python 2.7 环境并安装 aggrescan3d
conda create -n aggrescan3d python=2.7
conda install -n aggrescan3d -c lcbio aggrescan3d

# 安装 API wrapper 依赖
cd tools/Aggrescan3D
uv sync
```

启动服务：

```bash
cd tools/Aggrescan3D
uv run python service.py
```

环境变量：
- `AGGRESCAN_CONDA_ENV` — conda 环境路径（默认: `/home/lenovo/miniconda3/envs/aggrescan3d`）

## 测试

健康检查：

```bash
curl http://127.0.0.1:8102/health
```

用已有 PDB 文件测试：

```bash
python - <<'PY'
import json
from pathlib import Path
import httpx

pdb = Path("references/result-kyxq0/model.pdb").read_text()
payload = {
    "pdb_content": pdb,
    "chain_id": "A",
    "peptide_id": "model_kyxq0",
}
r = httpx.post("http://127.0.0.1:8102/predict", json=payload, timeout=600)
print(json.dumps(r.json(), indent=2, ensure_ascii=False)[:4000])
PY
```

## 输出解释

`details.residues` 保留 Aggrescan3D 原始逐残基分数；`score` 是服务层为了统一
API 额外计算的 0-1 聚集风险分数，越高代表聚集风险越高。当前算法用正分残基比例、
正分平均值和最大热点分数做归一化组合；正式排名时建议把它作为反向指标处理。

原始结果文件来自 Aggrescan3D 的 `A3D.csv`：

```text
protein,chain,residue,residue_name,score
```
