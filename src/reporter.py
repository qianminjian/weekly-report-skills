"""Word 报告生成：python-docx 生成增强版中文报告

包含：风险四象限、因果关系、趋势标记、依赖关系图、整体风险评分
"""

import logging
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn as QN

from .analyzer import PersonAnalysis, RiskItem, DependencyItem

logger = logging.getLogger(__name__)

# 风险等级排序 & 色彩映射
RISK_ORDER = {"阻塞": 0, "延期": 1, "资源": 2, "依赖": 3}
RISK_COLORS = {
    "阻塞": RGBColor(204, 0, 0),      # 深红
    "延期": RGBColor(230, 120, 0),     # 橙
    "资源": RGBColor(180, 130, 0),     # 暗金
    "依赖": RGBColor(0, 100, 180),     # 蓝
}
TREND_MARKS = {
    "加重": "↑ 加重",
    "减轻": "↓ 减轻",
    "持平": "→ 持平",
    "新增": "● 新增",
}


def generate_report(
    analyses: list[PersonAnalysis],
    output_path: str | Path,
    chat_name: str = "汇报",
    dependencies: list[DependencyItem] | None = None,
    overall_risk_score: int = 0,
    overall_summary: str = "",
    key_concerns: list[str] | None = None,
) -> str:
    """生成增强版 Word 报告"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    doc = Document()
    _set_chinese_font(doc)

    # === 标题 ===
    title = doc.add_heading(f"{chat_name} 差异分析报告", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # === 副标题 ===
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle = doc.add_paragraph(f"生成时间：{now} | 分析周期：最近2次双周汇报")
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.runs[0].font.size = Pt(10)
    subtitle.runs[0].font.color.rgb = RGBColor(128, 128, 128)

    doc.add_paragraph()

    # === 一、整体摘要 ===
    doc.add_heading("一、整体摘要", level=1)

    total_people = len(analyses)
    total_diffs = sum(len(a.diffs) for a in analyses)
    total_risks = sum(len(a.risks) for a in analyses)

    # 风险四象限统计
    blocking = sum(1 for a in analyses for r in a.risks if r.level == "阻塞")
    delayed = sum(1 for a in analyses for r in a.risks if r.level == "延期")
    resource = sum(1 for a in analyses for r in a.risks if r.level == "资源")
    dependency = sum(1 for a in analyses for r in a.risks if r.level == "依赖")

    summary_text = (
        f"本期共 {total_people} 人汇报，"
        f"{total_diffs} 项关键差异，"
        f"{total_risks} 项风险点需关注"
    )
    doc.add_paragraph(summary_text)

    # 风险分布
    if total_risks > 0:
        p = doc.add_paragraph()
        p.add_run("风险分布：").bold = True
        p.add_run(f" 阻塞×{blocking}  延期×{delayed}  资源×{resource}  依赖×{dependency}")

    # 整体风险评分
    if overall_risk_score > 0:
        p = doc.add_paragraph()
        p.add_run(f"整体风险评分：{overall_risk_score}/5  ")
        if overall_risk_score >= 4:
            run = p.add_run("⚠️ 高风险")
            run.font.color.rgb = RGBColor(204, 0, 0)
        elif overall_risk_score >= 3:
            run = p.add_run("⚡ 中等风险")
            run.font.color.rgb = RGBColor(230, 120, 0)
        else:
            run = p.add_run("✓ 低风险")
            run.font.color.rgb = RGBColor(0, 128, 0)

    if overall_summary:
        doc.add_paragraph(overall_summary)

    # 重点关注
    if key_concerns:
        doc.add_heading("重点关注事项", level=2)
        for concern in key_concerns:
            p = doc.add_paragraph(style="List Bullet")
            run = p.add_run("⚠ ")
            run.font.color.rgb = RGBColor(204, 0, 0)
            p.add_run(concern)

    # === 二、依赖关系图 ===
    if dependencies:
        doc.add_heading("二、跨人依赖关系", level=1)
        dep_table = doc.add_table(rows=1, cols=3, style="Table Grid")
        dep_table.columns[0].width = Inches(1.2)
        dep_table.columns[1].width = Inches(1.2)
        dep_table.columns[2].width = Inches(4.0)

        hdr = dep_table.rows[0].cells
        hdr[0].text = "依赖方"
        hdr[1].text = "被依赖方"
        hdr[2].text = "依赖描述"

        for dep in dependencies:
            row = dep_table.add_row().cells
            row[0].text = dep.from_person
            row[1].text = dep.to_person
            row[2].text = dep.description

        doc.add_paragraph()

    # === 三、各人汇报分析 ===
    section_num = 3 if dependencies else 2
    doc.add_heading(f"{'一二三四五六七八九十'[section_num-1]}、各人汇报分析", level=1)

    for analysis in analyses:
        _add_person_section(doc, analysis)

    # === 四 / 三、风险汇总 ===
    section_num += 1
    doc.add_heading(f"{'一二三四五六七八九十'[section_num-1]}、风险汇总", level=1)

    all_risks: list[tuple[str, RiskItem]] = []
    for analysis in analyses:
        for risk in analysis.risks:
            all_risks.append((analysis.person_name, risk))

    all_risks.sort(key=lambda x: RISK_ORDER.get(x[1].level, 99))

    if all_risks:
        table = doc.add_table(rows=1, cols=6, style="Table Grid")
        table.columns[0].width = Inches(0.6)
        table.columns[1].width = Inches(0.7)
        table.columns[2].width = Inches(2.0)
        table.columns[3].width = Inches(1.5)
        table.columns[4].width = Inches(0.7)
        table.columns[5].width = Inches(1.5)

        hdr = table.rows[0].cells
        for i, label in enumerate(["等级", "负责人", "风险描述", "原因", "趋势", "缓解建议"]):
            hdr[i].text = label

        for person_name, risk in all_risks:
            row = table.add_row().cells
            row[0].text = risk.level
            # 风险等级着色
            for p in row[0].paragraphs:
                for run in p.runs:
                    run.font.color.rgb = RISK_COLORS.get(risk.level, RGBColor(0, 0, 0))
                    run.bold = True
            row[1].text = person_name
            row[2].text = risk.content
            row[3].text = risk.cause or "-"
            row[4].text = TREND_MARKS.get(risk.trend, risk.trend) if risk.trend else "-"
            row[5].text = risk.suggestion or "-"
    else:
        doc.add_paragraph("本期无风险点。")

    doc.save(str(output_path))
    logger.info("报告已生成: %s", output_path)
    return str(output_path)


def _add_person_section(doc: Document, analysis: PersonAnalysis):
    """添加单人汇报分析段落（增强版）"""
    heading_text = analysis.person_name
    if analysis.is_first_report:
        heading_text += "（首次汇报）"
    doc.add_heading(heading_text, level=2)

    # 摘要
    if analysis.summary:
        p = doc.add_paragraph()
        p.add_run("摘要：").bold = True
        p.add_run(analysis.summary)

    # 关键差异
    if analysis.diffs:
        doc.add_paragraph("关键差异：", style="List Bullet")
        for diff in analysis.diffs:
            p = doc.add_paragraph(style="List Bullet 2")
            run = p.add_run(f"[{diff.category}] ")
            run.bold = True
            # 差异类型着色
            if diff.category == "新增":
                run.font.color.rgb = RGBColor(0, 128, 0)
            elif diff.category == "移除":
                run.font.color.rgb = RGBColor(128, 128, 128)
            elif diff.category == "变更":
                run.font.color.rgb = RGBColor(0, 100, 180)
            p.add_run(diff.content)
            if diff.impact:
                p2 = doc.add_paragraph(style="List Bullet 2")
                p2.add_run(f"    影响：{diff.impact}").font.size = Pt(9)

    # 风险点
    if analysis.risks:
        doc.add_paragraph("风险点：", style="List Bullet")
        for risk in analysis.risks:
            # 风险等级标题行
            p = doc.add_paragraph(style="List Bullet 2")
            run = p.add_run(f"[{risk.level}] ")
            run.bold = True
            run.font.color.rgb = RISK_COLORS.get(risk.level, RGBColor(204, 0, 0))

            # 趋势标记
            if risk.trend:
                trend_text = TREND_MARKS.get(risk.trend, risk.trend)
                run2 = p.add_run(f" {trend_text} ")
                run2.font.size = Pt(9)

            p.add_run(risk.content)

            # 原因
            if risk.cause:
                p2 = doc.add_paragraph(style="List Bullet 2")
                p2.add_run(f"    原因：{risk.cause}").font.size = Pt(9)

            # 缓解建议
            if risk.suggestion:
                p3 = doc.add_paragraph(style="List Bullet 2")
                p3.add_run(f"    建议：{risk.suggestion}").font.size = Pt(9)

            # 依赖对象
            if risk.depends_on:
                p4 = doc.add_paragraph(style="List Bullet 2")
                p4.add_run(f"    依赖方：{', '.join(risk.depends_on)}").font.size = Pt(9)


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
