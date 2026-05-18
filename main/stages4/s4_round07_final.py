"""
Round 7: 最终排名输出。

Top / Bottom 通道独立排名。排名依据可以从以下方案中选择：
  - sd_weight_3d: 对 SASA, (1-Aggrescan3D), pLDDT 三个 3D 指标做 SD 加权
  - pure_sasa: 直接按 SASA 排序（stages2 经验表明 SASA 区分度最好）

用法:
    uv run python -m main.stages4.s4_round07_final
    uv run python -m main.stages4.s4_round07_final --method sd_weight_3d
    uv run python -m main.stages4.s4_round07_final --method pure_sasa
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from main.stages4.s4_db import PipelineDB
from main.stages4.s4_analytics import compute_variance_weights, apply_weights_and_rank

OUTPUT4 = PROJECT_ROOT / "output4"
FINAL_DIR = OUTPUT4 / "final"
CONSTRUCTS_DIR = FINAL_DIR / "constructs"


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def generate_report(
    ranking: list[dict],
    channel: str,
    method: str,
    db: PipelineDB,
) -> str:
    """生成 Markdown 报告。"""
    lines = [
        f"# Round 7: {channel.title()} 通道最终排名",
        f"",
        f"**排名方法**: {method}",
        f"**候选数**: {len(ranking)}",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        f"| 排名 | Construct ID | 肽序列 | 位置 | Linker | SASA | pLDDT | Aggrescan3D | 综合分 |",
        f"|------|-------------|--------|------|--------|------|-------|-------------|--------|",
    ]

    for r in ranking[:50]:  # Top 50
        cid_str = f"con_{r['construct_id']:04d}"
        lines.append(
            f"| {r['rank']} | {cid_str} | {r['peptide_seq'][:25]} | "
            f"{r['position']} | {r['linker']} | "
            f"{r['sasa_score']:.4f} | {r.get('plddt', 0):.4f} | "
            f"{r.get('aggrisk_score', 0):.4f} | {r['composite_score']:.4f} |"
        )

    return "\n".join(lines)


def run(method: str = "sd_weight_3d"):
    start_time = time.time()

    # ── 1. 连接数据库 ──
    db = PipelineDB()
    conn = db.connect()
    db.init_schema()

    # ── 2. 读取评估结果 ──
    log("读取 PDB 评估结果...")
    rows = conn.execute("""
        SELECT
            p.construct_id,
            p.sasa_score,
            p.aggrescan3d_score,
            s.plddt,
            ct.channel,
            ct.peptide_seq,
            ct.position,
            ct.linker,
            ct.full_sequence
        FROM pdb_eval p
        JOIN structure_results s ON s.construct_id = p.construct_id
        JOIN constructs ct ON ct.construct_id = p.construct_id
        WHERE p.sasa_score IS NOT NULL
        ORDER BY ct.channel, p.sasa_score DESC
    """).fetchall()

    if not rows:
        log("❌ 无 PDB 评估数据，请先运行 Round 6")
        return

    data = [
        {
            "construct_id": int(r[0]),
            "sasa_score": float(r[1]) if r[1] else 0,
            "aggrescan3d_score": float(r[2]) if r[2] else 0,
            "aggrisk_score": 1 - (float(r[2]) if r[2] else 0),
            "plddt": float(r[3]) if r[3] else 0,
            "channel": r[4],
            "peptide_seq": r[5],
            "position": r[6],
            "linker": r[7],
            "full_sequence": r[8],
        }
        for r in rows
    ]

    top_data = [d for d in data if d["channel"] == "top"]
    bottom_data = [d for d in data if d["channel"] == "bottom"]
    log(f"Top: {len(top_data)}, Bottom: {len(bottom_data)}")

    # ── 3. 排名 ──
    def rank_channel(items: list[dict], method: str) -> list[dict]:
        if method == "pure_sasa":
            items = sorted(items, key=lambda x: x["sasa_score"], reverse=True)
            for rank, item in enumerate(items, start=1):
                item["rank"] = rank
                item["composite_score"] = item["sasa_score"]
            return items

        elif method == "sd_weight_3d":
            # 用 SD 加权排名：写入临时表，用 analytics 计算
            # 简化实现：在内存中计算
            sasa_vals = [d["sasa_score"] for d in items]
            agg_vals = [d["aggrisk_score"] for d in items]
            plddt_vals = [d["plddt"] for d in items]

            # 归一化到 [0,1]
            def normalize(vals):
                mn, mx = min(vals), max(vals)
                if mx - mn < 1e-8:
                    return [0.5] * len(vals)
                return [(v - mn) / (mx - mn) for v in vals]

            sasa_norm = normalize(sasa_vals)
            agg_norm = normalize(agg_vals)
            plddt_norm = normalize(plddt_vals)

            # 简单 SD weighting（不使用 analytics 模块以减少 DB 依赖）
            from main.stages4.s4_analytics import winsorized_stddev
            stds = [
                winsorized_stddev(sasa_vals),
                winsorized_stddev(agg_vals),
                winsorized_stddev(plddt_vals),
            ]
            total_std = sum(stds)
            if total_std > 0:
                w_sasa, w_agg, w_plddt = [s / total_std for s in stds]
            else:
                w_sasa, w_agg, w_plddt = 0.5, 0.3, 0.2

            log(f"  SD权重: SASA={w_sasa:.3f}, (1-Agg)={w_agg:.3f}, pLDDT={w_plddt:.3f}")

            for i, item in enumerate(items):
                item["composite_score"] = (
                    w_sasa * sasa_norm[i] + w_agg * agg_norm[i] + w_plddt * plddt_norm[i]
                )

            items = sorted(items, key=lambda x: x["composite_score"], reverse=True)
            for rank, item in enumerate(items, start=1):
                item["rank"] = rank
            return items

        else:
            raise ValueError(f"Unknown method: {method}")

    log(f"\n排名方法: {method}")
    top_ranked = rank_channel(top_data, method)
    bottom_ranked = rank_channel(bottom_data, method) if bottom_data else []

    # ── 4. 输出 ──
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    CONSTRUCTS_DIR.mkdir(parents=True, exist_ok=True)

    # CSV 输出
    def write_csv(items: list[dict], path: Path, channel: str):
        import csv
        with open(path, "w", newline="") as f:
            fieldnames = [
                "rank", "channel", "construct_id", "peptide_seq", "position",
                "linker", "sasa_score", "aggrisk_score", "aggrescan3d_score",
                "plddt", "composite_score",
            ]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for item in items:
                writer.writerow({
                    "rank": item["rank"],
                    "channel": channel,
                    "construct_id": item["construct_id"],
                    "peptide_seq": item["peptide_seq"][:30],
                    "position": item["position"],
                    "linker": item["linker"],
                    "sasa_score": f"{item['sasa_score']:.4f}",
                    "aggrisk_score": f"{item['aggrisk_score']:.4f}",
                    "aggrescan3d_score": f"{item['aggrescan3d_score']:.4f}",
                    "plddt": f"{item['plddt']:.4f}",
                    "composite_score": f"{item['composite_score']:.4f}",
                })

    write_csv(top_ranked, FINAL_DIR / "top_ranking.csv", "top")
    log(f"✅ Top 排名: {len(top_ranked)} ← saved")

    if bottom_ranked:
        write_csv(bottom_ranked, FINAL_DIR / "bottom_ranking.csv", "bottom")
        log(f"✅ Bottom 排名: {len(bottom_ranked)} ← saved")

    # Top 10 摘要
    top10 = top_ranked[:10]
    write_csv(top10, FINAL_DIR / "top10_summary.csv", "top")

    # 分数分布
    dist = {}
    for metric, key in [("sasa", "sasa_score"), ("aggrisk", "aggrisk_score"),
                         ("plddt", "plddt"), ("composite", "composite_score")]:
        vals = [d[key] for d in top_ranked]
        if vals:
            dist[metric] = {
                "n": len(vals),
                "mean": sum(vals) / len(vals),
                "min": min(vals),
                "max": max(vals),
            }

    with open(FINAL_DIR / "score_distribution.json", "w") as f:
        json.dump(dist, f, indent=2, default=str)

    # ── 5. 写入最终排名表 ──
    conn.execute("DELETE FROM final_ranking WHERE 1=1")
    for item in top_ranked:
        conn.execute("""
            INSERT INTO final_ranking
                (construct_id, candidate_id, channel, composite_score, rank, rank_in_channel)
            VALUES (?, NULL, 'top', ?, ?, ?)
        """, [item["construct_id"], item["composite_score"], item["rank"], item["rank"]])
    for item in bottom_ranked:
        conn.execute("""
            INSERT INTO final_ranking
                (construct_id, candidate_id, channel, composite_score, rank, rank_in_channel)
            VALUES (?, NULL, 'bottom', ?, ?, ?)
        """, [item["construct_id"], item["composite_score"], item["rank"], item["rank"]])

    # ── 6. 生成报告 ──
    report = generate_report(top_ranked, "top", method, db)
    with open(FINAL_DIR / "README.md", "w") as f:
        f.write(report)

    total_elapsed = time.time() - start_time
    db.set_checkpoint("round7", "final", "done",
                      total=len(data), processed=len(data))

    log(f"\n{'='*55}")
    log(f"  Round 7 完成!")
    log(f"  Top 排名:   {len(top_ranked)}")
    log(f"  Bottom 排名: {len(bottom_ranked)}")
    log(f"  输出目录:    {FINAL_DIR}")
    log(f"  总耗时:      {total_elapsed:.0f}s")
    log(f"{'='*55}")
    log(f"\nTop {min(5, len(top_ranked))}:")
    for item in top_ranked[:5]:
        cid = f"con_{item['construct_id']:04d}"
        log(f"  #{item['rank']} {cid} | "
            f"SASA={item['sasa_score']:.4f} | "
            f"score={item['composite_score']:.4f}")
    if bottom_ranked:
        log(f"\nBottom {min(5, len(bottom_ranked))}:")
        for item in bottom_ranked[:5]:
            cid = f"con_{item['construct_id']:04d}"
            log(f"  #{item['rank']} {cid} | "
                f"SASA={item['sasa_score']:.4f} | "
                f"score={item['composite_score']:.4f}")

    db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Round 7: 最终排名输出")
    parser.add_argument("--method", choices=["sd_weight_3d", "pure_sasa"],
                        default="sd_weight_3d",
                        help="排名方法: sd_weight_3d (默认) 或 pure_sasa")
    args = parser.parse_args()

    log(f"Round 7: 最终排名输出 (method={args.method})")
    run(method=args.method)


if __name__ == "__main__":
    main()
