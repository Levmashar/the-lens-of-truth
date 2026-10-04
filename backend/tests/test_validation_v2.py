"""V2 software-contract tests; fixture semantic answers are not clinical evaluation."""

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.judging.models import (
    EvidenceRef,
    JudgeConclusion,
    JudgeDecisionV2,
    JudgeLabel,
    JudgeRun,
    JudgeSlot,
    JudgeStatement,
    ProviderResponse,
)
from app.judging.prompt import prepare_judge_input
from app.judging.service import JudgeService
from app.pipeline.claim_types import ClaimType
from app.pipeline.pico import NormalizedPico
from app.report.builder import _neutral_sources, build_report
from app.retrieval.evidence_pack import build_evidence_pack
from app.retrieval.models import (
    AbstractSection,
    ClaimSnapshot,
    DocumentIntegrity,
    EvidencePack,
    PubMedDocument,
    StudyDesign,
)
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.validation.models import (
    ConclusionJustificationStatus,
    IssueCode,
    NumericAlignment,
    SemanticScope,
    StatementAttributionStatus,
    ValidationStatus,
)
from app.validation.numeric import compare_statement_numbers
from app.validation.semantic import (
    ConclusionSemanticResponse,
    PreparedSemanticInput,
    StatementSemanticResponse,
    prepare_semantic_input,
)
from app.validation.semantic_eval import CASES
from app.validation.v2 import validate_v2
from app.verdict.models import (
    AggregationContext,
    AggregationInput,
    AggregationMode,
    ClaimFacts,
    LensVerdict,
    ReasonCode,
    VerdictResult,
)
from app.verdict.policy import POLICY_V2, POLICY_V3
from app.verdict.service import VerdictService

NOW = datetime(2026, 9, 29, tzinfo=UTC)


def pack_for(
    claim: str, sections: tuple[tuple[str, str], ...], *,
    claim_type: ClaimType = ClaimType.CAUSAL,
    study_design: StudyDesign = "randomized_controlled_trial",
) -> EvidencePack:
    snapshot = ClaimSnapshot(
        claim_id=uuid4(), raw_text=claim, claim_type=claim_type,
        pico=NormalizedPico(
            original_claim=claim, claim_type=claim_type,
            intervention_or_exposure="X", outcome="Y",
        ),
    )
    docs = tuple(PubMedDocument(
        document_id=f"pubmed:{index + 1}", pmid=str(index + 1),
        title=f"Study {index + 1} of X and Y", abstract=text,
        abstract_sections=(AbstractSection(label=section, text=text),),
        canonical_url=f"https://pubmed.ncbi.nlm.nih.gov/{index + 1}/",
        retrieved_at=NOW, content_sha256=f"{index + 1:064x}",
        query_ids=("Q1",), integrity=DocumentIntegrity(status="valid"),
        study_design=study_design,
    ) for index, (section, text) in enumerate(sections))
    passages = tuple(item for doc in docs for item in extract_passages(doc))
    return build_evidence_pack(
        snapshot, plan_pubmed_queries(snapshot), docs,
        rank_passages(snapshot, docs, passages), selected_limit=8,
    )


def ref(pack: EvidencePack, text: str) -> EvidenceRef:
    item = next(item for item in pack.passages if text in item.passage.text)
    return EvidenceRef(evidence_id=item.evidence_id, quote=text)


def judge_for(
    pack: EvidencePack, statements: tuple[JudgeStatement, ...], *,
    label: JudgeLabel = JudgeLabel.NOT_ENOUGH_EVIDENCE,
    based_on: tuple[str, ...] = ("S1",),
    pack_id: object | None = None,
) -> JudgeRun:
    pack_id = pack_id or uuid4()
    prepared = prepare_judge_input(pack_id, pack, version="judge-input-2.0")
    decision = JudgeDecisionV2(
        schema_version="2.0", label=label, statements=statements,
        conclusion=JudgeConclusion(
            based_on_statement_ids=based_on,
            justification="The cited findings limit the exact causal conclusion.",
        ),
    )
    return JudgeRun(
        judge_run_id=uuid4(), claim_id=pack.claim_id, evidence_pack_id=pack_id,
        evidence_pack_hash=pack.snapshot_hash, slot=1, provider="fixture",
        model="fixture", model_family="fixture", prompt_version="judge-2.0",
        prompt_hash=prepared.prompt_hash, input_snapshot_version=prepared.input_snapshot_version,
        input_snapshot_hash=prepared.input_snapshot_hash,
        input_snapshot_json=prepared.input_snapshot_json,
        requested_at=NOW, responded_at=NOW, latency_ms=0, attempt_count=1,
        outcome_status="succeeded", decision=decision,
    )


class FixtureSemanticValidator:
    """Orchestration fake; live-model semantic accuracy is assessed separately."""

    provider = "fixture"
    model = "fixture"

    def __init__(
        self, *, conclusion: ConclusionJustificationStatus =
        ConclusionJustificationStatus.JUSTIFIED,
        statement_statuses: dict[str, StatementAttributionStatus] | None = None,
        scopes: dict[str, SemanticScope] | None = None,
    ) -> None:
        self.conclusion = conclusion
        self.statement_statuses = statement_statuses or {}
        self.scopes = scopes or {}
        self.calls: list[PreparedSemanticInput] = []

    async def assess_statement(
        self, prepared: PreparedSemanticInput,
    ) -> StatementSemanticResponse:
        self.calls.append(prepared)
        statement_id = prepared.statement_ids[0]
        return StatementSemanticResponse(
            statement_id=statement_id, evidence_ids=prepared.evidence_ids,
            status=self.statement_statuses.get(
                statement_id, StatementAttributionStatus.SUPPORTED_BY_SOURCES,
            ),
            scope_match=self.scopes.get(statement_id, SemanticScope.EXACT),
            reason="Fixture-assigned source-to-statement relation.",
        )

    async def assess_conclusion(
        self, prepared: PreparedSemanticInput,
    ) -> ConclusionSemanticResponse:
        self.calls.append(prepared)
        return ConclusionSemanticResponse(
            status=self.conclusion,
            based_on_statement_ids=prepared.statement_ids,
            evidence_ids=prepared.evidence_ids,
            reason="Fixture-assigned finding-to-label relation.",
        )


def finding(statement_id: str, text: str, *refs: EvidenceRef) -> JudgeStatement:
    return JudgeStatement(
        statement_id=statement_id, text=text, kind="study_finding",
        evidence_refs=refs,
    )


def test_evidence_opposing_claim_can_support_accurate_judge_statement() -> None:
    source = "The review says causality has not been established for X and Y."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    judge = judge_for(pack, (finding(
        "S1", "The review says causality has not been established for X and Y.",
        ref(pack, source),
    ),))
    validator = FixtureSemanticValidator()
    run = asyncio.run(validate_v2(judge, pack, validator))
    assert run.status == ValidationStatus.VALIDATED
    assert run.result.statement_attributions[0].status == (
        StatementAttributionStatus.SUPPORTED_BY_SOURCES
    )
    assert "original user claim is not the" in validator.calls[0].system_prompt.lower()
    assert validator.calls[0].operation == "statement_attribution"
    assert "original_claim" not in validator.calls[0].user_prompt
    assert "statement" in validator.calls[0].user_prompt
    assert validator.calls[1].operation == "conclusion_justification"


def test_frozen_input_validates_after_jsonb_array_round_trip() -> None:
    source = "The review says causality has not been established for X and Y."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    judge = judge_for(pack, (finding("S1", source, ref(pack, source)),))
    persisted = json.loads(json.dumps(judge.input_snapshot_json))
    reloaded = judge.model_copy(update={"input_snapshot_json": persisted})
    run = asyncio.run(validate_v2(reloaded, pack, FixtureSemanticValidator()))
    assert run.status == ValidationStatus.VALIDATED
    assert not run.result.fatal_issue_codes


def test_semantic_provider_failure_is_unavailable_not_a_scientific_rejection() -> None:
    source = "The study measured X and Y."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    judge = judge_for(pack, (finding("S1", source, ref(pack, source)),))

    class UnavailableValidator(FixtureSemanticValidator):
        async def assess_statement(
            self, prepared: PreparedSemanticInput,
        ) -> StatementSemanticResponse:
            raise TimeoutError("fixture provider timed out")

    audit = asyncio.run(validate_v2(judge, pack, UnavailableValidator()))
    assert audit.status == ValidationStatus.UNABLE_TO_VALIDATE
    assert audit.result.statement_attributions[0].status == (
        StatementAttributionStatus.UNABLE_TO_ASSESS
    )
    assert audit.result.conclusion_justification is not None
    assert audit.result.conclusion_justification.status == (
        ConclusionJustificationStatus.UNABLE_TO_ASSESS
    )


def test_correct_null_finding_can_have_unjustified_contradicted_conclusion() -> None:
    source = "The OR was 0.98 (95% CI 0.79-1.21), a nonsignificant association."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    judge = judge_for(pack, (finding(
        "S1", "The study reports OR 0.98 for X and Y.", ref(pack, source),
    ),), label=JudgeLabel.CONTRADICTED)
    run = asyncio.run(validate_v2(
        judge, pack, FixtureSemanticValidator(
            conclusion=ConclusionJustificationStatus.NOT_JUSTIFIED,
        ),
    ))
    assert run.result.statement_attributions[0].status == (
        StatementAttributionStatus.SUPPORTED_BY_SOURCES
    )
    assert run.result.conclusion_justification is not None
    assert run.result.conclusion_justification.status == (
        ConclusionJustificationStatus.NOT_JUSTIFIED
    )
    assert run.status == ValidationStatus.INVALID


def test_two_study_estimates_do_not_cross_contaminate() -> None:
    a = "Study A reports OR 0.98 for X and Y."
    b = "Study B reports OR 1.10 for X and Y."
    pack = pack_for("X causes Y.", (("RESULTS", a), ("RESULTS", b)))
    judge = judge_for(pack, (
        finding("S1", "Study A reports OR 0.98 for X and Y.", ref(pack, a)),
        finding("S2", "Study B reports OR 1.10 for X and Y.", ref(pack, b)),
    ), based_on=("S1", "S2"))
    run = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    assert run.status == ValidationStatus.VALIDATED
    assert not any(issue.issue_code == IssueCode.STATEMENT_NUMERIC_MISMATCH
                   for issue in run.result.targeted_issues)


def test_semantic_conclusion_input_names_exact_ids_to_echo() -> None:
    prepared = prepare_semantic_input(
        "conclusion_justification", {"original_claim": "X is associated with Y."},
        judge_run_id="judge", validation_run_id="validation",
        statement_ids=("S1", "S2"), evidence_ids=("E4", "E7"),
    )
    payload = json.loads(prepared.user_prompt.split("\n", maxsplit=1)[1])
    assert payload["required_statement_ids"] == ["S1", "S2"]
    assert payload["required_evidence_ids"] == ["E4", "E7"]
    assert "Copy required_statement_ids" in prepared.system_prompt
    assert "active-intervention-versus-active-intervention" in prepared.system_prompt
    assert 'An "and" coordination in the source is not a "because" claim' in (
        prepared.system_prompt
    )


@pytest.mark.parametrize(("statement", "source", "expected"), [
    ("Source reports OR 0.98.", "The OR was 0.98.", NumericAlignment.ALIGNED),
    ("Source reports OR 0.80.", "The OR was 0.15.", NumericAlignment.MISMATCH),
    ("Source reports OR 0.85.", "The RR was 0.85.", NumericAlignment.UNCERTAIN),
    ("Source reports 15% reduction.", "The reduction was 15%.", NumericAlignment.ALIGNED),
    (
        "Current smokers had HR 13.44; former smokers had HR 4.20.",
        "Current [hazard ratio (HR) 13.44] and former smokers "
        "(FS; HR 4.20) had higher lung cancer incidence.",
        NumericAlignment.ALIGNED,
    ),
    (
        "Current smokers had HR 13.44 (95% CI 10.80-16.75); "
        "former smokers had HR 4.20 (95% CI 3.48-5.08).",
        "Current smokers had hazard ratio (HR) 13.44 "
        "(95% confidence interval (CI) 10.80-16.75); "
        "former smokers had HR 4.20 (95% CI 3.48-5.08).",
        NumericAlignment.ALIGNED,
    ),
    (
        "The source reports a 95% CI 10.80-16.75.",
        "The source reports a higher risk without a confidence interval.",
        NumericAlignment.UNCERTAIN,
    ),
])
def test_statement_only_typed_numeric_comparison(
    statement: str, source: str, expected: NumericAlignment,
) -> None:
    assert compare_statement_numbers(statement, source)[0] == expected


def test_no_number_in_user_claim_does_not_hide_judge_numeric_error() -> None:
    source = "The study reports OR 0.15 for X and Y."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    judge = judge_for(pack, (finding(
        "S1", "The study reports OR 0.80 for X and Y.", ref(pack, source),
    ),))
    run = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    assert run.status == ValidationStatus.INVALID
    issue = next(item for item in run.result.targeted_issues
                 if item.issue_code == IssueCode.STATEMENT_NUMERIC_MISMATCH)
    assert issue.target_type == "judge_statement" and issue.target_id == "S1"
    assert issue.measure_type == "odds_ratio"


def test_user_number_can_differ_from_accurately_attributed_source_number() -> None:
    source = "The study found a 15% reduction in Y with X."
    pack = pack_for("X reduces Y by 80%.", (("RESULTS", source),))
    judge = judge_for(pack, (finding(
        "S1", "The study found a 15% reduction in Y with X.", ref(pack, source),
    ),))
    run = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    assert run.status == ValidationStatus.VALIDATED
    assert not run.result.targeted_issues


def test_joint_methods_and_results_are_visible_and_attributed_together() -> None:
    methods = "Adults were randomized to daily X or discretionary X."
    results = "The invasive Y rate was lower in the daily X group."
    claim = "Daily X causes invasive Y."
    snapshot = ClaimSnapshot(
        claim_id=uuid4(), raw_text=claim, claim_type=ClaimType.CAUSAL,
        pico=NormalizedPico(original_claim=claim, claim_type=ClaimType.CAUSAL,
                            intervention_or_exposure="Daily X", outcome="invasive Y"),
    )
    document = PubMedDocument(
        document_id="pubmed:123", pmid="123", title="Daily X and invasive Y",
        abstract=f"{methods} {results}",
        abstract_sections=(AbstractSection(label="METHODS", text=methods),
                           AbstractSection(label="RESULTS", text=results)),
        canonical_url="https://pubmed.ncbi.nlm.nih.gov/123/",
        retrieved_at=NOW, content_sha256="a" * 64, query_ids=("Q1",),
        integrity=DocumentIntegrity(status="valid"),
    )
    ranked = rank_passages(snapshot, (document,), extract_passages(document))
    pack = build_evidence_pack(snapshot, plan_pubmed_queries(snapshot),
                               (document,), ranked)
    prepared = prepare_judge_input(uuid4(), pack)
    method_ref, result_ref = ref(pack, methods), ref(pack, results)
    assert method_ref.evidence_id in prepared.selected_ids
    assert result_ref.evidence_id in prepared.selected_ids
    judge = judge_for(pack, (finding(
        "S1", "A randomized adult comparison observed a lower invasive Y rate.",
        method_ref, result_ref,
    ),))
    run = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    assert run.status == ValidationStatus.VALIDATED
    assert run.result.statement_attributions[0].evidence_ids == (
        method_ref.evidence_id, result_ref.evidence_id,
    )


def test_missing_context_is_unknown_not_fabricated_mismatch() -> None:
    source = "X and Y were examined."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    judge = judge_for(pack, (finding("S1", "X and Y were examined.", ref(pack, source)),))
    run = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator(
        scopes={"S1": SemanticScope.UNKNOWN},
    )))
    assert run.result.statement_attributions[0].scope_match == SemanticScope.UNKNOWN
    assert IssueCode.MATERIAL_SCOPE_MISMATCH not in run.result.fatal_issue_codes


def test_narrower_scope_differs_from_incompatible_scope() -> None:
    source = "Adult participants were assessed for X and Y."
    pack = pack_for("X causes Y.", (("METHODS", source),))
    judge = judge_for(pack, (finding("S1", source, ref(pack, source)),),
                      label=JudgeLabel.CONTRADICTED)
    narrower = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator(
        scopes={"S1": SemanticScope.COMPATIBLE_BUT_NARROWER},
    )))
    mismatch = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator(
        scopes={"S1": SemanticScope.MISMATCH},
    )))
    assert narrower.status == ValidationStatus.VALIDATED
    assert mismatch.status == ValidationStatus.INVALID


def test_bad_peripheral_finding_is_preserved_without_accepting_invalid_premise() -> None:
    good = "Study A found X and Y were associated."
    bad = "Study B found no clear relation between X and Y."
    pack = pack_for("X causes Y.", (("RESULTS", good), ("RESULTS", bad)))
    judge = judge_for(pack, (
        finding("S1", good, ref(pack, good)),
        finding("S2", "Study B proved X causes Y.", ref(pack, bad)),
    ), based_on=("S1",))
    validator = FixtureSemanticValidator(statement_statuses={
        "S2": StatementAttributionStatus.NOT_ESTABLISHED_BY_SOURCES,
    })
    run = asyncio.run(validate_v2(judge, pack, validator))
    assert run.result.statement_attributions[0].status == (
        StatementAttributionStatus.SUPPORTED_BY_SOURCES
    )
    assert run.result.statement_attributions[1].status == (
        StatementAttributionStatus.NOT_ESTABLISHED_BY_SOURCES
    )
    assert run.result.conclusion_justification is not None
    assert run.result.conclusion_justification.status == ConclusionJustificationStatus.JUSTIFIED
    assert run.status == ValidationStatus.INVALID
    dependent = judge_for(pack, judge.decision.statements, based_on=("S2",))
    dependent_run = asyncio.run(validate_v2(dependent, pack, validator))
    assert dependent_run.result.conclusion_justification is not None
    assert dependent_run.result.conclusion_justification.status == (
        ConclusionJustificationStatus.NOT_JUSTIFIED
    )


def test_quote_and_snapshot_integrity_fail_closed() -> None:
    source = "Study A found X and Y were associated."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    wrong = judge_for(pack, (finding(
        "S1", "Study A found X and Y were associated.",
        EvidenceRef(evidence_id=ref(pack, source).evidence_id, quote="fabricated quote"),
    ),))
    run = asyncio.run(validate_v2(wrong, pack, FixtureSemanticValidator()))
    assert run.status == ValidationStatus.INVALID
    assert IssueCode.QUOTE_NOT_IN_FROZEN_PASSAGE in run.result.fatal_issue_codes
    tampered = wrong.model_copy(update={"input_snapshot_hash": "0" * 64})
    tampered_run = asyncio.run(validate_v2(tampered, pack, FixtureSemanticValidator()))
    assert IssueCode.PACK_HASH_MISMATCH in tampered_run.result.fatal_issue_codes


def test_neutral_sources_only_for_intact_development_unable_report() -> None:
    source = "Study A found X and Y were associated."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    base = dict(
        policy_version="verdict-policy-1.2", claim_id=pack.claim_id,
        evidence_pack_id=uuid4(), evidence_pack_hash=pack.snapshot_hash,
        input_judge_run_ids=(), input_validation_run_ids=(), risk_class="standard",
        judge_qualifications=(), qualified_judges=0, excluded_judges=0,
        validated_label_counts={label: 0 for label in JudgeLabel},
        unanimous=None, conflicting_decisive_labels=False,
        disagreement_reason_codes=(), reason_codes=(), production_qualified=False,
        semantic_hash="0" * 64, verdict=LensVerdict.UNABLE_TO_VERIFY_RELIABLY,
    )
    evaluation = VerdictResult(**base, mode=AggregationMode.FIXTURE_OR_EVALUATION)
    production = VerdictResult(**base, mode=AggregationMode.PRODUCTION)
    assert _neutral_sources(evaluation, pack)
    assert not _neutral_sources(production, pack)
    item = pack.passages[0]
    corrupted = pack.model_copy(update={"passages": (
        item.model_copy(update={"passage": item.passage.model_copy(update={"text": "changed"})}),
        *pack.passages[1:],
    )})
    with pytest.raises(ValueError, match="hash"):
        _neutral_sources(evaluation, corrupted)


def test_semantic_revision_has_one_linked_run_and_one_call() -> None:
    source = "The study reports OR 0.15 for X and Y."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    original = judge_for(pack, (finding(
        "S1", "The study reports OR 0.80 for X and Y.", ref(pack, source),
    ),))
    audit = asyncio.run(validate_v2(original, pack, FixtureSemanticValidator()))
    assert audit.status == ValidationStatus.INVALID

    class CorrectionProvider:
        calls = 0

        async def evaluate(
            self, slot: JudgeSlot, prepared: object,
        ) -> ProviderResponse:
            self.calls += 1
            corrected = original.decision.model_copy(update={
                "statements": (finding(
                    "S1", "The study reports OR 0.15 for X and Y.", ref(pack, source),
                ),),
            })
            return ProviderResponse(content=corrected.model_dump_json())

    provider = CorrectionProvider()
    service = JudgeService({"fixture": provider})
    slot = JudgeSlot(slot=1, provider="fixture", model="fixture",
                     model_family="fixture", base_url="https://example.invalid/v1")
    persisted_original = original.model_copy(update={
        "input_snapshot_json": json.loads(json.dumps(original.input_snapshot_json)),
    })
    revised = asyncio.run(service.revise(persisted_original, audit, pack, slot))
    assert provider.calls == 1
    assert revised.revision_of_judge_run_id == original.judge_run_id
    assert revised.semantic_revision_number == 1
    assert revised.input_snapshot_hash == original.input_snapshot_hash
    assert revised.judge_run_id != original.judge_run_id
    with pytest.raises(ValueError, match="not eligible"):
        asyncio.run(service.revise(revised, audit, pack, slot))


def test_policy_never_counts_original_and_revision_twice() -> None:
    source = "Study A examined X and Y."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    parent = judge_for(pack, (finding("S1", source, ref(pack, source)),))
    child = parent.model_copy(update={
        "judge_run_id": uuid4(), "revision_of_judge_run_id": parent.judge_run_id,
        "semantic_revision_number": 1,
    })
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=parent.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash,
        judge_run_ids=(parent.judge_run_id, child.judge_run_id),
        judge_validation_run_ids=(), mode=AggregationMode.FIXTURE_OR_EVALUATION,
        policy_version=POLICY_V2.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                         risk_class="standard"),
        pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=(parent, child), validations=(),
    )
    result = VerdictService(policy=POLICY_V2).aggregate(request, context)
    assert result.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.AUDIT_RECORD_MISMATCH in result.reason_codes
    assert not result.production_qualified


def test_two_valid_v2_conclusions_feed_existing_count_policy_without_release() -> None:
    source = "The review did not establish that X causes Y."
    pack = pack_for("X causes Y.", (("RESULTS", source),))
    statement = finding("S1", "The review did not establish that X causes Y.",
                        ref(pack, source))
    pack_id = uuid4()
    first = judge_for(pack, (statement,), pack_id=pack_id)
    second = judge_for(pack, (statement,), pack_id=pack_id).model_copy(update={
        "slot": 2, "model": "fixture-2", "model_family": "fixture-family-2",
    })
    validations = tuple(asyncio.run(validate_v2(
        judge, pack, FixtureSemanticValidator(),
    )) for judge in (first, second))
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=pack_id,
        evidence_pack_hash=pack.snapshot_hash,
        judge_run_ids=(first.judge_run_id, second.judge_run_id),
        judge_validation_run_ids=tuple(item.id for item in validations),
        mode=AggregationMode.FIXTURE_OR_EVALUATION,
        policy_version=POLICY_V2.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                         risk_class="standard"),
        pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=(first, second), validations=validations,
    )
    verdict = VerdictService(policy=POLICY_V2).aggregate(request, context)
    assert verdict.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert verdict.qualified_judges == 2
    assert not verdict.production_qualified
    report = build_report(uuid4(), verdict, pack, (first, second), validations)
    assert report.key_evidence
    assert report.key_evidence[0].exact_excerpt in source
    assert report.verification_status.development_notice


@pytest.mark.parametrize("label", [JudgeLabel.SUPPORTED, JudgeLabel.CONTRADICTED])
def test_single_validated_standard_judge_is_explicitly_provisional_in_v3(
    label: JudgeLabel,
) -> None:
    source = "The cohort found an association between X and Y incidence."
    pack = pack_for("X is associated with Y incidence.", (("RESULTS", source),),
                    claim_type=ClaimType.ASSOCIATION)
    judge = judge_for(pack, (finding("S1", source, ref(pack, source)),), label=label)
    validation = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    assert validation.status == ValidationStatus.VALIDATED
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash,
        judge_run_ids=(judge.judge_run_id,),
        judge_validation_run_ids=(validation.id,),
        mode=AggregationMode.FIXTURE_OR_EVALUATION,
        policy_version=POLICY_V3.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                         risk_class="standard"),
        pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=(judge,), validations=(validation,),
    )
    verdict = VerdictService(policy=POLICY_V3).aggregate(request, context)
    assert verdict.verdict.value == label.value
    assert verdict.qualified_judges == 1
    assert ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT in verdict.reason_codes
    assert not verdict.production_qualified
    report = build_report(uuid4(), verdict, pack, (judge,), (validation,))
    assert report.verdict_display.startswith("Provisional ")
    assert report.key_evidence and report.sources
    assert "provisional development result" in report.short_summary.lower()
    assert report.verification_status.development_notice

    # The very same validated audit input cannot gain a production conclusion.
    production_judge = judge.model_copy(update={
        "model_identity_verified": True, "model_family_verified": True,
        "model_snapshot": "fixture-snapshot", "search_isolation_verified": True,
        "response_json": judge.decision.model_dump(mode="json") if judge.decision else None,
    })
    production_context = context.model_copy(update={"judges": (production_judge,)})
    production_request = request.model_copy(update={"mode": AggregationMode.PRODUCTION})
    production_policy = replace(
        POLICY_V3, approved_entailment_providers=frozenset({"fixture"}),
    )
    production = VerdictService(policy=production_policy).aggregate(
        production_request, production_context,
    )
    assert production.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.INSUFFICIENT_QUALIFIED_JUDGES in production.reason_codes
    assert not production.production_qualified

    high_context = context.model_copy(update={
        "claim": ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                            risk_class="high"),
    })
    high = VerdictService(policy=POLICY_V3).aggregate(request, high_context)
    assert high.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT not in high.reason_codes


def test_v3_does_not_promote_invalid_or_inconclusive_single_judge() -> None:
    source = "The cohort measured X and Y incidence."
    pack = pack_for("X is associated with Y incidence.", (("RESULTS", source),),
                    claim_type=ClaimType.ASSOCIATION)
    judge = judge_for(pack, (finding("S1", source, ref(pack, source)),),
                      label=JudgeLabel.NOT_ENOUGH_EVIDENCE)
    validation = asyncio.run(validate_v2(judge, pack, FixtureSemanticValidator()))
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=judge.evidence_pack_id,
        evidence_pack_hash=pack.snapshot_hash,
        judge_run_ids=(judge.judge_run_id,),
        judge_validation_run_ids=(validation.id,),
        mode=AggregationMode.FIXTURE_OR_EVALUATION,
        policy_version=POLICY_V3.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                         risk_class="standard"),
        pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=(judge,), validations=(validation,),
    )
    inconclusive = VerdictService(policy=POLICY_V3).aggregate(request, context)
    assert inconclusive.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT not in (
        inconclusive.reason_codes
    )
    invalid_validation = asyncio.run(validate_v2(
        judge, pack, FixtureSemanticValidator(
            conclusion=ConclusionJustificationStatus.NOT_JUSTIFIED,
        ),
    ))
    invalid_request = request.model_copy(update={
        "judge_validation_run_ids": (invalid_validation.id,),
    })
    invalid_context = context.model_copy(update={"validations": (invalid_validation,)})
    invalid = VerdictService(policy=POLICY_V3).aggregate(invalid_request, invalid_context)
    assert invalid.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
    assert ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT not in invalid.reason_codes


@pytest.mark.parametrize("judge_count", [1, 2])
def test_v3_does_not_turn_observational_association_into_causal_rejection(
    judge_count: int,
) -> None:
    source = "Higher carrot intake was associated with more reported poor night vision."
    pack = pack_for("Eating carrots improves eyesight.", (("RESULTS", source),),
                    study_design="cross_sectional")
    pack_id = uuid4()
    judges = tuple(judge_for(
        pack, (finding("S1", source, ref(pack, source)),),
        label=JudgeLabel.CONTRADICTED, pack_id=pack_id,
    ).model_copy(update={
        "slot": index + 1, "model_family": f"fixture-family-{index + 1}",
    }) for index in range(judge_count))
    validations = tuple(asyncio.run(validate_v2(
        judge, pack, FixtureSemanticValidator(),
    )) for judge in judges)
    assert all(item.status == ValidationStatus.VALIDATED for item in validations)
    request = AggregationInput(
        claim_id=pack.claim_id, evidence_pack_id=pack_id,
        evidence_pack_hash=pack.snapshot_hash,
        judge_run_ids=tuple(item.judge_run_id for item in judges),
        judge_validation_run_ids=tuple(item.id for item in validations),
        mode=AggregationMode.FIXTURE_OR_EVALUATION,
        policy_version=POLICY_V3.version,
    )
    context = AggregationContext(
        claim=ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                         risk_class="standard"),
        pack=pack, stored_pack_hash=pack.snapshot_hash, retrieval_status="ok",
        judges=judges, validations=validations,
    )
    verdict = VerdictService(policy=POLICY_V3).aggregate(request, context)
    assert verdict.verdict == LensVerdict.NOT_ENOUGH_EVIDENCE
    assert verdict.qualified_judges == judge_count
    assert ReasonCode.CAUSAL_EVIDENCE_TOO_INDIRECT in verdict.reason_codes
    assert ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT not in verdict.reason_codes
    if judge_count == 1:
        high_context = context.model_copy(update={
            "claim": ClaimFacts(claim_id=pack.claim_id, normalization_status="normalized",
                                risk_class="high"),
        })
        high = VerdictService(policy=POLICY_V3).aggregate(request, high_context)
        assert high.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
        assert ReasonCode.INSUFFICIENT_QUALIFIED_JUDGES in high.reason_codes

        decision = judges[0].decision
        production_judge = judges[0].model_copy(update={
            "model_identity_verified": True, "model_family_verified": True,
            "model_snapshot": "fixture-snapshot", "search_isolation_verified": True,
            "response_json": decision.model_dump(mode="json") if decision else None,
        })
        production_context = context.model_copy(update={
            "judges": (production_judge,),
        })
        production_request = request.model_copy(update={
            "mode": AggregationMode.PRODUCTION,
        })
        production_policy = replace(
            POLICY_V3, approved_entailment_providers=frozenset({"fixture"}),
        )
        production = VerdictService(policy=production_policy).aggregate(
            production_request, production_context,
        )
        assert production.verdict == LensVerdict.UNABLE_TO_VERIFY_RELIABLY
        assert ReasonCode.INSUFFICIENT_QUALIFIED_JUDGES in production.reason_codes
        assert not production.production_qualified


def test_opt_in_semantic_set_is_bounded_and_has_accept_reject_expectations() -> None:
    assert 12 <= len(CASES) <= 20
    assert any(case.conclusion == ConclusionJustificationStatus.JUSTIFIED for case in CASES)
    assert any(case.conclusion == ConclusionJustificationStatus.NOT_JUSTIFIED
               for case in CASES)
    assert any(case.attribution == StatementAttributionStatus.CONTRADICTED_BY_SOURCES
               for case in CASES)
    assert any(case.attribution == StatementAttributionStatus.NOT_ESTABLISHED_BY_SOURCES
               for case in CASES)
