"""The user-facing 3-agent model: PhDStudent, MasterStudent, Undergraduate.

See the individual modules for status enums and the workspace
contract.
"""

from src.agents.base import _WorkspaceAgent
from src.agents.master import MasterStudent
from src.agents.phd import GuideTask, PhDStudent
from src.agents.status import (
    MasterStatus, PhDStatus, UndergradStatus,
)
from src.agents.undergrad import Undergraduate

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
