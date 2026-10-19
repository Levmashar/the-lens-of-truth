"""Read-only presentation of saved, source-validated findings and exact quotes.

This does not generate an explanation, qualify evidence, or change a verdict.
Historical reports and their semantic hashes remain unchanged.
"""

import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.judging.models import JudgeDecisionV2, JudgeRun
from app.report.models import LensReport
from app.retrieval.models import EvidencePack
from app.validation.audit25 import audit_matches25
from app.validation.models import (
    JudgeValidationRun,
    StatementAttributionStatus,
    ValidationStatus,
)
from app.verdict.models import LensVerdict, ReasonCode, VerdictResult


class RetrievalSource(BaseModel):
    title: str
    url: str
    classification: str
    missing_qualifiers: tuple[str, ...]


class RetrievalCoverage(BaseModel):
    version: Literal["retrieval-coverage-2.0"] = "retrieval-coverage-2.0"
    state: Literal["search_incomplete", "no_eligible_sources", "related_only", "direct_candidates"]
    explanation: str
    sources: tuple[RetrievalSource, ...]


def retrieval_coverage(report: LensReport, pack: EvidencePack) -> RetrievalCoverage | None:
    """Search coverage, never a medical finding or a replacement for the verdict."""
    if pack.evidence_pack_version != "2.0":
        return None
    contexts = [
        d
        for d in pack.documents
        if d.retrieval_context and d.retrieval_context.classification != "irrelevant"
    ]
    selected_docs = {
        p.passage.document_id for p in pack.passages if p.evidence_id in pack.selected_evidence_ids
    }
    contexts.sort(
        key=lambda d: (d.document_id not in selected_docs, not bool(d.authoritative), d.document_id)
    )
    display = [d for d in contexts if d.document_id in selected_docs or d.authoritative]
    if not display:
        display = contexts[:4]
    sources = tuple(
        RetrievalSource(
            title=d.title,
            url=d.canonical_url,
            classification=d.retrieval_context.classification,
            missing_qualifiers=d.retrieval_context.missing_qualifiers,
        )
        for d in display[:8]
        if d.retrieval_context
    )
    partial_notice = (
        "Some source requests or discovered records could not be fully used. "
        if "retrieval_v2_provider_partial_failure" in pack.query_plan.warnings
        else ""
    )
    if any(r.code == ReasonCode.RETRIEVAL_TECHNICAL_FAILURE for r in report.why_this_result):
        return RetrievalCoverage(
            state="search_incomplete",
            sources=sources,
            explanation="The source search could not be completed reliably. This is a "
            "search problem, not a finding that the scientific evidence is inconclusive.",
        )
    if not contexts:
        return RetrievalCoverage(
            state="no_eligible_sources",
            sources=(),
            explanation=partial_notice
            + "The bounded search did not find usable sources for this claim. "
            "That does not establish that no research exists, or that the claim is false.",
        )
    if not any(
        d.retrieval_context and d.retrieval_context.classification == "direct" for d in contexts
    ):
        selected_contexts = [
            d.retrieval_context
            for d in contexts
            if d.document_id in selected_docs and d.retrieval_context
        ]
        missing_fields = [
            set(t.split(":", 1)[0] for t in c.missing_qualifiers) for c in selected_contexts
        ]
        common_gaps = set.intersection(*missing_fields) if missing_fields else set()
        detail = ""
        if pack.claim_snapshot.pico:
            for key, field in (
                ("exposure", "intervention_or_exposure"),
                ("outcome", "outcome"),
                ("population", "population"),
                ("comparator", "comparator"),
                ("timeframe", "timeframe"),
            ):
                value = getattr(pack.claim_snapshot.pico, field)
                if key in common_gaps and value:
                    detail = (
                        f"Search matching could not establish coverage for the {key}: “{value}”. "
                    )
                    break
        return RetrievalCoverage(
            state="related_only",
            sources=sources,
            explanation=partial_notice
            + "We found research or clinical guidance on related topics, but the "
            "search did not locate a source matching all the details in this claim. "
            + detail
            + "Related findings cannot establish or rule out the more specific claim. "
            "The reported assessment shows whether the available findings passed verification.",
        )
    return RetrievalCoverage(
        state="direct_candidates",
        sources=sources,
        explanation=partial_notice
        + "The search found sources with matching claim concepts. Search relevance "
        "alone does not establish the claim: source validation and the evidence assessment "
        "determine the result below.",
    )


class ReadingFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    text: str
    evidence_ids: tuple[str, ...]
    source_unit_ids: tuple[str, ...]


class QuoteHighlight(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source_unit_id: str
    exact_text: str
    kind: Literal["attribution_quote", "source_summary"] = "attribution_quote"


class ReportReadingGuide(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: str = "report-reading-guide-1.0"
    verdict_run_id: UUID
    report_semantic_hash: str
    findings: tuple[ReadingFinding, ...] = ()
    highlights: tuple[QuoteHighlight, ...] = ()
    retrieval: RetrievalCoverage | None = Field(
        default=None, exclude_if=lambda value: value is None
    )


_QUOTED = re.compile(
    r'"([^"\n]{25,1500})"|“([^”\n]{25,1500})”|'
    r"(?<!\w)\x27([^\n]{25,1500})\x27(?!\w)"
)
_SOURCE_SUMMARY = re.compile(
    r"^\s*(?:this|the|our)\s+(?:[a-z-]+\s+){0,6}"
    r"(?:study|trial|analysis|meta-analysis|review|results|findings|analyses)\s+"
    r"(?:(?:also|further|clearly)\s+)?"
    r"(?:shows?|showed|indicates?|indicated|suggests?|suggested|demonstrates?|"
    r"demonstrated|concludes?|concluded|finds?|found)\b",
    re.I,
)


def source_summary_sentences(text: str) -> tuple[str, ...]:
    """Literal, self-declared source summaries; no claim-word or direction matching."""
    return tuple(
        sentence
        for match in re.finditer(
            r"[^.!?\n]+(?:[.!?](?=\s|$)|$)",
            text,
        )
        if len(sentence := match.group().strip()) <= 1500
        and len(sentence.split()) >= 8
        and _SOURCE_SUMMARY.match(sentence)
    )[:2]


def build_reading_guide(
    report: LensReport,
    verdict: VerdictResult,
    pack: EvidencePack,
    judges: tuple[JudgeRun, ...],
    validations: tuple[JudgeValidationRun, ...],
    *,
    risk_class: str,
) -> ReportReadingGuide:
    """Project only qualified, exactly reconstructed V2.5 source attributions."""
    empty = ReportReadingGuide(
        verdict_run_id=report.verdict_run_id,
        report_semantic_hash=report.semantic_hash,
        retrieval=retrieval_coverage(report, pack),
    )
    if report.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY:
        return empty
    if (
        report.verdict != verdict.verdict
        or report.provenance.verdict_semantic_hash != verdict.semantic_hash
        or report.provenance.evidence_pack_hash != pack.snapshot_hash
        or report.provenance.evidence_pack_id != verdict.evidence_pack_id
    ):
        raise ValueError("Reading guide provenance mismatch")
    qualified = {q.judge_run_id for q in verdict.judge_qualifications if q.qualified}
    by_judge = {j.judge_run_id: j for j in judges}
    visible = {e.source_unit_id: e for c in report.key_evidence for e in c.excerpts}
    order = {unit: index for index, unit in enumerate(visible)}
    candidates: list[ReadingFinding] = []
    highlights: dict[tuple[str, str], QuoteHighlight] = {}
    for validation in sorted(
        validations,
        key=lambda v: by_judge[v.judge_run_id].slot if v.judge_run_id in by_judge else 99,
    ):
        judge = by_judge.get(validation.judge_run_id)
        if (
            judge is None
            or judge.judge_run_id not in qualified
            or not isinstance(judge.decision, JudgeDecisionV2)
            or judge.decision.schema_version != "2.5"
            or validation.status != ValidationStatus.VALIDATED
            or not audit_matches25(judge, validation, pack, risk_class)
        ):
            continue
        attributions = {a.statement_id: a for a in validation.result.statement_attributions}
        for statement in judge.decision.statements:
            attribution = attributions.get(statement.statement_id)
            units = tuple(u for u in statement.source_unit_ids if u in visible)
            if (
                attribution is None
                or attribution.status != StatementAttributionStatus.SUPPORTED_BY_SOURCES
                or not units
                or len(units) != len(statement.source_unit_ids)
                or any(visible[u].evidence_id not in attribution.evidence_ids for u in units)
            ):
                continue
            text = (statement.qualitative_finding or statement.text).strip()
            if text and len(text) <= 1800:
                candidates.append(
                    ReadingFinding(
                        text=text,
                        source_unit_ids=units,
                        evidence_ids=tuple(dict.fromkeys(visible[u].evidence_id for u in units)),
                    )
                )
            # Only literal quoted source text from the validated attribution is
            # highlighted. Never infer a proof sentence by keyword similarity.
            for match in _QUOTED.finditer(attribution.reason):
                quote = next(group for group in match.groups() if group is not None)
                if len(quote.split()) < 5:
                    continue
                for unit in units:
                    if quote in visible[unit].exact_text:
                        highlights[(unit, quote)] = QuoteHighlight(
                            source_unit_id=unit, exact_text=quote
                        )
    # When attribution prose has no literal quote, show only a sentence the
    # source itself explicitly identifies as its findings/conclusion. This is a
    # source summary, not a newly inferred decisive proof or claim direction.
    highlighted_units = {unit for unit, _ in highlights}
    validated_units = {unit for finding in candidates for unit in finding.source_unit_ids}
    for unit in sorted(validated_units, key=order.__getitem__):
        if unit not in highlighted_units:
            for sentence in source_summary_sentences(visible[unit].exact_text):
                highlights[(unit, sentence)] = QuoteHighlight(
                    source_unit_id=unit, exact_text=sentence, kind="source_summary"
                )
    # One finding per exact unit set; preserve source-card order and first slot.
    chosen: list[ReadingFinding] = []
    seen: set[tuple[str, ...]] = set()
    for finding in sorted(candidates, key=lambda f: min(order[u] for u in f.source_unit_ids)):
        key = tuple(sorted(finding.source_unit_ids))
        if key not in seen:
            chosen.append(finding)
            seen.add(key)
        if len(chosen) == 3:
            break
    return empty.model_copy(
        update={"findings": tuple(chosen), "highlights": tuple(highlights.values())[:24]}
    )
