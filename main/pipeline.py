"""
============================================================================
 流水线编排 — 7 步完整评估流程
============================================================================

这是整个项目的"主程序"，串联了从数据加载到最终排名的全部步骤。

每次运行 ``python -m main`` 或 ``python main.py``（如果存在），
都会执行本文件的 ``run()`` 函数。

流水线 7 步概览
---------------
Step 1 — 加载数据       : 读取 scaffold / linker / 功能肽
Step 2 — 预筛选功能肽     : 理化性质过滤（长度、亲水性、电荷）
Step 3 — 微服务评分       : 并发调用 10 个微服务对功能肽评分（枚举前评分）
Step 4 — 肽评分筛选       : 硬过滤（毒性/过敏原/溶血）+ 加权评分 + 取 Top N
Step 5 — 超级枚举 construct: Top 肽 × 位置 × linker 全排列
Step 6 — 预过滤 construct  : 剔除插入在禁入区的 construct
Step 7 — 综合评分 & 排名   : 加权求和排序，输出 Top 20

每一步的输出文件
---------------
每一步都产生独立的输出文件，保存在 ``output/`` 目录下：

  步骤     JSON（摘要/少量数据）            CSV（大规模 construct 列表）
  ──────  ─────────────────────────────  ──────────────────────────────
  Step 1  step01_loaded_data.json        —
  Step 2  step02_prefilter_peptides.json —
  Step 3  step03_peptide_scores.json     —
          step03_peptide_scores_detail.json
  Step 4  step04_peptide_selection.json  —
          step04_failed_peptides.json
  Step 5  step05_enumeration_summary.json step05_enumerated_constructs.csv
  Step 6  step06_prefilter_summary.json  step06_passed_constructs.csv
                                         step06_failed_constructs.csv
  Step 7  step07_final_ranking.json      step07_all_ranked.csv

容错策略
--------
- 微服务不可用时：Step 5–7 自动跳过，Step 1–4 的结果已保存
  这意味着即使没有任何微服务运行，也能得到完整的 construct 枚举
- 部分微服务不可用：只调用健康的服务，缺失的服务在评分中空缺
- 某一步产出为空（无通过项）：输出警告并终止，不抛异常

关于"微服务评分在肽级别而非 construct 级别"
----------------------------------------------
这是一个重要的设计决策。原因：
1. 微服务模型（AnOxPePred、ToxinPred3 等）训练数据是短肽（5–50 aa）
2. 融合蛋白 construct 全长 350–400 aa，远超模型训练分布
3. 因此先对短肽评分，construct 通过 peptide_id 继承其评分
4. construct 之间的真正差异在于"插入位置的结构兼容性"
   （已在 Step 4 禁入区过滤中体现）
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from main.config import (
    SERVICES,
    HARD_FILTERS,
    SCORE_WEIGHTS,
    SCORE_INVERT,
    OUTPUT_DIR,
    TOP_N,
    TOP_PEPTIDES_BEFORE_ENUMERATION,
)
from main.data_loader import (
    load_scaffold,
    load_linkers,
    load_function_peptides,
)
from main.enumeration import (
    filter_peptides,
    get_passed_peptides,
    find_forbidden_zones,
    generate_constructs,
    summarize_enumeration,
    prefilter_constructs,
    write_constructs_csv,
    save_step,
)
from main.client import ServiceClient


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                        Step 6 — 硬过滤                                        ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
#
# 硬过滤 = 一票否决。只要 construct 的肽在任一安全过滤服务上超标，直接淘汰。
#
# 三个过滤维度：
#   1. ToxinPred3  ≥ 0.38 → 毒性风险
#   2. AlgPred2    ≥ 0.3  → 过敏原风险
#   3. HemoPI2     ≥ 0.55 → 溶血性风险
#
# 这是安全底线——不存在"毒性高但抗氧化强所以通过"的妥协。


def apply_hard_filters(
    scored_constructs: list[dict],
) -> tuple[dict, list[dict], list[dict]]:
    """
    对带评分的 construct 执行硬过滤。

    遍历每条 construct 的 service_scores，
    检查硬过滤服务的分数是否超过阈值。
    一旦命中任一过滤规则，construct 被淘汰。

    返回 (summary_dict, passed_list, failed_list)。
    failed_list 中每条 construct 附有 hard_filter_reasons，说明被哪些服务淘汰。
    """
    passed: list[dict] = []
    failed: list[dict] = []

    for c in scored_constructs:
        scores = c.get("service_scores", {})
        failed_by: list[dict] = []

        for svc_name, svc_config in HARD_FILTERS.items():  # 遍历每一个服务的得分
            svc_result = scores.get(svc_name)
            if svc_result is None:
                continue  # 该服务不可用，跳过此过滤项
            score = svc_result.get("score")
            if score is None:
                continue

            threshold = svc_config["threshold"]
            rule = svc_config["rule"]

            # 根据规则判断是否触发过滤
            triggered = False
            if rule == ">=" and score >= threshold:
                triggered = True
            elif rule == "<=" and score <= threshold:
                triggered = True

            if triggered:
                failed_by.append(
                    {
                        "service": svc_name,
                        "score": score,
                        "threshold": threshold,
                        "reason": svc_config["reason"],
                    }
                )

        if failed_by:
            c["hard_filter_status"] = "failed"
            c["hard_filter_reasons"] = failed_by
            failed.append(c)
        else:
            c["hard_filter_status"] = "passed"
            c["hard_filter_reasons"] = []
            passed.append(c)

    summary = {
        "step": "06_hard_filter",
        "total": len(scored_constructs),
        "passed": len(passed),
        "failed": len(failed),
        "filters_applied": {
            name: {"threshold": cfg["threshold"], "rule": cfg["rule"]}
            for name, cfg in HARD_FILTERS.items()
        },
    }
    return summary, passed, failed


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                      Step 4 — 肽评分筛选（肽级别）                              ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
#
# 在微服务评分之后、枚举 construct 之前，对肽执行：
#   1. 硬过滤（毒性/过敏原/溶血）— 一票否决，不安全肽不进枚举
#   2. 加权评分 — Σ(weight_i × adjusted_score_i) / Σ(weight_i)
#   3. 取 Top N — 只保留评分最高的前 N 条肽进入后续枚举
#
# 这样有毒/低分肽根本不会进入枚举，大幅缩减 construct 空间。


def score_and_filter_peptides(
    peptide_scores: dict,
    peptides: list[dict],
    top_n: int | None = None,
) -> tuple[dict, list[dict], list[dict]]:
    """
    对肽执行硬过滤 + 加权评分 + Top-N 筛选。

    参数
    ----
    peptide_scores : {peptide_id: {service_name: {score, label, details}}}
        微服务对每条肽的评分结果。
    peptides : 通过理化预筛选的肽列表
    top_n : 保留前 N 名（None = 不限制）

    返回
    ----
    (summary, passed_peptides, failed_peptides)

    passed_peptides 中每条肽附有 final_score 和 score_breakdown。
    failed_peptides 中每条肽附有 hard_filter_reasons。
    """
    weights = SCORE_WEIGHTS
    scored_peptides: list[dict] = []
    failed: list[dict] = []

    # 检查是否有可用的评分数据
    has_scores = bool(peptide_scores)

    for pep in peptides:
        pid = pep.get("peptide_id", pep.get("sequence", "unknown"))
        seq = pep["sequence"]
        scores = peptide_scores.get(pid, {})

        # ── 硬过滤（仅当有评分数据时执行） ──
        failed_by: list[dict] = []
        for svc_name, svc_config in HARD_FILTERS.items():
            svc_result = scores.get(svc_name)
            if svc_result is None:
                continue
            score = svc_result.get("score")
            if score is None:
                continue

            threshold = svc_config["threshold"]
            rule = svc_config["rule"]
            triggered = False
            if rule == ">=" and score >= threshold:
                triggered = True
            elif rule == "<=" and score <= threshold:
                triggered = True

            if triggered:
                failed_by.append(
                    {
                        "service": svc_name,
                        "score": score,
                        "threshold": threshold,
                        "reason": svc_config["reason"],
                    }
                )

        if failed_by:
            failed.append(
                {
                    **pep,
                    "hard_filter_status": "failed",
                    "hard_filter_reasons": failed_by,
                }
            )
            continue

        # ── 加权评分 ──
        if has_scores:
            total_weight = 0.0
            weighted_sum = 0.0
            score_breakdown = {}

            for svc_name, weight in weights.items():
                svc_result = scores.get(svc_name)
                if svc_result is None:
                    continue
                raw_score = svc_result.get("score")
                if raw_score is None:
                    continue

                adjusted_score = (
                    (1.0 - raw_score) if svc_name in SCORE_INVERT else raw_score
                )

                weighted_sum += weight * adjusted_score
                total_weight += weight
                score_breakdown[svc_name] = {
                    "raw_score": round(raw_score, 4),
                    "adjusted_score": round(adjusted_score, 4),
                    "weight": weight,
                    "contribution": round(weight * adjusted_score, 4),
                }

            final_score = (
                round(weighted_sum / total_weight, 4) if total_weight > 0 else 0.0
            )
        else:
            # 无评分数据（微服务全部不可用）：给默认分 0，全部通过
            final_score = 0.0
            score_breakdown = {}

        scored_peptides.append(
            {
                **pep,
                "final_score": final_score,
                "score_breakdown": score_breakdown,
                "service_scores": scores,
                "hard_filter_status": "passed",
            }
        )

    # ── 排序 + Top-N ──
    # 无评分数据时 top_n 不生效（全部分数相同，截断无意义）
    effective_top_n = top_n if has_scores else None
    scored_peptides.sort(key=lambda x: x["final_score"], reverse=True)
    passed = (
        scored_peptides[:effective_top_n]
        if effective_top_n is not None
        else scored_peptides
    )

    summary = {
        "step": "04_peptide_selection",
        "total_input": len(peptides),
        "failed_hard_filter": len(failed),
        "scored": len(scored_peptides),
        "selected_for_enumeration": len(passed),
        "final_score_range": {
            "max": passed[0]["final_score"] if passed else 0,
            "min": passed[-1]["final_score"] if passed else 0,
        },
        "hard_filters_applied": {
            name: {"threshold": cfg["threshold"], "rule": cfg["rule"]}
            for name, cfg in HARD_FILTERS.items()
        },
        "score_weights_used": weights if has_scores else {},
        "top_n_limit": top_n,
    }
    return summary, passed, failed


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                      Step 7 — 综合评分 & 排名                                  ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
#
# 评分公式
# --------
# 对每条 construct：
#   final_score = Σ(weight_i × adjusted_score_i) / Σ(weight_i)
#
# 其中：
#   adjusted_score = raw_score          （正常指标：越高越好）
#   adjusted_score = 1.0 - raw_score    （反向指标：越高越差，如免疫原性）
#
# 这种加权平均方式：
#   - 各维度分数归一化到 0–1（微服务输出的 score 本身就是 0–1）
#   - 权重之和不必为 1.0，自动归一化
#   - 缺失的服务（不可用）不参与计算，权重自然重新分配
#
# score_breakdown 记录每个服务的原始分数、调整后分数、权重和贡献值，
# 用于追溯最终分数的来源。


def score_and_rank(
    passed_constructs: list[dict],
) -> tuple[dict, list[dict], list[dict]]:
    """
    对通过硬过滤的 construct 进行加权评分并排序。

    返回 (summary_dict, top_list, all_ranked_list)。

    all_ranked_list 包含所有 construct 的完整排名（写入 CSV），
    top_list 只取前 TOP_N 条（在终端展示 + 写入 JSON）。
    """
    weights = SCORE_WEIGHTS

    ranked = []
    for c in passed_constructs:
        scores = c.get("service_scores", {})
        total_weight = 0.0
        weighted_sum = 0.0
        score_breakdown = {}

        for svc_name, weight in weights.items():
            svc_result = scores.get(svc_name)
            if svc_result is None:
                continue  # 该服务对此肽无结果（服务不可用或未返回）
            raw_score = svc_result.get("score")
            if raw_score is None:
                continue

            # 反向指标（如 MHCflurry 免疫原性）取反
            adjusted_score = (
                (1.0 - raw_score) if svc_name in SCORE_INVERT else raw_score
            )

            weighted_sum += weight * adjusted_score
            total_weight += weight
            score_breakdown[svc_name] = {
                "raw_score": round(raw_score, 4),
                "adjusted_score": round(adjusted_score, 4),
                "weight": weight,
                "contribution": round(weight * adjusted_score, 4),
            }

        # 归一化：除以总权重，避免因部分服务缺失导致分数偏向
        final_score = round(weighted_sum / total_weight, 4) if total_weight > 0 else 0.0

        # 提取 construct 的核心字段 + 评分信息
        ranked.append(
            {
                **{
                    k: c[k]
                    for k in [
                        "construct_id",
                        "peptide_id",
                        "peptide_sequence",
                        "insertion_position",
                        "linker_id",
                        "linker_sequence",
                        "fusion_length",
                        "fusion_sequence",
                    ]
                },
                "final_score": final_score,
                "score_breakdown": score_breakdown,
            }
        )

    # 按最终分数降序排列（分数最高的在前）
    ranked.sort(key=lambda x: x["final_score"], reverse=True)
    top_n = ranked[:TOP_N]

    summary = {
        "step": "07_final_ranking",
        "total_ranked": len(ranked),
        "top_n": TOP_N,
        "score_weights": weights,
        "score_invert": list(SCORE_INVERT),
        "top_results": top_n,
    }
    return summary, top_n, ranked


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                          主流水线入口                                           ║
# ╚════════════════════════════════════════════════════════════════════════════════╝


async def run() -> None:
    """
    执行完整的 7 步流水线。

    这是外部调用的唯一入口（通过 ``main/__init__.py`` 的 ``main()``）。
    async 是因为 Step 5 需要异步 HTTP 调用微服务。
    """
    started_at = time.time()
    print("=" * 60)
    print("  iGEM-silk 融合蛋白设计流水线")
    print("=" * 60)

    # ═══════════════════════════════════════════════════════════════
    # Step 1: 加载数据
    # ═══════════════════════════════════════════════════════════════
    #
    # 从 data/ 目录加载三个输入文件：
    #   silk.fasta   → scaffold（丝素蛋白骨架，约 346 aa）
    #   linker.fasta → 10 种 linker（柔性/刚性/丝素衍生）
    #   function.csv → ~2.5 万条肽序列及功能标签
    #
    # 当前阶段只关注抗氧化肽（is_antioxidant == 1），
    # 后续可扩展为其他功能维度。

    print("\n[Step 1/7] 加载数据 …")
    scaffold = load_scaffold()
    linkers = load_linkers()
    peptides_df = load_function_peptides()

    # 筛选抗氧化肽（当前项目的核心功能方向）
    choosen_peptides = peptides_df[peptides_df["is_antioxidant"] == 1]
    # TODO: 功能肽选择扩展

    print(f"  Scaffold: {scaffold['id']} ({len(scaffold['sequence'])} aa)")
    print(f"  Linkers: {len(linkers)} 条")
    print(f"  功能肽总数: {len(peptides_df)}")
    print(f"  其中抗氧化肽: {len(choosen_peptides)}")

    # 输出 Step 1 摘要
    step01 = {
        "step": "01_loaded_data",
        "scaffold": {
            "id": scaffold["id"],
            "length": len(scaffold["sequence"]),
            "sequence": scaffold["sequence"],
        },
        "linkers": [{"id": l["id"], "sequence": l["sequence"]} for l in linkers],
        "total_peptides_in_csv": len(peptides_df),
        "choosen_peptides": len(choosen_peptides),
        "columns": list(peptides_df.columns),
    }
    save_step(step01, "step01_loaded_data.json")

    # ═══════════════════════════════════════════════════════════════
    # Step 2: 预筛选功能肽
    # ═══════════════════════════════════════════════════════════════
    #
    # 理化性质过滤：长度 5–15、GRAVY < 0（亲水）、净电荷 -3 ~ +3。
    # 每条肽都有完整的评估记录（通过/淘汰 + 原因），输出到 JSON 供人工复查。
    #
    # 过滤掉的肽不会进入后续枚举——这是第一道粗筛，
    # 淘汰的都是理化性质明显不合适的肽（太短/太长/太疏水/电荷极端）。

    print("\n[Step 2/7] 预筛选功能肽（理化性质过滤）…")
    step02 = filter_peptides(choosen_peptides)
    save_step(step02, "step02_prefilter_peptides.json")
    print(f"  通过: {step02['passed']} / 淘汰: {step02['failed']}")

    # 提取通过的肽
    passed_peptides = get_passed_peptides(step02)

    # 去重：相同序列只保留一条
    # function.csv 中可能存在同一肽序列来自不同文献/数据库的重复条目
    # 重复序列在功能上没有差异，去重可减少微服务调用次数和 construct 冗余
    seen_seq: set[str] = set()
    deduped_peptides: list[dict] = []
    for pep in passed_peptides:
        if pep["sequence"] not in seen_seq:
            seen_seq.add(pep["sequence"])
            deduped_peptides.append(pep)
    if len(deduped_peptides) < len(passed_peptides):
        print(f"  去重: {len(passed_peptides)} → {len(deduped_peptides)} 条唯一序列")
    passed_peptides = deduped_peptides

    if not passed_peptides:
        print("  ⚠️  没有肽通过预筛选，流水线终止。")
        return

    # ═══════════════════════════════════════════════════════════════
    # Step 3: 微服务评分
    # ═══════════════════════════════════════════════════════════════
    #
    # 在枚举 construct 之前先对肽评分。
    # 流程：
    #   0. 检测缓存 — 如果上次运行已保存评分，询问用户是否复用
    #   1. 健康检查 — 确定哪些服务在线
    #   2. 对在线服务，各发送全部肽的批量请求（并发执行）
    #   3. 聚合每个服务的响应，按 peptide_id 建立评分字典
    #   4. 写入缓存 — 保存本次评分结果供下次复用

    CACHE_PATH = Path(OUTPUT_DIR) / "cache_peptide_scores.json"
    eval_result = None  # 将在下面被赋值（来自缓存或微服务调用）

    # ── 0. 检测缓存 ──────────────────────────────────────────
    current_sequences = sorted(set(p["sequence"] for p in passed_peptides))

    if CACHE_PATH.exists():
        try:
            with open(CACHE_PATH, encoding="utf-8") as f:
                cache = json.load(f)
            cache_time = cache.get("cached_at", "未知时间")
            cache_sequences = sorted(cache.get("peptide_sequences", []))

            if cache_sequences == current_sequences:
                print(f"\n[Step 3/7] 发现缓存评分结果")
                print(f"  缓存时间: {cache_time}")
                print(f"  缓存肽数: {len(cache_sequences)} 条")
                print(f"  缓存服务: {', '.join(cache.get('services_used', []))}")
                answer = input("  是否使用缓存? [Y/n]: ").strip().lower()
                if answer in ("", "y", "yes"):
                    eval_result = {
                        "peptide_scores": cache["peptide_scores"],
                        "service_status": {
                            "available": cache.get("services_used", []),
                            "unavailable": [],
                        },
                        "errors": [],
                    }
                    print("  ✓ 已加载缓存评分，跳过微服务调用。")
                else:
                    print("  用户选择重新评分。")
            else:
                cache_seqs_set = set(cache_sequences)
                current_seqs_set = set(current_sequences)
                new_count = len(current_seqs_set - cache_seqs_set)
                removed_count = len(cache_seqs_set - current_seqs_set)
                print(f"\n[Step 3/7] 缓存肽列表与当前不一致")
                print(f"  缓存: {len(cache_sequences)} 条 (时间: {cache_time})")
                print(f"  当前: {len(current_sequences)} 条")
                if new_count > 0:
                    print(f"  新增 {new_count} 条肽，需重新评分")
                if removed_count > 0:
                    print(f"  移除 {removed_count} 条肽")
        except Exception as e:
            print(f"  ⚠ 读取缓存失败 ({e})，将重新评分。")

    # ── 1–3. 调用微服务（如果缓存未命中） ─────────────────────
    if eval_result is None:
        print("\n[Step 3/7] 调用微服务评分 …")
        client = ServiceClient()

        try:
            service_names = [
                name for name, cfg in SERVICES.items()
                if cfg.get("group") in {"score", "filter"}
            ]
            print("  健康检查中 …")
            health = await client.check_health(service_names)
            available = [n for n, s in health.items() if s["available"]]
            unavailable = [n for n, s in health.items() if not s["available"]]

            # 打印各服务状态
            for name, status in health.items():
                icon = "✓" if status["available"] else "✗"
                print(f"    [{icon}] {name}: {status['status']}")

            # 如果没有可用服务，优雅降级
            if not available:
                print("  ⚠️  没有可用微服务。")
                await client.close()

                # 尝试使用缓存
                if CACHE_PATH.exists():
                    try:
                        with open(CACHE_PATH, encoding="utf-8") as f:
                            cache = json.load(f)
                        eval_result = {
                            "peptide_scores": cache["peptide_scores"],
                            "service_status": {
                                "available": cache.get("services_used", []),
                                "unavailable": [],
                            },
                            "errors": [],
                        }
                        print(
                            f"  ✓ 回退使用缓存 (时间: {cache.get('cached_at', '未知')})"
                        )
                    except Exception:
                        pass

                if eval_result is None:
                    print("  → 无评分数据，将以全量肽继续枚举。")
                    eval_result = {
                        "peptide_scores": {},
                        "service_status": {
                            "available": [],
                            "unavailable": service_names,
                        },
                        "errors": [],
                    }

            else:
                # 并发调用各微服务
                print(
                    f"\n  对 {len(passed_peptides)} 条肽调用 {len(available)} 个微服务 …"
                )
                eval_result = await client.evaluate_peptides(
                    passed_peptides, available, health
                )

                # 打印各服务的错误（如有）
                if eval_result["errors"]:
                    for err in eval_result["errors"]:
                        print(f"    ⚠ {err['service']}: {err['error']}")

                # ── 4. 写入缓存 ──────────────────────────────
                cache_data = {
                    "cached_at": datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "peptide_count": len(passed_peptides),
                    "peptide_sequences": current_sequences,
                    "services_used": available,
                    "peptide_scores": eval_result["peptide_scores"],
                }
                save_step(cache_data, "cache_peptide_scores.json")
                print(
                    f"  ✓ 评分结果已缓存 ({len(passed_peptides)} 条肽, {len(available)} 个服务)"
                )
        finally:
            await client.close()

    # 输出 Step 3 结果
    step03 = {
        "step": "03_peptide_scores",
        "service_status": eval_result["service_status"],
        "errors": eval_result["errors"],
        "peptide_count": len(passed_peptides),
    }
    save_step(step03, "step03_peptide_scores.json")
    save_step(eval_result["peptide_scores"], "step03_peptide_scores_detail.json")

    # ═══════════════════════════════════════════════════════════════
    # Step 4: 肽评分筛选 — 硬过滤 + 加权评分 + Top-N
    # ═══════════════════════════════════════════════════════════════
    #
    # 在枚举前对肽执行硬过滤和评分筛选：
    #   1. 硬过滤：毒性 ≥0.38 / 过敏原 ≥0.3 / 溶血 ≥0.55 → 淘汰
    #   2. 加权评分：7 个评分服务的归一化加权平均
    #   3. 取 Top N：只保留评分最高的前 N 条肽进入枚举
    #
    # 有毒或低分肽被淘汰后不会进入超级枚举，大幅缩减 construct 空间。

    print("\n[Step 4/7] 肽评分筛选（硬过滤 + 加权评分）…")
    step04, top_peptides, failed_peptides = score_and_filter_peptides(
        eval_result["peptide_scores"],
        passed_peptides,
        top_n=TOP_PEPTIDES_BEFORE_ENUMERATION,
    )
    save_step(step04, "step04_peptide_selection.json")
    if failed_peptides:
        save_step(
            {
                "step": "04_failed_peptides",
                "count": len(failed_peptides),
                "results": failed_peptides,
            },
            "step04_failed_peptides.json",
        )
    print(f"  硬过滤淘汰: {len(failed_peptides)} 条")
    print(f"  评分通过: {len(top_peptides)} 条（将进入枚举）")
    if top_peptides:
        print(
            f"  评分范围: {step04['final_score_range']['max']:.4f} ~ {step04['final_score_range']['min']:.4f}"
        )

    if not top_peptides:
        print("  ⚠️  没有肽通过评分筛选，流水线终止。")
        return

    # ═══════════════════════════════════════════════════════════════
    # Step 5: 超级枚举 construct（仅对 Top 肽）
    # ═══════════════════════════════════════════════════════════════
    #
    # 枚举空间 = Top 肽 × (N+1 个插入位置) × (10 linker + 1 无 linker)
    # 因为肽已预先评分，直接继承 final_score / service_scores 到 construct。

    print("\n[Step 5/7] 超级枚举 construct …")
    constructs = generate_constructs(scaffold, top_peptides, linkers)

    # 将肽的评分复制到每条 construct（替代旧 ServiceClient.map_scores_to_constructs）
    for c in constructs:
        pid = c["peptide_id"]
        pep = next((p for p in top_peptides if p.get("peptide_id") == pid), None)
        if pep:
            c["service_scores"] = pep.get("service_scores", {})
            c["peptide_final_score"] = pep.get("final_score", 0.0)
            c["score_breakdown"] = pep.get("score_breakdown", {})

    step05 = summarize_enumeration(constructs, scaffold, top_peptides, linkers)
    save_step(step05, "step05_enumeration_summary.json")
    write_constructs_csv(
        constructs,
        "step05_enumerated_constructs.csv",
        extra_cols=["service_scores", "peptide_final_score"],
    )
    print(f"  生成 {len(constructs)} 条 construct")

    # ═══════════════════════════════════════════════════════════════
    # Step 6: 预过滤 construct — 禁入区检测
    # ═══════════════════════════════════════════════════════════════
    #
    # 扫描 scaffold 序列，标记禁止插入区域：
    #   poly-Ala 区（β-sheet 结晶）、Cys 密集区（二硫键风险）、疏水核心
    #
    # 插入位置落在禁入区的 construct 被淘汰。

    print("\n[Step 6/7] 预过滤 construct（禁入区检测）…")
    forbidden_zones = find_forbidden_zones(scaffold["sequence"])
    print(
        f"  禁入位点: {forbidden_zones['forbidden_count']} / {len(scaffold['sequence'])}"
    )
    for zone in forbidden_zones["zones"]:
        print(f"    - {zone['type']}: {zone['reason']}")

    step06, passed_constructs, failed_constructs = prefilter_constructs(
        constructs, forbidden_zones
    )
    save_step(step06, "step06_prefilter_summary.json")
    write_constructs_csv(
        passed_constructs,
        "step06_passed_constructs.csv",
        extra_cols=["prefilter_status", "service_scores", "peptide_final_score"],
    )
    write_constructs_csv(
        failed_constructs,
        "step06_failed_constructs.csv",
        extra_cols=["prefilter_status", "prefilter_reason"],
    )
    print(f"  通过: {step06['passed']} / 淘汰: {step06['failed']}")

    if not passed_constructs:
        print("  ⚠️  没有 construct 通过预过滤，流水线终止。")
        return

    # ═══════════════════════════════════════════════════════════════
    # Step 7: 综合评分 & 排名
    # ═══════════════════════════════════════════════════════════════
    #
    # 对通过的 construct 进行加权评分（基于已继承的 service_scores），
    # 按分数降序排列，输出 Top-N 方案。

    print("\n[Step 7/7] 综合评分 & 排名 …")
    step07, top_results, all_ranked = score_and_rank(passed_constructs)
    save_step(step07, "step07_final_ranking.json")
    write_constructs_csv(
        all_ranked,
        "step07_all_ranked.csv",
        extra_cols=["final_score", "score_breakdown"],
    )

    # ── 终端输出 Top-N ──
    print(f"\n  Top {TOP_N} 方案：")
    print(
        f"  {'排名':<5} {'Construct ID':<12} {'肽':<20} {'位置':<6} "
        f"{'Linker':<15} {'评分':<8}"
    )
    print(f"  {'─' * 5} {'─' * 12} {'─' * 20} {'─' * 6} {'─' * 15} {'─' * 8}")
    for i, r in enumerate(top_results, 1):
        pep_seq = r["peptide_sequence"]
        if len(pep_seq) > 18:
            pep_seq = pep_seq[:17] + "…"
        print(
            f"  {i:<5} {r['construct_id']:<12} {pep_seq:<20} "
            f"{r['insertion_position']:<6} {r['linker_id']:<15} "
            f"{r['final_score']:<8.4f}"
        )

    # ── 耗时统计 ──
    elapsed = time.time() - started_at
    print(f"\n总耗时: {elapsed:.1f}s")
    print(f"所有输出见: {OUTPUT_DIR}/")
    print("=" * 60)
