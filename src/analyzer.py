"""AI 对比分析：差异点、风险点、摘要 — 数据类定义与序列化"""

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 数据类定义
# ============================================================

@dataclass
class DiffItem:
    """差异项"""
    category: str       # "新增" | "变更" | "移除"
    content: str        # 具体描述
    impact: str = ""    # 影响评估（可选）


@dataclass
class RiskItem:
    """风险项 — 增强版，包含原因、建议、趋势"""
    level: str          # "阻塞" | "延期" | "资源" | "依赖"
    content: str        # 风险描述
    cause: str = ""     # 风险原因
    suggestion: str = ""  # 缓解建议
    trend: str = ""     # "加重" | "减轻" | "持平" | "新增"
    depends_on: list[str] = field(default_factory=list)  # 依赖对象列表


@dataclass
class DependencyItem:
    """跨人依赖关系"""
    from_person: str    # 依赖方
    to_person: str      # 被依赖方
    description: str    # 依赖描述（如"等待接口联调"）


@dataclass
class PersonAnalysis:
    """单人分析结果"""
    person_name: str
    diffs: list[DiffItem] = field(default_factory=list)
    risks: list[RiskItem] = field(default_factory=list)
    summary: str = ""
    is_first_report: bool = False


@dataclass
class OverallAnalysis:
    """整体分析结果"""
    analyses: list[PersonAnalysis] = field(default_factory=list)
    dependencies: list[DependencyItem] = field(default_factory=list)
    overall_risk_score: int = 0  # 1-5 分
    overall_summary: str = ""    # 整体评估摘要
    key_concerns: list[str] = field(default_factory=list)  # 需重点关注的事项


# ============================================================
# 序列化 / 反序列化（Agent ↔ Python 交接格式）
# ============================================================

def analyses_to_dict(overall: OverallAnalysis) -> dict:
    """将 OverallAnalysis 转为可 JSON 序列化的字典"""
    return {
        "analyses": [
            {
                "person_name": a.person_name,
                "is_first_report": a.is_first_report,
                "summary": a.summary,
                "diffs": [
                    {"category": d.category, "content": d.content, "impact": d.impact}
                    for d in a.diffs
                ],
                "risks": [
                    {
                        "level": r.level,
                        "content": r.content,
                        "cause": r.cause,
                        "suggestion": r.suggestion,
                        "trend": r.trend,
                        "depends_on": r.depends_on,
                    }
                    for r in a.risks
                ],
            }
            for a in overall.analyses
        ],
        "dependencies": [
            {
                "from_person": d.from_person,
                "to_person": d.to_person,
                "description": d.description,
            }
            for d in overall.dependencies
        ],
        "overall_risk_score": overall.overall_risk_score,
        "overall_summary": overall.overall_summary,
        "key_concerns": overall.key_concerns,
    }


def dict_to_analyses(data: dict) -> OverallAnalysis:
    """从字典还原 OverallAnalysis"""
    analyses = []
    for a in data.get("analyses", []):
        analyses.append(PersonAnalysis(
            person_name=a["person_name"],
            is_first_report=a.get("is_first_report", False),
            summary=a.get("summary", ""),
            diffs=[
                DiffItem(
                    category=d.get("category", "变更"),
                    content=d.get("content", ""),
                    impact=d.get("impact", ""),
                )
                for d in a.get("diffs", [])
            ],
            risks=[
                RiskItem(
                    level=r.get("level", "延期"),
                    content=r.get("content", ""),
                    cause=r.get("cause", ""),
                    suggestion=r.get("suggestion", ""),
                    trend=r.get("trend", ""),
                    depends_on=r.get("depends_on", []),
                )
                for r in a.get("risks", [])
            ],
        ))

    deps = [
        DependencyItem(
            from_person=d["from_person"],
            to_person=d["to_person"],
            description=d.get("description", ""),
        )
        for d in data.get("dependencies", [])
    ]

    return OverallAnalysis(
        analyses=analyses,
        dependencies=deps,
        overall_risk_score=data.get("overall_risk_score", 0),
        overall_summary=data.get("overall_summary", ""),
        key_concerns=data.get("key_concerns", []),
    )


def parse_ai_result(person_name: str, result_str: str) -> PersonAnalysis:
    """从 Agent 返回的 JSON 字符串解析单人分析结果"""
    json_str = _extract_json(result_str)
    if not json_str:
        logger.warning("无法从 Agent 返回中提取 JSON: %s", result_str[:200])
        return PersonAnalysis(person_name=person_name, summary="分析结果解析失败")

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning("Agent 返回非 JSON: %s", result_str[:200])
        return PersonAnalysis(person_name=person_name, summary="分析结果解析失败")

    diffs = [
        DiffItem(
            category=d.get("category", "变更"),
            content=d.get("content", ""),
            impact=d.get("impact", ""),
        )
        for d in data.get("diffs", [])
        if d.get("content")
    ]

    risks = [
        RiskItem(
            level=r.get("level", "延期"),
            content=r.get("content", ""),
            cause=r.get("cause", ""),
            suggestion=r.get("suggestion", ""),
            trend=r.get("trend", ""),
            depends_on=r.get("depends_on", []),
        )
        for r in data.get("risks", [])
        if r.get("content")
    ]

    return PersonAnalysis(
        person_name=person_name,
        diffs=diffs,
        risks=risks,
        summary=data.get("summary", ""),
        is_first_report=data.get("is_first_report", False),
    )


def _extract_json(text: str) -> str | None:
    """从文本中提取 JSON 块"""
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return None
