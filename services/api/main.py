"""
服务启动入口

导入所有模块以注册路由，然后启动 uvicorn 服务器。
"""

from .app import app

# 导入所有模块以注册路由
from . import lifecycle  # noqa: F401
from .prediction import routes as _pred_routes  # noqa: F401
from .tools import routes as _tools_routes  # noqa: F401
from .status import routes as _status_routes  # noqa: F401
from .root import routes as _root_routes  # noqa: F401


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
