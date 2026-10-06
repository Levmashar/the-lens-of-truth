"""Pure Phase 6B aggregation over explicitly named, frozen audit inputs."""

import hashlib
import json
from dataclasses import dataclass

from app.judging.models import JudgeDecisionV2, JudgeLabel, JudgeRun
from app.judging.prompt import input_snapshot_hash, prepare_judge_input
from app.pipeline.claim_types import ClaimType
from app.retrieval.evidence_pack import canonical_pack_bytes
from app.retrieval.sufficiency import design_eligible, design_fact, question_category
from app.validation.models import (
    ConclusionJustificationStatus,
    EntailmentStatus,
    IssueCode,
    JudgeValidationRun,
    NumericAlignment,
    RelationAlignment,
    ScopeAlignment,
    StatementAttributionStatus,
    ValidationStatus,
)
from app.validation.qualification import (
    CAUSAL_DESIGNS,
    ConclusionQualificationAudit,
    qualify_conclusion,
)
from app.validation.relation_flow import build_relation_payload
from app.validation.relations import RelationValidationAudit, canonical_hash, prepare_relation_input
from app.verdict.models import (
    AggregationContext,
    AggregationInput,
    AggregationMode,
    JudgeQualification,
    LensVerdict,
    ReasonCode,
    VerdictResult,
)
from app.verdict.policy import POLICY_V1, POLICY_V2, POLICY_V3, POLICY_V4, VerdictPolicyV1


def _unique_codes(codes: list[ReasonCode]) -> tuple[ReasonCode, ...]:
    return tuple(dict.fromkeys(codes))


def _has_direct_causal_design(
    context: AggregationContext,
    qualified: list[JudgeQualification],
) -> bool:
    """Require a conclusion-cited trial/synthesis for a decisive causal claim.

    Study-design metadata is only a conservative sufficiency gate, never a
    support/contradiction vote. Unknown/observational design cannot by itself
    establish or rule out an effect, even if an association points the other way.
    """

    pack = context.pack
    if pack is None:
        return False
    judges = {item.judge_run_id: item for item in context.judges}
    passages = {item.evidence_id: item for item in pack.passages}
    documents = {item.document_id: item for item in pack.documents}
    stronger = CAUSAL_DESIGNS
    for item in qualified:
        judge = judges[item.judge_run_id]
        decision = judge.decision
        if not isinstance(decision, JudgeDecisionV2):
            continue
        relied_on = set(decision.conclusion.based_on_statement_ids)
        if decision.schema_version == "2.5":
            from app.validation.position import EvidencePositionAudit

            validation = next(
                v for v in context.validations if v.judge_run_id == judge.judge_run_id
            )
            position = EvidencePositionAudit.model_validate(
                validation.result.conclusion_qualification
            )
            relied_on = set(position.output.decisive_statement_ids)
            if position.version in {
                "validated-evidence-position-1.1",
                "validated-evidence-position-1.2",
                "validated-evidence-position-1.3",
                "validated-evidence-position-1.4",
                "validated-evidence-position-1.5",
                "validated-evidence-position-1.6",
                "validated-evidence-position-1.7",
                                 "validated-evidence-position-1.8",
            }:
                facts = {
                    f.statement_id: f.evidence_design_facts for f in position.input.base.findings
                }
                facts.update(position.finding_design_overrides)
                if any(
                    design_eligible(position.input.base.question_category, fact,
                                    policy=position.input.base.evidence_policy,
                                    peers=tuple(f for identifier in relied_on
                                                for f in facts.get(identifier, ())))
                    for identifier in relied_on
                    for fact in facts.get(identifier, ())
                ):
                    return True
                continue
        for statement in decision.statements:
            if statement.statement_id not in relied_on:
                continue
            for ref in statement.evidence_refs:
                passage = passages.get(ref.evidence_id)
                document = documents.get(passage.passage.document_id) if passage else None
                if pack.evidence_pack_version == "1.5":
                    if document and design_eligible(question_category(pack.claim_snapshot),
                                                    design_fact(document)):
                        return True
                elif document is not None and document.study_design in stronger:
                    return True
    return False


def _pack_failure(
    request: AggregationInput, context: AggregationContext, policy: VerdictPolicyV1,
) -> ReasonCode | None:
    pack = context.pack
    if pack is None or context.stored_pack_hash is None:
        return ReasonCode.PACK_UNAVAILABLE
    if pack.evidence_pack_version not in {policy.pack_version, "1.4", "1.5"}:
        return ReasonCode.PACK_VERSION_UNSUPPORTED
    if pack.evidence_pack_version == "1.5" and policy.version != POLICY_V4.version:
        return ReasonCode.PACK_VERSION_UNSUPPORTED
    if (context.stored_pack_version is not None
            and context.stored_pack_version != pack.evidence_pack_version):
        return ReasonCode.AUDIT_RECORD_MISMATCH
    if (context.stored_pack_claim_id is not None
            and context.stored_pack_claim_id != request.claim_id):
        return ReasonCode.AUDIT_RECORD_MISMATCH
    actual_hash = hashlib.sha256(canonical_pack_bytes(
        pack.claim_snapshot, pack.query_plan, pack.documents, pack.passages,
        pack.selected_evidence_ids, pack_version=pack.evidence_pack_version,
    )).hexdigest()
    if (pack.snapshot_hash != actual_hash or context.stored_pack_hash != actual_hash
            or request.evidence_pack_hash != actual_hash):
        return ReasonCode.PACK_HASH_MISMATCH
    if pack.claim_id != request.claim_id or pack.claim_snapshot.claim_id != request.claim_id:
        return ReasonCode.AUDIT_RECORD_MISMATCH
    passages = {item.evidence_id: item for item in pack.passages}
    documents = {item.document_id: item for item in pack.documents}
    selected = pack.selected_evidence_ids
    if (len(passages) != len(pack.passages) or len(documents) != len(pack.documents)
            or len(set(selected)) != len(selected)):
        return ReasonCode.PACK_SELECTION_INVALID
    for evidence_id in selected:
        item = passages.get(evidence_id)
        if item is None or not item.selected_for_judging:
            return ReasonCode.PACK_SELECTION_INVALID
        document = documents.get(item.passage.document_id)
        if document is None or document.integrity.status == "retracted":
            return ReasonCode.PACK_SELECTION_INVALID
        if hashlib.sha256(item.passage.text.encode("utf-8")).hexdigest() != (
            item.passage.content_sha256
        ):
            return ReasonCode.PACK_SELECTION_INVALID
    if any(item.selected_for_judging != (item.evidence_id in selected)
           for item in pack.passages):
        return ReasonCode.PACK_SELECTION_INVALID
    return None


def _validation_failure(
    judge: JudgeRun,
    validation: JudgeValidationRun | None,
    policy: VerdictPolicyV1,
    *,
    evaluation_mode: bool,
) -> ReasonCode | None:
    if validation is None:
        return ReasonCode.VALIDATION_UNAVAILABLE
    decision = judge.decision
    result = validation.result
    if (
        decision is None
        or validation.judge_run_id != judge.judge_run_id
        or validation.evidence_pack_id != judge.evidence_pack_id
        or validation.evidence_pack_hash != judge.evidence_pack_hash
        or result.judge_run_id != judge.judge_run_id
        or result.evidence_pack_id != judge.evidence_pack_id
        or result.evidence_pack_hash != judge.evidence_pack_hash
        or result.judge_label != decision.label
        or result.validation_status != validation.status
        or result.validation_version != validation.validation_version
        or (
            validation.validation_version != policy.validation_version
            and not (
                isinstance(decision, JudgeDecisionV2)
                and decision.schema_version in {"2.1", "2.2", "2.3", "2.4", "2.5"}
                and validation.validation_version == f"judge-validation-{decision.schema_version}"
                and policy.validation_version == "judge-validation-2.0"
            )
        )
    ):
        return ReasonCode.AUDIT_RECORD_MISMATCH
    if isinstance(decision, JudgeDecisionV2):
        if decision.schema_version in {"2.4", "2.5"} and not evaluation_mode:
            return ReasonCode.VALIDATION_UNAVAILABLE
        if decision.schema_version == "2.5":
            from app.validation.position import VERSIONS, EvidencePositionAudit, derive_position

            if validation.error_category and validation.status != ValidationStatus.VALIDATED:
                return ReasonCode.VALIDATION_UNAVAILABLE
            try:
                position = EvidencePositionAudit.model_validate(result.conclusion_qualification)
                if (
                    position.version not in VERSIONS
                    or position != derive_position(position.input, version=position.version)
                    or result.validated_evidence_position != position.validated_evidence_position
                    or position.validated_evidence_position is None
                    or validation.status != ValidationStatus.VALIDATED
                    or validation.error_category
                    or result.fatal_issue_codes
                    or any(i.severity == "fatal" for i in result.targeted_issues)
                    or any(
                        a.status != StatementAttributionStatus.SUPPORTED_BY_SOURCES
                        for a in result.statement_attributions
                    )
                    or not validation.entailment_provider
                    or not validation.entailment_model
                    or not validation.prompt_hash
                    or validation.attempt_count != 1
                ):
                    return ReasonCode.VALIDATION_UNAVAILABLE
                return None
            except (ValueError, TypeError):
                return ReasonCode.AUDIT_RECORD_MISMATCH
        if policy.validation_version != "judge-validation-2.0":
            return ReasonCode.VALIDATION_UNAVAILABLE
        expected = {statement.statement_id: tuple(ref.evidence_id for ref in
                    statement.evidence_refs) for statement in decision.statements}
        actual = {item.statement_id: item.evidence_ids
                  for item in result.statement_attributions}
        conclusion = result.conclusion_justification
        if (actual != expected or conclusion is None
                or conclusion.based_on_statement_ids
                != decision.conclusion.based_on_statement_ids
                or conclusion.evidence_ids != tuple(dict.fromkeys(
                    ref.evidence_id for statement in decision.statements
                    if statement.statement_id in decision.conclusion.based_on_statement_ids
                    for ref in statement.evidence_refs
                ))):
            return ReasonCode.AUDIT_RECORD_MISMATCH
        if result.fatal_issue_codes or any(issue.severity == "fatal"
                                           for issue in result.targeted_issues):
            return ReasonCode.VALIDATION_FATAL_ISSUE
        if validation.status == ValidationStatus.INVALID:
            return ReasonCode.VALIDATION_INVALID
        if validation.status == ValidationStatus.PARTIALLY_VALIDATED:
            return ReasonCode.VALIDATION_PARTIAL
        from app.validation.joint import PROMPTS as JOINT_PROMPTS
        from app.validation.joint23 import PROMPTS as AXES_PROMPTS
        from app.validation.joint24 import VERSION as STRUCTURED_JOINT_VERSION

        joint_development = (
            evaluation_mode
            and decision.schema_version in {"2.2", "2.3", "2.4"}
            and validation.prompt_version
            in {*JOINT_PROMPTS, *AXES_PROMPTS, STRUCTURED_JOINT_VERSION}
            and (result.relation_validation or {}).get("prompt_version")
            == validation.prompt_version
        )
        if (validation.status != ValidationStatus.VALIDATED
                or conclusion.status != ConclusionJustificationStatus.JUSTIFIED
                or any(item.status != StatementAttributionStatus.SUPPORTED_BY_SOURCES
                       for item in result.statement_attributions)
                or not validation.entailment_provider or not validation.prompt_hash
                or validation.attempt_count < (1 if joint_development else 2)):
            return ReasonCode.VALIDATION_UNAVAILABLE
        if decision.schema_version in {"2.3", "2.4"}:
            from app.validation.axes import QUALIFIER_VERSIONS, AxesQualificationAudit, qualify_axes

            try:
                axes_audit = AxesQualificationAudit.model_validate(result.conclusion_qualification)
                if (axes_audit.version not in QUALIFIER_VERSIONS
                        or axes_audit.input.base.proposed_label != decision.label
                        or axes_audit.output != qualify_axes(axes_audit.input,
                                                            version=axes_audit.version)
                        or axes_audit.output.status != ConclusionJustificationStatus.JUSTIFIED):
                    return ReasonCode.AUDIT_RECORD_MISMATCH
            except (ValueError, TypeError):
                return ReasonCode.AUDIT_RECORD_MISMATCH
        if decision.schema_version == "2.2":
            try:
                relation = RelationValidationAudit.model_validate(result.relation_validation)
                qualifier = ConclusionQualificationAudit.model_validate(
                    result.conclusion_qualification,
                )
            except (ValueError, TypeError):
                return ReasonCode.AUDIT_RECORD_MISMATCH
            if (relation.version != "relation-validation-1.0"
                    or qualifier.version not in {"conclusion-qualifier-1.0",
                                                 "conclusion-qualifier-1.1"}
                    or relation.error_category or qualifier.input.defects
                    or relation.input_hash != canonical_hash(relation.input_json)
                    or relation.provider != validation.entailment_provider
                    or relation.model != validation.entailment_model
                    or qualifier.input.proposed_label != decision.label
                    or qualifier.input.based_on_statement_ids !=
                    decision.conclusion.based_on_statement_ids
                    or qualifier.input.relations != relation.assessments
                    or tuple(r.statement_id for r in relation.assessments) != tuple(expected)
                    or qualifier.output != qualify_conclusion(qualifier.input)
                    or qualifier.output.status != ConclusionJustificationStatus.JUSTIFIED):
                return ReasonCode.AUDIT_RECORD_MISMATCH
        return None
    if policy.validation_version == "judge-validation-2.0":
        return ReasonCode.VALIDATION_UNAVAILABLE
    if (tuple(item.evidence_id for item in result.citation_validations)
            != decision.cited_evidence_ids
            or tuple(item.evidence_id for item in result.opposing_citation_validations)
            != decision.opposing_evidence_ids):
        return ReasonCode.AUDIT_RECORD_MISMATCH
    if result.fatal_issue_codes or any(
        item.issue_codes for item in (*result.citation_validations,
                                      *result.opposing_citation_validations)
    ):
        return ReasonCode.VALIDATION_FATAL_ISSUE
    citations = (*result.citation_validations, *result.opposing_citation_validations)
    if not citations:
        return ReasonCode.VALIDATION_UNAVAILABLE
    if any(not item.exists or not item.selected_for_judging
           or not item.passage_hash_matches or not item.document_provenance_exists
           or item.integrity_status == "retracted" for item in citations):
        return ReasonCode.VALIDATION_INVALID
    if any(item.scope_alignment == ScopeAlignment.MISMATCH
           or item.relation_alignment in {
               RelationAlignment.MISMATCH, RelationAlignment.REVERSE,
           } for item in citations):
        return ReasonCode.VALIDATION_INVALID
    if decision.label != JudgeLabel.NOT_ENOUGH_EVIDENCE and any(
        item.role == "cited" and (
            item.relation_alignment == RelationAlignment.WEAKER_THAN_CLAIM
            or (decision.label == JudgeLabel.SUPPORTED
                and item.numeric_alignment == NumericAlignment.MISMATCH)
        ) for item in citations
    ):
        return ReasonCode.VALIDATION_INVALID
    if validation.status == ValidationStatus.INVALID:
        return ReasonCode.VALIDATION_INVALID
    if validation.status == ValidationStatus.UNABLE_TO_VALIDATE:
        return ReasonCode.VALIDATION_UNAVAILABLE
    if validation.status == ValidationStatus.PARTIALLY_VALIDATED:
        # A narrower study can be precisely why an inconclusive judge is
        # correct. Permit only that one partiality, only when each cited use
        # was semantically checked. This never qualifies a decisive label.
        if not (
            evaluation_mode
            and decision.label == JudgeLabel.NOT_ENOUGH_EVIDENCE
            and IssueCode.PARTIAL_SCOPE_MATCH in result.warnings
            and set(result.warnings) <= {IssueCode.PARTIAL_SCOPE_MATCH,
                                         IssueCode.RELATION_UNCERTAIN}
            and citations
            and all(item.entailment_status == EntailmentStatus.ENTAILS_JUDGE_USE
                    for item in citations)
        ):
            return ReasonCode.VALIDATION_PARTIAL
    allowed_partial_scope = (
        evaluation_mode
        and decision.label == JudgeLabel.NOT_ENOUGH_EVIDENCE
        and validation.status == ValidationStatus.PARTIALLY_VALIDATED
    )
    if validation.status != policy.decisive_validation_status and not allowed_partial_scope:
        return ReasonCode.VALIDATION_UNAVAILABLE
    material_warnings = {
        IssueCode.NUMERIC_UNCERTAIN, IssueCode.PARTIAL_SCOPE_MATCH,
        IssueCode.INTEGRITY_UNKNOWN, IssueCode.EXPRESSION_OF_CONCERN,
    }
    if allowed_partial_scope:
        material_warnings.remove(IssueCode.PARTIAL_SCOPE_MATCH)
    if (set(result.warnings) & material_warnings or any(
        set(item.warnings) & material_warnings for item in citations
    )):
        return ReasonCode.VALIDATION_PARTIAL
    if (validation.status not in {ValidationStatus.VALIDATED,
                                   ValidationStatus.PARTIALLY_VALIDATED}
            or not validation.entailment_provider or not validation.prompt_hash
            or validation.attempt_count < 1
            or any(item.entailment_status != EntailmentStatus.ENTAILS_JUDGE_USE
                   for item in citations)):
        return ReasonCode.VALIDATION_UNAVAILABLE
    return None


def _judge_qualification(
    judge: JudgeRun,
    validation: JudgeValidationRun | None,
    request: AggregationInput,
    policy: VerdictPolicyV1,
    seen_slots: set[int],
    seen_families: set[str],
) -> JudgeQualification:
    reasons: list[ReasonCode] = []
    if judge.slot in seen_slots:
        reasons.append(ReasonCode.DUPLICATE_JUDGE_SLOT)
    seen_slots.add(judge.slot)
    family = judge.model_family.strip().casefold()
    if not family or family in seen_families:
        reasons.append(ReasonCode.DUPLICATE_MODEL_FAMILY)
    seen_families.add(family)
    if judge.outcome_status != "succeeded" or judge.decision is None:
        reasons.append(ReasonCode.JUDGE_FAILED)
    else:
        if request.mode == AggregationMode.PRODUCTION and judge.schema_version_inferred:
            reasons.append(ReasonCode.AUDIT_RECORD_INVALID)
        if (request.mode == AggregationMode.PRODUCTION and
                judge.response_json != judge.decision.model_dump(mode="json")):
            reasons.append(ReasonCode.AUDIT_RECORD_INVALID)
        validation_failure = _validation_failure(
            judge, validation, policy,
            evaluation_mode=request.mode == AggregationMode.FIXTURE_OR_EVALUATION,
        )
        if validation_failure is not None:
            reasons.append(validation_failure)
    if request.mode == AggregationMode.PRODUCTION:
        if not judge.model_identity_verified or not judge.model_snapshot:
            reasons.append(ReasonCode.MODEL_IDENTITY_UNVERIFIED)
        if not judge.model_family_verified:
            reasons.append(ReasonCode.MODEL_FAMILY_UNVERIFIED)
        if judge.search_override_active or judge.search_guard_bypassed:
            reasons.append(ReasonCode.SEARCH_GUARD_BYPASSED)
        if not judge.search_isolation_verified:
            reasons.append(ReasonCode.SEARCH_ISOLATION_UNVERIFIED)
        if (validation is not None and
                validation.entailment_provider not in policy.approved_entailment_providers):
            reasons.append(ReasonCode.VALIDATION_PROVIDER_UNAPPROVED)
    return JudgeQualification(
        judge_run_id=judge.judge_run_id,
        slot=judge.slot,
        model_family=judge.model_family,
        label=(
            validation.result.validated_evidence_position
            if judge.decision
            and isinstance(judge.decision, JudgeDecisionV2)
            and judge.decision.schema_version == "2.5"
            and validation
            else judge.decision.label
            if judge.decision
            else None
        ),
        validation_status=validation.status if validation else None,
        qualified=not reasons,
        exclusion_reasons=_unique_codes(reasons),
    )


def _audit_failure(
    request: AggregationInput,
    context: AggregationContext,
) -> ReasonCode | None:
    if not context.audit_records_valid:
        return ReasonCode.AUDIT_RECORD_INVALID
    judge_ids = {judge.judge_run_id for judge in context.judges}
    validation_ids = {validation.id for validation in context.validations}
    if (judge_ids != set(request.judge_run_ids)
            or validation_ids != set(request.judge_validation_run_ids)):
        return ReasonCode.AUDIT_RECORD_MISSING
    for judge in context.judges:
        if (judge.claim_id != request.claim_id
                or judge.evidence_pack_id != request.evidence_pack_id
                or judge.evidence_pack_hash != request.evidence_pack_hash):
            return ReasonCode.AUDIT_RECORD_MISMATCH
    if request.policy_version in {POLICY_V2.version, POLICY_V3.version, POLICY_V4.version}:
        if context.pack is None:
            return ReasonCode.PACK_UNAVAILABLE
        try:
            version = (context.judges[0].input_snapshot_version
                       if context.judges else "judge-input-2.1")
            prepared = prepare_judge_input(request.evidence_pack_id, context.pack,
                                           version=version or "judge-input-2.0")
        except ValueError:
            return ReasonCode.PACK_SELECTION_INVALID
        if any(
            judge.input_snapshot_version != prepared.input_snapshot_version
            or judge.input_snapshot_hash != prepared.input_snapshot_hash
            or judge.input_snapshot_json is None
            or input_snapshot_hash(judge.input_snapshot_json) != prepared.input_snapshot_hash
            for judge in context.judges
        ):
            return ReasonCode.AUDIT_RECORD_MISMATCH
        snapshots = {(judge.input_snapshot_version, judge.input_snapshot_hash)
                     for judge in context.judges if judge.outcome_status == "succeeded"}
        if len(snapshots) > 1 or any(
            version
            not in {
                "judge-input-2.0",
                "judge-input-2.1",
                "judge-input-2.2",
                "judge-input-2.3",
                "judge-input-2.4",
                "judge-input-2.5",
            }
            or hash_ is None
            or len(hash_) != 64
            for version, hash_ in snapshots
        ):
            return ReasonCode.AUDIT_RECORD_MISMATCH
        ids = {judge.judge_run_id for judge in context.judges}
        if any(judge.revision_of_judge_run_id in ids for judge in context.judges):
            return ReasonCode.AUDIT_RECORD_MISMATCH
    else:
        prompts = {(judge.prompt_version, judge.prompt_hash) for judge in context.judges
                   if judge.outcome_status == "succeeded"}
        if len(prompts) > 1 or any(len(hash_) != 64 for _, hash_ in prompts):
            return ReasonCode.AUDIT_RECORD_MISMATCH
    for validation in context.validations:
        if (validation.judge_run_id not in judge_ids
                or validation.evidence_pack_id != request.evidence_pack_id
                or validation.evidence_pack_hash != request.evidence_pack_hash):
            return ReasonCode.AUDIT_RECORD_MISMATCH
        judge = next(j for j in context.judges if j.judge_run_id == validation.judge_run_id)
        if (
            isinstance(judge.decision, JudgeDecisionV2)
            and judge.decision.schema_version == "2.5"
            and validation.status == ValidationStatus.VALIDATED
        ):
            from app.validation.audit25 import audit_matches25

            if (
                context.pack is None
                or context.claim is None
                or not audit_matches25(judge, validation, context.pack, context.claim.risk_class)
            ):
                return ReasonCode.AUDIT_RECORD_MISMATCH
        if (
            isinstance(judge.decision, JudgeDecisionV2)
            and judge.decision.schema_version == "2.4"
            and validation.status == ValidationStatus.VALIDATED
        ):
            from app.validation.audit24 import audit_matches24

            if (
                context.pack is None
                or context.claim is None
                or not audit_matches24(judge, validation, context.pack, context.claim.risk_class)
            ):
                return ReasonCode.AUDIT_RECORD_MISMATCH
        if (isinstance(judge.decision, JudgeDecisionV2) and judge.decision.schema_version == "2.3"
                and validation.status == ValidationStatus.VALIDATED):
            from app.validation.audit23 import audit_matches23

            if (context.pack is None or context.claim is None
                    or not audit_matches23(judge, validation, context.pack,
                                           context.claim.risk_class)):
                return ReasonCode.AUDIT_RECORD_MISMATCH
        if (isinstance(judge.decision, JudgeDecisionV2)
                and judge.decision.schema_version == "2.2"
                and validation.status == ValidationStatus.VALIDATED):
            try:
                relation = RelationValidationAudit.model_validate(
                    validation.result.relation_validation,
                )
                qualifier = ConclusionQualificationAudit.model_validate(
                    validation.result.conclusion_qualification,
                )
                if context.pack is None or context.claim is None:
                    return ReasonCode.AUDIT_RECORD_MISSING
                payload, findings = build_relation_payload(context.pack, judge.decision.statements)
                from app.validation.joint import PROMPTS as JOINT_PROMPTS
                from app.validation.joint import JointResponse, check_response, prepare_joint_input

                if relation.prompt_version in JOINT_PROMPTS:
                    prepared_relation = prepare_joint_input(judge, context.pack, str(validation.id),
                                                             version=relation.prompt_version)
                    joint = JointResponse.model_validate_json(json.dumps(relation.joint_response))
                    check_response(joint, prepared_relation)
                    if (joint.missing_material_evidence or joint.assessments != relation.assessments
                            or any(a.status != b.status or a.scope_match != b.scope_match
                                   or a.reason != b.reason
                                   for a, b in zip(joint.attributions,
                                                   validation.result.statement_attributions,
                                                   strict=True))):
                        return ReasonCode.AUDIT_RECORD_MISMATCH
                else:
                    if relation.joint_response is not None:
                        return ReasonCode.AUDIT_RECORD_MISMATCH
                    prepared_relation = prepare_relation_input(
                        payload, judge_run_id=str(judge.judge_run_id),
                        validation_run_id=str(validation.id),
                        statement_ids=tuple(s.statement_id for s in judge.decision.statements),
                        prompt_version=relation.prompt_version,
                    )
                exact_input = json.loads(prepared_relation.user_prompt.split("\n", 1)[1])
                if (relation.prompt_hash != prepared_relation.prompt_hash
                        or relation.input_hash != canonical_hash(exact_input)
                        or relation.input_json != exact_input
                        or qualifier.input.findings != findings
                        or qualifier.input.claim_type != context.pack.claim_snapshot.claim_type
                        or qualifier.input.risk_class != context.claim.risk_class):
                    return ReasonCode.AUDIT_RECORD_MISMATCH
                modern = context.pack.evidence_pack_version == "1.5"
                if (qualifier.version != ("conclusion-qualifier-1.1" if modern else
                                          "conclusion-qualifier-1.0")
                        or qualifier.input.evidence_policy != ("question-evidence-1.0"
                                                               if modern else "legacy-1.0")
                        or qualifier.input.question_category != (
                            question_category(context.pack.claim_snapshot) if modern else "other"
                        )):
                    return ReasonCode.AUDIT_RECORD_MISMATCH
            except (ValueError, TypeError, KeyError):
                return ReasonCode.AUDIT_RECORD_MISMATCH
    if len({item.judge_run_id for item in context.validations}) != len(context.validations):
        return ReasonCode.AUDIT_RECORD_MISMATCH
    return None


def semantic_result_hash(result: VerdictResult) -> str:
    """Hash only policy inputs and deterministic output, never a row ID or clock."""

    semantic = result.model_dump(mode="json", exclude={"semantic_hash"})
    return hashlib.sha256(json.dumps(
        semantic, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _result(
    request: AggregationInput, risk_class: str | None, verdict: LensVerdict,
    reasons: list[ReasonCode], qualifications: tuple[JudgeQualification, ...] = (),
) -> VerdictResult:
    counts = {label: 0 for label in JudgeLabel}
    for item in qualifications:
        if item.qualified and item.label is not None:
            counts[item.label] += 1
    labels = [item.label for item in qualifications if item.qualified]
    conflict = bool(counts[JudgeLabel.SUPPORTED] and counts[JudgeLabel.CONTRADICTED])
    disagreement = ((ReasonCode.VALIDATED_JUDGE_DISAGREEMENT,) if conflict else ())
    if request.mode == AggregationMode.FIXTURE_OR_EVALUATION:
        reasons.append(ReasonCode.EVALUATION_ONLY)
    payload = VerdictResult(
        verdict=verdict, policy_version=request.policy_version,
        claim_id=request.claim_id, evidence_pack_id=request.evidence_pack_id,
        evidence_pack_hash=request.evidence_pack_hash,
        input_judge_run_ids=request.judge_run_ids,
        input_validation_run_ids=request.judge_validation_run_ids,
        mode=request.mode, risk_class=risk_class,
        judge_qualifications=qualifications,
        qualified_judges=sum(item.qualified for item in qualifications),
        excluded_judges=sum(not item.qualified for item in qualifications),
        validated_label_counts=counts,
        unanimous=len(set(labels)) == 1 if len(labels) >= 2 else None,
        conflicting_decisive_labels=conflict,
        disagreement_reason_codes=disagreement,
        reason_codes=_unique_codes(reasons),
        production_qualified=(request.mode == AggregationMode.PRODUCTION
                              and verdict != LensVerdict.UNABLE_TO_VERIFY_RELIABLY
                              and bool(qualifications)),
        semantic_hash="0" * 64,
    )
    return payload.model_copy(update={"semantic_hash": semantic_result_hash(payload)})


@dataclass(frozen=True)
class VerdictService:
    policy: VerdictPolicyV1 = POLICY_V1

    def aggregate(
        self, request: AggregationInput, context: AggregationContext,
    ) -> VerdictResult:
        if request.policy_version != self.policy.version:
            raise ValueError("Unsupported verdict policy version")
        claim = context.claim
        risk = claim.risk_class if claim else None
        failure: ReasonCode | None = None
        if claim is None or claim.claim_id != request.claim_id:
            failure = ReasonCode.CLAIM_UNAVAILABLE
        elif claim.normalization_status != "normalized" and not (
            claim.normalization_status == "partially_linked" and claim.normalization_reviewed
        ):
            failure = ReasonCode.NORMALIZATION_INCOMPLETE
        elif risk not in {"standard", "high"}:
            failure = ReasonCode.RISK_CLASS_INVALID
        if failure is None:
            failure = _pack_failure(request, context, self.policy)
        if failure is not None:
            return _result(request, risk, LensVerdict.UNABLE_TO_VERIFY_RELIABLY, [failure])
        if not context.audit_records_valid:
            return _result(
                request, risk, LensVerdict.UNABLE_TO_VERIFY_RELIABLY,
                [ReasonCode.AUDIT_RECORD_INVALID],
            )
        if context.retrieval_status not in {"ok", "no_results", "partial_metadata"}:
            return _result(
                request, risk, LensVerdict.UNABLE_TO_VERIFY_RELIABLY,
                [ReasonCode.RETRIEVAL_TECHNICAL_FAILURE],
            )
        pack = context.pack
        assert pack is not None  # _pack_failure established this.
        if not pack.selected_evidence_ids:
            if request.judge_run_ids or request.judge_validation_run_ids:
                return _result(
                    request, risk, LensVerdict.UNABLE_TO_VERIFY_RELIABLY,
                    [ReasonCode.AUDIT_RECORD_MISMATCH],
                )
            if context.retrieval_status == "partial_metadata":
                return _result(
                    request, risk, LensVerdict.UNABLE_TO_VERIFY_RELIABLY,
                    [ReasonCode.RETRIEVAL_TECHNICAL_FAILURE],
                )
            reason = (ReasonCode.RETRIEVAL_NO_RESULTS if context.retrieval_status == "no_results"
                      else ReasonCode.INSUFFICIENT_DECISIVE_EVIDENCE)
            return _result(request, risk, LensVerdict.NOT_ENOUGH_EVIDENCE, [reason])
        if context.retrieval_status == "no_results":
            return _result(
                request, risk, LensVerdict.UNABLE_TO_VERIFY_RELIABLY,
                [ReasonCode.AUDIT_RECORD_MISMATCH],
            )
        failure = _audit_failure(request, context)
        if failure is not None:
            return _result(request, risk, LensVerdict.UNABLE_TO_VERIFY_RELIABLY, [failure])
        judges = {judge.judge_run_id: judge for judge in context.judges}
        validations = {item.judge_run_id: item for item in context.validations}
        seen_slots: set[int] = set()
        seen_families: set[str] = set()
        qualifications = tuple(
            _judge_qualification(
                judges[judge_id], validations.get(judge_id), request, self.policy,
                seen_slots, seen_families,
            ) for judge_id in request.judge_run_ids
        )
        reasons = [reason for item in qualifications for reason in item.exclusion_reasons]
        qualified = [item for item in qualifications if item.qualified]
        assert risk is not None
        causal_design_insufficient = (
            self.policy.version in {POLICY_V3.version, POLICY_V4.version}
            and pack.claim_snapshot.claim_type in {
                ClaimType.CAUSAL, ClaimType.PREVENTION, ClaimType.TREATMENT,
            }
            and any(item.label in {JudgeLabel.SUPPORTED, JudgeLabel.CONTRADICTED}
                    for item in qualified)
            and not _has_direct_causal_design(context, qualified)
        )
        # A single fully validated, decisive assessment can power an explicitly
        # provisional development result. Production and high-risk claims keep
        # their multi-judge thresholds; unavailable/partial assessments cannot
        # be promoted to medical conclusions.
        if (self.policy.version in {POLICY_V3.version, POLICY_V4.version}
                and request.mode == AggregationMode.FIXTURE_OR_EVALUATION
                and risk == "standard" and len(qualified) == 1):
            label = qualified[0].label
            if label in {JudgeLabel.SUPPORTED, JudgeLabel.CONTRADICTED}:
                if causal_design_insufficient:
                    reasons.append(ReasonCode.CAUSAL_EVIDENCE_TOO_INDIRECT)
                    return _result(
                        request, risk, LensVerdict.NOT_ENOUGH_EVIDENCE,
                        reasons, qualifications,
                    )
                verdict = (LensVerdict.SUPPORTED if label == JudgeLabel.SUPPORTED
                           else LensVerdict.CONTRADICTED)
                reasons.append(ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT)
                return _result(request, risk, verdict, reasons, qualifications)
        if len(qualified) < self.policy.minimum_judges(risk):
            reasons.append(ReasonCode.INSUFFICIENT_QUALIFIED_JUDGES)
            if any(reason in {
                ReasonCode.VALIDATION_UNAVAILABLE, ReasonCode.VALIDATION_PARTIAL,
                ReasonCode.VALIDATION_INVALID, ReasonCode.VALIDATION_FATAL_ISSUE,
                ReasonCode.VALIDATION_PROVIDER_UNAPPROVED,
            } for reason in reasons):
                reasons.append(ReasonCode.INSUFFICIENT_VALIDATED_JUDGES)
            return _result(
                request, risk, LensVerdict.UNABLE_TO_VERIFY_RELIABLY,
                reasons, qualifications,
            )
        if causal_design_insufficient:
            reasons.append(ReasonCode.CAUSAL_EVIDENCE_TOO_INDIRECT)
            return _result(
                request, risk, LensVerdict.NOT_ENOUGH_EVIDENCE,
                reasons, qualifications,
            )
        counts = {label: sum(item.label == label for item in qualified)
                  for label in JudgeLabel}
        verdict, reason = self.policy.decide(risk, counts)
        reasons.append(reason)
        return _result(request, risk, verdict, reasons, qualifications)
