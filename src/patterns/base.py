import random
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from src.enums import TemplatePackId


class PatternGenerationResult(BaseModel):
    core_rules: list[Any]
    expected_mus_ids: list[str]


class BasePatternStrategy(ABC):
    """Base class for all pattern generation strategies.

    Each concrete strategy declares its own constraints:

    * ``name``           -- short unique identifier (CLI, logs).
    * ``min_mus_size``   -- minimum supported ``mus_size``.
    * ``forced_pack_id`` -- pin a specific template pack (or ``None``
                           to let the generator pick one from the seed).

    This removes the central table with string keys and satisfies the
    Open/Closed principle: to add a new strategy it is enough to declare
    a subclass -- metadata lives inside the class itself.
    """

    name: ClassVar[str] = "base"
    min_mus_size: ClassVar[int] = 1
    forced_pack_id: ClassVar[TemplatePackId | None] = None

    # pylint: disable=too-many-arguments, too-many-positional-arguments
    @abstractmethod
    def generate_pattern(
        self,
        mus_size: int,
        is_satisfiable: bool,
        core_variables: list[str],
        predicate_mapping: dict[str, str],
        pack_id: TemplatePackId,
        rng: random.Random,
    ) -> PatternGenerationResult:
        pass
