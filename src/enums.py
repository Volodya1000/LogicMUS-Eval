from enum import StrEnum


class OperatorType(StrEnum):
    FACT = "fact"
    IMPLIES = "implies"
    TERMINAL = "terminal"
    NOISE = "noise"


class TemplatePackId(StrEnum):
    PACK_00 = "pack_00"
    PACK_01 = "pack_01"
    PACK_02 = "pack_02"
    PACK_03 = "pack_03"
    PACK_04 = "pack_04"
