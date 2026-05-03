#!/usr/bin/env python3
"""
MLCPP 细胞穿透肽筛选管道

本脚本使用MLCPP工具进行细胞穿透肽（CPP）的高通量筛选。
支持在线和离线双模式运行，单个肽预测、批量处理和结果可视化。

使用方法：
    python cpp_screening_pipeline.py --input peptides.fasta --output results.csv
    python cpp_screening_pipeline.py --sequence "RKKRRQRRR" --mode online
"""

import argparse
import sys
import os
from pathlib import Path
import pandas as pd
import numpy as np

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from tools.mlcpp_integration import MLCPPIntegration
    MLCPP_AVAILABLE = True
except ImportError:
    print("警告: MLCPP集成模块未找到，使用模拟模式")
    MLCPP_AVAILABLE = False

def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='MLCPP细胞穿透肽筛选管道')
    
    # 输入选项
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--sequence', type=str, help='单个肽序列')
    input_group.add_argument('--input', type=str, help='输入文件路径 (FASTA或CSV格式)')
    input_group.add_argument('--list', type=str, nargs='+', help='肽序列列表')
    
    # 输出选项
    parser.add_argument('--output', type=str, default='mlcpp_results.csv', 
                       help='输出文件路径 (默认: mlcpp_results.csv)')
    parser.add_argument('--format', type=str, choices=['csv', 'json', 'excel'], 
                       default='csv', help='输出格式 (默认: csv)')
    
    # 预测选项
    parser.add_argument('--mode', type=str, default='online',
                       choices=['online', 'offline', 'auto'],
                       help='运行模式 (默认: online)')
    parser.add_argument('--threshold', type=float, default=0.5,
                       help='分类阈值 (默认: 0.5)')
    parser.add_argument('--calculate-features', action='store_true',
                       help='计算肽的物理化学特征')
    
    # 其他选项
    parser.add_argument('--visualize', action='store_true',
                       help='生成可视化图表')
    parser.add_argument('--verbose', action='store_true',
                       help='显示详细输出')
    parser.add_argument('--timeout', type=int, default=30,
                       help='在线模式超时时间(秒) (默认: 30)')
    
    return parser.parse_args()

def load_sequences(input_file):
    """从文件加载序列"""
    if input_file.endswith('.fasta') or input_file.endswith('.fa'):
        return load_fasta(input_file)
    elif input_file.endswith('.csv'):
        return load_csv(input_file)
    else:
        raise ValueError(f"不支持的文件格式: {input_file}")

def load_fasta(fasta_file):
    """加载FASTA文件"""
    sequences = {}
    current_id = None
    current_seq = []
    
    with open(fasta_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('>'):
                if current_id is not None:
                    sequences[current_id] = ''.join(current_seq)
                current_id = line[1:].split()[0]
                current_seq = []
            else:
                current_seq.append(line)
        
        if current_id is not None:
            sequences[current_id] = ''.join(current_seq)
    
    return sequences

def load_csv(csv_file):
    """加载CSV文件"""
    df = pd.read_csv(csv_file)
    
    # 检查列名
    if 'sequence' in df.columns and 'id' in df.columns:
        sequences = dict(zip(df['id'], df['sequence']))
    elif 'sequence' in df.columns:
        sequences = {f"peptide_{i}": seq for i, seq in enumerate(df['sequence'])}
    elif len(df.columns) >= 2:
        sequences = {str(row[0]): str(row[1]) for _, row in df.iterrows()}
    else:
        raise ValueError("CSV文件必须包含'sequence'列或至少两列")
    
    return sequences

def initialize_predictor(args):
    """初始化预测器"""
    if MLCPP_AVAILABLE:
        try:
            predictor = MLCPPIntegration(
                mode=args.mode,
                verbose=args.verbose,
                timeout=args.timeout
            )
            
            # 检查连接状态
            if args.mode == 'online':
                status = predictor.check_status()
                print(f"MLCPP在线模式状态: {status}")
            
            print(f"使用MLCPP {args.mode}模式")
            return predictor
            
        except Exception as e:
            print(f"MLCPP初始化失败: {e}")
            print("回退到模拟模式")
            return MockPredictor()
    else:
        print("使用模拟模式 (MLCPP集成模块未找到)")
        return MockPredictor()

class MockPredictor:
    """模拟预测器，用于测试"""
    def __init__(self, mode='offline', verbose=False, timeout=30):
        self.mode = mode
        self.verbose = verbose
        self.timeout = timeout
    
    def predict_single(self, sequence, peptide_id=None, threshold=0.5, calculate_features=False):
        """模拟单个肽预测"""
        class MockResult:
            def __init__(self, sequence, peptide_id):
                import random
                self.sequence = sequence
                self.peptide_id = peptide_id or f"peptide_{random.randint(1000, 9999)}"
                self.cell_penetrating_probability = random.uniform(0, 1)
                self.predicted_class = 'CPP' if self.cell_penetrating_probability > threshold else 'Non-CPP'
                self.confidence = random.uniform(0.7, 0.95)
                
                if calculate_features:
                    self.features = {
                        'length': len(sequence),
                        'molecular_weight': len(sequence) * 110.0,
                        'charge': random.uniform(-5, 5),
                        'hydrophobicity': random.uniform(-1, 1)
                    }
        
        return MockResult(sequence, peptide_id)
    
    def predict_batch(self, sequences, threshold=0.5, calculate_features=False):
        """模拟批量预测"""
        results = {}
        for peptide_id, sequence in sequences.items():
            results[peptide_id] = self.predict_single(
                sequence=sequence,
                peptide_id=peptide_id,
                threshold=threshold,
                calculate_features=calculate_features
            )
        return results
    
    def check_status(self):
        """检查状态"""
        return "模拟模式 - 正常"

def predict_single_sequence(predictor, sequence, peptide_id, args):
    """预测单个肽序列"""
    print(f"预测肽序列: {peptide_id}")
    print(f"序列: {sequence}")
    print(f"长度: {len(sequence)} 个氨基酸")
    
    try:
        result = predictor.predict_single(
            sequence=sequence,
            peptide_id=peptide_id,
            threshold=args.threshold,
            calculate_features=args.calculate_features
        )
        
        print(f"细胞穿透概率: {result.cell_penetrating_probability:.3f}")
        print(f"预测类别: {result.predicted_class}")
        
        if hasattr(result, 'confidence') and result.confidence is not None:
            print(f"置信度: {result.confidence:.3f}")
        
        if hasattr(result, 'features') and args.calculate_features:
            print("物理化学特征:")
            for feature, value in result.features.items():
                if isinstance(value, float):
                    print(f"  {feature}: {value:.3f}")
                else:
                    print(f"  {feature}: {value}")
        
        return result
        
    except Exception as e:
        print(f"预测失败: {e}")
        return None

def predict_batch_sequences(predictor, sequences, args):
    """批量预测肽序列"""
    print(f"批量预测 {len(sequences)} 个肽序列")
    print(f"运行模式: {args.mode}")
    
    try:
        results = predictor.predict_batch(
            sequences=sequences,
            threshold=args.threshold,
            calculate_features=args.calculate_features
        )
        
        print(f"成功预测 {len(results)} 个序列")
        
        # 统计结果
        cpp_count = sum(1 for r in results.values() 
                       if r.predicted_class == 'CPP')
        non_cpp_count = len(results) - cpp_count
        
        print(f"细胞穿透肽: {cpp_count} 个")
        print(f"非细胞穿透肽: {non_cpp_count} 个")
        
        if cpp_count > 0:
            avg_prob = np.mean([r.cell_penetrating_probability for r in results.values() 
                               if r.predicted_class == 'CPP'])
            print(f"平均细胞穿透概率: {avg_prob:.3f}")
        
        return results
        
    except Exception as e:
        print(f"批量预测失败: {e}")
        return None

def save_results(results, output_file, output_format):
    """保存结果到文件"""
    if not results:
        print("没有结果可保存")
        return
    
    # 转换为DataFrame
    data = []
    for peptide_id, result in results.items():
        row = {
            'peptide_id': peptide_id,
            'sequence': getattr(result, 'sequence', ''),
            'cell_penetrating_probability': result.cell_penetrating_probability,
            'predicted_class': result.predicted_class
        }
        
        if hasattr(result, 'confidence') and result.confidence is not None:
            row['confidence'] = result.confidence
        
        if hasattr(result, 'features'):
            for feature, value in result.features.items():
                row[f'feature_{feature}'] = value
        
        data.append(row)
    
    df = pd.DataFrame(data)
    
    # 保存文件
    if output_format == 'csv':
        df.to_csv(output_file, index=False)
        print(f"结果已保存到: {output_file}")
    elif output_format == 'json':
        df.to_json(output_file, orient='records', indent=2)
        print(f"结果已保存到: {output_file}")
    elif output_format == 'excel':
        df.to_excel(output_file, index=False)
        print(f"结果已保存到: {output_file}")

def generate_visualization(results, output_prefix):
    """生成可视化图表"""
    try:
        import matplotlib.pyplot as plt
        import seaborn as sns
        
        # 准备数据
        data = []
        for peptide_id, result in results.items():
            data.append({
                'peptide_id': peptide_id,
                'probability': result.cell_penetrating_probability,
                'class': result.predicted_class,
                'length': len(result.sequence)
            })
        
        df = pd.DataFrame(data)
        
        # 1. 概率分布直方图
        plt.figure(figsize=(10, 6))
        plt.hist(df['probability'], bins=20, alpha=0.7, color='lightgreen', edgecolor='black')
        plt.axvline(x=0.5, color='red', linestyle='--', label='阈值 (0.5)')
        plt.xlabel('细胞穿透概率')
        plt.ylabel('频数')
        plt.title('细胞穿透肽概率分布')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.savefig(f'{output_prefix}_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. 类别分布饼图
        plt.figure(figsize=(8, 8))
        class_counts = df['class'].value_counts()
        colors = ['lightcoral', 'lightgreen'] if len(class_counts) == 2 else ['lightblue']
        plt.pie(class_counts.values, labels=class_counts.index, autopct='%1.1f%%',
                colors=colors, startangle=90)
        plt.title('细胞穿透肽类别分布')
        plt.savefig(f'{output_prefix}_classes.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. 概率与序列长度散点图
        plt.figure(figsize=(10, 6))
        colors = ['red' if c == 'CPP' else 'blue' for c in df['class']]
        plt.scatter(df['length'], df['probability'], c=colors, alpha=0.6, edgecolors='black')
        plt.axhline(y=0.5, color='gray', linestyle='--', alpha=0.5)
        plt.xlabel('序列长度 (氨基酸数)')
        plt.ylabel('细胞穿透概率')
        plt.title('序列长度与细胞穿透概率关系')
        plt.grid(True, alpha=0.3)
        
        # 添加图例
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor='red', alpha=0.6, label='CPP'),
            Patch(facecolor='blue', alpha=0.6, label='Non-CPP')
        ]
        plt.legend(handles=legend_elements)
        
        plt.savefig(f'{output_prefix}_length_vs_probability.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"可视化图表已保存到: {output_prefix}_*.png")
        
    except ImportError:
        print("警告: matplotlib或seaborn未安装，跳过可视化")
    except Exception as e:
        print(f"可视化生成失败: {e}")

def main():
    """主函数"""
    args = parse_arguments()
    
    # 初始化预测器
    predictor = initialize_predictor(args)
    
    # 加载序列
    sequences = {}
    
    if args.sequence:
        sequences = {'single_peptide': args.sequence}
        print(f"分析单个肽序列: {args.sequence}")
        
    elif args.input:
        if not os.path.exists(args.input):
            print(f"错误: 输入文件不存在: {args.input}")
            return 1
        
        try:
            sequences = load_sequences(args.input)
            print(f"从文件加载 {len(sequences)} 个序列: {args.input}")
        except Exception as e:
            print(f"加载文件失败: {e}")
            return 1
        
    elif args.list:
        sequences = {f'peptide_{i}': seq for i, seq in enumerate(args.list)}
        print(f"分析 {len(sequences)} 个肽序列")
    
    # 执行预测
    results = {}
    
    if len(sequences) == 1:
        # 单个序列预测
        peptide_id, sequence = list(sequences.items())[0]
        result = predict_single_sequence(predictor, sequence, peptide_id, args)
        if result:
            results[peptide_id] = result
    else:
        # 批量预测
        results = predict_batch_sequences(predictor, sequences, args)
    
    # 保存结果
    if results:
        save_results(results, args.output, args.format)
        
        # 生成可视化
        if args.visualize:
            output_prefix = os.path.splitext(args.output)[0]
            generate_visualization(results, output_prefix)
        
        print(f"\n分析完成!")
        print(f"总序列数: {len(sequences)}")
        print(f"成功预测: {len(results)}")
        print(f"运行模式: {args.mode}")
        
        if len(results) > 0:
            cpp_count = sum(1 for r in results.values() 
                          if r.predicted_class == 'CPP')
            print(f"细胞穿透肽数量: {cpp_count} ({cpp_count/len(results)*100:.1f}%)")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())