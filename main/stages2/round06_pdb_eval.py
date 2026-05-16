"""
Round 6：PDB 评估 — SASA + Aggrescan3D + 最终综评

对 Round 5 生成的 90 个 OmegaFold PDB 结构运行：
  - SASA (溶剂可及表面积)：评估功能肽在结构表面的暴露程度
  - Aggrescan3D (聚集倾向)：评估整条链的聚集风险

结合已有分数（peptide_composite、SoDoPE、TemStaPro、pLDDT），
计算 Round 6 最终评分，输出全部 90 个 construct 的排名及分数分布。

用法：
    确保以下服务正在运行：
        SASA:        tools/SASA/.venv/bin/python tools/SASA/service.py     (port 8101)
        Aggrescan3D: docker compose --profile cpu up -d aggrescan3d       (port 8102)
    然后：
        uv run python -m main.stages2.round06_pdb_eval

输入：
    output/round05_3d/final/round6_input.json       ← 90 个 construct 列表
    output/round05_3d/constructs/con_XXXX/           ← PDB + 元数据 + 评分

输出：
    output/round06_pdb_eval/
    ├── final/
    │   ├── all_ranked.csv          ← 全部 90 个 construct 的 Round 6 排名
    │   ├── score_distribution.json ← 各分数维度的分布统计
    ├── raw/
    │   ├── sasa_results.json       ← SASA 原始返回
    │   ├── aggrescan3d_results.json ← Aggrescan3D 原始返回
    ├── README.md                   ← 报告
    └── run.log
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "output"
STAGE = "round06_pdb_eval"
STAGE_DIR = OUTPUT_DIR / STAGE
FINAL_DIR = STAGE_DIR / "final"
RAW_DIR = STAGE_DIR / "raw"

LOG_FILE: Path | None = None

# ── 评分权重（初始方案，用户确认分布后可能调整）──
W_CONSTRUCT = 0.50  # construct_composite（肽功能 + SoDoPE + TemStaPro）
W_pLDDT     = 0.15  # OmegaFold pLDDT（归一化后）
W_SASA      = 0.20  # SASA 功能肽暴露度
W_AGG       = 0.15  # 反向聚集风险 (1 - risk_score)

# ── 并发控制 ──
SASA_CONCURRENCY = 10       # SASA 很快，高并发
AGGRESCAN_CONCURRENCY = 2   # Aggrescan3D 内部 semaphore=2，外层保持一致

# ═══════════════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════════════

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    if LOG_FILE:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def make_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def describe(name: str, values: list[float]) -> dict[str, Any]:
    """计算单列分布统计，返回 dict 和可读字符串。"""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "message": f"{name}: 无有效数据"}
    sorted_v = sorted(values)
    mean = sum(sorted_v) / n
    median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    variance = sum((x - mean) ** 2 for x in sorted_v) / n
    std = variance ** 0.5
    p5 = sorted_v[int(n * 0.05)]
    p25 = sorted_v[int(n * 0.25)]
    p75 = sorted_v[int(n * 0.75)]
    p95 = sorted_v[int(n * 0.95)]
    return {
        "name": name,
        "n": n,
        "mean": round(mean, 4),
        "median": round(median, 4),
        "std": round(std, 4),
        "min": round(sorted_v[0], 4),
        "max": round(sorted_v[-1], 4),
        "p5": round(p5, 4),
        "p25": round(p25, 4),
        "p75": round(p75, 4),
        "p95": round(p95, 4),
    }


def print_distribution(stats: dict[str, Any]):
    """打印分布到终端，方便用户快速查看。"""
    name = stats["name"]
    values = stats  # already computed
    lines = [
        f"\n{'='*60}",
        f"  {name}",
        f"{'='*60}",
        f"  均值:   {values['mean']:.4f}",
        f"  中位数: {values['median']:.4f}",
        f"  标准差: {values['std']:.4f}",
        f"  P5:     {values['p5']:.4f}  |  P25: {values['p25']:.4f}  |  P75: {values['p75']:.4f}  |  P95: {values['p95']:.4f}",
        f"  范围:   {values['min']:.4f} ~ {values['max']:.4f}",
    ]
    print("\n".join(lines))


# ═══════════════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════════════

def load_constructs() -> list[dict]:
    """加载全部 90 个 construct 的元数据、评分、PDB 路径。"""
    input_path = OUTPUT_DIR / "round05_3d" / "final" / "round6_input.json"
    construct_list = read_json(input_path)["results"]

    constructs = []
    for entry in construct_list:
        cid = entry["construct_id"]
        con_dir = OUTPUT_DIR / "round05_3d" / "constructs" / cid

        # 元数据
        meta = read_json(con_dir / "metadata.json")
        scores = read_json(con_dir / "scores.json")

        # OmegaFold PDB
        pdb_path = con_dir / f"{cid}_omegafold.pdb"
        if not pdb_path.exists():
            log(f"  ⚠ {cid}: OmegaFold PDB 缺失，跳过")
            continue

        constructs.append({
            "construct_id": cid,
            "peptide_id": meta["peptide_id"],
            "peptide_sequence": meta["peptide_sequence"],
            "position": meta["position"],
            "linker_id": meta["linker_id"],
            "pdb_path": pdb_path,

            # 已有评分
            "peptide_composite": scores.get("peptide_composite"),
            "construct_composite": scores.get("construct_composite"),
            "sodope_score": scores.get("sodope"),
            "temstapro_score": scores.get("temstapro_construct"),
            "omegafold_plddt": scores.get("structure", {}).get("omegafold", {}).get("plddt"),
            "round3_services": scores.get("round3_services", {}),

            # SASA / Aggrescan3D（待填充）
            "sasa_score": None,
            "sasa_label": None,
            "sasa_details": None,
            "aggrisk_score": None,
            "aggrisk_label": None,
            "aggrisk_details": None,

            # Round 6 最终分
            "round6_score": None,
        })

    return constructs


# ═══════════════════════════════════════════════════════════════════════
# 调用 PDB 服务
# ═══════════════════════════════════════════════════════════════════════

async def call_sasa_batch(constructs: list[dict]) -> None:
    """并发调用 SASA 服务，传入功能肽序列以计算肽区暴露度。"""
    import httpx

    url = "http://127.0.0.1:8101/predict/batch"
    sem = asyncio.Semaphore(SASA_CONCURRENCY)
    results: list[tuple[str, dict | None]] = []

    async def call_one(c: dict) -> tuple[str, dict | None]:
        cid = c["construct_id"]
        pdb_content = c["pdb_path"].read_text(encoding="utf-8")
        payload = {
            "pdb_content": pdb_content,
            "peptide_id": cid,
            "sequence": c["peptide_sequence"],
            "chain_id": "A",
        }
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(url, json={"requests": [payload]})
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("results"):
                            return cid, data["results"][0]
                    return cid, None
            except Exception as e:
                log(f"  ⚠ SASA {cid} 失败: {e}")
                return cid, None

    tasks = [call_one(c) for c in constructs]
    batch_results = await asyncio.gather(*tasks)

    # 写回 construct 列表（注意 batch 返回的每个 result 中 score/label 在顶层）
    for cid, result in batch_results:
        for c in constructs:
            if c["construct_id"] == cid and result and result.get("success", True):
                c["sasa_score"] = result.get("score")
                c["sasa_label"] = result.get("label")
                c["sasa_details"] = result.get("details")

    # 保存原始返回
    raw = {}
    for cid, result in batch_results:
        raw[cid] = result
    write_json(RAW_DIR / "sasa_results.json", raw)

    ok = sum(1 for c in constructs if c["sasa_score"] is not None)
    log(f"  SASA 完成: {ok}/{len(constructs)}")


async def call_aggrescan3d_batch(constructs: list[dict]) -> None:
    """并发调用 Aggrescan3D 服务。"""
    import httpx

    url = "http://127.0.0.1:8102/predict/batch"
    sem = asyncio.Semaphore(AGGRESCAN_CONCURRENCY)
    results: list[tuple[str, dict | None]] = []

    async def call_one(c: dict) -> tuple[str, dict | None]:
        cid = c["construct_id"]
        pdb_content = c["pdb_path"].read_text(encoding="utf-8")
        payload = {
            "pdb_content": pdb_content,
            "peptide_id": cid,
            "sequence": None,          # Aggrescan3D 不需要定位肽
            "chain_id": "A",
        }
        async with sem:
            try:
                async with httpx.AsyncClient(timeout=600.0) as client:
                    resp = await client.post(url, json={"requests": [payload]})
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("results"):
                            return cid, data["results"][0]
                    return cid, None
            except Exception as e:
                log(f"  ⚠ Aggrescan3D {cid} 失败: {e}")
                return cid, None

    tasks = [call_one(c) for c in constructs]
    batch_results = await asyncio.gather(*tasks)

    for cid, result in batch_results:
        for c in constructs:
            if c["construct_id"] == cid and result and result.get("success", True):
                c["aggrisk_score"] = result.get("score")
                c["aggrisk_label"] = result.get("label")
                c["aggrisk_details"] = result.get("details")

    raw = {}
    for cid, result in batch_results:
        raw[cid] = result
    write_json(RAW_DIR / "aggrescan3d_results.json", raw)

    ok = sum(1 for c in constructs if c["aggrisk_score"] is not None)
    log(f"  Aggrescan3D 完成: {ok}/{len(constructs)}")


# ═══════════════════════════════════════════════════════════════════════
# 评分计算
# ═══════════════════════════════════════════════════════════════════════

def compute_scores(constructs: list[dict]) -> list[dict]:
    """计算 Round 6 综合评分。"""

    # 收集所有有效值用于归一化
    plddt_vals = [c["omegafold_plddt"] for c in constructs if c["omegafold_plddt"] is not None]
    sasa_vals = [c["sasa_score"] for c in constructs if c["sasa_score"] is not None]
    agg_vals = [c["aggrisk_score"] for c in constructs if c["aggrisk_score"] is not None]

    # pLDDT 归一化: 映射到 [0, 1]
    plddt_min = min(plddt_vals) if plddt_vals else 0
    plddt_max = max(plddt_vals) if plddt_vals else 1
    plddt_range = plddt_max - plddt_min if plddt_max > plddt_min else 1

    log(f"\n  归一化基准:")
    log(f"    pLDDT:        min={plddt_min:.4f}, max={plddt_max:.4f}, range={plddt_range:.4f}")
    if sasa_vals:
        log(f"    SASA:         min={min(sasa_vals):.4f}, max={max(sasa_vals):.4f}")
    if agg_vals:
        log(f"    Aggrescan3D:  min={min(agg_vals):.4f}, max={max(agg_vals):.4f}")

    scored = []
    for c in constructs:
        # pLDDT 归一化
        plddt_norm = (c["omegafold_plddt"] - plddt_min) / plddt_range if c["omegafold_plddt"] is not None else 0.5

        # SASA 暴露度 — 直接用 mean_relative_sasa (0-1)
        sasa = c["sasa_score"] if c["sasa_score"] is not None else 0.0

        # Aggrescan3D 反向 — 聚集风险低 = 好
        agg_inv = 1.0 - (c["aggrisk_score"] if c["aggrisk_score"] is not None else 0.5)

        # construct_composite — 已有综合分
        cc = c["construct_composite"] if c["construct_composite"] is not None else 0.0

        round6 = (
            W_CONSTRUCT * cc
            + W_pLDDT * plddt_norm
            + W_SASA * sasa
            + W_AGG * agg_inv
        )

        c["plddt_norm"] = round(plddt_norm, 4)
        c["agg_inv"] = round(agg_inv, 4)
        c["round6_score"] = round(round6, 4)
        scored.append(c)

    # 排名
    scored.sort(key=lambda x: x["round6_score"] or 0, reverse=True)
    for i, c in enumerate(scored):
        c["round6_rank"] = i + 1

    return scored


# ═══════════════════════════════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════════════════════════════

def extract_detail_fields(c: dict) -> dict:
    """提取用于 CSV 的关键字段。"""
    sasa_pep = (c.get("sasa_details") or {}).get("peptide", {})
    return {
        "construct_id": c["construct_id"],
        "peptide_id": c["peptide_id"],
        "peptide_sequence": c["peptide_sequence"],
        "position": c["position"],
        "linker_id": c["linker_id"],
        # 已有分数
        "peptide_composite": c.get("peptide_composite"),
        "construct_composite": c.get("construct_composite"),
        "sodope_score": c.get("sodope_score"),
        "temstapro_score": c.get("temstapro_score"),
        "omegafold_plddt": c.get("omegafold_plddt"),
        # Round 6 新增
        "sasa_score": c.get("sasa_score"),
        "sasa_label": c.get("sasa_label"),
        "sasa_mean_rel": sasa_pep.get("mean_relative_sasa"),
        "sasa_exposure_ratio": sasa_pep.get("exposure_ratio"),
        "aggrisk_score": c.get("aggrisk_score"),
        "aggrisk_label": c.get("aggrisk_label"),
        # 归一化分量
        "plddt_norm": c.get("plddt_norm"),
        "agg_inv": c.get("agg_inv"),
        # Round 6 结果
        "round6_score": c.get("round6_score"),
        "round6_rank": c.get("round6_rank"),
    }


def save_csv(constructs: list[dict], path: Path):
    """保存 CSV。"""
    import csv
    fieldnames = [
        "round6_rank", "construct_id", "peptide_id", "peptide_sequence",
        "position", "linker_id",
        "round6_score", "construct_composite", "peptide_composite",
        "sodope_score", "temstapro_score",
        "omegafold_plddt", "plddt_norm",
        "sasa_score", "sasa_label", "sasa_mean_rel", "sasa_exposure_ratio",
        "aggrisk_score", "aggrisk_label", "agg_inv",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for c in constructs:
            d = extract_detail_fields(c)
            w.writerow(d)


def save_readme(constructs: list[dict], dist: dict[str, Any], elapsed: float):
    """生成 README 报告。"""
    n = len(constructs)
    n_ok = sum(1 for c in constructs if c["round6_score"] is not None)

    top5 = constructs[:5]
    top5_lines = "\n".join(
        f"  {c['round6_rank']}. {c['construct_id']:12s} | {c['peptide_id']:12s} | "
        f"cc={c['construct_composite']:.4f} sasa={c['sasa_score']:.4f} agg={c['aggrisk_score']:.4f} "
        f"plddt={c['omegafold_plddt']:.4f} | **round6={c['round6_score']:.4f}**"
        for c in top5
    )

    # 分布文本
    dist_lines = []
    for key, label in [
        ("construct_composite", "construct_composite（肽功能+SoDoPE+TemStaPro）"),
        ("omegafold_plddt", "OmegaFold pLDDT"),
        ("sasa_score", "SASA 功能肽暴露度"),
        ("aggrisk_score", "Aggrescan3D 聚集风险"),
        ("round6_score", "Round 6 综合评分"),
    ]:
        s = dist.get(key)
        if s and s.get("n", 0) > 0:
            dist_lines.append(f"- **{label}**: mean={s['mean']:.4f}, median={s['median']:.4f}, "
                              f"std={s['std']:.4f}, range=[{s['min']:.4f}, {s['max']:.4f}], "
                              f"P5={s['p5']:.4f}, P95={s['p95']:.4f}")

    readme = f"""# Round 6：PDB 评估 — 报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**耗时**: {elapsed:.0f} 秒 ({elapsed/60:.1f} 分钟)
**Construct 数**: {n} / {n_ok} 有效

## 评分公式

```
round6_score = {W_CONSTRUCT} * construct_composite
             + {W_pLDDT} * pLDDT_norm
             + {W_SASA} * SASA_exposure
             + {W_AGG} * (1 - aggrisk)
```

- **construct_composite**: 0.65×肽综合 + 0.30×SoDoPE + 0.10×TemStaPro
- **pLDDT_norm**: OmegaFold pLDDT 在 90 个 construct 内归一化到 [0,1]
- **SASA_exposure**: 功能肽区平均相对 SASA (0-1)，越高=越暴露
- **(1 - aggrisk)**: Aggrescan3D 风险分反向，越低聚集=越高分

## 分数分布

{chr(10).join(dist_lines)}

## Top 5

| 排名 | Construct | 肽 | 分量 | Round6 |
|------|-----------|-----|------|--------|
{chr(10).join(
    f"| {c['round6_rank']} | {c['construct_id']} | {c['peptide_id']} | "
    f"cc={c['construct_composite']:.3f} sasa={c['sasa_score']:.3f} agg={c['aggrisk_score']:.3f} | **{c['round6_score']:.4f}** |"
    for c in top5
)}

## 输出文件

- `final/all_ranked.csv` — 全部 {n} 个 construct 的 {', '.join(f for f in [
    "round6_rank", "construct_composite", "omegafold_plddt", "sasa_score", "aggrisk_score", "round6_score"])}
- `final/score_distribution.json` — 各分数维度的分布统计
- `raw/sasa_results.json` — SASA 原始返回
- `raw/aggrescan3d_results.json` — Aggrescan3D 原始返回

## 备注

当前权重仅为初始方案，尚未最终确认。
"""
    path = STAGE_DIR / "README.md"
    path.write_text(readme, encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

async def main():
    global LOG_FILE
    t0 = time.time()

    # 目录
    make_dir(FINAL_DIR)
    make_dir(RAW_DIR)
    LOG_FILE = STAGE_DIR / "run.log"

    log("=" * 60)
    log("Round 6：PDB 评估 — SASA + Aggrescan3D")
    log("=" * 60)

    # 1. 加载
    log("\n📂 加载 construct 数据...")
    constructs = load_constructs()
    log(f"  已加载 {len(constructs)} 个 construct")

    # 2. 调用 SASA
    log("\n🔬 调用 SASA...")
    await call_sasa_batch(constructs)

    # 3. 调用 Aggrescan3D
    log("\n🧬 调用 Aggrescan3D...")
    await call_aggrescan3d_batch(constructs)

    # 4. 计算评分
    log("\n📊 计算 Round 6 评分...")
    constructs = compute_scores(constructs)

    # 5. 分布统计
    log("\n📈 分数分布:")
    distributions = {}
    for key, label in [
        ("construct_composite", "construct_composite"),
        ("omegafold_plddt", "OmegaFold pLDDT"),
        ("sasa_score", "SASA 暴露度"),
        ("aggrisk_score", "Aggrescan3D 风险"),
        ("round6_score", "Round 6 综合评分"),
        ("plddt_norm", "pLDDT 归一化"),
        ("agg_inv", "反向聚集分"),
    ]:
        vals = [c.get(key) for c in constructs if c.get(key) is not None]
        if vals:
            dist = describe(label, vals)
            distributions[key] = dist
            print_distribution(dist)

    write_json(FINAL_DIR / "score_distribution.json", distributions)

    # 6. 保存 CSV
    csv_path = FINAL_DIR / "all_ranked.csv"
    save_csv(constructs, csv_path)
    log(f"\n✅ CSV 已保存: {csv_path}")

    # 7. 输出 Top/Bottom
    log(f"\n🏆 Top 5:")
    for c in constructs[:5]:
        log(f"  {c['round6_rank']}. {c['construct_id']:12s} | "
            f"cc={c['construct_composite']:.4f} sasa={c['sasa_score']:.4f} "
            f"agg={c['aggrisk_score']:.4f} plddt={c['omegafold_plddt']:.4f} | "
            f"round6={c['round6_score']:.4f}")

    log(f"\n📉 Bottom 5:")
    for c in constructs[-5:]:
        log(f"  {c['round6_rank']}. {c['construct_id']:12s} | "
            f"cc={c['construct_composite']:.4f} sasa={c['sasa_score']:.4f} "
            f"agg={c['aggrisk_score']:.4f} plddt={c['omegafold_plddt']:.4f} | "
            f"round6={c['round6_score']:.4f}")

    # 8. README
    elapsed = time.time() - t0
    save_readme(constructs, distributions, elapsed)

    total_time = time.time() - t0
    log(f"\n✅ Round 6 完成！耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    log(f"  CSV: {csv_path}")
    log(f"  分布: {FINAL_DIR / 'score_distribution.json'}")


if __name__ == "__main__":
    asyncio.run(main())
