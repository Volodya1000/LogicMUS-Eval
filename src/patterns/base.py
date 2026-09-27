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

    Each concrete strategy self-describes:

    * ``name``           -- short unique identifier.
    * ``forced_pack_id`` -- pin a template pack (``None`` = pick from seed).

    Support for a given ``mus_size`` is queried via ``supports()``, not
    declared as a ClassVar list: this keeps the registry free of external
    constraints and satisfies the Open/Closed principle.
    """

    name: ClassVar[str] = "base"
    forced_pack_id: ClassVar[TemplatePackId | None] = None

    @classmethod
    def supports(cls, mus_size: int) -> bool:
        """Return True if this strategy can produce a valid case of the
        requested ``mus_size``.

        Default: any size >= 1. Fixed-structure strategies (idem, coverage,
        merge) override this to advertise the exact set of sizes they can
        honour.
        """
        return mus_size >= 1

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
