"""
iGEM-silk 融合蛋白设计流水线 —— 包入口。

运行方式：
    python -m main        # 以模块方式运行
    igem-silk             # CLI 命令（需 pip install）

本文件是 ``pyproject.toml`` 中 ``[project.scripts]`` 声明的入口点：
    igem-silk = "main:main"
即：导入 ``main`` 包时，调用 ``main()`` 函数。

整个流水线的实际逻辑在 ``main.pipeline.run()`` 中，这里只负责：
1. 导入异步 run 函数
2. 用 ``asyncio.run()`` 启动事件循环并执行
"""

from __future__ import annotations

import asyncio

from main.pipeline import run as _run


def main() -> None:
    """
    流水线入口。

    因为是异步流水线（需要并发调用多个微服务 HTTP 接口），
    这里用 asyncio.run() 创建事件循环并阻塞等待全部任务完成。
    """
    asyncio.run(_run())
