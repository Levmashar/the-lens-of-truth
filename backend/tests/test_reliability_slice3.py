"""Offline source/protocol and conditional policy controls, not clinical accuracy."""

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from test_reliability_slice2 import relation

from app.adapters.authoritative import (
    ApprovedSource,
    AuthoritativeAdapter,
    SourceManifest,
    freeze_html,
    load_manifest,
)
from app.judging.models import JudgeLabel
from app.judging.prompt import prepare_judge_input
from app.pipeline.claim_types import ClaimType
from app.pipeline.pico import NormalizedPico
from app.retrieval.analysis_design import characterize_analysis
from app.retrieval.evidence_pack import build_evidence_pack, canonical_pack_bytes
from app.retrieval.models import (
    ClaimSnapshot,
    EvidencePack,
    PubMedDocument,
)
from app.retrieval.passages import extract_passages
from app.retrieval.query_planner import plan_pubmed_queries
from app.retrieval.ranking import rank_passages
from app.retrieval.sufficiency import EvidenceDesignFact, design_eligible, independent_source_count
from app.validation.models import NumericAlignment
from app.validation.qualification import (
    ConclusionQualifierInput,
    FindingQualificationInput,
    qualify_conclusion,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)
HTML = (
    '<main id="evidence"><h2>Assessment</h2><p>The reviewed evidence concerns '
    "smoking and lung cancer risk; limitations remain explicit.</p>"
    "<h2>Methods</h2><p>This summary examines published studies of smoking "
    'and lung cancer.</p><a href="https://pubmed.ncbi.nlm.nih.gov/123/">Study</a>'
    '</main><time datetime="2025-04-01">April 1, 2025</time>'
)


def source() -> ApprovedSource:
    return ApprovedSource(
        source_id="fixture-nci",
        organization="NCI",
        canonical_url="https://www.cancer.gov/fixture",
        document_title="Synthetic source",
        document_purpose="causal_assessment",
        topic_terms=("smoking",),
        root_attribute="id",
        root_value="evidence",
        last_verified_at=NOW,
        retrieval_method="html_blocks",
        independence_group="fixture-body",
        attribution="Synthetic fixture, not an actual NCI document.",
    )


def claim() -> ClaimSnapshot:
    text = "Smoking causes lung cancer."
    return ClaimSnapshot(
        claim_id=uuid4(),
        raw_text=text,
        claim_type="causal",
        pico=NormalizedPico(
            original_claim=text,
            intervention_or_exposure="Smoking",
            outcome="lung cancer",
            claim_type="causal",
        ),
    )


def document(methods: str, *, design: str = "unknown") -> PubMedDocument:
    return PubMedDocument.model_validate(
        {
            "document_id": "pubmed:123",
            "pmid": "123",
            "title": "Synthetic smoking study",
            "abstract": methods,
            "abstract_sections": [{"label": "METHODS", "text": methods}],
            "canonical_url": "https://pubmed.ncbi.nlm.nih.gov/123/",
            "retrieved_at": NOW,
            "content_sha256": hashlib.sha256(methods.encode()).hexdigest(),
            "study_design": design,
            "study_design_source": "fixture_explicit_metadata",
            "integrity": {"status": "valid"},
        }
    )


def pack_for(
    documents: tuple[PubMedDocument, ...], snapshot: ClaimSnapshot, version: str = "1.5"
) -> EvidencePack:
    ranked = rank_passages(
        snapshot, documents, tuple(p for d in documents for p in extract_passages(d))
    )
    return build_evidence_pack(
        snapshot, plan_pubmed_queries(snapshot), documents, ranked, pack_version=version
    )


def test_manifest_domains_and_no_answer_table() -> None:
    manifest = load_manifest()
    assert {s.organization for s in manifest.sources} >= {"NCI", "CDC", "WHO", "IARC"}
    assert not any("supported" in s.model_dump_json() for s in manifest.sources)
    for url in (
        "http://www.cancer.gov/fixture",
        "https://evil.test/",
        "https://www.cancer.gov/fixture?url=x",
        "https://user@www.cancer.gov/fixture",
    ):
        with pytest.raises(ValidationError):
            ApprovedSource.model_validate({**source().model_dump(), "canonical_url": url})


def test_freeze_sections_offsets_provenance_roundtrip() -> None:
    doc = freeze_html(source(), HTML, now=NOW)
    assert doc.pmid == "" and doc.doi is None
    assert doc.authoritative.updated_at == date(2025, 4, 1)
    assert doc.authoritative.currency == "current"
    assert doc.authoritative.underlying_pmids == ("123",)
    assert [s.label for s in doc.abstract_sections] == ["Assessment", "Methods"]
    assert PubMedDocument.model_validate_json(doc.model_dump_json()) == doc
    for p in extract_passages(doc):
        assert hashlib.sha256(p.text.encode()).hexdigest() == p.content_sha256
        assert p.char_start == 0 and p.char_end == len(p.text)  # Unit-local offsets.


@pytest.mark.parametrize(
    "fragment,expected",
    [
        ("<footer>Site Last Updated: October 1, 2026</footer>", "unknown"),
        ('<time datetime="2010-01-01">January 1, 2010</time>', "stale"),
        ('<time datetime="2030-01-01">January 1, 2030</time>', "unknown"),
        ('<div class="date">25 September 2025</div>', "current"),
        (
            '<footer class="cgdp-article-footer"><time datetime="2025-01-01">'
            "January 1, 2025</time></footer>",
            "current",
        ),
    ],
)
def test_currency_is_not_fetch_success(fragment: str, expected: str) -> None:
    html = HTML.split("<time")[0] + fragment
    doc = freeze_html(source(), html, now=NOW)
    assert doc.authoritative.currency == expected
    if expected != "current":
        assert doc.integrity.status == "unknown"


def test_manifest_review_expiry_and_page_version() -> None:
    expired = source().model_copy(update={"last_verified_at": NOW - timedelta(days=91)})
    assert freeze_html(expired, HTML, now=NOW).authoritative.currency == "stale"
    first = freeze_html(source(), HTML, now=NOW)
    same = freeze_html(source(), HTML, now=NOW + timedelta(minutes=1))
    changed = freeze_html(source(), HTML.replace("limitations", "new limitations"), now=NOW)
    assert first.content_sha256 == same.content_sha256 != changed.content_sha256
    assert first.abstract_sections != changed.abstract_sections


@pytest.mark.parametrize("status", [200, 302, 403, 404])
def test_adapter_only_manifest_and_bounded_unavailability(status: int) -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(status, text=HTML, headers={"content-type": "text/html"})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            adapter = AuthoritativeAdapter(
                SourceManifest(version="fixture", sources=(source(),)), client=client
            )
            with pytest.raises(ValueError):
                await adapter.fetch("https://www.cancer.gov/unapproved")
            assert not seen
            docs, states = await adapter.retrieve(claim())
            assert bool(docs) == (status == 200)
            assert states["fixture-nci"] == ("current" if status == 200 else "unavailable")
            assert seen == [source().canonical_url]

    asyncio.run(run())


@pytest.mark.parametrize(
    "methods,parent,design,assignment",
    [
        (
            "We examined changes in smoking using longitudinal data collected in the trial.",
            "randomized_controlled_trial",
            "secondary_observational_analysis",
            "observed",
        ),
        (
            "Smokers were randomly assigned to vitamin supplements.",
            "randomized_controlled_trial",
            "unknown",
            "unknown",
        ),
        (
            "Adults were randomly assigned to smoking or control.",
            "randomized_controlled_trial",
            "randomized_intervention",
            "randomized",
        ),
        (
            "Smoking was measured in this prospective cohort study.",
            "cohort",
            "prospective_cohort",
            "observed",
        ),
        (
            "We conducted a case-control study of smoking.",
            "case_control",
            "case_control",
            "observed",
        ),
        (
            "A cross-sectional study measured smoking.",
            "cross_sectional",
            "cross_sectional",
            "observed",
        ),
        (
            "Published studies were synthesized.",
            "systematic_review",
            "systematic_review",
            "synthesized",
        ),
        ("Published studies were synthesized.", "meta_analysis", "meta_analysis", "synthesized"),
        ("We studied smoking and lung cancer.", "unknown", "unknown", "unknown"),
    ],
)
def test_relevant_exposure_design(methods: str, parent: str, design: str, assignment: str) -> None:
    analysis = characterize_analysis(claim(), document(methods, design=parent))
    assert (analysis.analysis_design, analysis.exposure_assignment) == (design, assignment)


def fact(**changes: object) -> EvidenceDesignFact:
    return EvidenceDesignFact.model_validate(
        {
            "document_id": "authoritative:fixture",
            "analysis_design": "unknown",
            "exposure_assignment": "unknown",
            "source_kind": "authoritative_public_health",
            "document_purpose": "causal_assessment",
            "role": "direct",
            "integrity": "valid",
            "currency": "current",
            "independence_group": "fixture",
            **changes,
        }
    )


@pytest.mark.parametrize(
    "category,changes,expected",
    [
        ("harmful_exposure_causality", {}, True),
        (
            "harmful_exposure_causality",
            {
                "source_kind": "pubmed",
                "analysis_design": "cross_sectional",
                "exposure_assignment": "observed",
            },
            False,
        ),
        ("treatment", {"document_purpose": "fact_sheet"}, False),
        (
            "treatment",
            {
                "source_kind": "pubmed",
                "analysis_design": "randomized_intervention",
                "exposure_assignment": "randomized",
            },
            True,
        ),
        ("prevention", {"source_kind": "pubmed", "analysis_design": "unknown"}, False),
        ("harmful_exposure_causality", {"role": "contextual"}, False),
        ("harmful_exposure_causality", {"currency": "unknown"}, False),
        ("diagnostic", {"document_purpose": "fact_sheet"}, False),
    ],
)
def test_question_specific_design_gate(category: str, changes: dict, expected: bool) -> None:
    assert design_eligible(category, fact(**changes)) is expected


@pytest.mark.parametrize(
    "direction,role,numeric,expected",
    [
        ("supports_claim", "direct", "not_applicable", "justified"),
        ("uncertain", "direct", "not_applicable", "uncertain"),
        ("supports_claim", "contextual", "not_applicable", "not_justified"),
        ("supports_claim", "direct", "uncertain", "not_justified"),
        ("supports_claim", "direct", "mismatch", "not_justified"),
    ],
)
def test_no_authority_truth_or_numeric_shortcut(
    direction: str, role: str, numeric: str, expected: str
) -> None:
    data = ConclusionQualifierInput(
        proposed_label=JudgeLabel.SUPPORTED,
        claim_type=ClaimType.CAUSAL,
        risk_class="standard",
        evidence_policy="question-evidence-1.0",
        question_category="harmful_exposure_causality",
        findings=(
            FindingQualificationInput(
                statement_id="S1",
                study_designs=("unknown",),
                integrity_statuses=("valid",),
                evidence_design_facts=(fact(role=role),),
                claim_magnitude_alignment=NumericAlignment(numeric),
            ),
        ),
        relations=(relation("S1", direction),),
        based_on_statement_ids=("S1",),
    )
    assert qualify_conclusion(data).status.value == expected


def test_document_sections_and_summary_references_are_not_independent() -> None:
    summary = fact(underlying_pmids=("123",))
    study = fact(document_id="pubmed:123", independence_group="pubmed:123")
    same_summary = fact(document_id="authoritative:other", independence_group="fixture")
    assert independent_source_count((summary, summary, study, same_summary)) == 1


def test_combined_pack_hash_versions_units_and_same_judge_input() -> None:
    snapshot = claim()
    research = document("In this prospective cohort, smoking and lung cancer were assessed.")
    approved = freeze_html(source(), HTML, now=NOW)
    combined = pack_for((research, approved), snapshot)
    assert {d.source_kind for d in combined.documents} == {"pubmed", "authoritative_public_health"}
    assert any(d.authoritative and d.evidence_role_hint == "direct" for d in combined.documents)
    prepared = prepare_judge_input(uuid4(), combined)
    assert len(
        {b["document"]["document_id"] for b in prepared.input_snapshot_json["document_bundles"]}
    ) == len(prepared.input_snapshot_json["document_bundles"])
    for unit in prepared.input_snapshot_json["source_units"]:
        assert hashlib.sha256(unit["text"].encode()).hexdigest() == unit["passage_sha256"]
    assert prepare_judge_input(prepared.pack_id, combined) == prepared
    assert "tools" not in prepared.input_snapshot_json
    same = pack_for(
        (research, approved.model_copy(update={"retrieved_at": NOW + timedelta(seconds=1)})),
        snapshot,
    )
    changed = pack_for(
        (research, freeze_html(source(), HTML.replace("limitations", "limitations X"), now=NOW)),
        snapshot,
    )
    assert combined.snapshot_hash == same.snapshot_hash != changed.snapshot_hash
    assert EvidencePack.model_validate_json(combined.model_dump_json()) == combined
    old = pack_for((research,), snapshot, version="1.4")
    prior = json.loads(
        canonical_pack_bytes(
            snapshot, old.query_plan, old.documents, old.passages, old.selected_evidence_ids
        )
    )
    assert "authoritative" not in prior["documents"][0]
    assert "relationship_analysis" not in prior["documents"][0]
    assert (
        old.snapshot_hash
        == hashlib.sha256(
            json.dumps(prior, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
    )


def test_summary_of_many_populations_is_not_a_never_smoker_cohort() -> None:
    html = HTML.replace("<h2>Methods</h2>", "<h2>Methods</h2><p>A study of never-smokers "
                        "is also discussed in this evidence summary.</p>")
    doc = freeze_html(source(), html, now=NOW)
    pack = pack_for((doc,), claim())
    assert pack.documents[0].relationship_directness.direction == "aligned"
    assert pack.documents[0].evidence_role_hint == "direct"
    assert pack.selected_evidence_ids


def test_topic_tag_is_not_synthesis_design() -> None:
    doc = document("Smoking was discussed.", design="systematic_review").model_copy(
        update={"study_design_source": "pubmed_mesh:systematic reviews as topic"})
    assert characterize_analysis(claim(), doc).analysis_design == "unknown"


def test_authoritative_no_pmid_can_be_attributed_offline() -> None:
    from test_reliability_slice2 import FixtureRelations
    from test_validation_v2 import finding, judge_for, ref

    from app.validation.models import ValidationStatus
    from app.validation.v2 import validate_v2

    doc = freeze_html(source(), HTML, now=NOW)
    pack = pack_for((doc,), claim())
    text = doc.abstract_sections[0].text
    judge = modern_judge(judge_for(pack, (finding("S1", text, ref(pack, text)),)), pack)
    audit = asyncio.run(validate_v2(judge, pack, FixtureRelations(("insufficient",))))
    assert audit.status == ValidationStatus.VALIDATED
    assert not any(i.issue_code == "DOCUMENT_PROVENANCE_MISSING"
                   for i in audit.result.targeted_issues)
    assert audit.result.conclusion_qualification["version"] == "conclusion-qualifier-1.1"


def test_one_source_card_retains_multiple_exact_units() -> None:
    from test_reliability_slice2 import FixtureRelations
    from test_verdict import case

    from app.report.builder import _cards
    from app.validation.v2 import validate_v2
    from app.verdict.service import VerdictService

    request, context = case((JudgeLabel.NOT_ENOUGH_EVIDENCE, JudgeLabel.NOT_ENOUGH_EVIDENCE))
    verdict = VerdictService().aggregate(request, context)
    long_methods = "This summary examines published studies of smoking and lung cancer. " * 12
    html = HTML.replace(
        "This summary examines published studies of smoking and lung cancer.", long_methods
    )
    pack = pack_for((freeze_html(source(), html, now=NOW),), claim())
    ids = tuple(p.evidence_id for p in pack.passages if p.passage.section != "TITLE")
    judges = tuple(modern_judge(j, pack) for j in context.judges)
    audits = tuple(asyncio.run(validate_v2(j, pack, FixtureRelations(("insufficient",))))
                   for j in judges)
    cards = _cards(verdict, pack, judges, audits)
    assert len(cards) == 1 and cards[0].pmid is None
    assert {e.evidence_id for e in cards[0].excerpts} == set(ids)
    assert {e.source_unit_id for e in cards[0].excerpts} == {f"{i}.U1" for i in ids}
    passages = {p.evidence_id: p.passage for p in pack.passages}
    assert any(len(e.exact_text) > 600 for e in cards[0].excerpts)
    for excerpt in cards[0].excerpts:
        assert excerpt.exact_text == passages[excerpt.evidence_id].text
        assert not excerpt.truncated
        assert hashlib.sha256(excerpt.exact_text.encode()).hexdigest() == excerpt.passage_sha256


def modern_judge(template: object, pack: EvidencePack) -> object:
    from app.judging.source_units import materialize_content

    prepared = prepare_judge_input(template.evidence_pack_id, pack)
    units = [u for u in prepared.input_snapshot_json["source_units"] if u["section"] != "TITLE"]
    content = {"label": "not_enough_evidence", "statements": [{
        "statement_id": "S1", "text": units[0]["text"], "kind": "study_finding",
        "source_unit_ids": [u["unit_id"] for u in units],
    }], "conclusion": {"based_on_statement_ids": ["S1"], "justification": "Limited evidence."},
               "uncertainty_reasons": []}
    return template.model_copy(update={
        "claim_id": pack.claim_id, "evidence_pack_hash": pack.snapshot_hash,
        "decision": materialize_content(json.dumps(content), prepared.input_snapshot_json),
        "input_snapshot_version": prepared.input_snapshot_version,
        "input_snapshot_hash": prepared.input_snapshot_hash,
        "input_snapshot_json": prepared.input_snapshot_json,
    })


def test_authoritative_response_size_and_type_limits() -> None:
    async def run() -> None:
        for body, kind in (("x" * 2_000_001, "text/html"), (HTML, "application/json")):
            async with httpx.AsyncClient(transport=httpx.MockTransport(
                lambda r, body=body, kind=kind: httpx.Response(
                    200, text=body, headers={"content-type": kind})
            )) as client:
                adapter = AuthoritativeAdapter(
                    SourceManifest(version="fixture", sources=(source(),)), client=client)
                with pytest.raises(ValueError):
                    await adapter.fetch("fixture-nci")
    asyncio.run(run())
