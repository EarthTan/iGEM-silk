#!/usr/bin/env bash
# ============================================================================
# scripts/start_tool.sh
# ============================================================================
# 启动单个工具微服务
#
# 用法：
#   ./scripts/start_tool.sh TOOL_NAME [PORT]
#
# 示例：
#   ./scripts/start_tool.sh anoxpepred 8001
#   ./scripts/start_tool.sh toxipred3 8003
# ============================================================================

set -e

TOOL_NAME="${1:-}"
PORT="${2:-}"

if [ -z "$TOOL_NAME" ]; then
    echo "用法: $0 TOOL_NAME [PORT]"
    echo ""
    echo "可用工具:"
    echo "  anoxpepred  - 抗氧化肽预测 (默认端口 8001)"
    echo "  toxipred3   - 毒性预测 (默认端口 8003)"
    echo "  hemopi2     - 溶血性预测 (默认端口 8004)"
    echo "  mhcflurry   - MHC 结合预测 (默认端口 8005)"
    echo "  plm4cpps    - CPP 预测 (默认端口 8006)"
    echo "  tipred      - 酪氨酸酶抑制肽预测 (默认端口 8007)"
    echo "  algpred2    - 过敏原性预测 (默认端口 8008)"
    echo "  bepipred3   - B 细胞表位预测 (默认端口 8002)"
    echo "  graphcpp    - CPP 图神经网络预测 (默认端口 8009)"
    echo "  mlcpp       - CPP 机器学习预测 (默认端口 8010)"
    exit 1
fi

# 默认端口映射
declare -A DEFAULT_PORTS=(
    ["anoxpepred"]=8001
    ["bepipred3"]=8002
    ["toxipred3"]=8003
    ["hemopi2"]=8004
    ["mhcflurry"]=8005
    ["plm4cpps"]=8006
    ["tipred"]=8007
    ["algpred2"]=8008
    ["graphcpp"]=8009
    ["mlcpp"]=8010
)

# 确定端口
if [ -z "$PORT" ]; then
    PORT="${DEFAULT_PORTS[$TOOL_NAME]:-8001}"
fi

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# 检查工具服务是否存在
SERVICE_PATH="$PROJECT_ROOT/services/tools/$TOOL_NAME/service.py"
if [ ! -f "$SERVICE_PATH" ]; then
    echo "ERROR: 工具服务不存在: $SERVICE_PATH"
    exit 1
fi

echo "═══════════════════════════════════════════════════════════"
echo "  启动 $TOOL_NAME 微服务"
echo "  端口: $PORT"
echo "  服务: $SERVICE_PATH"
echo "═══════════════════════════════════════════════════════════"

cd "$PROJECT_ROOT"

# 设置环境变量
export TOOL_PORT="$PORT"
export TOOL_CLASS="services.tools.${TOOL_NAME}.service:app"

# 启动服务
exec uv run uvicorn "services.tools.${TOOL_NAME}.service:app" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --log-level info