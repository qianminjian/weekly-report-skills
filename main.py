"""飞书汇报差异分析 - 主入口

双阶段流水线：
  collect → 数据采集，输出 JSON 供 Agent 分析
  report  → 读取 Agent 分析结果，生成 Word 报告
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from src.fetcher import find_report_chat, list_messages
from src.parser import group_by_sender, extract_top2_per_person
from src.analyzer import OverallAnalysis, PersonAnalysis, dict_to_analyses
from src.reporter import generate_report
from src.weekly_detail import generate_weekend_detail

logger = logging.getLogger(__name__)


def _resolve_workspace(arg_workspace: str | None) -> Path | None:
    """三层优先级解析工作区路径：

    1. CLI 参数 --workspace（run.sh 传入）
    2. SKILL_WORKSPACE 环境变量（WorkBuddy 等平台设置）
    3. None（fallback 到 Path.cwd()，通常指向技能安装目录，需避免）

    详见 SKILL.md「工作区路径」章节。
    """
    if arg_workspace:
        return Path(arg_workspace)
    env_ws = os.environ.get("SKILL_WORKSPACE")
    if env_ws:
        return Path(env_ws)
    return None


def setup_logging(workspace: Path | None = None):
    """配置日志"""
    base = workspace if workspace is not None else Path(__file__).parent
    log_dir = base / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _get_output_dir(date_str: str | None = None, workspace: Path | None = None) -> Path:
    """返回输出目录 'Weekly-Report-yyyy-mm-dd/'（位于 workspace 下，默认为 CWD）"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    base = workspace if workspace is not None else Path.cwd()
    return base / f"Weekly-Report-{date_str}"


def _next_version(output_dir: Path, date_str: str, ext: str) -> Path:
    """生成带递增版本号的文件路径

    扫描目录内已有的 Weekly-Report-ImportInfo-{date}-vN.{ext} 文件，
    返回下一个版本号的文件路径。

    示例:
      v1.docx 不存在 → Weekly-Report-ImportInfo-2026-05-31-v1.docx
      v1.docx 已存在 → Weekly-Report-ImportInfo-2026-05-31-v2.docx
    """
    prefix = "Weekly-Report-ImportInfo"
    pattern = re.compile(
        rf"{re.escape(prefix)}-{re.escape(date_str)}-v(\d+)\.{re.escape(ext)}"
    )
    max_v = 0
    if output_dir.exists():
        for f in output_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                max_v = max(max_v, int(m.group(1)))
    return output_dir / f"{prefix}-{date_str}-v{max_v + 1}.{ext}"


def cmd_collect(args):
    """Phase 1: 数据采集 → 输出 analysis_data.json"""
    logging.info("=== Phase 1: 数据采集 ===")
    logging.info("输入: %s, 回溯: %d 周", args.chat_name or "自动", args.weeks)

    # Step 1: 定位汇报对话（固定从「消息→汇报」路径拉取）
    chat_id = args.chat_id
    if not chat_id:
        chat_id = find_report_chat()
        if not chat_id:
            logging.error(
                "未找到汇报对话。请确认：\n"
                "  1) 飞书「消息→汇报」下有汇报消息\n"
                "  2) lark-cli 已认证（运行 lark-cli auth status 检查）\n"
                "  也可通过 --chat-id 直接指定对话 ID"
            )
            sys.exit(1)

    # Step 2: 拉取消息
    messages = list_messages(chat_id, weeks=args.weeks)
    if not messages:
        logging.error("未拉取到任何消息，请检查对话 ID 或回溯时间范围")
        sys.exit(1)

    # Step 3: 按人分组，取最近2条
    grouped = group_by_sender(messages)
    person_reports = extract_top2_per_person(grouped)

    if not person_reports:
        logging.error("无可分析的汇报消息")
        sys.exit(1)

    logging.info("共找到 %d 人的汇报", len(person_reports))

    # Step 4: 构建采集数据，输出为 JSON
    persons_data = []
    for person in person_reports:
        entry = {
            "name": person.sender_name,
            "sender_id": person.sender_id,
        }
        if person.current:
            entry["current"] = {
                "text": person.current.text,
                "source": person.current.source,
                "timestamp": person.current.timestamp,
                "doc_urls": person.current.doc_urls,
            }
        else:
            entry["current"] = None

        if person.previous:
            entry["previous"] = {
                "text": person.previous.text,
                "source": person.previous.source,
                "timestamp": person.previous.timestamp,
                "doc_urls": person.previous.doc_urls,
            }
        else:
            entry["previous"] = None

        persons_data.append(entry)

    output_data = {
        "source": "飞书消息→汇报",  # 数据来源固定为「消息→汇报」路径
        "collected_at": datetime.now().isoformat(),
        "persons": persons_data,
    }

    # 输出到 Weekly-Report-yyyy-mm-dd/ 目录
    workspace = _resolve_workspace(args.workspace)
    if args.output:
        output_path = Path(args.output)
    else:
        output_dir = _get_output_dir(workspace=workspace)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "analysis_data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_data, ensure_ascii=False, indent=2), encoding="utf-8")

    logging.info("数据采集完成 → %s", output_path)
    print(f"\n数据采集完成: {output_path}")
    print(f"共 {len(persons_data)} 人汇报，请交给 Agent 进行 AI 分析。")

    # 周末详情报告（不影响原有分析流程）
    if args.output:
        detail_output_dir = Path(args.output).parent
    else:
        detail_output_dir = _get_output_dir(workspace=workspace)

    detail_path = generate_weekend_detail(messages, detail_output_dir)
    if detail_path:
        print(f"周末详情报告已生成: {detail_path}")
    else:
        print("周末窗口内无汇报内容，跳过详情报告。")


def cmd_report(args):
    """Phase 3: 读取分析结果 → 生成 Word 报告"""
    logging.info("=== Phase 3: 报告生成 ===")

    # 读取 Agent 分析结果 JSON
    input_path = Path(args.input)
    if not input_path.exists():
        logging.error("分析结果文件不存在: %s", input_path)
        sys.exit(1)

    raw = input_path.read_text(encoding="utf-8")
    data = json.loads(raw)

    overall = dict_to_analyses(data)
    analyses = overall.analyses

    if not analyses:
        logging.error("分析结果为空")
        sys.exit(1)

    logging.info("加载 %d 人分析结果，%d 条依赖关系", len(analyses), len(overall.dependencies))

    # 生成 Word 报告 → Weekly-Report-yyyy-mm-dd/ 目录，版本号递增
    date_str = datetime.now().strftime("%Y-%m-%d")
    workspace = _resolve_workspace(args.workspace)

    if args.output:
        output_path = args.output
    else:
        output_dir = _get_output_dir(date_str, workspace=workspace)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(_next_version(output_dir, date_str, "docx"))

    result = generate_report(
        analyses,
        output_path,
        chat_name=args.chat_name,
        dependencies=overall.dependencies,
        overall_risk_score=overall.overall_risk_score,
        overall_summary=overall.overall_summary,
        key_concerns=overall.key_concerns,
    )

    logging.info("报告已生成: %s", result)
    print(f"\n报告已生成: {result}")
    print(f"版本号: {Path(result).stem}")

    # 清理中间 JSON 文件（除非 --keep-json）
    if not args.keep_json:
        output_dir = Path(result).parent
        json_files = list(output_dir.glob("*.json"))
        for jf in json_files:
            try:
                jf.unlink()
                logging.info("已清理中间文件: %s", jf)
                print(f"已清理: {jf.name}")
            except OSError as e:
                logging.warning("清理文件失败 %s: %s", jf, e)


def cmd_detail(args):
    """提取周五/六/日三天汇报原文，生成 Word 附件"""
    logging.info("=== 周末详情提取 ===")

    chat_id = args.chat_id
    if not chat_id:
        chat_id = find_report_chat()
        if not chat_id:
            logging.error("未找到汇报对话，请通过 --chat-id 指定")
            sys.exit(1)

    # 拉取消息（时间窗口由 generate_weekend_detail 内部过滤）
    messages = list_messages(chat_id, weeks=args.weeks)
    if not messages:
        logging.error("未拉取到任何消息")
        sys.exit(1)

    workspace = _resolve_workspace(args.workspace)
    output_dir = Path(args.output_dir) if args.output_dir else _get_output_dir(workspace=workspace)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = generate_weekend_detail(messages, output_dir)
    if result:
        print(f"\n周末详情报告已生成: {result}")
    else:
        print("\n周末窗口内无汇报内容，未生成详情报告。")


def main():
    # 预解析 --workspace 以初始化日志到正确目录
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--workspace", default=None)
    pre_args, _ = pre_parser.parse_known_args()
    workspace = _resolve_workspace(pre_args.workspace)
    setup_logging(workspace)

    parser = argparse.ArgumentParser(description="飞书汇报差异分析（双阶段流水线）")
    parser.add_argument("--workspace", default=None, help="工作目录（输出路径的基准目录，默认：当前目录）")
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # ---- collect 子命令 ----
    collect_parser = subparsers.add_parser("collect", help="数据采集：从「消息→汇报」拉取汇报 → 输出 JSON")
    collect_parser.add_argument("--chat-name", default=None, help="对话名称（可选，默认自动定位「消息→汇报」路径）")
    collect_parser.add_argument("--chat-id", default=None, help="对话 ID（优先于自动定位）")
    collect_parser.add_argument("--weeks", type=int, default=8, help="回溯周数（默认：8）")
    collect_parser.add_argument("--output", default=None, help="输出 JSON 路径（默认：Weekly-Report-yyyy-mm-dd/analysis_data.json）")
    collect_parser.set_defaults(func=cmd_collect)

    # ---- report 子命令 ----
    report_parser = subparsers.add_parser("report", help="生成报告：读取分析 JSON → 生成 Word 报告")
    report_parser.add_argument("input", help="Agent 分析结果 JSON 文件路径")
    report_parser.add_argument("--chat-name", default="汇报", help="数据来源名称（用于报告标题）")
    report_parser.add_argument("--output", default=None, help="输出 Word 路径（默认：Weekly-Report-yyyy-mm-dd/Weekly-Report-ImportInfo-yyyy-mm-dd-vN.docx）")
    report_parser.add_argument("--keep-json", action="store_true", help="保留中间 JSON 文件（默认清理）")
    report_parser.set_defaults(func=cmd_report)

    # ---- detail 子命令 ----
    detail_parser = subparsers.add_parser("detail", help="周末详情：提取周五/六/日三天汇报原文，生成 Word 附件")
    detail_parser.add_argument("--chat-id", default=None, help="对话 ID（优先于自动定位）")
    detail_parser.add_argument("--weeks", type=int, default=8, help="回溯周数（默认：8，确保能覆盖到目标周末）")
    detail_parser.add_argument("--output-dir", default=None, help="输出目录（默认：Weekly-Report-yyyy-mm-dd/）")
    detail_parser.set_defaults(func=cmd_detail)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
