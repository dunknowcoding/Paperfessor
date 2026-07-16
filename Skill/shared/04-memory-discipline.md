# Memory discipline: record facts, recall carefully

Paperfessor has four memory surfaces: `doc_memo.md` and
`article_memo.md` (PhD-private), `shared/research_log.md` and
`shared/code_log.md` (worker reports), plus the permanent `archived/`
database. Memory exists to *inform* the next decision, never to make
it. These rules are binding for every agent.

## Rules for WRITING memory

1. **Facts with evidence, not narration.** Every entry states what
   happened, the measurable outcome, and where the evidence lives
   (file path inside the workspace, metric value, log entry). If you
   cannot point to evidence, prefix the claim with `unverified:`.
2. **Never write a number you did not measure.** Metrics come from
   `src/results/results.json` or a log produced by an actual run.
3. **One entry per event, dated, tagged with method + stage.** Untagged
   entries cannot be recalled safely and will be dropped at compaction.
4. **Outcome lines are sacred.** Success/failure plus the reason must
   survive any summarization; process narration is what gets cut.
5. **No secrets, no local machine paths, no project-internal names.**
   Workspace-relative paths only.
6. **Write only to your own surface.** MS -> research_log, UG ->
   code_log, PhD -> memos/guides. Never edit another agent's records.

## Rules for USING memory

1. **Priority order when deciding:** current user request > active
   guide tasks > freshest log entries > memos > archive. A memory
   entry NEVER overrides the current user request or an active task.
2. **Recall narrowly.** Read the entries matching the current method
   or stage, most recent first. Do not re-read the whole file and do
   not let unrelated history bleed into the current decision.
3. **Memory is evidence about the past, not instruction for the
   present.** "We did X last time" justifies *considering* X, never
   *skipping the check* that X still applies.
4. **Vetoed stays vetoed.** A method the archive marks as failed for
   theoretical/model reasons is skipped, not retried — unless the
   user explicitly reopens it.
5. **Stale beats wrong: verify before reuse.** If a memo references a
   file, dataset, or result, confirm it still exists before basing a
   decision on it (runs clear `src/code`, `src/figures`,
   `src/results`).
6. **Conflicts are surfaced, not silently resolved.** If memory
   contradicts a fresh log or the user's request, record the conflict
   in your report and follow the higher-priority source.
