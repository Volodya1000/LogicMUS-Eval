"""Z3-translation evaluation strategy."""

from uuid import uuid4

from src.evaluation.strategies.base import (
    PROMPT_TAIL,
    BaseEvaluationStrategy,
    format_rules_block,
    format_variable_block,
)
from src.extractor import StructuredOutputExtractor
from src.models.evaluation import CasePrediction, ExtractionMetadata
from src.models.llm import LLMToZ3Response
from src.models.test_case import LogicTestCase
from src.sandbox.executor import Z3CodeExecutor

Z3_PROMPT_TEMPLATE = (
    "Ты — эксперт по формальной верификации. "
    "Переведи логические правила в исполняемый Python-код "
    "с библиотекой z3-solver.\n"
    "\n"
    "ВАЖНО: Не все правила обязательно участвуют в выводе. Обрабатывай все "
    "правила через assert_and_track, но помни, что некоторые могут быть "
    "избыточными — они не должны попасть в unsat_core.\n"
    "\n"
    "ТРЕБОВАНИЯ К КОДУ:\n"
    "1. Создай solver = Solver().\n"
    "2. Объяви ровно те Bool-переменные, которые перечислены ниже.\n"
    "3. Для каждого правила добавь ограничение "
    "через solver.assert_and_track(expr, '{ID правила}').\n"
    "4. Импликации задавай через Implies(ant, cons), "
    "не утверждай консеквент напрямую.\n"
    "5. Проверь: is_sat = (solver.check() == sat).\n"
    "6. Если результат unsat, извлеки "
    "conflict_core = [str(c) for c in solver.unsat_core()]. "
    "Если sat, conflict_core = [].\n"
    "7. Сначала заполни 'reasoning' на русском, затем "
    "'python_z3_code' с валидным Python-кодом.\n"
    "\n"
    "ОБЪЯВИ РОВНО ЭТИ ПЕРЕМЕННЫЕ (не больше, не меньше):\n"
    "{variable_block}\n"
    "\n"
    "ЗАПРЕЩЕНО:\n"
    "- Использовать ID правила как имя Bool-переменной.\n"
    "- Создавать переменные, которых нет в списке выше.\n"
    "- Использовать переменную до её объявления.\n"
    "- Объединять разные предикаты в одну переменную "
    "(например, 'X' и 'неверно, что X' — это две разные "
    "переменные X и Not(X)).\n"
    "\n"
    "ФОРМАТ ОТВЕТА (JSON):\n"
    "{\n"
    '  "reasoning": "<пошаговое рассуждение здесь>",\n'
    '  "python_z3_code": "<валидный Python-код>"\n'
    "}" + PROMPT_TAIL
)


class Z3TranslationEvaluationStrategy(BaseEvaluationStrategy):
    """Ask the LLM to translate the case to Z3 Python, then execute it."""

    def __init__(self, executor: Z3CodeExecutor | None = None) -> None:
        self.executor = executor or Z3CodeExecutor()

    def build_prompt(self, case: LogicTestCase) -> str:
        rules_block = format_rules_block(case)
        variable_block = format_variable_block(case)
        return (
            Z3_PROMPT_TEMPLATE.replace("{case_id}", case.case_id)
            .replace("{uuid}", str(uuid4()))
            .replace("{rules_block}", rules_block)
            .replace("{variable_block}", variable_block)
        )

    def evaluate_case(
        self, case: LogicTestCase, extractor: StructuredOutputExtractor
    ) -> tuple[CasePrediction, ExtractionMetadata]:
        prompt = self.build_prompt(case)
        result = extractor.extract_with_metadata(prompt, LLMToZ3Response)

        exec_res = self.executor.execute(result.data.python_z3_code)

        prediction = CasePrediction(
            is_sat=exec_res.is_sat,
            conflict_core=exec_res.conflict_core,
            reasoning=result.data.reasoning,
            generated_code=result.data.python_z3_code,
            execution_success=exec_res.success,
            error=exec_res.error,
        )
        return prediction, result.metadata
