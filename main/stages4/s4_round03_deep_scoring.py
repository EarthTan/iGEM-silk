"""
Round 3: 深度评分 + 方差加权（全流程唯一加权位置）+ ToxinPred3 阈值。

对安全通过的候选运行 6 个并行服务:
  - BepiPred3: B 细胞表位预测 (GPU)
  - TemStaPro: 热稳定性预测 (GPU)
  - SoDoPE: 溶解度预测 (CPU)
  - pLM4CPPs: 细胞穿透预测 (GPU)
  - GraphCPP: 细胞穿透 GNN (GPU)
  - ToxinPred3: 毒性预测 (CPU, ≥0.38 淘汰)

ToxinPred3 分数写入 round3_scores 表，打分后应用硬阈值淘汰，
不参与 SD 加权排名。

用法:
    uv run python -m main.stages4.s4_round03_deep_scoring
    uv run python -m main.stages4.s4_round03_deep_scoring \
        --max-top 150000 --max-bottom 50000 --top-pct 5
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from main.client import ServiceClient
from main.stages4.s4_db import PipelineDB
from main.stages4.s4_docker_utils import ensure_services
from main.stages4.s4_service_map import get_round_services
from main.stages4.s4_analytics import compute_variance_weights, apply_weights_and_rank

# ── 配置 ──
BATCH_SIZE = 1_000
CONCURRENCY = 5
PROGRESS_INTERVAL = 5
TOXIN_THRESHOLD = 0.38

# 参与打分的全部服务（含 ToxinPred3，CPU 无 GPU 竞争）
ALL_SERVICES = ["bepipred3", "temstapro", "sodope", "plm4cpps", "graphcpp", "toxinpred3"]
# 参与 SD 加权排名的服务（ToxinPred3 是硬阈值，不参与加权）
DEEP_SERVICES = ["bepipred3", "temstapro", "sodope", "plm4cpps", "graphcpp"]


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def get_passed_round2(db: PipelineDB, max_top: int = 150000, max_bottom: int = 50000) -> list[dict]:
    """获取 Round 2 安全通过的候选（各通道按 rank_in_channel 限流）。

    Top 通道取 AnOxPePred 最佳（rank 最小）的前 max_top 条；
    Bottom 通道取 AnOxPePred 最差（rank 最大）的后 max_bottom 条。
    """
    conn = db.connect()

    # Top: 最佳抗氧化分（rank_in_channel 最小）
    top_rows = conn.execute("""
        SELECT p.candidate_id, c.sequence, c.length, 'top'
        FROM round2_passed p
        JOIN candidates c ON c.candidate_id = p.candidate_id
        JOIN round1_channels ch ON ch.candidate_id = p.candidate_id
        WHERE p.channel = 'top' AND ch.rank_in_channel <= ?
        ORDER BY ch.rank_in_channel
    """, [max_top]).fetchall()

    # Bottom: 最差抗氧化分（rank_in_channel 最大）
    bottom_rows = conn.execute("""
        SELECT p.candidate_id, c.sequence, c.length, 'bottom'
        FROM round2_passed p
        JOIN candidates c ON c.candidate_id = p.candidate_id
        JOIN round1_channels ch ON ch.candidate_id = p.candidate_id
        WHERE p.channel = 'bottom'
        ORDER BY ch.rank_in_channel DESC
        LIMIT ?
    """, [max_bottom]).fetchall()

    rows = top_rows + bottom_rows
    return [
        {"candidate_id": int(r[0]), "sequence": r[1], "length": r[2], "channel": r[3]}
        for r in rows
    ]


async def run(top_pct: float, manual_coeffs: dict[str, float],
              max_top: int = 150000, max_bottom: int = 50000,
              toxin_threshold: float = 0.38):
    start_time = time.time()

    # ── 1. 连接数据库 ──
    db = PipelineDB()
    conn = db.connect()
    db.init_schema()

    passed = get_passed_round2(db, max_top=max_top, max_bottom=max_bottom)
    log(f"候选输入（Top ≤{max_top:,} + Bottom ≤{max_bottom:,}）: {len(passed):,} 条")

    if not passed:
        log("❌ 无候选可处理，请先运行 Round 2")
        return

    # ── 2. 评分阶段：6 服务并行（含 ToxinPred3）──
    client = ServiceClient(timeout=300.0)
    sem = asyncio.Semaphore(CONCURRENCY)

    chunks = [passed[i:i + BATCH_SIZE] for i in range(0, len(passed), BATCH_SIZE)]

    async def score_one(chunk: list[dict], svc: str) -> list[dict]:
        async with sem:
            items = [
                {"peptide_id": str(c["candidate_id"]), "sequence": c["sequence"]}
                for c in chunk
            ]
            result = await client.predict_batch(svc, items)
            if result.get("success") and result.get("results"):
                return result["results"]
            return [{"peptide_id": item["peptide_id"], "score": None} for item in items]

    async def score_service(svc: str) -> dict[str, float | None]:
        tasks = [score_one(chunk, svc) for chunk in chunks]
        results = await asyncio.gather(*tasks)
        flat: dict[str, float | None] = {}
        for batch_res in results:
            for r in batch_res:
                flat[r["peptide_id"]] = r.get("score")
        return flat

    # 并发所有 6 个服务（ToxinPred3 是 CPU，与 GPU 服务无竞争）
    log(f"并发评分 {len(ALL_SERVICES)} 个服务（含 ToxinPred3）...")
    svc_tasks = [score_service(svc) for svc in ALL_SERVICES]
    svc_results = await asyncio.gather(*svc_tasks)

    # 写入评分（含 ToxinPred3 列）
    for chunk_start in range(0, len(passed), BATCH_SIZE):
        batch = passed[chunk_start:chunk_start + BATCH_SIZE]
        records = []
        for c in batch:
            cid_str = str(c["candidate_id"])
            record = {"candidate_id": c["candidate_id"]}
            for svc_name, svc_map in zip(ALL_SERVICES, svc_results):
                score = svc_map.get(cid_str)
                record[f"{svc_name}_score"] = score
                record[f"{svc_name}_success"] = score is not None
            records.append(record)
        db.insert_round3_scores(records)
        log(f"  评分写入: {min(chunk_start + BATCH_SIZE, len(passed)):,}/{len(passed):,}")

    await client.close()
    log(f"评分完成: {len(passed):,} 条 ✅")

    # ── 3. ToxinPred3 硬阈值淘汰 ──
    log(f"\nToxinPred3 硬阈值 (≥{toxin_threshold} 淘汰)...")
    toxin_result = db.apply_toxin_threshold(threshold=toxin_threshold)
    log(f"  ToxinPred3 淘汰: {toxin_result['excluded']:,}")
    log(f"  排名剩余: {toxin_result['remaining']:,}")

    # ── 4. 方差感知加权 + 排名 ──
    log("\n计算方差感知权重...")

    score_columns = [f"{svc}_score" for svc in DEEP_SERVICES]

    weights_result = compute_variance_weights(
        db,
        table="round3_scores",
        score_columns=score_columns,
        stage_name="round3",
        manual_coefficients=manual_coeffs,
    )

    log(f"\n应用权重并排名...")
    ranking = apply_weights_and_rank(
        db,
        table="round3_scores",
        score_columns=score_columns,
        weights=weights_result["final_weights"],
        stage_name="round3",
        rank_table="round3_ranking",
    )

    # ── 5. 通道分类统计 ──
    top_n = max(1, int(len(ranking) * top_pct / 100))
    log(f"\n取 Top {top_pct}% = {top_n:,} 候选进入 Round 4")

    total_elapsed = time.time() - start_time
    db.set_checkpoint("round3", "scoring", "done",
                      total=len(passed), processed=len(passed))

    log(f"\n{'='*55}")
    log(f"  Round 3 完成!")
    log(f"  输入:          {len(passed):>10,}")
    log(f"  ToxinPred3 淘汰:{toxin_result['excluded']:>10,}")
    log(f"  排名完成:      {len(ranking):>10,}")
    log(f"  → Round 4:    {top_n:>10,}")
    log(f"  总耗时:        {total_elapsed:>8.0f}s ({total_elapsed/60:.1f} min)")
    log(f"{'='*55}")

    db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Round 3: 深度评分 + ToxinPred3 + 方差加权")
    parser.add_argument("--top-pct", type=float, default=5.0,
                        help="取前百分之几进入 Round 4 (default: 5.0)")
    parser.add_argument("--max-top", type=int, default=150000,
                        help="Top 通道取前 N 条 (default: 150000)")
    parser.add_argument("--max-bottom", type=int, default=50000,
                        help="Bottom 通道取前 N 条 (default: 50000)")
    parser.add_argument("--toxin-threshold", type=float, default=TOXIN_THRESHOLD,
                        help="ToxinPred3 阈值，≥此值淘汰 (default: 0.38)")
    parser.add_argument("--anoxpepred-coeff", type=float, default=None,
                        help="AnOxPePred 手动系数，如 1.3 (默认不参与加权)")
    parser.add_argument("--bepipred3-coeff", type=float, default=1.0)
    parser.add_argument("--temstapro-coeff", type=float, default=1.0)
    parser.add_argument("--sodope-coeff", type=float, default=1.0)
    parser.add_argument("--plm4cpps-coeff", type=float, default=1.0)
    parser.add_argument("--graphcpp-coeff", type=float, default=1.0)
    parser.add_argument("--adjust-reason", type=str, default="默认配置，无手动调节")
    args = parser.parse_args()

    # 构建手动系数（只包含有值的）
    manual_coeffs: dict[str, float] = {}
    for svc in ["bepipred3", "temstapro", "sodope", "plm4cpps", "graphcpp"]:
        val = getattr(args, f"{svc}_coeff")
        if val is not None:
            manual_coeffs[f"{svc}_score"] = val
    if args.anoxpepred_coeff is not None:
        manual_coeffs["anoxpepred_score"] = args.anoxpepred_coeff
    manual_coeffs["_reason"] = args.adjust_reason

    info = get_round_services("round3")
    log(f"Round 3: {info['desc']}")
    log(f"依赖服务: {', '.join(info['services'])}")
    log(f"输入限制: Top ≤{args.max_top:,}, Bottom ≤{args.max_bottom:,}")
    log(f"ToxinPred3 阈值: ≥{args.toxin_threshold}")

    if manual_coeffs:
        coeff_str = ", ".join(f"{k}={v}" for k, v in manual_coeffs.items() if not k.startswith("_"))
        log(f"手动系数: {coeff_str}")

    health = ensure_services(info["services"], info["profiles"], timeout=300.0)
    unavailable = [s for s, h in health.items() if not h["available"]]
    if unavailable:
        log(f"❌ 服务不可用，终止: {unavailable}")
        sys.exit(1)
    log("✅ 所有服务就绪\n")

    asyncio.run(run(args.top_pct, manual_coeffs,
                    max_top=args.max_top, max_bottom=args.max_bottom,
                    toxin_threshold=args.toxin_threshold))


if __name__ == "__main__":
    main()
