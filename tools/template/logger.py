"""
Logger — 所有微服务的统一日志配置。

用法:
    from tools.template.logger import get_logger
    logger = get_logger("myservice")
    logger.info("Hello %s", value)

输出:
    - 控制台:  时间 | 级别 | 服务名 | 消息
    - 文件:    tools/logs/<name>.log (自动轮转, 每 10 MB, 保留 5 个备份)
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """获取或创建带文件和控制台 handler 的 logger。

    对同一个 ``name`` 重复调用返回同一个 logger（不会重复添加 handler）。
    每个微服务在 ``load_model()`` 或 ``__init__`` 中调用一次即可。
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    fmt = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # 文件 handler — 不可写时静默退化到仅控制台
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            LOG_DIR / f"{name}.log",
            maxBytes=10_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except (OSError, PermissionError):
        pass

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger
