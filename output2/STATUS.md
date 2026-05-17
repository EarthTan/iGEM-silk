# output2 Pipeline 状态

> 最后更新: 2026-05-17 20:35

## 当前进度

| 阶段 | 状态 | 备注 |
|------|------|------|
| Step 0: 数据整合 | ✅ 完成 | 1,055,116 条清洗完成 |
| Round 1: 轻量评分 | ✅ 完成 | AnOxPePred + AlgPred2, 886s |
| Round 2: 分选+安全评分 | ✅ 完成 | top25K+bottom25K, 5 服务完整, 3755s |
| Round 3: 重服务评分 | ✅ 完成 | TemStaPro 50K + BepiPred3 15K, 7 服务, 3891s |
| Round 4: 枚举+Construct | ✅ 完成 | 150 constructs (90 Top + 60 Bottom), 5 服务完整 |
| Round 5: 3D 结构 | ⏳ 待运行 | ESMFold + OmegaFold |
| Round 6: PDB 评估 | ⏳ 待运行 | SASA + Aggrescan3D |
| Round 7: 最终输出 | ⏳ 待运行 | 双通道排名 |

## Pipeline 变更记录

v2 关键变更（vs 原 stages2）：
- Round 1 不跑 ToxinPred3（105 万条太慢 ~22h），改为 Round 2 对 50K 补跑
- Round 2 按纯 anoxpepred 分选 top25K + bottom25K，非加权综合分
- Round 3 在 50K 上跑，保留 channel 标签
- 全流程双通道（top/bottom）各自输出最终排名

详见 `main/stages2/PLAN2.md`。

## 输出目录结构

```
output2/
├── STATUS.md
├── step00_integrate/       ← 数据整合
│   └── final/cleaned.csv
├── round01_lightweight/    ← AnOxPePred + AlgPred2
│   └── final/
│       ├── all_scored.csv  ← 105 万条全量评分
│       └── top50k.csv      ← 加权分排序（仅参考）
├── round02_scoring/        ← 分选 + 安全评分
│   └── final/
│       ├── all_50k.csv     ← 50K 条（5 服务分 + 综合分 + channel）
│       ├── top25k.csv
│       └── bottom25k.csv
└── round03_heavy/          ← TemStaPro 预筛 + BepiPred3
    └── final/
        ├── all_scored.csv  ← 50K 条（7 服务分 + channel）
        ├── top80.csv       ← Top 通道前 80
        ├── bottom10.csv    ← Bottom 通道阴性对照
        ├── danger_list.csv ← 201 条高危
        └── trajectory.csv  ← 跨轮排名轨迹
```
