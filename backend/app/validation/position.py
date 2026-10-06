"""Backend-owned evidence position, independent of every model conclusion/label."""

from pydantic import Field

from app.judging.models import JudgeLabel
from app.retrieval.sufficiency import EvidenceDesignFact, design_eligible
from app.validation.axes import AxesQualifierInput, gradient_compatible, mapped_relations
from app.validation.models import ConclusionJustificationStatus as Status
from app.validation.models import FrozenModel
from app.validation.qualification import (
    CAUSAL_DESIGNS,
    CAUSAL_TYPES,
    ConclusionQualification,
    FindingQualificationInput,
    qualify_conclusion,
)
from app.validation.qualification import (
    QualificationReason as R,
)
from app.validation.relations import ClaimRelation, ClaimRelationAssessment, Materiality

LEGACY_VERSION = "validated-evidence-position-1.0"
METADATA_VERSION = "validated-evidence-position-1.1"
TRIAL_METHOD_VERSION = "validated-evidence-position-1.2"
SOURCE_GUARD_VERSION = "validated-evidence-position-1.3"
ENDPOINT_GUARD_VERSION = "validated-evidence-position-1.4"
SCOPE_POLARITY_VERSION = "validated-evidence-position-1.5"
LABORATORY_VERSION = "validated-evidence-position-1.6"
CLAIM_TYPE_VERSION = "validated-evidence-position-1.7"
VERSION = "validated-evidence-position-1.8"
VERSIONS = {LEGACY_VERSION, METADATA_VERSION, TRIAL_METHOD_VERSION, SOURCE_GUARD_VERSION,
            ENDPOINT_GUARD_VERSION, SCOPE_POLARITY_VERSION, LABORATORY_VERSION,
                                 CLAIM_TYPE_VERSION, VERSION}


class EvidencePositionAudit(FrozenModel):
    version: str = VERSION
    input: AxesQualifierInput
    output: ConclusionQualification
    validated_evidence_position: JudgeLabel | None
    guarded_relations: tuple[ClaimRelationAssessment, ...]
    design_materiality_statement_ids: tuple[str, ...] = ()
    semantic_guard_overrides: dict[str, tuple[str, ...]] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )
    finding_design_overrides: dict[str, tuple[EvidenceDesignFact, ...]] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )
    finding_relation_overrides: dict[str, tuple[str, ...]] = Field(
        default_factory=dict, exclude_if=lambda value: not value
    )
    ignored_context_integrity_statement_ids: tuple[str, ...] = Field(
        default=(), exclude_if=lambda value: not value
    )


def eligible(data: AxesQualifierInput, finding: FindingQualificationInput) -> bool:
    if data.base.evidence_policy in {"question-evidence-1.0", "question-evidence-2.0",
                                "question-evidence-2.1"}:
        peers = tuple(f for item in data.base.findings
                      if any(a.statement_id == item.statement_id and a.scope == "aligned"
                             and a.direction == next((axis.direction for axis in data.assessments
                                 if axis.statement_id == finding.statement_id), None)
                             and a.role in {"direct", "synthesis"}
                             and a.strength in {"strong", "decisive"}
                             and a.finding_basis in {"direct_result", "causal_assessment"}
                             for a in data.assessments)
                      for f in item.evidence_design_facts)
        return any(
            design_eligible(data.base.question_category, f, policy=data.base.evidence_policy,
                            peers=peers) for f in finding.evidence_design_facts
        )
    return data.base.claim_type not in CAUSAL_TYPES or bool(
        set(finding.study_designs) & CAUSAL_DESIGNS
    )


def _derive_position10(
    data: AxesQualifierInput, *, objective_design: bool = False
) -> EvidencePositionAudit:
    """Reuse provenance/design/numeric gates; proposals never determine a vote.

    All validated findings participate, including findings omitted from the
    judge's conclusion dependencies. Raw semantic axes remain untouched.
    """
    findings = {f.statement_id: f for f in data.base.findings}
    relations = list(mapped_relations(data))
    promoted = []
    for index, (axis, relation) in enumerate(zip(data.assessments, relations, strict=True)):
        finding = findings.get(axis.statement_id)
        aligned = axis.scope == "aligned" or (
            axis.scope == "compatible_but_narrower" and gradient_compatible(data, axis)
        )
        if (
            finding is not None
            and aligned
            and axis.role in {"direct", "synthesis"}
            and axis.strength == "supporting"
            and axis.finding_basis in {"direct_result", "causal_assessment"}
            and relation.relation in {"supports_claim", "contradicts_claim"}
            and eligible(data, finding)
            and "mismatch" not in finding.deterministic_scopes
            and (
                "aligned" in finding.deterministic_relations
                or (
                    objective_design
                    and any(
                        (
                            fact.synthesis_randomized_trials is True
                            or fact.completed_randomized_result_synthesis is True
                            or fact.experimental_assignment_text is not None
                            or (data.base.evidence_policy in {
                                "question-evidence-2.0", "question-evidence-2.1"}
                                and fact.causal_assessment_text is not None)
                        )
                        for fact in finding.evidence_design_facts
                    )
                )
            )
            and not {"reverse", "weaker_than_claim"} & set(finding.deterministic_relations)
        ):
            # A matched randomized intervention result or direct synthesis/causal
            # assessment has objective materiality. Design alone supplies no direction.
            randomized = any(
                f.analysis_design == "randomized_intervention"
                and f.exposure_assignment == "randomized"
                or f.analysis_design in {"controlled_laboratory_experiment",
                                         "laboratory_intervention"}
                and f.exposure_assignment == "experimental"
                for f in finding.evidence_design_facts
            )
            synthesis = (
                axis.role == "synthesis"
                or axis.finding_basis == "causal_assessment"
                or any(
                    f.analysis_design in {"systematic_review", "meta_analysis"}
                    for f in finding.evidence_design_facts
                )
            )
            if randomized or synthesis:
                relations[index] = relation.model_copy(update={"materiality": Materiality.DECISIVE})
                promoted.append(axis.statement_id)

    # Contextual/narrower/weak directional findings cannot manufacture conflict.
    # Preserve uncertain relations conservatively; never turn an imprecise null
    # into a contrary vote or promote a numerically ineligible finding.
    design_blocked = tuple(
        r.statement_id
        for r in relations
        if r.relation in {"supports_claim", "contradicts_claim"}
        and r.materiality == "decisive"
        and r.statement_id in findings
        and "mismatch" not in findings[r.statement_id].deterministic_scopes
        and not {"reverse", "weaker_than_claim"}
        & set(findings[r.statement_id].deterministic_relations)
        and not eligible(data, findings[r.statement_id])
    )
    guarded = tuple(
        r.model_copy(update={"relation": ClaimRelation.INSUFFICIENT})
        if r.relation in {"supports_claim", "contradicts_claim"}
        and (
            r.materiality != "decisive"
            or r.statement_id in design_blocked
            or r.scope not in {"aligned", "compatible_but_narrower"}
            or (
                r.statement_id in findings
                and (
                    "mismatch" in findings[r.statement_id].deterministic_scopes
                    or "reverse" in findings[r.statement_id].deterministic_relations
                    or (
                        data.base.claim_type in CAUSAL_TYPES
                        and set(findings[r.statement_id].deterministic_relations)
                        == {"weaker_than_claim"}
                    )
                )
            )
        )
        else r
        for r in relations
    )
    base = data.base.model_copy(
        update={
            "relations": guarded,
            "based_on_statement_ids": tuple(findings),
        }
    )
    trials = {
        label: qualify_conclusion(base.model_copy(update={"proposed_label": label}))
        for label in JudgeLabel
    }
    blockers = {
        R.RISK_CLASS_INVALID,
        R.FATAL_EVIDENCE_DEFECT,
        R.REQUIRED_FINDING_UNAVAILABLE,
        R.UNRESOLVED_REQUIRED_QUANTITY,
        R.RELATION_SET_INVALID,
        R.INTEGRITY_NOT_ESTABLISHED,
    }
    failure = next((o for o in trials.values() if set(o.reason_codes) & blockers), None)
    if failure is not None:
        return EvidencePositionAudit(
            version=LEGACY_VERSION,
            input=data,
            output=failure,
            validated_evidence_position=None,
            guarded_relations=guarded,
            design_materiality_statement_ids=tuple(promoted),
        )
    position = next(
        (
            label
            for label in (JudgeLabel.SUPPORTED, JudgeLabel.CONTRADICTED)
            if trials[label].status == Status.JUSTIFIED
        ),
        JudgeLabel.NOT_ENOUGH_EVIDENCE,
    )
    output = trials[position]
    if position == JudgeLabel.NOT_ENOUGH_EVIDENCE:
        reasons = output.reason_codes
        if (
            design_blocked
            and data.base.claim_type in CAUSAL_TYPES
            and not any(r.relation in {"supports_claim", "contradicts_claim"} for r in guarded)
        ):
            reasons = (R.CAUSAL_DESIGN_INSUFFICIENT,)
        if any(r.relation == "uncertain" or r.materiality == "uncertain" for r in guarded):
            reasons = (R.MATERIAL_RELATION_UNCERTAIN,)
        if R.CAUSAL_DESIGN_INSUFFICIENT in reasons:
            # This code means an eligible material direction failed the design
            # gate, never merely that a model assigned too little strength.
            directional = [
                r
                for r in guarded
                if r.relation in {"supports_claim", "contradicts_claim"}
                and r.materiality == "decisive"
            ]
            if not design_blocked and (
                not directional
                or any(eligible(data, findings[r.statement_id]) for r in directional)
            ):
                reasons = (R.ONLY_INSUFFICIENT_OR_CONTEXT,)
        output = output.model_copy(update={"status": Status.JUSTIFIED, "reason_codes": reasons})
    return EvidencePositionAudit(
        version=LEGACY_VERSION,
        input=data,
        output=output,
        validated_evidence_position=position,
        guarded_relations=guarded,
        design_materiality_statement_ids=tuple(promoted),
    )


def derive_position(data: AxesQualifierInput, *, version: str = VERSION) -> EvidencePositionAudit:
    """Versioned qualification projection; original facts/axes stay in the audit."""
    if version == LEGACY_VERSION:
        return _derive_position10(data)
    if version not in VERSIONS:
        raise ValueError("Unsupported evidence position version")
    from app.validation.relationship_guards import guarded_axes

    assessments, guards = (guarded_axes(data, legacy=version == SOURCE_GUARD_VERSION,
                                       scope_polarity=version in {SCOPE_POLARITY_VERSION,
                                                                 LABORATORY_VERSION,
                                 CLAIM_TYPE_VERSION, VERSION})
                          if version in {SOURCE_GUARD_VERSION, ENDPOINT_GUARD_VERSION,
                                         SCOPE_POLARITY_VERSION, LABORATORY_VERSION,
                                 CLAIM_TYPE_VERSION, VERSION}
                          else (data.assessments, {}))
    axes = {axis.statement_id: axis for axis in assessments}
    overrides = {}
    ignored = []
    findings = []
    for finding in data.base.findings:
        axis = axes.get(finding.statement_id)
        facts = finding.evidence_design_facts
        aligned = axis is not None and axis.scope == "aligned"
        direct = (
            aligned
            and axis is not None
            and axis.role in {"direct", "synthesis"}
            and axis.finding_basis in {"direct_result", "causal_assessment"}
            and axis.strength in {"decisive", "strong", "supporting"}
            and "mismatch" not in finding.deterministic_scopes
            and not {"reverse", "weaker_than_claim"} & set(finding.deterministic_relations)
        )
        # Retrieval role describes a whole document. An attributed, aligned trial
        # synthesis result can be direct evidence for a particular finding.
        projected = tuple(
            fact.model_copy(
                update={
                    "role": "direct",
                    **(
                        {"analysis_design": "causal_evidence_synthesis"}
                        if fact.completed_randomized_result_synthesis is True
                        else {}
                    ),
                }
            )
            if direct
            and (
                fact.role == "contextual"
                and fact.synthesis_randomized_trials is True
                or fact.completed_randomized_result_synthesis is True
                or (version in {SCOPE_POLARITY_VERSION, LABORATORY_VERSION,
                                 CLAIM_TYPE_VERSION, VERSION}
                    and fact.experimental_assignment_text is not None)
                or (version in {CLAIM_TYPE_VERSION, VERSION}
                    and fact.causal_assessment_text is not None
                    and data.base.question_category in {
                        "etiologic_exposure_causality", "disease_transmission"}
                    and design_eligible(data.base.question_category,
                        fact.model_copy(update={"role": "direct"}),
                        policy=data.base.evidence_policy))
            )
            else fact
            for fact in facts
        )
        if projected != facts:
            overrides[finding.statement_id] = projected
        # Unknown currency of an unused context page cannot veto independent
        # verified evidence. Retracted/concern sources still fail everywhere.
        context = (bool(projected) and all(fact.role != "direct" for fact in projected)) or (
            axis is not None and axis.role in {"background", "contextual"}
        )
        statuses = finding.integrity_statuses
        if context and "unknown" in statuses:
            statuses = tuple(status for status in statuses if status != "unknown")
            ignored.append(finding.statement_id)
        findings.append(
            finding.model_copy(
                update={"evidence_design_facts": projected, "integrity_statuses": statuses}
            )
        )
    projected_input = data.model_copy(
        update={
            "assessments": assessments,
            "base": data.base.model_copy(update={"findings": tuple(findings)}),
        }
    )
    relation_overrides = {}
    if version == VERSION and data.base.question_category in {
        "etiologic_exposure_causality", "disease_transmission",
    }:
        for i, finding in enumerate(findings):
            axis = axes.get(finding.statement_id)
            if (axis is not None and axis.scope == "aligned"
                    and axis.role in {"direct", "synthesis"}
                    and axis.strength in {"strong", "decisive"}
                    and axis.finding_basis == "causal_assessment"
                    and "weaker_than_claim" in finding.deterministic_relations
                    and "reverse" not in finding.deterministic_relations
                    and "mismatch" not in finding.deterministic_scopes
                    and any(f.causal_assessment_text for f in finding.evidence_design_facts)
                    and eligible(projected_input, finding)):
                # A source's explicit validated causal conclusion plus eligible
                # convergence is stronger than its incidental association wording.
                # A single association or explicit causal disclaimer cannot pass.
                relations = tuple("aligned" if r == "weaker_than_claim" else r
                                  for r in finding.deterministic_relations)
                findings[i] = finding.model_copy(update={"deterministic_relations": relations})
                relation_overrides[finding.statement_id] = relations
                guards[finding.statement_id] = (*guards.get(finding.statement_id, ()),
                                                 "VALIDATED_CAUSAL_ASSESSMENT_RELATION")
        projected_input = projected_input.model_copy(update={"base":
            projected_input.base.model_copy(update={"findings": tuple(findings)})})
    result = _derive_position10(
        projected_input,
        objective_design=version in {TRIAL_METHOD_VERSION, SOURCE_GUARD_VERSION,
                                    ENDPOINT_GUARD_VERSION, SCOPE_POLARITY_VERSION,
                                    LABORATORY_VERSION,
                                 CLAIM_TYPE_VERSION, VERSION},
    )
    return result.model_copy(
        update={
            "version": version,
            "input": data,
            "finding_design_overrides": overrides,
            "finding_relation_overrides": relation_overrides,
            "semantic_guard_overrides": guards,
            "ignored_context_integrity_statement_ids": tuple(ignored),
        }
    )
