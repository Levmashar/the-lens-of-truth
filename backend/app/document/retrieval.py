"""One source investigation and frozen citation namespace for each document group."""

import asyncio
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from time import monotonic
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.adapters.authoritative import AuthoritativeAdapter
from app.adapters.claim_extractor import ExtractedClaimCandidate, PicoCandidate
from app.adapters.crossref import CrossrefAdapter
from app.adapters.discovery import DiscoveryLead, ScholarlyDiscovery
from app.adapters.official_web import OfficialWebDiscovery
from app.adapters.pmc import PmcFullText, PmcFullTextAdapter
from app.adapters.pubmed import PubMedAdapter
from app.adapters.source_metrics import source_http_metrics
from app.document.models import DocumentAssertion, DocumentGroup, DocumentPlan
from app.document.study_identity import metadata_clues, version_fingerprints
from app.judging.source_quantities import derive_catalog
from app.judging.source_units import SourceUnit
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import UnconfiguredMeshProvider
from app.pipeline.completeness import NormalizationQuality, assess_completeness
from app.pipeline.pico import normalization_status, normalize_pico
from app.pipeline.readiness import ready_for_evidence
from app.retrieval.adaptive import discovery_terms, plan_adaptive_queries, scholarly_query
from app.retrieval.errors import RetrievalError
from app.retrieval.evidence_pack import (
    build_evidence_pack,
    canonical_pack_bytes,
    deduplicate_documents,
)
from app.retrieval.integrity import merge_integrity, unavailable_crossref
from app.retrieval.models import (
    ClaimSnapshot,
    CrossrefEnrichment,
    EvidencePack,
    EvidencePassage,
    PubMedDocument,
    QueryExecution,
    QueryPlan,
    RankedPassage,
    RetrievalQuery,
)
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.retrieval.service import _enrich_dois
from app.retrieval.study_quality import annotate_study_quality

VERSION: Literal["document-evidence-1.1"] = "document-evidence-1.1"
_MAX_QUERIES = 12
_MAX_PMIDS = 50
_MAX_SELECTED = 24
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_COHORT = re.compile(
    r"\b(?:[A-Z][\w’'-]*\s+){1,4}(?:Biobank|Cohort|Study|Trial|Registry|Consortium)\b"
)
_STOP = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "and",
        "for",
        "in",
        "to",
        "from",
        "on",
        "with",
        "that",
        "this",
        "study",
        "analysis",
        "found",
        "showed",
        "risk",
        "risks",
        "higher",
        "increased",
        "rates",
        "use",
        "users",
        "people",
        "participants",
        "after",
        "even",
        "up",
        "plus",
        "its",
        "it",
    }
)


class SourceMatchCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    document_id: str
    pmid: str
    title: str
    canonical_url: str
    score: float = Field(ge=0, le=1)
    matching_evidence: tuple[str, ...]
    discrepancies: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()
    identity_established: bool = False


class GroupSourceMatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    status: Literal["identified", "uncertain", "not_found", "not_applicable"]
    matched_document_ids: tuple[str, ...] = ()
    candidates: tuple[SourceMatchCandidate, ...] = ()
    reason: str
    discrepancies: tuple[str, ...] = ()


class GroupEvidenceSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    version: Literal[
        "document-evidence-1.0",
        "document-evidence-1.1",
        "document-evidence-2.0",
    ] = VERSION
    group_id: str
    document_sha256: str
    pack: EvidencePack
    claim_snapshots: dict[str, ClaimSnapshot]
    normalization_status: dict[str, str]
    normalization_quality: dict[str, NormalizationQuality]
    normalization_ready: dict[str, bool]
    per_assertion_evidence_ids: dict[str, tuple[str, ...]]
    source_match: GroupSourceMatch
    source_units: tuple[SourceUnit, ...]
    source_quantity_catalog: dict[str, object]
    query_executions: tuple[QueryExecution, ...] = ()
    candidate_pmids: tuple[str, ...] = ()
    unfetched_candidate_pmids: tuple[str, ...] = ()
    retrieved_passages: tuple[EvidencePassage, ...] = ()
    fulltext_sources: tuple[PmcFullText, ...] = ()
    source_fetches: dict[str, int]
    source_http_requests: dict[str, int] = Field(default_factory=dict)
    metrics: dict[str, float | int]
    limitations: tuple[str, ...] = ()
    discovery_audit: dict[str, object] | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    snapshot_hash: str

    @model_validator(mode="after")
    def exact_shared_catalog(self) -> "GroupEvidenceSnapshot":
        selected = set(self.pack.selected_evidence_ids)
        if set(self.claim_snapshots) != set(self.per_assertion_evidence_ids):
            raise ValueError("Group assertion coverage does not match claim snapshots")
        if any(
            set(values) != set(self.claim_snapshots)
            for values in (
                self.normalization_status,
                self.normalization_quality,
                self.normalization_ready,
            )
        ):
            raise ValueError("Group normalization audit must cover exactly its assertions")
        if any(not set(ids) <= selected for ids in self.per_assertion_evidence_ids.values()):
            raise ValueError("Assertion cites evidence outside the frozen group")
        passages = {p.evidence_id: p.passage for p in self.pack.passages}
        documents = {d.document_id: d for d in self.pack.documents}
        if {u.evidence_id for u in self.source_units} != selected:
            raise ValueError("Group units must cover exactly the shared selected evidence")
        if len({u.unit_id for u in self.source_units}) != len(self.source_units):
            raise ValueError("Duplicate shared unit")
        for unit in self.source_units:
            passage = passages[unit.evidence_id]
            if (
                unit.unit_id != f"{unit.evidence_id}.U1"
                or unit.text != passage.text
                or unit.document_id != passage.document_id
                or unit.passage_sha256 != passage.content_sha256
                or unit.document_sha256 != documents[passage.document_id].content_sha256
            ):
                raise ValueError("Shared unit ownership differs from frozen group evidence")
        raw_units = [u.model_dump(mode="json") for u in self.source_units]
        if derive_catalog(raw_units) != self.source_quantity_catalog:
            raise ValueError("Shared quantity catalog differs from frozen source units")
        pack_digest = hashlib.sha256(
            canonical_pack_bytes(
                self.pack.claim_snapshot,
                self.pack.query_plan,
                self.pack.documents,
                self.pack.passages,
                self.pack.selected_evidence_ids,
                pack_version=self.pack.evidence_pack_version,
            )
        ).hexdigest()
        if self.pack.snapshot_hash != pack_digest:
            raise ValueError("Shared Evidence Pack hash mismatch")
        if _snapshot_digest(self.model_dump(mode="json", exclude={"snapshot_hash"})) != (
            self.snapshot_hash
        ):
            raise ValueError("Group evidence snapshot hash mismatch")
        return self


def _snapshot_digest(data: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            data,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


class DocumentSourceCache:
    """Per-analysis raw public-source reuse; never cache assessments or verdicts."""

    def __init__(self) -> None:
        self.documents: dict[str, PubMedDocument] = {}
        self.crossref: dict[str, CrossrefEnrichment] = {}
        self.fulltext: dict[str, PmcFullText] = {}
        self.authoritative: dict[str, PubMedDocument] = {}


def _words(text: str) -> set[str]:
    return {
        word.casefold()
        for word in _WORD.findall(text)
        if len(word) > 2 and word.casefold() not in _STOP
    }


def _phrase(text: str) -> str:
    return " ".join(text.split()).strip('"“”')


def _query_phrase(text: str) -> str:
    # Only lexical words can enter the server-owned query grammar.
    return '"' + " ".join(_WORD.findall(text)) + '"[Title/Abstract]'


def _study_names(group: DocumentGroup) -> tuple[str, ...]:
    values = [match.group() for span in group.study_clues for match in _COHORT.finditer(span.text)]
    values += [
        match.group(1)
        for span in group.study_clues
        for match in re.finditer(r'["“]([^"”]{12,180})["”]', span.text)
    ]
    return tuple(
        dict.fromkeys(re.sub(r"^(?:The|A|An)\s+", "", _phrase(value)) for value in values)
    )[:4]


def document_claim_snapshots(
    analysis_id: UUID,
    plan: DocumentPlan,
    group: DocumentGroup,
    linker: MedicalEntityLinker | None = None,
) -> dict[str, ClaimSnapshot]:
    """Use existing PICO grounding; explicit context is source text, not inferred truth."""
    snapshots = {}
    for aid in group.assertion_ids:
        assertion = plan.assertion(aid)
        pico = assertion.pico
        # Normal clinical assertions remain grounded by the existing normalizer.
        # Reported-study/method/sample details use full-document context and are
        # not required to impersonate a clinical exposure-outcome proposition.
        if assertion.kind in {"general_medical_assertion", "interpretation"}:
            span = assertion.spans[0]
            candidate = ExtractedClaimCandidate(
                raw_span=span.text,
                span_start=span.start,
                span_end=span.end,
                claim_type=pico.claim_type,
                pico=PicoCandidate(
                    **{
                        name: getattr(pico, name)
                        for name in (
                            "population",
                            "intervention_or_exposure",
                            "comparator",
                            "outcome",
                            "timeframe",
                        )
                    }
                ),
            )
            pico = normalize_pico(candidate, source_text=plan.original_text)
            targets = [
                link.target
                for link in plan.context_links
                if link.link_id in assertion.context_link_ids
                and link.resolved
                and link.relationship == "shared_exposure"
                and link.target is not None
            ]
            # Exact, ordered document links must survive atomic re-normalization.
            updates = {
                name: getattr(assertion.pico, name)
                for name in (
                    "intervention_or_exposure",
                    "outcome",
                    "population",
                    "comparator",
                    "timeframe",
                )
                if getattr(pico, name) is None
                and getattr(assertion.pico, name)
                and any(getattr(assertion.pico, name) in target.text for target in targets)
            }
            if (
                linker
                and targets
                and re.fullmatch(
                    r"(?:higher|lower|larger|smaller) doses?",
                    pico.intervention_or_exposure or "",
                    re.I,
                )
            ):
                parents = [
                    a
                    for a in plan.assertions
                    if a.assertion_id != aid
                    and any(
                        s.start <= target.start < target.end <= s.end
                        for s in a.spans
                        for target in targets
                    )
                ]
                if len(parents) == 1 and parents[0].pico.claim_type == pico.claim_type:
                    parent = parents[0]
                    entities = linker.link(parent.pico)
                    exposures = {
                        e.surface_text
                        for e in entities
                        if e.entity_type == "intervention_or_exposure"
                        and (e.mesh_id or e.umls_cui)
                        and any(e.surface_text in t.text for t in targets)
                    }
                    if len(exposures) == 1:
                        updates["intervention_or_exposure"] = next(iter(exposures))
                        if (pico.outcome or "").casefold() in {
                            "protection",
                            "benefit",
                            "benefits",
                            "risk",
                        }:
                            updates["outcome"] = parent.pico.outcome
            pico = pico.model_copy(update=updates)
        snapshots[aid] = ClaimSnapshot(
            claim_id=uuid5(analysis_id, aid),
            raw_text=assertion.source_text,
            normalized_text=assertion.normalized_text,
            pico=pico,
            claim_type=pico.claim_type,
            entities=linker.link(pico) if linker else (),
        )
    return snapshots


def document_normalization_audit(
    plan: DocumentPlan,
    group: DocumentGroup,
    snapshots: dict[str, ClaimSnapshot],
    linker: MedicalEntityLinker | None = None,
) -> tuple[dict[str, str], dict[str, NormalizationQuality], dict[str, bool]]:
    """Apply unchanged clinical readiness without forcing study metadata into PICO."""
    statuses: dict[str, str] = {}
    qualities: dict[str, NormalizationQuality] = {}
    readiness: dict[str, bool] = {}
    for aid in group.assertion_ids:
        assertion = plan.assertion(aid)
        claim = snapshots[aid]
        if assertion.kind in {"reported_study_fact", "methodology", "sample_size"}:
            statuses[aid] = "not_applicable"
            qualities[aid] = NormalizationQuality(
                normalization_warnings=("reported_source_fact_not_a_clinical_pico_assessment",)
            )
            readiness[aid] = assertion.planning_status == "ready"
            continue
        pico = claim.pico or assertion.pico
        quality = assess_completeness(
            pico,
            claim.entities,
            linker.mesh if linker else UnconfiguredMeshProvider(),
        )
        status = normalization_status(
            pico,
            linked_count=sum(
                e.mesh_id is not None or e.umls_cui is not None for e in claim.entities
            ),
            mention_count=len(claim.entities),
            quality=quality,
        )
        statuses[aid] = status
        qualities[aid] = quality
        readiness[aid] = assertion.planning_status == "ready" and ready_for_evidence(
            status,
            pico_json=pico.model_dump(mode="json"),
            quality_json=quality.model_dump(mode="json"),
            standalone_text=claim.normalized_text,
        )
    return statuses, qualities, readiness


def plan_group_queries(
    group: DocumentGroup,
    snapshots: dict[str, ClaimSnapshot],
    *,
    adaptive: bool = False,
) -> tuple[QueryPlan, tuple[str, ...]]:
    """Clue queries and round-robin assertion queries retain bounded coverage."""
    queries: list[RetrievalQuery] = []
    names = _study_names(group)
    topics = tuple(
        dict.fromkeys(
            field
            for claim in snapshots.values()
            if claim.pico
            for field in (claim.pico.intervention_or_exposure, claim.pico.outcome)
            if field
        )
    )[:6]
    for name in names[:2]:
        clue_query = _query_phrase(name)
        if topics:
            clue_query += " AND (" + " OR ".join(_query_phrase(term) for term in topics) + ")"
        queries.append(
            RetrievalQuery(
                query_id=f"Q{len(queries) + 1}",
                family="distinctive",
                query=clue_query,
                source_fields=("document.group.study_clues", "assertion.pico"),
            )
        )
    raw_clues = " ".join(span.text for span in group.study_clues)
    doi = re.search(r"\b10\.\d{4,9}/[^\s\"<>]+", raw_clues)
    if doi:
        queries.insert(
            0,
            RetrievalQuery(
                query_id="Q0",
                family="distinctive",
                query=f'"{doi.group().rstrip(".,;")}"[DOI]',
                source_fields=("document.group.study_clues.doi",),
            ),
        )
    planner = plan_adaptive_queries if adaptive else plan_pubmed_queries
    assertion_plans = {aid: planner(claim) for aid, claim in snapshots.items()}
    for round_index in range(3 if adaptive else 2):
        for aid, assertion_plan in assertion_plans.items():
            if len(assertion_plan.queries) > round_index:
                q = assertion_plan.queries[round_index]
                queries.append(
                    q.model_copy(
                        update={
                            "source_fields": (f"assertions.{aid}", *q.source_fields),
                        }
                    )
                )
    seen: set[str] = set()
    unique: list[RetrievalQuery] = []
    for query_item in queries:
        if query_item.query not in seen:
            seen.add(query_item.query)
            unique.append(query_item.model_copy(update={"query_id": f"Q{len(unique) + 1}"}))
    omitted = tuple(q.query for q in unique[_MAX_QUERIES:])
    return QueryPlan(
        version="2.0" if adaptive else "1.6",
        queries=tuple(unique[:_MAX_QUERIES]),
        warnings=("bounded_document_query_limit",) if omitted else (),
    ), omitted


def _source_match(
    group: DocumentGroup,
    snapshots: dict[str, ClaimSnapshot],
    documents: tuple[PubMedDocument, ...],
    passages: tuple[EvidencePassage, ...],
    evidence_ids: dict[str, str],
) -> GroupSourceMatch:
    if not group.study_clues:
        return GroupSourceMatch(status="not_applicable", reason="No reported study is attributed.")
    names = _study_names(group)
    clues = " ".join(span.text for span in group.study_clues)
    identifiers = set(re.findall(r"\b10\.\d{4,9}/[^\s\"<>]+", clues, re.I))
    pmids = set(re.findall(r"\bPMID\s*:?\s*(\d+)\b", clues, re.I))
    exposure_terms = {
        _phrase(claim.pico.intervention_or_exposure)
        for claim in snapshots.values()
        if claim.pico and claim.pico.intervention_or_exposure
    }
    outcome_terms = {
        _phrase(claim.pico.outcome)
        for claim in snapshots.values()
        if claim.pico and claim.pico.outcome
    }
    topics = [_words(field) for field in sorted(exposure_terms | outcome_terms)]
    candidates = []
    for document in documents:
        if not document.pmid:
            continue
        owned = [p for p in passages if p.document_id == document.document_id]
        identity_text = " ".join(
            p.text
            for p in owned
            if (not p.section.startswith("FULL_TEXT/") or "method" in p.section.casefold())
        )
        all_text = " ".join(p.text for p in owned)
        matching = []
        bibliography = metadata_clues(clues, document)
        fingerprints = version_fingerprints(snapshots, all_text) if bibliography else ()
        exact_identifier = document.pmid in pmids or bool(
            document.doi
            and (document.doi.casefold() in {v.rstrip(".,;").casefold() for v in identifiers})
        )
        if exact_identifier:
            matching.append("Exact supplied publication identifier agrees with PubMed metadata.")
        matched_names = [
            name
            for name in names
            if _phrase(name).casefold() in (_phrase(identity_text).casefold())
        ]
        for name in matched_names:
            matching.append(f"Named study/cohort clue occurs in title/abstract/methods: {name}.")
        topic_hits = sum(
            bool(words and len(words & _words(all_text)) / len(words) >= 0.7) for words in topics
        )
        if topic_hits:
            matching.append(f"{topic_hits} distinct exposure/endpoint fields occur in the source.")
        discrepancies = []
        if names and not matched_names:
            discrepancies.append("Named study/cohort clue is absent from title/abstract/methods.")
        if not exact_identifier:
            discrepancies.append("No exact publication ID was supplied; identity uses study clues.")
        source_words = _words(all_text)
        exposure_hit = any(
            words and len(words & source_words) / len(words) >= 0.7
            for words in map(_words, exposure_terms)
        )
        outcome_hit = any(
            words and len(words & source_words) / len(words) >= 0.7
            for words in map(_words, outcome_terms)
        )
        identity = exact_identifier or bool(matched_names and exposure_hit and outcome_hit)
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", clues))
        year_conflict = bool(
            years and document.publication_date and str(document.publication_date.year) not in years
        )
        if bibliography:
            matching.extend(bibliography)
            matching.extend(fingerprints)
            identity = identity or bool(fingerprints and exposure_hit and outcome_hit)
        if year_conflict and not exact_identifier:
            identity = False
            discrepancies.append("Supplied publication year differs from candidate metadata.")
        score = min(
            1.0,
            (
                0.8
                if exact_identifier
                else 0.65
                if bibliography and fingerprints
                else 0.55
                if matched_names or bibliography
                else 0
            )
            + min(0.3, topic_hits * 0.1),
        )
        if not matching:
            continue
        candidates.append(
            SourceMatchCandidate(
                document_id=document.document_id,
                pmid=document.pmid,
                title=document.title,
                canonical_url=document.canonical_url,
                score=score,
                matching_evidence=tuple(matching),
                discrepancies=tuple(discrepancies),
                evidence_ids=tuple(
                    evidence_ids[p.passage_id] for p in owned if p.passage_id in evidence_ids
                ),
                identity_established=identity,
            )
        )
    by_id = {document.document_id: document for document in documents}
    candidates.sort(
        key=lambda item: (
            -item.score,
            "PMC_DISCOVERY" not in by_id[item.document_id].query_ids,
            item.document_id,
        )
    )
    strong = [c for c in candidates if c.identity_established]
    if len(strong) == 1:
        return GroupSourceMatch(
            status="identified",
            matched_document_ids=(strong[0].document_id,),
            candidates=tuple(candidates[:8]),
            reason="One candidate matches independent study clues.",
            discrepancies=(
                "Figures, measures, adjustments and causation remain subject to "
                "separate source-fidelity and scientific validation.",
            ),
        )
    return GroupSourceMatch(
        status="uncertain" if candidates else "not_found",
        candidates=tuple(candidates[:8]),
        reason="Several candidates match; no unique study identity is established."
        if strong
        else ("Available candidates do not establish the attributed study identity."),
        discrepancies=("The attributed source must not be assumed from topical similarity.",),
    )


def _reported_selection(
    assertion: DocumentAssertion,
    passages: tuple[EvidencePassage, ...],
    candidate_ids: set[str],
) -> tuple[str, ...]:
    words = _words(assertion.source_text)
    ranked = sorted(
        (
            (
                len(words & _words(p.text)) / max(1, len(words))
                - min(0.4, max(0, len(p.text) - 4000) / 20000)
                + (0.15 if p.document_id in candidate_ids else 0),
                p,
            )
            for p in passages
            if p.section != "TITLE" and (not candidate_ids or p.document_id in candidate_ids)
        ),
        key=lambda pair: (-pair[0], pair[1].passage_id),
    )
    return tuple(p.passage_id for score, p in ranked[:3] if score > 0)


async def retrieve_document_group(
    analysis_id: UUID,
    plan: DocumentPlan,
    group: DocumentGroup,
    adapter: PubMedAdapter,
    *,
    crossref: CrossrefAdapter | None = None,
    authoritative: AuthoritativeAdapter | None = None,
    fulltext: PmcFullTextAdapter | None = None,
    linker: MedicalEntityLinker | None = None,
    source_cache: DocumentSourceCache | None = None,
    claim_snapshots: dict[str, ClaimSnapshot] | None = None,
    discovery: ScholarlyDiscovery | None = None,
    web: OfficialWebDiscovery | None = None,
) -> GroupEvidenceSnapshot:
    """Freeze per-group source HTTP attempts, without affecting single-claim callers."""
    with source_http_metrics() as counts:
        return await _retrieve_document_group(
            analysis_id,
            plan,
            group,
            adapter,
            crossref=crossref,
            authoritative=authoritative,
            fulltext=fulltext,
            linker=linker,
            source_cache=source_cache,
            claim_snapshots=claim_snapshots,
            discovery=discovery,
            web=web,
            source_http_requests=counts,
        )


async def _retrieve_document_group(
    analysis_id: UUID,
    plan: DocumentPlan,
    group: DocumentGroup,
    adapter: PubMedAdapter,
    *,
    crossref: CrossrefAdapter | None,
    authoritative: AuthoritativeAdapter | None,
    fulltext: PmcFullTextAdapter | None,
    linker: MedicalEntityLinker | None,
    source_cache: DocumentSourceCache | None,
    claim_snapshots: dict[str, ClaimSnapshot] | None,
    source_http_requests: dict[str, int],
    discovery: ScholarlyDiscovery | None,
    web: OfficialWebDiscovery | None,
) -> GroupEvidenceSnapshot:
    """Search once, fetch each publication once and freeze one assertion coverage union."""
    started = monotonic()
    cache = source_cache or DocumentSourceCache()
    snapshots = claim_snapshots or document_claim_snapshots(analysis_id, plan, group, linker)
    if set(snapshots) != set(group.assertion_ids):
        raise ValueError("Retrieval snapshots do not cover exactly the document group")
    statuses, qualities, readiness = document_normalization_audit(plan, group, snapshots, linker)
    query_plan, omitted_queries = plan_group_queries(
        group, snapshots, adaptive=discovery is not None
    )
    eligible = tuple(
        claim
        for aid, claim in snapshots.items()
        if plan.assertion(aid).checkable
        and plan.assertion(aid).planning_status == "ready"
        and readiness[aid]
    )
    if not eligible:
        # Retain incomplete normalization without manufacturing a search question.
        query_plan = query_plan.model_copy(update={"queries": ()})
    executions = []
    provenance: dict[str, set[str]] = {}
    limitations = []
    requests: Counter[str] = Counter()
    discovery_leads: list[DiscoveryLead] = []
    discovered_guidance: tuple[PubMedDocument, ...] = ()
    for query in query_plan.queries:
        try:
            requests["pubmed_searches"] += 1
            pmids, hit = await adapter.search(query.query)
            requests["pubmed_searches"] -= int(hit)
            requests["pubmed_search_cache_hits"] += int(hit)
            executions.append(
                QueryExecution(
                    query_id=query.query_id,
                    pmids=pmids,
                    cache_hit=hit,
                    **getattr(adapter, "last_search_diagnostics", {}),
                )
            )
            for pmid in pmids:
                provenance.setdefault(pmid, set()).add(query.query_id)
        except RetrievalError as exc:
            limitations.append(f"{query.query_id}: public source search unavailable ({exc.kind}).")
            executions.append(QueryExecution(query_id=query.query_id, pmids=(), cache_hit=False))
    if discovery and eligible:
        # At most two distinct medical questions supplement the existing 12-query
        # assertion coverage bound. No reporting study identity is inferred here.
        unique = {discovery_terms(c, broad=True): c for c in eligible}
        searches = [
            (provider, scholarly_query(c, broad=True, provider=provider))
            for c in list(unique.values())[:2]
            for provider in ("europe_pmc", "openalex")
        ]
        batches = await asyncio.gather(*(discovery.search(p, q) for p, q in searches))
        for batch in batches:
            for lead in batch:
                discovery_leads.append(lead)
                if lead.pmid and lead.publication_type != "retracted":
                    provenance.setdefault(lead.pmid, set()).add("discovery:" + lead.provider)
        if len(unique) > 2:
            limitations.append(
                "Supplementary discovery covered two medical questions; "
                "remaining assertions retain bounded PubMed query coverage."
            )
        if web:
            discovered_guidance = await web.retrieve(
                eligible[0], discovery_terms(eligible[0], broad=True)
            )
    if fulltext and group.study_clues and query_plan.queries:
        # Search article bodies for clues missing from abstracts, through PMC only.
        topics = [
            _words(s.pico.intervention_or_exposure or "")
            for s in snapshots.values()
            if s.pico and s.pico.intervention_or_exposure
        ]
        names = _study_names(group)
        if names and topics:
            pmc_query = "(" + " OR ".join(_query_phrase(name) for name in names[:2]) + ") AND ("
            pmc_query += " OR ".join(_query_phrase(" ".join(sorted(words))) for words in topics[:2])
            pmc_query += ")"
            pmc_query = pmc_query.replace("[Title/Abstract]", "[All Fields]")
            before = fulltext.discovery_requests
            try:
                for pmid in await fulltext.discover(pmc_query):
                    provenance.setdefault(pmid, set()).add("PMC_DISCOVERY")
            except RetrievalError:
                limitations.append("PMC full-text candidate discovery was unavailable.")
            requests["pmc_discovery_requests"] += fulltext.discovery_requests - before
    if len(provenance) > _MAX_PMIDS:
        limitations.append(
            "Candidate retrieval exceeded the 50-publication bound; remaining IDs "
            "are recorded but not fetched."
        )
    wanted = tuple(
        sorted(
            provenance,
            key=lambda pmid: (
                "PMC_DISCOVERY" not in provenance[pmid],
                list(provenance).index(pmid),
            ),
        )
    )[:_MAX_PMIDS]
    missing = tuple(pmid for pmid in wanted if pmid not in cache.documents)
    if missing:
        fetched = await adapter.fetch_cached(missing) if discovery else await adapter.fetch(missing)
        requests["pubmed_fetch_batches"] += 1
        requests["pubmed_publications_fetched"] += len(fetched.documents)
        cache.documents.update({d.pmid: d for d in fetched.documents})
    requests["publication_reuse_hits"] += len(wanted) - len(missing)
    documents = deduplicate_documents(
        tuple(
            cache.documents[pmid].model_copy(
                update={
                    "query_ids": tuple(sorted(provenance[pmid])),
                }
            )
            for pmid in wanted
            if pmid in cache.documents
        )
    )
    if discovery:
        from app.retrieval.v2 import identity_matches

        verified = []
        for doc in documents:
            matching = [
                lead
                for lead in discovery_leads
                if identity_matches(lead, doc) and lead.publication_type != "retracted"
            ]
            if not matching and not any(
                q.startswith("Q") or q == "PMC_DISCOVERY" for q in provenance[doc.pmid]
            ):
                limitations.append(
                    f"Unverified supplementary identity excluded: {doc.document_id}."
                )
                continue
            verified.append(
                doc.model_copy(
                    update={
                        "metadata_provenance": {
                            **doc.metadata_provenance,
                            **{
                                "discovered_by:" + lead.provider: lead.identifier
                                for lead in matching
                            },
                            **{
                                "discovery_query:"
                                + lead.provider
                                + ":"
                                + hashlib.sha256(lead.query.encode()).hexdigest(): lead.query
                                for lead in matching
                                if lead.query
                            },
                        }
                    }
                )
            )
        documents = tuple(verified)
    unenriched = tuple(d for d in documents if d.document_id not in cache.crossref)
    if unenriched:
        cache.crossref.update(await _enrich_dois(unenriched, crossref, timeout_seconds=20))
        requests["crossref_enrichment_calls"] += (
            sum(bool(d.doi) for d in unenriched) if crossref else 0
        )
    representative = next(iter(snapshots.values()))
    documents = tuple(
        annotate_study_quality(
            representative,
            d.model_copy(
                update={
                    "crossref": cache.crossref.get(d.document_id, unavailable_crossref(d.doi)),
                    "integrity": merge_integrity(
                        d,
                        cache.crossref.get(
                            d.document_id,
                            unavailable_crossref(d.doi),
                        ),
                    ),
                }
            ),
        )
        for d in documents
    )
    if authoritative and eligible:
        approved, approved_statuses = await authoritative.retrieve_group(
            eligible,
            document_cache=cache.authoritative,
        )
        requests["authoritative_sources_considered"] += len(approved_statuses)
        requests["authoritative_publications_returned"] += len(approved)
        limitations.extend(
            f"Approved source {sid}: {status}."
            for sid, status in approved_statuses.items()
            if status not in {"available", "current"}
        )
        limitations.extend(
            f"Approved source {d.authoritative.source_id}: "
            f"{d.authoritative.omitted_block_count} complete paragraphs omitted from the bounded "
            "group excerpt; their claims remain subject to available-source coverage."
            for d in approved
            if d.authoritative and d.authoritative.omitted_block_count
        )
        documents = deduplicate_documents((*documents, *approved))
    documents = deduplicate_documents((*documents, *discovered_guidance))
    passages = tuple(p for d in documents for p in extract_passages(d))
    initial_ids = {p.passage_id: f"E{i}" for i, p in enumerate(passages, 1)}
    initial_match = _source_match(group, snapshots, documents, passages, initial_ids)
    fulltexts = []
    if fulltext:
        candidate_documents = {c.document_id for c in initial_match.candidates[:3]}
        for d in documents:
            if d.document_id not in candidate_documents:
                continue
            reused = d.document_id in cache.fulltext
            result = cache.fulltext.get(d.document_id)
            if result is None:
                result = await fulltext.fetch(d)
                cache.fulltext[d.document_id] = result
            fulltexts.append(result)
            requests["pmc_article_requests"] += 0 if reused else result.source_requests
            requests["pmc_cache_or_reuse_hits"] += int(reused or result.cache_hit)
            limitations.extend(result.limitations)
        passages = (*passages, *(p for result in fulltexts for p in result.passages))
    else:
        limitations.append("Full text is unavailable; source matching uses abstracts only.")
    unique_passages = {p.passage_id: p for p in passages}
    passages = tuple(unique_passages.values())
    evidence_ids = {p.passage_id: f"E{i}" for i, p in enumerate(passages, 1)}
    match = _source_match(group, snapshots, documents, passages, evidence_ids)
    candidate_ids = set(match.matched_document_ids) or {
        c.document_id for c in match.candidates[:2] if c.score >= 0.55
    }
    if not candidate_ids:
        # Unknown study identity is not permission to rank any large abstract
        # that happens to mention generic methods/participants. Require the
        # group's actual exposure and endpoint in publication-level context.
        exposures = [_words(c.pico.intervention_or_exposure or "") for c in eligible if c.pico]
        outcomes = [_words(c.pico.outcome or "") for c in eligible if c.pico]
        candidate_ids = {
            d.document_id
            for d in documents
            if any(w and len(w & _words(d.title)) / len(w) >= 0.6 for w in exposures)
            and any(w and len(w & _words(d.title)) / len(w) >= 0.6 for w in outcomes)
        }
    per_assertion: dict[str, tuple[str, ...]] = {}
    selected: set[str] = set()
    for aid, claim in snapshots.items():
        assertion = plan.assertion(aid)
        if not assertion.checkable or not readiness[aid]:
            per_assertion[aid] = ()
            continue
        if assertion.kind in {"reported_study_fact", "methodology", "sample_size"}:
            chosen = (
                _reported_selection(assertion, passages, candidate_ids) if candidate_ids else ()
            )
        else:
            ranked = rank_passages(claim, documents, passages)
            individual = build_evidence_pack(
                claim,
                query_plan,
                documents,
                ranked,
                selected_limit=3,
                max_per_document=2,
                pack_version="2.0" if discovery else "1.5",
            )
            local = {p.evidence_id: p.passage.passage_id for p in individual.passages}
            chosen = tuple(local[eid] for eid in individual.selected_evidence_ids)
        ids = tuple(evidence_ids[pid] for pid in chosen)
        per_assertion[aid] = ids
        selected.update(ids)
    # At most eight assertions x three passages; no assertion is silently crowded out.
    if len(selected) > _MAX_SELECTED:
        raise ValueError("Shared source coverage exceeded its assertion-derived bound")
    ranked_group = tuple(
        RankedPassage(
            evidence_id=evidence_ids[p.passage_id],
            passage=p,
            rank=i,
            retrieval_score=1.0 if evidence_ids[p.passage_id] in selected else 0.0,
            factors={"assertion_coverage_selection": float(evidence_ids[p.passage_id] in selected)},
            passage_type="title" if p.section == "TITLE" else "abstract",
            selected_for_judging=evidence_ids[p.passage_id] in selected,
            selection_reason="relevant_abstract"
            if evidence_ids[p.passage_id] in selected
            else None,
        )
        for i, p in enumerate(passages, 1)
        if evidence_ids[p.passage_id] in selected
    )
    selected_ids = tuple(
        evidence_ids[p.passage_id] for p in passages if evidence_ids[p.passage_id] in selected
    )
    pack_hash = hashlib.sha256(
        canonical_pack_bytes(
            representative,
            query_plan,
            documents,
            ranked_group,
            selected_ids,
            pack_version="2.0" if discovery else "1.5",
        )
    ).hexdigest()
    pack = EvidencePack(
        evidence_pack_version="2.0" if discovery else "1.5",
        claim_id=representative.claim_id,
        claim_snapshot=representative,
        query_plan=query_plan,
        documents=documents,
        passages=ranked_group,
        selected_evidence_ids=selected_ids,
        retrieved_at=datetime.now(UTC),
        snapshot_hash=pack_hash,
    )
    document_map = {d.document_id: d for d in documents}
    source_units = tuple(
        SourceUnit(
            unit_id=f"{p.evidence_id}.U1",
            evidence_id=p.evidence_id,
            document_id=p.passage.document_id,
            document_sha256=document_map[p.passage.document_id].content_sha256,
            passage_sha256=p.passage.content_sha256,
            content_version=pack.evidence_pack_version,
            start=0,
            end=len(p.passage.text),
            text=p.passage.text,
            section=p.passage.section,
        )
        for p in ranked_group
        if p.evidence_id in selected
    )
    if omitted_queries:
        limitations.append(
            f"{len(omitted_queries)} duplicate-free secondary queries exceeded the "
            "document search bound; no assertion was discarded."
        )
    data: dict[str, object] = {
        "version": "document-evidence-2.0" if discovery else VERSION,
        "group_id": group.group_id,
        "document_sha256": plan.original_sha256,
        "pack": pack.model_dump(mode="json"),
        "claim_snapshots": {aid: c.model_dump(mode="json") for aid, c in snapshots.items()},
        "normalization_status": statuses,
        "normalization_quality": {aid: q.model_dump(mode="json") for aid, q in qualities.items()},
        "normalization_ready": readiness,
        "per_assertion_evidence_ids": per_assertion,
        "source_match": match.model_dump(mode="json"),
        "source_units": [u.model_dump(mode="json") for u in source_units],
        "source_quantity_catalog": derive_catalog(
            [u.model_dump(mode="json") for u in source_units]
        ),
        "query_executions": [q.model_dump(mode="json") for q in executions],
        "candidate_pmids": tuple(provenance),
        "unfetched_candidate_pmids": tuple(pmid for pmid in provenance if pmid not in wanted),
        "retrieved_passages": [p.model_dump(mode="json") for p in passages],
        "fulltext_sources": [f.model_dump(mode="json") for f in fulltexts],
        "source_fetches": dict(requests),
        "source_http_requests": dict(source_http_requests),
        "metrics": {
            "retrieval_elapsed_ms": round((monotonic() - started) * 1000),
            "source_http_request_count": sum(source_http_requests.values()),
            "query_count": len(query_plan.queries),
            "candidate_count": len(documents),
            "selected_passage_count": len(selected),
            "assertions_with_coverage": sum(bool(ids) for ids in per_assertion.values()),
        },
        "limitations": tuple(dict.fromkeys(limitations)),
    }
    if discovery:
        data["discovery_audit"] = {
            "providers": discovery.executions,
            "official_web": web.executions if web else [],
            "lead_count": len(discovery_leads),
            "canonical_identity_required": True,
            "leads": [asdict(lead) for lead in discovery_leads],
            "model_calls": 0,
        }
    return GroupEvidenceSnapshot.model_validate({**data, "snapshot_hash": _snapshot_digest(data)})
