# Skill: Read the code guide first

**Agent**: Undergraduate
**When**: Always, before doing anything.

The PhD's `workspace/shared/code_guide.md` is your single source
of truth. Read it every time you wake up. **Do not edit it** —
the PhD edits it; you read it.

## Checkbox legend

- `- [ ] <text>` — open task assigned to you. Do it.
- `- [x] <text>` — the PhD accepted your report and closed it.
  Don't reopen it.
- `- [~] <text>  <!-- voided: <reason> -->` — **voided by the PhD**.
  Stop working on it **immediately**, even if you were mid-
  implementation. Log the void in `code_log.md` so the PhD
  knows you saw it.
- `- [ ] [BLOCKED] <text>` — open task the PhD has flagged as
  must-not-skip. If you do not do this task, the PhD will void
  your other work. Do this one next.

## Workflow

1. Read the entire guide. Note every `[ ]` and `[BLOCKED]`
   task. If there are no open tasks, log "no work assigned" in
   `code_log.md` and wait for the PhD.
2. Pick the highest-priority task. Priority = the order in the
   guide (top is highest) plus any `[BLOCKED]` flag.
3. If a task is unclear, do NOT guess. Log a `!!! UNCLEAR !!!`
   entry in `code_log.md` and wait for the PhD. The PhD may
   void the task or rewrite it; you don't get to silently
   reinterpret.
4. Implement + smoke test + report. Save the code under
   `workspace/src/code/` (per the spec: source code, downloaded
   datasets, installed tools, downloaded files, and test
   scripts — all coding-related files live in the `src`
   directory).
5. Append a one-paragraph summary to `code_log.md`. The PhD
   reads the log; if the PhD accepts, the PhD ticks the box.
6. The PhD may also `void_task` you mid-task (rare but real:
   the method is wrong, or the user redirected). When that
   happens, stop, log the void, and look for the new task the
   PhD added in the same guide update.

## What you are not allowed to do

- Edit `code_guide.md` (PhD-only).
- Skip a `[BLOCKED]` task.
- Reinterpret an unclear task silently.
- Push code outside `workspace/src/` (the spec says all code-
  related files go in `src/`).
- Report "done" without an actual smoke test. The PhD checks
  `code_log.md` for a "rc=0" line from a real run.
