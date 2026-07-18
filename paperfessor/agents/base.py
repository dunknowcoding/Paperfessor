"""Shared base class for the 3 agents.

Holds:
- A reference to the LLM router
- A reference to the workspace directory
- A status listener registry
- Common methods to set status, fire listeners, and call the LLM
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from paperfessor.config import Settings
from paperfessor.llm.router import LLMRouter

logger = logging.getLogger(__name__)


# Capability-refusal phrases: some models (especially local ones) decline
# tool-shaped tasks with a generic "I can't do X" even though the PROGRAM,
# not the model, performs the action. A short reply matching these is
# treated as a failed attempt and retried with an escalated reminder.
import re as _re

_REFUSAL_PATTERNS = tuple(_re.compile(p, _re.I) for p in (
    r"\bi (?:cannot|can't|can not|am unable to|am not able to)\b[^.]{0,60}"
    r"(?:search|browse|access|download|read|write|open|run|execute|"
    r"the (?:web|internet|file|filesystem))",
    r"\bas an ai\b[^.]{0,80}(?:cannot|can't|do not have|don't have|unable)",
    r"\bi (?:do not|don't) have (?:access|the ability)\b",
    r"\bi'm (?:just|only) a (?:language|text)\b",
    r"\bunable to (?:access|browse|search|download|run|execute)\b",
))


def _is_capability_refusal(text: str | None) -> bool:
    """True when ``text`` is a short reply dominated by a capability
    disclaimer rather than the requested artifact."""
    if not text:
        return False
    t = text.strip()
    # Only treat SHORT replies as refusals — a long, substantive answer
    # that happens to contain a caveat is fine.
    if len(t) > 600:
        return False
    return any(p.search(t) for p in _REFUSAL_PATTERNS)


class _WorkspaceAgent:
    """Common scaffolding for the PhD, MS, and UG agents."""

    def __init__(
        self,
        settings: Settings,
        router: LLMRouter,
        workspace: Path,
        group: str,
    ) -> None:
        self._settings = settings
        self._router = router
        self._workspace = Path(workspace)
        self._group = group  # "phd" | "ms" | "ug"
        self._lock = threading.RLock()
        self._status_listeners: list[Any] = []
        self._status_history: list[dict[str, str]] = []

    # ---- Status broadcast -------------------------------------------

    def add_status_listener(self, fn: Any) -> None:
        with self._lock:
            self._status_listeners.append(fn)

    def _record_status(self, status: str) -> None:
        """Push a status transition onto the in-memory history."""
        from datetime import datetime, timezone
        with self._lock:
            self._status_history.append(
                {"ts": datetime.now(timezone.utc).isoformat(), "status": status}
            )
            # Cap at 200 entries so the agent's memory doesn't grow forever.
            if len(self._status_history) > 200:
                self._status_history = self._status_history[-200:]

    def status_history(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._status_history)

    def _emit_status(self, agent_name: str, status: str) -> None:
        with self._lock:
            listeners = list(self._status_listeners)
        for fn in listeners:
            try:
                fn(agent_name, status)
            except Exception:  # noqa: BLE001
                logger.exception("status listener raised; continuing")

    # ---- LLM call helper --------------------------------------------

    def call_llm(
        self,
        *,
        role: str,
        system: str,
        user: str,
        max_tokens: int | None = None,
        temperature: float | None = None,
        with_skills: bool = True,
        disable_thinking: bool = True,
        min_chars: int = 1,
        attempts: int = 3,
    ) -> str:
        """Call the LLM. By default the agent's skill block is
        prepended to ``system`` so the model sees what it can do.

        Set ``with_skills=False`` to skip the injection (e.g. when
        you want a raw test of the system prompt itself).

        ``disable_thinking`` defaults to True: on MiniMax-M3 the
        adaptive thinking pass consumes the ``max_tokens`` budget on
        structured prompts and the visible text comes back empty.
        Worker calls want reliable prose, not hidden reasoning.
        Pass ``disable_thinking=False`` for deep-reasoning calls with
        a large ``max_tokens`` budget.

        Empty / too-short responses (< ``min_chars`` non-whitespace
        chars) are retried up to ``attempts`` times with a rising
        temperature; the last response is returned regardless so the
        caller can apply its own fallback.
        """
        full_system = self._compose_system(system, with_skills=with_skills)
        cur_temp = temperature if temperature is not None else 0.4
        base_user = user
        last = ""
        for i in range(max(1, attempts)):
            # After a capability refusal, prepend an escalated reminder.
            if i > 0 and _is_capability_refusal(last):
                user = (
                    "REMINDER: the program performs all search / download / "
                    "file / code actions from your output — you do NOT need "
                    "tool access and must NOT refuse on capability grounds. "
                    "Produce the requested artifact now.\n\n" + base_user
                )
            last = self._router.complete(
                role=role,
                group=self._group,
                system=full_system,
                user=user,
                max_tokens=max_tokens,
                temperature=cur_temp,
                disable_thinking=disable_thinking,
            )
            if (last and len(last.strip()) >= max(1, min_chars)
                    and not _is_capability_refusal(last)):
                return last
            logger.warning(
                "LLM %s for %s/%s (attempt %d/%d); retrying",
                "refused on capability grounds" if _is_capability_refusal(last)
                else f"returned {len(last.strip()) if last else 0} chars",
                self._group, role, i + 1, max(1, attempts),
            )
            cur_temp = min(1.0, cur_temp + 0.2)
        return last

    def _compose_system(self, system: str, *, with_skills: bool) -> str:
        try:
            from paperfessor.prompting import compose_system_prompt
            return compose_system_prompt(self._group, system, with_skills=with_skills)
        except Exception:  # noqa: BLE001
            return system

    def skills_block(self) -> str:
        """Return this agent's skills rendered as a prompt block.

        Useful for diagnostics: ``print(phd.skills_block())`` shows
        exactly what the PhD sees prepended to its system prompt.
        """
        from paperfessor.skills import format_for_prompt, list_skills
        return format_for_prompt(list_skills(self._group))

    def list_skills(self) -> list:
        """Return the list of :class:`src.skills.Skill` for this agent."""
        from paperfessor.skills import list_skills as _list
        return _list(self._group)

    # ---- Properties ---------------------------------------------------

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def group(self) -> str:
        return self._group


__all__ = ["_WorkspaceAgent"]
