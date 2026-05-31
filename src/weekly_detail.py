"""周末三天汇报原文提取与 Word 导出

功能：
  - 基于当前时间，自动确定目标周末窗口（周五/周六/周日）
  - 提取该窗口内所有人的汇报原文，不做任何删减
  - 合并为一个 Word 文档输出，文件名以 weekly-Detail 为前缀，带版本号
"""

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn as QN

from .fetcher import fetch_document, extract_doc_urls
from .parser import (
    group_by_sender,
    _extract_card_title,
    _parse_reporter_name,
    _is_system_title,
    _extract_message_text,
    _extract_sender_name,
    _strip_card_wrapper,
    _is_valid_report,
    _merge_same_day_messages,
)

logger = logging.getLogger(__name__)

# 风险等级排序 & 色彩映射（复用自 reporter.py）
RISK_COLORS = {
    "阻塞": RGBColor(204, 0, 0),
    "延期": RGBColor(230, 120, 0),
    "资源": RGBColor(180, 130, 0),
    "依赖": RGBColor(0, 100, 180),
}


def _calc_weekend_window(now: datetime) -> tuple[datetime, datetime]:
    """根据当前时间计算目标周末窗口

    - 周一 → 取上周五六日
    - 周二三四五 → 取上周五六日
    - 周六/周日 → 取本周五六日（截止到当前时间）
    返回 (start, end)，其中 end 不会超过 now
    """
    weekday = now.weekday()  # Mon=0, Sun=6

    if weekday == 0:
        # 周一：取上周末（已过去）
        # 上周五 = now - 3 天
        fri = now - timedelta(days=3)
    elif weekday == 5 or weekday == 6:
        # 周六/周日：取本周（尚未完全结束）
        days_since_fri = (weekday - 4)  # Sat=1, Sun=2
        fri = now - timedelta(days=days_since_fri)
    else:
        # 周二~周五：取上周五六日
        fri = now - timedelta(days=weekday + 3)

    sat = fri + timedelta(days=1)
    sun = fri + timedelta(days=2)

    # 结束时间不超过当前
    end = now if now < sun else sun.replace(hour=23, minute=59, second=59)
    return fri.replace(hour=0, minute=0, second=0), end


def _msg_in_window(msg: dict, start: datetime, end: datetime) -> bool:
    """判断消息是否在目标时间窗口内"""
    ts_str = msg.get("create_time", "")
    if not ts_str:
        return False
    try:
        # 飞书时间格式: 2026-05-29T10:30:00+08:00
        msg_time = datetime.fromisoformat(ts_str.replace("+08:00", "+0000"))
        msg_time = msg_time.replace(tzinfo=None)  # 去掉时区，转本地 naive
    except ValueError:
        try:
            msg_time = datetime.strptime(ts_str[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return False
    return start <= msg_time <= end


def _get_full_content(msg: dict) -> str:
    """获取消息完整内容（含文档原文），不做任何截断"""
    text = _extract_message_text(msg)
    urls = extract_doc_urls(text)

    if not urls:
        return text

    full_parts = [text] if text else []
    for url in urls:
        doc_content = fetch_document(url)
        if doc_content:
            full_parts.append(f"\n--- 文档内容 ---\n{doc_content}")
        else:
            full_parts.append(f"\n--- 文档链接（获取失败）---\n{url}")

    return "\n".join(full_parts)


def _next_detail_version(output_dir: Path, base_name: str, ext: str) -> Path:
    """生成 weekly-Detail-vN.docx 形式带版本号的路径"""
    pattern = re.compile(rf"{re.escape(base_name)}-v(\d+)\.{re.escape(ext)}")
    max_v = 0
    if output_dir.exists():
        for f in output_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                max_v = max(max_v, int(m.group(1)))
    return output_dir / f"{base_name}-v{max_v + 1}.{ext}"


def generate_weekend_detail(messages: list[dict], output_dir: Path) -> str | None:
    """提取周末三天汇报原文，生成 Word 文档

    Args:
        messages: 来自 list_messages() 的完整消息列表
        output_dir: 输出目录（通常是 Weekly-Report-yyyy-mm-dd/）

    Returns:
        生成的 Word 文件路径，失败返回 None
    """
    now = datetime.now()
    start, end = _calc_weekend_window(now)

    logger.info("周末窗口: %s ~ %s", start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    # 过滤目标窗口内的消息
    window_msgs = [m for m in messages if _msg_in_window(m, start, end)]
    if not window_msgs:
        logger.warning("周末窗口内无汇报消息: %s ~ %s", start.date(), end.date())
        return None

    logger.info("窗口内消息数: %d 条", len(window_msgs))

    # 按人分组（复用 parser 的 group_by_sender，但不过滤人数）
    grouped = group_by_sender(window_msgs)

    # 构建每人该窗口内的完整汇报内容
    sections: list[tuple[str, str]] = []  # (姓名, 合并后内容)

    for sender_id, msgs in grouped.items():
        valid = [m for m in msgs if _is_valid_report(m)]
        if not valid:
            continue

        merged = _merge_same_day_messages(valid)
        sender_name = _extract_sender_name(merged[0])

        # 合并同一人多天的内容
        full_text_parts: list[str] = []
        for msg in merged:
            day_text = _get_full_content(msg)
            if day_text:
                day_label = msg.get("create_time", "")[:10]
                full_text_parts.append(f"=== {day_label} ===\n{day_text}")

        if full_text_parts:
            sections.append((sender_name, "\n\n".join(full_text_parts)))

    if not sections:
        logger.warning("周末窗口内无有效汇报内容")
        return None

    # 生成 Word 文档
    doc = Document()
    _set_chinese_font(doc)

    # 标题
    title = doc.add_heading("周末三天汇报原文", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # 副标题
    date_range = f"{start.strftime('%Y-%m-%d')} ~ {end.strftime('%Y-%m-%d')}"
    subtitle = doc.add_paragraph(
        f"生成时间：{now.strftime('%Y-%m-%d %H:%M')}  |  周末窗口：{date_range}  |  共 {len(sections)} 人"
    )
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.size = Pt(10)
    subtitle.runs[0].font.color.rgb = RGBColor(128, 128, 128)

    doc.add_paragraph()

    # 正文：每人一个二级标题 + 原文内容
    for name, content in sections:
        doc.add_heading(name, level=2)
        doc.add_paragraph(content)

    # 保存
    base_name = "weekly-Detail"
    output_path = _next_detail_version(output_dir, base_name, "docx")
    doc.save(str(output_path))

    logger.info("周末详情报告已生成: %s", output_path)
    return str(output_path)


def _set_chinese_font(doc: Document):
    """设置文档默认中文字体"""
    style = doc.styles["Normal"]
    font = style.font
    font.name = "Microsoft YaHei"
    rPr = style.element.get_or_add_rPr()
    rFonts = rPr.find(QN("w:rFonts"))
    if rFonts is None:
        rFonts = doc.element.makeelement(QN("w:rFonts"), {})
        rPr.append(rFonts)
    rFonts.set(QN("w:eastAsia"), "Microsoft YaHei")
