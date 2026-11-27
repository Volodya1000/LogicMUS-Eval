import io
import json
from email.message import Message
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from logicmus_eval.runner import transport


def test_raw_http_preserves_unknown_usage_and_exact_payload(monkeypatch):

    payload = {
        "model": "served-id",
        "messages": [{"role": "user", "content": "exact"}],
        "max_tokens": 9,
        "seed": 42,
        "reasoning_effort": "low",
    }
    raw = {"id": "response-id", "choices": [], "usage": None}
    response = Mock()
    response.read.return_value = json.dumps(raw).encode()
    response.headers = {"x-request-id": "wire-request"}
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    factory = Mock(return_value=opener)
    monkeypatch.setattr(transport, "build_opener", factory)
    result = transport.request_completion(
        url="http://localhost/v1/chat/completions",
        body=payload,
        timeout=7.0,
        transport={
            "automatic_retries": 0,
            "follow_redirects": False,
            "environment_proxies": False,
        },
        api_key=None,
    )
    assert result["usage"] is None
    assert result["request_id"] == "wire-request"
    args, kwargs = opener.open.call_args
    assert json.loads(args[0].data) == payload
    assert kwargs["timeout"] == 7.0
    assert args[0].get_header("Authorization") is None
    assert opener.open.call_count == 1


def test_bad_request_never_retries_or_rewrites_prompt(monkeypatch):

    message = {
        "error": {
            "message": "Last message must have role `user`",
            "code": "bad_request",
        }
    }
    failure = HTTPError(
        "http://localhost",
        400,
        "Bad request",
        Message(),
        io.BytesIO(json.dumps(message).encode()),
    )
    opener = Mock()
    opener.open.side_effect = failure
    monkeypatch.setattr(transport, "build_opener", lambda *_: opener)
    body = {"model": "served-id", "messages": [{"role": "user", "content": "exact"}]}
    with pytest.raises(transport.TransportError) as caught:
        transport.request_completion(
            url="http://localhost/v1/chat/completions",
            body=body,
            timeout=1.0,
            transport={
                "automatic_retries": 0,
                "follow_redirects": False,
                "environment_proxies": False,
            },
            api_key="secret",
        )
    assert caught.value.error_type.value == "api_error"
    assert opener.open.call_count == 1
    assert json.loads(opener.open.call_args.args[0].data) == body


@pytest.mark.parametrize(
    "status,code,expected",
    [
        (400, "context_length_exceeded", "context_error"),
        (429, "rate_limit_exceeded", "api_rate_limit"),
        (503, "unavailable", "api_unavailable"),
    ],
)
def test_http_status_classification(monkeypatch, status, code, expected):

    failure = HTTPError(
        "http://localhost",
        status,
        "failure",
        Message(),
        io.BytesIO(json.dumps({"error": {"code": code}}).encode()),
    )
    opener = Mock()
    opener.open.side_effect = failure
    monkeypatch.setattr(transport, "build_opener", lambda *_: opener)
    with pytest.raises(transport.TransportError) as caught:
        transport.request_completion(
            url="http://localhost",
            body={},
            timeout=1.0,
            transport={
                "automatic_retries": 0,
                "follow_redirects": False,
                "environment_proxies": False,
            },
            api_key=None,
        )
    assert caught.value.error_type.value == expected
