#!/usr/bin/env bash
# ============================================================================
# scripts/start_all_tools.sh
# ============================================================================
# 启动所有工具微服务（后台运行）
#
# 用法：
#   ./scripts/start_all_tools.sh
#
# 注意：需要在后台运行，每个工具服务启动后会后台执行
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
PID_DIR="$PROJECT_ROOT/.pids"

# 创建日志和 PID 目录
mkdir -p "$LOG_DIR" "$PID_DIR"

echo "═══════════════════════════════════════════════════════════"
echo "  启动所有工具微服务"
echo "═══════════════════════════════════════════════════════════"

# 工具列表：名称, 端口, 是否需要 GPU
TOOLS=(
    "anoxpepred:8001:no"
    "bepipred3:8002:yes"
    "toxipred3:8003:no"
    "hemopi2:8004:no"
    "mhcflurry:8005:no"
    "plm4cpps:8006:no"
    "tipred:8007:no"
    "algpred2:8008:no"
    "graphcpp:8009:no"
    "mlcpp:8010:no"
)

STARTED=0
SKIPPED=0

for tool_spec in "${TOOLS[@]}"; do
    IFS=':' read -r name port gpu <<< "$tool_spec"

    # 检查 GPU 工具（如果不需要 GPU 或有 GPU 可用）
    if [ "$gpu" = "yes" ]; then
        if ! command -v nvidia-smi &> /dev/null; then
            echo "⏭️  跳过 $name (需要 GPU 但未检测到)"
            SKIPPED=$((SKIPPED + 1))
            continue
        fi
    fi

    echo "🚀 启动 $name on port $port ..."

    # 启动工具服务（后台运行）
    cd "$PROJECT_ROOT"
    nohup uv run uvicorn "services.tools.${name}.service:app" \
        --host 0.0.0.0 \
        --port "$port" \
        > "$LOG_DIR/${name}.log" 2>&1 &

    PID=$!
    echo $PID > "$PID_DIR/${name}.pid"

    echo "   PID: $PID, 日志: $LOG_DIR/${name}.log"
    STARTED=$((STARTED + 1))
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  启动完成"
echo "  已启动: $STARTED 个服务"
echo "  已跳过: $SKIPPED 个服务 (需要 GPU 但不可用)"
echo "  PID 文件: $PID_DIR/"
echo "  日志目录: $LOG_DIR/"
echo "═══════════════════════════════════════════════════════════"

# 显示帮助信息
echo ""
echo "查看日志: tail -f $LOG_DIR/<tool_name>.log"
echo "停止服务: ./scripts/stop_all.sh"