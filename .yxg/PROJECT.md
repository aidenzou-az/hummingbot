---
artifact_type: project
schema_version: "1.0"
kernel_version: "1"
id: project
status: active
created_at: "2026-04-16"
updated_at: 2026-05-26
---

# Project

## One-Sentence Goal
A repository centered on pytest cache directory #.

## Why This Project Exists
this repository should preserve project understanding and implementation context in durable repository artifacts instead of relying on chat history alone.

## Success Criteria
- The primary runtime surfaces remain healthy across bin/__init__.py, bin/.gitignore, bin/conf_migration_script.py.
- The repository has a clear verification path for future feature work.
- Completed work continues to harden the shared baseline instead of leaving new knowledge only in chat.

## Non-Negotiable Constraints
- Preserve the current runtime contract while evolving the repository.

## Product Principles
- Prefer small, legible feature changes over scope creep during iterative development.

## Engineering Principles
- Record concrete verification evidence in durable artifacts before closing work.

## Out Of Scope
- Do not silently expand the project beyond the repository's stated focus: pytest cache directory #.
- Do not rely on chat history as the only source of project understanding.
- Do not mix unrelated repository cleanup into ordinary feature work without making it explicit.
