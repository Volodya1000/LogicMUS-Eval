from typing import Any

from pydantic import BaseModel, Field

from src.enums import TemplatePackId


class LogicTestCase(BaseModel):
    case_id: str
    mus_size: int
    is_satisfiable: bool
    template_pack_id: TemplatePackId
    predicate_mapping: dict[str, str]
    rules: list[Any]
    mus_expected: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def k(self) -> int:
        return self.mus_size

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()
