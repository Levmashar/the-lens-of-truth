"""Exact append-only V2.5 audit reconstruction; historical 2.3 uses audit23."""

import json

from app.judging.compact25 import frozen_response_matches25
from app.judging.models import JudgeRun
from app.retrieval.models import EvidencePack
from app.validation.joint23 import JointResponse23
from app.validation.joint24 import (
    deterministic_version,
    finish_joint24,
    joint_prompt_version,
    prepare_joint24,
)
from app.validation.models import JudgeValidationRun, ValidationStatus
from app.validation.position import VERSIONS, EvidencePositionAudit
from app.validation.relations import canonical_hash


def audit_matches25(judge: JudgeRun, audit: JudgeValidationRun,
                    pack: EvidencePack, risk_class: str) -> bool:
    if not frozen_response_matches25(judge, pack):
        return False
    try:
        position = EvidencePositionAudit.model_validate(audit.result.conclusion_qualification)
        if position.version not in VERSIONS:
            return False
        if (audit.status != ValidationStatus.VALIDATED
                or audit.validation_version != "judge-validation-2.5"
                or audit.result.validation_version != audit.validation_version
                or audit.deterministic_validator_version != deterministic_version(
                    judge, position_version=position.version)
                or audit.prompt_version != joint_prompt_version(judge, position.version)
                or not audit.entailment_provider
                or not audit.entailment_model or audit.attempt_count != 1
                or audit.judge_run_id != judge.judge_run_id
                or audit.evidence_pack_id != judge.evidence_pack_id
                or audit.evidence_pack_hash != pack.snapshot_hash
                or audit.result.judge_run_id != judge.judge_run_id
                or audit.result.evidence_pack_id != judge.evidence_pack_id
                or audit.result.evidence_pack_hash != pack.snapshot_hash
                or audit.result.citation_validations or audit.result.opposing_citation_validations
                or audit.error_category is not None):
            return False
        relation = audit.result.relation_validation or {}
        response = JointResponse23.model_validate_json(json.dumps(relation["joint_response"]))
        if response.missing_material_evidence:
            return False
        prepared = prepare_joint24(judge, pack, str(audit.id), position_version=position.version)
        expected = finish_joint24(audit, judge, pack, response, prepared, risk_class=risk_class,
                                  provider=audit.entailment_provider, model=audit.entailment_model,
                                  position_version=position.version)
        return (audit.prompt_hash == prepared.prompt_hash
                and canonical_hash(expected.result.model_dump(mode="json")) ==
                canonical_hash(audit.result.model_dump(mode="json")))
    except (ValueError, TypeError, KeyError):
        return False
