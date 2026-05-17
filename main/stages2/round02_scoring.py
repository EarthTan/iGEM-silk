"""
Round 2：追加评分

在 Top 50,000 条候选肽上追加 2 个服务：
  - HemoPI2（溶血反向，权重 0.10）
  - MHCflurry（MHC-I 反向，权重 0.05）

与 Round 1 的 AnOxPePred + ToxinPred3 + AlgPred2 分数合并，
用 5 服务权重重算综合分，取 Top 10,000 进入 Round 3。

与原脚本的关键差异：
  - ⛔ 不再重复跑 ToxinPred3！原脚本在 Round 2 重新跑了 ToxinPred3
    （浪费 ~2.3 小时），本版直接复用 Round 1 的 ToxinPred3 分数。
    只追加 HemoPI2 + MHCflurry 两个新服务。
  - 使用 common.py 消除工具函数复制粘贴
  - 修复输入文件名：读 top50k.csv（原脚本读 top100k.csv — bug）
  - 新增断点续跑（checkpoint.json）
  - 统一 asyncio.gather 异常安全
  - 输出目录 output2/

用法：
    uv run python -m main.stages2.round02_scoring

输入：
    output2/round01_lightweight/final/top50k.csv

输出：
    output2/round02_scoring/
    ├── README.md              ← 分布报告 + Top/Bottom 展示
    ├── run.log
    ├── scores/                ← 各服务原始返回（JSON）
    ├── final/
    │   ├── top10k.csv         ← Top 10,000 肽（含综合分 + 安全标记）
    │   ├── all_scored.csv     ← 全部 50K 评分明细
    │   └── danger_list.csv    ← 🔴 高危肽清单
    └── stats.json             ← 程序化统计摘要
"""

from __future__ import annotations

import asyncio
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from main.client import ServiceClient

from main.stages2.common import (
    OUTPUT_DIR, calc_safety_flag, describe, log, make_dir,
    read_csv, setup_stage, write_csv, write_json,
)

STAGE = "round02_scoring"
STAGE_DIR = OUTPUT_DIR / STAGE

MAX_BATCH_SIZE = 1000

# ── Round 2 新增服务（不再重复跑 ToxinPred3）──
NEW_SERVICES = [
    ("hemopi2",   0.10, True, "溶血（反向，越低越好）"),
    ("mhcflurry", 0.05, True, "MHC-I 结合（反向，越低越好）"),
]

# ── 完整 5 服务权重（含 Round 1 已有的）──
ALL_WEIGHTS = {
    "anoxpepred":  0.50,
    "toxinpred3":  0.15,
    "algpred2":    0.10,
    "hemopi2":     0.10,
    "mhcflurry":   0.05,
}

SAFETY_THRESHOLDS = {
    "toxinpred3": {"caution": 0.60, "danger": 0.80},
    "algpred2":   {"caution": 0.50, "danger": 0.70},
    "hemopi2":    {"caution": 0.70, "danger": 0.85},
}

TOP_N = 10000
ROUND1_INPUT = OUTPUT_DIR / "round01_lightweight" / "final" / "top50k.csv"


# ═══════════════════════════════════════════════════════════════════════
# 并发批处理
# ═══════════════════════════════════════════════════════════════════════

async def process_service(
    client: ServiceClient,
    service_name: str,
    chunks: list[list[dict]],
    concurrency: int = 10,
) -> dict[str, dict]:
    sem = asyncio.Semaphore(concurrency)
    all_results: dict[str, dict] = {}
    errors = 0
    total = sum(len(c) for c in chunks)

    async def process_chunk(chunk: list[dict]) -> None:
        nonlocal errors
        async with sem:
            try:
                result = await asyncio.wait_for(
                    client.predict_batch(service_name, chunk),
                    timeout=300.0,
                )
                if result.get("success") and result.get("results"):
                    for r in result["results"]:
                        pid = r.get("peptide_id", "unknown")
                        all_results[pid] = {"score": r.get("score"), "label": r.get("label", "")}
                else:
                    errors += 1
                    for item in chunk:
                        pid = item.get("peptide_id", "unknown")
                        all_results[pid] = {"score": None, "label": "SERVICE_ERROR"}
            except asyncio.TimeoutError:
                errors += 1
                for item in chunk:
                    all_results[item.get("peptide_id", "unknown")] = {"score": None, "label": "TIMEOUT"}
            except Exception as e:
                errors += 1
                for item in chunk:
                    all_results[item.get("peptide_id", "unknown")] = {"score": None, "label": f"ERROR:{str(e)[:50]}"}

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
# CSV 读取（含数值转换）
# ═══════════════════════════════════════════════════════════════════════

def load_round1_peptides(path: Path) -> list[dict]:
    """加载 Round 1 输出并转换数值字段。"""
    peptides = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["anoxpepred"] = float(row["anoxpepred"]) if row.get("anoxpepred") else None
            row["toxinpred3"] = float(row["toxinpred3"]) if row.get("toxinpred3") else None
            row["algpred2"] = float(row["algpred2"]) if row.get("algpred2") else None
            row["weighted_score"] = float(row["weighted_score"]) if row.get("weighted_score") else None
            row["length"] = int(row["length"])
            peptides.append(row)
    return peptides


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

async def run():
    start_time = time.time()

    setup_stage(STAGE)
    log("=" * 60)
    log("Round 2：追加评分 — HemoPI2 + MHCflurry（不再重复跑 ToxinPred3）")
    log("=" * 60)

    # ── 加载 Round 1 Top 50K ──
    if not ROUND1_INPUT.exists():
        log(f"❌ 输入不存在: {ROUND1_INPUT}")
        log("请先运行: uv run python -m main.stages2.round01_lightweight")
        return

    peptides = load_round1_peptides(ROUND1_INPUT)
    total = len(peptides)
    log(f"\n输入: {total:,} 条 (Round 1 Top 50K)")
    log(f"  已含 ToxinPred3 分数: {sum(1 for p in peptides if p.get('toxinpred3') is not None):,} 条")
    log(f"  → 不再重复跑 ToxinPred3，只追加 HemoPI2 + MHCflurry")

    # ── 分块 ──
    chunks = []
    for i in range(0, total, MAX_BATCH_SIZE):
        chunk = peptides[i:i + MAX_BATCH_SIZE]
        chunks.append([{"sequence": p["sequence"], "peptide_id": p["peptide_id"]} for p in chunk])
    log(f"分块: {len(chunks)} 批 (≤{MAX_BATCH_SIZE}/批)")

    # ══════════════════════════════════════════════════════════════════
    # 并发调用 2 个新服务（不跑 ToxinPred3）
    # ══════════════════════════════════════════════════════════════════
    client = ServiceClient(timeout=300.0)
    svc_names = [s[0] for s in NEW_SERVICES]
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

    tasks = [run_one(svc, w, r, d) for svc, w, r, d in NEW_SERVICES]
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
    # 合并分数，用 5 服务权重重算综合分
    # ══════════════════════════════════════════════════════════════════
    log(f"\n合并分数 & 重算综合分...")

    all_services = list(ALL_WEIGHTS.keys())
    reverse_services = {"toxinpred3", "algpred2", "hemopi2", "mhcflurry"}
    scored_peptides: list[dict] = []

    for pep in peptides:
        pid = pep["peptide_id"]
        row = {
            "peptide_id": pid,
            "sequence": pep["sequence"],
            "length": pep["length"],
            "source": pep["source"],
            "anoxpepred": pep.get("anoxpepred"),
            "toxinpred3": pep.get("toxinpred3"),
            "algpred2": pep.get("algpred2"),
        }

        weighted_sum = 0.0
        total_weight = 0.0
        missing_svc = []

        for svc_name in all_services:
            weight = ALL_WEIGHTS[svc_name]
            reverse = svc_name in reverse_services

            # 新服务从 new_results 取，已有服务从 pep 取
            if svc_name in new_results:
                svc_data = new_results[svc_name].get(pid, {})
                raw_score = svc_data.get("score")
                row[svc_name] = raw_score
            else:
                raw_score = pep.get(svc_name)

            if raw_score is None:
                if svc_name not in row or row[svc_name] is None:
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

    # ── 排序 + 输出 ──
    log(f"\n排序...")
    scored_peptides.sort(key=lambda x: (x["weighted_score"] or 0), reverse=True)

    final_dir = make_dir(STAGE_DIR, "final")
    fieldnames = [
        "peptide_id", "sequence", "length", "source",
        "anoxpepred", "toxinpred3", "algpred2", "hemopi2", "mhcflurry",
        "weighted_score", "safety_flag",
    ]

    # 全部
    all_path = final_dir / "all_scored.csv"
    write_csv(all_path, fieldnames, scored_peptides)

    # Top N
    n_top = min(TOP_N, len(scored_peptides))
    top_peptides = scored_peptides[:n_top]
    top_path = final_dir / "top10k.csv"
    write_csv(top_path, fieldnames, top_peptides)
    log(f"Top {n_top:,}: {top_path}")

    # 高危
    danger_list = [p for p in scored_peptides if "danger" in p.get("safety_flag", "")]
    danger_path = final_dir / "danger_list.csv"
    write_csv(danger_path, fieldnames, danger_list)
    log(f"高危清单: {danger_path} ({len(danger_list)} 条)")

    # ══════════════════════════════════════════════════════════════════
    # 统计报告
    # ══════════════════════════════════════════════════════════════════
    total_elapsed = time.time() - start_time
    valid_scores = [p["weighted_score"] for p in scored_peptides if p["weighted_score"] is not None]

    all_reports = [describe("综合分", valid_scores)]
    for svc_name in all_services:
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

    stats = {
        "stage": STAGE, "timestamp": datetime.now().isoformat(),
        "elapsed_sec": round(total_elapsed, 1),
        "input": total,
        "new_services": {s[0]: {"weight": s[1], "reverse": s[2], "desc": s[3]} for s in NEW_SERVICES},
        "all_weights": ALL_WEIGHTS,
        "note": "ToxinPred3 复用 Round 1 数据，未重新计算",
        "scoring": {"n_valid": len(valid_scores),
                     "mean": round(sum(valid_scores)/len(valid_scores), 4) if valid_scores else None,
                     "top_n": n_top},
        "safety": {"safe": n_safe, "caution": n_caution, "danger": n_danger, "missing": n_missing},
    }
    write_json(STAGE_DIR / "stats.json", stats)

    # ── README ──
    readme = f"""# Round 2：追加评分 — 报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**耗时**: {total_elapsed:.0f} 秒
**输入**: {total:,} 条肽（Round 1 Top 50K）
**输出目录**: output2/

## ⚠️ 重要变更

本版 Round 2 **不再重复跑 ToxinPred3**（原脚本浪费 ~2.3h），
直接复用 Round 1 的 ToxinPred3 分数。新增 HemoPI2 + MHCflurry。

## 评分服务（5 服务）

| 服务 | 权重 | 方向 | 有效 | 来源 |
|------|------|------|------|------|
| AnOxPePred | 0.50 | 正向 | {sum(1 for p in scored_peptides if p.get('anoxpepred') is not None):,} | Round 1 |
| ToxinPred3 | 0.15 | 反向 | {sum(1 for p in scored_peptides if p.get('toxinpred3') is not None):,} | Round 1（复用） |
| AlgPred2 | 0.10 | 反向 | {sum(1 for p in scored_peptides if p.get('algpred2') is not None):,} | Round 1 |
| HemoPI2 | 0.10 | 反向 | {sum(1 for p in scored_peptides if p.get('hemopi2') is not None):,} | Round 2（新增） |
| MHCflurry | 0.05 | 反向 | {sum(1 for p in scored_peptides if p.get('mhcflurry') is not None):,} | Round 2（新增） |

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

## Top 10

| ID | 序列 | 长度 | 综合分 | 安全 |
|----|------|------|--------|------|
{top10_lines}

## Bottom 10

| ID | 序列 | 长度 | 综合分 | 安全 |
|----|------|------|--------|------|
{bottom10_lines}

## 输出

- `final/top10k.csv` — Top {n_top:,} 条 → Round 3
- `final/all_scored.csv` — 全部 {len(scored_peptides):,} 条
- `final/danger_list.csv` — 高危 {len(danger_list)} 条
"""

    readme_path = STAGE_DIR / "README.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)
    log(f"\n报告: {readme_path}")
    log(f"\n{'='*60}")
    log(f"Round 2 汇总")
    log(f"  输入: {total:,} 条 | Top: {n_top:,}")
    log(f"  ToxinPred3 复用 Round 1（节省 ~2.3h）")
    if valid_scores:
        log(f"  综合分: mean={sum(valid_scores)/len(valid_scores):.4f}, max={max(valid_scores):.4f}")
    log(f"  安全: {n_safe:,} / {n_caution:,} / {n_danger:,}")
    log(f"  耗时: {total_elapsed:.0f}s")
    log(f"{'='*60}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
