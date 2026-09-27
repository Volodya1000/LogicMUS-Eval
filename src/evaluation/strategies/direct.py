"""Direct-reasoning evaluation strategy (no Z3 translation)."""

from uuid import uuid4

from src.evaluation.strategies.base import (
    PROMPT_TAIL,
    BaseEvaluationStrategy,
    format_rules_block,
)
from src.extractor import StructuredOutputExtractor
from src.models.evaluation import CasePrediction, ExtractionMetadata
from src.models.llm import DirectReasoningResponse
from src.models.test_case import LogicTestCase

DIRECT_PROMPT_TEMPLATE = (
    "Ты — экспертная система логического вывода. "
    "Проанализируй набор логических правил.\n"
    "\n"
    "ВАЖНО: Правила с префиксом NR — это фоновые записи.\n"
    "Они НЕ участвуют в логическом выводе. "
    "НЕ включай их в reasoning.\n"
    "НЕ используй их для поиска противоречий. "
    "НЕ добавляй их в conflict_core.\n"
    "Игнорируй их полностью. "
    "Работай ТОЛЬКО с правилами без префикса N.\n"
    "\n"
    "ТВОЯ ЗАДАЧА:\n"
    "Шаг 1. Выпиши все FACT-правила (без префикса NR) как аксиомы.\n"
    "Шаг 2. Применяй modus ponens к IMPLIES-правилам.\n"
    "Шаг 3. Проверь терминальное правило.\n"
    "Шаг 4. Если производное значение конфликтует с терминалом — "
    'установи "is_sat": false и перечисли ID правил, участвующих '
    'в выводе конфликта, в "conflict_core". Если конфликта нет — '
    '"is_sat": true и "conflict_core": [].\n'
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
        return (
            DIRECT_PROMPT_TEMPLATE.replace("{case_id}", case.case_id)
            .replace("{uuid}", str(uuid4()))
            .replace("{rules_block}", rules_block)
        )

    def evaluate_case(
        self, case: LogicTestCase, extractor: StructuredOutputExtractor
    ) -> tuple[CasePrediction, ExtractionMetadata]:
        prompt = self.build_prompt(case)
        result = extractor.extract_with_metadata(prompt, DirectReasoningResponse)
        prediction = CasePrediction(
            is_sat=result.data.is_sat,
            conflict_core=result.data.conflict_core,
            reasoning=result.data.reasoning,
        )
        return prediction, result.metadata
