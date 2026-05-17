"""
Step 1: 轻量初筛 — AnOxPePred(抗氧化) + AlgPred2(过敏原排除)

对 19.9M 候选肽运行两个轻量评分服务:
  - AnOxPePred: 抗氧化活性预测（核心信号，越高越好）
  - AlgPred2: 过敏原预测（硬阈值 ≥0.30 淘汰）

流程:
  1. 确保 Docker 微服务就绪
  2. 从 candidates 表分批读取候选肽
  3. 并发调用两个服务评分
  4. 写入 stage1_scores 表
  5. 应用 AlgPred2 硬过滤 → stage1_passed

用法:
  uv run python -m main.stages3.stage01_lightweight
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
from main.stages3.db import PipelineDB
from main.stages3.docker_utils import ensure_services
from main.stages3.service_map import get_step_services

# ── 配置 ──
DB_BATCH = 100_000           # 每次从 DB 读取的行数
HTTP_BATCH = 1_000           # 每次 HTTP 请求发送的序列数
CONCURRENCY = 5              # 每个服务的并发 HTTP 请求数
PROGRESS_INTERVAL = 10       # 每 N 轮打印一次进度
ALGPRED2_THRESHOLD = 0.30    # AlgPred2 硬阈值（≥此值淘汰）


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


async def run():
    start_time = time.time()

    # ── 1. 连接数据库 ──
    db = PipelineDB()
    db.connect()
    db.init_schema()

    total = db.row_count("candidates")
    last_id = db.get_last_processed_id("stage1_scores")

    log(f"候选池: {total:,} 条")
    log(f"已评分 (stage1_scores): {last_id:,} 条")

    if last_id >= total:
        log("✅ Step 1 评分已完成，跳过评分阶段")
    else:
        log(f"待评分: {total - last_id:,} 条\n")

        # ── 3. 初始化 HTTP 客户端 ──
        client = ServiceClient(timeout=120.0)
        sem = asyncio.Semaphore(CONCURRENCY)

        # ── 4. 主评分循环 ──
        processed = last_id
        round_num = 0
        total_errors = 0
        conn = db.connect()

        while processed < total:
            # 4a. 从 DB 读一批
            rows = conn.execute("""
                SELECT candidate_id, sequence
                FROM candidates
                WHERE candidate_id > ? AND candidate_id <= ?
                ORDER BY candidate_id
            """, [processed, processed + DB_BATCH]).fetchall()

            if not rows:
                break

            candidate_ids = [r[0] for r in rows]
            batch_items = [
                {"peptide_id": str(cid), "sequence": r[1]}
                for cid, r in zip(candidate_ids, rows)
            ]

            # 4b. 拆成 HTTP 子批
            chunks = [
                batch_items[i:i + HTTP_BATCH]
                for i in range(0, len(batch_items), HTTP_BATCH)
            ]

            # 4c. 并发评分两个服务
            async def score_one(chunk: list[dict], svc: str) -> list[dict]:
                async with sem:
                    result = await client.predict_batch(svc, chunk)
                    if result.get("success") and result.get("results"):
                        return result["results"]
                    return [
                        {"peptide_id": item["peptide_id"], "score": None}
                        for item in chunk
                    ]

            async def score_service(svc: str) -> dict[str, float]:
                tasks = [score_one(chunk, svc) for chunk in chunks]
                results = await asyncio.gather(*tasks)
                flat: dict[str, float] = {}
                for batch_res in results:
                    for r in batch_res:
                        flat[r["peptide_id"]] = r.get("score")
                return flat

            anox_map, alg_map = await asyncio.gather(
                score_service("anoxpepred"),
                score_service("algpred2"),
            )

            # 4d. 写入 stage1_scores
            score_records = [
                {
                    "candidate_id": cid,
                    "anoxpepred_score": anox_map.get(str(cid)),
                    "anoxpepred_success": anox_map.get(str(cid)) is not None,
                    "algpred2_score": alg_map.get(str(cid)),
                    "algpred2_success": alg_map.get(str(cid)) is not None,
                }
                for cid in candidate_ids
            ]
            db.insert_stage1_scores(score_records)

            # 4e. 更新进度
            processed += len(rows)
            round_num += 1
            round_errors = sum(
                1 for r in score_records
                if r["anoxpepred_score"] is None or r["algpred2_score"] is None
            )
            total_errors += round_errors

            # 4f. 检查点
            db.set_checkpoint("step1", "lightweight", "running",
                              total=total, processed=processed)

            # 4g. 进度报告
            if round_num % PROGRESS_INTERVAL == 0:
                elapsed = time.time() - start_time
                rate = processed / elapsed if elapsed > 0 else 0
                pct = processed / total * 100
                log(f"进度: {processed:,}/{total:,} ({pct:.1f}%) | "
                    f"{rate:.0f} seq/s | 错误: {total_errors:,} | "
                    f"耗时: {elapsed:.0f}s")

        await client.close()
        log(f"\n评分完成: {processed:,} 条, 错误: {total_errors:,}")

    # ── 5. 应用 AlgPred2 硬过滤 ──
    log("\n应用 AlgPred2 硬过滤...")
    conn = db.connect()
    conn.execute("""
        INSERT INTO stage1_passed (candidate_id, anoxpepred_score, passed_reason)
        SELECT s.candidate_id, s.anoxpepred_score,
               CASE
                   WHEN s.algpred2_score IS NULL THEN 'algpred2_unavailable'
                   ELSE 'algpred2_threshold'
               END
        FROM stage1_scores s
        WHERE s.algpred2_score IS NULL OR s.algpred2_score < ?
        ON CONFLICT (candidate_id) DO NOTHING
    """, [ALGPRED2_THRESHOLD])
    passed = db.row_count("stage1_passed")
    failed = total - passed

    # ── 6. 完成 ──
    total_elapsed = time.time() - start_time
    db.set_checkpoint("step1", "lightweight", "done",
                      total=total, processed=total)

    log(f"\n{'='*55}")
    log(f"  Step 1 完成!")
    log(f"  候选池:        {total:>10,}")
    log(f"  已评分:        {total:>10,}")
    log(f"  通过过滤:      {passed:>10,}")
    log(f"  淘汰 (AlgPred2≥{ALGPRED2_THRESHOLD}): {failed:>10,}")
    log(f"  通过率:        {passed/total*100:>9.1f}%")
    log(f"  总耗时:        {total_elapsed:>8.0f}s ({total_elapsed/60:.1f} min)")
    log(f"{'='*55}")

    db.close()


def main():
    # Docker 启动（在 async 上下文外执行，避免 asyncio.run 嵌套）
    info = get_step_services("step1")
    log(f"Step 1: {info['desc']}")
    log(f"依赖服务: {', '.join(info['services'])}")

    health = ensure_services(info["services"], info["profiles"], timeout=180.0)
    unavailable = [s for s, h in health.items() if not h["available"]]
    if unavailable:
        log(f"❌ 服务不可用，终止: {unavailable}")
        sys.exit(1)
    log("✅ 所有服务就绪\n")

    # 评分循环（async）
    asyncio.run(run())


if __name__ == "__main__":
    main()
