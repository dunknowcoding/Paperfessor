"""Prompt composition helpers for Paperfessor agents.

Centralizes the non-negotiable operating rules that should be
prepended to every agent system prompt, plus the shared and
role-specific skill blocks.
"""

from __future__ import annotations

from typing import Final

from paperfessor.skills import format_for_prompt, list_skills


_GROUP_WRITE_SCOPE: Final[dict[str, tuple[str, ...]]] = {
    "phd": (
        "workspace/doc_memo.md",
        "workspace/article_memo.md",
        "workspace/shared/research_guide.md",
        "workspace/shared/code_guide.md",
        "workspace/paper/",
        "workspace/archived/",
    ),
    "ms": (
        "workspace/shared/research_log.md",
    ),
    "ug": (
        "workspace/src/",
        "workspace/shared/code_log.md",
    ),
}


def compose_system_prompt(group: str, system: str, *, with_skills: bool = True) -> str:
    """Compose the full system prompt for an agent group."""
    blocks: list[str] = []
    if system.strip():
        blocks.append(system.strip())
    blocks.append(_operating_guardrails(group))
    if with_skills:
        skills = list_skills(group)
        skill_block = format_for_prompt(skills)
        if skill_block:
            blocks.append(skill_block)
    return "\n\n".join(block for block in blocks if block.strip())


def _operating_guardrails(group: str) -> str:
    allowed = _GROUP_WRITE_SCOPE.get(group, ("workspace/",))
    allowed_text = "\n".join(f"- {item}" for item in allowed)
    return (
        "## Operating guardrails\n\n"
        "You are running through the MiniMax API configured by the host application. "
        "The key is stored in the OS keychain / Windows Credential Manager path and "
        "must never be printed, copied into files, echoed in logs, or rewritten into prompts.\n\n"
        "MiniMax may follow instructions loosely. Because of that, file operations are "
        "strictly conservative:\n"
        "- Create a file or folder only when the current task explicitly requires it.\n"
        "- Prefer editing an existing file over creating alternates, backups, copies, or scratch files.\n"
        "- Never delete, wipe, or replace a file or folder unless the user, the guide, or the supervising PhD task explicitly authorizes that deletion.\n"
        "- If you think deletion is needed but it was not explicitly authorized, report the candidate path and reason instead of deleting it yourself.\n"
        "- Never write outside your allowed project scope.\n\n"
        "Your allowed write scope for this role is:\n"
        f"{allowed_text}\n\n"
        "Before handing work to the next stage, summarize: what changed, what evidence supports it, "
        "what remains risky, and what the next agent must do."
    )


__all__ = ["compose_system_prompt"]