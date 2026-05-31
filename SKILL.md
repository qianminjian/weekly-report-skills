---
name: lark-workflow-weekly-report
version: 2.0.0
description: "飞书周报提炼分析：从飞书群聊获取汇报材料，Agent 内置 AI 智能对比分析差异与风险，生成 Word 报告。当用户说'帮我提炼周报'、'总结一下周报'、'看一下周报的内容'或其他周报相关需求时使用。"
metadata:
  requires:
    bins: ["lark-cli", "uv", "python3"]
---

# 飞书周报提炼分析（v2）

**触发场景**：用户提及"帮我提炼周报"、"总结一下周报"、"看一下周报的内容"、"分析周报"、"周报差异"等关键词时触发本 Skill。

## 核心设计

本 Skill 采用 **双阶段流水线**，AI 分析由 Agent（当前运行的模型）直接在上下文中完成，无需外部 AI API：

```
Phase 1 (Python)           Phase 2 (Agent)              Phase 3 (Python)
数据采集 ──► JSON 数据 ──► AI 智能分析 ──► 分析结果 ──► Word 报告生成
```

## 适用场景

- "帮我提炼周报" / "总结一下周报" / "看一下周报的内容"
- "生成这周的汇报分析报告"
- "分析群里的汇报差异"

## 前置条件

1. **lark-cli 认证** — lark-cli 认证由运行本 Skill 的 Agent 外部配置，无需在 Skill 内配置。确保 Agent 已通过 lark-cli 连接飞书：

```bash
lark-cli auth status
```

> 认证、权限处理由 Agent 环境统一管理，本 Skill 不内置飞书链接或认证凭据。

2. **汇报数据路径** — 采集固定从飞书「消息→汇报」路径拉取，不再搜索群聊，避免盲目寻找。确保飞书账户「消息」Tab 下有「汇报」会话。

3. **Python 环境** — 使用 `uv` 管理，首次运行会自动初始化：

```bash
./scripts/setup.sh
```

## 工作流

### 整体流程

```
用户指令 ─► Phase 1: 数据采集 ─► Phase 2: Agent AI 分析 ─► Phase 3: 报告生成
```

### Phase 1: 数据采集（Python 脚本）

Agent 执行以下命令，从飞书「消息→汇报」路径拉取汇报数据：

```bash
# 基础采集（自动定位「消息→汇报」路径，回溯 6 周）
./scripts/run.sh collect

# 指定回溯周数和输出路径
./scripts/run.sh collect --weeks 4 --output output/my_data.json
```

**参数说明：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--chat-id` | 无 | 对话 ID，指定后跳过自动定位 |
| `--weeks` | `6` | 回溯周数 |
| `--output` | `Weekly-Report-yyyy-mm-dd/analysis_data.json` | 采集数据输出路径 |

> 输出目录固定为 `Weekly-Report-yyyy-mm-dd/`，位于项目工作目录下。中间文件（`analysis_data.json`、`analysis_result.json`）使用稳定名称，最终报告使用版本号递增。

> 采集固定从飞书「消息→汇报」路径拉取，无需指定群聊名称。内部实现优先查找汇报 Bot P2P 对话，其次搜索汇报群聊，不盲目搜索所有群。

**输出文件**：`output/analysis_data.json`

```json
{
  "source": "飞书消息→汇报",
  "collected_at": "2026-05-31T20:00:00",
  "persons": [
    {
      "name": "张三",
      "sender_id": "xxx",
      "current": {
        "text": "本周完成：1. 登录模块重构...",
        "source": "document",
        "timestamp": "2026-05-30T10:00:00",
        "doc_urls": ["https://xxx.feishu.cn/docx/xxx"]
      },
      "previous": {
        "text": "上周完成：1. 登录模块设计...",
        "source": "message",
        "timestamp": "2026-05-16T10:00:00"
      }
    }
  ]
}
```

### Phase 2: Agent AI 智能分析

Agent 读取 `output/analysis_data.json`，使用当前运行的模型，对每人进行对比分析。

**分析维度（四象限风险识别）：**

| 风险类型 | 识别标准 | 关键信号词 |
|---------|---------|-----------|
| **阻塞** | 任务完全卡住，无法推进 | "被阻塞"、"卡住了"、"无法推进"、"等待" |
| **延期** | 进度落后于预期时间线 | "延期"、"延迟"、"晚于计划"、"进度落后" |
| **资源** | 人力/设备/预算/环境不足 | "人手不够"、"资源不足"、"需要支持"、"预算" |
| **依赖** | 依赖外部团队/模块/决策 | "等XX完成"、"依赖XX"、"需要XX配合"、"排期" |

**分析步骤：**

1. **逐人分析**：对每个 `person`，对比 `current` 和 `previous` 的汇报内容
2. **差异识别**：提取新增/变更/移除的工作项
3. **风险识别**：按四象限标准识别风险，包含：
   - 风险等级（阻塞/延期/资源/依赖）
   - 风险描述
   - 风险原因（为什么出现）
   - 缓解建议（如何应对）
   - 趋势判断（相比上周：加重/减轻/持平/新增）
   - 依赖对象（如果涉及跨人依赖）
4. **跨人依赖分析**：识别"A 等 B 完成某事"等表述，建立依赖关系图
5. **整体评估**：综合所有分析，给出：
   - 整体风险评分（1-5 分）
   - 整体评估摘要（一段话）
   - 重点关注事项（最紧急的 3-5 个问题）

**分析 Prompt 模板**：见 `prompts/diff_analysis.md`，Agent 应使用此模板对每人进行分析。

**Agent 输出格式**：分析完成后，Agent 将结果写入 `output/analysis_result.json`：

```json
{
  "analyses": [
    {
      "person_name": "张三",
      "is_first_report": false,
      "summary": "登录模块从设计进入重构阶段，进度正常",
      "diffs": [
        {"category": "新增", "content": "登录模块重构", "impact": "替换现有实现"},
        {"category": "变更", "content": "将后端 API 从 REST 改为 GraphQL", "impact": "前后端联调需重新适配"}
      ],
      "risks": [
        {
          "level": "依赖",
          "content": "登录重构依赖后端 API 改造完成",
          "cause": "后端 GraphQL 迁移尚未完成",
          "suggestion": "建议与后端对齐排期，或先做前端部分",
          "trend": "新增",
          "depends_on": ["李四"]
        }
      ]
    }
  ],
  "dependencies": [
    {"from_person": "张三", "to_person": "李四", "description": "登录重构需要后端 GraphQL 接口"}
  ],
  "overall_risk_score": 2,
  "overall_summary": "整体进展正常，主要关注张三的后端依赖风险和李四的延期交付",
  "key_concerns": [
    "张三的登录重构依赖李四的 GraphQL 接口，需协调排期",
    "李四的支付模块已延期2周，需评估对整体进度的影响"
  ]
}
```

### Phase 3: 报告生成（Python 脚本）

Agent 完成分析后，执行以下命令生成 Word 报告：

```bash
# 生成报告
./scripts/run.sh report output/analysis_result.json

# 指定群名和输出路径
./scripts/run.sh report output/analysis_result.json --chat-name "团队周报" --output output/my_report.docx
```

**参数说明：**

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `input` | 必填 | Agent 分析结果 JSON 文件路径 |
| `--chat-name` | `"汇报"` | 数据来源名称（用于报告标题） |
| `--output` | `Weekly-Report-yyyy-mm-dd/Weekly-Report-ImportInfo-yyyy-mm-dd-vN.docx` | 输出 Word 路径（版本号自动递增） |

> 同一目录下多次生成报告，版本号自动递增：`v1` → `v2` → `v3` …

### 完整执行示例

Agent 端到端执行流程：

```bash
# 1. 数据采集（自动从「消息→汇报」路径拉取，回溯 6 周）
./scripts/run.sh collect

# 2. Agent 读取 output/analysis_data.json 并进行分析（Agent 上下文内完成）
#    → 写入 output/analysis_result.json

# 3. 报告生成
./scripts/run.sh report output/analysis_result.json
```

## 报告结构

生成的 Word 报告包含：

1. **一、整体摘要** — 人数统计、风险四象限分布、整体风险评分
2. **二、跨人依赖关系** — 依赖方 → 被依赖方关系表
3. **三、各人汇报分析** — 每人独立分析：
   - 摘要（Agent 生成的总结）
   - 关键差异（新增/变更/移除，带影响评估）
   - 风险点（等级着色 + 原因 + 缓解建议 + 趋势）
4. **四、风险汇总** — 按风险等级排序的汇总表（含原因、趋势、建议）

## 注意事项

- **无需外部 AI API Key**：AI 分析由当前 Agent 模型完成
- 消息中如包含飞书文档链接（`docx`/`wiki`），会自动拉取文档正文进行全文分析
- 当天同人的多条消息会自动合并，每人提取最近 2 次汇报
- 日志文件保存在 `logs/` 目录，报告和数据保存在 `output/` 目录

## 参考

- [lark-shared](https://www.codebuddy.ai/docs/zh/ide/Skills/lark-shared) — 认证、权限处理
- [lark-im](https://www.codebuddy.ai/docs/zh/ide/Skills/lark-im) — 群聊搜索、消息拉取
- [lark-drive](https://www.codebuddy.ai/docs/zh/ide/Skills/lark-drive) — Wiki 解析、文档读取
