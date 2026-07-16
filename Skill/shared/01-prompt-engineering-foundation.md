# Skill: Prompt engineering foundation

**Agent**: All agents
**When**: Before every substantial LLM task, especially when the task changes phase.

Paperfessor is a multi-agent paper-production system. Each agent must not
only "answer the prompt" but also preserve the project contract. When you
receive a task, build your response around five prompt-engineering moves:

1. **Restate the task in operational terms**.
   Convert vague language into a bounded deliverable. Example:
   - vague: "survey the area"
   - operational: "find 8-12 full-text papers from top venues, extract datasets,
     metrics, baselines, and open disagreements"

2. **Declare the output contract before doing the work**.
   Decide what shape the result must take: checklist update, log entry, code diff,
   table, section draft, failure report, or escalation note. Keep the output
   machine-readable when possible.

3. **Separate evidence from inference**.
   - Evidence: quotes, metrics, datasets, reproduced errors, file paths.
   - Inference: your synthesis, recommendation, or diagnosis.
   Never present inference as if it were evidence.

4. **Constrain the next step**.
   End every substantial task by making the next actor's job easier:
   identify what is ready, what is blocked, and what decision remains.

5. **Use anti-drift language**.
   If the current task does not support the paper goal, say so directly.
   Do not expand scope silently. Do not replace missing evidence with filler.

## Required prompt shape

For non-trivial tasks, mentally structure the prompt as:

`goal -> constraints -> available evidence -> required output -> next actor`

If any element is missing, infer only the minimum needed and record that
assumption in your log or memo.

## Failure behavior

If a task cannot be completed correctly:
- state the blocker,
- preserve partial useful outputs,
- recommend the smallest recovery step,
- do not fake completion.