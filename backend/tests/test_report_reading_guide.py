"""Saved-case UI projections remain source-bound and cannot change a verdict."""

import asyncio
from uuid import uuid4

import pytest

from app.api.routes import analyses
from app.core.config import Settings
from app.core.errors import LensError
from app.report.builder import build_report
from app.report.reading_guide import _QUOTED, build_reading_guide, source_summary_sentences
from app.verdict.models import AggregationContext, AggregationInput, AggregationMode, ClaimFacts
from app.verdict.policy import POLICY_V4
from app.verdict.service import VerdictService
from tests.test_validated_evidence_position import EXPECTED, position_contract, saved, validate


@pytest.fixture(scope="module")
def cases():
    result = {}
    for name in EXPECTED:
        old, pack, response = saved(name)
        first = position_contract(old, pack, advisory=None)
        judges = (first, first.model_copy(update={
            "judge_run_id": uuid4(), "slot": 3 if first.slot == 2 else 2,
            "model_family": "offline-second-family",
        }))
        audits = tuple(validate(judge, pack, response) for judge in judges)
        request = AggregationInput(
            claim_id=pack.claim_id, evidence_pack_id=first.evidence_pack_id,
            evidence_pack_hash=pack.snapshot_hash,
            judge_run_ids=tuple(j.judge_run_id for j in judges),
            judge_validation_run_ids=tuple(a.id for a in audits),
            mode=AggregationMode.FIXTURE_OR_EVALUATION, policy_version=POLICY_V4.version,
        )
        context = AggregationContext(
            claim=ClaimFacts(claim_id=pack.claim_id, risk_class="standard",
                             normalization_status="normalized"),
            pack=pack, stored_pack_hash=pack.snapshot_hash,
            retrieval_status="ok", judges=judges, validations=audits,
        )
        verdict = VerdictService(POLICY_V4).aggregate(request, context)
        report = build_report(uuid4(), verdict, pack, judges, audits)
        result[name] = report, verdict, pack, judges, audits
    return result


@pytest.mark.parametrize("name", EXPECTED)
def test_saved_cases_have_source_bound_findings_without_rewriting_report(cases, name):
    report, verdict, pack, judges, audits = cases[name]
    before = report.model_dump_json(), verdict.model_dump_json()
    guide = build_reading_guide(report, verdict, pack, judges, audits, risk_class="standard")
    assert guide.findings
    assert len(guide.findings) <= 3
    assert guide.verdict_run_id == report.verdict_run_id
    assert guide.report_semantic_hash == report.semantic_hash
    texts = {s.qualitative_finding for j in judges for s in j.decision.statements}
    units = {e.source_unit_id: e for c in report.key_evidence for e in c.excerpts}
    for finding in guide.findings:
        assert finding.text in texts
        assert set(finding.source_unit_ids) <= set(units)
        assert set(finding.evidence_ids) == {units[u].evidence_id for u in finding.source_unit_ids}
    for highlight in guide.highlights:
        assert highlight.exact_text in units[highlight.source_unit_id].exact_text
    assert before == (report.model_dump_json(), verdict.model_dump_json())


def test_tampered_semantic_audits_cannot_supply_findings_or_highlights(cases):
    report, verdict, pack, judges, audits = cases["sunscreen"]
    bad = tuple(a.model_copy(update={"prompt_hash": "f" * 64}) for a in audits)
    guide = build_reading_guide(report, verdict, pack, judges, bad, risk_class="standard")
    assert not guide.findings and not guide.highlights


def test_excluded_judges_cannot_supply_findings(cases):
    report, verdict, pack, judges, audits = cases["smoking85"]
    excluded = verdict.model_copy(update={"judge_qualifications": tuple(
        q.model_copy(update={"qualified": False}) for q in verdict.judge_qualifications)})
    guide = build_reading_guide(report, excluded, pack, judges, audits, risk_class="standard")
    assert not guide.findings and not guide.highlights


def test_foreign_report_provenance_is_rejected(cases):
    report, verdict, pack, judges, audits = cases["sunscreen"]
    foreign = report.model_copy(update={"provenance": report.provenance.model_copy(
        update={"evidence_pack_hash": "f" * 64})})
    with pytest.raises(ValueError, match="provenance mismatch"):
        build_reading_guide(foreign, verdict, pack, judges, audits, risk_class="standard")


def test_reading_guide_uses_the_existing_production_report_gate(monkeypatch):
    async def gated(*args):
        raise LensError(403, "report_not_qualified", "Not qualified.")

    monkeypatch.setattr(analyses, "get_claim_report", gated)
    with pytest.raises(LensError) as caught:
        asyncio.run(analyses.get_report_reading_guide(
            uuid4(), uuid4(), object(), Settings(app_env="production", _env_file=None)))
    assert caught.value.status_code == 403


@pytest.mark.parametrize("marks", [('"', '"'), ('“', '”'), ("'", "'")])
def test_source_quotation_extraction_keeps_apostrophes_and_negation(marks):
    text = "The participants' measured hormones did not change after supplementation."
    matches = list(_QUOTED.finditer(f"Source states {marks[0]}{text}{marks[1]}"))
    assert len(matches) == 1
    assert next(group for group in matches[0].groups() if group is not None) == text


def test_source_summary_fallback_is_literal_complete_and_preserves_negation():
    text = ("Prior reports described an increase. "
            "This updated meta-analysis indicates that neither exposure changes "
            "the outcome in men. "
            "Additional research may be useful.")
    assert source_summary_sentences(text) == (
        "This updated meta-analysis indicates that neither exposure changes the outcome in men.",)


def test_planned_studies_and_generic_keyword_mentions_are_not_source_summaries():
    text = ("This study was designed to investigate whether the exposure changes the outcome. "
            "The authors mention a previous review and a disease endpoint. "
            "Research may eventually show a benefit.")
    assert source_summary_sentences(text) == ()
