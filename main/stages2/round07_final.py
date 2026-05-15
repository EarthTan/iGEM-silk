"""
Round 7：Final Round — 最终输出

按 SASA 暴露度排序，输出全部 90 个 construct 的最终结果包。

用法：
    uv run python -m main.stages2.round07_final

输入：
    output/round05_3d/constructs/  ← PDB + 元数据 + 评分
    output/round06_pdb_eval/       ← SASA + Aggrescan3D 结果

输出：
    output/round07_final/
    ├── README.md                 ← 全流程报告
    ├── sasa_ranking.csv          ← 全部 90 个 construct SASA 排名
    ├── top10_ranking.csv         ← Top 10 精简表
    ├── score_distribution.json   ← 各分数维度分布
    └── constructs/               ← 每人一个文件夹
        ├── con_XXXX_PEPTIDE_POS/
        │   ├── construct.fasta
        │   ├── construct_omegafold.pdb
        │   ├── scores.json
        │   └── metadata.json
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
STAGE_DIR = OUTPUT_DIR / "round07_final"
CONSTRUCTS_DIR = STAGE_DIR / "constructs"

# ── 字段映射 ──
CSV_FIELDS = [
    "rank", "construct_id", "peptide_id", "peptide_sequence",
    "position", "linker_id", "peptide_composite", "construct_composite",
    "sodope_score", "temstapro_score",
    "omegafold_plddt",
    "sasa_score", "sasa_label",
    "aggrisk_score", "aggrisk_label",
    "final_score",
]

TOP10_FIELDS = [
    "rank", "construct_id", "peptide_id", "peptide_sequence",
    "position", "linker_id", "sasa_score", "construct_composite",
    "omegafold_plddt",
]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    CONSTRUCTS_DIR.mkdir(parents=True, exist_ok=True)

    # ── 1. 加载 SASA 排名 ──
    ranking_csv = OUTPUT_DIR / "round06_pdb_eval" / "final" / "final_ranked_sasa.csv"
    rows = []
    with open(ranking_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"📋 加载 {len(rows)} 个 construct 排名")

    # ── 2. 读取 SASA/A3D 原始数据 ──
    sasa_raw = read_json(OUTPUT_DIR / "round06_pdb_eval" / "raw" / "sasa_results.json")
    a3d_raw = read_json(OUTPUT_DIR / "round06_pdb_eval" / "raw" / "aggrescan3d_results.json")

    # ── 3. 统计分布 ──
    dist_data = {
        "sasa": [],
        "construct_composite": [],
        "plddt": [],
        "aggrisk": [],
    }

    construct_records = []
    for row in rows:
        cid = row["construct_id"]
        con_src = OUTPUT_DIR / "round05_3d" / "constructs" / cid
        scores = read_json(con_src / "scores.json")
        meta = read_json(con_src / "metadata.json")

        sasa_entry = sasa_raw.get(cid, {})
        a3d_entry = a3d_raw.get(cid, {})

        sasa_score = float(row.get("sasa_score", 0) or 0)
        cc = float(row.get("construct_composite", 0) or 0)
        plddt = float(row.get("omegafold_plddt", 0) or 0)
        aggrisk = float(a3d_entry.get("score", 0) or 0)

        dist_data["sasa"].append(sasa_score)
        dist_data["construct_composite"].append(cc)
        dist_data["plddt"].append(plddt)
        dist_data["aggrisk"].append(aggrisk)

        construct_records.append({
            "cid": cid,
            "meta": meta,
            "scores": scores,
            "sasa_entry": sasa_entry,
            "a3d_entry": a3d_entry,
            "sasa_score": sasa_score,
            "cc": cc,
            "plddt": plddt,
        })

    # ── 4. 输出 per-construct 文件夹 ──
    print("📁 生成 construct 文件夹...")
    for rec in construct_records:
        cid = rec["cid"]
        meta = rec["meta"]
        con_src = OUTPUT_DIR / "round05_3d" / "constructs" / cid

        pep_label = meta.get("peptide_id", "unknown").replace("pep_", "pep")
        pos_label = meta.get("position", "X")
        folder_name = f"{cid}_{pep_label}_{pos_label}"
        folder_path = CONSTRUCTS_DIR / folder_name
        folder_path.mkdir(parents=True, exist_ok=True)

        # construct.fasta
        seq = meta.get("construct_sequence", "")
        fasta_lines = [
            f">{cid} | {meta.get('peptide_id','')} | {meta.get('position','')} | {meta.get('linker_id','')} | silk-fibroin fusion",
            seq,
        ]
        (folder_path / "construct.fasta").write_text(
            "\n".join(fasta_lines) + "\n", encoding="utf-8"
        )

        # construct_omegafold.pdb (copy)
        pdb_src = con_src / f"{cid}_omegafold.pdb"
        if pdb_src.exists():
            shutil.copy2(pdb_src, folder_path / "construct_omegafold.pdb")

        # scores.json — 聚合全流水线评分
        combined_scores = {
            "construct_id": cid,
            "peptide_id": meta.get("peptide_id", ""),
            "peptide_sequence": meta.get("peptide_sequence", ""),
            "position": meta.get("position", ""),
            "linker_id": meta.get("linker_id", ""),
            "pipeline_scores": {
                "peptide_composite": rec["scores"].get("peptide_composite"),
                "construct_composite": rec["scores"].get("construct_composite"),
                "sodope": rec["scores"].get("sodope"),
                "temstapro_construct": rec["scores"].get("temstapro_construct"),
                "round3_services": rec["scores"].get("round3_services"),
            },
            "structure": {
                "method": "omegafold",
                "plddt": rec["plddt"],
            },
            "pdb_evaluation": {
                "sasa_score": rec["sasa_score"],
                "sasa_label": rec["sasa_entry"].get("label", ""),
                "sasa_details": rec["sasa_entry"].get("details"),
                "aggrescan3d_score": rec["a3d_entry"].get("score"),
                "aggrescan3d_label": rec["a3d_entry"].get("label", ""),
            },
            "ranking": {
                "criteria": "SASA_exposure",
                "sasa_rank": int(row["sasa_rank"]),
            },
        }
        write_json(folder_path / "scores.json", combined_scores)

        # metadata.json — 原始来源信息
        write_json(folder_path / "metadata.json", meta.get("original_database", {}))

    print(f"  ✅ 共 {len(construct_records)} 个文件夹")

    # ── 5. 写入 sasa_ranking.csv ──
    csv_path = STAGE_DIR / "sasa_ranking.csv"
    # Re-read ranking CSV to get full data with rank
    ranking_rows = []
    with open(ranking_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cid = row["construct_id"]
            meta = read_json(OUTPUT_DIR / "round05_3d" / "constructs" / cid / "metadata.json")
            scores = read_json(OUTPUT_DIR / "round05_3d" / "constructs" / cid / "scores.json")
            a3d = a3d_raw.get(cid, {})
            ranking_rows.append({
                "rank": row["sasa_rank"],
                "construct_id": cid,
                "peptide_id": meta.get("peptide_id", ""),
                "peptide_sequence": meta.get("peptide_sequence", ""),
                "position": meta.get("position", ""),
                "linker_id": meta.get("linker_id", ""),
                "peptide_composite": scores.get("peptide_composite", ""),
                "construct_composite": scores.get("construct_composite", ""),
                "sodope_score": scores.get("sodope", ""),
                "temstapro_score": scores.get("temstapro_construct", ""),
                "omegafold_plddt": row.get("omegafold_plddt", ""),
                "sasa_score": row.get("sasa_score", ""),
                "sasa_label": row.get("sasa_label", ""),
                "aggrisk_score": a3d.get("score", ""),
                "aggrisk_label": a3d.get("label", ""),
                "final_score": row.get("sasa_score", ""),  # SASA = final score
            })
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in ranking_rows:
            w.writerow(r)
    print(f"📄 {csv_path}")

    # ── 6. 写入 top10_ranking.csv ──
    top10_path = STAGE_DIR / "top10_ranking.csv"
    with open(top10_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TOP10_FIELDS)
        w.writeheader()
        for r in ranking_rows[:10]:
            w.writerow({k: r.get(k, "") for k in TOP10_FIELDS})
    print(f"📄 {top10_path}")

    # ── 7. 分布统计 ──
    def describe(vals):
        n = len(vals)
        sv = sorted(vals)
        mean = sum(sv) / n
        median = sv[n // 2] if n % 2 else (sv[n // 2 - 1] + sv[n // 2]) / 2
        std = (sum((x - mean) ** 2 for x in sv) / n) ** 0.5
        return {
            "n": n, "mean": round(mean, 4), "median": round(median, 4),
            "std": round(std, 4), "min": round(sv[0], 4), "max": round(sv[-1], 4),
            "p5": round(sv[int(n * 0.05)], 4), "p95": round(sv[int(n * 0.95)], 4),
        }

    dist = {}
    for key in dist_data:
        if dist_data[key]:
            dist[key] = describe(dist_data[key])
    write_json(STAGE_DIR / "score_distribution.json", dist)

    # ── 8. README.md ──
    top5 = ranking_rows[:5]
    top5_table = "\n".join(
        f"| {r['rank']} | {r['construct_id']} | {r['peptide_sequence']} | "
        f"{r['position']} | {r['linker_id']} | {r['sasa_score']} | {r['construct_composite']} | {r['omegafold_plddt']} |"
        for r in top5
    )

    sasa_d = dist.get("sasa", {})
    cc_d = dist.get("construct_composite", {})
    plddt_d = dist.get("plddt", {})
    agg_d = dist.get("aggrisk", {})

    readme = f"""# Round 7：Final Round — iGEM-silk 抗氧化肽融合蛋白最终结果

**生成日期**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Construct 总数**: 90
**骨架**: 丝素蛋白 (~346 aa) + His6 标签
**排名标准**: SASA 暴露度（功能肽在 3D 结构表面的相对可及表面积）

---

## 全流程回顾

| 阶段 | 步骤 | 输入 → 输出 | 主要服务 | 耗时 |
|------|------|------------|---------|------|
| Round 1 | 轻量过滤 | 25K 肽 → Top 100K | ToxinPred3, AlgPred2, HemoPI2 | ~2 min |
| Round 2 | 评分排序 | 100K → Top 10K | AnOxPePred, BepiPred-3.0, pLM4CPPs, MHCflurry, GraphCPP | ~1 min |
| Round 3 | 重服务 | 10K → Top 80 | BepiPred-3.0, TemStaPro | ~5 min |
| Round 4 | 枚举 | 80 肽 × 6 Linker × 3 位置 → 90 construct | 组合筛选 + SoDoPE | ~2 min |
| Round 5 | 3D 结构预测 | 90 construct → ESMFold + OmegaFold PDB | ESMFold, OmegaFold | ~2.3 h |
| Round 6 | PDB 评估 | 90 PDB → SASA + Aggrescan3D | SASA (FreeSASA), Aggrescan3D | ~3 min |
| **Round 7** | **最终输出** | **SASA 排名 → 最终结果包** | — | — |

## 排名标准

按 **SASA 暴露度** 从高到低排序。SASA（溶剂可及表面积）反映功能肽在融合蛋白 3D 结构中的表面暴露程度：
- **SASA 越高** = 功能肽越暴露在蛋白表面 → 越可能发挥生物活性
- **SASA 越低** = 功能肽被包埋在蛋白内部 → 活性可能受限

## Top 5 排名

| 排名 | Construct | 肽序列 | 位置 | Linker | SASA 暴露度 | 综合分 | pLDDT |
|------|-----------|--------|------|--------|-------------|--------|-------|
{top5_table}

## 分数分布概览

| 维度 | 均值 | 标准差 | 范围 |
|------|------|--------|------|
| SASA 暴露度 | {sasa_d.get('mean', 'N/A')} | {sasa_d.get('std', 'N/A')} | {sasa_d.get('min', 'N/A')} ~ {sasa_d.get('max', 'N/A')} |
| construct_composite | {cc_d.get('mean', 'N/A')} | {cc_d.get('std', 'N/A')} | {cc_d.get('min', 'N/A')} ~ {cc_d.get('max', 'N/A')} |
| OmegaFold pLDDT | {plddt_d.get('mean', 'N/A')} | {plddt_d.get('std', 'N/A')} | {plddt_d.get('min', 'N/A')} ~ {plddt_d.get('max', 'N/A')} |
| Aggrescan3D 风险 | {agg_d.get('mean', 'N/A')} | {agg_d.get('std', 'N/A')} | {agg_d.get('min', 'N/A')} ~ {agg_d.get('max', 'N/A')} |

## 输出目录结构

```
output/round07_final/
├── README.md                     ← 本报告
├── sasa_ranking.csv              ← 全部 90 个 construct SASA 排名
├── top10_ranking.csv             ← Top 10 精简表
├── score_distribution.json       ← 各分数维度分布统计
└── constructs/                   ← 每人一个独立文件夹
    ├── con_0025_pep000743_N/
    │   ├── construct.fasta         ← 完整融合蛋白序列 (FASTA)
    │   ├── construct_omegafold.pdb ← OmegaFold 3D 结构
    │   ├── scores.json             ← 全流水线评分聚合
    │   └── metadata.json           ← 原始数据库来源信息
    ├── con_0030_pep000743_Both/
    └── ... (共 {len(construct_records)} 个文件夹)
```

## 注意事项

- **OmegaFold pLDDT** 均值约 0.42，属于中等偏低置信度，SASA/A3D 结果仅供参考
- SASA 排名仅反映功能肽的空间暴露程度，不直接代表生物活性
- 建议选取 Top 5-10 肽序列进行 wet-lab 验证
- 如需更高精度 3D 结构，可使用 AlphaFold3 做后续精修
"""
    (STAGE_DIR / "README.md").write_text(readme, encoding="utf-8")
    print(f"📄 {STAGE_DIR / 'README.md'}")

    print(f"\n✅ Round 7 完成！输出目录: {STAGE_DIR}")
    print(f"   ├── sasa_ranking.csv ({len(ranking_rows)} 个 construct)")
    print(f"   ├── top10_ranking.csv")
    print(f"   └── constructs/ ({len(construct_records)} 个文件夹)")


if __name__ == "__main__":
    main()
