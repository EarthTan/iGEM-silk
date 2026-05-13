#!/usr/bin/env python3
"""
全微服务测试脚本 — 验证所有微服务（除 PDB 类）的功能。

用法:
    cd tools && python test_all_services.py

设计要点:
    - CPU/轻量服务并发测试（不争 GPU 显存）
    - GPU 重量服务串行测试（逐个跑，避免显存争用）
    - AlphaFold3 通过 /predict/async 异步轮询测试

输出:
    - 控制台实时输出
    - 测试报告写入 test_report.md
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import httpx

from main.config import SERVICES
from main.client import ServiceClient

# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════

TEST_PEPTIDE = "YDFYTP"
TEST_PEPTIDE_ID = "test_pep_001"

# 排除的服务
SKIP_SERVICES = {"sasa", "aggrescan3d", "pepfold4", "temstapro"}
# sasa / aggrescan3d: PDB 类服务，需要 PDB 输入
# pepfold4: 缺少 Docker 镜像（需从 RPBS OwnCloud 下载）
# temstapro: 需要下载 ProtT5-XL (~3GB)，目前仍在加载

# GPU 重量服务（加载大模型，需要串行测试避免显存争用）
GPU_HEAVY_SERVICES = {"bepipred3", "plm4cpps", "hemopi2", "alphafold3", "esmfold", "omegafold"}

# ═══════════════════════════════════════════════════════════════════════════════
# 全局状态
# ═══════════════════════════════════════════════════════════════════════════════

test_results: dict[str, dict] = {}
START_TIME = time.time()


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def fmt_result(name: str, ok: bool, data: dict) -> dict:
    return {"service": name, "ok": ok, "data": data, "time": time.time() - START_TIME}


def _extract_score_label(resp: dict) -> tuple:
    """从 /predict 响应中提取 score 和 label。

    响应结构（FASTA 服务）:
        {"success": true, "result": {"score": 0.85, "label": "xxx", ...}}
    响应结构（结构预测服务）:
        {"success": true, "result": {"pdb_content": "...", "confidence": 0.87, ...}}
    """
    result = resp.get("result") or {}
    score = result.get("score")
    label = result.get("label")
    if score is None and label is None:
        confidence = result.get("confidence")
        has_pdb = bool(result.get("pdb_content"))
        if confidence is not None or has_pdb:
            label = f"struct(conf={confidence}, pdb={has_pdb})"
    return score, label


# ═══════════════════════════════════════════════════════════════════════════════
# 1. CPU/轻量服务测试（可并发）
# ═══════════════════════════════════════════════════════════════════════════════

async def test_lightweight_services(client: ServiceClient, names: list[str]):
    """并发测试 CPU/轻量服务（不争 GPU 显存）。"""
    if not names:
        return
    log(f"CPU/轻量服务 ({len(names)} 个, 并发)...")
    tasks = [_test_one(client, name) for name in names]
    results = await asyncio.gather(*tasks)
    for r in results:
        test_results[r["service"]] = r


# ═══════════════════════════════════════════════════════════════════════════════
# 2. GPU 重量服务测试（串行）
# ═══════════════════════════════════════════════════════════════════════════════

async def test_gpu_heavy_services(client: ServiceClient, names: list[str]):
    """串行测试 GPU 重量服务（逐个跑，避免显存争用）。

    每个服务测试前检查显存使用量，如果显存占用过高发出警告。
    """
    if not names:
        return
    log(f"GPU 重量服务 ({len(names)} 个, 串行 — 避免显存争用)...")
    for name in names:
        _check_gpu_memory(name)
        r = await _test_one(client, name)
        test_results[r["service"]] = r
        # 测试完一个等一会儿让显存释放
        await asyncio.sleep(5)


def _check_gpu_memory(name: str):
    """检查 GPU 显存使用量，过高时发出警告。"""
    import subprocess
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
        )
        used, total = result.stdout.strip().split(", ")
        used_int, total_int = int(used), int(total)
        pct = used_int / total_int * 100
        if pct > 50:
            log(f"  ⚠  {name}: GPU 显存已用 {used_int}/{total_int} MiB ({pct:.0f}%)，"
                f"测试可能因 OOM 失败")
        else:
            log(f"  GPU 显存: {used_int}/{total_int} MiB ({pct:.0f}%) — OK")
    except Exception:
        pass  # nvidia-smi 不可用时静默跳过


# ═══════════════════════════════════════════════════════════════════════════════
# 3. 单个服务测试
# ═══════════════════════════════════════════════════════════════════════════════

async def _test_one(client: ServiceClient, name: str) -> dict:
    """测试单个 FASTA 微服务的 /predict。"""
    t0 = time.time()
    try:
        resp = await client.predict_single(name, TEST_PEPTIDE, TEST_PEPTIDE_ID)
        elapsed = time.time() - t0

        success = resp.get("success", False)
        score, label = _extract_score_label(resp)
        error = resp.get("error")

        if success:
            if score is not None:
                log(f"  [PASS] {name}: score={score:.4f}, label={label}, "
                    f"t={elapsed:.1f}s")
            elif label is not None:
                log(f"  [PASS] {name}: label={label}, t={elapsed:.1f}s")
            else:
                log(f"  [WARN] {name}: success但无score/label, t={elapsed:.1f}s")
        else:
            log(f"  [FAIL] {name}: {error}, t={elapsed:.1f}s")

        return fmt_result(name, success, resp)

    except Exception as e:
        elapsed = time.time() - t0
        log(f"  [FAIL] {name}: exception={e}, t={elapsed:.1f}s")
        return fmt_result(name, False, {"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════════
# 4. AlphaFold3 异步轮询测试
# ═══════════════════════════════════════════════════════════════════════════════

async def test_alphafold3_async():
    """测试 AF3 异步轮询 — POST /predict/async + 轮询 + GET /result。

    AF3 测试前会检查 GPU 显存，如果被其他服务占用则会警告。
    """
    log("=" * 60)
    log("AlphaFold3 异步轮询测试")
    log("=" * 60)

    base_url = "http://127.0.0.1:8201"

    async with httpx.AsyncClient(timeout=30.0) as http:

        # Step 1: 健康检查 + GPU 显存检查
        log("\n[1/5] 健康检查...")
        resp = await http.get(f"{base_url}/health")
        health = resp.json()
        log(f"  model_loaded={health.get('model_loaded')}, "
            f"status={health.get('status')}")

        if not health.get("model_loaded"):
            log("  ⛔ AF3 未就绪，跳过")
            test_results["alphafold3"] = fmt_result(
                "alphafold3", False, {"error": "model not loaded"}
            )
            return

        _check_gpu_memory("alphafold3")

        # Step 2: 提交异步预测
        log(f"\n[2/5] 提交异步预测 (seq={TEST_PEPTIDE})...")
        resp = await http.post(
            f"{base_url}/predict/async",
            json={"sequence": TEST_PEPTIDE, "peptide_id": TEST_PEPTIDE_ID},
        )
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}"
        async_resp = resp.json()
        job_id = async_resp["job_id"]
        log(f"  job_id={job_id}")
        test_results["alphafold3_submit"] = fmt_result(
            "alphafold3_submit", True, async_resp
        )

        # Step 3: 轮询状态
        log(f"\n[3/5] 轮询中 (每 30s 检查一次)...")
        poll_interval = 30
        max_polls = 480  # 最多等 4 小时
        final_status = None
        status_history = set()
        poll_count = 0

        for i in range(max_polls):
            resp = await http.get(f"{base_url}/status/{job_id}")
            status_data = resp.json()
            status = status_data["status"]
            progress = status_data.get("progress", "")

            if status not in status_history:
                log(f"  status={status}, progress={progress[:100]}")
                status_history.add(status)

            if status in ("success", "failed"):
                final_status = status
                log(f"  完成: {status} (耗时 {time.time() - START_TIME:.0f}s)")
                break
            poll_count += 1
            await asyncio.sleep(poll_interval)

        if final_status is None:
            log(f"  ⛔ 轮询超时")
            test_results["alphafold3_poll"] = fmt_result(
                "alphafold3_poll", False,
                {"error": f"轮询超时 ({max_polls * poll_interval}s)",
                 "history": list(status_history)},
            )
            return

        test_results["alphafold3_poll"] = fmt_result(
            "alphafold3_poll", True,
            {"status": final_status, "polls": poll_count,
             "history": list(status_history)},
        )

        # Step 4: 获取结果
        log(f"\n[4/5] 获取结果...")
        resp = await http.get(f"{base_url}/result/{job_id}")
        result = resp.json()
        if final_status == "success":
            has_pdb = bool(result.get("pdb_content", ""))
            confidence = result.get("confidence")
            log(f"  structure={'✅' if has_pdb else '❌'}, "
                f"confidence={confidence}, "
                f"cif={len(result.get('pdb_content',''))} bytes")
        else:
            error = result.get("error", "unknown")
            log(f"  error={error[:200]}...")

        test_results["alphafold3_result"] = fmt_result(
            "alphafold3_result", final_status == "success", result
        )

        # Step 5: 列出 + 清理
        log(f"\n[5/5] 清理 job...")
        resp = await http.delete(f"{base_url}/jobs/{job_id}")
        log(f"  deleted: {resp.json()}")

        # 列出剩余 jobs
        resp = await http.get(f"{base_url}/jobs")
        jobs = resp.json().get("jobs", [])
        log(f"  剩余 jobs: {len(jobs)}")

        log(f"\nAF3 测试完成 (总耗时 {time.time() - START_TIME:.0f}s)")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 生成报告
# ═══════════════════════════════════════════════════════════════════════════════

def generate_report():
    log("=" * 60)
    log("生成报告...")
    log("=" * 60)

    report_path = os.path.join(os.path.dirname(__file__), "test_report.md")
    name_to_cat = {n: i.get("group", "?") for n, i in SERVICES.items()}

    lines = [
        "# 微服务测试报告",
        "",
        f"**测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**测试序列**: {TEST_PEPTIDE} ({TEST_PEPTIDE_ID})",
        "",
        "## 总览",
        "",
        "| 服务 | 类别 | 结果 | 详细信息 |",
        "|------|------|------|----------|",
    ]

    for name in sorted(test_results.keys()):
        r = test_results[name]
        ok, data = r["ok"], r["data"]
        cat = name_to_cat.get(name, "async")

        if ok:
            detail = _summarize_success(name, data)
            mark = "✅ PASS"
        else:
            detail = _summarize_failure(name, data)
            mark = "❌ FAIL"

        lines.append(f"| {name} | {cat} | {mark} | {detail} |")

    lines.extend([
        "",
        "## 详细结果",
        "",
    ])

    for name in sorted(test_results.keys()):
        r = test_results[name]
        lines.append(f"### {name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(r["data"], indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    lines.extend([
        "## 跳过的服务",
        "",
        "| 服务 | 原因 |",
        "|------|------|",
        "| sasa | PDB 服务（需要 PDB 输入） |",
        "| aggrescan3d | PDB 服务（需要 PDB 输入） |",
        "| pepfold4 | 缺少 Docker 镜像 `pepfold4` |",
        "| temstapro | 仍在下载 ProtT5-XL 模型 (~3GB) |",
        "",
        f"---",
        f"*总耗时: {time.time() - START_TIME:.0f}s*",
    ])

    report = "\n".join(lines)
    with open(report_path, "w") as f:
        f.write(report)
    log(f"报告: {report_path}")


def _summarize_success(name: str, data: dict) -> str:
    if name == "alphafold3_submit":
        return f"job_id={data.get('job_id')}"
    if name == "alphafold3_poll":
        return f"status={data.get('status')}, polls={data.get('polls')}"
    if name == "alphafold3_result":
        return (f"has_structure={bool(data.get('pdb_content'))}, "
                f"confidence={data.get('confidence')}")
    result = data.get("result") or {}
    # 结构预测服务 — 显示 pdb 长度和置信度
    if "pdb_content" in result:
        pdb_len = len(result.get("pdb_content", ""))
        conf = result.get("confidence")
        return f"pdb={pdb_len}B, confidence={conf}"
    score, label = _extract_score_label(data)
    if score is not None:
        return f"score={score:.4f}, label={label}"
    return f"label={label}" if label else "OK"


def _summarize_failure(name: str, data: dict) -> str:
    if name == "alphafold3":
        return data.get("error", "未知错误")
    if name == "alphafold3_result":
        err = data.get("error", "")
        return err[:120] + "..." if len(err) > 120 else err
    result = data.get("result") or {}
    err = (data.get("error") or result.get("error") or
           data.get("details", {}).get("error", "未知错误"))
    return err[:120] + "..." if len(err) > 120 else err


# ═══════════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════════

async def main():
    log("=" * 60)
    log("iGEM-silk 微服务测试")
    log(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"序列: {TEST_PEPTIDE}")
    log(f"跳过: {', '.join(sorted(SKIP_SERVICES))}")
    log(f"GPU串行: {', '.join(sorted(GPU_HEAVY_SERVICES))}")
    log("=" * 60)

    # ── 健康检查 ──
    client = ServiceClient(timeout=30.0)
    all_services = [n for n in SERVICES if n not in SKIP_SERVICES]
    log(f"\n健康检查 ({len(all_services)} 个服务)...")
    health = await client.check_health(all_services)

    available, unavailable = [], []
    for name in all_services:
        h = health.get(name, {})
        (available if h.get("available") else unavailable).append(name)
    log(f"  可用: {len(available)} → {', '.join(available)}")
    for name in unavailable:
        log(f"  ✗ {name}: {health[name].get('error', 'unknown')}")

    available_set = set(available)

    # ── CPU 轻量服务并发测试 ──
    cpu_services = sorted(available_set - GPU_HEAVY_SERVICES)
    await test_lightweight_services(client, cpu_services)

    # ── GPU 重量服务串行测试 ──
    gpu_services = sorted(available_set & GPU_HEAVY_SERVICES - {"alphafold3"})
    await test_gpu_heavy_services(client, gpu_services)
    await client.close()

    # ── AlphaFold3 异步轮询测试 ──
    if "alphafold3" in available_set:
        log("\n⚠  测试 AF3 前确认其他 GPU 服务已停止，否则显存不足")
        await test_alphafold3_async()

    # ── 报告 ──
    generate_report()

    passed = sum(1 for r in test_results.values() if r["ok"])
    failed = sum(1 for r in test_results.values() if not r["ok"])
    log("=" * 60)
    log(f"完成: {passed} passed, {failed} failed / {len(test_results)} total")
    log("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
