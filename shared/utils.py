"""shared/utils.py
公共工具函数，供所有 parse_*.py 脚本复用。
"""
import glob
import os
from datetime import datetime


def pct_change(cur, prev):
    """计算环比变化率，返回 float 百分比（如 12.3），或 None。"""
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / abs(prev) * 100, 1)


def parse_num(s):
    """解析数字字符串，失败返回 None。

    处理逗号、$、%、空值等常见格式。
    """
    if s is None:
        return None
    s = str(s).strip().replace(',', '').replace('$', '').replace('%', '')
    if s in ('', '-', '—', 'null', 'N/A'):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_num_or_zero(s):
    """解析数字字符串，失败返回 0.0。

    适用于累加场景，None 会破坏求和逻辑。
    """
    v = parse_num(s)
    return v if v is not None else 0.0


def month_of(date_str):
    """从日期字符串提取 YYYY-MM，失败返回 None。

    自动处理带括号后缀的格式如 '2026-01-01(四)'。
    """
    s = clean_date_str(date_str)
    try:
        return datetime.strptime(s, '%Y-%m-%d').strftime('%Y-%m')
    except (ValueError, TypeError):
        return None


def clean_date_str(s):
    """去掉日期字符串中的括号后缀。

    '2026-01-01(四)' -> '2026-01-01'
    '2026-01-01（四）' -> '2026-01-01'
    """
    s = str(s).strip()
    for bracket in ('(', '（'):
        if bracket in s:
            s = s[:s.index(bracket)]
    return s.strip()


def date_in_range(date_str, start_date=None, end_date=None, month=None):
    """判断日期是否在指定范围内。

    支持两种模式：
    - date range: start_date + end_date
    - month prefix: month (如 '2026-02')
    """
    s = clean_date_str(date_str)
    try:
        d = datetime.strptime(s, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return False
    if start_date and end_date:
        sd = datetime.strptime(start_date, '%Y-%m-%d').date()
        ed = datetime.strptime(end_date, '%Y-%m-%d').date()
        return sd <= d <= ed
    if month:
        return s.startswith(month)
    return False


def find_csv(data_dir, keyword):
    """按关键字模糊匹配 CSV 文件名，返回最新的匹配路径或 None。"""
    pattern = os.path.join(str(data_dir), f'*{keyword}*.csv')
    matches = glob.glob(pattern)
    if not matches:
        return None
    return sorted(matches, key=os.path.getmtime, reverse=True)[0]
