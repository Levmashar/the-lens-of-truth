"""Concurrent independent judge calls over one validated frozen evidence view."""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from time import monotonic
from typing import Literal
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.adapters.judge import JudgeProvider, ProviderFailure
from app.core.diagnostics import sanitize_diagnostic
from app.judging.citation_errors import (
    CitationReferenceError,
    SourceUnitReferenceError,
    citation_error_details,
)
from app.judging.compact23 import VERSION as AXES_COMPACT_VERSION
from app.judging.compact24 import VERSION as STRUCTURED_COMPACT_VERSION
from app.judging.compact25 import VERSION as POSITION_COMPACT_VERSION
from app.judging.config import is_search_enabled_model, judge_request_options
from app.judging.models import (
    AnyJudgeDecision,
    DisagreementSummary,
    JudgeDecision,
    JudgeDecisionV2,
    JudgeRun,
    JudgeSlot,
    JudgeStatement,
    decision_evidence_ids,
    describe_disagreement,
)
from app.judging.prompt import (
    PreparedJudgeInput,
    input_snapshot_hash,
    prepare_compact_v2,
    prepare_judge_input,
)
from app.judging.source_quantities import QuantityReferenceError
from app.judging.source_units import materialize_content, normalize_parent_unit_ids
from app.retrieval.models import EvidencePack
from app.validation.models import JudgeValidationRun, ValidationStatus

logger = logging.getLogger(__name__)
CITATION_PREFLIGHT_VERSION = "evidence-citation-preflight-1.1"


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
    compact_development: bool = False
    axes_development: bool = False
    # Explicit recorded-version replay only; normal development uses V2.5.
    axes_contract: Literal["2.3", "2.4", "2.5"] = "2.5"

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
        if self.axes_development:
            if app_env not in {"development", "test"}:
                raise ValueError("Axes judge contract is development/test only")
            from app.judging.compact24 import prepare_compact24

            if self.axes_contract == "2.3":
                from app.judging.compact23 import prepare_compact23

                prepared = prepare_compact23(pack_id, pack)
            elif self.axes_contract == "2.5":
                from app.judging.compact25 import prepare_compact25

                prepared = prepare_compact25(pack_id, pack)
            else:
                prepared = prepare_compact24(pack_id, pack)
        elif self.compact_development:
            if app_env not in {"development", "test"}:
                raise ValueError("Compact judge prompt is development/test only")
            prepared = prepare_compact_v2(prepared)
        semaphore = asyncio.Semaphore(self.concurrency_limit)
        # Some OpenAI-compatible gateways queue large concurrent requests per
        # endpoint. Keep independent gateways parallel, but avoid consuming a
        # slot's entire deadline while another slot occupies the same gateway.
        endpoint_semaphores = {
            slot.base_url.rstrip("/"): asyncio.Semaphore(1)
            for slot in slots if slot.provider in {"openai_compatible", "paratera"}
        }

        async def one(slot: JudgeSlot) -> JudgeRun:
            async with semaphore:
                endpoint = endpoint_semaphores.get(slot.base_url.rstrip("/"))
                if slot.provider in {"openai_compatible", "paratera"} and endpoint is not None:
                    async with endpoint:
                        return await self._run_slot(pack, prepared, slot)
                return await self._run_slot(pack, prepared, slot)

        runs = tuple(await asyncio.gather(*(one(slot) for slot in slots)))
        return runs, describe_disagreement(runs)

    async def _run_slot(
        self, pack: EvidencePack, prepared: PreparedJudgeInput, slot: JudgeSlot,
        *, max_attempts: int = 2, revision_of: UUID | None = None,
    ) -> JudgeRun:
        requested_at = datetime.now(UTC)
        run_id = uuid4()
        prepared_for_slot = replace(
            prepared, judge_run_id=str(run_id),
            semantic_revision_number=1 if revision_of else 0,
        )
        started = monotonic()
        attempts = 0
        decision: AnyJudgeDecision | None = None
        schema_version_inferred = False
        source_unit_id_normalizations: list[dict[str, str]] = []
        response_json: dict[str, object] | None = None
        rejected_responses: list[dict[str, object]] = []
        attempt_failures: list[dict[str, object]] = []
        error: str | None = None
        failure_request_id: str | None = None
        provider_response = None
        request_slot = slot
        provider = self.providers.get(slot.provider)
        if not self.breaker.available(slot.slot):
            error = "circuit_open"
        elif provider is None:
            error = "provider_unconfigured"
        else:
            try:
                async with asyncio.timeout(self.total_timeout_seconds):
                    for attempts in range(1, max_attempts + 1):
                        provider_response = None
                        failure_request_id = None
                        decision = None
                        schema_version_inferred = False
                        source_unit_id_normalizations = []
                        response_json = None
                        try:
                            async with asyncio.timeout(self.attempt_timeout_seconds):
                                provider_response = await provider.evaluate(
                                    request_slot, prepared_for_slot,
                                )
                                parsed_content = provider_response.content
                                if (self.axes_development and
                                        prepared.prompt_version in {
                                            AXES_COMPACT_VERSION, STRUCTURED_COMPACT_VERSION,
                                            POSITION_COMPACT_VERSION}):
                                    parsed_content, source_unit_id_normalizations = (
                                        normalize_parent_unit_ids(
                                            parsed_content, prepared.input_snapshot_json,
                                        )
                                    )
                                decision, schema_version_inferred = parse_provider_decision(
                                    parsed_content, prepared.selected_ids,
                                    allow_visible_siblings=(self.axes_development
                                                            and prepared.prompt_version in {
                                                                AXES_COMPACT_VERSION,
                                                                STRUCTURED_COMPACT_VERSION,
                                                                POSITION_COMPACT_VERSION}),
                                    snapshot=prepared.input_snapshot_json
                                    if prepared.input_snapshot_version in
                                    {"judge-input-2.1", "judge-input-2.2", "judge-input-2.3",
                                     "judge-input-2.4", "judge-input-2.5"}
                                    else None,
                                )
                                if not isinstance(decision, JudgeDecisionV2):
                                    raise DecisionFailure("legacy_schema_not_accepted")
                                if (prepared.prompt_version ==
                                        "judge-2.11-compact-development-2026-10-02"
                                        and "RESPONSE CONTRACT: Qualitative claim." in
                                        prepared.user_prompt):
                                    prose = " ".join([s.text for s in decision.statements] +
                                                     [decision.conclusion.justification])
                                    if re.search(r"\d", re.sub(r"\bS[1-8]\b", "", prose)):
                                        raise DecisionFailure("optional_numeric_content",
                                                              retryable=True)
                            response_json = decision.model_dump(mode="json")
                            if prepared.input_snapshot_version == "judge-input-2.5":
                                response_json["citation_preflight_version"] = (
                                    CITATION_PREFLIGHT_VERSION
                                )
                            if prepared.input_snapshot_version in {"judge-input-2.3",
                                                                   "judge-input-2.4",
                                                                   "judge-input-2.5"}:
                                response_json["raw_model_content"] = sanitize_diagnostic(
                                    provider_response.content, (slot.api_key or "",),
                                )
                                if source_unit_id_normalizations:
                                    response_json["source_unit_id_normalizations"] = (
                                        source_unit_id_normalizations
                                    )
                            error = None
                            break
                        except TimeoutError:
                            error, retryable = "timeout", True
                        except ProviderFailure as exc:
                            error, retryable = exc.category, exc.retryable
                            failure_request_id = exc.provider_request_id
                            if error == "response_format_unsupported":
                                request_slot = slot.model_copy(
                                    update={"request_json_schema": False},
                                )
                        except DecisionFailure as exc:
                            error, retryable = exc.category, exc.retryable
                            rejected_responses.append({
                                "attempt": attempts, "category": exc.category,
                                "schema_errors": exc.schema_errors,
                                "citation_errors": sanitize_diagnostic(
                                    exc.citation_errors, (slot.api_key or "",),
                                ),
                                "exception_type": exc.exception_type,
                                "exception_message": sanitize_diagnostic(
                                    exc.exception_message, (slot.api_key or "",),
                                ),
                                "citation_preflight_version": CITATION_PREFLIGHT_VERSION,
                                "content": sanitize_diagnostic(
                                    provider_response.content, (slot.api_key or "",),
                                )[:32768]
                                if provider_response else None,
                                "content_truncated": bool(provider_response and
                                                          len(provider_response.content) > 32768),
                            })
                        if error is not None:
                            attempt_failures.append({"attempt": attempts, "category": error,
                                                     "retryable": retryable})
                        logger.warning(
                            "judge_attempt slot=%d provider=%s model=%s family=%s "
                            "attempt=%d failure=%s elapsed_ms=%d retry=%s",
                            slot.slot, slot.provider, slot.model, slot.model_family,
                            attempts, error, round((monotonic() - started) * 1000),
                            attempts < max_attempts and retryable,
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
        if error is not None:
            decision = None
            response_json = ({"rejected_responses": rejected_responses}
                             if rejected_responses else None)
            schema_version_inferred = False
        if (prepared.input_snapshot_version in {"judge-input-2.3", "judge-input-2.4",
                                               "judge-input-2.5"} and attempt_failures):
            response_json = {**(response_json or {}), "attempt_failures": attempt_failures}
        if slot.thinking_enabled is not None:
            response_json = {
                **(response_json or {}), "generation_options": judge_request_options(slot),
            }
        if error is None:
            self.breaker.record(slot.slot, success=True)
            if isinstance(decision, JudgeDecisionV2) and len(decision.statements) > 3:
                logger.info("judge_expanded_findings slot=%d count=%d "
                            "reason=additional_context_or_conflict_requested "
                            "justification_recorded=true", slot.slot, len(decision.statements))
        elif error not in {"circuit_open", "provider_unconfigured"}:
            self.breaker.record(slot.slot, success=False)
        responded_at = datetime.now(UTC)
        logger.info(
            "judge_run slot=%d provider=%s model=%s family=%s status=%s "
            "attempts=%d latency_ms=%d pack_hash=%s schema_version_inferred=%s",
            slot.slot, slot.provider, slot.model, slot.model_family,
            "succeeded" if error is None and decision is not None else "failed", attempts,
            round((monotonic() - started) * 1000), prepared.pack_hash,
            schema_version_inferred,
        )
        return JudgeRun(
            judge_run_id=run_id, claim_id=pack.claim_id, evidence_pack_id=prepared.pack_id,
            evidence_pack_hash=prepared.pack_hash, slot=slot.slot,
            provider=slot.provider, model=slot.model, model_family=slot.model_family,
            model_snapshot=provider_response.model_snapshot if provider_response else None,
            schema_version_inferred=schema_version_inferred,
            search_override_active=slot.search_override_active,
            search_guard_bypassed=slot.search_guard_bypassed,
            search_isolation_verified=False,
            prompt_version=prepared.prompt_version, prompt_hash=prepared.prompt_hash,
            input_snapshot_version=prepared.input_snapshot_version,
            input_snapshot_hash=prepared.input_snapshot_hash,
            input_snapshot_json=prepared.input_snapshot_json,
            revision_of_judge_run_id=revision_of,
            semantic_revision_number=1 if revision_of else 0,
            requested_at=requested_at, responded_at=responded_at,
            latency_ms=round((monotonic() - started) * 1000), attempt_count=attempts,
            outcome_status="succeeded" if error is None and decision is not None else "failed",
            response_json=response_json, decision=decision,
            input_tokens=provider_response.input_tokens if provider_response else None,
            output_tokens=provider_response.output_tokens if provider_response else None,
            provider_request_id=(provider_response.provider_request_id
                                 if provider_response else failure_request_id),
            error_category=error,
        )

    async def revise(
        self, original: JudgeRun, validation: JudgeValidationRun,
        pack: EvidencePack, slot: JudgeSlot,
    ) -> JudgeRun:
        """At most one same-evidence semantic correction; no second schema retry."""

        if (original.semantic_revision_number != 0
                or original.revision_of_judge_run_id is not None
                or not isinstance(original.decision, JudgeDecisionV2)
                or validation.judge_run_id != original.judge_run_id
                or (validation.status not in {ValidationStatus.INVALID,
                                               ValidationStatus.PARTIALLY_VALIDATED}
                    and not (validation.status == ValidationStatus.UNABLE_TO_VALIDATE
                             and any(i.issue_code.value == "NUMERIC_UNCERTAIN"
                                     for i in validation.result.targeted_issues)))
                or original.slot != slot.slot or original.model != slot.model
                or original.evidence_pack_hash != pack.snapshot_hash):
            raise ValueError("Judge run is not eligible for semantic revision")
        base = prepare_judge_input(original.evidence_pack_id, pack,
                                   version=original.input_snapshot_version or "judge-input-2.0")
        if (original.input_snapshot_hash != base.input_snapshot_hash
                or original.input_snapshot_json is None
                or input_snapshot_hash(original.input_snapshot_json)
                != base.input_snapshot_hash):
            raise ValueError("Revision evidence differs from the original frozen input")
        issues = [issue.model_dump(mode="json")
                  for issue in validation.result.targeted_issues]
        if not issues:
            raise ValueError("No target-specific semantic issue to revise")
        system = base.system_prompt + (
            "\nONE SEMANTIC REVISION ONLY. Recheck your own statements and source units, "
            "numeric attribution, and conclusion. Retain uncertainty if the "
            "frozen sources cannot justify a decisive label. Do not use outside "
            "sources or another judge's response. Return the same content contract. "
            "An optional unresolved numerical detail may be omitted in a fresh statement "
            "only if the remaining conclusion is still established at the unchanged "
            "claim magnitude and scope. Never omit an essential quantity.\n"
        )
        user = base.user_prompt + "\nYOUR PREVIOUS DECISION AND TARGETED ISSUES:\n" + json.dumps({
            "your_decision": original.decision.model_dump(mode="json"),
            "issues": issues,
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        prompt_hash = hashlib.sha256(json.dumps({
            "version": "judge-revision-2.0", "system": system, "user": user,
        }, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        prepared = replace(base, system_prompt=system, user_prompt=user,
                           prompt_hash=prompt_hash)
        return await self._run_slot(
            pack, prepared, slot, max_attempts=1,
            revision_of=original.judge_run_id,
        )


class DecisionFailure(Exception):
    def __init__(self, category: str, *, retryable: bool = False,
                 schema_errors: tuple[dict[str, object], ...] = (),
                 citation_errors: tuple[dict[str, object], ...] = (),
                 exception_type: str | None = None,
                 exception_message: str | None = None) -> None:
        self.category = category
        self.retryable = retryable
        self.schema_errors = schema_errors
        self.citation_errors = citation_errors
        self.exception_type = exception_type
        self.exception_message = exception_message or category
        super().__init__(category)


def parse_provider_decision(
    content: str, selected_ids: tuple[str, ...],
    *, snapshot: dict[str, object] | None = None,
    allow_visible_siblings: bool = False,
) -> tuple[AnyJudgeDecision, bool]:
    """Infer only the fixed protocol version; never repair a medical judgment.

    The raw model completion is retained in the development trace. The inferred
    version is audited in the append-only judge row and is ineligible for
    production qualification.
    """

    if snapshot is not None:
        if not content.strip():
            raise DecisionFailure("empty_response", retryable=True)
        if len(content) > 65536:
            raise DecisionFailure("schema_violation", retryable=True)
        try:
            json.loads(content)
        except json.JSONDecodeError as exc:
            raise DecisionFailure("malformed_json", retryable=True) from exc
        try:
            decision = materialize_content(content, snapshot)
            allowed_ids = selected_ids
            if allow_visible_siblings:
                raw_visible = snapshot.get("judge_visible_evidence_ids")
                if (snapshot.get("validation_contract") not in {"judge-validation-2.3",
                                                               "judge-validation-2.4",
                                                               "judge-validation-2.5"}
                        or not isinstance(raw_visible, list)
                        or not all(isinstance(identifier, str) for identifier in raw_visible)
                        or not set(selected_ids) <= set(raw_visible)):
                    raise ValueError("Invalid frozen judge-visible evidence set")
                allowed_ids = tuple(raw_visible)
            _validate_decision_citations(decision, allowed_ids, snapshot=snapshot)
            return decision, False
        except QuantityReferenceError as exc:
            raise _reference_failure("invalid_source_quantity", exc) from exc
        except SourceUnitReferenceError as exc:
            raise _reference_failure("invalid_source_unit", exc) from exc
        except CitationReferenceError as exc:
            raise _reference_failure("schema_violation", exc) from exc
        except KeyError as exc:
            raise _reference_failure("invalid_source_unit", exc) from exc
        except ValidationError as exc:
            raise DecisionFailure("schema_violation", retryable=True,
                                  schema_errors=_schema_errors(exc),
                                  exception_type=type(exc).__name__,
                                  exception_message="Judge schema invalid; see field errors."
                                  ) from exc
        except ValueError as exc:
            raise _reference_failure("schema_violation", exc) from exc
    try:
        return parse_decision(content, selected_ids), False
    except DecisionFailure as exc:
        if exc.category != "schema_violation":
            raise
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            raise exc from None
        if not isinstance(data, dict) or "schema_version" in data:
            raise exc
        version = "2.0" if "statements" in data else "1.0"
        repaired = {**data, "schema_version": version}
        return parse_decision(json.dumps(repaired), selected_ids), True


def parse_decision(content: str, selected_ids: tuple[str, ...]) -> AnyJudgeDecision:
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
        decision = (JudgeDecisionV2.model_validate_json(content)
                    if data.get("schema_version") in {"2.0", "2.1", "2.2", "2.3", "2.4", "2.5"}
                    else JudgeDecision.model_validate_json(content))
    except ValidationError as exc:
        raise DecisionFailure("schema_violation", retryable=True,
                              schema_errors=_schema_errors(exc)) from exc
    _validate_decision_citations(decision, selected_ids)
    return decision


def _reference_failure(category: str, exc: BaseException) -> DecisionFailure:
    detail = citation_error_details(exc)
    return DecisionFailure(
        category, retryable=True, citation_errors=(detail,) if detail else (),
        exception_type=type(exc).__name__, exception_message=str(exc),
    )


def _validate_decision_citations(
    decision: AnyJudgeDecision, selected_ids: tuple[str, ...], *,
    snapshot: dict[str, object] | None = None,
) -> None:
    if (snapshot is not None and snapshot.get("validation_contract") == "judge-validation-2.5"
            and isinstance(decision, JudgeDecisionV2) and decision.schema_version == "2.5"):
        _validate_source_bound_prose(decision, selected_ids)
        return
    # Historical/free-text contracts keep their original acceptance rules.
    allowed = set(selected_ids)
    cited = set(decision_evidence_ids(decision))
    prose = (" ".join(statement.text for statement in decision.statements)
             + " " + decision.conclusion.justification
             if isinstance(decision, JudgeDecisionV2) else decision.reasoning_summary)
    mentioned = set(re.findall(r"\bE\d+\b", prose))
    if not cited <= allowed or not mentioned <= cited:
        raise DecisionFailure("invalid_evidence_citation", retryable=True)
    if re.search(r"\b(?:PMID|DOI)\s*[:#]?\s*\S+", prose, re.I):
        raise DecisionFailure("invalid_evidence_citation", retryable=True)


_PROSE_REFERENCE = re.compile(r"\bE\d+(?:\.U\d+(?:\.Q\d+)?)?\b")
_CITATION_PREFIX = re.compile(
    r"\b(?:evidence|source|study|passage|reference|citation|document|unit|quantity|see|cites?|"
    r"according to|reported in|reported by|shown in)\s*(?:id\s*)?[:#]?\s*$", re.I,
)
_CITATION_SUFFIX = re.compile(
    r"^(?:['’]s\s+(?:results?|findings?|conclusions?|abstract|study)\b|"
    r"\s+(?:reports?|states?|shows?|found|concludes?|supports?|contradicts?|indicates?|"
    r"demonstrated|establishes?|results?|findings?)\b)", re.I,
)


def _explicit_prose_reference(text: str, match: re.Match[str]) -> bool:
    if "." in match.group():
        return True
    before, after = text[:match.start()], text[match.end():]
    in_brackets = before.rfind("[") > before.rfind("]") and "]" in after
    from_source = re.search(r"(?:^|[.!?]\s+)from\s+$", before, re.I)
    prefix = _CITATION_PREFIX.search(before)
    # "To study E2 concentrations" uses study as a verb. "According to study
    # E2" is a citation, so the surrounding grammar must stay distinct.
    verb_study = re.search(r"\b(?:to|we|they|can|could|will|would|should|may)\s+study\s*$",
                           before, re.I) and not re.search(r"according\s+to\s+study\s*$",
                                                          before, re.I)
    if verb_study and prefix and prefix.group().strip().casefold() == "study":
        prefix = None
    return bool(in_brackets or from_source or prefix
                or _CITATION_SUFFIX.search(after))


def _validate_source_bound_prose(decision: JudgeDecisionV2, allowed_ids: tuple[str, ...]) -> None:
    """Disambiguate source vocabulary without inventing or aliasing a citation.

    Bare E-number terms can be scientific names when present in the same finding's
    actual frozen quotes. Explicit citation syntax never receives this exemption.
    Units/quantities remain exact local references; conclusions inherit only their
    declared statement dependencies. No disease-specific vocabulary is used.
    """
    allowed = set(allowed_ids)
    for statement in decision.statements:
        for ref in statement.evidence_refs:
            if ref.evidence_id not in allowed:
                _prose_failure(statement.statement_id, "evidence_refs.evidence_id",
                               ref.evidence_id, allowed_ids,
                               "Evidence is outside the judge-visible set.")

    def check(text: str, field_name: str, statement_id: str | None,
              statements: tuple[JudgeStatement, ...]) -> None:
        evidence = tuple(dict.fromkeys(ref.evidence_id for s in statements
                                      for ref in s.evidence_refs))
        units = tuple(dict.fromkeys(u for s in statements for u in s.source_unit_ids))
        quantities = tuple(dict.fromkeys(q for s in statements
                                        for q in s.source_quantity_ids or ()))
        vocabulary = {m.group() for s in statements for ref in s.evidence_refs
                      for m in _PROSE_REFERENCE.finditer(ref.quote) if "." not in m.group()}
        for match in _PROSE_REFERENCE.finditer(text):
            identifier = match.group()
            if (identifier in vocabulary and not _explicit_prose_reference(text, match)):
                continue
            expected = (quantities if ".Q" in identifier else units
                        if ".U" in identifier else evidence)
            if identifier not in expected:
                _prose_failure(statement_id, field_name, identifier, expected,
                               "Prose cites a reference not owned by this finding or conclusion.")
        external = re.search(r"\b(?:PMID|DOI)\s*[:#]?\s*\S+", text, re.I)
        if external:
            _prose_failure(statement_id, field_name, external.group()[:256], evidence,
                           "Raw publication identifiers are not accepted as judge citations.")

    for statement in decision.statements:
        check(statement.text, "text", statement.statement_id, (statement,))
        check(statement.qualitative_finding or "", "qualitative_finding", statement.statement_id,
              (statement,))
    dependencies = tuple(s for s in decision.statements
                         if s.statement_id in decision.conclusion.based_on_statement_ids)
    check(decision.conclusion.justification, "conclusion.justification", None, dependencies)
    check(decision.conclusion.qualitative_justification or "",
          "conclusion.qualitative_justification", None, dependencies)


def _prose_failure(statement_id: str | None, field_name: str, identifier: str,
                   allowed_ids: tuple[str, ...], message: str) -> None:
    cause = CitationReferenceError(
        message, statement_id=statement_id, reference_field=field_name,
        offending_id=identifier, expected_allowed_ids=allowed_ids,
        source_unit_id=identifier.split(".Q")[0] if ".U" in identifier else None,
        evidence_id=identifier.split(".")[0] if identifier.startswith("E") else None,
    )
    raise _reference_failure("invalid_evidence_citation", cause) from cause


def _schema_errors(exc: ValidationError) -> tuple[dict[str, object], ...]:
    """Field paths/types only; do not persist error inputs, prompts or provider internals."""
    return tuple({"location": error["loc"], "type": error["type"]}
                 for error in exc.errors(include_input=False, include_context=False,
                                         include_url=False)[:20])
