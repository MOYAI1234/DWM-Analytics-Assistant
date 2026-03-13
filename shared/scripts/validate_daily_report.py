#!/usr/bin/env python3
"""
validate_daily_report.py
Pre-archive quality gate for daily report markdown.
Only validates hard constraints; does not judge writing style.
"""

import argparse
import json
import re
from pathlib import Path


REQUIRED_SECTIONS = [
    "今日核心看板",
    "基础补充",
    "机台参与与产出异常",
    "内购与生命周期结构",
    "资源经济",
    "投放与回收",
    "广告变现监控",
    "大R风险快照",
    "风险清单与明日动作",
]


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"file not found: {path}")
    # utf-8-sig: 自动去除可能存在的 UTF-8 BOM，保证 shebang 和 json.loads 不受影响
    return path.read_text(encoding="utf-8-sig")


def has_lifecycle_buckets(text: str) -> bool:
    patterns = [
        r"0\s*[-~]\s*30\s*天",
        r"30\s*[-~]\s*120\s*天",
        r"120\s*天\s*\+",
        r"120\s*天以上",
    ]
    hit_0_30 = re.search(patterns[0], text) is not None
    hit_30_120 = re.search(patterns[1], text) is not None
    hit_120_plus = re.search(patterns[2], text) is not None or re.search(patterns[3], text) is not None
    return hit_0_30 and hit_30_120 and hit_120_plus


def count_tomorrow_actions(text: str) -> int:
    # Prefer counting actionable list items in the "明日动作" neighborhood.
    lines = text.splitlines()
    idx = -1
    for i, ln in enumerate(lines):
        if "明日动作" in ln:
            idx = i
            break
    if idx == -1:
        return 0

    window = lines[idx : min(idx + 40, len(lines))]
    cnt = 0
    for ln in window:
        s = ln.strip()
        if re.match(r"^[-*]\s+", s):
            cnt += 1
        elif re.match(r"^\d+\.\s+", s):
            cnt += 1
    return cnt


def _section_headings(text: str) -> set:
    """Return the set of words found in markdown heading lines (## / ###)."""
    headings: set = set()
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#"):
            # Remove leading '#' chars and whitespace to get the heading text
            heading_text = stripped.lstrip("#").strip()
            headings.add(heading_text)
    return headings


def _extract_section(text: str, section_name: str) -> str:
    """Return the content between *section_name* heading and the next same-level heading."""
    lines = text.splitlines()
    start = -1
    heading_prefix = ""
    for i, ln in enumerate(lines):
        stripped = ln.lstrip()
        if stripped.startswith("#") and section_name in stripped:
            # Capture the '#' prefix to detect next heading at same or higher level
            heading_prefix = stripped[: len(stripped) - len(stripped.lstrip("#"))]
            start = i + 1
            break
    if start == -1:
        return ""
    result = []
    level = len(heading_prefix)
    for ln in lines[start:]:
        stripped = ln.lstrip()
        if stripped.startswith("#"):
            this_level = len(stripped) - len(stripped.lstrip("#"))
            if this_level <= level:
                break
        result.append(ln)
    return "\n".join(result)


def validate_markdown(report_text: str):
    errors = []
    warnings = []

    # Check sections by heading lines only, not arbitrary substring match
    headings = _section_headings(report_text)
    missing_sections = [s for s in REQUIRED_SECTIONS if not any(s in h for h in headings)]
    if missing_sections:
        errors.append(f"missing sections: {', '.join(missing_sections)}")

    # D-1 / D-7 must appear inside the "资源经济" section, not just anywhere in the file
    resource_section = _extract_section(report_text, "资源经济")
    if not resource_section:
        errors.append("section '资源经济' not found; cannot check D-1/D-7 markers")
    else:
        if "D-1" not in resource_section:
            errors.append("resource/compare text missing D-1 marker inside '资源经济' section")
        if "D-7" not in resource_section:
            errors.append("resource/compare text missing D-7 marker inside '资源经济' section")

    if not has_lifecycle_buckets(report_text):
        errors.append("lifecycle buckets missing required 0-30 / 30-120 / 120+ structure")

    for top_tag in ["Top1", "Top2", "Top3"]:
        if top_tag not in report_text:
            errors.append(f"risk priority marker missing: {top_tag}")

    action_count = count_tomorrow_actions(report_text)
    if action_count < 3:
        errors.append(f"tomorrow actions too few: {action_count} (<3)")
    elif action_count < 5:
        warnings.append(f"tomorrow actions count is {action_count}; recommended 3-5")

    return errors, warnings


def validate_snapshot(snapshot: dict):
    errors = []
    warnings = []

    coverage = snapshot.get("_coverage", [])
    required_bad = [
        c for c in coverage if c.get("required") and c.get("status") in ("missing", "parse_error")
    ]
    if required_bad:
        names = [f"{x.get('csv_key')}({x.get('status')})" for x in required_bad]
        errors.append("snapshot required coverage failed: " + ", ".join(names))

    res = snapshot.get("resource", {})
    for metric in ["consume_total", "grant_total", "net_consume"]:
        node = res.get(metric, {}) if isinstance(res, dict) else {}
        if not isinstance(node, dict):
            errors.append(f"snapshot resource.{metric} is invalid")
            continue
        for key in ["current", "d1", "d7", "chg_d1", "chg_d7"]:
            if key not in node:
                errors.append(f"snapshot resource.{metric}.{key} missing")

    if snapshot.get("_warnings"):
        warnings.append(f"snapshot has warnings: {len(snapshot.get('_warnings', []))}")

    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description="Validate daily report hard constraints before archive")
    ap.add_argument("--report", required=True, help="Path to markdown report (wip/final)")
    ap.add_argument("--snapshot", required=True, help="Path to daily_snapshot.json")
    ap.add_argument("--output", default="", help="Optional output json path")
    args = ap.parse_args()

    report_path = Path(args.report)
    snapshot_path = Path(args.snapshot)

    report_text = read_text(report_path)
    try:
        snapshot = json.loads(read_text(snapshot_path))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[ERROR] snapshot JSON is invalid: {exc}") from exc

    md_errors, md_warnings = validate_markdown(report_text)
    sp_errors, sp_warnings = validate_snapshot(snapshot)

    errors = md_errors + sp_errors
    warnings = md_warnings + sp_warnings

    result = {
        "ok": len(errors) == 0,
        "report": str(report_path),
        "snapshot": str(snapshot_path),
        "errors": errors,
        "warnings": warnings,
    }

    output_json = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
    print(output_json)

    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
