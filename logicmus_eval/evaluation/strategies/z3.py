"""Z3-translation evaluation strategy."""

from logicmus_eval.enums import EvaluationErrorStage
from logicmus_eval.evaluation.strategies.base import (
    BaseEvaluationStrategy,
    format_rules_block,
    format_variable_block,
)
from logicmus_eval.evaluation.strategies.z3_prompt import (
    Z3_PROMPT_TEMPLATE,
)
from logicmus_eval.extractor import ExtractionResult, StructuredOutputExtractor
from logicmus_eval.models.evaluation import (
    Z3_EXECUTION_PROTOCOL_VERSION,
    CasePrediction,
    ExtractionMetadata,
    Z3ExecutionResult,
)
from logicmus_eval.models.llm import LLMToZ3Response
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.sandbox.executor import Z3CodeExecutor

__all__: list[str] = ["Z3_PROMPT_TEMPLATE", "Z3TranslationEvaluationStrategy"]


class Z3TranslationEvaluationStrategy(BaseEvaluationStrategy):
    """Ask the LLM to translate the case to Z3 Python, then execute it."""

    z3_execution_protocol_version: str = Z3_EXECUTION_PROTOCOL_VERSION

    def __init__(self, executor: Z3CodeExecutor | None = None) -> None:
        self.executor: Z3CodeExecutor = executor or Z3CodeExecutor()

    def build_prompt(self, case: LogicTestCase) -> str:
        rules_block: str = format_rules_block(case)
        variable_block: str = format_variable_block(case)
        return Z3_PROMPT_TEMPLATE.replace("{rules_block}", rules_block).replace(
            "{variable_block}", variable_block
        )

    def evaluate_case(
        self, case: LogicTestCase, extractor: StructuredOutputExtractor
    ) -> tuple[CasePrediction, ExtractionMetadata]:
        prompt: str = self.build_prompt(case)
        result: ExtractionResult[LLMToZ3Response] = extractor.extract_with_metadata(
            prompt, LLMToZ3Response
        )

        rule_ids: list[str] = [
            rule["id"] if isinstance(rule, dict) else rule.id for rule in case.rules
        ]
        exec_res: Z3ExecutionResult = self.executor.execute(
            result.data.python_z3_code, rule_ids
        )

        prediction: CasePrediction = CasePrediction(
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
