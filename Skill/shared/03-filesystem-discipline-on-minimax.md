# Skill: Filesystem discipline on MiniMax

**Agent**: All agents
**When**: Any task that might create, rename, move, or delete files or folders.

MiniMax can satisfy the broad idea of a task while still making messy file-system
changes. Assume the model needs an explicit brake.

## Rules

1. Do not create scratch files at the project root.
2. Do not create parallel "final", "new", "fixed", "backup", or timestamped copies
   unless the task explicitly asks for them.
3. Do not delete a file just because it looks old. Delete only when the user,
   the guide, or the supervising stage explicitly says it is redundant.
4. Stay inside your role's write scope.
5. When the safest action is unclear, log the candidate change and escalate instead
   of touching the file tree.

## Role scopes

- **PhD**: memos, guides, paper artifacts, archive metadata.
- **MS**: `shared/research_log.md` only.
- **UG**: `workspace/src/` and `shared/code_log.md`.

## Before any deletion

Ask yourself:
- Is this deletion explicitly authorized?
- Is there a simpler edit that avoids deletion?
- Will the next stage lose needed evidence if I remove this path?

If any answer is uncertain, do not delete the path.