"""Direct-reasoning evaluation strategy (no Z3 translation)."""

from logicmus_eval.evaluation.strategies.base import (
    PROMPT_TAIL,
    BaseEvaluationStrategy,
    format_rules_block,
)
from logicmus_eval.evaluation.strategies.semantics import RULE_SEMANTICS
from logicmus_eval.models.evaluation import CasePrediction, ExtractionMetadata
from logicmus_eval.models.extraction import ExtractionClient
from logicmus_eval.models.llm import DirectReasoningResponse
from logicmus_eval.models.test_case import LogicTestCase

DIRECT_PROMPT_TEMPLATE = (
    "Ты — экспертная система логического вывода. "
    "Проанализируй набор логических правил.\n\n" + RULE_SEMANTICS + "\n"
    'Для совместимого набора верни "is_sat": true и "conflict_core": [].\n'
    'Для несовместимого набора верни "is_sat": false и укажи в "conflict_core" '
    "ID правил из минимального несовместимого подмножества. Это подмножество "
    "должно стать совместимым при удалении любого из его правил. Используй "
    "исходные ID из списка правил.\n"
    "\n"
    "ФОРМАТ ОТВЕТА (JSON):\n"
    "{\n"
    '  "reasoning": "<пошаговое рассуждение здесь>",\n'
    '  "is_sat": <true | false>,\n'
    '  "conflict_core": ["<ID правила>", "..."]\n'
    "}" + PROMPT_TAIL
)


class DirectEvaluationStrategy(BaseEvaluationStrategy):
    """Ask the LLM to reason directly and emit a SAT verdict."""

    def build_prompt(self, case: LogicTestCase) -> str:
        rules_block = format_rules_block(case)
        return DIRECT_PROMPT_TEMPLATE.replace("{rules_block}", rules_block)

    def evaluate_case(
        self, case: LogicTestCase, extractor: ExtractionClient
    ) -> tuple[CasePrediction, ExtractionMetadata]:
        prompt = self.build_prompt(case)
        result = extractor.extract_with_metadata(prompt, DirectReasoningResponse)
        prediction = CasePrediction(
            is_sat=result.data.is_sat,
            conflict_core=result.data.conflict_core,
            reasoning=result.data.reasoning,
            raw_response=result.raw_response,
        )
        return prediction, result.metadata
