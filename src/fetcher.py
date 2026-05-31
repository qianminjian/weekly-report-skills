"""飞书数据获取：从「消息→汇报」路径拉取汇报数据、文档读取"""

import json
import logging
import re
import subprocess
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DOC_URL_PATTERN = re.compile(
    r"https?://[a-zA-Z0-9-]+\.feishu\.cn/(docx|wiki|doc)/[a-zA-Z0-9]+"
)

# 汇报相关关键词：用于识别汇报 Bot 对话
REPORT_KEYWORDS = ["汇报", "周报", "工作汇报", "报告"]


def _run_lark_cli(args: list[str]) -> dict | list | None:
    """执行 lark-cli 命令并解析 JSON 输出，自动解包 {ok, data, ...} 嵌套"""
    try:
        result = subprocess.run(
            ["lark-cli"] + args,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.error("lark-cli 执行失败: %s", result.stderr)
            return None
        output = result.stdout.strip()
        if not output:
            return None
        parsed = json.loads(output)
        # lark-cli API 响应格式: {ok: true, identity: ..., data: {...}, _notice: ...}
        # 自动解包 data 字段
        if isinstance(parsed, dict) and "ok" in parsed and "data" in parsed:
            return parsed["data"]
        return parsed
    except subprocess.TimeoutExpired:
        logger.error("lark-cli 执行超时: %s", " ".join(args))
        return None
    except json.JSONDecodeError:
        logger.error("lark-cli 输出非 JSON: %s", result.stdout[:200])
        return None


def _is_report_chat(chat: dict) -> bool:
    """判断对话是否与汇报相关（根据名称匹配关键词）"""
    name = chat.get("name", "") or chat.get("id", "")
    return any(kw in name for kw in REPORT_KEYWORDS)


def find_report_chat() -> str | None:
    """定位「消息→汇报」对话，返回 chat_id

    飞书汇报功能通过「汇报」应用/Bot 向群聊或 P2P 下发消息卡片。
    本方法按以下顺序定位汇报对话：

    1. 优先查找 P2P 对话中的汇报 Bot（对应飞书「消息→汇报」入口）
    2. 其次搜索包含"汇报"关键词的群聊
    3. 仍找不到则通过消息搜索兜底

    不再盲目搜索所有群聊，固定从「消息→汇报」路径拉取。
    """
    # Step 1: 查找 P2P 对话中的汇报 Bot
    # 汇报 Bot 会向用户发送 P2P 消息，对应飞书客户端「消息」Tab 下的「汇报」会话
    data = _run_lark_cli([
        "im", "+chat-search", "--query", "汇报",
        "--chat-type", "p2p", "--format", "json",
    ])
    if data:
        items = data if isinstance(data, list) else data.get("items", data.get("chats", []))
        for chat in items:
            if _is_report_chat(chat):
                chat_id = chat.get("chat_id") or chat.get("id")
                chat_name = chat.get("name", "未知")
                logger.info("找到汇报 Bot P2P 对话: %s (chat_id: %s)", chat_name, chat_id)
                return chat_id

    # Step 2: 搜索群聊中的汇报群
    logger.info("未找到汇报 Bot P2P 对话，尝试搜索汇报群聊...")
    data = _run_lark_cli([
        "im", "+chat-search", "--query", "汇报",
        "--chat-type", "group", "--format", "json",
    ])
    if data:
        items = data if isinstance(data, list) else data.get("items", data.get("chats", []))
        if items:
            chat = items[0]
            chat_id = chat.get("chat_id") or chat.get("id")
            chat_name = chat.get("name", "未知")
            logger.info("找到汇报群聊: %s (chat_id: %s)", chat_name, chat_id)
            return chat_id

    # Step 3: 兜底——通过消息搜索定位汇报对话
    logger.info("通过群聊搜索未找到，尝试搜索汇报消息定位对话...")
    data = _run_lark_cli([
        "im", "+messages-search", "--query", "汇报",
        "--page-size", "5", "--format", "json",
    ])
    if data:
        messages = data if isinstance(data, list) else data.get("messages", data.get("items", []))
        if messages:
            chat_id = messages[0].get("chat_id")
            if chat_id:
                logger.info("通过消息搜索定位到对话: chat_id=%s", chat_id)
                return chat_id

    logger.warning("未找到汇报对话，请确认飞书账户「消息→汇报」下有汇报消息")
    return None


def list_messages(chat_id: str, weeks: int = 6) -> list[dict]:
    """拉取群消息，返回消息列表（自动分页）"""
    start_time = (datetime.now() - timedelta(weeks=weeks)).strftime("%Y-%m-%dT00:00:00")
    all_items = []
    page_token = None

    while True:
        args = [
            "im", "+chat-messages-list",
            "--chat-id", chat_id,
            "--sort", "desc",
            "--page-size", "50",
            "--format", "json",
            "--start", start_time,
        ]
        if page_token:
            args.extend(["--page-token", page_token])

        data = _run_lark_cli(args)
        if not data:
            logger.warning("消息拉取中断: chat_id=%s", chat_id)
            break

        # 解析消息列表
        items = data if isinstance(data, list) else data.get("items", data.get("messages", []))
        all_items.extend(items)

        # 检查是否还有更多数据
        if isinstance(data, dict):
            has_more = data.get("has_more", False)
            page_token = data.get("page_token") if has_more else None
            if not has_more:
                break
        else:
            break

    logger.info("获取到 %d 条消息（分页完成）", len(all_items))
    return all_items


def fetch_document(url: str) -> str | None:
    """获取飞书文档内容（处理 wiki/docx 两种链接）"""
    # 判断是否为 wiki URL，需要先解析
    if "/wiki/" in url:
        doc_token = _resolve_wiki_url(url)
        if not doc_token:
            logger.warning("Wiki URL 解析失败，尝试直接获取: %s", url)
            doc_token = url
    else:
        doc_token = url

    data = _run_lark_cli([
        "docs", "+fetch",
        "--api-version", "v2",
        "--doc", doc_token,
        "--doc-format", "markdown",
    ])
    if not data:
        logger.warning("文档获取失败: %s", url)
        return None

    # docs +fetch 返回的可能直接是文本内容或带结构的数据
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        content = data.get("content") or data.get("text") or data.get("body", "")
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False) if content else None
    return str(data) if data else None


def _resolve_wiki_url(url: str) -> str | None:
    """解析 wiki URL，获取底层文档 token"""
    data = _run_lark_cli(["drive", "+inspect", "--url", url, "--format", "json"])
    if not data:
        return None
    if isinstance(data, dict):
        # drive +inspect 返回 {ok: true, data: {token: "xxx", ...}}
        data_obj = data.get("data", data)
        return data_obj.get("token") or data_obj.get("doc_token") or data_obj.get("document_id")
    return None


def extract_doc_urls(text: str) -> list[str]:
    """从文本中提取飞书文档链接"""
    return DOC_URL_PATTERN.findall(text) if text else []
