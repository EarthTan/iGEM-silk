"""
Round 2: 安全筛检 — 纯硬阈值，无加权。

对 Top + Bottom 通道的候选运行三个安全服务:
  - ToxinPred3: 毒性预测 (CPU, ≥0.38 淘汰)
  - HemoPI2: 溶血性预测 (CPU, ≥0.55 淘汰)
  - MHCflurry: MHC-I 结合预测 (GPU, ≥0.5 淘汰)

每个安全属性独立淘汰。未通过任意安全项即淘汰，不参与后续轮次。

用法:
    uv run python -m main.stages4.s4_round02_safety_screen
    uv run python -m main.stages4.s4_round02_safety_screen \
        --toxin-threshold 0.38 --hemo-threshold 0.55 --mhc-threshold 0.5
"""

from __future__ import annotations

import asyncio
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

# ── 默认阈值 ──
TOXIN_THRESHOLD = 0.38   # ToxinPred3 ≥ 0.38 → 有毒
HEMO_THRESHOLD = 0.55    # HemoPI2 ≥ 0.55 → 溶血
MHC_THRESHOLD = 0.5      # MHCflurry ≥ 0.5 → 强免疫原性


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def run(toxin_threshold: float, hemo_threshold: float, mhc_threshold: float):
    start_time = time.time()

    # ── 1. 连接数据库 ──
    db = PipelineDB()
    conn = db.connect()
    db.init_schema()

    # ── 2. 获取待处理的候选（Top + Bottom 通道） ──
    top_candidates = db.get_channel_candidates("top")
    bottom_candidates = db.get_channel_candidates("bottom")
    all_candidates = top_candidates + bottom_candidates

    log(f"Top 通道: {len(top_candidates):,} 条")
    log(f"Bottom 通道: {len(bottom_candidates):,} 条")
    log(f"待筛检总计: {len(all_candidates):,} 条")

    # 检查是否已有评分
    last_id = db.get_last_processed_id("round2_scores")
    if last_id > 0:
        log(f"已评分 (round2_scores): {last_id:,} 条")

    # ── 3. 并发评分三个安全服务 ──
    client = ServiceClient(timeout=180.0)
    sem_toxin = asyncio.Semaphore(2)   # ToxinPred3 线程不安全，低并发
    sem_hemo = asyncio.Semaphore(10)   # HemoPI2 轻量，高并发
    sem_mhc = asyncio.Semaphore(10)    # MHCflurry 可高并发

    log("\n开始安全服务评分...")

    # 将候选分批（ToxinPred3 需要更小的 batch）
    toxin_chunks = [[c] for c in all_candidates]  # 单条发送
    hemo_chunks = [all_candidates[i:i + 100] for i in range(0, len(all_candidates), 100)]
    mhc_chunks = [all_candidates[i:i + 100] for i in range(0, len(all_candidates), 100)]

    async def score_toxin(chunk: list[dict]) -> dict[int, float | None]:
        async with sem_toxin:
            peptide_id = chunk[0]["candidate_id"]
            result = await client.predict_single("toxinpred3", chunk[0]["sequence"])
            return {peptide_id: result.get("score") if result.get("success") else None}

    async def score_hemo(chunk: list[dict]) -> dict[int, float | None]:
        async with sem_hemo:
            items = [{"peptide_id": str(c["candidate_id"]), "sequence": c["sequence"]} for c in chunk]
            result = await client.predict_batch("hemopi2", items)
            if result.get("success") and result.get("results"):
                return {int(r["peptide_id"]): r.get("score") for r in result["results"]}
            return {c["candidate_id"]: None for c in chunk}

    async def score_mhc(chunk: list[dict]) -> dict[int, float | None]:
        async with sem_mhc:
            items = [{"peptide_id": str(c["candidate_id"]), "sequence": c["sequence"]} for c in chunk]
            result = await client.predict_batch("mhcflurry", items)
            if result.get("success") and result.get("results"):
                return {int(r["peptide_id"]): r.get("score") for r in result["results"]}
            return {c["candidate_id"]: None for c in chunk}

    # 并发执行三个服务
    toxin_results, hemo_results, mhc_results = await asyncio.gather(
        asyncio.gather(*[score_toxin(c) for c in toxin_chunks], return_exceptions=True),
        asyncio.gather(*[score_hemo(c) for c in hemo_chunks], return_exceptions=True),
        asyncio.gather(*[score_mhc(c) for c in mhc_chunks], return_exceptions=True),
    )

    # 合并结果
    toxin_map: dict[int, float | None] = {}
    for r in toxin_results:
        if isinstance(r, dict):
            toxin_map.update(r)

    hemo_map: dict[int, float | None] = {}
    for r in hemo_results:
        if isinstance(r, dict):
            hemo_map.update(r)

    mhc_map: dict[int, float | None] = {}
    for r in mhc_results:
        if isinstance(r, dict):
            mhc_map.update(r)

    # ── 4. 写入评分 ──
    score_records = [
        {
            "candidate_id": c["candidate_id"],
            "toxinpred3_score": toxin_map.get(c["candidate_id"]),
            "toxinpred3_success": toxin_map.get(c["candidate_id"]) is not None,
            "hemopi2_score": hemo_map.get(c["candidate_id"]),
            "hemopi2_success": hemo_map.get(c["candidate_id"]) is not None,
            "mhcflurry_score": mhc_map.get(c["candidate_id"]),
            "mhcflurry_success": mhc_map.get(c["candidate_id"]) is not None,
        }
        for c in all_candidates
    ]
    written = db.insert_round2_scores(score_records)
    log(f"评分写入完成: {written:,} 条")

    await client.close()

    # ── 5. 应用安全硬阈值 ──
    log(f"\n应用安全硬阈值...")
    log(f"  ToxinPred3 ≥ {toxin_threshold} → 淘汰")
    log(f"  HemoPI2 ≥ {hemo_threshold} → 淘汰")
    log(f"  MHCflurry ≥ {mhc_threshold} → 淘汰")

    result = db.apply_safety_thresholds(
        toxin_threshold=toxin_threshold,
        hemo_threshold=hemo_threshold,
        mhc_threshold=mhc_threshold,
    )

    log(f"\n  安全筛检结果:")
    log(f"    ToxinPred3 淘汰: {result['details']['toxin']:,}")
    log(f"    HemoPI2 淘汰:    {result['details']['hemo']:,}")
    log(f"    MHCflurry 淘汰:  {result['details']['mhc']:,}")
    log(f"    合计淘汰:        {result['excluded']:,}")
    log(f"    安全通过:        {result['passed']:,}")

    total_elapsed = time.time() - start_time
    db.set_checkpoint("round2", "safety", "done",
                      total=len(all_candidates), processed=len(all_candidates))

    log(f"\n{'='*55}")
    log(f"  Round 2 完成!")
    log(f"  输入:          {len(all_candidates):>10,}")
    log(f"  安全通过:      {result['passed']:>10,}")
    log(f"  淘汰:          {result['excluded']:>10,}")
    log(f"  总耗时:        {total_elapsed:>8.0f}s")
    log(f"{'='*55}")

    db.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Round 2: 安全筛检（硬阈值）")
    parser.add_argument("--toxin-threshold", type=float, default=TOXIN_THRESHOLD)
    parser.add_argument("--hemo-threshold", type=float, default=HEMO_THRESHOLD)
    parser.add_argument("--mhc-threshold", type=float, default=MHC_THRESHOLD)
    args = parser.parse_args()

    info = get_round_services("round2")
    log(f"Round 2: {info['desc']}")
    log(f"依赖服务: {', '.join(info['services'])}")

    health = ensure_services(info["services"], info["profiles"], timeout=180.0)
    unavailable = [s for s, h in health.items() if not h["available"]]
    if unavailable:
        log(f"❌ 服务不可用，终止: {unavailable}")
        sys.exit(1)
    log("✅ 所有服务就绪\n")

    asyncio.run(run(args.toxin_threshold, args.hemo_threshold, args.mhc_threshold))


if __name__ == "__main__":
    main()
