"""Concurrent independent judge calls over one validated frozen evidence view."""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.adapters.judge import JudgeProvider, ProviderFailure
from app.judging.config import is_search_enabled_model
from app.judging.models import (
    DisagreementSummary,
    JudgeDecision,
    JudgeRun,
    JudgeSlot,
    describe_disagreement,
)
from app.judging.prompt import PROMPT_VERSION, PreparedJudgeInput, prepare_judge_input
from app.retrieval.models import EvidencePack

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    """Small per-slot process-local breaker; never shared between model families."""

    threshold: int = 2
    cooldown_seconds: float = 60.0
    consecutive_failures: dict[int, int] = field(default_factory=dict)
    open_until: dict[int, float] = field(default_factory=dict)

    def available(self, slot: int) -> bool:
        return monotonic() >= self.open_until.get(slot, 0.0)

    def record(self, slot: int, *, success: bool) -> None:
        if success:
            self.consecutive_failures[slot] = 0
            self.open_until.pop(slot, None)
            return
        count = self.consecutive_failures.get(slot, 0) + 1
        self.consecutive_failures[slot] = count
        if count >= self.threshold:
            self.open_until[slot] = monotonic() + self.cooldown_seconds


@dataclass
class JudgeService:
    providers: dict[str, JudgeProvider]
    attempt_timeout_seconds: float = 45.0
    total_timeout_seconds: float = 80.0
    concurrency_limit: int = 3
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)

    async def run(
        self, pack_id: UUID, pack: EvidencePack, slots: tuple[JudgeSlot, ...], *,
        allow_same_family: bool = False,
        app_env: Literal["development", "test", "staging", "production"] = "production",
        allow_search_enabled_development: bool = False,
    ) -> tuple[tuple[JudgeRun, ...], DisagreementSummary]:
        """Run all available slots concurrently; failures remain individual records."""

        if not slots:
            raise ValueError("Configure at least one judge slot")
        if len({slot.slot for slot in slots}) != len(slots):
            raise ValueError("Duplicate judge slot")
        families = [slot.model_family.casefold() for slot in slots]
        if not allow_same_family and len(set(families)) != len(families):
            raise ValueError("Judge slots must use distinct model families")
        search_slots = tuple(slot for slot in slots if is_search_enabled_model(slot.model))
        if search_slots:
            if app_env not in {"development", "test"} or not allow_search_enabled_development:
                raise ValueError("Search-enabled judge model mode is not permitted")
            if not all(slot.search_override_active for slot in slots):
                raise ValueError("Search override audit marker is missing from a judge slot")
            if not all(slot.search_guard_bypassed for slot in search_slots):
                raise ValueError("Search guard bypass audit marker is missing")
        elif any(slot.search_override_active for slot in slots):
            raise ValueError("Search override audit marker requires a search-enabled model")
        if any(slot.search_guard_bypassed and not is_search_enabled_model(slot.model)
               for slot in slots):
            raise ValueError("Non-search judge cannot have a bypass marker")
        if self.concurrency_limit < 1:
            raise ValueError("Judge concurrency limit must be positive")
        prepared = prepare_judge_input(pack_id, pack)
        semaphore = asyncio.Semaphore(self.concurrency_limit)

        async def one(slot: JudgeSlot) -> JudgeRun:
            async with semaphore:
                return await self._run_slot(pack, prepared, slot)

        runs = tuple(await asyncio.gather(*(one(slot) for slot in slots)))
        return runs, describe_disagreement(runs)

    async def _run_slot(
        self, pack: EvidencePack, prepared: PreparedJudgeInput, slot: JudgeSlot,
    ) -> JudgeRun:
        requested_at = datetime.now(UTC)
        started = monotonic()
        attempts = 0
        decision: JudgeDecision | None = None
        response_json: dict[str, object] | None = None
        error: str | None = None
        failure_request_id: str | None = None
        provider_response = None
        provider = self.providers.get(slot.provider)
        if not self.breaker.available(slot.slot):
            error = "circuit_open"
        elif provider is None:
            error = "provider_unconfigured"
        else:
            try:
                async with asyncio.timeout(self.total_timeout_seconds):
                    for attempts in (1, 2):
                        provider_response = None
                        failure_request_id = None
                        try:
                            async with asyncio.timeout(self.attempt_timeout_seconds):
                                provider_response = await provider.evaluate(slot, prepared)
                                decision = parse_decision(
                                    provider_response.content, prepared.selected_ids,
                                )
                            response_json = decision.model_dump(mode="json")
                            error = None
                            break
                        except TimeoutError:
                            error, retryable = "timeout", True
                        except ProviderFailure as exc:
                            error, retryable = exc.category, exc.retryable
                            failure_request_id = exc.provider_request_id
                        except DecisionFailure as exc:
                            error, retryable = exc.category, exc.retryable
                        logger.warning(
                            "judge_attempt slot=%d provider=%s model=%s family=%s "
                            "attempt=%d failure=%s elapsed_ms=%d retry=%s",
                            slot.slot, slot.provider, slot.model, slot.model_family,
                            attempts, error, round((monotonic() - started) * 1000),
                            attempts == 1 and retryable,
                        )
                        if not retryable:
                            break
            except TimeoutError:
                error = "timeout"
            except Exception as exc:
                logger.error(
                    "judge_internal_failure slot=%d failure_class=%s",
                    slot.slot, type(exc).__name__,
                )
                error = "internal_error"
        if error is None:
            self.breaker.record(slot.slot, success=True)
        elif error not in {"circuit_open", "provider_unconfigured"}:
            self.breaker.record(slot.slot, success=False)
        responded_at = datetime.now(UTC)
        logger.info(
            "judge_run slot=%d provider=%s model=%s family=%s status=%s "
            "attempts=%d latency_ms=%d pack_hash=%s",
            slot.slot, slot.provider, slot.model, slot.model_family,
            "succeeded" if decision is not None else "failed", attempts,
            round((monotonic() - started) * 1000), prepared.pack_hash,
        )
        return JudgeRun(
            judge_run_id=uuid4(), claim_id=pack.claim_id, evidence_pack_id=prepared.pack_id,
            evidence_pack_hash=prepared.pack_hash, slot=slot.slot,
            provider=slot.provider, model=slot.model, model_family=slot.model_family,
            model_snapshot=provider_response.model_snapshot if provider_response else None,
            search_override_active=slot.search_override_active,
            search_guard_bypassed=slot.search_guard_bypassed,
            search_isolation_verified=False,
            prompt_version=PROMPT_VERSION, prompt_hash=prepared.prompt_hash,
            requested_at=requested_at, responded_at=responded_at,
            latency_ms=round((monotonic() - started) * 1000), attempt_count=attempts,
            outcome_status="succeeded" if decision is not None else "failed",
            response_json=response_json, decision=decision,
            input_tokens=provider_response.input_tokens if provider_response else None,
            output_tokens=provider_response.output_tokens if provider_response else None,
            provider_request_id=(provider_response.provider_request_id
                                 if provider_response else failure_request_id),
            error_category=error,
        )


class DecisionFailure(Exception):
    def __init__(self, category: str, *, retryable: bool = False) -> None:
        self.category = category
        self.retryable = retryable
        super().__init__(category)


def parse_decision(content: str, selected_ids: tuple[str, ...]) -> JudgeDecision:
    """Never repair medical content or silently discard an unsupported citation."""

    if not content.strip():
        raise DecisionFailure("empty_response", retryable=True)
    if len(content) > 65536:
        raise DecisionFailure("schema_violation", retryable=True)
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DecisionFailure("malformed_json", retryable=True) from exc
    if not isinstance(data, dict):
        raise DecisionFailure("schema_violation", retryable=True)
    if data.get("label") not in {
        "supported", "contradicted", "not_enough_evidence",
    }:
        raise DecisionFailure("unsupported_label")
    try:
        decision = JudgeDecision.model_validate_json(content)
    except ValidationError as exc:
        raise DecisionFailure("schema_violation", retryable=True) from exc
    allowed = set(selected_ids)
    cited = set(decision.cited_evidence_ids) | set(decision.opposing_evidence_ids)
    mentioned = set(re.findall(r"\bE\d+\b", decision.reasoning_summary))
    if not cited <= allowed or not mentioned <= cited:
        raise DecisionFailure("invalid_evidence_citation")
    if re.search(r"\b(?:PMID|DOI)\s*[:#]?\s*\S+", decision.reasoning_summary, re.I):
        raise DecisionFailure("invalid_evidence_citation")
    return decision
