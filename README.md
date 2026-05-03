# 项目约定

1. 项目的根目录名称是 `iGEM-silk/`,以后统一用 `./` 表示
2. 项目的python环境使用 uv 管理，总的虚拟环境安装在 `./venv`。项目的python环境使用 `pyproject.toml` 来管理。`tools/`下的微服务每个有各自的环境。
3. 本项目统一使用 `docker` 来运行、测试、打包。为了便于迁移，不使用愚蠢的`conda`来管理环境。 





# Agent 行为守则

1. Never use subagent
2. 