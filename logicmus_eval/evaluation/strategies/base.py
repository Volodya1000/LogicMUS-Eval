"""Shared base class, prompt fragments and formatting helpers."""

from abc import ABC, abstractmethod

from logicmus_eval.extractor import StructuredOutputExtractor
from logicmus_eval.models.evaluation import CasePrediction, ExtractionMetadata
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.prompt_formatting import format_rules_block, format_variable_block

__all__ = [
    "PROMPT_TAIL",
    "BaseEvaluationStrategy",
    "format_rules_block",
    "format_variable_block",
]

# Common prompt tail shared by both strategies. Kept in one place so the
# <RULES> framing, CASE_ID/UUID epilogue and the final instruction stay
# in sync. Extracted from the per-strategy templates to avoid pylint
# duplicate-code warnings between direct.py and z3.py.
PROMPT_TAIL = "\n\n<RULES>\n{rules_block}\n</RULES>\n\nВерни только JSON.\n"


class BaseEvaluationStrategy(ABC):
    """Abstract interface for all evaluation strategies."""

    @abstractmethod
    def evaluate_case(
        self, case: LogicTestCase, extractor: StructuredOutputExtractor
    ) -> tuple[CasePrediction, ExtractionMetadata]:
        pass
