---
name: 结构预测置信度级联对下游 PDB 评估的影响 v1.0
author: Claude Code
created: 2026-05-14
version: 1.0.0
tags: [pipeline, confidence, esmfold, plddt, sasa, structure-prediction]
validated: true
---

# Gene Capsule: 结构预测置信度级联对下游 PDB 评估的影响

## Experience

**问题类型**: ESMFold 对富含重复序列的长蛋白（丝素蛋白融合 construct）的 pLDDT 置信度普遍低于 0.31，直接导致下游 SASA/Aggrescan3D 的评估结果不可靠——不是工具算错了，而是输入结构不可靠。

**核心策略**:
1. **置信度级联效应**：3D 预测的置信度向下游逐级传递——如果 ESMFold pLDDT 低，所有基于 PDB 的分析（SASA 暴露度、聚集倾向、分子动力学）都建立在不稳定的结构上，结论只能作为参考而非定量依据
2. **pLDDT 阈值检查机制**：在阶段五（ESMFold）输出时就评估置信度，如果全部 < 0.5 应给出警告，提示下游评估结果可靠性受限。在阶段六引入 "pLDDT 置信度带"——SASA 评分附带 pLDDT 范围供参考
3. **识别根本原因而非工具问题**：ESMFold 对 (a) 长度 > 400 aa、(b) 序列高度重复 (GAGAGS)n、(c) intrinsically disordered 区域的预测天生不可靠——这是蛋白本身的性质，非 ESMFold 的问题
4. **分域策略**：将长融合蛋白分割为独立结构域（功能肽+部分 Linker，<100 aa）分别预测，避免长序列和重复序列对预测的干扰

**关键参数**:

| 蛋白特征 | ESMFold 表现 | 置信度阈值 |
|----------|-------------|-----------|
| 球蛋白 < 400 aa | 良好 | pLDDT ≥ 0.7 可信 |
| 多结构域蛋白 | 中等 | pLDDT 0.5-0.7 参考 |
| 重复/固有无序 | 差 | pLDDT < 0.5 不可靠 |
| **丝素融合 (>380 aa, 重复)** | **差** | **pLDDT ≤ 0.31** |

**典型指标**:
- ESMFold pLDDT < 0.5 → SASA 暴露度偏高的假阳性风险增大（未折叠区域在计算中被迫暴露）
- ESMFold pLDDT < 0.5 → Aggrescan3D 聚集风险可能被低估（结构松散导致埋藏热点暴露不足）

## Environment Fingerprint

- **任务域**: 计算生物学流水线，融合蛋白/重复序列蛋白的结构预测与下游评估
- **输入特征**: 丝素蛋白级融合 construct，包含高度重复的 (GAGAGS)n 序列，长度 380-440 aa
- **约束条件**: 默认使用 ESMFold（快速，~2min/construct），AlphaFold3 更准但更慢且需外部 API
- **不适用**:
  - 球蛋白/酶（ESMFold 对其准确度高）
  - 短肽独立预测（<100 aa，ESMFold 对其 pLDDT 较高）
  - 仅需 SASA/A3D 评分的相对排名而非绝对定量

## Audit Record

- **验证方式**: iGEM-silk 阶段五（90 construct ESMFold）+ 阶段六（SASA + A3D）全量运行
- **测试用例**:
  1. 90 个 construct ESMFold 预测 → pLDDT mean=0.281, max=0.307, all < 0.5
  2. SASA 基于低置信度结构计算 → 95.6% 判定为 "exposed"（区分度不足）
  3. Aggrescan3D 基于低置信度结构计算 → 全部 low-moderate（无法确定真伪）
  4. 修复 ESMFold bug 后重跑 → pLDDT mean 0.2806 → 0.2810（微幅提升，根本原因仍是序列性质）
- **成功率**: 不适用（这不是"修复"，而是揭示计算方法的固有局限性）
- **局限性**: 分割结构域预测需要重新设计 construct 构造逻辑，且 Linker 区域的分割点选择会影响结果

## Usage

- **触发条件**: ESMFold 预测结果中 pLDDT 全部 < 0.5；或下游 SASA/Aggrescan3D 评分缺乏区分度
- **调用方式**:
  1. 在阶段五脚本中添加 pLDDT 质量门控：`if mean_plddt < 0.5: logger.warning("结构置信度低，下游评估仅作参考")`
  2. 在阶段六输出中标注 SASA/A3D 的 pLDDT 置信度范围
  3. 如果是重复蛋白序列，考虑分割结构域后独立预测
- **注意事项**: 不要因为 pLDDT 低就否定 ESMFold——这是 tool for the right job 的问题，不是工具质量问题。丝素蛋白的构象灵活性是其天然属性，实验上也需要通过 CD/WAXS 等表征确定二级结构
