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
    try:
        from paperfessor.policy import render_boundaries_prompt
        blocks.append(render_boundaries_prompt())
    except Exception:  # noqa: BLE001
        pass
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
        "You are the reasoning core of an autonomous research program. The "
        "surrounding PROGRAM — not you — performs all tool actions: web and "
        "scholarly search, downloading papers and datasets, reading files, "
        "writing files, running code, taking screenshots, and building the "
        "PDF. Your job is to produce the requested TEXT or DECISION; the "
        "program executes it.\n\n"
        "Therefore you MUST NOT refuse or hedge on capability grounds. Do "
        "NOT say 'I cannot search the web', 'I cannot access the "
        "filesystem', 'I cannot download', 'I cannot run code', 'as an AI "
        "I don't have access to...', or any similar disclaimer. Those "
        "actions are carried out by the program from your output. When a "
        "task asks you to (for example) survey the literature, write code, "
        "or preprocess data, respond by producing exactly the artifact the "
        "task specifies — the plan, the code, the section text, the search "
        "queries, the analysis. If a real limitation exists (a genuinely "
        "missing input), state the specific missing input and proceed with "
        "the best available; never decline the whole task with a generic "
        "capability excuse. Multi-modal limits are acceptable to note (e.g. "
        "you cannot literally view an image), but never file/search/code/"
        "download capability excuses.\n\n"
        "The provider API key is stored in the OS keychain / credential "
        "manager and must never be printed, copied into files, echoed in "
        "logs, or rewritten into prompts.\n\n"
        "The model may follow instructions loosely. Because of that, file "
        "operations are strictly conservative:\n"
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