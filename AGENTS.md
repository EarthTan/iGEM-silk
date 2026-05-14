# 项目约定

1. 项目的根目录名称是 `iGEM-silk/`,以后统一用 `./` 表示

2. 项目的python环境使用 uv 管理，总的虚拟环境安装在 `./venv`。项目的python环境使用 `pyproject.toml` 来管理。`tools/`下的微服务每个有各自的环境，通过 FastAPI 的方式提供微服务，暴露端口提供给核心功能使用。

3. 本项目使用聪慧的 `uv` 和 `pyproject.toml` 来管理python环境，而不使用愚蠢的 `pip` 或者 `requirements.md`。

   


# Agent 须知

1. Never use subagent, do it yourself, step by step.
2. `.agents/learnings` 存储了学到的经验和教训，值得参考
3. `.agents/skills` 是本项目常用的skill，其中就包括了 "GEP-creator"
