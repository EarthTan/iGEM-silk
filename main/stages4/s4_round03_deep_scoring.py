"""
Round 3: 深度评分 + 方差加权（全流程唯一加权位置）。

对安全通过的候选运行深度评分服务:
  - BepiPred3: B 细胞表位预测 (GPU)
  - TemStaPro: 热稳定性预测 (GPU)
  - SoDoPE: 溶解度预测 (CPU)
  - pLM4CPPs: 细胞穿透预测 (GPU)
  - GraphCPP: 细胞穿透 GNN (GPU)

然后使用方差感知权重（SD 驱动 + 手动调节）计算综合分并排名。

用法:
    uv run python -m main.stages4.s4_round03_deep_scoring
    uv run python -m main.stages4.s4_round03_deep_scoring \
        --top-pct 5 --anoxpepred-coeff 1.0
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
DEEP_SERVICES = ["bepipred3", "temstapro", "sodope", "plm4cpps", "graphcpp"]


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def get_passed_round2(db: PipelineDB) -> list[dict]:
    """获取 Round 2 安全通过的候选（含通道信息）。"""
    conn = db.connect()
    rows = conn.execute("""
        SELECT p.candidate_id, c.sequence, c.length, p.channel
        FROM round2_passed p
        JOIN candidates c ON c.candidate_id = p.candidate_id
        ORDER BY p.channel, p.candidate_id
    """).fetchall()
    return [
        {"candidate_id": int(r[0]), "sequence": r[1], "length": r[2], "channel": r[3]}
        for r in rows
    ]


async def run(top_pct: float, manual_coeffs: dict[str, float]):
    start_time = time.time()

    # ── 1. 连接数据库 ──
    db = PipelineDB()
    conn = db.connect()
    db.init_schema()

    passed = get_passed_round2(db)
    log(f"安全通过的候选: {len(passed):,} 条")

    if not passed:
        log("❌ 无候选可处理，请先运行 Round 2")
        return

    # ── 2. 检查预打分数据（来自 s4_round03_precompute.py）──
    conn = db.connect()
    complete = conn.execute("""
        SELECT COUNT(*) FROM round2_passed p
        JOIN round3_scores s ON p.candidate_id = s.candidate_id
        WHERE s.bepipred3_score IS NOT NULL
          AND s.temstapro_score IS NOT NULL
          AND s.sodope_score IS NOT NULL
          AND s.plm4cpps_score IS NOT NULL
          AND s.graphcpp_score IS NOT NULL
    """).fetchone()[0]
    total_passed = len(passed)

    if complete >= total_passed:
        log(f"✅ 预打分数据完整 ({complete:,}/{total_passed:,})，跳过评分阶段")
        to_score: list[dict] = []
    else:
        log(f"预打分: {complete:,}/{total_passed:,} 条完整")
        missing_rows = conn.execute("""
            SELECT p.candidate_id
            FROM round2_passed p
            LEFT JOIN round3_scores s ON p.candidate_id = s.candidate_id
            WHERE s.candidate_id IS NULL
               OR s.bepipred3_score IS NULL
               OR s.temstapro_score IS NULL
               OR s.sodope_score IS NULL
               OR s.plm4cpps_score IS NULL
               OR s.graphcpp_score IS NULL
        """).fetchall()
        missing_ids = {int(r[0]) for r in missing_rows}
        to_score = [c for c in passed if c["candidate_id"] in missing_ids]
        log(f"待评分: {len(to_score):,} 条\n")

    if to_score:
        client = ServiceClient(timeout=300.0)
        sem = asyncio.Semaphore(CONCURRENCY)

        chunks = [to_score[i:i + BATCH_SIZE] for i in range(0, len(to_score), BATCH_SIZE)]
        total_chunks = len(chunks)

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

        async def score_service(svc: str) -> dict[str, float]:
            tasks = [score_one(chunk, svc) for chunk in chunks]
            results = await asyncio.gather(*tasks)
            flat: dict[str, float] = {}
            for batch_res in results:
                for r in batch_res:
                    flat[r["peptide_id"]] = r.get("score")
            return flat

        # 并发所有深度服务
        log(f"并发评分 {len(DEEP_SERVICES)} 个服务...")
        svc_tasks = [score_service(svc) for svc in DEEP_SERVICES]
        svc_results = await asyncio.gather(*svc_tasks)

        # 写入评分
        for chunk_start in range(0, len(to_score), BATCH_SIZE):
            batch = to_score[chunk_start:chunk_start + BATCH_SIZE]
            records = []
            for c in batch:
                cid_str = str(c["candidate_id"])
                record = {"candidate_id": c["candidate_id"]}
                for svc_name, svc_map in zip(DEEP_SERVICES, svc_results):
                    score = svc_map.get(cid_str)
                    record[f"{svc_name}_score"] = score
                    record[f"{svc_name}_success"] = score is not None
                records.append(record)
            db.insert_round3_scores(records)
            log(f"  评分写入: {chunk_start + len(batch):,}/{len(to_score):,}")

        await client.close()
        log(f"评分完成: {len(to_score):,} 条")

    # ── 3. 方差感知加权 + 排名 ──
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

    # ── 4. 通道分类统计 ──
    top_n = max(1, int(len(ranking) * top_pct / 100))
    log(f"\n取 Top {top_pct}% = {top_n:,} 候选进入 Round 4")
    log(f"  (排名前 {top_n} 进入构造枚举)")

    total_elapsed = time.time() - start_time
    db.set_checkpoint("round3", "scoring", "done",
                      total=len(passed), processed=len(passed))

    log(f"\n{'='*55}")
    log(f"  Round 3 完成!")
    log(f"  输入:          {len(passed):>10,}")
    log(f"  排名完成:      {len(ranking):>10,}")
    log(f"  → Round 4:    {top_n:>10,}")
    log(f"  总耗时:        {total_elapsed:>8.0f}s ({total_elapsed/60:.1f} min)")
    log(f"{'='*55}")

    db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Round 3: 深度评分 + 方差加权")
    parser.add_argument("--top-pct", type=float, default=5.0,
                        help="取前百分之几进入 Round 4 (default: 5.0)")
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

    if manual_coeffs:
        coeff_str = ", ".join(f"{k}={v}" for k, v in manual_coeffs.items() if not k.startswith("_"))
        log(f"手动系数: {coeff_str}")

    health = ensure_services(info["services"], info["profiles"], timeout=300.0)
    unavailable = [s for s, h in health.items() if not h["available"]]
    if unavailable:
        log(f"❌ 服务不可用，终止: {unavailable}")
        sys.exit(1)
    log("✅ 所有服务就绪\n")

    asyncio.run(run(args.top_pct, manual_coeffs))


if __name__ == "__main__":
    main()
