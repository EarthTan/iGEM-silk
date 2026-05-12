# Aggrescan3D 微服务

Aggrescan3D 是基于 PDB 结构的蛋白聚集倾向分析工具。原工具是 Python 2.7
standalone/CLI，本服务不把它安装进项目 Python 3.11 环境，而是通过 Docker CLI
调用原作者镜像 `lcbio/a3d_server` 里的 `aggrescan` 命令。

## 类型

- 微服务类别：`pdb_service`
- 输入：PDB 文本
- 输出：结构整体聚集风险分数、链级统计、逐残基 A3D score
- 默认端口：`8102`

## 环境准备

```bash
docker pull lcbio/a3d_server
cd tools/Aggrescan3D
uv sync
```

本地直接启动时，需要系统能访问 Docker：

```bash
cd tools/Aggrescan3D
uv run python service.py
```

如果使用 compose，需要先构建 API wrapper：

```bash
cd tools
docker compose --profile cpu up -d aggrescan3d
```

也可以从项目根目录手动构建 API wrapper：

```bash
docker build -f tools/Aggrescan3D/Dockerfile -t igem-silk/aggrescan3d-api .
docker run --rm -p 8102:8102 \
    -v /var/run/docker.sock:/var/run/docker.sock \
    igem-silk/aggrescan3d-api
```

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
