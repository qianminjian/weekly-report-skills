#!/bin/bash
set -euo pipefail

# 保存用户当前工作目录（即工作区目录），后续所有输出将基于此目录
WORKSPACE_DIR="$PWD"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 确保虚拟环境存在
if [ ! -d ".venv" ]; then
    echo "虚拟环境不存在，正在初始化..."
    ./scripts/setup.sh
fi

# 运行主程序，传入工作区目录
uv run python main.py --workspace "$WORKSPACE_DIR" "$@"
