---
artifact_type: baseline-import-summary
schema_version: "1.0"
kernel_version: "1"
id: import-summary
created_at: "2026-05-26"
updated_at: "2026-05-26"
---

# Import Summary

## Evidence Sources
- [code-backed] Source tree and repository file structure were scanned.
- [doc-backed] Repository documentation files were inspected.
- [doc-backed] CI or workflow definitions were inspected.

## High-Confidence Conclusions
- [code-backed] Top-level directories include .agents, .claude, .github, .pytest_cache.
- [code-backed] Runtime entrypoint candidates include bin/.gitignore, bin/__init__.py, bin/conf_migration_script.py, bin/hummingbot.py.
- [code-backed] Automated verification clues exist: CI/workflow definitions exist under .github/workflows (.github/workflows/docker_buildx_workflow.yml, .github/workflows/workflow.yml).
- [code-backed] Recent completed work WU-017 (WU-017: BTC 1d probability-gap post-sampling settlement-aware analysis。当前 10 天采样已因 run_days_elapsed 停止，DB `.yxg/data/probability_gap_samples_wu013_clean.sqlite` 含 4654 行，覆盖 2026-05-09 到 2026-05-19，且 WU-015/WU-016 已修正 early observable sampling 与分段 schedule。目标：冻结这批样本，做数据质量审计、settlement/proxy settlement 回填、模型验证、模型演进对比与 execution-aware replay，产出下一步是否进入 paper trading、继续采样、还是继续改模型/执行规则的明确结论。范围包括复制 frozen DB、按市场完整度分层、用 official 或 Binance 1m proxy settlement 给已 closed 市场打标签、运行 `scripts/probability_gap_model_validation.py`、`scripts/probability_gap_model_evolution.py`、`scripts/probability_gap_execution_replay.py`，并按 time bucket、side、edge bucket、confidence、gamma、spread、maker/taker/hold 参数网格输出结论。范围外：不改采样调度、不改 live scanner trading eligibility、不接实盘、不重启采样。验证要求：报告能解释哪些市场可用于结论、哪些样本只能辅助观察；settlement 标签来源清楚；replay PnL/EV 扣除当前 fee/spread 假设；给出 go/no-go 与后续 WU 建议。) added durable knowledge about .yxg/data/probability_gap_samples_wu013_clean.sqlite, .yxg/data/probability_gap_samples_20260509_0519_frozen.sqlite, .yxg/data/probability_gap_settlements.json.

## Documentation-Supported Conclusions
- [doc-backed] .pytest_cache/README.md is titled "pytest cache directory #".
- [doc-backed] README.md is titled "Clone the repository".
- [doc-backed] controllers/generic/lp_rebalancer/README.md is titled "LP Rebalancer Controller".

## Low-Confidence Inferences
- [inferred-low-confidence] README suggests the repository centers on "pytest cache directory #".

## Conflicts Or Gaps
- [inferred-low-confidence] package.json is absent, so stack inference is limited.
- [inferred-low-confidence] No local module import graph could be derived from repository source files.
- [inferred-low-confidence] No concrete execution-path narrative could be derived from the current code graph.

## Recommended Next Safe Action
- [inferred-low-confidence] Review the baseline and create the next work unit.
