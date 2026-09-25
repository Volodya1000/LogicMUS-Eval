# pylint: disable=duplicate-code
import random
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from src.enums import TemplatePackId


class PatternGenerationResult(BaseModel):
    core_rules: list[Any]
    expected_mus_ids: list[str]


class BasePatternStrategy(ABC):
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
