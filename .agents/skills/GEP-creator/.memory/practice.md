# GEP-Creator Skill Practice Log

## 2026-04-20 — Skill 创建

**事件**: 为天成创建了 GEP-creator skill，基于 Superlinear Academy EvoMap 课程中的 GEP（Genome Evolution Protocol）概念。

**设计决策**:
- Skill 命名为 `GEP-creator`（与 skill-creator 命名风格一致）
- 三要素结构（Experience / Environment Fingerprint / Audit Record）直接映射 EvoMap/GEP 论文中的基因胶囊设计
- 遵循 skill-creator 的模板规范（SKILL.md + references/ + .memory/）
- 存储路径使用 `~/.gep/capsules/` 作为建议目录，与 OpenClaw workspace 分离

**待验证**:
- 环境指纹（Environment Fingerprint）的粒度把控需要实践反馈
- Audit Record 的"成功率"量化方式在非正式验证场景下可能偏主观
- 胶囊版本管理策略（deprecated + superseded_by）参考了语义化版本思想

**后续建议**:
- 可补充 `gep-evaluator` skill：验证基因胶囊质量
- 可补充 `gep-searcher` skill：在已知胶囊库中检索适合当前任务的胶囊
- 可补充 `gep-evolver` skill：对已有胶囊进行变异 + 选择，迭代优化
