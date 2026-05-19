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

# ── ToxinPred3 多实例（跨进程安全，每个容器独立 2 并发） ──
TOXIN_INSTANCES = ["toxinpred3", "toxinpred3-2", "toxinpred3-3"]


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

# ToxinPred3 分批大小（单条发送，每批此数量后报告进度）
TOXIN_BATCH_PROGRESS = 2000


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
    sem_hemo = asyncio.Semaphore(10)   # HemoPI2 轻量，高并发
    sem_mhc = asyncio.Semaphore(10)    # MHCflurry 可高并发

    log("\n开始安全服务评分（HemoPI2/MHCflurry 与 ToxinPred3 并行）...")

    hemo_chunks = [all_candidates[i:i + 100] for i in range(0, len(all_candidates), 100)]
    mhc_chunks = [all_candidates[i:i + 100] for i in range(0, len(all_candidates), 100)]

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

    # ToxinPred3 多实例并行（每个实例独立 Semaphore(2)，跨进程安全）
    # 按实例分块，每个实例内部用 asyncio.gather 实现 2 并发
    TOXIN_PER_INSTANCE_CONCURRENCY = 2
    TOXIN_MINI_BATCH = 200  # 每实例每批并发数量
    n_instances = len(TOXIN_INSTANCES)
    total_t = len(all_candidates)
    per_instance = total_t // n_instances
    instance_batches = []
    for idx, inst in enumerate(TOXIN_INSTANCES):
        start = idx * per_instance
        end = start + per_instance if idx < n_instances - 1 else total_t
        instance_batches.append((inst, all_candidates[start:end]))

    async def run_instance(inst: str, batch: list[dict],
                           progress: dict[str, int]) -> dict[int, float | None]:
        sem = asyncio.Semaphore(TOXIN_PER_INSTANCE_CONCURRENCY)
        result_map: dict[int, float | None] = {}

        async def score_one(c: dict) -> None:
            async with sem:
                result = await client.predict_single(inst, c["sequence"])
                result_map[c["candidate_id"]] = result.get("score") if result.get("success") else None
                progress["done"] += 1

        for i in range(0, len(batch), TOXIN_MINI_BATCH):
            mini = batch[i:i + TOXIN_MINI_BATCH]
            await asyncio.gather(*[score_one(c) for c in mini], return_exceptions=True)
        return result_map

    async def run_toxin_scoring() -> dict[int, float | None]:
        toxin_map: dict[int, float | None] = {}
        progress = {"done": 0}
        tasks = [run_instance(inst, batch, progress) for inst, batch in instance_batches]

        # 启动进度监控协程
        async def report_progress():
            while True:
                done = progress["done"]
                if done >= total_t:
                    break
                pct = done / total_t * 100
                elapsed = time.time() - start_time
                rate = done / elapsed if elapsed > 0 else 0
                log(f"  ToxinPred3: {done:,}/{total_t:,} ({pct:.1f}%) | {rate:.0f} seq/s | 耗时: {elapsed:.0f}s")
                await asyncio.sleep(30)

        monitor = asyncio.create_task(report_progress())
        results = await asyncio.gather(*tasks, return_exceptions=True)
        monitor.cancel()

        for r in results:
            if isinstance(r, dict):
                toxin_map.update(r)
        return toxin_map

    # 并行执行：HemoPI2/MHCflurry（GPU 快） + ToxinPred3（CPU 慢）
    toxin_task = asyncio.create_task(run_toxin_scoring())

    hemo_results, mhc_results = await asyncio.gather(
        asyncio.gather(*[score_hemo(c) for c in hemo_chunks], return_exceptions=True),
        asyncio.gather(*[score_mhc(c) for c in mhc_chunks], return_exceptions=True),
    )

    hemo_map: dict[int, float | None] = {}
    for r in hemo_results:
        if isinstance(r, dict):
            hemo_map.update(r)
    mhc_map: dict[int, float | None] = {}
    for r in mhc_results:
        if isinstance(r, dict):
            mhc_map.update(r)
    log(f"  HemoPI2: {len(hemo_map):,} 条 ✅")
    log(f"  MHCflurry: {len(mhc_map):,} 条 ✅")

    # 等待 ToxinPred3 完成
    toxin_map = await toxin_task
    log(f"  ToxinPred3: {len(toxin_map):,} 条 ✅")

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
    all_services = info["services"] + [s for s in TOXIN_INSTANCES if s not in info["services"]]
    log(f"Round 2: {info['desc']}")
    log(f"依赖服务: {', '.join(all_services)} (ToxinPred3 × {len(TOXIN_INSTANCES)} 实例)")

    health = ensure_services(all_services, info["profiles"], timeout=180.0)
    unavailable = [s for s, h in health.items() if not h["available"]]
    if unavailable:
        log(f"❌ 服务不可用，终止: {unavailable}")
        sys.exit(1)
    log("✅ 所有服务就绪\n")

    asyncio.run(run(args.toxin_threshold, args.hemo_threshold, args.mhc_threshold))


if __name__ == "__main__":
    main()
