"""The user-facing 3-agent model: PhDStudent, MasterStudent, Undergraduate.

See the individual modules for status enums and the workspace
contract.
"""

from paperfessor.agents.base import _WorkspaceAgent
from paperfessor.agents.master import MasterStudent
from paperfessor.agents.phd import GuideTask, PhDStudent
from paperfessor.agents.status import (
    MasterStatus, PhDStatus, UndergradStatus,
)
from paperfessor.agents.undergrad import Undergraduate

__all__ = [
    "GuideTask",
    "MasterStatus",
    "MasterStudent",
    "PhDStatus",
    "PhDStudent",
    "UndergradStatus",
    "Undergraduate",
    "_WorkspaceAgent",
]
