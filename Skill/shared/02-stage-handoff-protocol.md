# Skill: Stage handoff and communication protocol

**Agent**: All agents
**When**: Whenever work moves from planning to survey, survey to coding,
coding to writing, writing to review, or any stage is paused, voided, or restarted.

Paperfessor depends on clean handoffs. Every handoff must leave the next agent
with a usable task rather than a vague narrative.

## Handoff packet

When finishing a stage, provide a compact packet with these fields:

- `stage`: the stage that just finished
- `objective`: what this stage tried to achieve
- `inputs used`: sources, files, datasets, or prompts actually used
- `outputs produced`: files, summaries, code paths, figures, or decisions created
- `open risks`: what is still unreliable or unverified
- `next required action`: the exact next task for the next agent
- `stop conditions`: when the next agent must pause or escalate instead of pushing forward

## Per-stage emphasis

- **PhD -> MS**: define the research question, novelty target, venue constraints,
  archive exclusions, and the exact evidence the survey must extract.
- **MS -> PhD**: return evidence clusters, conflicts, benchmark datasets, real
  numbers, and a one-sentence gap statement.
- **PhD -> UG**: translate the method into an implementation checklist with
  datasets, acceptance tests, and failure thresholds.
- **UG -> PhD**: report code status, reproducible commands, validation results,
  blockers, and whether the implementation matches the intended method.
- **PhD -> writing/review**: state the argument the paper section must prove,
  what evidence backs it, and which claims are still provisional.

## Communication rules

1. Report facts before opinions.
2. Use short headings or checklist items so later scans are cheap.
3. If a task is voided, explicitly say which downstream assumptions are now invalid.
4. If user intervention changes direction, repeat the new direction in the next handoff.
5. Never let the next stage infer critical constraints from memory alone.

## Minimal templates

### Research or code log entry

`timestamp | subject`
- objective:
- completed:
- evidence or validation:
- blockers:
- next required action:

### Memo entry extension

- handoff received from:
- handoff sent to:
- unresolved risk carried forward: