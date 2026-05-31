#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 确保虚拟环境存在
if [ ! -d ".venv" ]; then
    echo "虚拟环境不存在，正在初始化..."
    ./scripts/setup.sh
fi

# 运行主程序
uv run python main.py "$@"
