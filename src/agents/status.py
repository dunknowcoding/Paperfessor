"""Status enums + listener infrastructure for the 3-agent model.

The user's spec calls out specific status values for each agent.
The PhD's set is my design (it supervises); MS + UG are exactly as
the user spec requires.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable


class PhDStatus(str, Enum):
    """PhD's user-visible status."""

    PLANNING = "planning"
    DISPATCHING = "dispatching"
    MONITORING = "monitoring"
    REVIEWING = "reviewing"
    WRITING = "writing"
    ARCHIVING = "archiving"
    IDLE = "idle"
    STOPPED = "stopped"


class MasterStatus(str, Enum):
    """MS's user-visible status. Mirrors the user spec exactly."""

    WEBSEARCH = "websearch"
    READING = "reading"
    ANALYZING = "analyzing"
    REPORTING = "reporting"
    IDLE = "idle"
    STOPPED = "stopped"


class UndergradStatus(str, Enum):
    """Undergraduate's user-visible status. Mirrors the user spec exactly."""

    CODING = "coding"
    THINKING = "thinking"
    REPORTING = "reporting"
    IDLE = "idle"
    STOPPED = "stopped"


# Type alias for the listener callback.
StatusListener = Callable[[str, str], None]


__all__ = [
    "MasterStatus",
    "PhDStatus",
    "StatusListener",
    "UndergradStatus",
]
