"""
main.py - TIPred 微服务启动器

Usage:
    python main.py                    # 启动服务（默认端口 8007）
    PORT=8008 python main.py          # 指定端口启动
"""

import os
import uvicorn


def main():
    port = int(os.environ.get("PORT", "8007"))

    print(f"""
╔══════════════════════════════════════════════════════╗
║  TIPred 微服务                                       ║
║  酪氨酸酶抑制肽预测工具 (Stacked Ensemble)          ║
║                                                      ║
║  端口: {port}                                        ║
║  API 文档: http://localhost:{port}/docs              ║
╚══════════════════════════════════════════════════════╝
    """)

    from service import app

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        reload=False
    )


if __name__ == "__main__":
    main()