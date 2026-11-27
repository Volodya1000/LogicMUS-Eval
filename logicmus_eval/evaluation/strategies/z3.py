"""Z3-translation evaluation strategy."""

from logicmus_eval.enums import EvaluationErrorStage
from logicmus_eval.evaluation.strategies.base import (
    PROMPT_TAIL,
    BaseEvaluationStrategy,
    format_rules_block,
    format_variable_block,
)
from logicmus_eval.extractor import StructuredOutputExtractor
from logicmus_eval.models.evaluation import (
    Z3_EXECUTION_PROTOCOL_VERSION,
    CasePrediction,
    ExtractionMetadata,
)
from logicmus_eval.models.llm import LLMToZ3Response
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.sandbox.executor import Z3CodeExecutor

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
    "2. Объяви перечисленные ниже переменные с указанными типами Bool или Real.\n"
    "3. Для каждого входного ID ровно один раз добавь булево ограничение "
    "через solver.assert_and_track(expr, '{ID правила}').\n"
    "4. Импликации задавай через Implies(ant, cons), "
    "не утверждай консеквент напрямую.\n"
    "5. Используй только один Solver() без аргументов. "
    "Не используй add, +=, push/pop, reset, set, assumptions, тактики "
    "или другие конструкторы решателя. Все ограничения регистрируй через "
    "assert_and_track с ID-строкой.\n"
    "6. SAT/UNSAT и минимальное ядро вычислит доверенный исполнитель. "
    "Переменные is_sat и conflict_core не требуются и не определяют итог. "
    "Допустимы check(), unsat_core(), model(), assertions(), reason_unknown().\n"
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

    z3_execution_protocol_version = Z3_EXECUTION_PROTOCOL_VERSION

    def __init__(self, executor: Z3CodeExecutor | None = None) -> None:
        self.executor = executor or Z3CodeExecutor()

    def build_prompt(self, case: LogicTestCase) -> str:
        rules_block = format_rules_block(case)
        variable_block = format_variable_block(case)
        return Z3_PROMPT_TEMPLATE.replace("{rules_block}", rules_block).replace(
            "{variable_block}", variable_block
        )

    def evaluate_case(
        self, case: LogicTestCase, extractor: StructuredOutputExtractor
    ) -> tuple[CasePrediction, ExtractionMetadata]:
        prompt = self.build_prompt(case)
        result = extractor.extract_with_metadata(prompt, LLMToZ3Response)

        rule_ids = [
            rule["id"] if isinstance(rule, dict) else rule.id for rule in case.rules
        ]
        exec_res = self.executor.execute(result.data.python_z3_code, rule_ids)

        prediction = CasePrediction(
            is_sat=exec_res.is_sat,
            conflict_core=exec_res.conflict_core,
            reasoning=result.data.reasoning,
            generated_code=result.data.python_z3_code,
            execution_success=exec_res.success,
            error=exec_res.error,
            error_type=exec_res.error_type,
            error_stage=EvaluationErrorStage.EXECUTION
            if not exec_res.success
            else None,
            raw_response=result.raw_response,
        )
        return prediction, result.metadata
