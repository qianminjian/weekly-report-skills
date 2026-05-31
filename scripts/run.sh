#!/bin/bash
set -euo pipefail

# 工作区目录获取优先级：
#   1. SKILL_WORKSPACE 环境变量（WorkBuddy 等平台由 Agent 设置）
#   2. 当前工作目录 $PWD（适用于直接在项目目录执行的情况）
#   3. 如果前两者都指向技能安装目录，由调用方通过 --workspace 传入
WORKSPACE_DIR="${SKILL_WORKSPACE:-$PWD}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# 工作区目录不能是技能目录本身，防止输出生成到技能安装目录
SKILL_DIR="$(cd "$PROJECT_DIR" && pwd)"
if [ "$(cd "$WORKSPACE_DIR" 2>/dev/null && pwd)" = "$SKILL_DIR" ]; then
    echo "⚠️  警告: 工作区目录与技能安装目录相同"
    echo "   技能目录: $SKILL_DIR"
    echo "   请通过 SKILL_WORKSPACE 环境变量指定工作区，或 cd 到项目目录后执行。"
    echo "   示例: SKILL_WORKSPACE=/path/to/your/project bash scripts/run.sh collect"
    echo "   或先 cd 到目标项目目录再执行。"
fi

cd "$PROJECT_DIR"

# 确保虚拟环境存在
if [ ! -d ".venv" ]; then
    echo "虚拟环境不存在，正在初始化..."
    ./scripts/setup.sh
fi

# 运行主程序，传入工作区目录
uv run python main.py --workspace "$WORKSPACE_DIR" "$@"
