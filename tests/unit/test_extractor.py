import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from src.extractor import ExtractorError, StructuredOutputExtractor


class DummyModel(BaseModel):
    value: str
    number: int


@patch("src.extractor.litellm.completion")
def test_extractor_success(mock_completion):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps(
        {"value": "test", "number": 42}
    )
    mock_completion.return_value = mock_response

    extractor = StructuredOutputExtractor("fake-model")
    result = extractor.extract("Hello", DummyModel)

    assert result.value == "test"
    assert result.number == 42


@patch("src.extractor.litellm.completion")
def test_extractor_json_error(mock_completion):
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "not a json"
    mock_completion.return_value = mock_response

    extractor = StructuredOutputExtractor("fake-model")

    with pytest.raises(ExtractorError, match="Failed to parse JSON"):
        extractor.extract("Hello", DummyModel)
