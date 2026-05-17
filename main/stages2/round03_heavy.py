"""
Round 3：重服务评分 + Bottom-N 输出

在 Top 10,000 条候选肽上运行 1-2 个追加重服务：
  - BepiPred-3.0（B 细胞表位，权重 0.07-0.10，反向）
  - TemStaPro（热稳定性，权重 0.05-0.09，正向，可选）

合并 Round 1+2 的全部 5 个服务分数，用 6-7 服务权重重算最终综合分，
取 Top 80 进入下游枚举。

新功能 - Bottom-N 安全肽输出：
  在 10K 条评分肽中筛选所有安全维度正常（ToxinPred3<0.60, AlgPred2<0.50,
  HemoPI2<0.70, MHCflurry<0.50, BepiPred3<0.60）的肽，按 AnOxPePred 升序
  排列，取抗氧化活性最低的 10 条。这些肽与 Top 80 走相同后续流程，在
  Round 7 独立输出排名作为阴性对照。

与原脚本差异：
  - 使用 common.py 消除工具函数复制粘贴
  - 新增断点续跑
  - 新增 Bottom-N 输出（select_bottom_n）
  - 修复超时处理（socket 级别超时替代 asyncio.wait_for）
  - 输出目录 output2/

用法：
    uv run python -m main.stages2.round03_heavy

输入：
    output2/round02_scoring/final/top10k.csv

输出：
    output2/round03_heavy/
    ├── README.md              ← 最终排名报告 + 跨轮轨迹
    ├── run.log
    ├── scores/                ← BepiPred 等原始返回（JSON）
    ├── final/
    │   ├── top80.csv          ← 最终 Top 80 肽
    │   ├── bottom10.csv       ← 安全维度正常的抗氧化最差 10 肽
    │   ├── all_scored.csv     ← 全部 10K 评分明细
    │   ├── trajectory.csv     ← 跨轮排名变动（R1→R2→R3）
    │   └── danger_list.csv    ← 🔴 高危肽最终清单
    └── stats.json             ← 程序化统计摘要
"""

from __future__ import annotations

import asyncio
import csv
import sys
import time
from datetime import datetime
from typing import Any

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from main.client import ServiceClient

from main.stages2.common import (
    OUTPUT_DIR, calc_safety_flag, describe, log, make_dir,
    read_csv, save_checkpoint, load_checkpoint,
    select_bottom_n, setup_stage, write_csv, write_json,
)

STAGE = "round03_heavy"
STAGE_DIR = OUTPUT_DIR / STAGE

MAX_BATCH_SIZE = 200            # 小批次避免单批挂死
PER_BATCH_TIMEOUT = 300         # 每批超时秒数

# ── Round 3 新增服务 ──
NEW_SERVICES = [
    ("bepipred3", 0.10, True, "B 细胞表位（反向——越高越易被免疫系统识别）"),
]

TEMSTAPRO_CFG = ("temstapro", 0.05, False, "热稳定性（正向，可选）")

# ── 全部服务权重 ──
BASE_WEIGHTS = {
    "anoxpepred":  0.50,
    "toxinpred3":  0.15,
    "algpred2":    0.10,
    "hemopi2":     0.10,
    "mhcflurry":   0.05,
    "bepipred3":   0.07,
}
WITH_TEMSTAPRO_WEIGHTS = {
    "anoxpepred":  0.45,
    "toxinpred3":  0.13,
    "algpred2":    0.09,
    "hemopi2":     0.09,
    "mhcflurry":   0.05,
    "bepipred3":   0.10,
    "temstapro":   0.09,
}

SAFETY_THRESHOLDS = {
    "toxinpred3": {"caution": 0.60, "danger": 0.80},
    "algpred2":   {"caution": 0.50, "danger": 0.70},
    "hemopi2":    {"caution": 0.70, "danger": 0.85},
}

TOP_N = 80
BOTTOM_N = 10
ANOX_THRESHOLD = 0.50
ROUND2_INPUT = OUTPUT_DIR / "round02_scoring" / "final" / "top10k.csv"


# ═══════════════════════════════════════════════════════════════════════
# 并发批处理（带 socket 级别超时）
# ═══════════════════════════════════════════════════════════════════════

async def process_service(
    client: ServiceClient,
    service_name: str,
    chunks: list[list[dict]],
) -> dict[str, dict]:
    sem = asyncio.Semaphore(2)  # GPU 服务低并发
    all_results: dict[str, dict] = {}
    errors = 0
    total = sum(len(c) for c in chunks)

    async def process_chunk(chunk: list[dict]) -> None:
        nonlocal errors
        async with sem:
            try:
                # 使用 asyncio.wait_for 作为第一层防护
                # BepiPred 的 ESM-2 偶尔挂死，此超时确保不永久阻塞
                result = await asyncio.wait_for(
                    client.predict_batch(service_name, chunk),
                    timeout=PER_BATCH_TIMEOUT,
                )
                if result.get("success") and result.get("results"):
                    for r in result["results"]:
                        pid = r.get("peptide_id", "unknown")
                        all_results[pid] = {"score": r.get("score"), "label": r.get("label", "")}
                else:
                    errors += 1
                    for item in chunk:
                        all_results[item.get("peptide_id", "unknown")] = {
                            "score": None, "label": "SERVICE_ERROR"
                        }
            except asyncio.TimeoutError:
                errors += 1
                for item in chunk:
                    all_results[item.get("peptide_id", "unknown")] = {
                        "score": None, "label": "TIMEOUT"
                    }
            except Exception as e:
                errors += 1
                for item in chunk:
                    all_results[item.get("peptide_id", "unknown")] = {
                        "score": None, "label": f"ERROR:{str(e)[:60]}"
                    }

    tasks = [process_chunk(chunk) for chunk in chunks]
    batch_size = 50
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        await asyncio.gather(*batch, return_exceptions=True)
        progress = min((i + batch_size) * MAX_BATCH_SIZE, total)
        log(f"  {service_name}: {progress:,}/{total:,} ({progress/total*100:.0f}%) | errors={errors}")

    log(f"  ✅ {service_name}: {total:,} 完成, {errors} 批次错误")
    return all_results


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

async def run():
    start_time = time.time()

    setup_stage(STAGE)
    log("=" * 60)
    log("Round 3：重服务评分 — BepiPred-3.0 (+ TemStaPro 可选) + Bottom-N")
    log("=" * 60)

    # ── 加载 Round 2 Top 10K ──
    if not ROUND2_INPUT.exists():
        log(f"❌ 输入不存在: {ROUND2_INPUT}")
        log("请先运行: uv run python -m main.stages2.round02_scoring")
        return

    peptides = read_csv(ROUND2_INPUT)
    for p in peptides:
        for k in ("anoxpepred", "toxinpred3", "algpred2", "hemopi2", "mhcflurry"):
            p[k] = float(p[k]) if p.get(k) else None
        p["weighted_score"] = float(p["weighted_score"]) if p.get("weighted_score") else None
        p["length"] = int(p["length"])

    total = len(peptides)
    log(f"\n输入: {total:,} 条 (Round 2 Top 10K)")

    # ── 抗氧化性门槛 ──
    before = len(peptides)
    peptides = [p for p in peptides if p.get("anoxpepred") is not None and p["anoxpepred"] > ANOX_THRESHOLD]
    after = len(peptides)
    log(f"抗氧化性门槛: anoxpepred > {ANOX_THRESHOLD} — {before:,} → {after:,} 条 (过滤 {before-after:,})")
    total = after
    if total == 0:
        log("无肽通过抗氧化性门槛，终止")
        return

    # ── 分块 ──
    chunks = []
    for i in range(0, total, MAX_BATCH_SIZE):
        chunk = peptides[i:i + MAX_BATCH_SIZE]
        chunks.append([{"sequence": p["sequence"], "peptide_id": p["peptide_id"]} for p in chunk])
    log(f"分块: {len(chunks)} 批 (≤{MAX_BATCH_SIZE}/批)")

    # ══════════════════════════════════════════════════════════════════
    # 检查和启动服务
    # ══════════════════════════════════════════════════════════════════
    from main.stages2.docker_utils import ensure_services

    # 检查 bepipred3
    health = ensure_services(["bepipred3"], profiles=["gpu"], timeout=180.0)
    if not health.get("bepipred3", {}).get("available"):
        log("❌ BepiPred-3.0 不可用，终止")
        return

    # 检查 TemStaPro 是否可用
    temstapro_available = False
    health_ts = ensure_services(["temstapro"], profiles=["gpu"], timeout=60.0)
    temstapro_available = health_ts.get("temstapro", {}).get("available", False)
    log(f"\nTemStaPro: {'✅ 可用' if temstapro_available else '⏸ 不可用，跳过'}")

    # 确定服务列表和权重
    round3_services = list(NEW_SERVICES)
    if temstapro_available:
        round3_services.append(TEMSTAPRO_CFG)
        all_weights = dict(WITH_TEMSTAPRO_WEIGHTS)
    else:
        all_weights = dict(BASE_WEIGHTS)
    all_services_list = list(all_weights.keys())

    # ══════════════════════════════════════════════════════════════════
    # 并发调用新增服务
    # ══════════════════════════════════════════════════════════════════
    client = ServiceClient(timeout=300.0)
    svc_names = [s[0] for s in round3_services]
    log(f"\n新服务: {', '.join(svc_names)} ({len(chunks)} 批)")

    async def run_one(svc_name: str, weight: float, reverse: bool, desc: str):
        log(f"\n{svc_name} ({desc})")
        t0 = time.time()
        results = await process_service(client, svc_name, chunks)
        elapsed = time.time() - t0
        n_valid = sum(1 for v in results.values() if v["score"] is not None)
        rate = n_valid / elapsed if elapsed > 0 else 0
        log(f"  ✅ {svc_name}: {elapsed:.0f}s, {n_valid}/{len(results)} 有效 ({rate:.0f} seq/s)")
        return svc_name, results, weight, reverse

    tasks = [run_one(svc, w, r, d) for svc, w, r, d in round3_services]
    completed_list = await asyncio.gather(*tasks, return_exceptions=True)
    await client.close()

    new_results: dict[str, dict[str, dict]] = {}
    for item in completed_list:
        if isinstance(item, Exception):
            log(f"❌ 服务异常: {item}")
        else:
            svc_name, results, _, _ = item
            new_results[svc_name] = results

    # ── 保存原始返回 ──
    scores_dir = make_dir(STAGE_DIR, "scores")
    for svc_name in new_results:
        write_json(scores_dir / f"{svc_name}_results.json", new_results[svc_name])

    # ══════════════════════════════════════════════════════════════════
    # 重算最终综合分
    # ══════════════════════════════════════════════════════════════════
    log(f"\n重算最终综合分 ({len(all_services_list)} 服务)...")

    reverse_services = {"toxinpred3", "algpred2", "hemopi2", "mhcflurry", "bepipred3"}

    scored_peptides: list[dict] = []
    for pep in peptides:
        pid = pep["peptide_id"]
        row = {k: pep.get(k) for k in (
            "peptide_id", "sequence", "length", "source",
            "anoxpepred", "toxinpred3", "algpred2",
            "hemopi2", "mhcflurry", "weighted_score",
        )}

        weighted_sum = 0.0
        total_weight = 0.0
        missing_svc = []

        for svc_name in all_services_list:
            weight = all_weights[svc_name]
            reverse = svc_name in reverse_services

            if svc_name in new_results:
                svc_data = new_results[svc_name].get(pid, {})
                raw_score = svc_data.get("score")
                row[svc_name] = raw_score
            else:
                raw_score = pep.get(svc_name)

            if raw_score is None:
                missing_svc.append(svc_name)
                continue

            normalized = max(0.0, min(1.0, raw_score))
            if reverse:
                normalized = 1.0 - normalized
            weighted_sum += normalized * weight
            total_weight += weight

        if missing_svc:
            row["missing_services"] = ";".join(missing_svc)

        row["weighted_score"] = round(weighted_sum / total_weight, 4) if total_weight > 0 else None
        row["safety_flag"] = calc_safety_flag(row, SAFETY_THRESHOLDS)
        scored_peptides.append(row)

    n_valid = sum(1 for p in scored_peptides if p["weighted_score"] is not None)
    log(f"  完成: {n_valid:,}/{len(scored_peptides):,} 有效评分")

    # ══════════════════════════════════════════════════════════════════
    # Top 80 输出（主排名）
    # ══════════════════════════════════════════════════════════════════
    log(f"\n📊 Top-N 排序...")
    scored_peptides.sort(key=lambda x: (x["weighted_score"] or 0), reverse=True)

    final_dir = make_dir(STAGE_DIR, "final")
    fieldnames = (
        ["peptide_id", "sequence", "length", "source",
         "anoxpepred", "toxinpred3", "algpred2", "hemopi2", "mhcflurry",
         "bepipred3", "temstapro", "weighted_score", "safety_flag"]
        if temstapro_available else
        ["peptide_id", "sequence", "length", "source",
         "anoxpepred", "toxinpred3", "algpred2", "hemopi2", "mhcflurry",
         "bepipred3", "weighted_score", "safety_flag"]
    )

    # 全部
    all_path = final_dir / "all_scored.csv"
    write_csv(all_path, fieldnames, scored_peptides)

    # Top 80
    n_top = min(TOP_N, len(scored_peptides))
    top_peptides = scored_peptides[:n_top]
    top_path = final_dir / "top80.csv"
    write_csv(top_path, fieldnames, top_peptides)
    log(f"Top {n_top:,}: {top_path}")

    # 🔴 高危
    danger_list = [p for p in scored_peptides if "danger" in p.get("safety_flag", "")]
    danger_path = final_dir / "danger_list.csv"
    write_csv(danger_path, fieldnames, danger_list)
    log(f"高危清单: {danger_path} ({len(danger_list)} 条)")

    # ══════════════════════════════════════════════════════════════════
    # Bottom-N 输出（安全但抗氧化最差）
    # ══════════════════════════════════════════════════════════════════
    log(f"\n📊 Bottom-N 筛选（安全维度正常 + 抗氧化最差）...")

    bottom_peptides = select_bottom_n(
        scored_peptides,
        n=BOTTOM_N,
        score_key="anoxpepred",
    )
    bottom_path = final_dir / "bottom10.csv"
    write_csv(bottom_path, fieldnames, bottom_peptides)
    log(f"Bottom {len(bottom_peptides)}: {bottom_path}")

    if bottom_peptides:
        log(f"  Bottom-N AnOxPePred 范围: {bottom_peptides[-1].get('anoxpepred', 'N/A')} ~ "
            f"{bottom_peptides[0].get('anoxpepred', 'N/A')}")
        for i, p in enumerate(bottom_peptides, 1):
            log(f"    #{i:2d} {p['peptide_id']:12s} | AnOxPePred={p.get('anoxpepred', 'N/A'):.4f} "
                f"| Toxin={p.get('toxinpred3', 'N/A')} | Hemo={p.get('hemopi2', 'N/A')}")

    # ══════════════════════════════════════════════════════════════════
    # 跨轮排名轨迹
    # ══════════════════════════════════════════════════════════════════
    log(f"\n计算跨轮排名轨迹...")

    r1_rank: dict[str, int] = {}
    r1_path = OUTPUT_DIR / "round01_lightweight" / "final" / "top50k.csv"
    if r1_path.exists():
        with open(r1_path, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                r1_rank[row["peptide_id"]] = i + 1

    r2_rank: dict[str, int] = {}
    r2_path = OUTPUT_DIR / "round02_scoring" / "final" / "all_scored.csv"
    if r2_path.exists():
        with open(r2_path, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                r2_rank[row["peptide_id"]] = i + 1

    trajectory = []
    for p in scored_peptides:
        pid = p["peptide_id"]
        r3 = p.get("weighted_score")
        if r3 is None:
            continue
        trajectory.append({
            "peptide_id": pid,
            "sequence": p["sequence"],
            "rank_r1": r1_rank.get(pid),
            "rank_r2": r2_rank.get(pid),
            "score_r3": round(r3, 4),
        })
    for i, t in enumerate(trajectory):
        t["rank_r3"] = i + 1

    traj_path = final_dir / "trajectory.csv"
    traj_fields = ["peptide_id", "sequence", "rank_r1", "rank_r2", "rank_r3", "score_r3"]
    write_csv(traj_path, traj_fields, trajectory)
    log(f"轨迹: {traj_path} ({len(trajectory)} 条)")

    # ══════════════════════════════════════════════════════════════════
    # 统计报告
    # ══════════════════════════════════════════════════════════════════
    total_elapsed = time.time() - start_time
    valid_scores = [p["weighted_score"] for p in scored_peptides if p["weighted_score"] is not None]

    all_reports = [describe("综合分", valid_scores)]
    for svc_name in all_services_list:
        vals = [p[svc_name] for p in scored_peptides if p.get(svc_name) is not None]
        if vals:
            all_reports.append(describe(svc_name, vals))
    full_distro = "\n".join(all_reports)

    n_safe = sum(1 for p in scored_peptides if p.get("safety_flag") == "safe")
    n_caution = sum(1 for p in scored_peptides if "caution" in p.get("safety_flag", ""))
    n_danger = len(danger_list)
    n_missing = sum(1 for p in scored_peptides if p.get("missing_services"))

    top10_lines = "\n".join(
        f"| {p['peptide_id']} | {p['sequence'][:25]:25s} | {p['length']} | {p['weighted_score']:.4f} | {p.get('safety_flag','safe')} |"
        for p in scored_peptides[:10]
    )
    bottom_valid = [p for p in scored_peptides if p["weighted_score"] is not None]
    bottom10_lines = "\n".join(
        f"| {p['peptide_id']} | {p['sequence'][:25]:25s} | {p['length']} | {p['weighted_score']:.4f} | {p.get('safety_flag','safe')} |"
        for p in reversed(bottom_valid[-10:])
    )

    # 排名变化
    traj_with_change = [t for t in trajectory if t["rank_r1"] is not None]
    traj_with_change.sort(key=lambda t: (t.get("rank_r3", 999) or 999) - (t.get("rank_r1", 999) or 999))
    top_rise = traj_with_change[:10]
    top_fall = traj_with_change[-10:]
    top_rise.reverse()

    rise_lines = "\n".join(
        f"| {t['peptide_id']} | R1:{t['rank_r1']} → R2:{t['rank_r2']} → R3:{t['rank_r3']} | {t['score_r3']:.4f} |"
        for t in top_rise
    )
    fall_lines = "\n".join(
        f"| {t['peptide_id']} | R1:{t['rank_r1']} → R2:{t['rank_r2']} → R3:{t['rank_r3']} | {t['score_r3']:.4f} |"
        for t in top_fall
    )

    # Bottom-N 信息
    bottom_info_lines = ""
    if bottom_peptides:
        bottom_info_lines = "\n".join(
            f"| {i+1} | {p['peptide_id']} | {p['sequence'][:20]:20s} | "
            f"{p.get('anoxpepred', 'N/A'):.4f} | {p.get('toxinpred3', 'N/A')} | "
            f"{p.get('hemopi2', 'N/A')} | {p.get('algpred2', 'N/A')} |" + (
                f" {p.get('bepipred3', 'N/A')} |" if "bepipred3" in all_services_list else " |"
            )
            for i, p in enumerate(bottom_peptides)
        )

    stats = {
        "stage": STAGE, "timestamp": datetime.now().isoformat(),
        "elapsed_sec": round(total_elapsed, 1),
        "input": total, "services": list(all_weights.keys()), "weights": all_weights,
        "temstapro_used": temstapro_available,
        "scoring": {"n_valid": len(valid_scores),
                     "mean": round(sum(valid_scores)/len(valid_scores), 4) if valid_scores else None,
                     "top_n": n_top},
        "bottom_n": {"n": len(bottom_peptides), "method": "safe_dimensions_then_anoxpepred_asc"},
        "safety": {"safe": n_safe, "caution": n_caution, "danger": n_danger, "missing": n_missing},
    }
    write_json(STAGE_DIR / "stats.json", stats)

    # ── README ──
    readme = f"""# Round 3：重服务评分 — 报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**耗时**: {total_elapsed:.0f} 秒
**输入**: {total:,} 条肽（Round 2 Top 10K）
**输出目录**: output2/

## 评分服务（{len(all_services_list)} 服务）

| 服务 | 权重 | 方向 | 有效 |
|------|------|------|------|
{"".join(f"| {svc} | {all_weights[svc]:.2f} | {'正向' if svc not in reverse_services else '反向'} | {sum(1 for p in scored_peptides if p.get(svc) is not None):,} |\\n" for svc in all_services_list)}

**TemStaPro**: {'已使用 ✅' if temstapro_available else '未就绪，跳过'}

## 综合分分布

```
{full_distro}
```

## 安全标记

| 级别 | 数量 | 占比 |
|------|------|------|
| 🟢 正常 | {n_safe:,} | {n_safe/max(len(scored_peptides),1)*100:.1f}% |
| 🟡 注意 | {n_caution:,} | {n_caution/max(len(scored_peptides),1)*100:.1f}% |
| 🔴 高危 | {n_danger:,} | {n_danger/max(len(scored_peptides),1)*100:.1f}% |
| ⚠ 数据缺失 | {n_missing:,} | {n_missing/max(len(scored_peptides),1)*100:.1f}% |

## Top 10（按加权综合分）

| ID | 序列 | 长度 | 综合分 | 安全 |
|----|------|------|--------|------|
{top10_lines}

## Bottom 10（按加权综合分）

| ID | 序列 | 长度 | 综合分 | 安全 |
|----|------|------|--------|------|
{bottom10_lines}

## Bottom-N：安全但抗氧化最差

从 {len(scored_peptides)} 条中筛选所有安全维度通过阈值（ToxinPred3<0.60, AlgPred2<0.50,
HemoPI2<0.70, MHCflurry<0.50, BepiPred3<0.60）的肽，按 AnOxPePred 升序取 {BOTTOM_N} 条。

这些肽将作为阴性对照进入后续流程。

| # | ID | 序列 | AnOxPePred | ToxinPred3 | HemoPI2 | AlgPred2 | BepiPred3 |
|---|-----|------|-----------|------------|---------|----------|-----------|
{bottom_info_lines}

## 排名上升 Top 10（R1 → R3）

| 肽 | 排名变化 | R3 综合分 |
|----|----------|-----------|
{rise_lines}

## 排名下降 Top 10（R1 → R3）

| 肽 | 排名变化 | R3 综合分 |
|----|----------|-----------|
{fall_lines}

## 输出

- `final/top80.csv` — Top {n_top:,} 条 → Stage 4 枚举
- `final/bottom10.csv` — 安全但抗氧化最差 {len(bottom_peptides)} 条 → Stage 4 枚举
- `final/all_scored.csv` — 全部 {len(scored_peptides):,} 条
- `final/danger_list.csv` — 高危 {len(danger_list)} 条
- `final/trajectory.csv` — 跨轮排名轨迹（{len(trajectory)} 条）
"""

    readme_path = STAGE_DIR / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    log(f"\n报告: {readme_path}")

    log(f"\n{'='*60}")
    log(f"Round 3 汇总")
    log(f"  输入: {total:,} 条 | Top: {n_top:,} | Bottom: {len(bottom_peptides)}")
    if valid_scores:
        log(f"  综合分: mean={sum(valid_scores)/len(valid_scores):.4f}, max={max(valid_scores):.4f}")
    log(f"  安全: {n_safe:,} / {n_caution:,} / {n_danger:,}")
    if temstapro_available:
        log(f"  TemStaPro: 已使用")
    log(f"  耗时: {total_elapsed:.0f}s")
    log(f"{'='*60}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
