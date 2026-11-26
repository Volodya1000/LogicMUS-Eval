import logging
import os

import pytest

# Tests must not download LiteLLM's cost map at import time.
os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"


@pytest.fixture(autouse=True)
def _silence_logging_errors():
    previous = logging.raiseExceptions
    logging.raiseExceptions = False
    yield
    logging.raiseExceptions = previous
