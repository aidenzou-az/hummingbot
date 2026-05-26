---
artifact_type: baseline-architecture
schema_version: "1.0"
kernel_version: "1"
id: architecture
created_at: "2026-05-26"
updated_at: "2026-05-26"
---

# Architecture

## Repository Shape
- [code-backed] Top-level directory present: .agents.
- [code-backed] Top-level directory present: .claude.
- [code-backed] Top-level directory present: .github.
- [code-backed] Top-level directory present: .pytest_cache.
- [code-backed] Top-level directory present: __pycache__.
- [code-backed] Top-level directory present: bin.
- [code-backed] Top-level directory present: build.
- [code-backed] Top-level directory present: conf.
- [code-backed] Top-level directory present: controllers.
- [code-backed] Top-level directory present: hummingbot.
- [code-backed] Top-level directory present: logs.
- [code-backed] Top-level directory present: plugins.
- [code-backed] Top-level directory present: scripts.
- [code-backed] Top-level directory present: setup.
- [code-backed] Top-level directory present: test.

## Runtime Entry Points
- [code-backed] bin/__init__.py is a medium-confidence cli entrypoint candidate.
- [code-backed] bin/.gitignore is a medium-confidence cli entrypoint candidate.
- [code-backed] bin/conf_migration_script.py is a medium-confidence cli entrypoint candidate.
- [code-backed] bin/hummingbot_quickstart.py is a medium-confidence cli entrypoint candidate.

## Major Modules
- [code-backed] Recent completed work WU-017 (WU-017: BTC 1d probability-gap post-sampling settlement-aware analysis。当前 10 天采样已因 run_days_elapsed 停止，DB `.yxg/data/probability_gap_samples_wu013_clean.sqlite` 含 4654 行，覆盖 2026-05-09 到 2026-05-19，且 WU-015/WU-016 已修正 early observable sampling 与分段 schedule。目标：冻结这批样本，做数据质量审计、settlement/proxy settlement 回填、模型验证、模型演进对比与 execution-aware replay，产出下一步是否进入 paper trading、继续采样、还是继续改模型/执行规则的明确结论。范围包括复制 frozen DB、按市场完整度分层、用 official 或 Binance 1m proxy settlement 给已 closed 市场打标签、运行 `scripts/probability_gap_model_validation.py`、`scripts/probability_gap_model_evolution.py`、`scripts/probability_gap_execution_replay.py`，并按 time bucket、side、edge bucket、confidence、gamma、spread、maker/taker/hold 参数网格输出结论。范围外：不改采样调度、不改 live scanner trading eligibility、不接实盘、不重启采样。验证要求：报告能解释哪些市场可用于结论、哪些样本只能辅助观察；settlement 标签来源清楚；replay PnL/EV 扣除当前 fee/spread 假设；给出 go/no-go 与后续 WU 建议。) confirmed touch points .yxg/data/probability_gap_samples_wu013_clean.sqlite, .yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite, .yxg/data/probability_gap_settlements.json, scripts/probability_gap_model_validation.py, scripts/probability_gap_model_evolution.py.

## Key Data Flows
- [code-backed] Recent completed work WU-017 established: Current live check on 2026-05-25: LaunchAgent is loaded but not running; logs show `SCHEDULE_STOP ... reason=run_days_elapsed`, so the planned sampling window has completed.
- [code-backed] Recent completed work WU-017 established: Current DB evidence: `.yxg/data/probability_gap_samples_wu013_clean.sqlite` has `4654` rows from `2026-05-09T04:57:35.014045+00:00` to `2026-05-19T05:45:10.741520+00:00`.
- [code-backed] Recent completed work WU-017 established: Current market coverage is uneven: high-row markets include May 9, May 11, May 14, and May 18; May 10, May 12, May 13, May 15, and May 19 are partial or sparse.

## Boundary Notes
- [code-backed] Executable entry points are separated under bin/.
