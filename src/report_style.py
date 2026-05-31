"""报告样式管理器：从参考模板动态读取样式

通过解析 references/output-Demo.docx 提取：
- 页面设置（边距、纸张大小）
- 字体定义（中文字体、标题字体）
- 颜色方案（风险等级、差异类别、趋势标记）
- 表格样式（列宽、表头样式）
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union, Dict, List

from docx import Document
from docx.shared import Cm, Pt, RGBColor, Emu
from docx.oxml.ns import qn as QN

logger = logging.getLogger(__name__)

# 默认样式（当参考文件不存在时使用）
DEFAULT_COLORS = {
    "blocking": RGBColor(204, 0, 0),      # CC0000 深红
    "delayed": RGBColor(230, 120, 0),     # E67800 橙
    "resource": RGBColor(180, 130, 0),    # B48200 暗金
    "dependency": RGBColor(0, 100, 180),  # 0064B4 蓝
}

DEFAULT_DIFF_COLORS = {
    "新增": RGBColor(0, 128, 0),       # 008000 绿
    "变更": RGBColor(0, 100, 180),     # 0064B4 蓝
    "移除": RGBColor(128, 128, 128),   # 808080 灰
}

DEFAULT_TREND_MARKS = {
    "加重": "↑ 加重",
    "减轻": "↓ 减轻",
    "持平": "→ 持平",
    "新增": "● 新增",
}

RISK_LEVEL_MAP = {
    "阻塞": "blocking",
    "延期": "delayed",
    "资源": "resource",
    "依赖": "dependency",
}


@dataclass
class TableStyle:
    """表格样式定义"""
    headers: List[str] = field(default_factory=list)
    column_widths: List[Cm] = field(default_factory=list)
    header_fill: str = "D9D9D9"  # 灰底


@dataclass
class ReportStyle:
    """报告样式管理器"""
    reference_path: Optional[Path] = None
    _doc: Optional[Document] = None

    # 页面设置
    page_width: Cm = Cm(21.59)
    page_height: Cm = Cm(27.94)
    margin_left: Cm = Cm(3.17)
    margin_right: Cm = Cm(3.17)
    margin_top: Cm = Cm(2.54)
    margin_bottom: Cm = Cm(2.54)

    # 中文字体
    font_name: str = "Microsoft YaHei"
    font_name_east_asia: str = "微软雅黑"

    # 标题字体
    title_font_size: Pt = Pt(26)
    heading1_font_size: Pt = Pt(14)
    heading2_font_size: Pt = Pt(13)

    # 颜色方案
    risk_colors: Dict[str, RGBColor] = field(default_factory=lambda: {
        "阻塞": DEFAULT_COLORS["blocking"],
        "延期": DEFAULT_COLORS["delayed"],
        "资源": DEFAULT_COLORS["resource"],
        "依赖": DEFAULT_COLORS["dependency"],
    })
    diff_colors: Dict[str, RGBColor] = field(default_factory=lambda: dict(DEFAULT_DIFF_COLORS))
    trend_marks: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_TREND_MARKS))

    # 表格样式
    dep_table_style: TableStyle = field(default_factory=lambda: TableStyle(
        headers=["依赖方", "被依赖方", "依赖描述"],
        column_widths=[Cm(3.05), Cm(3.05), Cm(10.16)],
    ))
    risk_table_style: TableStyle = field(default_factory=lambda: TableStyle(
        headers=["等级", "负责人", "风险描述", "原因", "趋势", "缓解建议"],
        column_widths=[Cm(1.52), Cm(1.78), Cm(5.08), Cm(3.81), Cm(1.78), Cm(3.81)],
    ))

    # 风险排序
    risk_order: Dict[str, int] = field(default_factory=lambda: {
        "阻塞": 0, "延期": 1, "资源": 2, "依赖": 3
    })

    @classmethod
    def from_reference(cls, reference_path: Union[str, Path]) -> "ReportStyle":
        """从参考文档加载样式"""
        path = Path(reference_path)
        if not path.exists():
            logger.warning("参考文档不存在: %s，使用默认样式", path)
            return cls()

        try:
            doc = Document(path)
            style = cls(reference_path=path, _doc=doc)
            style._extract_from_doc(doc)
            logger.info("已从 %s 加载样式", path)
            return style
        except Exception as e:
            logger.warning("读取参考文档失败: %s，使用默认样式: %s", path, e)
            return cls()

    def _extract_from_doc(self, doc: Document):
        """从文档提取样式定义"""
        section = doc.sections[0]

        # 页面设置
        self.page_width = Cm(section.page_width.cm)
        self.page_height = Cm(section.page_height.cm)
        self.margin_left = Cm(section.left_margin.cm)
        self.margin_right = Cm(section.right_margin.cm)
        self.margin_top = Cm(section.top_margin.cm)
        self.margin_bottom = Cm(section.bottom_margin.cm)

        # 字体设置
        self._extract_fonts(doc)

        # 颜色方案
        self._extract_colors(doc)

        # 表格样式
        self._extract_table_styles(doc)

    def _extract_fonts(self, doc: Document):
        """提取字体定义"""
        # 从 Normal 样式获取正文字体
        if "Normal" in doc.styles:
            normal_style = doc.styles["Normal"]
            if normal_style.font.name:
                self.font_name = normal_style.font.name
            # 尝试获取东亚字体
            rpr = normal_style.element.find('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}rPr')
            if rpr is not None:
                rfonts = rpr.find('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia')
                if rfonts is not None:
                    val = rfonts.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}hAnsi')
                    if val:
                        self.font_name_east_asia = val

        # 从 Title 样式获取标题字体大小
        if "Title" in doc.styles:
            title_style = doc.styles["Title"]
            if title_style.font.size:
                self.title_font_size = Pt(title_style.font.size.pt)

        # 从 Heading 1 获取标题字体大小
        if "Heading 1" in doc.styles:
            h1_style = doc.styles["Heading 1"]
            if h1_style.font.size:
                self.heading1_font_size = Pt(h1_style.font.size.pt)

        # 从 Heading 2 获取字体大小
        if "Heading 2" in doc.styles:
            h2_style = doc.styles["Heading 2"]
            if h2_style.font.size:
                self.heading2_font_size = Pt(h2_style.font.size.pt)

    def _extract_colors(self, doc: Document):
        """提取颜色方案"""
        # 从文档内容中提取颜色定义
        colors_map: dict[str, RGBColor] = {}

        for para in doc.paragraphs:
            for run in para.runs:
                if run.font.color and run.font.color.rgb:
                    text = run.text.strip()
                    color = run.font.color.rgb

                    # 根据文本内容识别颜色用途
                    if text in ["阻塞", "延期", "资源", "依赖"]:
                        colors_map[text] = color
                    elif text in ["新增", "变更", "移除"]:
                        self.diff_colors[text] = color

        # 更新风险颜色
        for level, color in colors_map.items():
            if level in self.risk_colors:
                self.risk_colors[level] = color

    def _extract_table_styles(self, doc: Document):
        """提取表格样式"""
        for i, table in enumerate(doc.tables):
            if len(table.columns) == 3:
                # 依赖关系表
                headers = [cell.text for cell in table.rows[0].cells]
                widths = [Cm(col.width.cm) for col in table.columns]
                self.dep_table_style = TableStyle(
                    headers=headers,
                    column_widths=widths,
                )
            elif len(table.columns) == 6:
                # 风险汇总表
                headers = [cell.text for cell in table.rows[0].cells]
                widths = [Cm(col.width.cm) for col in table.columns]
                self.risk_table_style = TableStyle(
                    headers=headers,
                    column_widths=widths,
                )
                # 提取表头背景色
                for cell in table.rows[0].cells:
                    shading = cell._element.find(
                        './/{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd'
                    )
                    if shading is not None:
                        fill = shading.get(
                            '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill'
                        )
                        if fill and fill != "auto":
                            self.risk_table_style.header_fill = fill
                            self.dep_table_style.header_fill = fill
                            break

    def get_risk_color(self, level: str) -> RGBColor:
        """获取风险等级颜色"""
        return self.risk_colors.get(level, DEFAULT_COLORS["blocking"])

    def get_diff_color(self, category: str) -> RGBColor:
        """获取差异类别颜色"""
        return self.diff_colors.get(category, RGBColor(0, 100, 180))

    def get_trend_mark(self, trend: str) -> str:
        """获取趋势标记"""
        return self.trend_marks.get(trend, trend)


# 全局样式实例（延迟加载）
_style_instance: Optional[ReportStyle] = None


def get_report_style(reference_path: Optional[Union[str, Path]] = None) -> ReportStyle:
    """获取报告样式单例"""
    global _style_instance
    if _style_instance is None:
        if reference_path is None:
            # 默认路径
            ref_path = Path(__file__).parent.parent / "references" / "output-Demo.docx"
        else:
            ref_path = Path(reference_path)
        _style_instance = ReportStyle.from_reference(ref_path)
    return _style_instance


def reset_style():
    """重置样式（用于测试或强制重新加载）"""
    global _style_instance
    _style_instance = None
