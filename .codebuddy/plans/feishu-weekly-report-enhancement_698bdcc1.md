---
name: feishu-weekly-report-enhancement
overview: 完善飞书汇报差异分析项目，整合 workbuddy 中已验证的 lark-cli 实现，包括分页支持、认证流程文档化、以及潜在 AI 集成方案。
todos:
  - id: fix-pagination
    content: 完善 fetcher.py 分页逻辑，支持迭代获取所有消息
    status: completed
  - id: fix-wiki-parse
    content: 修正 Wiki URL 解析，改用 drive +inspect
    status: completed
  - id: update-setup
    content: 增强 setup.sh，添加认证状态检查和引导
    status: completed
  - id: add-readme
    content: 新建 README.md，补充认证配置文档
    status: completed
    dependencies:
      - update-setup
---

## 用户需求

整合 workbuddy 中已完成的飞书链接配置和汇报获取实现，完善当前项目。

## 核心改进点

1. **fetcher.py 分页逻辑修复** — 补充 `--page-token` 分页迭代，避免数据截断
2. **Wiki URL 解析完善** — 修正 `_resolve_wiki_url()` 使用 `drive +inspect --url`
3. **认证流程文档化** — 补充 README.md 认证配置说明
4. **setup.sh 增强** — 添加更完善的认证状态检查和引导

## 保留功能

- 5 模块架构（main/fetcher/parser/analyzer/reporter）
- lark-cli 作为飞书数据获取工具
- python-docx 生成 Word 报告
- AI 分析扩展支持（analyzer.py 的 ai_callback）

## 技术栈

- Python 3.12+ / uv 依赖管理
- lark-cli 飞书 CLI 工具（数据获取）
- python-docx Word 报告生成
- prompts/diff_analysis.md AI 分析 prompt

## 实现方案

### 1. fetcher.py 完善

**分页逻辑修复**：

```python
def list_messages(chat_id: str, weeks: int = 6) -> list[dict]:
    all_items = []
    page_token = None
    while True:
        args = ["im", "+chat-messages-list", "--chat-id", chat_id, 
                "--sort", "desc", "--page-size", "50", "--format", "json",
                "--start", start_time]
        if page_token:
            args.extend(["--page-token", page_token])
        data = _run_lark_cli(args)
        # ... 解析逻辑 ...
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return all_items
```

**Wiki URL 解析修复**：

- 改用 `lark-cli drive +inspect --url <wiki_url>` 获取 doc_token

### 2. README.md 新增

- lark-cli 安装说明
- 认证配置步骤（`config init --new` → 二维码登录 → `auth login`）
- 常见问题处理

### 3. setup.sh 增强

- 添加 lark-cli 认证状态检查
- 引导用户完成首次配置

## Agent Extensions

- **mmx-cli**：可选用于 AI 对比分析接入（MiniMax API）