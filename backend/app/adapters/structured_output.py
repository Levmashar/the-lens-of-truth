"""Recognize explicit provider rejection of optional structured-output mode."""

from typing import Any

import httpx

_LOCAL_ONLY_KEYWORDS = frozenset({
    "default", "minLength", "maxLength", "pattern", "minItems", "maxItems",
})


def quota_exhausted(response: httpx.Response) -> bool:
    """Recognize an explicit billing/key quota failure without storing its body."""
    if response.status_code not in {402, 403}:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if isinstance(error, dict):
        details = " ".join(str(error.get(key, "")) for key in ("code", "type", "message"))
    elif isinstance(error, str):
        details = error
    else:
        return False
    details = details[:2048].casefold()
    return any(token in details for token in (
        "all_time_limit_exceeded", "api key quota exceeded", "insufficient credits",
        "run out of credits", "insufficient balance",
    ))


def strict_chat_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Use the strict chat-API JSON Schema subset; keep richer checks locally.

    Pydantic permits defaulted fields and length constraints that the strict
    response-format API may reject. The model still has to pass the original
    Pydantic schema, including those constraints, before any judge is stored.
    """

    def normalize(value: Any) -> Any:
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: normalize(item) for key, item in value.items()
                  if key not in _LOCAL_ONLY_KEYWORDS}
        if isinstance(result.get("properties"), dict):
            result["required"] = list(result["properties"])
            result["additionalProperties"] = False
        return result

    result = normalize(schema)
    assert isinstance(result, dict)
    return result


def rejects_json_schema_mode(response: httpx.Response) -> bool:
    """Only a clear mode incompatibility permits a plain-JSON retry.

    A generic 400 (including a bad model ID, context limit, or invalid request)
    must not be disguised as a response-format problem.
    """

    if response.status_code not in {400, 422}:
        return False
    try:
        payload = response.json()
    except ValueError:
        return False
    if not isinstance(payload, dict):
        return False
    error = payload.get("error")
    if isinstance(error, dict):
        details = " ".join(str(error.get(key, "")) for key in ("code", "type", "message"))
    elif isinstance(error, str):
        details = error
    else:
        return False
    details = details[:2048].casefold()
    names_format = any(token in details for token in (
        "response_format", "json_schema", "structured output", "structured_output",
    ))
    rejects_mode = any(token in details for token in (
        "unsupported", "not supported", "does not support", "not available",
        "not implemented", "unknown", "unrecognized", "invalid type",
        "only json_object", "must be json_object",
    ))
    return names_format and rejects_mode
