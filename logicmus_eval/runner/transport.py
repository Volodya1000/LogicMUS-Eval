"""One explicit OpenAI-compatible HTTP POST. No SDK rewriting or retries."""

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from logicmus_eval.enums import EvaluationErrorType


class TransportError(Exception):
    def __init__(
        self, error_type: EvaluationErrorType, response: dict[str, Any] | None = None
    ) -> None:
        super().__init__(f"HTTP request failed: {error_type.value}")
        self.error_type = error_type
        self.response = response


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def _envelope(data: bytes, status: int, request_id: str | None) -> dict[str, Any]:
    text = data.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return {
        **(parsed if isinstance(parsed, dict) else {}),
        "raw_body": text,
        "http_status": status,
        "request_id": request_id,
        "body_json_error": not isinstance(parsed, dict),
    }


def request_completion(
    *,
    url: str,
    body: dict[str, Any],
    timeout: float,
    transport: dict[str, Any],
    api_key: str | None,
) -> dict[str, Any]:
    if transport != {
        "automatic_retries": 0,
        "follow_redirects": False,
        "environment_proxies": False,
    }:
        raise ValueError("Unsupported transport policy")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    # No implicit proxy/env selection, redirect following, retry or prompt mutation.
    opener = build_opener(ProxyHandler({}), NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            return _envelope(response.read(), 200, response.headers.get("x-request-id"))
    except HTTPError as error:
        envelope = _envelope(
            error.read(), error.code, error.headers.get("x-request-id")
        )
        detail = envelope.get("error")
        code = detail.get("code") if isinstance(detail, dict) else None
        if code in {"context_length_exceeded", "context_window_exceeded"}:
            kind = EvaluationErrorType.CONTEXT_ERROR
        elif error.code == 429:
            kind = EvaluationErrorType.API_RATE_LIMIT
        elif error.code in {408, 504}:
            kind = EvaluationErrorType.API_TIMEOUT
        elif error.code in {500, 502, 503}:
            kind = EvaluationErrorType.API_UNAVAILABLE
        else:
            kind = EvaluationErrorType.API_ERROR
        raise TransportError(kind, envelope) from error
    except TimeoutError as error:
        raise TransportError(EvaluationErrorType.API_TIMEOUT) from error
    except URLError as error:
        kind = (
            EvaluationErrorType.API_TIMEOUT
            if isinstance(error.reason, TimeoutError)
            else EvaluationErrorType.API_CONNECTION
        )
        raise TransportError(kind) from error
