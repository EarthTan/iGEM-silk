#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TIPred 训练示例脚本

使用模拟数据演示完整的训练和预测流程。
实际使用时，请替换为真实的 TIP/非 TIP 数据。
"""

import sys
sys.path.insert(0, '.')
from scripts.tipredictor_full import TIPredictorMVFF, load_fasta
import pandas as pd
import numpy as np

# 示例训练数据
# 注意：这些是模拟数据，实际训练需要使用实验验证的 TIP/非 TIP 数据

# TIP 样本（酪氨酸酶抑制肽示例）
tip_sequences = [
    'YGGFL',      # 脑啡肽，有报道显示酪氨酸酶抑制活性
    'GHK',        # 铜肽，有美白功效
    'PAL',        # 短肽
    'KYGGF',      # 酪氨酸-rich
    'YGGFY',      # 双酪氨酸
    'WHW',        # 色氨酸-rich
    'FWY',        # 芳香族氨基酸
    'YY',         # 双酪氨酸
    'YGY',        # 酪氨酸-glycine-酪氨酸
    'KYK',        # 赖氨酸 - 酪氨酸
    'AYGFL',      # 类似脑啡肽
    'WY',         # 色氨酸 - 酪氨酸
    'YYG',        # 双酪氨酸-glycine
    'YW',         # 酪氨酸 - 色氨酸
    'FY',         # 苯丙氨酸 - 酪氨酸
]

# 非 TIP 样本
non_tip_sequences = [
    'RRRRR',      # 精氨酸-rich，通常无 TIP 活性
    'DDDDD',      # 天冬氨酸-rich
    'KKKKK',      # 赖氨酸-rich
    'EEEEE',      # 谷氨酸-rich
    'PPPPP',      # 脯氨酸-rich
    'GGGGG',      # glycine-rich
    'AAAAA',      # 丙氨酸-rich
    'VVVVV',      # 缬氨酸-rich
    'LLLLL',      # 亮氨酸-rich
    'IIIII',      # 异亮氨酸-rich
    'RRRK',       # 碱性肽
    'DDDE',       # 酸性肽
    'PPPG',       # 脯氨酸-glycine
    'AAA',        # 短丙氨酸肽
    'RRR',        # 短精氨酸肽
]

# 准备训练数据（重复以满足最小样本要求）
sequences = (tip_sequences + non_tip_sequences) * 2
labels = [1] * len(tip_sequences) * 2 + [0] * len(non_tip_sequences) * 2

print("=== TIPred 训练示例 ===\n")
print(f"TIP 样本数：{len(tip_sequences)}")
print(f"非 TIP 样本数：{len(non_tip_sequences)}")
print(f"总样本数：{len(sequences)}\n")

# 创建并训练预测器
predictor = TIPredictorMVFF(model_type='stacked')  # 使用堆叠集成模型

print("正在训练模型...")
results = predictor.train(sequences, labels, test_size=0.3)

print("\n=== 训练结果 ===")
print(f"训练集大小：{results['train_size']}")
print(f"测试集大小：{results['test_size']}")
print(f"特征维度：{results['feature_dim']}")
print(f"测试集准确率：{results['test_accuracy']:.4f}")
print(f"测试集 MCC: {results['test_mcc']:.4f}")
print(f"测试集 AUC: {results['test_auc']:.4f}")

# 保存模型
model_path = 'tip_model.pkl'
predictor.save(model_path)
print(f"\n模型已保存到：{model_path}")

# 预测新序列
print("\n=== 预测示例 ===")
test_seqs = [
    'YGGFL',      # 已知 TIP
    'RRRRR',      # 已知非 TIP
    'ACDEFGHIK',  # 未知
    'LMNPQRSTVWY', # 未知
    'YYGG',       # 酪氨酸-rich
    'KRRR',       # 碱性肽
]

probs = predictor.predict(test_seqs)
classes = predictor.predict_class(test_seqs)

print("\n预测结果:")
for seq, prob, cls in zip(test_seqs, probs, classes):
    status = "✓ TIP" if cls == 1 else "✗ non-TIP"
    print(f"  {seq:15s} → 概率：{prob:.3f} → {status}")

# 批量预测演示
print("\n=== 批量预测演示 ===")
batch_seqs = ['YGGFL', 'GHK', 'PAL'] * 100  # 300 条序列
import time
start = time.time()
batch_probs = predictor.predict(batch_seqs)
elapsed = time.time() - start
print(f"处理 {len(batch_seqs)} 条序列耗时：{elapsed:.3f}秒")
print(f"平均速度：{len(batch_seqs)/elapsed:.1f} 序列/秒")

print("\n=== 完成 ===")
print("提示：实际使用时，请使用实验验证的 TIP/非 TIP 数据重新训练模型。")
