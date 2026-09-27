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
    DATASET_JSONL = "dataset_v1_frozen.jsonl"
    MANIFEST_JSON = "dataset_v1_frozen.manifest.json"


class FailureTag(StrEnum):
    CORRECT = "correct"
    REFUSAL_NO_FACTS = "refusal_no_facts"
    WRONG_SAT = "wrong_sat"
    WRONG_MUS_MISSING = "wrong_mus_missing"
    WRONG_MUS_EXTRA = "wrong_mus_extra"
    EXEC_ERROR = "exec_error"
    UNKNOWN = "unknown"
