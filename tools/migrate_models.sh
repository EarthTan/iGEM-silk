#!/bin/bash
# ============================================================================
# 一次性脚本：将各服务已有的 fair-esm 模型迁移到共享目录
# ============================================================================
#
# 用法:
#   ./tools/migrate_models.sh        # 执行迁移
#   ./tools/migrate_models.sh --dry-run  # 仅预览，不做实际操作
#
# 迁移逻辑:
#   1. 检查 pLM4CPPs/models/torch/hub/checkpoints/
#   2. 检查 BepiPred-3.0/models/torch/hub/checkpoints/
#   3. 将其中所有 .pt 文件复制到 tools/models/fair-esm/hub/checkpoints/
#   4. 同名文件跳过或校验
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SHARED_DIR="$SCRIPT_DIR/models/fair-esm/hub/checkpoints"
DRY_RUN=false

[ "${1:-}" = "--dry-run" ] && DRY_RUN=true

echo "=== iGEM-silk 模型迁移脚本 ==="
echo "共享目录: $SHARED_DIR"
echo "模式: $([ "$DRY_RUN" = true ] && echo 'DRY RUN (预览)' || echo 'EXECUTE (执行)')"
echo ""

mkdir -p "$SHARED_DIR"

# 扫描各服务的 torch.hub 缓存
SOURCES=(
    "$SCRIPT_DIR/BepiPred-3.0/models/torch/hub/checkpoints"
    "$SCRIPT_DIR/pLM4CPPs/models/torch/hub/checkpoints"
)

migrated=0
skipped=0

for src in "${SOURCES[@]}"; do
    if [ ! -d "$src" ]; then
        echo "[SKIP] 源目录不存在: $src"
        continue
    fi

    for pt_file in "$src"/*.pt; do
        [ -f "$pt_file" ] || continue

        basename=$(basename "$pt_file")
        dest="$SHARED_DIR/$basename"

        if [ -f "$dest" ]; then
            # 比较文件是否相同
            if cmp -s "$pt_file" "$dest"; then
                echo "[OK]   $basename — 已存在且相同，跳过"
                skipped=$((skipped + 1))
            else
                echo "[WARN] $basename — 已存在但内容不同！保留共享目录版本，源文件不动。"
            fi
        else
            if [ "$DRY_RUN" = false ]; then
                cp "$pt_file" "$dest"
                echo "[COPY] $basename → shared/"
            else
                echo "[DRY]  $basename → shared/"
            fi
            migrated=$((migrated + 1))
        fi
    done
done

echo ""
echo "迁移完成: $migrated 个文件迁移, $skipped 个跳过"
if [ "$DRY_RUN" = true ]; then
    echo "（仅预览，未实际执行。去掉 --dry-run 以执行迁移。）"
else
    echo ""
    echo "各服务旧的 models/torch/ 目录可以手动删除（不影响运行）。"
fi
