"""Construct unsuccessful results without carrying exceptions over IPC."""

from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.models.evaluation import Z3ExecutionResult
from logicmus_eval.sandbox.errors import ContractError, SolverUnknownError
from logicmus_eval.sandbox.limits import DIAGNOSTIC_LIMIT


def execution_failure(kind: EvaluationErrorType, message: str) -> Z3ExecutionResult:
    return Z3ExecutionResult(
        success=False, error_type=kind, error=message[:DIAGNOSTIC_LIMIT]
    )


def exception_result(error: BaseException) -> Z3ExecutionResult:
    kind: EvaluationErrorType = EvaluationErrorType.EXEC_ERROR
    if isinstance(error, ContractError):
        kind = EvaluationErrorType.Z3_CONTRACT_ERROR
    elif isinstance(error, TimeoutError):
        kind = EvaluationErrorType.Z3_TIMEOUT
    elif isinstance(error, SolverUnknownError):
        kind = EvaluationErrorType.Z3_SOLVER_UNKNOWN
    return execution_failure(kind, f"{type(error).__name__}: {error}")
