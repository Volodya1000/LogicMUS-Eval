"""Evaluation strategies for direct reasoning and Z3 translation."""

# pylint: disable=line-too-long

from abc import ABC, abstractmethod
from uuid import uuid4

from src.extractor import StructuredOutputExtractor
from src.models.evaluation import CasePrediction, ExtractionMetadata
from src.models.llm import DirectReasoningResponse, LLMToZ3Response
from src.models.test_case import LogicTestCase
from src.sandbox.executor import Z3CodeExecutor

DIRECT_PROMPT_TEMPLATE = r"""CASE_ID: {case_id}
UUID: {uuid}

Ты — экспертная система логического вывода. Проанализируй набор логических правил.

ПРАВИЛА:
{rules_block}

ТВОЯ ЗАДАЧА:
1. Выпиши все факты в виде "Факт: <предикат> = true/false".
2. Применяй modus ponens к цепочкам импликаций: если антецедент истинен, то консеквент тоже истинен.
3. Сравни выведенные значения с терминальными требованиями.
4. Если обнаружено противоречие, определи минимальный набор правил, который его вызывает.
5. Сначала заполни поле "reasoning" пошаговым выводом на русском языке.
6. Затем установи "is_sat": true, если противоречий нет, и false, если есть.
7. Если "is_sat": false, перечисли ID правил, образующих минимальное противоречие, в "conflict_core". Если true — "conflict_core": [].

ФОРМАТ ОТВЕТА (JSON):
{
  "reasoning": "...",
  "is_sat": true,
  "conflict_core": []
}

ПРИМЕР 1 (SAT):
Правила:
R1: Установлен факт: A.
R2: Если A, то B.
R3: Главное требование: B.
Ответ:
{
  "reasoning": "Факт: A = true. Применяю R2: A -> B, значит B = true. Терминал R3 требует B = true. Противоречий нет.",
  "is_sat": true,
  "conflict_core": []
}

ПРИМЕР 2 (UNSAT):
Правила:
R1: Установлен факт: A.
R2: Если A, то B.
R3: Главное требование: not B.
Ответ:
{
  "reasoning": "Факт: A = true. Применяю R2: A -> B, значит B = true. Терминал R3 требует B = false. Противоречие. Минимальный набор: R1, R2, R3.",
  "is_sat": false,
  "conflict_core": ["R1", "R2", "R3"]
}

Теперь реши текущий кейс. Верни только JSON.
"""

Z3_PROMPT_TEMPLATE = r"""CASE_ID: {case_id}
UUID: {uuid}

Ты — эксперт по формальной верификации. Переведи логические правила в исполняемый Python-код с библиотекой z3-solver.

ПРАВИЛА:
{rules_block}

ТРЕБОВАНИЯ К КОДУ:
1. Создай solver = Solver().
2. Для каждого предиката создай Bool-переменную.
3. Каждое правило добавь через solver.assert_and_track(expr, 'RULE_ID').
4. Импликации задавай через Implies(ant, cons), не утверждай консеквент напрямую.
5. Проверь: is_sat = (solver.check() == sat).
6. Если результат unsat, извлеки conflict_core = [str(c) for c in solver.unsat_core()]. Если sat, conflict_core = [].
7. Сначала заполни "reasoning" на русском, затем "python_z3_code" с валидным Python-кодом.

ФОРМАТ ОТВЕТА (JSON):
{
  "reasoning": "...",
  "python_z3_code": "..."
}

ПРИМЕР 1 (SAT):
Правила:
R1: Установлен факт: A.
R2: Если A, то B.
R3: Главное требование: B.
Ответ:
{
  "reasoning": "Создаю переменные A и B. R1 утверждает A. R2 задаёт Implies(A, B). R3 требует B. Проверка даёт sat.",
  "python_z3_code": "from z3 import Solver, Bool, Implies, sat\n\nsolver = Solver()\nA = Bool('A')\nB = Bool('B')\nsolver.assert_and_track(A, 'R1')\nsolver.assert_and_track(Implies(A, B), 'R2')\nsolver.assert_and_track(B, 'R3')\nis_sat = (solver.check() == sat)\nconflict_core = []"
}

ПРИМЕР 2 (UNSAT):
Правила:
R1: Установлен факт: A.
R2: Если A, то B.
R3: Главное требование: not B.
Ответ:
{
  "reasoning": "Создаю переменные A и B. R1 утверждает A. R2 задаёт Implies(A, B). R3 требует Not(B). Проверка даёт unsat, ядро содержит R1, R2, R3.",
  "python_z3_code": "from z3 import Solver, Bool, Implies, Not, sat\n\nsolver = Solver()\nA = Bool('A')\nB = Bool('B')\nsolver.assert_and_track(A, 'R1')\nsolver.assert_and_track(Implies(A, B), 'R2')\nsolver.assert_and_track(Not(B), 'R3')\nis_sat = (solver.check() == sat)\nif not is_sat:\n    conflict_core = [str(c) for c in solver.unsat_core()]\nelse:\n    conflict_core = []"
}

Теперь переведи текущий кейс. Верни только JSON.
"""


class BaseEvaluationStrategy(ABC):
    @abstractmethod
    def evaluate_case(
        self, case: LogicTestCase, extractor: StructuredOutputExtractor
    ) -> tuple[CasePrediction, ExtractionMetadata]:
        pass


class DirectEvaluationStrategy(BaseEvaluationStrategy):
    def build_prompt(self, case: LogicTestCase) -> str:
        rules_block = ""
        for rule in case.rules:
            rule_dict = rule if isinstance(rule, dict) else rule.model_dump()
            rules_block += f"ID: {rule_dict['id']} | Rule: {rule_dict['text']}\n"

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


class Z3TranslationEvaluationStrategy(BaseEvaluationStrategy):
    def __init__(self, executor: Z3CodeExecutor | None = None) -> None:
        self.executor = executor or Z3CodeExecutor()

    def build_prompt(self, case: LogicTestCase) -> str:
        rules_block = ""
        for rule in case.rules:
            rule_dict = rule if isinstance(rule, dict) else rule.model_dump()
            rules_block += f"ID: {rule_dict['id']} | Rule: {rule_dict['text']}\n"

        return (
            Z3_PROMPT_TEMPLATE.replace("{case_id}", case.case_id)
            .replace("{uuid}", str(uuid4()))
            .replace("{rules_block}", rules_block)
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
