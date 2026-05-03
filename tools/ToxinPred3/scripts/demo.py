#!/usr/bin/env python3
"""
ToxinPred 3.0 功能演示脚本

展示如何使用 toxinpred_features.py 中的 Python API
"""

import os

# 动态添加 toxinpred_features.py 所在目录到 Python 路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # ToxinPred3 目录

import sys
sys.path.insert(0, PROJECT_ROOT)

from toxinpred_features import (
    aac_composition,
    dpc_composition,
    extract_features,
    predict_toxicity,
    batch_predict_from_file,
)


def demo_aac():
    print("\n" + "=" * 60)
    print("1. AAC (氨基酸组成) 特征提取")
    print("=" * 60)

    sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG", "GIGAVLKVLTTGLPALISWIKRKRQQ"]

    aac = aac_composition(sequences)
    print(f"输出维度: {aac.shape}")
    print("\n示例 (前5列):")
    print(aac.iloc[:, :5])


def demo_dpc():
    print("\n" + "=" * 60)
    print("2. DPC (二肽组成) 特征提取")
    print("=" * 60)

    sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG", "GIGAVLKVLTTGLPALISWIKRKRQQ"]

    dpc = dpc_composition(sequences)
    print(f"输出维度: {dpc.shape}")
    print("\n示例 (前5列):")
    print(dpc.iloc[:, :5])


def demo_full_features():
    print("\n" + "=" * 60)
    print("3. 完整特征集 (AAC + DPC = 420维)")
    print("=" * 60)

    sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG", "GIGAVLKVLTTGLPALISWIKRKRQQ"]

    features = extract_features(sequences)
    print(f"特征矩阵维度: {features.shape}")
    print(f"AAC 特征: 20 维")
    print(f"DPC 特征: 400 维")
    print(f"总计: {len(features.columns)} 维")


def demo_toxicity_prediction():
    print("\n" + "=" * 60)
    print("4. 毒性预测 (Model 1: AAC+DPC)")
    print("=" * 60)

    sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG", "GIGAVLKVLTTGLPALISWIKRKRQQ"]

    try:
        results = predict_toxicity(sequences, threshold=0.38, model=1)
        print(results.to_string(index=False))
    except Exception as e:
        print(f"注意: 毒性预测功能暂不可用")
        print(f"原因: scikit-learn 模型版本不兼容")
        print(f"错误: {str(e)[:80]}...")
        print("\n特征提取功能 (AAC/DPC) 正常工作")


def demo_hybrid_prediction():
    print("\n" + "=" * 60)
    print("5. 混合预测 (Model 2: Hybrid = ML + MERCI)")
    print("=" * 60)

    sequences = ["KWKLFKKIGAVLKVL", "MKPPLNAKLVLKPMWIG", "GIGAVLKVLTTGLPALISWIKRKRQQ"]

    try:
        results = predict_toxicity(sequences, threshold=0.38, model=2)
        print(results.to_string(index=False))
    except Exception as e:
        print(f"注意: 混合预测功能暂不可用")
        print(f"原因: scikit-learn 模型版本不兼容")
        print(f"错误: {str(e)[:80]}...")


def demo_batch_prediction():
    print("\n" + "=" * 60)
    print("6. 批量预测 (从 FASTA 文件)")
    print("=" * 60)

    # 创建测试文件
    test_file = os.path.join(PROJECT_ROOT, "test_demo.fa")
    with open(test_file, 'w') as f:
        f.write(">pep1\nKWKLFKKIGAVLKVL\n")
        f.write(">pep2\nMKPPLNAKLVLKPMWIG\n")
        f.write(">pep3\nGIGAVLKVLTTGLPALISWIKRKRQQ\n")

    try:
        results = batch_predict_from_file(test_file, threshold=0.38, model=2)
        print(f"总序列数: {len(results)}")
        print(f"有毒序列: {len(results[results['Prediction'] == 'Toxin'])}")
        print(f"无毒序列: {len(results[results['Prediction'] == 'Non-Toxin'])}")
    except Exception as e:
        print(f"注意: 批量预测功能暂不可用")
        print(f"原因: scikit-learn 模型版本不兼容")
        print(f"错误: {str(e)[:80]}...")
        print("\n但特征提取功能仍然可用！")
    finally:
        # 清理测试文件
        if os.path.exists(test_file):
            os.remove(test_file)


def main():
    print("=" * 60)
    print("ToxinPred 3.0 功能演示")
    print("=" * 60)

    demo_aac()
    demo_dpc()
    demo_full_features()
    demo_toxicity_prediction()
    demo_hybrid_prediction()
    demo_batch_prediction()

    print("\n" + "=" * 60)
    print("演示完成!")
    print("=" * 60)


if __name__ == "__main__":
    main()
