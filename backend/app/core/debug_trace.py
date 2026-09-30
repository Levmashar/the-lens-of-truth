"""Bounded, process-local model diagnostics for development analysis runs only."""

from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from time import monotonic
from uuid import UUID

_MAX_ANALYSES = 50
_MAX_EVENTS = 80
_MAX_RESPONSE_CHARS = 3000
_TTL_SECONDS = 3600
_active_analysis: ContextVar[UUID | None] = ContextVar("debug_analysis", default=None)
_active_claim: ContextVar[UUID | None] = ContextVar("debug_claim", default=None)


@dataclass(frozen=True)
class ModelDebugEvent:
    role: str
    provider: str
    model: str
    attempt: int
    status: str
    failure_type: str | None
    http_status: int | None
    elapsed_ms: int
    response_excerpt: str | None
    analysis_id: str
    claim_id: str | None = None
    judge_run_id: str | None = None
    statement_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    validation_run_id: str | None = None
    call_id: str | None = None
    operation_kind: str | None = None
    semantic_revision_number: int = 0


_traces: OrderedDict[UUID, tuple[float, list[ModelDebugEvent]]] = OrderedDict()


@contextmanager
def trace_analysis(analysis_id: UUID, *, enabled: bool) -> Iterator[None]:
    """Scope capture to one development worker without altering normal runs."""

    token = _active_analysis.set(analysis_id if enabled else None)
    try:
        yield
    finally:
        _active_analysis.reset(token)


@contextmanager
def trace_claim(claim_id: UUID) -> Iterator[None]:
    token = _active_claim.set(claim_id)
    try:
        yield
    finally:
        _active_claim.reset(token)


def record_model_event(
    *, role: str, provider: str, model: str, attempt: int, status: str,
    failure_type: str | None, http_status: int | None, elapsed_ms: int,
    response_content: str | None = None,
    judge_run_id: str | None = None,
    statement_ids: tuple[str, ...] = (),
    evidence_ids: tuple[str, ...] = (),
    validation_run_id: str | None = None,
    call_id: str | None = None,
    operation_kind: str | None = None,
    semantic_revision_number: int = 0,
) -> int:
    analysis_id = _active_analysis.get()
    if analysis_id is None:
        return 0
    _prune()
    _, events = _traces.get(analysis_id, (monotonic() + _TTL_SECONDS, []))
    if attempt == 0:
        attempt = 1 + max(
            (event.attempt for event in events
             if event.role == role and event.model == model),
            default=0,
        )
    events.append(ModelDebugEvent(
        role=role, provider=provider, model=model, attempt=attempt, status=status,
        failure_type=failure_type, http_status=http_status, elapsed_ms=elapsed_ms,
        response_excerpt=(response_content[:_MAX_RESPONSE_CHARS]
                          if response_content is not None else None),
        analysis_id=str(analysis_id),
        claim_id=str(_active_claim.get()) if _active_claim.get() else None,
        judge_run_id=judge_run_id, statement_ids=statement_ids,
        evidence_ids=evidence_ids, validation_run_id=validation_run_id,
        call_id=call_id, operation_kind=operation_kind,
        semantic_revision_number=semantic_revision_number,
    ))
    if len(events) > _MAX_EVENTS:
        del events[:-_MAX_EVENTS]
    _traces[analysis_id] = (monotonic() + _TTL_SECONDS, events)
    _traces.move_to_end(analysis_id)
    while len(_traces) > _MAX_ANALYSES:
        _traces.popitem(last=False)
    return attempt


def model_events(analysis_id: UUID) -> list[dict[str, object]]:
    """Return an immutable snapshot; never return another analysis's output."""

    _prune()
    trace = _traces.get(analysis_id)
    return [asdict(event) for event in trace[1]] if trace else []


def _prune() -> None:
    now = monotonic()
    for analysis_id, (expires_at, _) in list(_traces.items()):
        if expires_at <= now:
            del _traces[analysis_id]
