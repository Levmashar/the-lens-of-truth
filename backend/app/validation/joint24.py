"""V2.4 transport repair retaining the independent, non-voting joint checker."""

import asyncio
import json
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from app.judging.compact23 import deduplicated_wire_snapshot
from app.judging.compact24 import frozen_response_matches24
from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.prompt import prepare_judge_input
from app.retrieval.models import EvidencePack
from app.retrieval.sufficiency import question_category
from app.validation.axes import (
    QUALIFIER_VERSION,
    AxesQualificationAudit,
    AxesQualifierInput,
    gradient_compatible,
    gradient_kind,
    null_precision_reason,
    qualify_axes,
)
from app.validation.axes import (
    VERSION as AXES_VERSION,
)
from app.validation.joint23 import (
    INSTRUCTIONS as INSTRUCTIONS23,
)
from app.validation.joint23 import (
    JointResponse23,
    JointValidator23,
    normalize_frozen_references,
    qualitative_statements,
)
from app.validation.models import (
    ConclusionJustification,
    ConclusionJustificationStatus,
    IssueCode,
    JudgeValidationResult,
    JudgeValidationRun,
    NumericAlignment,
    StatementAttribution,
    StatementAttributionStatus,
    ValidationIssue,
    ValidationStatus,
)
from app.validation.numeric24 import VERSION as NUMERIC_VERSION
from app.validation.numeric24 import numeric_findings24, numeric_issues24
from app.validation.numeric_effects import NumericFinding, magnitude_alignment
from app.validation.position import VERSION as POSITION_VERSION
from app.validation.position import EvidencePositionAudit
from app.validation.qualification import ConclusionQualifierInput
from app.validation.relation_flow import build_relation_payload
from app.validation.relations import canonical_hash
from app.validation.semantic import PreparedSemanticInput
from app.validation.v2 import validate_v2

VERSION = "joint-evidence-axes-2.5-structured-numeric-2026-10-04"
SCOPE_PROMPT_VERSION = "joint-evidence-axes-2.6-scope-polarity-2026-10-06"
DETERMINISTIC_VERSION = f"source-unit+{NUMERIC_VERSION}+axes-1.0"
INSTRUCTIONS = (
    INSTRUCTIONS23.replace(
        "The raw\ndescription/numeric_details are separately retained and numerically checked.",
        "The original description is retained for semantic audit. Numeric source fidelity\n"
        "is checked through frozen source_quantity_ids, never by parsing generated prose.",
    )
    + """
V2.4 NUMERIC TRANSPORT: Each candidate carries source_quantity_ids and the selected
backend-owned source_quantities, also frozen in source_quantity_catalog. They are
the only source numeric premises. Check that the finding's meaning, direction,
population/exposure/comparator/endpoint/time and strength follow from the cited
units and quantities. A verified reference alone does NOT establish an attribution
or semantic qualification. No quantity refs may still establish qualitative
direction, but cannot establish the submitted exact magnitude. Do not invent
conversions from ambiguous times-higher or substitute PAF/OR/HR for RR.
numeric_independent concerns the proposition's semantic dependence on exact
quantities; keep the existing independent direction/scope/strength/role and basis
axes. The backend compares source quantities to the submitted numeric_effect only
AFTER your semantic scope result. Conclusion prose is not a new numeric source.
"""
)

SCOPE_INSTRUCTIONS = INSTRUCTIONS + """
EXACT QUESTION AND SETTING: Compare directions against the original_claim,
not a familiar positive version of it. 'X lowers Y' and 'X increases Y' have
opposite polarity even when they retrieve identical evidence. Preserve negation.
A claim that X CAN treat Y asserts a demonstrated capability, not success in
every population or with every member of a drug class. A demonstrated compatible
subpopulation can support that capability; it cannot establish a universal,
permanent, complete or explicitly population-specific effect. Keep wrong
endpoints and active-comparator limitations distinct from population limits.
Experimental cell-line claims concern cellular endpoints under that stated
setting, not disease incidence in people. Direct controlled laboratory results
can be direct evidence for a laboratory endpoint; they remain mechanistic/context
for a clinical disease-onset claim. Do not require human randomized trials for
an explicitly cellular question. Mechanistic rationale alone is still context.
Clinical onset includes carcinogenesis/development, not just the word 'risk'.
Treatment/diagnosis elsewhere in a source does not change an attributed causal
onset finding into a treatment endpoint. A narrative causal assertion is not
automatically a systematic synthesis or an eligible causal design.
"""


CAUSAL_PROMPT_VERSION = "joint-evidence-axes-2.7-claim-type-causality-2026-10-06"
CAUSAL_INSTRUCTIONS = SCOPE_INSTRUCTIONS + """
CLAIM-TYPE CAUSAL EVIDENCE: Etiologic exposure and disease-transmission questions
do not require randomized human exposure. Explicit reviewed causal assessments
or route-inclusion/exclusion guidance from an approved source can be direct
causal_assessment evidence when it actually establishes the named exposure,
endpoint and scope. Cohort/case-control epidemiology with temporal and mechanistic
convergence can establish etiology; association alone, hypothetical mechanism,
an ordinary narrative opinion and surveys of people's beliefs cannot.
For transmission, explicit exclusion of a route is different from omission of
that route or an imprecise null. Preserve all negations and list introductions.
Publisher authority alone is not evidence. Report the strength and relevance of
the actual cited assessment, not just its publication container.
Treatment, preventive interventions and manipulation of a risk factor still
require intervention-appropriate evidence. Do not transfer natural exposure
eligibility to a treatment or infer clinical prevention from cell experiments.
"""


def joint_prompt_version(judge: JudgeRun, position_version: str = POSITION_VERSION) -> str:
    if (judge.decision is not None and judge.decision.schema_version == "2.5"
            and position_version in {"validated-evidence-position-1.7",
                                    "validated-evidence-position-1.8"}):
        return CAUSAL_PROMPT_VERSION
    return SCOPE_PROMPT_VERSION if (judge.decision is not None
        and judge.decision.schema_version == "2.5"
        and position_version in {"validated-evidence-position-1.5",
                                 "validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"}) else VERSION


def prepare_joint24(
    judge: JudgeRun,
    pack: EvidencePack,
    validation_id: str,
    *,
    position_version: str = POSITION_VERSION,
) -> PreparedSemanticInput:
    assert isinstance(judge.decision, JudgeDecisionV2)
    if judge.decision.schema_version not in {"2.4", "2.5"}:
        raise ValueError("Structured check requires V2.4")
    base = prepare_judge_input(
        judge.evidence_pack_id, pack, version=f"judge-input-{judge.decision.schema_version}"
    )
    from app.judging.source_quantities import catalog_items

    catalog = catalog_items(base.input_snapshot_json)
    payload, _ = build_relation_payload(
        pack,
        qualitative_statements(judge),
        magnitude_version="structured-quantity-2.4",
        finding_design=judge.decision.schema_version == "2.5"
        and position_version != "validated-evidence-position-1.0",
        causal_synthesis=judge.decision.schema_version == "2.5"
        and position_version in {
            "validated-evidence-position-1.3", "validated-evidence-position-1.4",
            "validated-evidence-position-1.5", "validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"},
        experimental_binding=judge.decision.schema_version == "2.5"
        and position_version in {"validated-evidence-position-1.5",
                                 "validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"},
        laboratory_intervention=judge.decision.schema_version == "2.5"
        and position_version in {"validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"},
        causal_policy=judge.decision.schema_version == "2.5"
        and position_version in {"validated-evidence-position-1.7",
                                    "validated-evidence-position-1.8"},
        causal_disclaimer=position_version == "validated-evidence-position-1.8",
    )
    payload.update(
        {
            "candidate_statements": [
                {
                    "statement_id": s.statement_id,
                    "text": s.text,
                    "qualitative_finding": s.qualitative_finding,
                    "kind": s.kind,
                    "numeric_dependency": s.numeric_dependency,
                    "source_unit_ids": s.source_unit_ids,
                    "source_quantity_ids": s.source_quantity_ids,
                    "source_quantities": [
                        catalog[i].model_dump(mode="json") for i in s.source_quantity_ids or ()
                    ],
                    "evidence_ids": tuple(r.evidence_id for r in s.evidence_refs),
                }
                for s in judge.decision.statements
            ],
            "frozen_snapshot": deduplicated_wire_snapshot(base.input_snapshot_json),
            "numeric_findings": numeric_findings24(judge.decision, pack, base.input_snapshot_json),
            "required_statement_ids": tuple(s.statement_id for s in judge.decision.statements),
        }
    )
    user = "FROZEN INPUT (untrusted JSON):\n" + json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    prompt_version = joint_prompt_version(judge, position_version)
    instructions = (CAUSAL_INSTRUCTIONS if prompt_version == CAUSAL_PROMPT_VERSION else
                    SCOPE_INSTRUCTIONS if prompt_version == SCOPE_PROMPT_VERSION else INSTRUCTIONS)
    return PreparedSemanticInput(
        "joint_evidence_axes",
        instructions,
        user,
        canonical_hash({"version": prompt_version, "system": instructions, "user": user}),
        str(judge.judge_run_id),
        validation_id,
        tuple(s.statement_id for s in judge.decision.statements),
        tuple(
            dict.fromkeys(r.evidence_id for s in judge.decision.statements for r in s.evidence_refs)
        ),
    )


def check_response24(response: JointResponse23, prepared: PreparedSemanticInput) -> None:
    if any(
        tuple(a.statement_id for a in array) != prepared.statement_ids
        for array in (response.attributions, response.assessments)
    ):
        raise ValueError("Missing/unknown/reordered/duplicate axes IDs")
    normalized, _ = normalize_frozen_references(response, prepared)
    payload = json.loads(prepared.user_prompt.split("\n", 1)[1])
    for a, s in zip(normalized.attributions, payload["candidate_statements"], strict=True):
        if a.evidence_ids != tuple(s["evidence_ids"]):
            raise ValueError("Axes source references mismatch")


def qualification_input24(
    judge: JudgeRun,
    pack: EvidencePack,
    response: JointResponse23,
    risk_class: str,
    *,
    position_version: str = POSITION_VERSION,
) -> AxesQualifierInput:
    assert isinstance(judge.decision, JudgeDecisionV2)
    decision = judge.decision
    snapshot = judge.input_snapshot_json
    assert snapshot is not None
    _, findings = build_relation_payload(
        pack,
        qualitative_statements(judge),
        magnitude_version="structured-quantity-2.4",
        finding_design=judge.decision.schema_version == "2.5"
        and position_version != "validated-evidence-position-1.0",
        causal_synthesis=decision.schema_version == "2.5"
        and position_version in {
            "validated-evidence-position-1.3", "validated-evidence-position-1.4",
            "validated-evidence-position-1.5", "validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"},
        experimental_binding=decision.schema_version == "2.5"
        and position_version in {"validated-evidence-position-1.5",
                                 "validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"},
        laboratory_intervention=judge.decision.schema_version == "2.5"
        and position_version in {"validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"},
        causal_policy=judge.decision.schema_version == "2.5"
        and position_version in {"validated-evidence-position-1.7",
                                    "validated-evidence-position-1.8"},
        causal_disclaimer=position_version == "validated-evidence-position-1.8",
    )
    inputs = AxesQualifierInput(
        base=ConclusionQualifierInput(
            proposed_label=decision.label,
            claim_type=pack.claim_snapshot.claim_type,
            risk_class=risk_class,
            findings=findings,
            relations=(),
            based_on_statement_ids=decision.conclusion.based_on_statement_ids,
            defects=numeric_issues24(decision, snapshot),
            required_findings_available=all(
                a.status == StatementAttributionStatus.SUPPORTED_BY_SOURCES
                for a in response.attributions
            )
            and not response.missing_material_evidence,
            evidence_policy=("question-evidence-2.1" if position_version ==
                             "validated-evidence-position-1.8" and decision.schema_version == "2.5"
                             else "question-evidence-2.0" if position_version ==
                             "validated-evidence-position-1.7" and decision.schema_version == "2.5"
                             else "question-evidence-1.0")
            if pack.evidence_pack_version == "1.5"
            else "legacy-1.0",
            question_category=question_category(pack.claim_snapshot,
                experimental_setting=position_version in {"validated-evidence-position-1.5",
                                                         "validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"},
                causal_policy=decision.schema_version == "2.5"
                and position_version in {"validated-evidence-position-1.7",
                                    "validated-evidence-position-1.8"})
            if pack.evidence_pack_version == "1.5"
            else "other",
        ),
        assessments=response.assessments,
        comparator=pack.claim_snapshot.pico.comparator if pack.claim_snapshot.pico else None,
        exact_claim=pack.claim_snapshot.standalone_text,
        source_texts={
            s.statement_id: tuple(r.quote for r in s.evidence_refs) for s in decision.statements
        },
    )
    if (position_version in {"validated-evidence-position-1.3", "validated-evidence-position-1.4",
                            "validated-evidence-position-1.5", "validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"}
            and decision.schema_version == "2.5"):
        from app.validation.relationship_guards import relationship_context

        inputs = inputs.model_copy(
            update={"relationship_context": relationship_context(judge, pack,
                scope_polarity=position_version in {"validated-evidence-position-1.5",
                                                  "validated-evidence-position-1.6",
                                 "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8"})}
        )
    numeric = numeric_findings24(
        decision,
        pack,
        snapshot,
        assessments={
            a.statement_id: (a.scope, a.scope_basis, gradient_compatible(inputs, a))
            for a in response.assessments
        },
    )
    eligibility = {}
    adjusted = []
    claim = pack.claim_snapshot.pico.numeric_effect if pack.claim_snapshot.pico else None
    for finding in findings:
        items = tuple(
            NumericFinding.model_validate(n)
            for n in numeric
            if n["target_id"] == finding.statement_id
        )
        if claim is not None:
            eligibility[finding.statement_id] = bool(items) and all(
                item.numeric_effect in {"supports_magnitude", "opposes_magnitude"} for item in items
            )
            alignment = magnitude_alignment(items) if items else NumericAlignment.UNCERTAIN
        else:
            alignment = NumericAlignment.NOT_APPLICABLE
        adjusted.append(finding.model_copy(update={"claim_magnitude_alignment": alignment}))
    return inputs.model_copy(
        update={
            "base": inputs.base.model_copy(update={"findings": tuple(adjusted)}),
            "magnitude_eligible": eligibility,
        }
    )


def finish_joint24(
    preflight: JudgeValidationRun,
    judge: JudgeRun,
    pack: EvidencePack,
    response: JointResponse23,
    prepared: PreparedSemanticInput,
    *,
    risk_class: str,
    provider: str,
    model: str,
    position_version: str = POSITION_VERSION,
) -> JudgeValidationRun:
    assert isinstance(judge.decision, JudgeDecisionV2)
    assert judge.input_snapshot_json is not None
    check_response24(response, prepared)
    original = response
    response, conversions = normalize_frozen_references(response, prepared)
    issues = list(numeric_issues24(judge.decision, judge.input_snapshot_json))
    provenance = {
        "provider": provider,
        "model": model,
        "prompt_version": joint_prompt_version(judge, position_version),
        "prompt_hash": prepared.prompt_hash,
    }
    attributions = []
    for a in response.attributions:
        if a.status in {
            StatementAttributionStatus.NOT_ESTABLISHED_BY_SOURCES,
            StatementAttributionStatus.CONTRADICTED_BY_SOURCES,
        }:
            issues.append(
                ValidationIssue(
                    target_type="judge_statement",
                    target_id=a.statement_id,
                    evidence_refs=a.evidence_ids,
                    issue_code=IssueCode.STATEMENT_ATTRIBUTION_FAILED,
                    severity="fatal",
                )
            )
        attributions.append(
            StatementAttribution(
                statement_id=a.statement_id,
                evidence_ids=a.evidence_ids,
                status=a.status,
                scope_match=a.scope_match,
                reason=a.reason,
                issues=tuple(i for i in issues if i.target_id == a.statement_id),
                validator_provenance=provenance,
            )
        )
    inputs = qualification_input24(
        judge, pack, response, risk_class, position_version=position_version
    )
    qualification: AxesQualificationAudit | EvidencePositionAudit
    if judge.decision.schema_version == "2.5":
        from app.validation.position import derive_position

        qualification = derive_position(inputs, version=position_version)
    else:
        qualification = AxesQualificationAudit(
            version=QUALIFIER_VERSION, input=inputs, output=qualify_axes(inputs)
        )
    fatal = tuple(dict.fromkeys(i.issue_code for i in issues if i.severity == "fatal"))
    status = (
        ValidationStatus.INVALID
        if fatal
        else ValidationStatus.VALIDATED
        if qualification.output.status == ConclusionJustificationStatus.JUSTIFIED
        else ValidationStatus.UNABLE_TO_VALIDATE
    )
    exact = json.loads(prepared.user_prompt.split("\n", 1)[1])
    conclusion = ConclusionJustification(
        status=qualification.output.status,
        based_on_statement_ids=judge.decision.conclusion.based_on_statement_ids,
        evidence_ids=tuple(
            dict.fromkeys(
                r.evidence_id
                for s in judge.decision.statements
                if s.statement_id in judge.decision.conclusion.based_on_statement_ids
                for r in s.evidence_refs
            )
        ),
        reason="; ".join(qualification.output.reason_codes),
        validator_provenance=provenance,
    )
    result = preflight.result.model_copy(
        update={
            "validation_status": status,
            "statement_attributions": tuple(attributions),
            **(
                {"validated_evidence_position": qualification.validated_evidence_position}
                if isinstance(qualification, EvidencePositionAudit)
                else {}
            ),
            "conclusion_justification": conclusion,
            "targeted_issues": tuple(issues),
            "fatal_issue_codes": fatal,
            "warnings": (),
            "relation_validation": {
                "version": AXES_VERSION,
                **provenance,
                "input_json": exact,
                "input_hash": canonical_hash(exact),
                "joint_response": original.model_dump(mode="json"),
                "id_normalizations": conversions,
                "finding_diagnostics": {
                    a.statement_id: {
                        "null_precision_reason": null_precision_reason(
                            inputs.source_texts.get(a.statement_id, ())
                        )
                        if a.finding_basis in {"precise_null", "imprecise_null"}
                        else None,
                        "gradient_kind": gradient_kind(inputs.source_texts.get(a.statement_id, ())),
                        "raw_finding_basis": a.finding_basis,
                        "raw_scope_basis": a.scope_basis,
                    }
                    for a in response.assessments
                },
            },
            "conclusion_qualification": qualification.model_dump(mode="json"),
            "numeric_findings": numeric_findings24(
                judge.decision,
                pack,
                judge.input_snapshot_json,
                assessments={
                    a.statement_id: (a.scope, a.scope_basis, gradient_compatible(inputs, a))
                    for a in response.assessments
                },
            ),
            "numeric_occurrences": None,
            "semantic_validation": None,
        }
    )
    return preflight.model_copy(
        update={
            "status": status,
            "result": result,
            "attempt_count": 1,
            "entailment_provider": provider,
            "entailment_model": model,
            "prompt_version": joint_prompt_version(judge, position_version),
            "prompt_hash": prepared.prompt_hash,
            "deterministic_validator_version": deterministic_version(
                judge, position_version=position_version
            ),
            "error_category": "missing_material_evidence"
            if response.missing_material_evidence
            else None,
        }
    )


async def validate_joint24(
    judge: JudgeRun,
    pack: EvidencePack,
    validator: JointValidator23 | None,
    *,
    risk_class: str = "standard",
    timeout_seconds: float = 45.0,
) -> JudgeValidationRun:
    started = monotonic()
    assert isinstance(judge.decision, JudgeDecisionV2)
    if judge.decision.schema_version not in {"2.4", "2.5"}:
        raise ValueError("Structured validation requires V2.4")
    try:
        preflight = await validate_v2(judge, pack, None, risk_class=risk_class)
    except ValueError:
        # A corrupt frozen Pack is an operational defect, never semantic NEI.
        now = datetime.now(UTC)
        preflight = JudgeValidationRun(
            id=uuid4(),
            judge_run_id=judge.judge_run_id,
            evidence_pack_id=judge.evidence_pack_id,
            evidence_pack_hash=judge.evidence_pack_hash,
            validation_version=f"judge-validation-{judge.decision.schema_version}",
            deterministic_validator_version=deterministic_version(judge),
            entailment_provider=None,
            entailment_model=None,
            prompt_version=None,
            prompt_hash=None,
            started_at=now,
            completed_at=now,
            status=ValidationStatus.INVALID,
            result=JudgeValidationResult(
                judge_run_id=judge.judge_run_id,
                evidence_pack_id=judge.evidence_pack_id,
                evidence_pack_hash=judge.evidence_pack_hash,
                judge_label=judge.decision.label,
                citation_validations=(),
                opposing_citation_validations=(),
                validation_status=ValidationStatus.INVALID,
                validation_version=f"judge-validation-{judge.decision.schema_version}",
                fatal_issue_codes=(IssueCode.PACK_HASH_MISMATCH,),
                warnings=(),
            ),
            error_category="reference_preflight_failure",
            latency_ms=0,
            attempt_count=0,
        )
    issues = numeric_issues24(judge.decision, judge.input_snapshot_json or {})
    identity_valid = frozen_response_matches24(judge, pack)
    if judge.decision.schema_version == "2.5":
        from app.judging.compact25 import frozen_response_matches25

        identity_valid = frozen_response_matches25(judge, pack)
    if not identity_valid:
        issues += (
            ValidationIssue(
                target_type="judge_statement",
                target_id="conclusion",
                evidence_refs=(),
                issue_code=IssueCode.PACK_HASH_MISMATCH,
                severity="fatal",
            ),
        )
    preflight = preflight.model_copy(
        update={
            "deterministic_validator_version": deterministic_version(judge),
            "result": preflight.result.model_copy(
                update={
                    "numeric_findings": numeric_findings24(
                        judge.decision, pack, judge.input_snapshot_json or {}
                    )
                    if identity_valid
                    else (),
                    "numeric_occurrences": None,
                }
            ),
        }
    )
    if preflight.result.fatal_issue_codes or issues:
        blockers = (*preflight.result.targeted_issues, *issues)
        skip = "skipped_due_to_reference_preflight"
        provenance = {
            "state": skip,
            "provider": validator.provider if validator else "",
            "model": validator.model if validator else "",
        }
        result = preflight.result.model_copy(
            update={
                "validation_status": ValidationStatus.INVALID,
                "targeted_issues": blockers,
                "fatal_issue_codes": tuple(
                    dict.fromkeys(i.issue_code for i in blockers if i.severity == "fatal")
                ),
                "semantic_validation": {
                    **provenance,
                    "blocking_issue_ids": [
                        f"{i.target_id}:{i.issue_code.value}:{index}"
                        for index, i in enumerate(blockers)
                    ],
                },
                "statement_attributions": tuple(
                    a.model_copy(
                        update={
                            "reason": skip,
                            "validator_provenance": provenance,
                        }
                    )
                    for a in preflight.result.statement_attributions
                ),
                "conclusion_justification": preflight.result.conclusion_justification.model_copy(
                    update={"reason": skip, "validator_provenance": provenance}
                )
                if preflight.result.conclusion_justification
                else None,
            }
        )
        return preflight.model_copy(
            update={
                "status": ValidationStatus.INVALID,
                "result": result,
                "error_category": "reference_preflight_failure",
            }
        )
    if validator is None:
        return preflight
    prepared = prepare_joint24(judge, pack, str(preflight.id))
    response: JointResponse23 | None = None
    try:
        async with asyncio.timeout(timeout_seconds):
            response = await validator.assess_joint23(prepared)
        checked = finish_joint24(
            preflight,
            judge,
            pack,
            response,
            prepared,
            risk_class=risk_class,
            provider=validator.provider,
            model=validator.model,
        )
    except Exception as exc:
        error = (
            getattr(exc, "category", "source_id_contract_error")
            if isinstance(exc, ValueError)
            else "joint_axes_timeout"
            if isinstance(exc, TimeoutError)
            else "joint_axes_validator_unavailable"
        )
        exact = json.loads(prepared.user_prompt.split("\n", 1)[1])
        checked = preflight.model_copy(
            update={
                "attempt_count": 1,
                "error_category": error,
                "prompt_version": joint_prompt_version(judge),
                "prompt_hash": prepared.prompt_hash,
                "entailment_provider": validator.provider,
                "entailment_model": validator.model,
                "result": preflight.result.model_copy(
                    update={
                        "relation_validation": {
                            "version": AXES_VERSION,
                            "prompt_version": joint_prompt_version(judge),
                            "prompt_hash": prepared.prompt_hash,
                            "input_json": exact,
                            "input_hash": canonical_hash(exact),
                            "error_category": error,
                            "provider": validator.provider,
                            "model": validator.model,
                            "exception_type": type(exc.__cause__ or exc).__name__,
                            "exception_message": str(exc),
                            "failed_response_content": getattr(exc, "response_content", None)
                            or (response.model_dump_json() if response is not None else None),
                        }
                    }
                ),
            }
        )
    return checked.model_copy(
        update={
            "completed_at": datetime.now(UTC),
            "latency_ms": round((monotonic() - started) * 1000),
        }
    )


def deterministic_version(judge: JudgeRun, *, position_version: str = POSITION_VERSION) -> str:
    return (
        DETERMINISTIC_VERSION + "+" + position_version
        if isinstance(judge.decision, JudgeDecisionV2) and judge.decision.schema_version == "2.5"
        else DETERMINISTIC_VERSION
    )
