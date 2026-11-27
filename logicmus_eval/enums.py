from enum import StrEnum


class TemplatePackId(StrEnum):
    PACK_00 = "pack_00"
    PACK_01 = "pack_01"
    PACK_02 = "pack_02"
    PACK_03 = "pack_03"
    PACK_04 = "pack_04"
    MATH_PACK = "math_pack"


class OperatorType(StrEnum):
    FACT = "FACT"
    IMPLIES = "IMPLIES"
    TERMINAL = "TERMINAL"
    NOISE = "NOISE"
    AND_IMPLIES = "AND_IMPLIES"
    OR_FACT = "OR_FACT"
    NUMERIC = "NUMERIC"
    NUMERIC_GT = "NUMERIC_GT"
    NUMERIC_LT = "NUMERIC_LT"
    NUMERIC_EQ = "NUMERIC_EQ"


class RulePrefix(StrEnum):
    CORE_VAR = "V"
    NOISE_VAR = "N"
    CORE_RULE = "R"
    NOISE_RULE = "NR"
    NEUTRAL_VAR = "p"


class CaseStatus(StrEnum):
    SAT = "SAT"
    UNSAT = "UNSAT"


class MetricType(StrEnum):
    WORD_TFIDF = "word_tfidf"
    CHAR_TFIDF = "char_tfidf"


class AnalyzerType(StrEnum):
    WORD = "word"
    CHAR_WB = "char_wb"


class ManifestFilename(StrEnum):
    DATASET_JSONL = "dataset_v2.jsonl"
    MANIFEST_JSON = "dataset_v2.manifest.json"


class FailureTag(StrEnum):
    CORRECT = "correct"
    REFUSAL_NO_FACTS = "refusal_no_facts"
    WRONG_SAT = "wrong_sat"
    WRONG_MUS_MISSING = "wrong_mus_missing"
    WRONG_MUS_EXTRA = "wrong_mus_extra"
    EXEC_ERROR = "exec_error"
    UNKNOWN = "unknown"


class EvaluationStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"


class EvaluationErrorStage(StrEnum):
    REQUEST = "request"
    RESPONSE = "response"
    PARSE = "parse"
    SCHEMA = "schema"
    EXTRACTION = "extraction"
    EXECUTION = "execution"
    RESPONSE_VALIDATION = "response_validation"


class EvaluationErrorCategory(StrEnum):
    API = "api"
    RESPONSE = "response"
    EXECUTION = "execution"


class EvaluationErrorType(StrEnum):
    API_TIMEOUT = "api_timeout"
    API_CONNECTION = "api_connection"
    API_RATE_LIMIT = "api_rate_limit"
    EMPTY_RESPONSE = "empty_response"
    JSON_ERROR = "json_error"
    SCHEMA_ERROR = "schema_error"
    EXTRACTION_ERROR = "extraction_error"
    EXEC_ERROR = "exec_error"
    Z3_TIMEOUT = "z3_timeout"
    Z3_CONTRACT_ERROR = "z3_contract_error"
    Z3_SOLVER_UNKNOWN = "z3_solver_unknown"
    Z3_WORKER_ERROR = "z3_worker_error"
    INVALID_RESPONSE = "invalid_response"
    MISSING_ANSWER = "missing_answer"
    REFUSAL = "refusal"

    @property
    def category(self) -> EvaluationErrorCategory | None:
        if self in {self.API_TIMEOUT, self.API_CONNECTION, self.API_RATE_LIMIT}:
            return EvaluationErrorCategory.API
        if self in {
            self.EXEC_ERROR,
            self.Z3_TIMEOUT,
            self.Z3_CONTRACT_ERROR,
            self.Z3_SOLVER_UNKNOWN,
            self.Z3_WORKER_ERROR,
        }:
            return EvaluationErrorCategory.EXECUTION
        if self is self.REFUSAL:
            return None
        return EvaluationErrorCategory.RESPONSE
