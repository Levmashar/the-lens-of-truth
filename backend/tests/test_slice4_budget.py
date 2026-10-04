"""No network/paid calls: persistent ceiling survives concurrency and restart."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from app.evaluation.call_budget import ModelCallBudgetExceeded, PersistentModelBudget


def test_atomic_ceiling_and_restart(tmp_path: Path) -> None:
    path = tmp_path / "budget.sqlite3"
    budget = PersistentModelBudget(path, 12)
    def reserve(_: int) -> bool:
        try:
            PersistentModelBudget(path, 12).reserve("family/model", "fixture")
            return True
        except ModelCallBudgetExceeded:
            return False
    with ThreadPoolExecutor(max_workers=6) as pool:
        accepted = list(pool.map(reserve, range(24)))
    assert sum(accepted) == 12
    assert budget.summary()["remaining"] == 0
    assert PersistentModelBudget(path, 12).summary()["initiated"] == 12
    with pytest.raises(ValueError, match="cannot be changed"):
        PersistentModelBudget(path, 13)


def test_transport_guard_counts_failures_not_retrieval(tmp_path: Path) -> None:
    budget = PersistentModelBudget(tmp_path / "budget.sqlite3", 2)
    sent = []
    def respond(request: httpx.Request) -> httpx.Response:
        sent.append(request.url.path)
        return httpx.Response(503 if len(sent) == 1 else 200, json={
            "usage": {"prompt_tokens": 7, "completion_tokens": 3}, "secret": "not retained",
        })
    async def run() -> None:
        with budget.measure():
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                for _ in range(2):
                    await client.post("https://example.invalid/v1/chat/completions",
                                      json={"model": "family/model"})
                await client.get("https://example.invalid/pubmed")
                with pytest.raises(ModelCallBudgetExceeded):
                    await client.post("https://example.invalid/v1/chat/completions",
                                      json={"model": "family/model"})
    asyncio.run(run())
    assert len(sent) == 3
    summary = budget.summary()
    assert summary["initiated"] == 2
    assert [r["outcome"] for r in summary["calls"]] == ["response_failed", "response_success"]
    assert "not retained" not in str(summary)
