from pydantic import BaseModel

from logicmus_eval.models.manifests import TfidfMetrics


class DatasetValidationMetrics(BaseModel):
    sat_valid: int = 0
    unsat_valid: int = 0
    mus_valid: int = 0
    mus_minimal: int = 0


class LeakageReport(BaseModel):
    global_word: tuple[float, float]
    global_char: tuple[float, float]
    by_mus_size: dict[str, dict[str, TfidfMetrics]]
