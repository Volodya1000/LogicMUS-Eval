"""Instructions for the Python/Z3 formalization protocol."""

from logicmus_eval.evaluation.strategies.base import PROMPT_TAIL
from logicmus_eval.evaluation.strategies.semantics import RULE_SEMANTICS

Z3_PROMPT_TEMPLATE: str = (
    "Ты — эксперт по формальной верификации. "
    "Переведи логические правила в исполняемый Python-код "
    "с библиотекой z3-solver.\n\n" + RULE_SEMANTICS + "\n"
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
    "- Объединять разные предикаты в одну переменную.\n"
    "- Вводить отдельную переменную для отрицания предиката X. "
    "Его отрицание выражается через Not(X).\n"
    "\n"
    "ФОРМАТ ОТВЕТА (JSON):\n"
    "{\n"
    '  "reasoning": "<пошаговое рассуждение здесь>",\n'
    '  "python_z3_code": "<валидный Python-код>"\n'
    "}" + PROMPT_TAIL
)
