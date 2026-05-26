---
artifact_type: baseline-risks
schema_version: "1.0"
kernel_version: "1"
id: risks
created_at: "2026-05-26"
updated_at: "2026-05-26"
---

# Risks

## Stale Or Conflicting Documentation
- [doc-backed] none

## Weak Boundaries
- [inferred-low-confidence] unknown

## Verification Gaps
- [code-backed] No explicit test script was detected in package.json.
- [code-backed] No test files were detected from repository file names.
- [code-backed] Recent completed work WU-017 validated Frozen DB exists and row counts match the original at freeze time.; Data-quality report identifies usable and unusable markets..

## Sensitive Paths
- [code-backed] .yxg/ is a framework state root and should be updated intentionally.

## Import Warnings
- [inferred-low-confidence] package.json is absent, so stack inference is limited.
- [inferred-low-confidence] No local module import graph could be derived from repository source files.
- [inferred-low-confidence] No concrete execution-path narrative could be derived from the current code graph.
