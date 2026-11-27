"""Expected application errors and their observed diagnostics."""

from logicmus_eval.enums import EvaluationErrorStage, EvaluationErrorType
from logicmus_eval.models.evaluation import ExtractionMetadata


class ExtractorError(Exception):
    """An expected request/response failure, with all observed diagnostics."""

    # Each keyword preserves a distinct observed request/response diagnostic.
    # pylint: disable=too-many-arguments
    def __init__(
        self,
        message: str,
        *,
        error_type: EvaluationErrorType = EvaluationErrorType.EXTRACTION_ERROR,
        stage: EvaluationErrorStage = EvaluationErrorStage.EXTRACTION,
        metadata: ExtractionMetadata | None = None,
        raw_response: str | None = None,
        refusal: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_type: EvaluationErrorType = error_type
        self.stage: EvaluationErrorStage = stage
        self.metadata: ExtractionMetadata = (
            metadata if metadata is not None else ExtractionMetadata()
        )
        self.raw_response: str | None = raw_response
        self.refusal: bool = refusal


class IncompleteReportError(ValueError):
    """A returned report is not evidence of a completed evaluation."""
