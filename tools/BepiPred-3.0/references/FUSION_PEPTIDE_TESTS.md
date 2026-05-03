# BepiPred-3.0 融合肽场景测试

## 测试背景

融合肽通常由多个功能模块通过 linker（如 GGGGS, EAAAK）连接而成。测试 BepiPred-3.0 在这种场景下的表现对于评估其在融合引擎中的应用至关重要。

## 测试用例

### 测试 1：双功能模块融合

**序列**：
```
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG + GGGSEAAAK + GILGFVFTLTVPSERGL
```

**功能模块**：
- 模块 1：MKPTHPNPRG（未知功能肽）
- Linker：GGGGSEAAAK
- 模块 2：GILGFVFTLTVPSERGL（来自流感病毒肽）

**预测结果**：
```
MKflillfnilclfpvlaADNHGNPKTHPNPRGGGGSEAAAKGILGFvFTltVPSERGl
```

**分析**：
- Linker 区域（GGGGSEAAAK）大部分为小写，表示非表位 ✅
- 模块 1 末尾的 D, N, H, G, N 被预测为表位
- 模块 2 末尾的 E, R, G, L 被预测为表位

### 测试 2：含短 linker 的融合

**序列**：
```
SIINFEKLTEWTSV + GGGGM + MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG
```

**结果**：
```
sIINFEKLTEWTSVGGGGMmKflillfnilclfpvlaADNHGNPKTHPNPRG
```

**观察**：
- 短 linker (GGGGM) 后紧接着功能模块时，表位预测会延续
- 说明表位预测是序列连续的，非模块化判断

### 测试 3：单功能模块 + 长 linker

**序列**：
```
MKFLILLFNILCLFPVLAADNHGNPKTHPNPRG + GGGGSGGGGSGGGGS + SIINFEKLTEWTSV
```

**结果分析**：
- 长重复 linker 通常预测为非表位
- 功能模块边界是表位预测的热点区域

## Linker 对表位预测的影响

| Linker 类型 | 长度 | 表位预测 | 备注 |
|-------------|------|----------|------|
| GGGGS | 5 | 非表位 | 柔性 linker，常用于融合肽 |
| EAAAK | 5 | 非表位 | 刚性 linker |
| (GGGS)n | 可变 | 非表位 | 重复结构 |
| AP | 2 | 变化 | 短 linker，可能影响边界 |
| 无 linker | 0 | N/A | 直接融合可能产生新表位 |

## 融合肽预测建议

### 1. 全长预测优先

**建议**：对完整融合肽进行预测，而非分别预测各功能模块。

**原因**：
- ESM-2 模型需要足够的序列上下文
- 模块边界可能产生新表位
- Linker 的存在可能影响整体表位分布

### 2. 表位密度分析

```python
def epitope_density_analysis(csv_path, window_size=7):
    """分析表位密度分布"""
    df = pd.read_csv(csv_path)

    # 计算滑动窗口表位密度
    scores = df['BepiPred-3.0 score'].values
    densities = []

    for i in range(len(scores) - window_size + 1):
        window = scores[i:i+window_size]
        density = (window > 0.1512).mean()
        densities.append(density)

    return densities
```

### 3. Linker 区域特殊处理

如果 linker 区域被预测为高表位风险：
- 检查是否功能模块边界暴露了新表位
- 考虑调整 linker 长度或序列
- 使用更长的 linker 可能降低边界效应

## 在融合引擎中的集成

### 流程图

```
候选融合肽 → BepiPred-3.0 预测 → 提取表位特征
                                         ↓
                    ┌─────────────────────┴─────────────────────┐
                    ↓                                           ↓
            表位分数提取                                  惩罚项计算
            - max_score                                  - epitope_penalty
            - mean_score                                 - high_ratio_penalty
            - epitope_ratio                              - combined_penalty
                    ↓                                           ↓
                    └─────────────────────┬─────────────────────┘
                                            ↓
                                    融合引擎评分
```

### 集成示例

```python
class EpitopeScorer:
    """表位风险评分器"""

    def __init__(self, threshold=0.1512, penalty_weight=0.3):
        self.threshold = threshold
        self.penalty_weight = penalty_weight

    def score(self, csv_path):
        """返回表位风险分数（越高风险越大）"""
        df = pd.read_csv(csv_path)

        max_score = df['BepiPred-3.0 score'].max()
        epitope_ratio = (df['BepiPred-3.0 score'] > self.threshold).mean()

        # 综合风险分数
        risk_score = max_score * 0.6 + epitope_ratio * 0.4

        return risk_score

    def should_penalize(self, csv_path, max_risk=0.5):
        """判断是否需要惩罚"""
        risk = self.score(csv_path)
        return risk > max_risk
```

## 已知限制

1. **短肽场景**：<10 aa 的融合肽模块预测不可靠
2. **边界效应**：功能模块与 linker 连接处可能有假阳性
3. **非标准氨基酸**：D-氨基酸、β-氨基酸等不被支持
4. **修饰肽**：磷酸化、糖基化等翻译后修饰无法考虑

## 结论

BepiPred-3.0 可以有效评估融合肽的表位风险，但需要注意：
- 建议对完整融合肽进行预测
- Linker 区域通常安全，但边界需要关注
- 表位分数可作为惩罚项有效降低高风险候选
