"""Persistent, atomic paid-call ceiling for an opt-in development continuation.

Reserve before HTTP transport. Failed/in-flight reservations count permanently;
there is no reset/refund command. Retrieval, database and test traffic do not count.
"""

import argparse
import json
import re
import runpy
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any
from unittest.mock import patch

import httpx

from app.core.config import Settings


class ModelCallBudgetExceeded(httpx.RequestError):
    """No request was sent; the persisted reservation ceiling was reached."""


class PersistentModelBudget:
    def __init__(self, path: Path, limit: int = 120) -> None:
        if not 1 <= limit <= 150:
            raise ValueError("Continuation ceiling must be at most 150")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS budget (id INTEGER PRIMARY KEY "
                               "CHECK(id=1), ceiling INTEGER NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, "
                               "model TEXT NOT NULL, provider TEXT NOT NULL, "
                               "purpose TEXT NOT NULL, "
                               "initiated_at TEXT NOT NULL, outcome TEXT NOT NULL, "
                               "http_status INTEGER, latency_ms INTEGER, input_tokens INTEGER, "
                               "output_tokens INTEGER)")
            connection.execute("INSERT OR IGNORE INTO budget VALUES (1, ?)", (limit,))
            if connection.execute("SELECT ceiling FROM budget WHERE id=1").fetchone()[0] != limit:
                raise ValueError("Existing ledger ceiling cannot be changed")

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def reserve(self, model: str, purpose: str) -> int:
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            ceiling = connection.execute("SELECT ceiling FROM budget WHERE id=1").fetchone()[0]
            count = connection.execute("SELECT count(*) FROM calls").fetchone()[0]
            if count >= ceiling:
                raise ModelCallBudgetExceeded("persistent_model_call_budget_exhausted")
            cursor = connection.execute(
                "INSERT INTO calls (model, provider, purpose, initiated_at, outcome) "
                "VALUES (?, 'openai_compatible', ?, ?, 'initiated')",
                (model, purpose, datetime.now(UTC).isoformat()),
            )
            assert cursor.lastrowid is not None
            return cursor.lastrowid

    def finish(self, identifier: int, status: int | None, elapsed_ms: int,
               usage: dict[str, Any]) -> None:
        def token(key: str) -> int | None:
            value = usage.get(key)
            return value if type(value) is int and value >= 0 else None
        with self.connect() as connection:
            connection.execute(
                "UPDATE calls SET outcome=?, http_status=?, latency_ms=?, input_tokens=?, "
                "output_tokens=? WHERE id=? AND outcome='initiated'",
                ("response_success" if status is not None and 200 <= status < 300 else
                 "response_failed", status, elapsed_ms, token("prompt_tokens"),
                 token("completion_tokens"), identifier),
            )

    def summary(self) -> dict[str, Any]:
        with self.connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = [dict(row) for row in connection.execute("SELECT * FROM calls ORDER BY id")]
            ceiling = connection.execute("SELECT ceiling FROM budget WHERE id=1").fetchone()[0]
        return {"ceiling": ceiling, "initiated": len(rows), "remaining": ceiling - len(rows),
                "calls": rows, "counting": "Reservations include failed and interrupted calls"}

    @contextmanager
    def measure(self) -> Iterator[None]:
        original = httpx.AsyncClient.send
        budget = self

        async def guarded_send(client: httpx.AsyncClient, request: httpx.Request,
                               **kwargs: Any) -> httpx.Response:
            if request.method != "POST" or not request.url.path.rstrip("/").endswith(
                ("/chat/completions", "/responses", "/completions"),
            ):
                return await original(client, request, **kwargs)
            try:
                payload = json.loads(request.content)
                model = payload["model"]
                if not isinstance(model, str) or not re.fullmatch(r"[\w./:-]{1,160}", model):
                    raise ValueError("Unbounded model identifier")
            except (ValueError, KeyError, TypeError) as exc:
                raise ModelCallBudgetExceeded("unclassifiable_model_request", request=request
                                              ) from exc
            schema = payload.get("response_format", {}).get("json_schema", {})
            purpose = schema.get("name", "model_call")
            if not isinstance(purpose, str) or not re.fullmatch(r"[\w-]{1,80}", purpose):
                purpose = "model_call"
            identifier = budget.reserve(model, purpose)
            started = monotonic()
            status = None
            usage: dict[str, Any] = {}
            try:
                response = await original(client, request, **kwargs)
                status = response.status_code
                await response.aread()
                try:
                    value = response.json().get("usage")
                    usage = value if isinstance(value, dict) else {}
                except (ValueError, AttributeError):
                    pass
                return response
            finally:
                budget.finish(identifier, status, round((monotonic() - started) * 1000), usage)

        with patch.object(httpx.AsyncClient, "send", guarded_send):
            yield


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--module", help="Guard all model traffic of this app.evaluation module")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    settings = Settings(_env_file="../.env")  # type: ignore[call-arg]
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Development/test only")
    source = Path(__file__).resolve()
    roots = (source.parents[3] / "runtime", source.parents[2] / "runtime")
    if not any(args.ledger.resolve().is_relative_to(root) for root in roots):
        raise SystemExit("Ledger must stay in ignored runtime")
    budget = PersistentModelBudget(args.ledger, args.limit)
    if args.module:
        if not args.module.startswith("app.evaluation."):
            raise SystemExit("Only opt-in evaluation modules are allowed")
        sys.argv = [args.module, *([*args.arguments][1:] if args.arguments[:1] == ["--"]
                                 else args.arguments)]
        with budget.measure():
            runpy.run_module(args.module, run_name="__main__")
    print(json.dumps(budget.summary()))


if __name__ == "__main__":
    main()
