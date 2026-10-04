"""Process-local HTTP counting/deadline for opt-in developer evaluations only."""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from unittest.mock import patch

import httpx

evaluation_row: ContextVar[str | None] = ContextVar("evaluation_row", default=None)


@dataclass
class EvaluationBudget:
    max_calls: int
    deadline_seconds: float
    started: float = field(default_factory=monotonic)
    calls: list[dict[str, Any]] = field(default_factory=list)
    failure: str | None = None

    async def before(self, request: httpx.Request) -> None:
        if self.failure:
            raise ValueError(self.failure)
        if monotonic() - self.started >= self.deadline_seconds:
            self.failure = "evaluation_deadline_exceeded"
            raise TimeoutError(self.failure)
        if len(self.calls) >= self.max_calls:
            self.failure = "evaluation_call_budget_exceeded"
            raise ValueError(self.failure)
        request.extensions["evaluation_index"] = len(self.calls)
        request.extensions["evaluation_started"] = monotonic()
        model = None
        if request.content:
            try:
                model = json.loads(request.content).get("model")
            except (ValueError, AttributeError):
                pass
        # Never retain URL, headers, credentials, provider internals or prompts.
        self.calls.append({"model": model, "http_status": None, "elapsed_ms": None,
                           "evaluation_row": evaluation_row.get()})

    async def after(self, response: httpx.Response) -> None:
        await response.aread()
        record = self.calls[response.request.extensions["evaluation_index"]]
        record["http_status"] = response.status_code
        record["elapsed_ms"] = round((monotonic() - response.request.extensions[
            "evaluation_started"]) * 1000)
        try:
            payload = response.json()
            usage = payload.get("usage") or {}
            record["usage"] = {k: v for k, v in usage.items()
                               if k in {"prompt_tokens", "completion_tokens", "total_tokens"}
                               and type(v) is int and v >= 0} if isinstance(usage, dict) else {}
            for key, value in (("returned_model", payload.get("model")),
                               ("system_fingerprint", payload.get("system_fingerprint")),
                               ("response_id", payload.get("id")),
                               ("provider_request_id", response.headers.get("x-request-id"))):
                if isinstance(value, str) and re.fullmatch(r"[\w./:-]{1,160}", value, re.ASCII):
                    record[key] = value
            # Stop an opt-in sweep after an account-wide quota failure. Never
            # log the provider response, switch accounts or retry paid requests.
            if response.status_code == 403 and "ALL_TIME_LIMIT_EXCEEDED" in str(payload):
                self.failure = "provider_quota_exhausted"
        except (ValueError, AttributeError):
            pass

    @contextmanager
    def measure(self) -> Iterator[None]:
        budget = self
        class MeasuredClient(httpx.AsyncClient):
            def __init__(self, **kwargs: Any) -> None:
                kwargs["event_hooks"] = {"request": [budget.before], "response": [budget.after]}
                super().__init__(**kwargs)

        with patch("httpx.AsyncClient", MeasuredClient):
            yield

    def summary(self) -> dict[str, object]:
        return {
            "http_calls": len(self.calls), "elapsed_seconds": round(monotonic() - self.started, 3),
            "failure": self.failure, "calls": self.calls,
            "input_tokens": sum(c.get("usage", {}).get("prompt_tokens", 0) or 0
                                for c in self.calls),
            "output_tokens": sum(c.get("usage", {}).get("completion_tokens", 0) or 0
                                 for c in self.calls),
        }
