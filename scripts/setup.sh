#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== 飞书汇报差异分析 - 环境初始化 ==="
echo ""

cd "$PROJECT_DIR"

# 检查 uv 是否可用
if ! command -v uv &>/dev/null; then
    echo "❌ 错误: uv 未安装，请先安装 uv"
    echo "   安装方式: brew install uv"
    exit 1
fi
echo "✓ uv 已安装"

# 检查 lark-cli 是否可用
if ! command -v lark-cli &>/dev/null; then
    echo "❌ 错误: lark-cli 未安装，请先安装"
    echo "   安装方式: npm install -g @minimax/lark-cli"
    exit 1
fi
echo "✓ lark-cli 已安装"

# 检查 lark-cli 版本
echo ""
echo "lark-cli 版本:"
lark-cli --version || true

# 检查认证状态
echo ""
echo "检查飞书认证状态..."
AUTH_STATUS=$(lark-cli auth status 2>&1 || echo "not_authenticated")

if echo "$AUTH_STATUS" | grep -q "user"; then
    echo "✓ 用户身份已认证"
    AUTH_TYPE="user"
elif echo "$AUTH_STATUS" | grep -q "bot"; then
    echo "✓ 应用身份已认证"
    AUTH_TYPE="bot"
else
    echo "⚠️  未检测到有效认证，需要进行配置"
    AUTH_TYPE=""
fi

# 创建虚拟环境并安装依赖
echo ""
echo "初始化 Python 环境..."
uv sync

# 创建必要目录
mkdir -p output logs

echo ""
echo "=== 初始化完成 ==="
echo ""

# 提供认证指引
if [ -z "$AUTH_TYPE" ]; then
    echo "📋 飞书认证配置步骤:"
    echo ""
    echo "1. 初始化配置（生成二维码）:"
    echo "   lark-cli config init --new"
    echo ""
    echo "2. 使用飞书扫码登录（用户身份）:"
    echo "   lark-cli auth login --scope \"im:chat:read im:message:readonly drive:doc:readonly\""
    echo ""
    echo "3. 完成后重新运行:"
    echo "   ./scripts/run.sh collect --chat-name \"汇报\" --weeks 6"
else
    echo "🚀 运行方式:"
    echo ""
    echo "   # Phase 1: 数据采集"
    echo "   ./scripts/run.sh collect --chat-name \"汇报\""
    echo ""
    echo "   # Phase 2: Agent 自动进行 AI 分析（无需外部 API Key）"
    echo ""
    echo "   # Phase 3: 生成报告"
    echo "   ./scripts/run.sh report output/analysis_result.json"
fi
