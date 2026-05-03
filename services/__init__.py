"""
services/__init__.py
====================

【模块说明】
-----------
services/ 是整个微服务架构的"大脑"目录，包含了所有服务相关的代码。
这个文件夹就像是一个"办公楼"，里面有不同的"部门"（子模块），
每个部门负责不同的工作。

【子模块结构】
------------
services/
├── template/          # 部门1：服务模板部门
│   └── tool_service.py # 服务模板（所有工具服务都应该"继承"的培训手册）
│
├── orchestrator/       # 部门2：调度中心
│   ├── registry.py     # 工具注册表（所有工具的联系方式本）
│   ├── core.py         # 调度核心（派发任务、收集结果）
│   └── scoring.py      # 评分引擎（多工具结果怎么融合成最终分数）
│
├── api/               # 部门3：前台接待
│   └── main.py        # REST API 服务器（接收外部请求、返回结果）
│
└── tools/             # 部门4：工具实现（具体每个工具服务的代码）
    └── anoxpepred/    # 抗氧化预测工具的示例实现
        └── service.py

【使用说明】
-----------
正常情况下，你不需要修改任何 __init__.py 文件。
如果你要添加新工具，参考 services/tools/anoxpepred/service.py 的写法。
"""

# ============================================================
# 导入说明：
# 这里从 orchestrator 模块导入所有"公开"的类和数据结构。
# 这样做的好处是：如果外部代码想使用 Orchestrator，
# 只需要写 "from services import Orchestrator" 而不需要
# 知道 orchestrator 子模块的存在。
# ============================================================

from .orchestrator import (
    Orchestrator,           # 调度核心：派发任务给各个工具、收集结果
    PredictionRequest,      # 预测请求的数据结构（输入什么肽序列？要调用哪些工具？）
    FusionResult,           # 融合结果（最终的综合评分和详细评分）
    ToolResult,             # 单个工具的预测结果（抗氧化分数、毒性分数等）
    TOOL_REGISTRY,          # 工具注册表（所有可用工具的配置文件）
    ToolConfig,             # 单个工具的配置信息（URL、类型、超时时间等）
    compute_fused_score,    # 计算融合分数的函数
    rank_candidates,        # 对候选肽序列进行排名的函数
)

# __all__ 声明了这个模块"公开"给外部使用的所有名称
# 类似于一个部门的"公开名单"，外部代码只能使用这个名单上的人和物
__all__ = [
    "Orchestrator",         # 调度核心
    "PredictionRequest",    # 输入请求
    "FusionResult",         # 输出结果
    "ToolResult",           # 单工具结果
    "TOOL_REGISTRY",        # 工具配置表
    "ToolConfig",           # 单工具配置
    "compute_fused_score",  # 评分函数
    "rank_candidates",      # 排序函数
]