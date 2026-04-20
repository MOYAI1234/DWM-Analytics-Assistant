# data_extractor.py
# 职责：读取版本 CSV 数据，聚合成结构化 JSON，供 Claude 读取分析
# 用法：python data_extractor.py --folder <路径> --start <日期> --end <日期> --output <json路径>

import argparse
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')
from datetime import date, datetime
from data_loader import load_all_data
import numpy as np


def _make_serializable(all_data):
    """
    把 all_data 转为可 JSON 序列化的纯 Python 结构。
    跳过 _meta、DataFrame（raw_current）、None 值。
    """
    import pandas as pd
    result = {}
    for report_key, report_val in all_data.items():
        if report_key == "_meta":
            continue
        if not isinstance(report_val, dict):
            continue
        cleaned = {}
        for section_key, section_val in report_val.items():
            # 跳过 DataFrame
            if isinstance(section_val, pd.DataFrame):
                continue
            if isinstance(section_val, dict):
                # 递归清理嵌套 dict
                inner = {}
                for k, v in section_val.items():
                    if isinstance(v, pd.DataFrame):
                        continue
                    if isinstance(v, dict):
                        inner[k] = {
                            kk: (_safe(vv) if not isinstance(vv, dict) else
                                 {kkk: _safe(vvv) for kkk, vvv in vv.items()})
                            for kk, vv in v.items()
                        }
                    elif isinstance(v, (int, float, str, type(None))):
                        inner[k] = _safe(v)
                    else:
                        inner[k] = _safe(v)
                cleaned[section_key] = inner
            elif isinstance(section_val, (int, float, str, type(None))):
                cleaned[section_key] = _safe(section_val)
        result[report_key] = cleaned
    return result


class _JsonEncoder(json.JSONEncoder):
    """处理 numpy 类型和 date 类型的 JSON 序列化"""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (date, datetime)):
            return str(obj)
        return super().default(obj)


def _safe(v):
    """把 numpy 数值转为 Python 原生类型"""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 4)
    return v


def fmt_num(v, decimal=2):
    """格式化数字为可读字符串"""
    if v is None:
        return "N/A"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(v) >= 1e8:
        return f"{v/1e8:.{decimal}f}亿"
    if abs(v) >= 1e4:
        return f"{v/1e4:.{decimal}f}万"
    return f"{v:.{decimal}f}"


def pct_change(cur, prev):
    """计算环比变化率，返回字符串"""
    try:
        if prev and prev != 0:
            chg = (cur - prev) / abs(prev) * 100
            arrow = "↑" if chg > 0 else "↓"
            return f"{arrow}{abs(chg):.1f}%"
    except Exception:
        pass
    return "-"


def _r_label(r):
    """将任意格式的R段 key 转为可读标签"""
    r_str = str(r)
    if "500" in r_str and ("∞" in r_str or "inf" in r_str.lower() or "+" in r_str):
        return "大R(≥500)"
    if "100" in r_str and "500" in r_str:
        return "中R(100-500)"
    if "10" in r_str and "100" in r_str:
        return "小R(10-100)"
    if "0.1" in r_str and "10" in r_str:
        return "微R(<10)"
    return r_str


def _r_sort_key(r):
    """按大R→中R→小R→微R排序"""
    r_str = str(r)
    if "500" in r_str and ("∞" in r_str or "+" in r_str):
        return 0
    if "100" in r_str and "500" in r_str:
        return 1
    if "10" in r_str and "100" in r_str:
        return 2
    return 3


def build_summary(all_data):
    """
    把 all_data 整理为结构化摘要，分为两层：
    1. readable_summary: 给 Claude 看的人类可读文本（按章节）
    2. raw_data: 完整数据（备用）
    """
    meta = all_data.get("_meta", {})
    current_start = meta.get("current_start")
    current_end = meta.get("current_end")
    prev_start = meta.get("prev_start")
    prev_end = meta.get("prev_end")

    sections = {}

    # 计算版本周期天数（用于日均环比）
    def _days(start, end):
        if start and end:
            try:
                from datetime import date as _date
                s = _date.fromisoformat(str(start)) if not hasattr(start, 'toordinal') else start
                e = _date.fromisoformat(str(end)) if not hasattr(end, 'toordinal') else end
                return (e - s).days + 1
            except Exception:
                pass
        return None

    cur_days = _days(current_start, current_end)
    prev_days = _days(prev_start, prev_end)

    # ── 第一章：基础大盘 ──────────────────────────────
    base = all_data.get("基础数据", {})
    cur_b = base.get("current", {})
    prev_b = base.get("previous", {})

    def get_val(d, key, sub="mean"):
        return _safe(d.get(key, {}).get(sub)) if d else None

    # 环比统一用日均（mean）计算，避免版本周期长度不同导致误差
    # 显示值用 sum（期间总量）；环比用 mean（日均），括号注明（日均环比）
    lines = [f"【基础大盘数据】（本版本{cur_days}天 vs 上版本{prev_days}天，环比基于日均）"]
    metrics = [
        # (显示标签, 显示用sub, 环比用sub, 是否百分比)
        ("DAU", "mean", "mean", False),
        ("MAU", "mean", "mean", False),
        ("DNU", "sum", "mean", False),
        ("次留(%)", "mean", "mean", True),
        ("付费率(%)", "mean", "mean", True),
        ("破产率(%)", "mean", "mean", True),
        ("总收入($)", "sum", "mean", False),
        ("内购收入($)", "sum", "mean", False),
        ("广告收入($)", "sum", "mean", False),
        ("内购ARPU($)", "mean", "mean", False),
        ("内购ARPPU($)", "mean", "mean", False),
        ("推广成本($)", "sum", "mean", False),
    ]
    for label, display_sub, cmp_sub, is_pct in metrics:
        c = get_val(cur_b, label, display_sub)
        c_cmp = get_val(cur_b, label, cmp_sub)
        p_cmp = get_val(prev_b, label, cmp_sub)
        c_str = (fmt_num(c) + "%" if is_pct else fmt_num(c)) if c is not None else "N/A"
        chg = pct_change(c_cmp, p_cmp) if (c_cmp and p_cmp) else "-"
        lines.append(f"  {label}：本版本={c_str}，环比={chg}")
    sections["基础大盘"] = "\n".join(lines)

    # ── 广告数据 ──────────────────────────────────────
    ad = all_data.get("广告大盘数据", {})
    cur_ad = ad.get("current", {})
    prev_ad = ad.get("previous", {})

    lines = [f"【广告大盘数据】（环比基于日均）"]
    ad_metrics = [
        # (标签, 显示sub, 环比sub)
        ("广告总收入", "sum", "mean"),
        ("广告观看次数", "sum", "mean"),
        ("广告观看人数", "sum", "mean"),
        ("ECPM", "mean", "mean"),
        ("广告arpu", "mean", "mean"),
        ("广告渗透率", "mean", "mean"),
        ("活跃人均次数", "mean", "mean"),
    ]
    for label, display_sub, cmp_sub in ad_metrics:
        c = get_val(cur_ad, label, display_sub)
        c_cmp = get_val(cur_ad, label, cmp_sub)
        p_cmp = get_val(prev_ad, label, cmp_sub)
        c_str = fmt_num(c) if c is not None else "N/A"
        chg = pct_change(c_cmp, p_cmp) if (c_cmp and p_cmp) else "-"
        lines.append(f"  {label}：本版本={c_str}，环比={chg}")
    sections["广告数据"] = "\n".join(lines)

    # ── 活跃数据 ──────────────────────────────────────
    act = all_data.get("活跃数据监控", {})
    cur_act = act.get("current", {})
    prev_act = act.get("previous", {})

    lines = ["【活跃行为数据】"]
    act_metrics = [
        ("spin用户数", "mean"), ("人均spin次数", "mean"),
        ("机台通过率", "mean"), ("激励广告覆盖率", "mean"),
        ("激励广告人均", "mean"), ("插屏广告覆盖率", "mean"), ("插屏广告人均", "mean"),
    ]
    for label, sub in act_metrics:
        c = get_val(cur_act, label, sub)
        p = get_val(prev_act, label, sub)
        c_str = fmt_num(c) if c is not None else "N/A"
        chg = pct_change(c, p) if (c and p) else "-"
        lines.append(f"  {label}：本版本={c_str}，环比={chg}")
    sections["活跃数据"] = "\n".join(lines)

    # ── 新用户：破冰率 ────────────────────────────────
    brk = all_data.get("注册破冰率监控", {})
    stage = brk.get("stage", {})
    cur_brk = brk.get("current", {})

    lines = ["【注册破冰率（阶段值）】"]
    day_keys = ["当日", "第1日", "第2日", "第3日", "第4日", "第5日", "第6日", "第7日"]
    for k in day_keys:
        v = stage.get(k)
        lines.append(f"  {k}：{fmt_num(v)}%" if v is not None else f"  {k}：N/A")

    if cur_brk and cur_brk.get("daily_avg"):
        lines.append("【区间内逐日均值】")
        for k in day_keys:
            v = cur_brk["daily_avg"].get(k)
            lines.append(f"  {k}：{fmt_num(v)}%" if v is not None else f"  {k}：N/A")

    total_users = cur_brk.get("total_users", 0) if cur_brk else 0
    lines.append(f"  区间内总注册用户数：{fmt_num(total_users)}")
    sections["破冰率"] = "\n".join(lines)

    # ── 新用户：首日 Spin ─────────────────────────────
    spin = all_data.get("首日人均spin", {})
    cur_spin = spin.get("current", {})

    lines = ["【首日人均 Spin（分渠道）】"]
    for channel, metrics_d in (cur_spin or {}).items():
        lines.append(f"  渠道：{channel}")
        for col, val_dict in metrics_d.items():
            v = _safe(val_dict.get("mean"))
            lines.append(f"    {col}：{fmt_num(v)}")
    sections["首日spin"] = "\n".join(lines)

    # ── 用户结构 ──────────────────────────────────────
    uc = all_data.get("用户构成", {})
    cur_uc = uc.get("current", {})

    lines = ["【用户构成（生命周期 × 付费段）- 各付费段汇总】"]
    if cur_uc:
        r_totals = {}
        for key, val in cur_uc.items():
            parts = key.split(" | ")
            if len(parts) == 2:
                r_seg = parts[1]
                r_totals[r_seg] = r_totals.get(r_seg, 0) + (_safe(val) or 0)
        total = sum(r_totals.values()) or 1
        for r, v in sorted(r_totals.items(), key=lambda x: x[1], reverse=True):
            pct = v / total * 100
            lines.append(f"  {r}：平均{fmt_num(v)}人（占比{fmt_num(pct)}%）")
    sections["用户结构"] = "\n".join(lines)

    # ── 付费点位分布 ──────────────────────────────────
    pd_data = all_data.get("付费点位分布", {})
    cur_pd = pd_data.get("current", {})

    lines = ["【付费点位分布（本版本，按收入排序）】"]
    for pos, m in (cur_pd or {}).items():
        rev = _safe(m.get("内购金额", 0))
        cnt = _safe(m.get("内购次数", 0))
        users = _safe(m.get("内购人数", 0))
        if rev and rev > 0:
            lines.append(f"  {pos}：收入=${fmt_num(rev)}，次数={int(cnt or 0)}，人数={int(users or 0)}")
    sections["付费点位分布"] = "\n".join(lines)

    # ── 付费点位点击率 ────────────────────────────────
    ctr_data = all_data.get("付费点位点击率", {})
    cur_ctr = ctr_data.get("current", {})

    lines = ["【付费点位点击率 Top15（按点击率排序）】"]
    if cur_ctr:
        sorted_ctr = sorted(cur_ctr.items(), key=lambda x: x[1].get("avg_rate", 0), reverse=True)[:15]
        for k, v in sorted_ctr:
            rate = _safe(v.get("avg_rate", 0))
            lines.append(f"  {k}：平均点击率={fmt_num(rate)}%")
    sections["付费点位点击率"] = "\n".join(lines)

    # ── 资源经济：资源监控 ────────────────────────────
    res = all_data.get("付费用户资源监控", {})
    cur_res = res.get("current", {})

    # R段格式因产品而异：有 "[500,+∞)" / "[500, +∞)" / "500~+∞" 等多种写法
    # 使用模块级 _r_label / _r_sort_key 处理
    lines = ["【付费用户资源监控（分R段）】"]
    sorted_r_keys = sorted((cur_res or {}).keys(), key=_r_sort_key)
    for r in sorted_r_keys:
        d = (cur_res or {}).get(r, {})
        if not d:
            continue
        label = _r_label(r)
        net = _safe(d.get("钻石净消耗总额（无付费补充）"))
        net_med = _safe(d.get("钻石净消耗中位数（无付费补充）"))
        diamond_sum = _safe(d.get("消耗钻石总和"))
        pay_d = _safe(d.get("付费购买钻石购买价格总和"))
        pay_g = _safe(d.get("付费购买金币购买价格总和"))
        spin_sum = _safe(d.get("下线事件.本次Spin赢得金币数量总和"))
        spin_med = _safe(d.get("下线事件.本次Spin赢得金币数量中位数"))
        lines.append(f"  {label}：")
        lines.append(f"    钻石消耗总量={fmt_num(diamond_sum)}")
        lines.append(f"    钻石净消耗总额（无付费补充）={fmt_num(net)}，中位数={fmt_num(net_med)}")
        lines.append(f"    钻石付费收入=${fmt_num(pay_d)}，金币付费收入=${fmt_num(pay_g)}")
        lines.append(f"    Spin赢得金币总量={fmt_num(spin_sum)}，中位数={fmt_num(spin_med)}")
    sections["资源监控"] = "\n".join(lines)

    # ── 资源经济：金币库存 ────────────────────────────
    inv = all_data.get("付费用户金币库存监控", {})
    cur_inv = inv.get("current", {})

    lines = ["【付费用户金币库存（各R段中位数）】"]
    sorted_inv_keys = sorted((cur_inv or {}).keys(), key=_r_sort_key)
    for r in sorted_inv_keys:
        d = (cur_inv or {}).get(r, {})
        if not d:
            continue
        label = _r_label(r)
        asset = _safe(d.get("用户登录.当前资产中位数"))
        spin_gain = _safe(d.get("下线事件.本次Spin赢得金币数量中位数"))
        lines.append(f"  {label}：当前资产中位数={fmt_num(asset)}，Spin赢得金币中位数={fmt_num(spin_gain)}")
    sections["金币库存"] = "\n".join(lines)

    # ── 合并成最终给 Claude 的全文摘要 ──────────────────
    full_text_parts = [
        f"产品版本数据摘要",
        f"当前版本区间：{current_start} ~ {current_end}",
        f"上版本区间：{prev_start} ~ {prev_end}",
        "",
        sections.get("基础大盘", ""),
        "",
        sections.get("广告数据", ""),
        "",
        sections.get("活跃数据", ""),
        "",
        sections.get("破冰率", ""),
        "",
        sections.get("首日spin", ""),
        "",
        sections.get("用户结构", ""),
        "",
        sections.get("付费点位分布", ""),
        "",
        sections.get("付费点位点击率", ""),
        "",
        sections.get("资源监控", ""),
        "",
        sections.get("金币库存", ""),
    ]

    return {
        "meta": {
            "current_start": str(current_start),
            "current_end": str(current_end),
            "prev_start": str(prev_start),
            "prev_end": str(prev_end),
        },
        "sections": sections,
        "full_summary": "\n".join(full_text_parts),
        # 保留原始聚合数据（report_builder 生成表格用）
        # 过滤掉 DataFrame 类型（无法序列化）和 _meta
        "raw": _make_serializable(all_data)
    }


def main():
    parser = argparse.ArgumentParser(description="版本数据提取器")
    parser.add_argument("--folder", required=True, help="CSV 数据文件夹路径")
    parser.add_argument("--start", required=True, help="本版本开始日期 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="本版本结束日期 YYYY-MM-DD")
    parser.add_argument("--prev-start", required=False, default=None, help="上版本开始日期 YYYY-MM-DD（不填则自动推算：与本版本等长的前一周期）")
    parser.add_argument("--prev-end", required=False, default=None, help="上版本结束日期 YYYY-MM-DD（不填则自动推算）")
    parser.add_argument("--output", required=True, help="输出 JSON 文件路径")
    args = parser.parse_args()

    from datetime import timedelta
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    if args.prev_start and args.prev_end:
        prev_start = datetime.strptime(args.prev_start, "%Y-%m-%d").date()
        prev_end = datetime.strptime(args.prev_end, "%Y-%m-%d").date()
    else:
        # 自动推算：上版本天数 = 本版本天数，紧接在本版本前
        cur_days = (end - start).days + 1
        prev_end = start - timedelta(days=1)
        prev_start = prev_end - timedelta(days=cur_days - 1)
        print(f"[自动推算] 上版本日期：{prev_start} ~ {prev_end}（与本版本同为 {cur_days} 天）")

    print(f"[START] 开始提取数据...")
    print(f"  文件夹：{args.folder}")
    print(f"  本版本区间：{start} ~ {end}")
    print(f"  上版本区间：{prev_start} ~ {prev_end}")

    all_data = load_all_data(args.folder, start, end, prev_start, prev_end)
    summary = build_summary(all_data)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, cls=_JsonEncoder)

    print(f"[OK] 数据提取完成，已写入：{args.output}")
    print(f"\n{'='*60}")
    print("以下是给 Claude 读取的数据摘要：")
    print('='*60)
    print(summary["full_summary"])
    print('='*60)


if __name__ == "__main__":
    main()
