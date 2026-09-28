"""Validate one judge decision against its exact frozen Evidence Pack, never vote."""

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Literal
from uuid import uuid4

from app.judging.models import JudgeLabel, JudgeRun
from app.retrieval.evidence_pack import canonical_pack_bytes
from app.retrieval.models import EvidencePack
from app.validation.entailment import (
    PROMPT_VERSION,
    EvidenceEntailmentValidator,
    prepare_entailment_input,
)
from app.validation.models import (
    FATAL_ISSUES,
    CitationValidation,
    EntailmentInput,
    EntailmentStatus,
    IssueCode,
    JudgeValidationResult,
    JudgeValidationRun,
    NumericAlignment,
    RelationAlignment,
    ScopeAlignment,
    ValidationStatus,
)
from app.validation.numeric import VERSION as NUMERIC_VERSION
from app.validation.numeric import compare_numbers
from app.validation.scope import VERSION as SCOPE_VERSION
from app.validation.scope import compare_relation, compare_scope

VALIDATION_VERSION = "judge-validation-1.0"
DETERMINISTIC_VERSION = f"pack-1.3+{NUMERIC_VERSION}+{SCOPE_VERSION}"


@dataclass
class ValidationService:
    entailment_validator: EvidenceEntailmentValidator | None = None
    entailment_timeout_seconds: float = 20.0

    async def run(self, judge: JudgeRun, pack: EvidencePack) -> JudgeValidationRun:
        """Create a fresh audit object even when validating the same run twice."""

        if judge.decision is None or judge.outcome_status != "succeeded":
            raise ValueError("Only successful, strictly parsed judge runs can be validated")
        decision = judge.decision
        started_at, start = datetime.now(UTC), monotonic()
        actual_hash = hashlib.sha256(canonical_pack_bytes(
            pack.claim_snapshot, pack.query_plan, pack.documents, pack.passages,
            pack.selected_evidence_ids,
        )).hexdigest()
        pack_valid = (
            pack.evidence_pack_version == "1.3"
            and judge.evidence_pack_hash == pack.snapshot_hash == actual_hash
            and judge.claim_id == pack.claim_id == pack.claim_snapshot.claim_id
            and len({item.evidence_id for item in pack.passages}) == len(pack.passages)
            and len({item.document_id for item in pack.documents}) == len(pack.documents)
            and len(set(pack.selected_evidence_ids)) == len(pack.selected_evidence_ids)
        )
        passage_map = {item.evidence_id: item for item in pack.passages}
        document_map = {item.document_id: item for item in pack.documents}
        attempts = 0
        prompt_hashes: list[str] = []
        error_category: str | None = None

        async def citation(
            evidence_id: str, role: Literal["cited", "opposing"],
        ) -> CitationValidation:
            nonlocal attempts, error_category
            ranked = passage_map.get(evidence_id)
            document = (document_map.get(ranked.passage.document_id)
                        if ranked is not None else None)
            exists = ranked is not None
            selected = bool(ranked is not None and ranked.selected_for_judging
                            and evidence_id in pack.selected_evidence_ids)
            hash_matches = bool(ranked is not None and hashlib.sha256(
                ranked.passage.text.encode("utf-8"),
            ).hexdigest() == ranked.passage.content_sha256)
            provenance = bool(document and document.pmid and document.canonical_url
                              and document.content_sha256)
            issues: list[IssueCode] = []
            warnings: list[IssueCode] = []
            if not pack_valid:
                issues.append(IssueCode.PACK_HASH_MISMATCH)
            if not exists:
                issues.append(IssueCode.CITATION_NOT_IN_PACK)
            elif not selected:
                issues.append(IssueCode.CITATION_NOT_SELECTED)
            if exists and not hash_matches:
                issues.append(IssueCode.PASSAGE_HASH_MISMATCH)
            if exists and not provenance:
                issues.append(IssueCode.DOCUMENT_PROVENANCE_MISSING)
            numeric = NumericAlignment.UNCERTAIN
            scope = ScopeAlignment.UNCERTAIN
            relation = RelationAlignment.UNCERTAIN
            entailment = EntailmentStatus.UNCERTAIN
            entailment_scope: ScopeAlignment | None = None
            evidence_claim: str | None = None
            entailment_reason: str | None = None
            validator_provenance = {"deterministic_version": DETERMINISTIC_VERSION}
            integrity = document.integrity.status if document else None
            if document is not None and ranked is not None:
                if integrity == "retracted":
                    issues.append(IssueCode.RETRACTED_CITATION)
                elif integrity == "expression_of_concern":
                    warnings.append(IssueCode.EXPRESSION_OF_CONCERN)
                elif integrity == "unknown":
                    warnings.append(IssueCode.INTEGRITY_UNKNOWN)
                if document.quality_prior < 0.25:
                    warnings.append(IssueCode.QUALITY_PRIOR_LOW)
                if not issues:
                    numeric = compare_numbers(
                        pack.claim_snapshot.raw_text, decision.reasoning_summary,
                        ranked.passage.text,
                    )
                    reasoning_numeric = compare_numbers(
                        "", decision.reasoning_summary, ranked.passage.text,
                    )
                    scope = compare_scope(pack.claim_snapshot, document, ranked)
                    relation = compare_relation(pack.claim_snapshot, document, ranked)
                    decisive = decision.label != JudgeLabel.NOT_ENOUGH_EVIDENCE
                    if reasoning_numeric == NumericAlignment.MISMATCH or (
                        decisive and role == "cited"
                        and decision.label == JudgeLabel.SUPPORTED
                        and numeric == NumericAlignment.MISMATCH
                    ):
                        issues.append(IssueCode.MATERIAL_NUMERIC_MISMATCH)
                    elif numeric == NumericAlignment.UNCERTAIN:
                        warnings.append(IssueCode.NUMERIC_UNCERTAIN)
                    if scope == ScopeAlignment.MISMATCH and decisive:
                        issues.append(IssueCode.MATERIAL_SCOPE_MISMATCH)
                    elif scope in {ScopeAlignment.MISMATCH, ScopeAlignment.PARTIAL}:
                        warnings.append(IssueCode.PARTIAL_SCOPE_MATCH)
                    if (relation == RelationAlignment.WEAKER_THAN_CLAIM and decisive
                            and role == "cited"):
                        issues.append(IssueCode.RELATION_STRENGTH_MISMATCH)
                    elif relation == RelationAlignment.WEAKER_THAN_CLAIM:
                        warnings.append(IssueCode.RELATION_UNCERTAIN)
                    elif relation == RelationAlignment.REVERSE and decisive:
                        issues.append(IssueCode.MATERIAL_SCOPE_MISMATCH)
                    elif relation == RelationAlignment.UNCERTAIN:
                        warnings.append(IssueCode.RELATION_UNCERTAIN)
                    if not issues:
                        if self.entailment_validator is None:
                            warnings.append(IssueCode.ENTAILMENT_UNAVAILABLE)
                        else:
                            facts = EntailmentInput(
                                evidence_id=evidence_id, role=role,
                                exact_claim=pack.claim_snapshot.raw_text,
                                judge_label=decision.label,
                                reasoning_summary=decision.reasoning_summary,
                                passage=ranked.passage.text,
                                document_title=document.title,
                                document_pmid=document.pmid,
                                study_design=document.study_design,
                            )
                            prepared = prepare_entailment_input(facts)
                            prompt_hashes.append(prepared.prompt_hash)
                            validator_provenance.update({
                                "provider": self.entailment_validator.provider,
                                "model": self.entailment_validator.model,
                                "prompt_version": PROMPT_VERSION,
                                "prompt_hash": prepared.prompt_hash,
                            })
                            attempts += 1
                            try:
                                async with asyncio.timeout(self.entailment_timeout_seconds):
                                    output = await self.entailment_validator.validate(prepared)
                                if output.evidence_id != evidence_id:
                                    raise ValueError("entailment evidence ID mismatch")
                                entailment = output.status
                                entailment_scope = output.scope_match
                                evidence_claim = output.evidence_claim
                                entailment_reason = output.reason
                                if output.scope_match == ScopeAlignment.MISMATCH and decisive:
                                    issues.append(IssueCode.MATERIAL_SCOPE_MISMATCH)
                                if entailment == EntailmentStatus.CONTRADICTS_JUDGE_USE:
                                    issues.append(IssueCode.EVIDENCE_CONTRADICTS_JUDGE_USE)
                                elif entailment != EntailmentStatus.ENTAILS_JUDGE_USE:
                                    warnings.append(IssueCode.ENTAILMENT_UNCERTAIN)
                            except (TimeoutError, ValueError, TypeError) as exc:
                                error_category = (
                                    "entailment_timeout" if isinstance(exc, TimeoutError)
                                    else "entailment_invalid_response"
                                )
                                warnings.append(IssueCode.ENTAILMENT_UNAVAILABLE)
                            except Exception:
                                error_category = "entailment_provider_error"
                                warnings.append(IssueCode.ENTAILMENT_UNAVAILABLE)
            return CitationValidation(
                evidence_id=evidence_id, role=role, exists=exists,
                selected_for_judging=selected, passage_hash_matches=hash_matches,
                document_provenance_exists=provenance, integrity_status=integrity,
                numeric_alignment=numeric, scope_alignment=scope,
                relation_alignment=relation, entailment_status=entailment,
                entailment_scope_match=entailment_scope,
                evidence_claim=evidence_claim, entailment_reason=entailment_reason,
                issue_codes=tuple(dict.fromkeys(issues)),
                warnings=tuple(dict.fromkeys(warnings)),
                validator_provenance=validator_provenance,
            )

        citations = tuple([await citation(item, "cited")
                           for item in decision.cited_evidence_ids])
        opposing = tuple([await citation(item, "opposing")
                          for item in decision.opposing_evidence_ids])
        all_citations = (*citations, *opposing)
        fatal = {issue for item in all_citations for issue in item.issue_codes
                 if issue in FATAL_ISSUES}
        if not pack_valid:
            fatal.add(IssueCode.PACK_HASH_MISMATCH)
        warnings = {warning for item in all_citations for warning in item.warnings}
        decisive = decision.label != JudgeLabel.NOT_ENOUGH_EVIDENCE
        valid_cited = [item for item in citations if not item.issue_codes and
                       item.entailment_status == EntailmentStatus.ENTAILS_JUDGE_USE]
        if (decisive and not valid_cited and not fatal and error_category is None
                and self.entailment_validator is not None):
            fatal.add(IssueCode.NO_VALID_DECISIVE_CITATION)
        if fatal:
            status = ValidationStatus.INVALID
        elif not all_citations or self.entailment_validator is None or error_category:
            status = ValidationStatus.UNABLE_TO_VALIDATE
        elif all(item.entailment_status == EntailmentStatus.ENTAILS_JUDGE_USE
                 for item in all_citations):
            material_warnings = {
                IssueCode.NUMERIC_UNCERTAIN, IssueCode.PARTIAL_SCOPE_MATCH,
                IssueCode.INTEGRITY_UNKNOWN, IssueCode.EXPRESSION_OF_CONCERN,
            }
            status = (ValidationStatus.PARTIALLY_VALIDATED
                      if warnings & material_warnings else ValidationStatus.VALIDATED)
        elif valid_cited:
            status = ValidationStatus.PARTIALLY_VALIDATED
        else:
            status = ValidationStatus.UNABLE_TO_VALIDATE
        result = JudgeValidationResult(
            judge_run_id=judge.judge_run_id, evidence_pack_id=judge.evidence_pack_id,
            evidence_pack_hash=judge.evidence_pack_hash, judge_label=decision.label,
            citation_validations=citations, opposing_citation_validations=opposing,
            validation_status=status, fatal_issue_codes=tuple(sorted(fatal)),
            warnings=tuple(sorted(warnings)), validation_version=VALIDATION_VERSION,
        )
        aggregate_prompt_hash = (hashlib.sha256("".join(prompt_hashes).encode()).hexdigest()
                                 if prompt_hashes else None)
        return JudgeValidationRun(
            id=uuid4(), judge_run_id=judge.judge_run_id,
            evidence_pack_id=judge.evidence_pack_id,
            evidence_pack_hash=judge.evidence_pack_hash,
            validation_version=VALIDATION_VERSION,
            deterministic_validator_version=DETERMINISTIC_VERSION,
            entailment_provider=(self.entailment_validator.provider
                                 if self.entailment_validator else None),
            entailment_model=(self.entailment_validator.model
                              if self.entailment_validator else None),
            prompt_version=PROMPT_VERSION if prompt_hashes else None,
            prompt_hash=aggregate_prompt_hash,
            started_at=started_at, completed_at=datetime.now(UTC), status=status,
            result=result, error_category=error_category,
            latency_ms=round((monotonic() - start) * 1000), attempt_count=attempts,
        )
