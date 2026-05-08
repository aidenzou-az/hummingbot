---
artifact_type: baseline-architecture
schema_version: "1.0"
kernel_version: "1"
id: architecture
created_at: "2026-05-08"
updated_at: "2026-05-08"
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
- [code-backed] Recent completed work WU-006 (WU-006: BTC 1d probability gap 模型 edge validation 与 settlement labeling。基于 WU-005 结论，补官方或可靠 proxy settlement outcome，验证 iv_digital_v1/A_edge/A_residual 对最终 settlement PnL 的 calibration、Brier/log loss、edge bucket -> final PnL；区分模型错误和执行错误。明确 out of scope: 不改定价模型、不做真实交易、不做 paper trading。) confirmed touch points [controllers/generic/probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/controllers/generic/probability_gap_execution_replay.py:1), A new settlement/model-validation helper module if needed under `controllers/generic/`., [scripts/probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/scripts/probability_gap_execution_replay.py:1) or a new CLI script for settlement validation., [test/controllers/test_probability_gap_execution_replay.py](/Users/bytedance/Projects/hummingbot/test/controllers/test_probability_gap_execution_replay.py:1) or a new focused model-validation test file., .yxg/data/probability_gap_samples_iv_v1.sqlite` as the current sample corpus..

## Key Data Flows
- [code-backed] Recent completed work WU-006 established: WU-005 showed `A_edge` and `A_residual` have positive short-horizon return correlation, but maker fill is toxic and settlement validation is missing.
- [code-backed] Recent completed work WU-006 established: Cross-model checks showed `iv_digital_v1` has the strongest closeout-return ranking among tested models, but current samples are not enough for final EV claims.
- [code-backed] Recent completed work WU-006 established: Current SQLite snapshots did not include official `settlement_outcome`; near-final proxy checks were possible only for a small number of markets.

## Boundary Notes
- [code-backed] Executable entry points are separated under bin/.
