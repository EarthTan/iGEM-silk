#!/usr/bin/env python3
"""
main.py
=======
iGEM-silk 命令行入口。

用法：
-----
# 单序列预测
python main.py predict "YVPLPNVPQG"

# 批量预测（从文件）
python main.py predict-batch sequences.fasta

# 启动 API 服务
python main.py serve

# 列出所有工具
python main.py tools
"""

import argparse
import asyncio
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="iGEM-silk 丝素蛋白融合功能肽设计平台",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # ── predict 命令 ───────────────────────────────────────
    predict_parser = subparsers.add_parser("predict", help="单序列预测")
    predict_parser.add_argument("sequence", help="氨基酸序列")
    predict_parser.add_argument("--peptide-id", "-i", help="肽 ID")
    predict_parser.add_argument("--tools", "-t", nargs="+", help="指定工具列表")

    # ── predict-batch 命令 ────────────────────────────────
    batch_parser = subparsers.add_parser("predict-batch", help="批量预测")
    batch_parser.add_argument("input", help="输入文件（FASTA 或 CSV）")
    batch_parser.add_argument("--output", "-o", help="输出文件路径")
    batch_parser.add_argument("--tools", "-t", nargs="+", help="指定工具列表")
    batch_parser.add_argument("--top-k", "-k", type=int, default=50, help="返回 top k 结果")

    # ── serve 命令 ─────────────────────────────────────────
    serve_parser = subparsers.add_parser("serve", help="启动 API 服务")
    serve_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    serve_parser.add_argument("--port", "-p", type=int, default=8000, help="监听端口")

    # ── tools 命令 ────────────────────────────────────────
    subparsers.add_parser("tools", help="列出所有可用工具")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    # ── 执行命令 ─────────────────────────────────────────
    if args.command == "predict":
        asyncio.run(cmd_predict(args.sequence, args.peptide_id, args.tools))
    elif args.command == "predict-batch":
        asyncio.run(cmd_predict_batch(args.input, args.output, args.tools, args.top_k))
    elif args.command == "serve":
        cmd_serve(args.host, args.port)
    elif args.command == "tools":
        cmd_list_tools()


async def cmd_predict(sequence: str, peptide_id: str | None, tools: list[str] | None):
    """执行单序列预测"""
    from services.orchestrator import Orchestrator, PredictionRequest

    async with Orchestrator() as orchestrator:
        result = await orchestrator.predict_single(
            PredictionRequest(sequence=sequence, peptide_id=peptide_id, tools=tools)
        )

        print(f"\n=== 预测结果 ===")
        print(f"序列: {result.sequence}")
        print(f"融合分数: {result.fused_score:.4f}" if result.fused_score else "融合分数: N/A")
        print(f"融合标签: {result.fused_label}")
        print(f"总延迟: {result.total_latency_ms:.0f}ms")
        print(f"\n各工具结果:")
        for tr in result.tool_results:
            status = "✅" if tr.error is None else "❌"
            print(f"  {status} {tr.tool_name}: score={tr.score}, label={tr.label}, latency={tr.latency_ms:.0f}ms")


async def cmd_predict_batch(input_file: str, output_file: str | None, tools: list[str] | None, top_k: int):
    """执行批量预测"""
    from services.orchestrator import Orchestrator, PredictionRequest
    from Bio import SeqIO

    # 读取输入文件
    sequences = []
    peptide_ids = []

    input_path = Path(input_file)
    if input_path.suffix.lower() in [".fasta", ".fa", ".faa"]:
        # FASTA 格式
        for record in SeqIO.parse(input_path, "fasta"):
            sequences.append(str(record.seq))
            peptide_ids.append(record.id)
    elif input_path.suffix.lower() == ".csv":
        # CSV 格式（需要 id, sequence 列）
        import pandas as pd
        df = pd.read_csv(input_path)
        if "sequence" not in df.columns:
            print("ERROR: CSV 必须包含 'sequence' 列")
            return
        sequences = df["sequence"].tolist()
        peptide_ids = df.get("id", [f"pep_{i}" for i in range(len(sequences))]).tolist()
    else:
        print(f"ERROR: 不支持的输入文件格式: {input_path.suffix}")
        return

    print(f"读取到 {len(sequences)} 条序列")

    # 执行批量预测
    async with Orchestrator() as orchestrator:
        requests = [
            PredictionRequest(sequence=seq, peptide_id=pid)
            for seq, pid in zip(sequences, peptide_ids)
        ]
        results = await orchestrator.predict_batch(requests, tools=tools)

    # 排序
    from services.orchestrator import rank_candidates
    ranked = rank_candidates(results, top_k=top_k)

    # 输出
    if output_file:
        import pandas as pd
        df = pd.DataFrame([
            {
                "peptide_id": r.peptide_id,
                "sequence": r.sequence,
                "fused_score": r.fused_score,
                "fused_label": r.fused_label,
                "total_latency_ms": r.total_latency_ms
            }
            for r in ranked
        ])
        df.to_csv(output_file, index=False)
        print(f"结果已保存到: {output_file}")
    else:
        print(f"\n=== Top {len(ranked)} 结果 ===")
        for r in ranked:
            print(f"  {r.peptide_id}: score={r.fused_score:.4f}, label={r.fused_label}")


def cmd_serve(host: str, port: int):
    """启动 API 服务"""
    import uvicorn
    from services.api.main import app

    print(f"启动 iGEM-silk Orchestrator API ...")
    print(f"文档: http://localhost:{port}/docs")
    uvicorn.run(app, host=host, port=port)


def cmd_list_tools():
    """列出所有工具"""
    from services.orchestrator.registry import TOOL_REGISTRY

    print("\n=== 可用工具 ===")
    print(f"{'名称':<15} {'URL':<25} {'类型':<20} {'优先级':<8} {'GPU':<6}")
    print("-" * 80)
    for name, cfg in TOOL_REGISTRY.items():
        print(f"{name:<15} {cfg.url:<25} {cfg.type:<20} {cfg.priority:<8} {cfg.requires_gpu:<6}")


if __name__ == "__main__":
    main()