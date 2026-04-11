# Requirements Management System

Instructions for Claude Code sessions on how to work with the requirements tracking system in this project. Referenced from the project's `CLAUDE.md`.

## File Structure

```
docs/requirements/
  REQUIREMENTS_INDEX.md     ← Overview table: one row per requirement (ID, title, status, file link, dependencies)
  REQ-xxx.md                ← Copyable template for new requirements
  REQ-001.md                ← One file per requirement
  REQ-002.md
  ...
```

Each requirement lives in its own file. Status changes touch exactly two files: the requirement file and the index. No content is moved between files.

## Requirement File Format

Each `REQ-xxx.md` file contains a single requirement with these fields:

- **Status:** `OPEN` | `IN PROGRESS` | `DONE` | `DROPPED`
- **Added:** Date the requirement was created
- **Completed:** Date the requirement was finished (or `–`)
- **Verified by:** How it was verified (or `–`)
- **Depends on:** Other requirement IDs that must be completed first
- **Description:** What the requirement is and why it exists
- **Acceptance criteria:** Checkable items (`- [ ]` / `- [x]`) that define "done"
- **Notes:** Implementation notes, decisions, references

## Index File Format

`REQUIREMENTS_INDEX.md` is a markdown table with columns:

| ID | Title | Status | File | Depends on |
|----|-------|--------|------|------------|

The File column links to the individual requirement file: `[REQ-001](REQ-001.md)`.

## Workflow Rules

### 1. Reading requirements

- **At session start:** Read `REQUIREMENTS_INDEX.md` to understand overall project state and dependencies.
- **For implementation work:** Read only the specific `REQ-xxx.md` file for the requirement being worked on. Do not load all requirement files into context.

### 2. Completing a requirement

Edit exactly two files:
1. **`REQ-xxx.md`:** Set `Status` to `DONE`, set `Completed` date, check all acceptance criteria boxes (`[x]`).
2. **`REQUIREMENTS_INDEX.md`:** Update the Status column to `DONE`.

No file moves, no content copying.

### 3. Verifying a requirement

Set the `Verified by` field in the requirement file to a short description: e.g. "manual test 2026-02-18", "pytest test_foo.py", "build + visual inspection".

### 4. Authoring new requirements

1. Copy `REQ-xxx.md` to `REQ-NNN.md` (next available ID).
2. Fill in all fields.
3. Add a row to `REQUIREMENTS_INDEX.md`.

Design guidelines:
- **Granularity:** Each requirement should be independently implementable and testable. Split large features into sub-requirements (e.g. REQ-009a/b/c/d).
- **Dependencies:** Explicitly link to prerequisite requirements using `Depends on`.
- **Acceptance criteria:** Concrete, checkable items — not vague goals. Each criterion should be verifiable by running a command, inspecting output, or observing behavior.

### 5. Keeping the index in sync

Any change to a requirement's status, title, or dependencies must be reflected in both the `REQ-xxx.md` file and `REQUIREMENTS_INDEX.md`. These two files must always agree.

### 6. Pre-commit requirements check (mandatory)

**Before every commit that implements or modifies functionality**, do the following:

1. Read `REQUIREMENTS_INDEX.md`.
2. Check if any OPEN requirements have acceptance criteria that the committed code addresses.
3. If found:
   - Check off completed acceptance criteria in the `REQ-xxx.md` file.
   - If all criteria are met: set Status to `DONE`, set `Completed` date.
   - Update `REQUIREMENTS_INDEX.md` to match.
4. Include the requirements docs update in the same commit as the implementation.

This is a mandatory step. Do not commit implementation work without checking and updating requirements docs. The purpose is to prevent requirements from silently becoming stale — if code satisfies a requirement, the docs must reflect that immediately.
