---
name: lark-workflow-weekly-report-risk-analysis
overview: 为飞书周报提炼分析 Skill 添加 AI 智能风险识别能力：阻塞/延期/资源/依赖风险自动识别、交叉依赖分析、风险趋势追踪、Word 报告增强。
todos:
  - id: create-minimax-client
    content: 新建 src/minimax_client.py：MiniMax API 直接 HTTP 调用封装
    status: completed
  - id: upgrade-prompt
    content: 升级 prompts/diff_analysis.md：增加风险识别标准、趋势分析、跨人依赖识别
    status: completed
  - id: modify-ai-client
    content: 修改 src/ai_client.py：整合 minimax_client，保留 mmx-cli 回退
    status: completed
    dependencies:
      - create-minimax-client
  - id: modify-analyzer
    content: 修改 src/analyzer.py：默认走 AI 路径，无 Key 时报错退出
    status: completed
    dependencies:
      - upgrade-prompt
      - modify-ai-client
  - id: modify-main
    content: 修改 main.py：删除 --ai 参数，默认启用 AI 分析
    status: completed
    dependencies:
      - modify-analyzer
  - id: add-requests-dep
    content: 修改 pyproject.toml：新增 requests 依赖
    status: completed
  - id: update-skill
    content: 更新 SKILL.md：删除 --ai 参数说明，更新环境变量配置说明
    status: completed
    dependencies:
      - modify-main
  - id: test-ai-analysis
    content: 运行完整流程验证 AI 智能分析输出
    status: completed
    dependencies:
      - add-requests-dep
      - update-skill
---

## 用户需求

必须使用 AI 智能分析（MiniMax-M2.7 模型），自动识别四类风险（阻塞/延期/资源/依赖），作为周报提炼的**默认行为**，删除 `--ai` 可选参数的概念。

## 现状分析

| 模块 | 当前状态 | 问题 |
| --- | --- | --- |
| `ai_client.py` | 仅支持 `mmx-cli` 子进程调用 | `mmx-cli` 未认证，调用失败 |
| `analyzer.py` | 有 `DiffItem/RiskItem/PersonAnalysis` 数据类 | prompt 风险识别标准模糊 |
| `prompts/diff_analysis.md` | 已有 JSON 结构 | 缺乏识别标准、趋势分析、跨人依赖 |
| `main.py` | AI 分析需 `--ai` 显式开启 | 需改为默认启用 |
| `SKILL.md` | 提及 `--ai` 参数 | 需更新描述 |


## 核心挑战

`mmx-cli` 未认证，无法通过子进程调用 MiniMax API。解决方案：**直接通过 HTTP 调用 MiniMax 开放平台 API**，API Key 通过环境变量 `MINIMAX_API_KEY` 配置（用户需提供 Key）。

## 功能目标

1. **直接 HTTP 调用 MiniMax API** — 删除对 `mmx-cli` 认证的依赖
2. **升级 Prompt 模板** — 明确风险识别标准，增加趋势分析、跨人依赖识别
3. **默认启用 AI 分析** — 删除 `--ai` 参数概念
4. **优雅降级** — 若无 API Key 则报错提示（不再静默回退到文本对比）

## 技术方案

### 1. AI 调用层：新增 MiniMax 直接 HTTP 调用

新增 `src/minimax_client.py`，直接调用 MiniMax 开放平台 API：

```
POST https://api.minimax.chat/v1/text/chatcompletion_v2
Authorization: Bearer $MINIMAX_API_KEY
```

**输入**：分析 prompt（字符串），**输出**：AI 返回文本（字符串）

同时保留 `ai_client.py` 的 `mmx-cli` 回退逻辑（已认证时优先用）。

### 2. Prompt 模板升级

升级 `prompts/diff_analysis.md`，新增：

- **风险识别标准**：明确定义四类风险的判断依据
- **风险原因**：每项风险需说明原因
- **缓解建议**：每项风险需给出初步缓解方向
- **跨人依赖**：识别本次汇报中提及其他人的工作依赖
- **风险趋势**：与上周对比，风险是否加重/减轻
- **整体风险评分**：0-10 分，说明理由

### 3. 分析层调整

- `analyzer.py` 新增 `_analyze_with_api_key()` 路径
- `analyze_diff()` 默认使用 AI，无 API Key 时直接报错退出（不再静默回退）

### 4. 入口层调整

- 删除 `main.py` 中 `--ai` 参数及相关逻辑
- `check_mmx_available()` 改为检查 `MINIMAX_API_KEY` 环境变量或 `mmx-cli` 认证状态
- API Key 优先从环境变量读取

### 5. 依赖变更

`pyproject.toml` 新增 `requests` 依赖（用于 HTTP 调用）。

## 目录结构

```
src/
├── __init__.py
├── minimax_client.py   # [NEW] MiniMax API 直接 HTTP 调用
├── ai_client.py        # [MODIFY] 整合 minimax_client，保留 mmx-cli 回退
├── analyzer.py          # [MODIFY] 默认走 AI 路径
├── fetcher.py           # (已有)
├── parser.py            # (已有)
└── reporter.py          # (已有)
prompts/
└── diff_analysis.md     # [MODIFY] 升级 prompt，增加风险识别标准
main.py                  # [MODIFY] 删除 --ai 参数，默认 AI
SKILL.md                 # [MODIFY] 更新参数说明
pyproject.toml           # [MODIFY] 新增 requests 依赖
```