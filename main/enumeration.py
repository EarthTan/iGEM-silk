"""
============================================================================
 超级枚举法 — 肽理化筛选 · 插入位点枚举 · 禁入区过滤 · 文件输出
============================================================================

本模块是流水线的计算核心，实现了 PROGRAM 1.md 中描述的"超级枚举法"。

整体流程
--------
1. 理化性质计算      — GRAVY、净电荷、pI、分子量
2. 功能肽预筛选 (Step 2) — 按长度/亲水性/电荷过滤，淘汰不合适的肽
3. 禁入区识别         — 扫描 scaffold，找出 poly-Ala / Cys密集 / 疏水核心
4. Construct 枚举 (Step 3) — 每条肽 × 每个位置 × 每种 linker 全排列
5. Construct 预过滤 (Step 4) — 剔除插入位置落在禁入区的 construct
6. 文件输出           — JSON（摘要）+ CSV（大规模 construct 列表）

关键设计决策
-----------
- 微服务评分是肽级别的，不是 construct 级别。
  原因：这些模型训练时用的是短肽，对 500+ aa 的全长融合蛋白无意义。
  construct 的评分继承其功能肽的评分，差异体现在插入位置的"结构兼容性"上。

- 枚举空间可能很大：648 肽 × 347 位置 × 11 linker ≈ 247 万条 construct。
  因此 construct 列表用 CSV 输出（流式友好的表格格式），
  JSON 只存放摘要和统计信息。

- 理化计算优先使用 Biopython（已安装），失败时回退到手动实现。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
from Bio.SeqUtils.ProtParam import ProteinAnalysis

from main.config import (
    KYTE_DOOLITTLE,
    PEPTIDE_MIN_LENGTH,
    PEPTIDE_MAX_LENGTH,
    PEPTIDE_MAX_GRAVY,
    PEPTIDE_MIN_CHARGE,
    PEPTIDE_MAX_CHARGE,
    PI_CAUTION_RANGE,
    POLY_ALA_MIN_LEN,
    CYS_CLUSTER_COUNT,
    CYS_CLUSTER_WINDOW,
    FORBIDDEN_WINDOW,
    HYDROPHOBIC_CORE_THRESHOLD,
    HYDROPHOBIC_CONSECUTIVE_WINDOWS,
    OUTPUT_DIR,
)


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                       一、理化性质计算工具函数                                  ║
# ╚════════════════════════════════════════════════════════════════════════════════╝

def compute_gravy(sequence: str) -> float:
    """
    计算 GRAVY —— Grand Average of Hydropathicity。

    GRAVY = 各残基 Kyte-Doolittle 值的算术平均。

    解读：
      GRAVY < 0  → 亲水性（倾向于暴露在蛋白表面，我们的目标）
      GRAVY > 0  → 疏水性（倾向于埋入蛋白内部，需淘汰）
      GRAVY ≈ 0  → 两亲性（可能在界面处）

    优先使用 Biopython 的 ProteinAnalysis.gravy()，
    如果它挂了（极少数情况下），回退到手动查表计算。
    """
    try:
        return ProteinAnalysis(sequence).gravy()
    except Exception:
        # 手动 fallback：查 Kyte-Doolittle 表取平均值
        if len(sequence) == 0:
            return 0.0
        total = sum(KYTE_DOOLITTLE.get(aa, 0.0) for aa in sequence)
        return total / len(sequence)


def compute_net_charge(sequence: str, ph: float = 7.0) -> float:
    """
    估算生理 pH (~7.0) 下的净电荷。

    简化模型（不去解完整的 Henderson-Hasselbalch 方程）：
      酸性残基 D (Asp), E (Glu)  →  -1（pKa ~4，pH 7 时完全去质子化）
      碱性残基 R (Arg)           →  +1（pKa ~12.5，pH 7 时始终质子化）
      碱性残基 K (Lys)           →  +1（pKa ~10.5，pH 7 时完全质子化）
      组氨酸 H (His)             →  +0.5（pKa ~6.0，pH 7 时约半数质子化）
      Cys, Tyr                  →   0（pKa > 8，pH 7 时不电离）

    注：这是近似计算，精确值需用 Biopython 的 pI 模块或 EMBOSS。
    """
    charge = 0.0
    for aa in sequence:
        if aa in ("D", "E"):
            charge -= 1.0
        elif aa in ("R", "K"):
            charge += 1.0
        elif aa == "H":
            charge += 0.5  # imidazole pKa ~6.0
    return charge


def compute_pi(sequence: str) -> float:
    """
    计算等电点 pI（使用 Biopython 的迭代求解算法）。

    pI 是蛋白/肽净电荷为零时的 pH。
    如果 pI 在 6–8 范围内，说明肽在生理 pH 附近溶解性可能较差，
    复性缓冲液需要故意偏离其 pI 来维持溶解。
    """
    try:
        return ProteinAnalysis(sequence).isoelectric_point()
    except Exception:
        return float("nan")


def compute_molecular_weight(sequence: str) -> float:
    """计算分子量（Dalton），基于氨基酸平均分子量。"""
    try:
        return ProteinAnalysis(sequence).molecular_weight()
    except Exception:
        return float("nan")


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                    二、Step 2 — 功能肽预筛选                                    ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
#
# 在开始昂贵的枚举之前，先用 O(n) 的理化计算筛掉明显不合适的肽。
#
# 过滤条件（三条都需满足才通过）：
#   1. 长度 5–15 aa — 太短没功能，太长干扰折叠
#   2. GRAVY < 0   — 必须偏亲水，避免在复性时被包埋
#   3. 净电荷 -3~+3 — 极端电荷影响 pI 分布和复性条件
#
# 额外警告（不淘汰）：
#   pI 在 6–8 范围 → 需注意复性 pH
#
# 输出结构
# --------
# 每条肽生成一个 entry dict：
#   {
#     "peptide_id": ...,   # 来源名
#     "sequence": ...,     # 序列
#     "length": ...,       # 长度
#     "gravy": ...,        # 亲疏水性
#     "net_charge": ...,   # 净电荷
#     "pi": ...,           # 等电点（可能为 null）
#     "molecular_weight": ...,
#     "passed": true/false,
#     "checks": [          # 每项检查的详细结果
#       {"check": "length", "passed": true, "detail": "..."},
#       ...
#     ],
#     "warnings": [...]    # 不淘汰但需注意的问题
#   }

def filter_peptides(df: pd.DataFrame) -> dict:
    """
    对功能肽 DataFrame 逐条做理化性质预筛选。

    参数
    ----
    df : 已经过 is_antioxidant == 1 过滤的 DataFrame（由 pipeline 层过滤）

    返回
    ----
    dict : {
        "step": "02_prefilter_peptides",
        "total": 总条目数,
        "passed": 通过数,
        "failed": 淘汰数,
        "filters_applied": {各过滤条件的阈值},
        "results": [每条肽的完整评估结果]
    }
    """
    results: list[dict] = []
    passed_count = 0
    failed_count = 0

    for _, row in df.iterrows():
        seq = str(row["sequence"]).strip().upper()

        # 跳过空值或非标准序列
        if not seq or pd.isna(row["sequence"]):
            continue

        # ── 计算四项理化性质 ──
        length = len(seq)
        gravy = compute_gravy(seq)
        net_charge = compute_net_charge(seq)
        pi = compute_pi(seq)
        mw = compute_molecular_weight(seq)

        checks = []
        passed = True

        # 检查 1：长度
        if length < PEPTIDE_MIN_LENGTH:
            checks.append({"check": "length_min", "passed": False,
                           "detail": f"长度 {length} < {PEPTIDE_MIN_LENGTH}"})
            passed = False
        elif length > PEPTIDE_MAX_LENGTH:
            checks.append({"check": "length_max", "passed": False,
                           "detail": f"长度 {length} > {PEPTIDE_MAX_LENGTH}"})
            passed = False
        else:
            checks.append({"check": "length", "passed": True,
                           "detail": f"长度 {length} 在 [{PEPTIDE_MIN_LENGTH}, {PEPTIDE_MAX_LENGTH}]"})

        # 检查 2：GRAVY 亲水性
        if gravy >= PEPTIDE_MAX_GRAVY:
            checks.append({"check": "gravy", "passed": False,
                           "detail": f"GRAVY {gravy:.3f} >= {PEPTIDE_MAX_GRAVY}（偏疏水）"})
            passed = False
        else:
            checks.append({"check": "gravy", "passed": True,
                           "detail": f"GRAVY {gravy:.3f} < {PEPTIDE_MAX_GRAVY}（亲水）"})

        # 检查 3：净电荷
        if net_charge < PEPTIDE_MIN_CHARGE:
            checks.append({"check": "net_charge", "passed": False,
                           "detail": f"净电荷 {net_charge:.1f} < {PEPTIDE_MIN_CHARGE}"})
            passed = False
        elif net_charge > PEPTIDE_MAX_CHARGE:
            checks.append({"check": "net_charge", "passed": False,
                           "detail": f"净电荷 {net_charge:.1f} > {PEPTIDE_MAX_CHARGE}"})
            passed = False
        else:
            checks.append({"check": "net_charge", "passed": True,
                           "detail": f"净电荷 {net_charge:.1f} 在 [{PEPTIDE_MIN_CHARGE}, {PEPTIDE_MAX_CHARGE}]"})

        # 警告（不淘汰）：pI 在 6–8 范围
        warnings = []
        if not pd.isna(pi) and PI_CAUTION_RANGE[0] <= pi <= PI_CAUTION_RANGE[1]:
            warnings.append(f"pI {pi:.1f} 在 6-8 范围，复性时需注意偏离 pH")

        entry = {
            "peptide_id": row.get("source_name", row.get("database_id", "")),
            "sequence": seq,
            "length": length,
            "gravy": round(gravy, 4),
            "net_charge": round(net_charge, 2),
            "pi": round(pi, 2) if not pd.isna(pi) else None,
            "molecular_weight": round(mw, 2) if not pd.isna(mw) else None,
            "is_antioxidant": int(row.get("is_antioxidant", 0)),
            "is_cell_penetrating": int(row.get("is_cell_penetrating", 0)),
            "passed": passed,
            "checks": checks,
            "warnings": warnings,
        }
        results.append(entry)
        if passed:
            passed_count += 1
        else:
            failed_count += 1

    return {
        "step": "02_prefilter_peptides",
        "total": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "filters_applied": {
            "length": f"[{PEPTIDE_MIN_LENGTH}, {PEPTIDE_MAX_LENGTH}]",
            "gravy": f"< {PEPTIDE_MAX_GRAVY}",
            "net_charge": f"[{PEPTIDE_MIN_CHARGE}, {PEPTIDE_MAX_CHARGE}]",
        },
        "results": results,
    }


def get_passed_peptides(prefilter_result: dict) -> list[dict]:
    """从预筛选结果中提取所有通过（passed=True）的肽。"""
    return [r for r in prefilter_result["results"] if r["passed"]]


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                    三、禁入区识别 — 扫描 scaffold                               ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
#
# 在 scaffold 序列上滑动扫描，标记三类"禁止插入"的区域。
# 这些区域如果被插入功能肽，要么破坏丝素蛋白的结构完整性，
# 要么导致功能肽在复性后被包埋而丧失功能。
#
# 返回的 forbidden_positions 是一个 set，包含所有禁止插入的残基位置（0-based）。
# construct 的插入位置如果在此 set 中，则在 Step 4 被淘汰。

def find_forbidden_zones(scaffold_seq: str) -> dict:
    """
    扫描 scaffold 序列，返回所有禁入区信息。

    参数
    ----
    scaffold_seq : str, 丝素蛋白骨架氨基酸序列

    返回
    ----
    dict : {
        "scaffold_length": int,
        "forbidden_count": int,           # 禁入残基位置总数
        "forbidden_positions": [int, ...], # 有序列表，所有禁入位置
        "zones": [{type, start, end, reason}, ...]  # 每个禁入区的详情
    }

    三类禁入区
    ----------
    1. poly-Ala 区
       连续 ≥ POLY_ALA_MIN_LEN 个丙氨酸残基 → β-sheet 结晶区
       插入功能肽会打断 β-sheet 晶体堆积，导致力学结构崩溃
       算法：单指针扫描，找到所有连续 A run，超过阈值则标记

    2. Cys 密集区
       在 CYS_CLUSTER_WINDOW 窗口内有 ≥ CYS_CLUSTER_COUNT 个半胱氨酸
       插入的肽若含 Cys，可能在此形成非预期二硫键 → 错误折叠
       算法：收集所有 Cys 位置，滑窗检测聚集

    3. 疏水核心
       用 FORBIDDEN_WINDOW 大小的滑动窗口计算 Kyte-Doolittle 平均疏水性
       连续 ≥ HYDROPHOBIC_CONSECUTIVE_WINDOWS 个窗口均值 > HYDROPHOBIC_CORE_THRESHOLD
       功能肽插入疏水核心 → 复性时被 β-sheet 堆叠包埋 → 功能丧失
       算法：滑动窗口 → 找连续超标窗口 → 合并为区域
    """
    n = len(scaffold_seq)
    forbidden_positions: set[int] = set()
    zone_details: list[dict] = []

    # ── 扫描 1：poly-Ala 区 ──────────────────────────────────
    # 用双指针 i, j 扫描连续 A 序列
    i = 0
    while i < n:
        if scaffold_seq[i] == "A":
            j = i
            while j < n and scaffold_seq[j] == "A":
                j += 1
            run_len = j - i
            if run_len >= POLY_ALA_MIN_LEN:
                # 将整个 A run 的所有残基位置标记为禁入
                for pos in range(i, j):
                    forbidden_positions.add(pos)
                zone_details.append({
                    "type": "poly-Ala",
                    "start": i,
                    "end": j - 1,
                    "length": run_len,
                    "sequence": scaffold_seq[i:j],
                    "reason": f"连续 {run_len} 个 Ala（≥{POLY_ALA_MIN_LEN}），β-sheet 结晶区",
                })
            i = j
        else:
            i += 1

    # ── 扫描 2：Cys 密集区 ──────────────────────────────────
    # 收集所有 Cys 的索引位置
    cys_positions = [i for i, aa in enumerate(scaffold_seq) if aa == "C"]

    for i in range(len(cys_positions)):
        # 以当前 Cys 为起点，收集窗口内所有 Cys
        cluster = [cys_positions[i]]
        for j in range(i + 1, len(cys_positions)):
            if cys_positions[j] - cluster[0] <= CYS_CLUSTER_WINDOW:
                cluster.append(cys_positions[j])
            else:
                break  # 距离超出窗口，不再属于同一 cluster

        if len(cluster) >= CYS_CLUSTER_COUNT:
            # 标记窗口范围（cluster 周围各扩展半个窗口）
            zone_start = max(0, cluster[0] - CYS_CLUSTER_WINDOW // 2)
            zone_end = min(n, cluster[-1] + CYS_CLUSTER_WINDOW // 2)
            for pos in range(zone_start, zone_end):
                forbidden_positions.add(pos)
            zone_details.append({
                "type": "Cys_cluster",
                "cys_positions": cluster,
                "count": len(cluster),
                "span": cluster[-1] - cluster[0],
                "reason": f"{len(cluster)} 个 Cys 间距 ≤ {CYS_CLUSTER_WINDOW}，二硫键风险区",
            })
            # 跳到 cluster 最后一个 Cys 的索引，避免重复标记同一 cluster
            i = cys_positions.index(cluster[-1])

    # ── 扫描 3：疏水核心 ────────────────────────────────────
    window = FORBIDDEN_WINDOW
    hydrophobic_starts: list[int] = []

    # 第一遍：找出所有疏水窗口的起始位置
    for i in range(n - window + 1):
        window_seq = scaffold_seq[i:i + window]
        avg_hydro = sum(KYTE_DOOLITTLE.get(aa, 0.0) for aa in window_seq) / window
        if avg_hydro > HYDROPHOBIC_CORE_THRESHOLD:
            hydrophobic_starts.append(i)

    # 第二遍：将连续的疏水窗口合并为区域
    if hydrophobic_starts:
        # 按连续性分组
        consecutive_groups = []
        current_group = [hydrophobic_starts[0]]
        for pos in hydrophobic_starts[1:]:
            if pos <= current_group[-1] + 1:
                # 与前一个窗口相邻或重叠 → 同一组
                current_group.append(pos)
            else:
                # 断开 → 开始新组
                consecutive_groups.append(current_group)
                current_group = [pos]
        consecutive_groups.append(current_group)  # 最后一组

        # 只保留连续窗口数 ≥ 阈值的组
        for group in consecutive_groups:
            if len(group) >= HYDROPHOBIC_CONSECUTIVE_WINDOWS:
                zone_start = group[0]
                zone_end = group[-1] + window  # +window 因为窗口覆盖 window 个残基
                for pos in range(zone_start, zone_end):
                    forbidden_positions.add(pos)
                zone_details.append({
                    "type": "hydrophobic_core",
                    "start": zone_start,
                    "end": zone_end - 1,
                    "consecutive_windows": len(group),
                    "sequence_window": scaffold_seq[zone_start:zone_end],
                    "reason": (
                        f"连续 {len(group)} 个窗口疏水均值 "
                        f"> {HYDROPHOBIC_CORE_THRESHOLD}（≥{HYDROPHOBIC_CONSECUTIVE_WINDOWS}），疏水核心"
                    ),
                })

    return {
        "scaffold_length": n,
        "forbidden_count": len(forbidden_positions),
        "forbidden_positions": sorted(forbidden_positions),
        "zones": zone_details,
    }


def is_position_forbidden(pos: int, forbidden_zones: dict) -> tuple[bool, str | None]:
    """
    检查给定的插入位置是否在禁入区。

    返回 (is_forbidden: bool, reason: str | None)。

    pos 是插入位置（0-based），表示在 scaffold[pos] 之前插入。
    比如 pos=5 表示在残基 4 和 5 之间插入，即替换 scaffold[5:] 的起始位置。
    禁入区检查覆盖该位置对应的残基范围。
    """
    if pos in forbidden_zones["forbidden_positions"]:
        # 找到该位置属于哪个禁入区（用于输出淘汰原因）
        for zone in forbidden_zones["zones"]:
            start = zone.get("start", 0)
            end = zone.get("end", 0)
            if zone["type"] == "Cys_cluster":
                # Cys 密集区的范围是 cluster ± 半个窗口
                cys_pos = zone["cys_positions"]
                if cys_pos[0] - CYS_CLUSTER_WINDOW // 2 <= pos <= cys_pos[-1] + CYS_CLUSTER_WINDOW // 2:
                    return True, zone["reason"]
            elif start <= pos <= end:
                return True, zone["reason"]
        return True, "位于禁止插入区"
    return False, None


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                  四、Step 3 — Construct 超级枚举                                ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
#
# 这就是 PROGRAM 1.md 中描述的"逐个位置插入（枚举法）"。
#
# 枚举空间 = 肽 × 插入位置 × linker 选项
#   - 肽：通过 Step 2 预筛选的肽（约 650 条）
#   - 位置：0 到 len(scaffold)，共 N+1 个位置（包含 N 端和 C 端）
#   - linker：10 种 FASTA linker + 1 种"无 linker"（直接插入）
#
# 对于一个 346 aa 的 scaffold：
#   650 × 347 × 11 ≈ 248 万种 construct
#
# 插入的三种模式
# --------------
# pos = 0（N 端插入）
#   结构：peptide + [linker] + scaffold
#   无 linker 时：peptide + scaffold
#   优势：末端自然暴露，肽不被包埋（PROGRAM 0.md 策略 B）
#
# 0 < pos < N（内部插入）
#   结构：scaffold[:pos] + linker + peptide + linker + scaffold[pos:]
#   无 linker 时：scaffold[:pos] + peptide + scaffold[pos:]
#   注意：内部插入用两个 linker（两侧各一个），保证肽的构象自由度
#         这是 PROGRAM 0.md 策略 A 的 GGX 无定形区插入方式
#
# pos = N（C 端插入）
#   结构：scaffold + [linker] + peptide
#   无 linker 时：scaffold + peptide
#   优势：同 N 端，自然暴露

def generate_constructs(
    scaffold: dict[str, str],
    peptides: list[dict],
    linkers: list[dict[str, str]],
) -> list[dict]:
    """
    超级枚举法：生成所有融合蛋白 construct。

    参数
    ----
    scaffold : {"id": str, "sequence": str}
    peptides : [{"peptide_id": str, "sequence": str, ...}, ...]
    linkers  : [{"id": str, "sequence": str}, ...]
               不含 "no_linker" 选项，函数内部自动追加

    返回
    ----
    list[dict] : 每条 construct 包含：
        construct_id      — 唯一编号（C000001 格式）
        peptide_id        — 来源肽的标识
        peptide_sequence  — 功能肽序列
        insertion_position— 插入位置（0..N）
        linker_id         — linker 标识（含 "no_linker"）
        linker_sequence   — linker 序列（空字符串表示无 linker）
        scaffold_id       — 骨架标识
        scaffold_length   — 骨架长度
        fusion_sequence   — 完整的融合蛋白序列
        fusion_length     — 融合蛋白总长度
    """
    scaffold_seq = scaffold["sequence"]
    scaffold_id = scaffold["id"]
    n = len(scaffold_seq)

    # 构建 linker 选项列表：无 linker 在最前面
    linker_options: list[dict[str, str]] = [{"id": "no_linker", "sequence": ""}]
    linker_options.extend(linkers)

    constructs: list[dict] = []
    construct_id = 0

    # 三重循环：肽 × 位置 × linker
    for pep in peptides:
        pep_seq = pep["sequence"]
        pep_id = pep.get("peptide_id", pep.get("source_name", "unknown"))

        for pos in range(n + 1):          # 0, 1, 2, ..., n
            for linker in linker_options:  # no_linker + 10 linkers
                linker_seq = linker["sequence"]
                linker_id = linker["id"]

                # ── 根据位置拼接融合序列 ──
                if pos == 0:
                    # N 端：肽在最前面
                    if linker_seq:
                        fusion_seq = pep_seq + linker_seq + scaffold_seq
                    else:
                        fusion_seq = pep_seq + scaffold_seq

                elif pos == n:
                    # C 端：肽在最后面
                    if linker_seq:
                        fusion_seq = scaffold_seq + linker_seq + pep_seq
                    else:
                        fusion_seq = scaffold_seq + pep_seq

                else:
                    # 内部插入：scaffold 分为两段，肽夹在中间
                    if linker_seq:
                        fusion_seq = (
                            scaffold_seq[:pos]
                            + linker_seq
                            + pep_seq
                            + linker_seq
                            + scaffold_seq[pos:]
                        )
                    else:
                        fusion_seq = scaffold_seq[:pos] + pep_seq + scaffold_seq[pos:]

                construct_id += 1
                constructs.append({
                    "construct_id": f"C{construct_id:06d}",
                    "peptide_id": pep_id,
                    "peptide_sequence": pep_seq,
                    "insertion_position": pos,
                    "linker_id": linker_id,
                    "linker_sequence": linker_seq,
                    "scaffold_id": scaffold_id,
                    "scaffold_length": n,
                    "fusion_sequence": fusion_seq,
                    "fusion_length": len(fusion_seq),
                })

    return constructs


def summarize_enumeration(constructs: list[dict], scaffold: dict, peptides: list[dict],
                          linkers: list[dict]) -> dict:
    """
    生成枚举步骤的摘要（不包含 construct 列表，因为太大）。
    仅输出统计信息和计算公式，完整列表见 CSV 文件。
    """
    return {
        "step": "03_enumerated_constructs",
        "scaffold": {
            "id": scaffold["id"],
            "length": len(scaffold["sequence"]),
        },
        "input_peptides": len(peptides),
        "input_linkers": len(linkers) + 1,  # +1 是无 linker 选项
        "insertion_positions": len(scaffold["sequence"]) + 1,
        "total_constructs": len(constructs),
        "formula": (
            f"{len(peptides)} peptides × "
            f"{len(scaffold['sequence']) + 1} positions × "
            f"{len(linkers) + 1} linkers = {len(constructs)}"
        ),
    }


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                 五、Step 4 — Construct 预过滤                                  ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
#
# 根据 Step 3 生成的禁入区信息，过滤 construct：
#   插入位置落在禁入区 → 淘汰
#   插入位置在安全区 → 通过

def prefilter_constructs(
    constructs: list[dict],
    forbidden_zones: dict,
) -> tuple[dict, list[dict], list[dict]]:
    """
    根据禁入区过滤 construct。

    返回 (summary_dict, passed_list, failed_list) 三元组。

    summary_dict 包含过滤统计和各类型淘汰数量，
    passed_list / failed_list 分别包含通过和淘汰的 construct 完整信息。
    """
    passed: list[dict] = []
    failed: list[dict] = []

    for c in constructs:
        pos = c["insertion_position"]
        forbidden, reason = is_position_forbidden(pos, forbidden_zones)

        if forbidden:
            c["prefilter_status"] = "failed"
            c["prefilter_reason"] = reason
            failed.append(c)
        else:
            c["prefilter_status"] = "passed"
            c["prefilter_reason"] = None
            passed.append(c)

    # 按禁入区类型统计淘汰数量
    # 用于输出报告："poly-Ala 淘汰了 X 条，Cys 密集区淘汰了 Y 条..."
    zone_type_counts: dict[str, int] = {}
    for c in failed:
        reason = c.get("prefilter_reason", "unknown")
        if "poly-Ala" in (reason or ""):
            zone_type_counts["poly-Ala"] = zone_type_counts.get("poly-Ala", 0) + 1
        elif "Cys" in (reason or ""):
            zone_type_counts["Cys_cluster"] = zone_type_counts.get("Cys_cluster", 0) + 1
        elif "疏水" in (reason or ""):
            zone_type_counts["hydrophobic_core"] = zone_type_counts.get("hydrophobic_core", 0) + 1
        else:
            zone_type_counts["other"] = zone_type_counts.get("other", 0) + 1

    summary = {
        "step": "04_prefilter_constructs",
        "total": len(constructs),
        "passed": len(passed),
        "failed": len(failed),
        "filter_reasons": zone_type_counts,
        "forbidden_zones_summary": {
            "total_forbidden_positions": forbidden_zones["forbidden_count"],
            "zones": forbidden_zones["zones"],
        },
    }
    return summary, passed, failed


# ╔════════════════════════════════════════════════════════════════════════════════╗
# ║                     六、文件输出工具函数                                         ║
# ╚════════════════════════════════════════════════════════════════════════════════╝
#
# 两种输出格式各有用途：
#   JSON — 人类可读的摘要、配置、少量记录（适合 git diff、文本编辑器）
#   CSV  — 大规模 construct 列表（可导入 Excel/Pandas/数据库）

# construct CSV 的基础列（所有 construct CSV 文件共享）
CONSTRUCT_CSV_COLUMNS = [
    "construct_id", "peptide_id", "peptide_sequence",
    "insertion_position", "linker_id", "linker_sequence",
    "scaffold_id", "scaffold_length", "fusion_length", "fusion_sequence",
]


def write_constructs_csv(constructs: list[dict], filename: str,
                         extra_cols: list[str] | None = None) -> None:
    """
    将 construct 列表写入 CSV 文件（适合大规模数据，约 1GB / 250 万行）。

    extra_cols 参数允许不同步骤追加各自的元数据列：
      Step 3: 无额外列（仅基础列）
      Step 4: prefilter_status, prefilter_reason
      Step 5: service_scores
      Step 6: service_scores, hard_filter_status, hard_filter_reasons
      Step 7: final_score, score_breakdown

    extrasaction="ignore" 确保 construct dict 中多出的 key 不会导致写入失败，
    只写入 fieldnames 中声明的列。
    """
    output_path = Path(OUTPUT_DIR) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    columns = list(CONSTRUCT_CSV_COLUMNS)
    if extra_cols:
        columns.extend(extra_cols)

    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(constructs)

    print(f"  [✓] 已保存: {output_path} ({len(constructs)} rows)")


def save_step(result: dict, filename: str) -> None:
    """
    将步骤结果保存为 JSON 文件（适合少量数据：摘要、配置、评分详情）。

    JSON 编码器会自动处理：
      - numpy 数值类型 → Python float/int
      - pandas Timestamp → ISO 字符串
      - 自定义 __float__ 方法的对象 → float
    """
    output_path = Path(OUTPUT_DIR) / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)

    class NpEncoder(json.JSONEncoder):
        """扩展 JSONEncoder 以处理 numpy/pandas 的特殊类型。"""
        def default(self, obj):
            if hasattr(obj, "item"):       # numpy scalar
                return obj.item()
            if isinstance(obj, (pd.Timestamp,)):
                return str(obj)
            if hasattr(obj, "__float__"):  # numpy float
                return float(obj)
            return super().default(obj)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, cls=NpEncoder)

    print(f"  [✓] 已保存: {output_path}")
