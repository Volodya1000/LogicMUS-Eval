import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from logicmus_eval.enums import TemplatePackId
from logicmus_eval.evaluation.pipeline import EvaluationPipeline
from logicmus_eval.evaluation.strategies import DirectEvaluationStrategy
from logicmus_eval.extractor import ExtractionResult
from logicmus_eval.models.evaluation import (
    EvaluationCaseReport,
    EvaluationSummary,
    ExtractionMetadata,
    RunInfo,
)
from logicmus_eval.models.llm import DirectReasoningResponse
from logicmus_eval.models.test_case import LogicTestCase


class DummyExtractor:
    def extract_with_metadata(self, _prompt, _response_model):
        resp = DirectReasoningResponse(
            reasoning="dummy reasoning", is_sat=True, conflict_core=[]
        )
        return ExtractionResult(data=resp, metadata=ExtractionMetadata())


def test_pipeline_saves_intermediate_results():
    strategy = DirectEvaluationStrategy()
    extractor = DummyExtractor()
    pipeline = EvaluationPipeline(strategy=strategy, extractor=extractor, metrics=[])

    case = LogicTestCase(
        case_id="test_id_1",
        mus_size=2,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={},
        rules=[{"id": "R1", "text": "Test rule", "operator_type": "FACT"}],
        mus_expected=[],
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_path = Path(tmp_dir) / "partial_output.json"

        pipeline.run([case], limit=1, output_path=output_path)

        assert output_path.exists()
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["details"]) == 1
        assert data["details"][0]["case_id"] == "test_id_1"
        assert data["details"][0]["reasoning"] == "dummy reasoning"


def test_evaluation_summary_preserves_run_info():
    started = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2024, 1, 1, 12, 5, 0, tzinfo=UTC)

    run_info = RunInfo(
        model_name="test-model",
        strategy="direct",
        dataset_filename="dataset_v1_frozen.jsonl",
        dataset_sha256="abc123",
        prompt_template_hash="def456",
        git_commit="0123456789abcdef",
        started_at=started,
        finished_at=finished,
        limit=2,
        total_cases_processed=2,
    )

    case_report = EvaluationCaseReport(
        case_id="c1",
        mus_size=2,
        expected_sat=True,
        predicted_sat=True,
        is_sat_correct=True,
        expected_mus=[],
        predicted_mus=[],
        is_mus_correct=False,
        metadata=ExtractionMetadata(),
        reasoning="ok",
    )

    summary = EvaluationSummary(
        metrics={"sat_accuracy": 1.0},
        details=[case_report],
        run_info=run_info,
    )

    dumped = summary.model_dump()
    assert "run_info" in dumped
    assert dumped["run_info"]["model_name"] == "test-model"
    assert dumped["run_info"]["dataset_filename"] == "dataset_v1_frozen.jsonl"
    assert dumped["run_info"]["dataset_sha256"] == "abc123"
    assert dumped["run_info"]["prompt_template_hash"] == "def456"
    assert dumped["run_info"]["git_commit"] == "0123456789abcdef"
    assert dumped["run_info"]["limit"] == 2
    assert dumped["run_info"]["total_cases_processed"] == 2

    restored = EvaluationSummary.model_validate(dumped)
    assert restored.run_info is not None
    assert restored.run_info.dataset_sha256 == "abc123"
    assert restored.run_info.total_cases_processed == 2
