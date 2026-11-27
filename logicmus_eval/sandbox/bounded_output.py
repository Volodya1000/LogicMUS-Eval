"""Bounded diagnostic stream for a generated program."""

import io

from logicmus_eval.sandbox.limits import DIAGNOSTIC_LIMIT


class BoundedOutput(io.TextIOBase):
    """Discard diagnostic overflow while reporting successful writes to print."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.size: int = 0

    def write(self, text: str) -> int:
        part: str = text[: max(0, DIAGNOSTIC_LIMIT - self.size)]
        if part:
            self.parts.append(part)
        self.size += len(part)
        return len(text)

    def getvalue(self) -> str:
        return "".join(self.parts)
