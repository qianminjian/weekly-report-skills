"""消息解析：按人分组、链接提取、内容归类"""

import json
import logging
import re
from dataclasses import dataclass, field

from .fetcher import fetch_document, extract_doc_urls

logger = logging.getLogger(__name__)

# 过滤阈值：纯文字消息少于此字数且无链接则忽略
MIN_TEXT_LENGTH = 10

# 卡片标题提取：<card title="朱健的自由汇报">  → "朱健"
CARD_TITLE_PATTERN = re.compile(r'<card\s+title="(.+?)"')
# 汇报名称模式：提取人名（"XXX的自由汇报" / "XXX的工作周报" 等）
REPORT_NAME_PATTERN = re.compile(
    r"^(.+?)的(自由汇报|工作周报|基拓团队工作周报|周报|汇报|工作汇报|核心产品部落|本周工作汇报)"
)
# 系统消息标题（非真实汇报人，需过滤）
SYSTEM_TITLES = {"汇报提交统计", "评论回复"}


@dataclass
class ReportContent:
    """单次汇报内容"""
    text: str                           # 汇报文本内容
    source: str                         # "document" | "message"
    doc_urls: list[str] = field(default_factory=list)
    timestamp: str = ""                 # 消息发送时间


@dataclass
class PersonReports:
    """单人汇报对（当前 + 上次）"""
    sender_name: str
    sender_id: str
    current: ReportContent | None = None
    previous: ReportContent | None = None


def _extract_card_title(msg: dict) -> str | None:
    """从消息的 content 字段提取卡片标题"""
    # 优先从 content 字段读取（P2P 机器人消息把内容放在 content 而非 body 中）
    raw = msg.get("content", "") or msg.get("body", "")
    if isinstance(raw, dict):
        raw = raw.get("content", "")
    if isinstance(raw, str):
        m = CARD_TITLE_PATTERN.search(raw)
        if m:
            return m.group(1)
    return None


def _parse_reporter_name(title: str) -> str:
    """从卡片标题解析汇报人姓名，如 '朱健的自由汇报' → '朱健'，'苗阳_Michael的苗阳本周工作汇报' → '苗阳'"""
    m = REPORT_NAME_PATTERN.match(title.strip())
    if m:
        name = m.group(1)
        # 去掉英文别名（如 "苗阳_Michael" → "苗阳"）
        if "_" in name:
            name = name.split("_")[0]
        return name.strip()
    # 回退：取第一个"的"之前的部分作为姓名
    if "的" in title:
        name = title.split("的")[0].strip()
        if "_" in name:
            name = name.split("_")[0]
        return name
    return title


def _is_system_title(title: str | None) -> bool:
    """判断卡片标题是否为系统消息"""
    if not title:
        return False
    return title.strip() in SYSTEM_TITLES


def group_by_sender(messages: list[dict]) -> dict[str, list[dict]]:
    """按发送人分组，返回 {sender_id: [messages]}
    
    对于机器人卡片消息（msg_type=interactive），按卡片标题中的汇报人姓名分组。
    对于普通消息，按 sender.id 分组。
    自动过滤系统消息（如"汇报提交统计"、"评论回复"）。
    """
    grouped: dict[str, list[dict]] = {}
    for msg in messages:
        if msg.get("msg_type") == "interactive" or msg.get("chat_type") == "p2p":
            # 机器人卡片消息 / P2P 消息：从 card title 提取汇报人
            title = _extract_card_title(msg)
            if not title or _is_system_title(title):
                continue
            sender_id = _parse_reporter_name(title)
        else:
            sender = msg.get("sender", {})
            sender_id = sender.get("id") or sender.get("sender_id", {})
            if isinstance(sender_id, dict):
                sender_id = sender_id.get("open_id", "unknown")
            if not sender_id or sender_id == "unknown":
                continue
        grouped.setdefault(sender_id, []).append(msg)
    return grouped


def _extract_sender_name(msg: dict) -> str:
    """从消息中提取发送人名称"""
    # 对于机器人卡片消息，从 title 提取
    if msg.get("msg_type") == "interactive":
        title = _extract_card_title(msg)
        if title:
            return _parse_reporter_name(title)
    # 普通消息从 sender 字段提取
    sender = msg.get("sender", {})
    name = sender.get("name", "")
    if name:
        return name
    sender_id = sender.get("id") or sender.get("sender_id", {})
    if isinstance(sender_id, dict):
        return sender_id.get("name", "未知")
    return "未知"


def _strip_card_wrapper(text: str) -> str:
    """去除卡片包装标签，提取纯文本内容"""
    # 移除 <card title="..."> 和 </card> 标签
    text = CARD_TITLE_PATTERN.sub("", text)
    text = text.replace("</card>", "").replace("<card>", "")
    # 清理空行
    return text.strip()


def _extract_message_text(msg: dict) -> str:
    """从消息中提取文本内容，支持普通消息和机器人卡片消息"""
    # P2P 机器人消息：content 字段直接是字符串
    raw_content = msg.get("content", "")
    if isinstance(raw_content, str) and raw_content:
        return _strip_card_wrapper(raw_content)

    # 普通消息：body.content 字段
    body = msg.get("body", {})
    content = body.get("content", "") if isinstance(body, dict) else ""
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                text_parts = []
                for block in parsed.get("content", []):
                    if isinstance(block, dict):
                        text_parts.append(block.get("text", ""))
                    elif isinstance(block, list):
                        for item in block:
                            if isinstance(item, dict):
                                text_parts.append(item.get("text", ""))
                return " ".join(filter(None, text_parts))
        except (json.JSONDecodeError, KeyError, TypeError):
            return content
    return str(content) if content else ""


def _is_valid_report(msg: dict) -> bool:
    """判断消息是否为有效汇报（过滤系统消息、过短消息等）"""
    msg_type = msg.get("msg_type", "")
    # 忽略系统消息
    if msg_type in ("system", "interaction", "share_chat"):
        return False

    text = _extract_message_text(msg)
    urls = extract_doc_urls(text)

    # 有文档链接的都算有效
    if urls:
        return True

    # 纯文字需达到最低字数
    if len(text.strip()) >= MIN_TEXT_LENGTH:
        return True

    return False


def _merge_same_day_messages(messages: list[dict]) -> list[dict]:
    """合并同一天同一人的多条消息为一条"""
    if not messages:
        return []

    merged = []
    current_day = ""
    current_texts: list[str] = []
    current_urls: list[str] = []
    current_msg = messages[0]

    for msg in messages:
        create_time = msg.get("create_time", "")
        day = create_time[:10] if create_time else "unknown"

        text = _extract_message_text(msg)
        urls = extract_doc_urls(text)

        if day != current_day:
            # 保存前一天的合并结果
            if current_day:
                current_msg["body"] = current_msg.get("body", {})
                current_msg["body"]["content"] = " ".join(current_texts)
                # 将 URL 信息附加
                if current_urls:
                    current_msg["body"]["content"] += " " + " ".join(current_urls)
                merged.append(current_msg)
            current_day = day
            current_msg = msg
            current_texts = [text] if text else []
            current_urls = urls
        else:
            if text:
                current_texts.append(text)
            current_urls.extend(urls)

    # 处理最后一条
    if current_texts or current_urls:
        current_msg["body"] = current_msg.get("body", {})
        current_msg["body"]["content"] = " ".join(current_texts)
        if current_urls:
            current_msg["body"]["content"] += " " + " ".join(current_urls)
        merged.append(current_msg)

    return merged


def extract_top2_per_person(grouped: dict[str, list[dict]]) -> list[PersonReports]:
    """每人取最近2条汇报，返回 PersonReports 列表"""
    results = []
    for sender_id, messages in grouped.items():
        # 过滤有效汇报
        valid = [m for m in messages if _is_valid_report(m)]
        if not valid:
            continue

        # 合并同一天的消息
        merged = _merge_same_day_messages(valid)

        # 取发送人名称（从第一条消息获取）
        sender_name = _extract_sender_name(merged[0])

        person = PersonReports(sender_name=sender_name, sender_id=sender_id)

        # 取前2条
        if len(merged) >= 1:
            person.current = _build_report_content(merged[0])
        if len(merged) >= 2:
            person.previous = _build_report_content(merged[1])

        if person.current:
            results.append(person)

    return results


def _build_report_content(msg: dict) -> ReportContent | None:
    """从消息构建 ReportContent"""
    text = _extract_message_text(msg)
    urls = extract_doc_urls(text)
    timestamp = msg.get("create_time", "")

    # 如果有文档链接，获取文档内容
    if urls:
        full_text = text
        for url in urls:
            doc_content = fetch_document(url)
            if doc_content:
                full_text += f"\n\n--- 文档内容 ---\n{doc_content}"
            else:
                logger.warning("文档获取失败，使用消息文本: %s", url)
        return ReportContent(
            text=full_text,
            source="document",
            doc_urls=urls,
            timestamp=timestamp,
        )

    # 纯文字消息
    if text.strip():
        return ReportContent(
            text=text,
            source="message",
            doc_urls=[],
            timestamp=timestamp,
        )

    return None
