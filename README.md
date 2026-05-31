# 飞书周报提炼分析

从飞书「消息→汇报」自动拉取汇报材料，Agent 内置 AI 智能对比分析差异与风险，生成 Word 报告。

## 功能特性

- 从飞书「消息→汇报」自动定位汇报对话、拉取消息（支持分页）
- 自动识别并抓取飞书文档（docx/wiki）正文
- **Agent 内置 AI 分析**：四象限风险识别（阻塞/延期/资源/依赖）、跨人依赖分析、整体评估
- 生成格式优美的 Word 分析报告（风险着色表格）
- **周末详情附件**：自动提取周五/六/日三天汇报原文，合并输出 Word

## 分享与安装

### 方式 1：GitHub 克隆 + CodeBuddy 导入（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/minjianq/feishu-weekly-report-skills.git
cd feishu-weekly-report-skills

# 2. 导入到 CodeBuddy
#    打开 CodeBuddy → 设置 → Skills → 导入 Skill → 选择本项目文件夹
#    或直接拖入 CodeBuddy 窗口

# 3. 环境初始化
./scripts/setup.sh

# 4. 飞书认证（如未配置）
lark-cli auth login --scope "im:chat:read im:message:readonly drive:doc:readonly"
```

### 方式 2：CodeBuddy 插件市场安装

```bash
# 在 CodeBuddy 中输入：
/plugin install lark-workflow-weekly-report
```

安装后按方式 1 的步骤 3-4 完成环境初始化。

### 方式 3：手动导入 Skill 文件夹

如果已从他人处获得本项目文件夹：

1. 打开 CodeBuddy → 设置 → Skills
2. 点击「导入 Skill」→ 选择 `feishu-weekly-report-skills/` 文件夹
3. 重启 CodeBuddy
4. 运行 `./scripts/setup.sh` 初始化环境

## 环境要求

| 依赖 | 安装方式 | 用途 |
|------|---------|------|
| Python 3.12+ | [python.org](https://python.org) | 运行环境 |
| [uv](https://github.com/astral-sh/uv) | `brew install uv` | 依赖管理 |
| [lark-cli](https://www.npmjs.com/package/@minimax/lark-cli) | `npm install -g @minimax/lark-cli` | 飞书 API |

## 快速开始

```bash
# Phase 1: 数据采集（自动从「消息→汇报」拉取，回溯 6 周）
./scripts/run.sh collect

# Phase 2: Agent 自动进行 AI 分析（当前 AI 模型上下文中完成）
#   → 写入 Weekly-Report-yyyy-mm-dd/analysis_result.json

# Phase 3: 生成 Word 报告
./scripts/run.sh report Weekly-Report-yyyy-mm-dd/analysis_result.json
```

## 命令参考

| 命令 | 说明 |
|------|------|
| `./scripts/run.sh collect` | 数据采集 → 周末详情附件 |
| `./scripts/run.sh report <json>` | 读取分析结果 → 生成 Word 报告 |
| `./scripts/run.sh detail` | 单独提取周末三天汇报原文 |

### collect 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--chat-id` | 自动定位 | 对话 ID |
| `--weeks` | `8` | 回溯周数 |
| `--output` | `Weekly-Report-yyyy-mm-dd/analysis_data.json` | 输出路径 |

### report 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input` | 必填 | 分析结果 JSON |
| `--chat-name` | `"汇报"` | 报告标题来源 |
| `--output` | 自动版本递增 | 输出 Word 路径 |
| `--keep-json` | 关闭 | 保留中间 JSON 文件 |

## 输出产物

```
Weekly-Report-2026-05-31/
├── Weekly-Report-ImportInfo-2026-05-31-v1.docx   ← 分析报告
└── weekly-Detail-v1.docx                         ← 周末详情
```

## 报告结构

1. **整体摘要** — 人数统计、风险四象限分布、整体风险评分
2. **跨人依赖关系** — 依赖方 → 被依赖方关系表
3. **各人汇报分析** — 摘要、关键差异、风险点（含原因/建议/趋势）
4. **风险汇总** — 按风险等级排序的汇总表

## 项目结构

```
feishu-weekly-report-skills/
├── .codebuddy-plugin/          # 插件元数据（市场分发）
│   └── plugin.json
├── skills/                     # 插件模式 Skill
│   └── lark-workflow-weekly-report/
│       └── SKILL.md
├── SKILL.md                    # 独立 Skill 入口
├── main.py                     # 主入口
├── src/
│   ├── fetcher.py              # 飞书数据获取
│   ├── parser.py               # 消息解析
│   ├── analyzer.py             # 数据结构定义
│   ├── reporter.py             # Word 报告生成
│   └── weekly_detail.py        # 周末详情提取
├── prompts/
│   └── diff_analysis.md        # AI 分析 prompt 模板
├── scripts/
│   ├── setup.sh                # 环境初始化
│   └── run.sh                  # 运行脚本
├── pyproject.toml              # Python 项目配置
└── README.md
```

## 工作原理

```
Phase 1 (Python)           Phase 2 (Agent)              Phase 3 (Python)
数据采集 ──► JSON 数据 ──► AI 智能分析 ──► 分析结果 ──► Word 报告生成
```

1. **数据获取**：通过 lark-cli 从「消息→汇报」路径拉取消息
2. **消息解析**：按发送人分组，提取文本和文档链接
3. **AI 分析**：Agent 读取 JSON，对比相邻两次汇报，四象限风险识别
4. **报告生成**：输出 Word 格式分析报告 + 周末详情附件

## 分享给他人

1. **GitHub**：将本仓库 push 到 GitHub，分享链接即可
2. **打包文件夹**：将整个项目打包为 zip，对方解压后按方式 3 导入
3. **插件市场**：提交到 CodeBuddy 插件市场后，对方通过 `/plugin install` 安装

## License

MIT
