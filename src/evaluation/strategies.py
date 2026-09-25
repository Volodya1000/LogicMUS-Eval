from abc import ABC, abstractmethod

from src.extractor import StructuredOutputExtractor
from src.models.evaluation import CasePrediction, ExtractionMetadata
from src.models.llm import DirectReasoningResponse, LLMToZ3Response
from src.models.test_case import LogicTestCase
from src.sandbox.executor import Z3CodeExecutor


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
            "You are an expert logical reasoning system. Analyze the following set of logical rules.\n\n"
            f"RULES:\n{rules_block}\n\n"
            "You MUST write your step-by-step logical deduction in the 'reasoning' JSON field FIRST.\n"
            "Inside your reasoning, explicitly write out:\n"
            "1. FACT: What are the initial given true/false states?\n"
            "2. CHAIN: Apply implications step-by-step.\n"
            "3. CONTRADICTION CHECK: Compare derived states with requirements.\n"
            "4. CONCLUSION: State clearly if there is a contradiction or not.\n\n"
            "Only AFTER writing this detailed reasoning, set 'is_sat' to true or false. "
            "If there is a contradiction, list the conflicting rule IDs in 'conflict_core'."
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
            "You are an expert formal verification engineer. Translate the following logical rules "
            "into valid, executable Python code using the z3-solver library.\n\n"
            f"RULES:\n{rules_block}\n\n"
            "CODE CONVENTIONS:\n"
            "1. Instantiate a solver: `solver = Solver()`\n"
            "2. Define boolean variables for each predicate, e.g. `p1 = Bool('...')`\n"
            "3. Assert each rule using trackable assertions: `solver.assert_and_track(assertion, 'RULE_ID')`\n"
            "4. Check satisfiability: `is_sat = (solver.check() == sat)`\n"
            "5. If unsatisfiable, extract core: `conflict_core = [str(c) for c in solver.unsat_core()]`, else `conflict_core = []`\n"
            "Return valid Python code in the `python_z3_code` field."
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
