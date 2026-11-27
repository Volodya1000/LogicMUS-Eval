"""Protocol limits shared by process management and diagnostic capture."""

from typing import Final

DIAGNOSTIC_LIMIT: Final[int] = 8192
CLEANUP_SECONDS: Final[float] = 1.0
