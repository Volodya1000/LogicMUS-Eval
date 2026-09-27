import logging

import pytest


@pytest.fixture(autouse=True)
def _silence_logging_errors():
    previous = logging.raiseExceptions
    logging.raiseExceptions = False
    yield
    logging.raiseExceptions = previous
