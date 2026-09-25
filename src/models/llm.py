from pydantic import BaseModel, Field


class DirectReasoningResponse(BaseModel):
    reasoning: str = Field(
        description="Step-by-step reasoning for the logical analysis."
    )
    is_sat: bool = Field(
        description="True if the set of rules is satisfiable, False otherwise."
    )
    conflict_core: list[str] = Field(
        default_factory=list,
        description="List of rule IDs that form the Minimal Unsatisfiable Core (MUS) if unsatisfiable. Empty if satisfiable.",
    )


class LLMToZ3Response(BaseModel):
    reasoning: str = Field(description="Explanation of the formulation strategy.")
    python_z3_code: str = Field(
        description="Valid Python code using the z3-solver library to check satisfiability."
    )
