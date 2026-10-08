"""Outbound document planning transport using the configured extraction profile."""

import asyncio
from time import monotonic

import httpx

from app.adapters.claim_extractor import MiriClaimExtractor, OpenAICompatibleClaimExtractor
from app.adapters.document_models import account_limiter
from app.core.config import Settings
from app.judging.models import JudgeSlot


async def post_document_plan(
    adapter: OpenAICompatibleClaimExtractor | MiriClaimExtractor,
    settings: Settings,
    body: dict[str, object],
    headers: dict[str, str],
) -> tuple[httpx.Response, int]:
    """One paid request; queue time is separate from the provider deadline."""
    slot = JudgeSlot(
        slot=1, provider="miri" if isinstance(adapter, MiriClaimExtractor) else "openai_compatible",
        model=adapter.model_id, model_family="extraction", base_url=adapter.base_url,
        api_key=adapter.api_key or "",
    )
    queued = monotonic()
    async with account_limiter(slot, settings.judge_concurrency_limit):
        queue_wait = round((monotonic() - queued) * 1000)
        async with asyncio.timeout(adapter.timeout_seconds):
            async with adapter.build_client() as client:
                response = await client.post(f"{adapter.base_url.rstrip('/')}/chat/completions",
                                             headers=headers, json=body)
    return response, queue_wait
