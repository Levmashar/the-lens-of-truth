"""Reconstruct new V2 axes audits without touching historical contracts/rows."""

import json

from app.judging.compact23 import prepare_compact23
from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.source_units import materialize_content, normalize_parent_unit_ids
from app.retrieval.models import EvidencePack
from app.validation.axes import (
    QUALIFIER_VERSIONS,
    AxesQualificationAudit,
    gradient_kind,
    null_precision_reason,
    qualify_axes,
)
from app.validation.axes import VERSION as AXES_VERSION
from app.validation.joint23 import (
    PRE_COMPACT_VERSION,
    PREVIOUS_VERSION,
    PROMPTS,
    VERSION,
    JointResponse23,
    check_response23,
    normalized_references23,
    prepare_joint23,
    qualification_input23,
)
from app.validation.models import ConclusionJustificationStatus, JudgeValidationRun
from app.validation.numeric23 import FIDELITY_VERSION as FIDELITY_NUMERIC_VERSION
from app.validation.numeric23 import LEGACY_VERSION as LEGACY_NUMERIC_VERSION
from app.validation.numeric23 import PREVIOUS_VERSION as PREVIOUS_NUMERIC_VERSION
from app.validation.numeric23 import VERSION as NUMERIC_VERSION
from app.validation.numeric23 import numeric_issues23
from app.validation.relations import canonical_hash


def audit_matches23(judge: JudgeRun, audit: JudgeValidationRun,
                    pack: EvidencePack, risk_class: str) -> bool:
    if not isinstance(judge.decision, JudgeDecisionV2) or judge.decision.schema_version != "2.3":
        return False
    try:
        prepared_judge = prepare_compact23(judge.evidence_pack_id, pack,
                                          version=judge.prompt_version)
        if (judge.prompt_version != prepared_judge.prompt_version
                or judge.prompt_hash != prepared_judge.prompt_hash
                or canonical_hash(judge.input_snapshot_json) !=
                canonical_hash(prepared_judge.input_snapshot_json)):
            return False
        # Exactly retained raw content must rematerialize the same canonical response.
        raw = (judge.response_json or {}).get("raw_model_content")
        if not isinstance(raw, str):
            return False
        recorded_changes = (judge.response_json or {}).get("source_unit_id_normalizations")
        if recorded_changes is not None:
            if not isinstance(recorded_changes, list) or not recorded_changes:
                return False
            materialized, changes = normalize_parent_unit_ids(
                raw, prepared_judge.input_snapshot_json,
            )
            if canonical_hash(recorded_changes) != canonical_hash(changes):
                return False
        else:
            materialized = raw
        if materialize_content(materialized, prepared_judge.input_snapshot_json) != judge.decision:
            return False
        relation = audit.result.relation_validation or {}
        version = relation.get("prompt_version")
        if version not in PROMPTS:
            return False
        numeric_version = next((candidate for candidate in (
            LEGACY_NUMERIC_VERSION, NUMERIC_VERSION,
            PREVIOUS_NUMERIC_VERSION,
            FIDELITY_NUMERIC_VERSION,
        ) if audit.deterministic_validator_version ==
            f"source-unit+{candidate}+axes-1.0"), None)
        if numeric_version is None:
            return False
        prepared = prepare_joint23(judge, pack, str(audit.id), version=version,
                                   numeric_version=numeric_version)
        exact = json.loads(prepared.user_prompt.split("\n", 1)[1])
        response = JointResponse23.model_validate_json(json.dumps(relation["joint_response"]))
        check_response23(response, prepared)
        response, conversions = normalized_references23(response, prepared)
        if relation.get("id_normalizations", ()) != conversions:
            # PostgreSQL JSONB changes tuples to lists; compare canonical content.
            if canonical_hash(relation.get("id_normalizations", ())) != canonical_hash(conversions):
                return False
        qualification = AxesQualificationAudit.model_validate(audit.result.conclusion_qualification)
        inputs = qualification_input23(judge, pack, response, risk_class, version=version,
                                       numeric_version=numeric_version)
        expected_qualifier = ("conclusion-qualifier-1.4" if version in
                              {PRE_COMPACT_VERSION, VERSION} else
                              "conclusion-qualifier-1.3" if version == PREVIOUS_VERSION else
                              "conclusion-qualifier-1.2")
        if version in {PRE_COMPACT_VERSION, VERSION}:
            expected_diagnostics = {a.statement_id: {
                "null_precision_reason": null_precision_reason(
                    inputs.source_texts.get(a.statement_id, ()))
                if a.finding_basis in {"precise_null", "imprecise_null"} else None,
                "gradient_kind": gradient_kind(inputs.source_texts.get(a.statement_id, ())),
                "raw_finding_basis": a.finding_basis,
                "raw_scope_basis": a.scope_basis,
            } for a in response.assessments}
            if relation.get("finding_diagnostics") != expected_diagnostics:
                return False
        if (relation.get("version") != AXES_VERSION
                or relation.get("prompt_hash") != prepared.prompt_hash
                or relation.get("input_json") != exact
                or relation.get("input_hash") != canonical_hash(exact)
                or relation.get("provider") != audit.entailment_provider
                or relation.get("model") != audit.entailment_model
                or audit.prompt_version != version or audit.prompt_hash != prepared.prompt_hash
                or qualification.version not in QUALIFIER_VERSIONS
                or qualification.version != expected_qualifier
                or qualification.input != inputs or qualification.output != qualify_axes(
                    inputs, version=qualification.version)
                or qualification.output.status != ConclusionJustificationStatus.JUSTIFIED
                or response.missing_material_evidence
                or tuple(audit.result.targeted_issues) != numeric_issues23(
                    judge.decision, pack, version=numeric_version,
                )):
            return False
        if numeric_version in {FIDELITY_NUMERIC_VERSION, NUMERIC_VERSION}:
            from app.validation.axes import gradient_compatible
            from app.validation.numeric23 import numeric_findings23

            expected_numeric = numeric_findings23(judge.decision, pack, version=numeric_version,
                                                 assessments={
                a.statement_id: (a.scope, a.scope_basis, gradient_compatible(inputs, a))
                for a in response.assessments
            })
            if canonical_hash(audit.result.numeric_findings) != canonical_hash(expected_numeric):
                return False
        elif audit.result.numeric_findings is not None:
            return False
        if numeric_version == NUMERIC_VERSION:
            from app.validation.numeric23 import numeric_occurrences23

            if canonical_hash(audit.result.numeric_occurrences) != canonical_hash(
                numeric_occurrences23(judge.decision, pack)
            ):
                return False
            if audit.result.semantic_validation is not None:
                return False  # A skipped audit cannot describe successful semantic qualification.
        elif audit.result.numeric_occurrences is not None:
            return False
        for a, b in zip(response.attributions, audit.result.statement_attributions, strict=True):
            if (a.statement_id != b.statement_id or a.evidence_ids != b.evidence_ids
                    or a.status != b.status or a.scope_match != b.scope_match
                    or a.reason != b.reason
                    or b.validator_provenance != {"provider": audit.entailment_provider,
                                                  "model": audit.entailment_model,
                                                  "prompt_version": version,
                                                  "prompt_hash": prepared.prompt_hash}):
                return False
        return True
    except (ValueError, TypeError, KeyError):
        return False
