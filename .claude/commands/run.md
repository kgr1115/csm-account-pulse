---
description: Run csm-account-pulse's core workflow on a single input.
argument-hint: [input — file path, id, or URL; omit for default target]
---

Run the `core-workflow` skill on the input `$ARGUMENTS` (or the default target if no argument).

If the workflow requires judgment or fan-out across multiple inputs, spawn the `worker` agent with the input(s) instead, and let it invoke the skill as part of its steps.

Report the skill's structured output back to the user verbatim. Do not paraphrase `Status:` — the user reads the status field directly.
