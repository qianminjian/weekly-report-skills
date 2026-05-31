# feishu-weekly-report-skills 项目配置

> 本文件为飞书汇报差异分析项目级配置
> 项目根目录：`/Users/minjianq/Documents/CodeBuddy/feishu-weekly-report-skills`

---

## 继承关系

本项目继承以下配置（按优先级从高到低）：

1. **本文件** — feishu-weekly-report-skills 项目专用规范
2. **`../project/codebuddy.md`** — CodeBuddy 项目级规范
3. **`../cde-rules.md`** — CodeBuddy 测试闭环 & Git PR 自动化规范

> 如本文件与上级规范冲突，以本文件为准。

---

## 项目概述

- **项目名称**：feishu-weekly-report-skills（飞书汇报差异分析）
- **项目类型**：Python CLI 工具
- **功能说明**：从飞书群聊获取汇报材料，AI 对比分析差异与风险，生成 Word 报告
- **技术栈**：Python 3.12+ / uv / python-docx / lark-cli

---

## 本项目特定约定

### 依赖管理

- 使用 `uv` 管理依赖和虚拟环境
- 虚拟环境目录：`.venv`
- 核心依赖：`python-docx`

### 运行方式

所有操作通过 `scripts/` 下的 shell 脚本执行：

```bash
# 初始化环境
./scripts/setup.sh

# 运行分析
./scripts/run.sh --chat-name "汇报" --weeks 6
```

### 目录规范

```
├── src/           # 核心代码
├── prompts/       # AI prompt 模板
├── output/        # 生成的报告
├── logs/          # 运行日志
└── scripts/       # 运行脚本
```

### 文件行数约束

- 单文件不超过 300 行（Python 动态语言）

---

_本文件继承自 `../project/codebuddy.md` 及 `../cde-rules.md`，如有冲突以本文件为准。_
