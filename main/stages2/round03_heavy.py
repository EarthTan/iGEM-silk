"""
Round 3：重服务评分

在 Top 10,000 条候选肽上运行 1-2 个追加重服务：
  - BepiPred-3.0（B 细胞表位，权重 0.10，正向，~50 seq/s）
  - TemStaPro（热稳定性，权重 0.05，正向，可选）

合并 Round 1+2 的全部 5 个服务分数，用 6-7 服务权重重算最终综合分，
取 Top 80 进入下游枚举和 3D 预测。

用法：
    uv run python -m main.stages2.round03_heavy

输入：
    output/round02_scoring/final/top10k.csv

输出：
    output/round03_heavy/
    ├── README.md              ← 最终排名报告 + 跨轮轨迹
    ├── run.log
    ├── scores/                ← BepiPred 等原始返回（JSON）
    ├── final/
    │   ├── top80.csv          ← 最终 Top 80 肽
    │   ├── all_scored.csv     ← 全部 10K 评分明细
    │   ├── trajectory.csv     ← 跨轮排名变动（R1→R2→R3）
    │   └── danger_list.csv    ← 🔴 高危肽最终清单
    └── stats.json             ← 程序化统计摘要
"""

from __future__ import annotations

import asyncio
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "output"
STAGE = "round03_heavy"
STAGE_DIR = OUTPUT_DIR / STAGE

from main.client import ServiceClient

LOG_FILE: Path | None = None
MAX_BATCH_SIZE = 1000
CONCURRENT_CHUNKS = 10

# ── Round 3 新增服务 ──
NEW_SERVICES = [
    ("bepipred3",   0.10, False, "B 细胞表位（正向）"),
]

# TemStaPro 可选 —— 如果服务健康则追加
TEMSTAPRO_CFG = ("temstapro", 0.05, False, "热稳定性（正向，可选）")

# ── 全部服务权重 ──
BASE_WEIGHTS = {
    "anoxpepred":  0.50,
    "toxinpred3":  0.15,
    "algpred2":    0.10,
    "hemopi2":     0.10,
    "mhcflurry":   0.05,
    "bepipred3":   0.07,   # Round 3 追加，降低权重给 TemStaPro 预留空间
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
ROUND2_INPUT = OUTPUT_DIR / "round02_scoring" / "final" / "top10k.csv"


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


def make_dir(name: str) -> Path:
    d = STAGE_DIR / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def describe(name: str, values: list[float]) -> str:
    n = len(values)
    if n == 0:
        return f"{name}: 无有效数据"
    sorted_v = sorted(values)
    mean = sum(sorted_v) / n
    median = sorted_v[n // 2] if n % 2 == 1 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
    variance = sum((x - mean) ** 2 for x in sorted_v) / n
    std = variance ** 0.5
    p5 = sorted_v[int(n * 0.05)]
    p25 = sorted_v[int(n * 0.25)]
    p75 = sorted_v[int(n * 0.75)]
    p95 = sorted_v[int(n * 0.95)]
    lines = [
        f"{name} 分布 (n={n}):",
        f"  均值:   {mean:.4f}",
        f"  中位数: {median:.4f}",
        f"  标准差: {std:.4f}",
        f"  最小值: {sorted_v[0]:.4f}",
        f"  最大值: {sorted_v[-1]:.4f}",
        f"  P5: {p5:.4f}  |  P25: {p25:.4f}  |  P75: {p75:.4f}  |  P95: {p95:.4f}",
        "",
        "  分布直方图:",
    ]
    vmin = sorted_v[0]
    vmax = sorted_v[-1]
    if vmax - vmin < 0.001:
        lines.append(f"  所有值 ≈ {vmin:.4f}，无分布")
        return "\n".join(lines)
    raw_bins = 8
    bin_width = (vmax - vmin) / raw_bins
    bins = [vmin + bin_width * i for i in range(raw_bins + 1)]
    for i in range(len(bins) - 1):
        lo = bins[i]
        hi = bins[i + 1]
        count = sum(1 for v in values if lo <= v < hi)
        pct = count / n * 100
        filled = round(count / n * 14)
        bar = "█" * filled + "░" * (14 - filled)
        marker = "  ← 均值" if lo <= mean < hi else ""
        lines.append(f"  {lo:.4f}-{hi:.4f}: {bar}  ({count:,} 条, {pct:.1f}%){marker}")
    lines.append("")
    return "\n".join(lines)


def calc_safety_flag(peptide: dict) -> str:
    flags = []
    for svc_name, cfg in SAFETY_THRESHOLDS.items():
        score = peptide.get(svc_name)
        if score is None:
            continue
        if score >= cfg["danger"]:
            flags.append(f"{svc_name}:danger({score:.3f})")
        elif score >= cfg["caution"]:
            flags.append(f"{svc_name}:caution({score:.3f})")
    return ";".join(flags) if flags else "safe"


# ═══════════════════════════════════════════════════════════════════════
# 并发批处理
# ═══════════════════════════════════════════════════════════════════════

async def process_service(
    client: ServiceClient,
    service_name: str,
    chunks: list[list[dict]],
) -> dict[str, dict]:
    sem = asyncio.Semaphore(CONCURRENT_CHUNKS)
    all_results: dict[str, dict] = {}
    errors = 0
    total = sum(len(c) for c in chunks)

    async def process_chunk(chunk: list[dict]) -> None:
        nonlocal errors
        async with sem:
            result = await client.predict_batch(service_name, chunk)
            if result.get("success") and result.get("results"):
                for r in result["results"]:
                    pid = r.get("peptide_id", "unknown")
                    all_results[pid] = {
                        "score": r.get("score"),
                        "label": r.get("label", ""),
                    }
            else:
                errors += 1
                for item in chunk:
                    pid = item.get("peptide_id", "unknown")
                    all_results[pid] = {"score": None, "label": "SERVICE_ERROR"}

    tasks = [process_chunk(chunk) for chunk in chunks]
    batch_size = 50
    for i in range(0, len(tasks), batch_size):
        batch = tasks[i:i + batch_size]
        await asyncio.gather(*batch)
        progress = min((i + batch_size) * MAX_BATCH_SIZE, total)
        log(f"  {service_name}: {progress:,}/{total:,} ({progress/total*100:.0f}%) | errors={errors}")

    log(f"  ✅ {service_name}: {total:,} 完成, {errors} 批次错误")
    return all_results


# ═══════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════

async def run():
    global LOG_FILE
    start_time = time.time()

    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE = STAGE_DIR / "run.log"
    log("=" * 60)
    log("Round 3：重服务评分 — BepiPred-3.0 (+ TemStaPro 可选)")
    log("=" * 60)

    # ── 加载 Round 2 Top 10K ──
    if not ROUND2_INPUT.exists():
        log(f"输入不存在: {ROUND2_INPUT}")
        log("请先运行: uv run python -m main.stages2.round02_scoring")
        return

    peptides: list[dict] = []
    with open(ROUND2_INPUT, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k in ("anoxpepred", "toxinpred3", "algpred2", "hemopi2", "mhcflurry"):
                row[k] = float(row[k]) if row.get(k) else None
            row["weighted_score"] = float(row["weighted_score"]) if row.get("weighted_score") else None
            row["length"] = int(row["length"])
            peptides.append(row)

    total = len(peptides)
    log(f"\n输入: {total:,} 条 (Round 2 Top 10K)")

    # ── 分块 ──
    chunks: list[list[dict]] = []
    for i in range(0, total, MAX_BATCH_SIZE):
        chunk = peptides[i:i + MAX_BATCH_SIZE]
        chunks.append([{"sequence": p["sequence"], "peptide_id": p["peptide_id"]} for p in chunk])
    log(f"分块: {len(chunks)} 批 (≤{MAX_BATCH_SIZE}/批)")

    # ── 客户端 + 检查 TemStaPro ──
    client = ServiceClient(timeout=300.0)

    # 检查 TemStaPro 是否可用
    temstapro_available = False
    try:
        health = await client.check_health("temstapro")
        if health.get("status") == "healthy" and health.get("model_loaded"):
            temstapro_available = True
            log(f"\nTemStaPro 可用 ✅ 将参与评分")
        else:
            log(f"\nTemStaPro 不可用 (status={health.get('status')})，跳过")
    except Exception as e:
        log(f"\nTemStaPro 不可用 ({e})，跳过")

    # 确定服务列表和权重
    round3_services = list(NEW_SERVICES)
    all_services_list = list(BASE_WEIGHTS.keys())
    if temstapro_available:
        round3_services.append(TEMSTAPRO_CFG)
        all_weights = dict(WITH_TEMSTAPRO_WEIGHTS)
        all_services_list = list(WITH_TEMSTAPRO_WEIGHTS.keys())
    else:
        all_weights = dict(BASE_WEIGHTS)
        all_services_list = list(BASE_WEIGHTS.keys())

    # ══════════════════════════════════════════════════════════════════
    # 并发调用新增服务
    # ══════════════════════════════════════════════════════════════════
    svc_names = [s[0] for s in round3_services]
    log(f"\n新服务: {', '.join(svc_names)} ({len(chunks)} 批)")

    async def run_one(svc_name: str, weight: float, reverse: bool, desc: str):
        log(f"\n{svc_name} ({desc})")
        t0 = time.time()
        results = await process_service(client, svc_name, chunks)
        elapsed = time.time() - t0
        n_valid = sum(1 for v in results.values() if v["score"] is not None)
        rate = n_valid / elapsed if elapsed > 0 else 0
        log(f"  {svc_name}: {elapsed:.0f}s, {n_valid}/{len(results)} 有效 ({rate:.0f} seq/s)")
        return svc_name, results, weight, reverse

    tasks = [run_one(svc, w, r, d) for svc, w, r, d in round3_services]
    completed = await asyncio.gather(*tasks)
    new_results: dict[str, dict[str, dict]] = {svc: res for svc, res, _, _ in completed}

    await client.close()

    # ── 保存原始返回 ──
    scores_dir = make_dir("scores")
    for svc_name in new_results:
        write_json(scores_dir / f"{svc_name}_results.json", new_results[svc_name])

    # ══════════════════════════════════════════════════════════════════
    # 重算最终综合分
    # ══════════════════════════════════════════════════════════════════
    log(f"\n重算最终综合分 ({len(all_services_list)} 服务)...")

    reverse_services = {"toxinpred3", "algpred2", "hemopi2", "mhcflurry"}

    scored_peptides: list[dict] = []
    for pep in peptides:
        pid = pep["peptide_id"]
        row = {k: pep.get(k) for k in ("peptide_id", "sequence", "length", "source",
                                         "anoxpepred", "toxinpred3", "algpred2",
                                         "hemopi2", "mhcflurry", "weighted_score")}

        weighted_sum = 0.0
        total_weight = 0.0
        missing_svc = []

        for svc_name in all_services_list:
            weight = all_weights[svc_name]
            reverse = svc_name in reverse_services

            # 取分数
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
            row[f"{svc_name}_raw_norm"] = round(normalized, 4)
            if reverse:
                normalized = 1.0 - normalized
            weighted_sum += normalized * weight
            total_weight += weight

        if missing_svc:
            row["missing_services"] = ";".join(missing_svc)

        row["weighted_score"] = round(weighted_sum / total_weight, 4) if total_weight > 0 else None
        row["safety_flag"] = calc_safety_flag(row)
        scored_peptides.append(row)

    n_valid = sum(1 for p in scored_peptides if p["weighted_score"] is not None)
    log(f"  完成: {n_valid:,}/{len(scored_peptides):,} 有效评分")

    # ── 排序 + 输出 ──
    log(f"\n排序...")
    scored_peptides.sort(key=lambda x: (x["weighted_score"] or 0), reverse=True)

    final_dir = make_dir("final")
    fieldnames = ["peptide_id", "sequence", "length", "source",
                  "anoxpepred", "toxinpred3", "algpred2", "hemopi2", "mhcflurry",
                  "bepipred3", "temstapro", "weighted_score", "safety_flag"] if temstapro_available else \
                 ["peptide_id", "sequence", "length", "source",
                  "anoxpepred", "toxinpred3", "algpred2", "hemopi2", "mhcflurry",
                  "bepipred3", "weighted_score", "safety_flag"]

    # 全部
    all_path = final_dir / "all_scored.csv"
    with open(all_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(scored_peptides)

    # Top N
    n_top = min(TOP_N, len(scored_peptides))
    top_peptides = scored_peptides[:n_top]
    top_path = final_dir / "top80.csv"
    with open(top_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(top_peptides)
    log(f"Top {n_top:,}: {top_path}")

    # 高危
    danger_list = [p for p in scored_peptides if "danger" in p.get("safety_flag", "")]
    danger_path = final_dir / "danger_list.csv"
    with open(danger_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(danger_list)
    log(f"高危清单: {danger_path} ({len(danger_list)} 条)")

    # ══════════════════════════════════════════════════════════════════
    # 跨轮排名轨迹
    # ══════════════════════════════════════════════════════════════════
    log(f"\n计算跨轮排名轨迹...")
    # 读取 Round 1 和 Round 2 的排名
    r1_rank: dict[str, int] = {}
    r1_path = OUTPUT_DIR / "round01_lightweight" / "final" / "top100k.csv"
    if r1_path.exists():
        with open(r1_path, newline="", encoding="utf-8") as f:
            for i, row in enumerate(csv.DictReader(f)):
                r1_rank[row["peptide_id"]] = i + 1  # 1-based

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
            "rank_r1": r1_rank.get(pid, None),
            "rank_r2": r2_rank.get(pid, None),
            "rank_r3": None,  # will fill below
            "score_r1": None,  # will fill below
            "score_r2": p.get("anoxpepred"),  # 近似用已有数据
            "score_r3": round(r3, 4),
        })

    # 填 R3 排名
    for i, t in enumerate(trajectory):
        t["rank_r3"] = i + 1

    traj_path = final_dir / "trajectory.csv"
    traj_fields = ["peptide_id", "sequence", "rank_r1", "rank_r2", "rank_r3",
                   "score_r2", "score_r3"]
    with open(traj_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=traj_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(trajectory)
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

    top10_lines = [f"| {p['peptide_id']} | {p['sequence'][:25]:25s} | {p['length']} | {p['weighted_score']:.4f} | {p.get('safety_flag','safe')} |"
                   for p in scored_peptides[:10]]
    bottom_valid = [p for p in scored_peptides if p["weighted_score"] is not None]
    bottom10_lines = [f"| {p['peptide_id']} | {p['sequence'][:25]:25s} | {p['length']} | {p['weighted_score']:.4f} | {p.get('safety_flag','safe')} |"
                      for p in reversed(bottom_valid[-10:])]

    # 排名变化最大的 Top/Bottom 10
    traj_with_change = [t for t in trajectory if t["rank_r1"] is not None and t["rank_r2"] is not None]
    traj_with_change.sort(key=lambda t: (t["rank_r3"] or 999) - t["rank_r1"])
    top_rise = traj_with_change[:10]   # 上升最多
    top_fall = traj_with_change[-10:]  # 下降最多
    top_rise.reverse()  # 上升最多的排前面

    rise_lines = [f"| {t['peptide_id']} | R1:{t['rank_r1']} → R2:{t['rank_r2']} → R3:{t['rank_r3']} | {t['score_r3']:.4f} |"
                  for t in top_rise]
    fall_lines = [f"| {t['peptide_id']} | R1:{t['rank_r1']} → R2:{t['rank_r2']} → R3:{t['rank_r3']} | {t['score_r3']:.4f} |"
                  for t in top_fall]

    stats = {
        "stage": STAGE,
        "timestamp": datetime.now().isoformat(),
        "elapsed_sec": round(total_elapsed, 1),
        "input": total,
        "services": list(all_weights.keys()),
        "weights": all_weights,
        "temstapro_used": temstapro_available,
        "scoring": {"n_valid": len(valid_scores),
                     "mean": round(sum(valid_scores)/len(valid_scores), 4) if valid_scores else None,
                     "top_n": n_top},
        "safety": {"safe": n_safe, "caution": n_caution, "danger": n_danger, "missing": n_missing},
    }
    write_json(STAGE_DIR / "stats.json", stats)

    # ── README ──
    readme = f"""# Round 3：重服务评分 — 报告

**时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**耗时**: {total_elapsed:.0f} 秒
**输入**: {total:,} 条肽（Round 2 Top 10K）

## 评分服务（{len(all_services_list)} 服务）

| 服务 | 权重 | 方向 | 有效 |
|------|------|------|------|
{"".join(f"| {svc} | {all_weights[svc]:.2f} | {'正向' if svc not in reverse_services else '反向'} | {sum(1 for p in scored_peptides if p.get(svc) is not None):,} |\\n" for svc in all_services_list).strip()}

**TemStaPro**: {"已使用 ✅" if temstapro_available else "未就绪，跳过"}

## 综合分分布

```
{full_distro}
```

## 安全标记

| 级别 | 数量 | 占比 |
|------|------|------|
| 正常 | {n_safe:,} | {n_safe/max(len(scored_peptides),1)*100:.1f}% |
| 注意 | {n_caution:,} | {n_caution/max(len(scored_peptides),1)*100:.1f}% |
| 高危 | {n_danger:,} | {n_danger/max(len(scored_peptides),1)*100:.1f}% |
| 数据缺失 | {n_missing:,} | {n_missing/max(len(scored_peptides),1)*100:.1f}% |

## Top 10

| ID | 序列 | 长度 | 综合分 | 安全 |
|----|------|------|--------|------|
{chr(10).join(top10_lines)}

## Bottom 10

| ID | 序列 | 长度 | 综合分 | 安全 |
|----|------|------|--------|------|
{chr(10).join(bottom10_lines)}

## 排名上升 Top 10（R1 → R3）

| 肽 | 排名变化 | R3 综合分 |
|----|----------|-----------|
{chr(10).join(rise_lines)}

## 排名下降 Top 10（R1 → R3）

| 肽 | 排名变化 | R3 综合分 |
|----|----------|-----------|
{chr(10).join(fall_lines)}

## 输出

- `final/top80.csv` — Top {n_top:,} 条 → Stage 4 枚举
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
    log(f"  输入: {total:,} 条 | Top: {n_top:,}")
    if valid_scores:
        log(f"  综合分: mean={sum(valid_scores)/len(valid_scores):.4f}, max={max(valid_scores):.4f}")
    log(f"  安全: {n_safe:,} / {n_caution:,} / {n_danger:,}")
    log(f"  耗时: {total_elapsed:.0f}s")
    if temstapro_available:
        log(f"  TemStaPro: 已使用")
    log(f"{'='*60}")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
