import json
import tempfile
from pathlib import Path

from src.enums import TemplatePackId
from src.evaluation.pipeline import EvaluationPipeline
from src.evaluation.strategies import DirectEvaluationStrategy
from src.extractor import ExtractionResult
from src.models.evaluation import ExtractionMetadata
from src.models.llm import DirectReasoningResponse
from src.models.test_case import LogicTestCase


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
        assert len(data["details"][0]["rules"]) == 1
        assert data["details"][0]["rules"][0]["id"] == "R1"
        assert data["details"][0]["reasoning"] == "dummy reasoning"
