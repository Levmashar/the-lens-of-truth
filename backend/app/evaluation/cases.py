"""Versioned engineering controls, NOT clinical gold or historical live analyses.

Existing conditional premises are explicitly synthetic source units. The split
is fixed before any Slice 4 model measurements. Expected annotations never
enter judge requests. Public real-source controls are frozen separately.
"""

import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from app.pipeline.claim_types import ClaimType
from app.pipeline.pico import NormalizedPico
from app.retrieval.evidence_pack import canonical_pack_bytes
from app.retrieval.models import (
    AbstractSection,
    ClaimSnapshot,
    DocumentIntegrity,
    EvidencePack,
    EvidencePassage,
    PubMedDocument,
    QueryPlan,
    RankedPassage,
    RelationshipAnalysis,
)
from app.validation.relation_cases import CASES, RelationCase
from app.validation.relations import ClaimRelation, ClaimScope, Materiality

VERSION = "judge-controls-1.0"
NOW = datetime(2026, 10, 2, tzinfo=UTC)


@dataclass(frozen=True)
class BenchmarkCase:
    id: str
    split: str
    annotation: RelationCase
    pack: EvidencePack
    origin: str = "synthetic conditional development fixture; not a real paper"


def synthetic_pack(case: RelationCase) -> EvidencePack:
    identity = uuid5(NAMESPACE_URL, f"{VERSION}:{case.id}")
    snapshot = ClaimSnapshot(
        claim_id=identity, raw_text=case.claim, claim_type=case.claim_type,
        pico=NormalizedPico(
            original_claim=case.claim, claim_type=case.claim_type, population=case.population,
            intervention_or_exposure=case.exposure, comparator=case.comparator,
            outcome=case.outcome,
        ),
    )
    digest = hashlib.sha256(case.statement.encode()).hexdigest()
    randomized = case.study_design in {"randomized_controlled_trial", "clinical_trial"}
    analysis = ("randomized_intervention" if randomized else
                case.study_design if case.study_design in {"meta_analysis", "systematic_review",
                                                           "cross_sectional", "case_control"}
                else "prospective_cohort" if case.study_design == "cohort" else "unknown")
    doc = PubMedDocument(
        document_id=f"fixture:{identity}", pmid="fixture-only-NOT-A-PMID",
        title="SYNTHETIC CONDITIONAL PREMISE — not a publication",
        abstract=case.statement, abstract_sections=(AbstractSection(label="RESULTS",
                                                                   text=case.statement),),
        canonical_url="https://example.invalid/development-fixture", retrieved_at=NOW,
        content_sha256=digest, integrity=DocumentIntegrity(status="valid"),
        study_design=case.study_design,  # type: ignore[arg-type]
        study_design_source="synthetic_stipulated_metadata", evidence_role_hint="direct",
        relationship_analysis=RelationshipAnalysis(
            analysis_design=analysis,  # type: ignore[arg-type]
            exposure_assignment="randomized" if randomized else "synthesized" if
            analysis in {"meta_analysis", "systematic_review"} else "observed",
            basis="synthetic_stipulation_NOT_clinical_evidence",
        ),
    )
    passage = RankedPassage(
        evidence_id="E1", rank=1, retrieval_score=1, factors={}, selected_for_judging=True,
        passage=EvidencePassage(
            passage_id=f"{identity}:result", document_id=doc.document_id,
            text=case.statement, section="RESULTS", content_sha256=digest,
        ),
    )
    plan = QueryPlan(queries=(), claim_type=case.claim_type)
    payload = canonical_pack_bytes(snapshot, plan, (doc,), (passage,), ("E1",), pack_version="1.5")
    return EvidencePack(
        evidence_pack_version="1.5", claim_id=identity, claim_snapshot=snapshot,
        query_plan=plan, documents=(doc,), passages=(passage,), selected_evidence_ids=("E1",),
        retrieved_at=NOW, snapshot_hash=hashlib.sha256(payload).hexdigest(),
    )


def benchmark_cases() -> tuple[BenchmarkCase, ...]:
    extras = (
        RelationCase("inverse-smoking", "inverse", "Smoking does not cause lung cancer.",
                     "A systematic synthesis of epidemiologic evidence concluded that smoking "
                     "causes lung cancer.", ClaimRelation.CONTRADICTS, ClaimScope.ALIGNED,
                     Materiality.DECISIVE, "Explicit opposite causal synthesis.",
                     study_design="systematic_review", exposure="Smoking", outcome="lung cancer"),
        RelationCase("regular-smoking", "smoking",
                     "Regularly smoking cigarettes causes lung cancer.",
                     "A systematic synthesis concluded that regularly smoking cigarettes "
                     "causes lung cancer.", ClaimRelation.SUPPORTS, ClaimScope.ALIGNED,
                     Materiality.DECISIVE, "Exact synthesis finding, not one observed cohort.",
                     study_design="systematic_review", exposure="smoking cigarettes",
                     outcome="lung cancer"),
        RelationCase("hypertension-stroke", "association",
                     "High blood pressure increases stroke risk.",
                     "A prospective cohort found higher stroke risk with high blood pressure.",
                     ClaimRelation.SUPPORTS, ClaimScope.ALIGNED, Materiality.DECISIVE,
                     "Risk association matches assertion strength.",
                     claim_type=ClaimType.ASSOCIATION, study_design="cohort",
                     exposure="High blood pressure", outcome="stroke"),
        RelationCase("hypertension-cancer", "endpoint", "High blood pressure causes cancer.",
                     "High blood pressure was associated with stroke; cancer was not measured.",
                     ClaimRelation.CONTEXT_ONLY, ClaimScope.MISMATCH, Materiality.CONTEXTUAL,
                     "Wrong endpoint cannot establish asserted causation.",
                     study_design="cohort", exposure="High blood pressure", outcome="cancer"),
        RelationCase("vitamin-c-cold", "prevention", "Vitamin C prevents the common cold.",
                     "A systematic review found imprecise incidence estimates for Vitamin C "
                     "and the common cold, with confidence intervals spanning benefit and harm.",
                     ClaimRelation.INSUFFICIENT, ClaimScope.ALIGNED, Materiality.SUPPORTING,
                     "Synthetic imprecise result, not proof of no preventive effect.",
                     claim_type=ClaimType.PREVENTION, study_design="systematic_review",
                     exposure="Vitamin C", outcome="common cold"),
        RelationCase("soy-men-estrogen", "population",
                     "Regular soy consumption in men increases estrogen levels.",
                     "A randomized soy trial in women measured estrogen levels; men were not "
                     "enrolled.", ClaimRelation.INSUFFICIENT, ClaimScope.MISMATCH,
                     Materiality.SUPPORTING, "Exposure arm does not match population.",
                     population="men", exposure="soy", outcome="estrogen levels"),
        RelationCase("soy-men-muscle", "comparator",
                     "Regular soy consumption in men lowers muscle gain.",
                     "Men assigned to soy versus whey had similar muscle gain; no nonuse "
                     "comparison was included.", ClaimRelation.INSUFFICIENT, ClaimScope.INDIRECT,
                     Materiality.SUPPORTING, "Active comparator cannot decide absolute use.",
                     population="men", exposure="soy", outcome="muscle gain"),
        replace(CASES[0], id="held-out-support", claim="Intervention X increases outcome Y.",
                statement="Randomized Intervention X versus placebo increased outcome Y "
                "incidence with a precise estimate.", exposure="Intervention X",
                outcome="outcome Y"),
    )
    return tuple(BenchmarkCase(c.id, "held_out" if i % 4 == 3 else "development", c,
                               synthetic_pack(c)) for i, c in enumerate((*CASES, *extras)))
