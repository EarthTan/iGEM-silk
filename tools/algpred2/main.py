"""
main.py - AlgPred2 微服务启动器

Usage:
    python main.py                    # 启动服务（默认端口 8008）
    PORT=8009 python main.py          # 指定端口

Port 端口分配（参考 services/orchestrator/registry.py）：
    8008: algpred2
"""

import os
import uvicorn


def main():
    port = int(os.environ.get("PORT", "8008"))

    print(f"""
╔══════════════════════════════════════════════════════╗
║  AlgPred2 微服务                                      ║
║  过敏原性风险预测工具（随机森林模型）                 ║
║                                                      ║
║  端口: {port}                                        ║
║  API 文档: http://localhost:{port}/docs              ║
╚══════════════════════════════════════════════════════╝
    """)

    # 直接导入 app 对象（不是字符串）
    from service import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )


if __name__ == "__main__":
    main()