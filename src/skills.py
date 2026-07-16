"""Per-agent skill discovery and prompt injection.

Each agent has its own skills directory under ``Skill/<agent>/``
(where ``<agent>`` is ``doc``, ``researcher``, or ``coder``).
Each ``.md`` file in that directory is a separate skill.

The skills are loaded on demand and serialized into the LLM system
prompt, so the agent knows what it can do and how to do it well.

    Skill/doc/01-read-the-soul.md     <- PhD's "read the SOUL first" skill
    Skill/researcher/01-search.md    <- MS's search skill
    Skill/coder/01-read-guide.md      <- UG's read-the-code-guide skill

The :func:`list_skills` function returns one :class:`Skill` per file
(sorted by filename for stable ordering). The
:func:`format_for_prompt` function renders them as a numbered
Markdown list for inclusion in the LLM system prompt.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

logger = logging.getLogger(__name__)

# Mapping from internal agent id (as used in the agent classes) to
# the directory name under ``Skill/``.
AGENT_SKILL_DIR: Final[dict[str, str]] = {
    "phd": "doc",
    "ms": "researcher",
    "ug": "coder",
}
SHARED_SKILL_DIRNAME: Final[str] = "shared"


@dataclass(frozen=True)
class Skill:
    """A single skill the agent can use."""

    name: str           # slug: e.g. "01-read-the-soul"
    title: str          # first heading or first line
    content: str        # full Markdown body
    path: Path          # absolute path on disk
    scope: str = "agent"  # "shared" or "agent"

    def __str__(self) -> str:  # pragma: no cover - debugging only
        return f"Skill({self.name}, title={self.title!r})"


# ---- Discovery ------------------------------------------------------------


def skills_root() -> Path:
    """Return the path to the project's ``Skill/`` directory."""
    # src/skills.py -> go up 2 parents to reach the repo root.
    return Path(__file__).resolve().parent.parent / "Skill"


def skill_dir_for(agent: str) -> Path:
    """Return the skill directory for an agent id (``phd`` / ``ms`` / ``ug``)."""
    sub = AGENT_SKILL_DIR.get(agent)
    if sub is None:
        raise KeyError(f"unknown agent id: {agent!r} (expected one of {list(AGENT_SKILL_DIR)})")
    return skills_root() / sub


def shared_skill_dir() -> Path:
    """Return the shared skill directory used by all agents."""
    return skills_root() / SHARED_SKILL_DIRNAME


def list_skills(agent: str) -> list[Skill]:
    """Return all skills for ``agent``, sorted by filename.

    Files whose name starts with an underscore (``_foo.md``) are
    treated as private and excluded. Non-``.md`` files are ignored.
    Missing skill dirs return an empty list (the agent just has no
    skills in this install).
    """
    out = _read_skill_dir(shared_skill_dir(), scope="shared")
    root = skill_dir_for(agent)
    if not root.is_dir():
        logger.info("no skill dir for %s at %s", agent, root)
        return out
    out.extend(_read_skill_dir(root, scope="agent"))
    return out


# ---- Prompt formatting ----------------------------------------------------


def format_for_prompt(skills: list[Skill], *, heading: str = "Your skills") -> str:
    """Render ``skills`` as a numbered Markdown list for system prompts.

    Returns an empty string if there are no skills (so the caller can
    always concatenate without a conditional).
    """
    if not skills:
        return ""
    lines: list[str] = [f"## {heading}"]
    lines.append("")
    lines.append(
        "These are your skills. Read them before acting. When a skill "
        "applies to your current task, follow it step by step. When a skill "
        "contradicts the user's direct instruction, the user wins."
    )
    lines.append("")
    shared = [s for s in skills if s.scope == "shared"]
    role_specific = [s for s in skills if s.scope != "shared"]
    if shared:
        lines.append("### Shared operating skills")
        lines.append("")
        for s in shared:
            body = s.content.strip()
            lines.append(f"#### {s.title}")
            lines.append("")
            lines.append(body)
            lines.append("")
    for i, s in enumerate(role_specific, 1):
        # Use the full Markdown content so the LLM sees the
        # instructions, not just a summary. Skill files are
        # small (under 2KB each) so this is cheap.
        body = s.content.strip()
        lines.append(f"### {i}. {s.title}")
        lines.append("")
        lines.append(body)
        lines.append("")
    return "\n".join(lines)


# ---- Internals -------------------------------------------------------------


_HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _read_skill_dir(root: Path, *, scope: str) -> list[Skill]:
    if not root.is_dir():
        return []
    out: list[Skill] = []
    for path in sorted(root.iterdir()):
        if not path.is_file():
            continue
        if not path.name.endswith(".md"):
            continue
        if path.name.startswith("_"):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("failed to read skill %s: %s", path, exc)
            continue
        title = _extract_title(content) or path.stem
        out.append(
            Skill(
                name=path.stem,
                title=title,
                content=content,
                path=path,
                scope=scope,
            )
        )
    return out


def _extract_title(text: str) -> str | None:
    """Return the first Markdown heading in ``text`` (without the ``#``s)."""
    m = _HEADING_RE.search(text)
    return m.group(1).strip() if m else None


__all__ = [
    "AGENT_SKILL_DIR",
    "Skill",
    "format_for_prompt",
    "list_skills",
    "shared_skill_dir",
    "skill_dir_for",
    "skills_root",
]
