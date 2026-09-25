from enum import Enum


class TemplatePackId(str, Enum):
    PACK_00 = "pack_00"
    PACK_01 = "pack_01"
    PACK_02 = "pack_02"
    PACK_03 = "pack_03"
    PACK_04 = "pack_04"


class OperatorType(str, Enum):
    FACT = "FACT"
    IMPLIES = "IMPLIES"
    TERMINAL = "TERMINAL"
    NOISE = "NOISE"
    AND_IMPLIES = "AND_IMPLIES"
    OR_FACT = "OR_FACT"


class RulePrefix(str, Enum):
    CORE_VAR = "V"
    NOISE_VAR = "N"
    CORE_RULE = "R"
    NOISE_RULE = "NR"


class CaseStatus(str, Enum):
    SAT = "SAT"
    UNSAT = "UNSAT"


class MetricType(str, Enum):
    WORD_TFIDF = "word_tfidf"
    CHAR_TFIDF = "char_tfidf"
