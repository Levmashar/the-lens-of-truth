"""Explicit synthetic engineering premises; not papers or reviewed clinical gold."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.evaluation.cases import synthetic_pack
from app.judging.compact23 import prepare_compact23
from app.judging.models import JudgeRun
from app.judging.source_units import materialize_content
from app.retrieval.models import EvidencePack
from app.validation.axes import EvidenceClaimAssessment
from app.validation.joint23 import JointResponse23
from app.validation.relation_cases import RelationCase
from app.validation.relations import ClaimRelation, ClaimScope, Materiality


@dataclass(frozen=True)
class ProbeCase:
    id: str
    claim: str
    source: str
    finding: str
    direction: str
    scope: str = "aligned"
    strength: str = "strong"
    role: str = "direct"
    scope_basis: str = "same_question"
    finding_basis: str = "direct_result"
    design: str = "randomized_controlled_trial"
    exposure: str = "X"
    outcome: str = "Y"
    label: str = "supported"
    raw: str | None = None
    details: tuple[str, ...] = ()
    comparator: str | None = None
    attribution: str = "supported_by_sources"


CASES = (
    ProbeCase("sunscreen-null", "Frequent sunscreen use causes invasive melanoma.",
              "A synthesis found no significant association between sunscreen and melanoma; "
              "estimates were imprecise with intervals spanning benefit and harm.",
              "The synthesis found an imprecise nonsignificant association.", "neutral",
              strength="insufficient", role="synthesis", finding_basis="imprecise_null",
              design="meta_analysis", exposure="Frequent sunscreen use",
              outcome="invasive melanoma",
              label="not_enough_evidence"),
    ProbeCase("sunscreen-gradient", "Frequent sunscreen use causes invasive melanoma.",
              "Adults were randomized to daily or discretionary sunscreen. Invasive melanomas "
              "were substantially fewer in the daily group, HR 0.27 (95% CI 0.08-0.97).",
              "The randomized daily versus discretionary sunscreen trial found fewer invasive "
              "melanomas in the daily group.", "opposes_claim", scope="compatible_but_narrower",
              scope_basis="exposure_gradient", exposure="Frequent sunscreen use",
              outcome="invasive melanoma", label="contradicted"),
    ProbeCase("smoking-positive", "Smoking causes lung cancer.",
              "A systematic causal assessment concludes that smoking causes lung cancer.",
              "The causal synthesis concludes that smoking causes lung cancer.", "supports_claim",
              role="synthesis", finding_basis="causal_assessment", design="systematic_review",
              exposure="Smoking", outcome="lung cancer"),
    ProbeCase("smoking-inverse", "Smoking does not cause lung cancer.",
              "A systematic causal assessment concludes that smoking causes lung cancer.",
              "The causal synthesis concludes that smoking causes lung cancer.", "opposes_claim",
              role="synthesis", finding_basis="causal_assessment", design="systematic_review",
              exposure="Smoking", outcome="lung cancer", label="contradicted"),
    ProbeCase("carrot-reverse", "Carrots improve eyesight.",
              "A cross-sectional survey associated carrots with poor night vision. People with "
              "poor vision may eat more carrots; reverse causation cannot be excluded.",
              "The observational carrot association cannot exclude reverse causation.", "unclear",
              strength="insufficient", finding_basis="reverse_causation", design="cross_sectional",
              exposure="Carrots", outcome="eyesight", label="not_enough_evidence"),
    ProbeCase("numeric-distortion", "X reduces Y risk by 85%.",
              "A randomized X versus placebo study found RR 0.85 for Y.",
              "X reduced Y risk by 85%.", "opposes_claim", finding_basis="direct_result"),
    ProbeCase("conflicting-evidence", "X increases Y.",
              "One randomized X trial increased Y; a different randomized X trial reduced Y. "
              "The conflicting evidence cannot be resolved.",
              "Two randomized X studies reported opposing effects on Y.", "mixed",
              strength="uncertain", finding_basis="conflicting_results",
              label="not_enough_evidence"),
    ProbeCase("wide-null", "X increases Y.",
              "A randomized X trial found RR 1.10 (95% CI 0.40-3.00), nonsignificant.",
              "The randomized estimate was imprecise and nonsignificant.", "neutral",
              strength="insufficient", finding_basis="imprecise_null",
              label="not_enough_evidence"),
    ProbeCase("precise-null", "X doubles Y risk.",
              "A randomized X trial precisely excluded a doubling of Y risk and established "
              "equivalence within narrow clinically relevant bounds.",
              "The randomized equivalence result excluded a doubling of Y risk.", "opposes_claim",
              finding_basis="precise_null", label="contradicted"),
    ProbeCase("opposite-trial", "X increases Y.",
              "A randomized X versus placebo trial precisely found less Y with X.",
              "The randomized trial found less Y with X.", "opposes_claim", label="contradicted"),
    ProbeCase("association-causal", "X causes Y.",
              "A cohort associated X with Y, but confounding prevents causal inference.",
              "The cohort reported an association but could not infer causality.", "supports_claim",
              strength="insufficient", finding_basis="association", design="cohort",
              label="not_enough_evidence"),
    ProbeCase("narrow-population", "X increases Y.",
              "A randomized X trial in children increased Y. Adults were not studied.",
              "The randomized effect was limited to children.", "supports_claim",
              scope="compatible_but_narrower", scope_basis="population", strength="supporting",
              label="not_enough_evidence"),
    ProbeCase("narrow-dose", "X increases Y.",
              "A randomized high-dose X trial increased Y; lower doses were not tested.",
              "The randomized increase was observed only for the tested high dose.",
              "supports_claim",
              scope="compatible_but_narrower", scope_basis="dose", strength="supporting",
              label="not_enough_evidence"),
    ProbeCase("soy-comparator", "Soy use lowers muscle gain.",
              "Soy versus whey yielded similar muscle gain; no absolute-use effect was tested.",
              "The soy versus whey trial only tested that active comparison.", "neutral",
              scope="broader_or_indirect", scope_basis="active_alternative", strength="supporting",
              exposure="Soy use", outcome="muscle gain", label="not_enough_evidence"),
    ProbeCase("wrong-outcome", "X causes Y.",
              "A trial of X measured vitamin D but did not measure Y.",
              "The trial measured a different endpoint, not Y.", "unclear", scope="incompatible",
              scope_basis="endpoint", strength="insufficient", role="contextual",
              finding_basis="context", label="not_enough_evidence"),
    ProbeCase("background", "Smoking causes lung cancer.",
              "A paper described stigma among lung-cancer patients. "
              "Smoking causality was not tested.",
              "The paper describes patient stigma, not smoking causality.", "neutral",
              strength="weak", role="background", finding_basis="context", design="unknown",
              exposure="Smoking", outcome="lung cancer", label="not_enough_evidence"),
    ProbeCase("guidance", "X causes Y.",
              "An organization's guidance recommends avoiding X, "
              "but does not assess causal Y evidence.",
              "The source recommends avoidance without a causal evidence assessment.", "neutral",
              strength="weak", role="contextual", finding_basis="context", design="unknown",
              label="not_enough_evidence"),
    ProbeCase("overstated-null", "X causes Y.",
              "No significant association was found. Intervals span benefit and harm; "
              "further studies are needed.", "X does not cause Y.", "neutral",
              strength="insufficient", finding_basis="imprecise_null", design="meta_analysis",
              label="contradicted", attribution="not_established_by_sources"),
)


def probe_judge(case: ProbeCase) -> tuple[JudgeRun, EvidencePack]:
    annotation = RelationCase(
        case.id, "slice41", case.claim, case.source, ClaimRelation.INSUFFICIENT,
        ClaimScope.ALIGNED, Materiality.SUPPORTING, "Synthetic engineering premise only.",
        study_design=case.design, exposure=case.exposure, outcome=case.outcome,
        comparator=case.comparator,
    )
    pack = synthetic_pack(annotation)
    prepared = prepare_compact23(uuid4(), pack)
    raw = json.dumps({"label": case.label, "statements": [{
        "statement_id": "S1", "text": case.raw or case.finding,
        "qualitative_finding": case.finding, "numeric_details": case.details,
        "numeric_dependency": False, "kind": "study_finding", "source_unit_ids": ["E1.U1"],
    }], "conclusion": {"based_on_statement_ids": ["S1"],
                        "justification": "S1 is the source-grounded premise for this proposal.",
                        "qualitative_justification": "S1 is the premise for this proposal.",
                        "numeric_dependency": False}, "uncertainty_reasons": []})
    now = datetime.now(UTC)
    decision = materialize_content(raw, prepared.input_snapshot_json)
    return JudgeRun(
        judge_run_id=uuid4(), claim_id=pack.claim_id, evidence_pack_id=prepared.pack_id,
        evidence_pack_hash=pack.snapshot_hash, slot=1, provider="fixture", model="fixture",
        model_family="fixture", prompt_version=prepared.prompt_version,
        prompt_hash=prepared.prompt_hash, requested_at=now, responded_at=now,
        latency_ms=0, attempt_count=0, outcome_status="succeeded", decision=decision,
        response_json={**decision.model_dump(mode="json"), "raw_model_content": raw},
        input_snapshot_version=prepared.input_snapshot_version,
        input_snapshot_json=prepared.input_snapshot_json,
        input_snapshot_hash=prepared.input_snapshot_hash,
    ), pack


def annotated_response(case: ProbeCase) -> JointResponse23:
    assessment = EvidenceClaimAssessment.model_validate({
        "statement_id": "S1", "direction": case.direction, "scope": case.scope,
        "strength": case.strength, "role": case.role, "scope_basis": case.scope_basis,
        "finding_basis": case.finding_basis, "reason": "Explicit synthetic fixture annotation.",
    })
    return JointResponse23.model_validate_json(json.dumps({
        "attributions": [{"statement_id": "S1", "evidence_ids": ("E1",),
                          "status": case.attribution, "scope_match": "exact",
                          "reason": "Stipulated accurate qualitative premise.",
                          "numeric_independent": True}],
        "assessments": [assessment.model_dump(mode="json")], "missing_material_evidence": False,
    }))
