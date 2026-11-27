"""Deadline conversion for all SMT checks in one worker."""

import math
import time


def remaining_milliseconds(deadline: float) -> int:
    remaining: float = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Z3 execution deadline exhausted")
    return max(1, min(2**31 - 1, math.ceil(remaining * 1000)))
