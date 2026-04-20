# validate_analysis.py
# 职责：校验 analysis_results.json 中的环比方向描述是否与 extracted_data.json 一致
# 用法：python validate_analysis.py
# 返回：0=校验通过，1=存在矛盾（打印具体冲突并阻止继续）

import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import json
import re
from pathlib import Path

_SKILL_DIR    = Path(__file__).parent
DATA_PATH     = str(_SKILL_DIR / "extracted_data.json")
ANALYSIS_PATH = str(_SKILL_DIR / "analysis_results.json")

# ──────────────────────────────────────────────
# 1. 从 full_summary 解析「指标名 → 实际环比方向」
# ──────────────────────────────────────────────
# full_summary 格式示例（UTF-8后）：
#   内购收入($)：本版本=4644.18，环比=↑26.4%
#   DAU：本版本=3771.73，环比=↓2.4%

def parse_ground_truth(full_summary: str) -> dict:
    """
    返回 { 指标关键词: '+'/'-' } 的字典
    从 full_summary 的 ↑/↓ 提取真实方向
    """
    truth = {}
    # 匹配形如 "某某指标：...环比=↑X%" 或 "环比=↓X%"
    for line in full_summary.splitlines():
        up   = '↑' in line
        down = '↓' in line
        if not (up or down):
            continue
        direction = '+' if up else '-'
        # 提取冒号前的指标名（去掉括号内单位）
        m = re.match(r'\s*(.+?)(?:（.*?）|\(.*?\))?[：:]', line)
        if m:
            key = m.group(1).strip()
            truth[key] = direction
    return truth


# ──────────────────────────────────────────────
# 2. 指标别名映射：分析文字里用的词 → full_summary 里的指标名
#    只需覆盖"容易写错方向"的核心财务指标
# ──────────────────────────────────────────────
ALIAS_MAP = {
    # 分析文字关键词          : full_summary 指标名
    '内购收入':               '内购收入($)',
    '内购ARPU':               '内购ARPU($)',
    '内购 ARPU':              '内购ARPU($)',
    'ARPPU':                  '内购ARPPU($)',
    '内购ARPPU':              '内购ARPPU($)',
    '付费率':                 '付费率(%)',
    'DAU':                    'DAU',
    'MAU':                    'MAU',
    'DNU':                    'DNU',
    '次留':                   '次留(%)',
    '广告收入':               '广告收入($)',
    '广告ARPU':               '广告arpu',
    '广告 ARPU':              '广告arpu',
    'ECPM':                   'ECPM',
    '推广成本':               '推广成本($)',
    '总收入':                 '总收入($)',
    '破产率':                 '破产率(%)',
    '广告渗透率':             '广告渗透率',
}

# ──────────────────────────────────────────────
# 3. 从分析文字中提取「指标+方向」断言
# ──────────────────────────────────────────────

def extract_assertions(analysis_text: str) -> list:
    """
    在分析文字中找「指标关键词 + ↑/↓」的组合，返回 [(keyword, direction, snippet)]
    匹配规则：关键词后紧跟（最多8个非箭头字符）再接箭头，避免跨指标误匹配。
    覆盖格式：
      A) 关键词（↑3%）  / 关键词（↓3%）
      B) 关键词 ↑3%     / 关键词 ↓3%
      C) 关键词 $X.XX（↑3%）
    排除：「XXX背景下内购收入逆势↑」这类，关键词和箭头之间夹了其他指标名
    """
    assertions = []
    for alias in ALIAS_MAP:
        # 关键词后8字符内出现箭头（排除中间有"背景""下"等连接词的情况）
        pattern = re.compile(
            r'(?<![与和、])'           # 前面不是并列词（避免「A与B」中的A误匹配B的箭头）
            + re.escape(alias)
            + r'[^↑↓，。；\n]{0,12}'  # 中间最多12个字符，且不跨句
            + r'(↑|↓)',
            re.DOTALL
        )
        for m in pattern.finditer(analysis_text):
            snippet = m.group(0)
            # 额外过滤：片段中间不能出现其他指标关键词（防止「DAU与DNU双降…逆势↑」）
            middle = snippet[len(alias):]
            other_alias_found = any(
                a in middle for a in ALIAS_MAP if a != alias and len(a) >= 3
            )
            if other_alias_found:
                continue
            direction = '+' if m.group(1) == '↑' else '-'
            assertions.append((alias, direction, snippet.strip()))
    return assertions


# ──────────────────────────────────────────────
# 4. 主校验逻辑
# ──────────────────────────────────────────────

def main():
    with open(DATA_PATH,     'r', encoding='utf-8') as f:
        data = json.load(f)
    with open(ANALYSIS_PATH, 'r', encoding='utf-8') as f:
        analysis = json.load(f)

    full_summary = data.get('full_summary', '')
    truth = parse_ground_truth(full_summary)

    if not truth:
        print("[WARN] full_summary 解析结果为空，无法校验，跳过。")
        sys.exit(0)

    # 把所有章节分析文字拼成一个大字符串校验
    all_text = '\n'.join(str(v) for v in analysis.values())
    assertions = extract_assertions(all_text)

    errors = []
    for alias, claimed_dir, snippet in assertions:
        gt_key = ALIAS_MAP.get(alias)
        if gt_key not in truth:
            continue  # full_summary 里没有这个指标，跳过
        actual_dir = truth[gt_key]
        if claimed_dir != actual_dir:
            arrow_claimed = '↑' if claimed_dir == '+' else '↓'
            arrow_actual  = '↑' if actual_dir  == '+' else '↓'
            errors.append({
                'indicator': alias,
                'claimed':   arrow_claimed,
                'actual':    arrow_actual,
                'snippet':   snippet,
            })

    if not errors:
        print(f"[OK] 校验通过，共检查 {len(assertions)} 处断言，无方向矛盾。")
        sys.exit(0)
    else:
        print(f"[ERROR] 发现 {len(errors)} 处环比方向矛盾，请修正后重新生成报告：\n")
        for i, e in enumerate(errors, 1):
            print(f"  [{i}] 指标「{e['indicator']}」")
            print(f"       分析文字写的：{e['claimed']}")
            print(f"       数据实际方向：{e['actual']}")
            print(f"       出处片段：「{e['snippet']}」")
            print()
        sys.exit(1)


if __name__ == '__main__':
    main()
