# DWM Analytics Assistant

Claude Code skills and parsing scripts for WOOHOO CASINO data analysis reports.

## Structure

```
shared/scripts/     # Python CSV parsing scripts shared by monthly & weekly reports
monthly-report/     # Monthly report skill (SKILL.md) and config files
weekly-report/      # Weekly report skill (SKILL.md)
daily-report/       # Daily report skill (SKILL.md), config files, and snapshot script
```

## Skills

| Skill | Description |
|-------|-------------|
| monthly-report | Monthly recap report generator |
| weekly-report  | Weekly recap report generator  |
| daily-report   | Daily data monitoring snapshot |

## Shared Scripts

Located in `shared/scripts/`, used by both monthly and weekly reports via `run_all.py`:

- `run_all.py` — Orchestrator, runs all parse scripts and outputs `extracted_data.json`
- `parse_basic.py` — Basic metrics (DAU, revenue, retention)
- `parse_iap.py` — IAP breakdown by entry point
- `parse_spin.py` — Spin data overview
- `parse_resource.py` — Paid user resource monitoring (date comparison)
- `parse_paying_users.py` — Paying user summary by lifecycle group
- `parse_promotion.py` — Promotion/UA monitoring
- `parse_big_r.py` — Big spender user detail
- `validate_daily_report.py` — Validation helper for daily reports
