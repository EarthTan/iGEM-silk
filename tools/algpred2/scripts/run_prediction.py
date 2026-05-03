#!/usr/bin/env python3
"""
AlgPred2 预测脚本 - 提供便捷的预测接口

用法:
    uv run python scripts/run_prediction.py -i input.txt -o output.csv
    uv run python scripts/run_prediction.py -i input.fasta -o output.csv -m 1 -d 2
"""

import argparse
import sys
from algpred2.python_scripts.algpred2 import main as algpred_main


def parse_args():
    parser = argparse.ArgumentParser(
        description='AlgPred2 过敏原性风险预测',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('-i', '--input', required=True, help='输入文件 (FASTA 或纯序列文本)')
    parser.add_argument('-o', '--output', default='output.csv', help='输出 CSV 文件')
    parser.add_argument('-t', '--threshold', type=float, default=0.3, help='阈值 (0-1)')
    parser.add_argument('-m', '--model', type=int, default=1, choices=[1, 2],
                        help='模型: 1=Allergen, 2=Non-Allergen')
    parser.add_argument('-d', '--display', type=int, default=2, choices=[1, 2],
                        help='显示: 1=Allergen, 2=所有肽')
    return parser.parse_args()


def main():
    args = parse_args()

    # 设置 sys.argv 以便 algpred2.main() 使用
    sys.argv = [
        'algpred2',
        '-i', args.input,
        '-o', args.output,
        '-t', str(args.threshold),
        '-m', str(args.model),
        '-d', str(args.display)
    ]

    print(f"Running AlgPred2 prediction...")
    print(f"Input: {args.input}")
    print(f"Output: {args.output}")
    print(f"Threshold: {args.threshold}")
    print(f"Model: {'Allergen' if args.model == 1 else 'Non-Allergen'}")
    print(f"Display: {'All' if args.display == 2 else 'Allergen only'}")
    print("-" * 50)

    algpred_main()


if __name__ == '__main__':
    main()