---
name: daily-report
description: >
  生成手游日常数据监控报告的完整工作流。当用户提到"日报"、"日常监控"、"日度复盘"、"写X月X日监控"、"昨天数据监控"、"daily report"时，必须使用本 skill。

  适用场景：用户需要基于指定日期 D 输出单日监控结论，核心对比包含 D vs D-1、D vs 过去7天均值、D vs 上周同期（D-7）。
  支持完整流程：浏览器下载 ZIP（可选）→ 聚合 CSV 到日级指标 → 逐章节写入 Markdown 日报。
version: 0.4.0
---

# 日常数据监控报告生成器

本 skill 的单一真源为 `.claude` 目录：
- `.claude/skills/daily-report/`（即 `${USERPROFILE}/.claude/skills/daily-report/` 或 `${HOME}/.claude/skills/daily-report/`，也可通过环境变量 `CLAUDE_SKILLS_DIR` 自定义）

`daily_snapshot` 现已覆盖 8 类必需 CSV + 1 类可选广告 CSV，并输出 `_coverage` 矩阵，避免静默漏解析。
同时新增数据新鲜度纠偏：
- 次留默认读取 `T-1`（D日通常不完整）
- 投放回收默认读取 `T-1`（AF回传延迟）
- 内购新增 `iap_points`（Top点位变化 vs D-1）
- 大R新增风险画像：关注 `20-30天` 流失尾部用户及集中特征
- 广告大盘新增解析：按`点位`与`类型`双维分组监控（Top点位、类型占比、vs D-1变化）

## 参考路径

| 路径 | 说明 |
|------|------|
| `D:/workspace/mobile_game_reports/reports_daily/` | 日报存档目录，命名：`<产品名>日常监控 - YYYY-MM-DD.md` |
| `D:/workspace/mobile_game_reports/skill/csv_mapping.json` | CSV 文件名映射（复用月报） |
| `D:/workspace/mobile_game_reports/skill/style_guide.json` | 文风规范（复用月报） |
| `.claude/skills/daily-report/daily_section_registry.json`（示例：`${USERPROFILE}/.claude/skills/daily-report/daily_section_registry.json`，或由 `CLAUDE_SKILLS_DIR` 指定） | 日报章节定义（v0.3） |
| `.claude/skills/daily-report/daily_calculation_spec.json`（示例同上） | 日报计算口径（v0.3） |
| `.claude/skills/daily-report/scripts/build_daily_snapshot.py`（示例同上） | 日级聚合脚本（8类解析+coverage） |
| `D:/workspace/mobile_game_reports/skill/wip_daily_report.md` | 当前日报草稿 |
| `D:/workspace/mobile_game_reports/skill/daily_snapshot.json` | 脚本输出的结构化数据 |

## 第零步：初始化

1. 从用户输入确认：`产品名 + 目标日期 D`（如 `Demo Casino, 2026-03-02`）
   - `D` 是数据日期，不是下载日期。
2. 明确统计窗口：
   - D-1：前一自然日
   - 过去7天均值：D-7 到 D-1（不含 D）
   - 上周同期：D-7
3. 清空或新建 `wip_daily_report.md`，写入：
   ```
   # <产品名>日常数据监控 - <YYYY-MM-DD>
   ```

## 第一步：计算日级对比指标

1. 确认数据目录：
   `D:/workspace/mobile_game_reports/data/<产品名>_<YYYY-MM-DD>/日常数据_<YYYYMMDD>/`

2. 运行聚合脚本（默认要求覆盖 8 类必需 CSV；广告报表为可选自动解析）。将下方占位符替换为本机实际路径，`<SKILLS_DIR>` 替换方式见首节说明；路径示例：

   - Windows：`<OUTPUT_JSON_PATH>=D:/workspace/mobile_game_reports/skill/daily_snapshot.json`，`<CSV_MAPPING_PATH>=D:/workspace/mobile_game_reports/skill/csv_mapping.json`
   - Unix：`<OUTPUT_JSON_PATH>=~/workspace/mobile_game_reports/skill/daily_snapshot.json`，`<CSV_MAPPING_PATH>=~/workspace/mobile_game_reports/skill/csv_mapping.json`

   ```bash
   python "<SKILLS_DIR>/scripts/build_daily_snapshot.py" \
     --input-dir "<CSV目录>" \
     --target-date "YYYY-MM-DD" \
     --output "<OUTPUT_JSON_PATH>" \
     --csv-mapping "<CSV_MAPPING_PATH>"
   ```

3. 强校验模式（推荐）：
   ```bash
   python "<SKILLS_DIR>/scripts/build_daily_snapshot.py" \
     --input-dir "<CSV目录>" \
     --target-date "YYYY-MM-DD" \
     --output "<OUTPUT_JSON_PATH>" \
     --csv-mapping "<CSV_MAPPING_PATH>" \
     --expected-csv-count 8 \
     --strict
   ```

4. `daily_snapshot.json` 关键字段：
   - `core`（基础数据其二）
   - `basic1`（基础数据其1）
   - `spin` / `top_machines`
   - `iap`
   - `iap_points`（Top点位变化）
   - `paying_users`
   - `resource`（双周期口径）
   - `promo`（默认T-1）
   - `promo_raw_d`（D日原值，仅参考）
   - `big_r`（含流失倾向用户画像与集中特征）
   - `ads`（广告总量、点位Top、类型分组、vs D-1变化）
   - `_freshness`（口径锚点说明）
   - `_coverage`（每类CSV的 found/parsed/missing/parse_error 状态）
   - `_warnings`


## 第二步：按章节生成日报

章节顺序（固定）：
1. 今日核心看板
2. 基础补充（基础数据其1）
3. 机台参与与产出异常
4. 内购与生命周期结构
5. 资源经济（双周期）
6. 投放与回收
7. 广告变现监控（点位×类型）
8. 大R风险快照
9. 风险清单与明日动作

写作要求：
- 文风遵循 `style_guide.json`。
- 日维指标必须给出三组对比：`vs D-1`、`vs 7日均值`、`vs D-7`。
- 次留使用 `basic1.next_day_retention_meta.anchor_date` 作为当日可用口径（通常为 D-1）。
- 投放回收使用 `_freshness.promo_anchor_date`（通常为 D-1）；如需说明当天延迟，引用 `promo_raw_d`。
- 广告章节读取 `ads`：至少输出 Top点位变化（vs D-1）与类型结构占比（reward/inter 等），并点出异常集中风险。
- 资源与大R属于非纯日维口径，按各自周期/快照逻辑解释，不强行套 D-1。
- 大R章节默认不把 `active_30d_rate` 作为主结论；优先看 `at_risk_users_20_30d`、`high_risk_users_27_30d` 与 `concentrated_features`。
- 生命周期章节必须做结构拆分，不允许只写汇总均值：至少拆成 `0-30天 / 30-120天 / 120天+` 三档，并逐档写人数占比、D-1变化、行为强度变化（spin/bet/钻石三者至少二者）。
- 生命周期章节结尾必须给”产品周期判断”：明确当前是新客驱动、成长期驱动、还是成熟老客驱动，并说明对应风险。
- 正文生成方式：基于 `style_guide.json` + 本技能纠偏口径，由 AI 手工撰写章节，不强制使用固定文案模板。
- 变动绝对值 >15% 且无明确归因时前置 `⚠️`。
- 推广成本/ROI 为 0 时标注 `T+1 延迟`。

### 格式规范：「表格先行，结论跟随」

**所有含量化数据的章节，必须先写 Markdown 表格，再写分析文字。禁止在正文段落中大段嵌入数字——数字集中在表格，判断集中在文字。**

标准量化表头（适用于章一、章二、章六等核心指标章节）：
```
| 指标 | 当日 | vs D-1 | vs D-7 | vs 7日均 |
```

各章节强制格式：

| 章节 | 表格内容 | 表格后文字 |
|------|---------|-----------|
| 一 核心看板 | 所有核心指标一行一个，含三组对比 | **核心结论：** 加粗段落，1-3句，点明今日核心驱动或风险 |
| 二 基础补充 | 净收入/安装/次留/活跃付费用户，含三组对比 | 关键异常简述，1-2句 |
| 三 机台 | `机台\|Spin次数\|用户数\|金币消耗\|vs D-1 Spin\|vs D-1用户` | **关键异常：** 要点列表，逐条说明 |
| 四 IAP | 4.1 内购收入汇总（仅收入，三组对比；用户数/ARPPU 引用核心看板，不从分点位 CSV 汇总）→ 4.2 点位明细表（各点位独立的收入/用户数/ARPPU/vs D-1/vs D-7，不做跨点位汇总行）→ 4.3 生命周期三档表 | 逐档行为描述 + 产品周期判断段落 |
| 五 资源 | 产消汇总表（消耗/发放/净消耗 + 三组对比）+ 消耗原因明细表（含 vs D-1 列） | 1-2句归因说明 |
| 六 投放 | T-1指标表（收入/成本/ROI/安装/CPI，含三组对比）；今日原始参考值另起一行注明 | 文字判断，重点说ROI趋势和效率 |
| 七 广告 | 汇总表 + 广告类型占比表（rewarded/interstitial + 份额）+ Top点位表（点位\|量\|占比\|vs D-1\|vs D-7） | 关键变化说明，1-2句 |
| 八 大R | 概况表（总数/7日活跃/at-risk人数/占比）→ 集中特征要点列表 → at-risk 明细表（UID/LTV/最大单笔/上次付费/流失天数） | 活跃大R简述 |
| 九 风险清单 | `🔴/🟡/🟢 优先级\|风险项\|数据依据` 三列表格 | 明日动作编号列表，3-5条 |

## 第三步：输出与归档

1. 将章节写入 `wip_daily_report.md`
2. 复制为正式文件：
   `D:/workspace/mobile_game_reports/reports_daily/<产品名>日常监控 - <YYYY-MM-DD>.md`
3. 结尾输出 3-5 条明日执行动作

## 常见问题

- 数据不足 7 天：保留 D-1 / D-7，对 7日均值标注样本不足。
- 缺失字段：明确字段缺失，不臆测。
- 文件名不匹配：脚本使用 `csv_mapping.json` 关键字匹配；仍失败则人工指定。
- 多产品需求：每产品单独日报，不合并。
- **IAP 用户数/ARPPU 口径（硬性规则）**：内购数据_分点位 CSV 按点位分组，同一用户在多个点位购买会被重复计数。**禁止**将各点位的 `付费总用户数` 求和作为汇总用户数，也**禁止**从该求和值派生 ARPPU。汇总层的付费用户数、付费率、ARPPU 统一取 core（基础数据其二）或 basic1（基础数据其1）。分点位数据仅展示各点位独立指标，不做跨点位汇总行。
