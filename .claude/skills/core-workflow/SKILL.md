---
name: core-workflow
description: Example playbook for csm-account-pulse's core repeatable workflow. Rename this skill and rewrite the steps to match the actual deterministic sequence your project runs — e.g. "ingest a manifest and register each row", "generate the weekly report", "draft a document from a template". Skills are for near-deterministic multi-step workflows; if the work needs independent judgment, use an agent instead. Invoked by the worker agent (or directly by the user) when executing this specific workflow.
argument-hint: [input — e.g. path to file, id, URL — or omit to run on the default target]
---

Input: `$ARGUMENTS`

---

## When to use this skill

Use when the caller needs to run csm-account-pulse's core repeatable workflow on a single input. If the caller needs multi-input fan-out, orchestration, or judgment calls, they should spawn an agent (e.g. `worker`) instead — an agent can invoke this skill as one of its steps.

## Phase 1 — Prepare

1. **Resolve the input.** If `$ARGUMENTS` is empty, derive the default target from the project's conventions (e.g. most-recent file in `inputs/`). Otherwise, treat `$ARGUMENTS` as the target.
2. **Validate.** Confirm the target exists, is readable, and matches the expected shape (file type, schema, etc.). If not, stop and return a structured error.
3. **Load supporting context.** Read whatever templates, config, or prior artifacts this workflow depends on. Note the files read so the caller can audit.

## Phase 2 — Execute

Replace this phase with the actual project-specific steps. Template:

1. **<Step 1 verb>** — what this step does, what it produces, what file(s) it writes.
2. **<Step 2 verb>** — ...
3. **<Step 3 verb>** — ...

Each step should be idempotent where possible. If a step has a known-flaky external dependency, document the retry policy inline.

## Phase 3 — Verify

Before declaring success, run the cheap checks:

- All expected output files exist and are non-empty.
- No placeholder strings (`{{...}}`, `TODO`, `FIXME`, `<fill in>`) leaked into generated artifacts.
- If this workflow mutates any shared state, the mutation matches expectations.

If any check fails, treat this as a FAILURE, not a SUCCESS — return what you've got plus the check that failed.

## Phase 4 — Report

Return a structured report the caller can consume:

```
Skill: core-workflow
Status: SUCCESS | FAILURE

On SUCCESS:
- Inputs: <what was processed>
- Outputs: <files produced, with one-line purpose each>
- Checks: <which verification checks passed>

On FAILURE:
- Phase: <Prepare | Execute | Verify>
- Error: <exact error>
- What's recoverable: <partial outputs that are still valid, if any>
- Recommended next step: <e.g. "fix input X and re-run", "blocked pending Y">
```

## Project-specific landmines

<!-- Populate as you encounter them. Each entry saves a future run. -->

- <e.g. "Use `os.replace()` not `shutil.move()` — cross-volume moves fail silently on Windows.">
- <e.g. "After pdf conversion, verify `output.stat().st_size > 0` before deleting the source .docx.">
