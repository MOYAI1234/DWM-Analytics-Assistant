# data_loader.py — CSV文件扫描、匹配、读取、聚合

import os
import re
import pandas as pd
from datetime import datetime, timedelta
from config import CSV_FILE_PATTERNS, VERSION_CYCLE_DAYS


def parse_date_from_filename(filename):
    """
    从文件名中提取日期区间，格式如：_20260127-20260225
    返回 (start_date, end_date) 或 None
    """
    pattern = r'_(\d{8})-(\d{8})'
    match = re.search(pattern, filename)
    if match:
        start = datetime.strptime(match.group(1), "%Y%m%d").date()
        end = datetime.strptime(match.group(2), "%Y%m%d").date()
        return start, end
    # 基础数据只有单日期（如 基础数据_20260226.csv）
    pattern_single = r'_(\d{8})'
    match = re.search(pattern_single, filename)
    if match:
        d = datetime.strptime(match.group(1), "%Y%m%d").date()
        return d, d
    return None


def match_report_type(filename):
    """根据文件名关键词识别报表类型"""
    for report_type, keyword in CSV_FILE_PATTERNS.items():
        if keyword in filename:
            return report_type
    return None


def scan_data_folder(folder_path):
    """
    扫描指定文件夹，返回所有识别出的CSV文件信息
    返回: dict {report_type: {"path": str, "dates": (start, end)}}
    """
    if not os.path.exists(folder_path):
        raise FileNotFoundError(f"数据文件夹不存在：{folder_path}")

    found = {}
    unrecognized = []

    for filename in os.listdir(folder_path):
        if not filename.endswith(".csv"):
            continue
        report_type = match_report_type(filename)
        if report_type:
            dates = parse_date_from_filename(filename)
            found[report_type] = {
                "path": os.path.join(folder_path, filename),
                "filename": filename,
                "dates": dates,
            }
        else:
            unrecognized.append(filename)

    if unrecognized:
        print(f"[WARN] 以下文件未能识别报表类型，已跳过：{unrecognized}")

    return found


def load_csv(path):
    """读取CSV，处理BOM和编码问题"""
    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        df = pd.read_csv(path, encoding="gbk")
    # 清理列名空格
    df.columns = [c.strip() for c in df.columns]
    return df


def clean_numeric(value):
    """将带逗号、百分号的字符串转为数字，无法转换返回 None"""
    if pd.isna(value):
        return None
    s = str(value).strip().replace(",", "").replace("%", "").replace("$", "")
    try:
        return float(s)
    except ValueError:
        return None


def get_date_col(df):
    """自动检测日期列名，兼容'日期'和'时间'两种格式"""
    for col in ["日期", "时间", "初始事件发生时间"]:
        if col in df.columns:
            return col
    # fallback: 第一列
    return df.columns[0]


def filter_by_date_range(df, date_col, start_date, end_date):
    """
    按日期列筛选行，日期列格式如 '2026-01-27(二)' 或 '2026-01-27'
    """
    def parse_cell_date(val):
        s = str(val).strip()
        # 去掉括号内容
        s = re.sub(r'\（.*?\）|\(.*?\)', '', s).strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    dates = df[date_col].apply(parse_cell_date)
    mask = dates.apply(lambda d: d is not None and start_date <= d <= end_date)
    return df[mask].copy()


# ─────────────────────────────────────────────
# 各报表专用解析函数
# ─────────────────────────────────────────────

def parse_基础数据(path, current_start, current_end, prev_start, prev_end):
    """
    基础数据：逐日明细，按日期范围筛选后聚合
    返回 {current: {...}, previous: {...}}
    """
    df = load_csv(path)
    date_col = get_date_col(df)

    def aggregate(start, end):
        sub = filter_by_date_range(df, date_col, start, end)
        if sub.empty:
            return None
        numeric_cols = [c for c in sub.columns if c != date_col]
        result = {}
        for col in numeric_cols:
            numeric_vals = sub[col].apply(clean_numeric).dropna()
            if len(numeric_vals) == 0:
                continue
            # 总收入/成本类字段求和，其余求均值
            sum_keywords = ["收入", "成本", "利润", "安装量", "DNU", "DAU"]
            if any(k in col for k in sum_keywords):
                result[col] = {"sum": numeric_vals.sum(), "mean": numeric_vals.mean()}
            else:
                result[col] = {"mean": numeric_vals.mean()}
        return result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
        "raw_current": filter_by_date_range(df, date_col, current_start, current_end),
    }


def parse_活跃数据监控(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    date_col = get_date_col(df)

    def aggregate(start, end):
        sub = filter_by_date_range(df, date_col, start, end)
        if sub.empty:
            return None
        result = {}
        for col in sub.columns:
            if col == date_col:
                continue
            numeric_vals = sub[col].apply(clean_numeric).dropna()
            if len(numeric_vals) == 0:
                continue
            result[col] = {"mean": numeric_vals.mean()}
        return result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


def parse_广告大盘数据(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    date_col = get_date_col(df)

    def aggregate(start, end):
        sub = filter_by_date_range(df, date_col, start, end)
        if sub.empty:
            return None
        result = {}
        sum_cols = ["广告总收入", "广告观看次数", "广告观看人数"]
        for col in sub.columns:
            if col == date_col:
                continue
            numeric_vals = sub[col].apply(clean_numeric).dropna()
            if len(numeric_vals) == 0:
                continue
            if col in sum_cols:
                result[col] = {"sum": numeric_vals.sum(), "mean": numeric_vals.mean()}
            else:
                result[col] = {"mean": numeric_vals.mean()}
        return result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


def parse_首日人均spin(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    date_col = get_date_col(df)
    # 只取 mintegral 和 Organic 渠道
    key_channels = ["mintegral_int", "Organic"]

    def aggregate(start, end):
        sub = filter_by_date_range(df, date_col, start, end)
        if sub.empty:
            return None
        result = {}
        source_col = "#vp@media_source" if "#vp@media_source" in sub.columns else sub.columns[1]
        for channel in key_channels:
            ch_df = sub[sub[source_col] == channel]
            if ch_df.empty:
                continue
            ch_result = {}
            for col in ch_df.columns:
                if col in [date_col, source_col]:
                    continue
                numeric_vals = ch_df[col].apply(clean_numeric).dropna()
                if len(numeric_vals) > 0:
                    ch_result[col] = {"mean": numeric_vals.mean()}
            result[channel] = ch_result
        return result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


def parse_注册破冰率监控(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    date_col = df.columns[0]  # 第一列：初始事件的发生时间

    # 提取阶段值行
    stage_row = df[df[date_col].astype(str).str.contains("阶段值", na=False)]

    # 破冰率列名兼容两种格式：
    #   格式A（含"第"）："第1日"、"第2日" ...
    #   格式B（不含"第"）："1日"、"2日" ... 以及 "当日"
    # 统一标准化为 "当日"、"第1日" ... "第7日"
    def _find_day_cols(columns):
        """返回 [(原始列名, 标准化名)] 列表"""
        result = []
        for c in columns:
            if c == "当日":
                result.append((c, "当日"))
            elif re.match(r'^第?\d+日$', c.strip()):
                # 提取数字，统一映射为 "第N日"
                num = re.search(r'\d+', c).group()
                result.append((c, f"第{num}日"))
        return result

    day_col_map = _find_day_cols(df.columns)

    def aggregate(start, end):
        sub = filter_by_date_range(df, date_col, start, end)
        if sub.empty:
            return None
        result = {"daily_avg": {}, "total_users": 0}
        for orig_col, std_name in day_col_map:
            numeric_vals = sub[orig_col].apply(clean_numeric).dropna()
            if len(numeric_vals) > 0:
                result["daily_avg"][std_name] = numeric_vals.mean()
        # 总注册用户数
        user_col = [c for c in df.columns if "用户数" in c or "注册用户数" in c]
        if user_col:
            result["total_users"] = sub[user_col[0]].apply(clean_numeric).dropna().sum()
        return result

    # 阶段值直接返回（同样用标准化名）
    stage_data = {}
    if not stage_row.empty:
        for orig_col, std_name in day_col_map:
            val = stage_row.iloc[0][orig_col]
            stage_data[std_name] = clean_numeric(val)

    return {
        "stage": stage_data,
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


def parse_付费点位分布(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    date_col = get_date_col(df)

    def aggregate(start, end):
        sub = filter_by_date_range(df, date_col, start, end)
        if sub.empty:
            return None
        pos_col = "项目位置"
        value_cols = ["内购次数", "内购人数", "内购金额"]
        result = {}
        for pos, group in sub.groupby(pos_col):
            result[pos] = {}
            for col in value_cols:
                if col in group.columns:
                    result[pos][col] = group[col].apply(clean_numeric).dropna().sum()
        # 按内购金额排序
        sorted_result = dict(
            sorted(result.items(), key=lambda x: x[1].get("内购金额", 0), reverse=True)
        )
        return sorted_result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


def parse_付费点位点击率(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    date_col = get_date_col(df)

    def aggregate(start, end):
        sub = filter_by_date_range(df, date_col, start, end)
        if sub.empty:
            return None
        pos_col = "项目位置"
        r_col = "总付费金额"
        rate_col = "自定义指标"
        result = {}
        for (pos, r), group in sub.groupby([pos_col, r_col]):
            numeric_vals = group[rate_col].apply(clean_numeric).dropna()
            if len(numeric_vals) > 0:
                key = f"{pos} | {r}"
                result[key] = {"avg_rate": numeric_vals.mean()}
        return result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


def _melt_wide_table(df, r_col, metric_col, id_cols):
    """
    将宽表（行=R段×指标，列=日期）转为长表（行=R段×指标×日期）。
    id_cols: 非日期的固定列，如 ['总付费金额', '分析指标', '阶段汇总']
    日期列判断标准：列名能被 %Y-%m-%d 解析。
    返回 df_long 含列：r_col, metric_col, '日期', '值'
    """
    date_cols = []
    for c in df.columns:
        try:
            datetime.strptime(c.strip(), "%Y-%m-%d")
            date_cols.append(c)
        except ValueError:
            pass
    if not date_cols:
        return None
    df_long = df.melt(
        id_vars=id_cols,
        value_vars=date_cols,
        var_name="日期",
        value_name="值"
    )
    df_long["日期"] = pd.to_datetime(df_long["日期"], format="%Y-%m-%d").dt.date
    df_long["值"] = df_long["值"].apply(clean_numeric)
    return df_long


def _detect_wide_table_cols(df):
    """
    自动检测宽表的 R段列名 和 指标列名。
    支持多产品的列名变体：
      R段列：总付费金额
      指标列：分析指标 / 数据指标（不同产品可能不同）
      汇总列：阶段汇总 / 阶段定义（可选）
    返回 (r_col, metric_col, id_cols)
    """
    # R段列：第一列通常是付费段
    r_candidates = ["总付费金额"]
    r_col = next((c for c in r_candidates if c in df.columns), df.columns[0])

    # 指标列：第二列，名称因产品而异
    metric_candidates = ["分析指标", "数据指标"]
    metric_col = next((c for c in metric_candidates if c in df.columns), None)
    if metric_col is None:
        # 回退：取第一个非日期、非R段的列
        for c in df.columns:
            if c != r_col and not c.strip().startswith("20"):
                metric_col = c
                break

    # 汇总列（可选）
    extra_candidates = ["阶段汇总", "阶段定义"]
    id_cols = [r_col, metric_col] + [c for c in extra_candidates if c in df.columns]
    return r_col, metric_col, id_cols


def parse_付费用户金币库存监控(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    r_col, metric_col, id_cols = _detect_wide_table_cols(df)

    df_long = _melt_wide_table(df, r_col, metric_col, id_cols)
    if df_long is None:
        return {"current": None, "previous": None}

    value_cols = ["用户登录.当前资产中位数", "下线事件.本次Spin赢得金币数量中位数"]

    def aggregate(start, end):
        sub = df_long[(df_long["日期"] >= start) & (df_long["日期"] <= end)]
        sub = sub[sub[metric_col].isin(value_cols)]
        if sub.empty:
            return None
        result = {}
        for r_level, r_group in sub.groupby(r_col):
            result[r_level] = {}
            for metric, m_group in r_group.groupby(metric_col):
                vals = m_group["值"].dropna()
                if len(vals) > 0:
                    result[r_level][metric] = vals.median()
        return result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


def parse_付费用户资源监控(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    r_col, metric_col, id_cols = _detect_wide_table_cols(df)

    df_long = _melt_wide_table(df, r_col, metric_col, id_cols)
    if df_long is None:
        return {"current": None, "previous": None}

    key_metrics = [
        "消耗钻石总和", "消耗钻石中位数", "消耗钻石用户均值",
        "下线事件.本次Spin赢得金币数量总和", "下线事件.本次Spin赢得金币数量.用户均值",
        "下线事件.本次Spin赢得金币数量中位数",
        "付费购买钻石购买价格总和", "付费购买金币购买价格总和",
        "钻石净消耗总额", "钻石净消耗中位数",
        "钻石净消耗总额（无付费补充）", "钻石净消耗中位数（无付费补充）",
        "点击购买钻石触发用户数", "点击购买金币触发用户数",
    ]
    sum_metrics = {
        "消耗钻石总和", "下线事件.本次Spin赢得金币数量总和",
        "付费购买钻石购买价格总和", "付费购买金币购买价格总和",
        "钻石净消耗总额", "钻石净消耗总额（无付费补充）",
    }

    def aggregate(start, end):
        sub = df_long[(df_long["日期"] >= start) & (df_long["日期"] <= end)]
        sub = sub[sub[metric_col].isin(key_metrics)]
        if sub.empty:
            return None
        result = {}
        for r_level, r_group in sub.groupby(r_col):
            result[r_level] = {}
            for metric, m_group in r_group.groupby(metric_col):
                vals = m_group["值"].dropna()
                if len(vals) == 0:
                    continue
                if metric in sum_metrics:
                    result[r_level][metric] = vals.sum()
                else:
                    result[r_level][metric] = vals.mean()
        return result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


def parse_用户构成(path, current_start, current_end, prev_start, prev_end):
    df = load_csv(path)
    date_col = get_date_col(df)

    def aggregate(start, end):
        sub = filter_by_date_range(df, date_col, start, end)
        if sub.empty:
            return None
        lifecycle_col = "事件与注册相差天数"
        r_col = "总付费金额"
        user_col = "用户登录.触发用户数"
        result = {}
        for (lc, r), group in sub.groupby([lifecycle_col, r_col]):
            vals = group[user_col].apply(clean_numeric).dropna()
            key = f"{lc} | {r}"
            result[key] = vals.mean()
        return result

    return {
        "current": aggregate(current_start, current_end),
        "previous": aggregate(prev_start, prev_end),
    }


# ─────────────────────────────────────────────
# 主入口：加载全部报表
# ─────────────────────────────────────────────

PARSERS = {
    "基础数据": parse_基础数据,
    "活跃数据监控": parse_活跃数据监控,
    "广告大盘数据": parse_广告大盘数据,
    "首日人均spin": parse_首日人均spin,
    "注册破冰率监控": parse_注册破冰率监控,
    "付费点位分布": parse_付费点位分布,
    "付费点位点击率": parse_付费点位点击率,
    "付费用户金币库存监控": parse_付费用户金币库存监控,
    "付费用户资源监控": parse_付费用户资源监控,
    "用户构成": parse_用户构成,
}


def load_all_data(folder_path, current_start, current_end, prev_start, prev_end):
    """
    主入口：扫描文件夹，解析所有报表
    prev_start/prev_end 由调用方明确传入（上版本日期区间）
    返回 all_data dict
    """
    print(f"\n[日期] 当前版本区间：{current_start} ~ {current_end}")
    print(f"[日期] 上版本区间：{prev_start} ~ {prev_end}")

    files = scan_data_folder(folder_path)
    print(f"\n[文件] 识别到的报表：{list(files.keys())}")

    all_data = {}
    missing = []

    for report_type, parser in PARSERS.items():
        if report_type not in files:
            missing.append(report_type)
            continue
        path = files[report_type]["path"]
        try:
            data = parser(path, current_start, current_end, prev_start, prev_end)
            all_data[report_type] = data
            print(f"  [OK] {report_type}")
        except Exception as e:
            print(f"  [ERR] {report_type} 解析失败：{e}")

    if missing:
        print(f"\n[WARN] 缺少以下报表（将跳过对应章节）：{missing}")

    all_data["_meta"] = {
        "current_start": current_start,
        "current_end": current_end,
        "prev_start": prev_start,
        "prev_end": prev_end,
    }

    return all_data
