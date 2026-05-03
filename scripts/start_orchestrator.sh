#!/usr/bin/env bash
# ============================================================================
# scripts/start_orchestrator.sh
# ============================================================================
# 启动 Orchestrator API 服务
#
# 用法：
#   ./scripts/start_orchestrator.sh [--port PORT] [--host HOST]
#
# 示例：
#   ./scripts/start_orchestrator.sh --port 8000 --host 0.0.0.0
# ============================================================================

set -e

PORT="${TOOL_PORT:-8000}"
HOST="${TOOL_HOST:-0.0.0.0}"

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

echo "═══════════════════════════════════════════════════════════"
echo "  iGEM-silk Orchestrator API"
echo "  端口: $PORT"
echo "  地址: $HOST"
echo "═══════════════════════════════════════════════════════════"

# 检查依赖
if ! uv pip show fastapi > /dev/null 2>&1; then
    echo "ERROR: fastapi 未安装"
    echo "运行: uv add fastapi httpx pydantic uvicorn"
    exit 1
fi

# 启动服务
exec uv run uvicorn services.api.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level info