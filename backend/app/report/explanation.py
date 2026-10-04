"""Verdict explanation 1.0: descriptive, non-voting templates over audited inputs."""

from dataclasses import dataclass

from pydantic import ValidationError

from app.judging.models import JudgeDecisionV2, JudgeRun
from app.report.models import ExplanationReason as R
from app.report.models import SourceCard, VerdictExplanation
from app.retrieval.models import EvidencePack
from app.validation.axes import AxesQualificationAudit, EvidenceClaimAssessment
from app.validation.models import (
    JudgeValidationRun,
    NumericAlignment,
    StatementAttributionStatus,
)
from app.validation.numeric_effects import NumericFinding
from app.validation.qualification import ConclusionQualificationAudit
from app.verdict.models import LensVerdict, ReasonCode, VerdictResult

VERSION = "1.0"


@dataclass(frozen=True)
class Finding:
    axis: EvidenceClaimAssessment
    magnitude: NumericAlignment
    evidence_ids: tuple[str, ...]
    decisive: bool
    weaker_relation: bool
    incomparable_magnitude: bool = False


def _audited_findings(
    verdict: VerdictResult, judges: tuple[JudgeRun, ...],
    validations: tuple[JudgeValidationRun, ...], cards: tuple[SourceCard, ...],
) -> tuple[tuple[Finding, ...], frozenset[str]]:
    qualified = {q.judge_run_id for q in verdict.judge_qualifications if q.qualified}
    visible = {excerpt.evidence_id for card in cards for excerpt in card.excerpts}
    visible.update(card.evidence_id for card in cards)
    by_judge = {j.judge_run_id: j for j in judges}
    findings: list[Finding] = []
    reasons: set[str] = set()
    for validation in sorted(validations, key=lambda v: str(v.id)):
        if validation.judge_run_id not in qualified:
            continue
        judge = by_judge.get(validation.judge_run_id)
        raw = validation.result.conclusion_qualification
        if raw is None or judge is None or not isinstance(judge.decision, JudgeDecisionV2):
            continue
        try:
            audit = AxesQualificationAudit.model_validate(raw)
        except ValidationError:
            # Earlier relation-only audits can still contribute explicit reason codes.
            try:
                older = ConclusionQualificationAudit.model_validate(raw)
            except ValidationError:
                continue
            reasons.update(older.output.reason_codes)
            continue
        reasons.update(audit.output.reason_codes)
        numeric_rows = tuple(NumericFinding.model_validate(n)
                             for n in validation.result.numeric_findings or ())
        metadata = {f.statement_id: f for f in audit.input.base.findings}
        statements = {s.statement_id: s for s in judge.decision.statements}
        attributions = {a.statement_id: a for a in validation.result.statement_attributions}
        dependencies = set(judge.decision.conclusion.based_on_statement_ids)
        for axis in audit.input.assessments:
            statement = statements.get(axis.statement_id)
            attribution = attributions.get(axis.statement_id)
            fact = metadata.get(axis.statement_id)
            if (statement is None or attribution is None or fact is None
                    or axis.statement_id not in dependencies
                    or attribution.status != StatementAttributionStatus.SUPPORTED_BY_SOURCES):
                continue
            ids = tuple(dict.fromkeys(r.evidence_id for r in statement.evidence_refs
                                      if r.evidence_id in visible
                                      and r.evidence_id in attribution.evidence_ids))
            if not ids or len(ids) != len({r.evidence_id for r in statement.evidence_refs}):
                continue
            findings.append(Finding(
                axis=axis, magnitude=fact.claim_magnitude_alignment, evidence_ids=ids,
                decisive=axis.statement_id in audit.output.decisive_statement_ids,
                weaker_relation="weaker_than_claim" in fact.deterministic_relations,
                incomparable_magnitude=any(
                    n.target_id == axis.statement_id
                    and n.comparability.magnitude_relation == "different"
                    and n.numeric_effect == "noncomparable" for n in numeric_rows
                ),
            ))
    return tuple(findings), frozenset(reasons)


def build_explanation(
    verdict: VerdictResult, pack: EvidencePack, judges: tuple[JudgeRun, ...],
    validations: tuple[JudgeValidationRun, ...], cards: tuple[SourceCard, ...],
) -> VerdictExplanation:
    """Read the final verdict; never qualify a finding, aggregate votes, or call a model."""
    label = verdict.verdict
    if label == LensVerdict.UNABLE_TO_VERIFY_RELIABLY:
        technical = any(code not in {
            ReasonCode.INSUFFICIENT_QUALIFIED_JUDGES,
            ReasonCode.INSUFFICIENT_VALIDATED_JUDGES, ReasonCode.EVALUATION_ONLY,
        } for code in verdict.reason_codes)
        if technical:
            failed = sum(bool(set(q.exclusion_reasons) & {
                ReasonCode.JUDGE_FAILED, ReasonCode.VALIDATION_INVALID,
                ReasonCode.VALIDATION_UNAVAILABLE, ReasonCode.VALIDATION_PARTIAL,
                ReasonCode.VALIDATION_FATAL_ISSUE,
            }) for q in verdict.judge_qualifications if not q.qualified)
            noun = "assessment" if failed == 1 else "assessments"
            unresolved = (f"{failed} {noun} could not be completed or validated, "
                          "leaving too few qualified assessments for a reliable conclusion."
                          if failed else
                          "Verification did not meet the required evidence and assessment "
                          "checks, so a reliable conclusion could not be reached.")
        else:
            unresolved = ("Too few qualified assessments were available to reach a reliable "
                          "conclusion about this claim.")
        return VerdictExplanation(
            summary=unresolved, established=None, unresolved=unresolved, evidence_ids=(),
            reason_category=R.TECHNICAL_VALIDATION_FAILURE if technical else
            R.INSUFFICIENT_QUALIFIED_JUDGES,
        )

    findings, qualifier_reasons = _audited_findings(verdict, judges, validations, cards)
    ids = tuple(sorted({e for card in cards for e in
                        (card.evidence_id, *(x.evidence_id for x in card.excerpts))}))
    pico = pack.claim_snapshot.pico
    magnitude = pico.numeric_effect if pico else None
    numeric = magnitude is not None
    notation = "claimed magnitude"
    if magnitude is not None and magnitude.status == "parsed" and magnitude.value:
        if magnitude.unit == "%":
            notation = f"{magnitude.value}%"
        elif magnitude.unit:
            notation = f"{magnitude.value} {magnitude.unit}"

    # A qualitative premise can be established only by an attributed, applicable
    # finding of a qualified assessment. Numeric mismatches never prove direction.
    directional = [f for f in findings if f.axis.direction == "supports_claim"
                   and f.axis.scope == "aligned" and f.axis.role in {"direct", "synthesis"}
                   and f.axis.strength in {"strong", "decisive", "supporting"}
                   and f.axis.finding_basis in {"direct_result", "causal_assessment"}
                   and not f.weaker_relation]
    established = None
    if numeric and directional:
        established = "Validated evidence supports the claimed direction of effect."
        if (pico and pico.intervention_or_exposure and pico.outcome and magnitude
                and magnitude.direction in {"increase", "decrease"}):
            # PICO strings are literal normalized claim components, never inferred.
            relation = "an increase" if magnitude.direction == "increase" else "a decrease"
            candidate = (f"Validated evidence supports {relation} in {pico.outcome} "
                         f"with {pico.intervention_or_exposure}.")
            if len(candidate) <= 155:
                established = candidate

    def result(category: R, unresolved: str | None, *, known: str | None = established,
               evidence_ids: tuple[str, ...] = ids) -> VerdictExplanation:
        summary = " ".join(x for x in (known, unresolved) if x)
        if ReasonCode.EVALUATION_SINGLE_VALIDATED_ASSESSMENT in verdict.reason_codes:
            summary += " This is a provisional development result."
        return VerdictExplanation(summary=summary, reason_category=category,
                                  established=known, unresolved=unresolved,
                                  evidence_ids=evidence_ids)

    if label == LensVerdict.SUPPORTED:
        quantifier = "Multiple validated assessments" if verdict.qualified_judges > 1 else \
            "One validated assessment"
        qualifier = (" The conclusion applies to the tested comparison."
                     if any(f.decisive and f.axis.scope == "compatible_but_narrower"
                            for f in findings) else "")
        return result(R.SUPPORTED_BY_VALIDATED_EVIDENCE, None,
                      known=f"{quantifier} found evidence supporting the claim "
                      f"at its stated scope.{qualifier}")
    if label == LensVerdict.CONTRADICTED:
        numeric_opposition = [f for f in findings if f.decisive
                             and f.magnitude == NumericAlignment.MISMATCH
                             and f.axis.scope == "aligned"
                             and f.axis.direction == "opposes_claim"]
        if numeric and established and numeric_opposition:
            return result(R.CONTRADICTED_BY_VALIDATED_EVIDENCE,
                          f"Sufficiently comparable evidence conflicts with the claimed "
                          f"{notation} magnitude; the quantitative claim is contradicted.")
        return result(R.CONTRADICTED_BY_VALIDATED_EVIDENCE, None,
                      known="Validated evidence conflicts with the claim at its stated scope.")

    # NEI: audited magnitude, scope, design, conflict, indirect/context, direct gaps.
    numeric_gap = numeric and (any(f.magnitude in {
        NumericAlignment.UNCERTAIN, NumericAlignment.MISMATCH,
    } for f in findings) or bool(qualifier_reasons & {
        "MATERIAL_MAGNITUDE_NOT_SUPPORTED", "UNRESOLVED_REQUIRED_QUANTITY",
    }))
    if numeric_gap:
        incomparable = any(f.incomparable_magnitude or (
            f.magnitude == NumericAlignment.MISMATCH and f.axis.scope != "aligned"
        ) for f in findings)
        if incomparable:
            return result(R.NUMERIC_EVIDENCE_NOT_COMPARABLE,
                          "Available estimates differ from the claimed magnitude, but are "
                          "not sufficiently comparable to establish contradiction.")
        return result(R.NUMERIC_MAGNITUDE_UNVERIFIED,
                      f"The retrieved evidence does not establish the claimed {notation} "
                      "magnitude at a sufficiently comparable scope, so the specific "
                      "magnitude could not be verified.")

    scope = [f for f in findings if f.axis.scope in {
        "incompatible", "compatible_but_narrower", "broader_or_indirect",
    }]
    for basis, category, wording in (
        ("active_alternative", R.COMPARATOR_MISMATCH,
         "The evidence uses a different comparator and does not resolve the comparison "
         "in the claim."),
        ("population", R.POPULATION_MISMATCH,
         "The evidence concerns a different or restricted population and does not establish "
         "the claim for its stated population."),
        ("endpoint", R.OUTCOME_MISMATCH,
         "The evidence measures a different outcome and does not establish the outcome claimed."),
    ):
        if any(f.axis.scope_basis == basis for f in scope):
            return result(category, wording, known=None)
    if any(f.axis.scope == "compatible_but_narrower" for f in scope):
        return result(R.SCOPE_TOO_NARROW,
                      "The evidence covers a narrower scope and does not establish the "
                      "claim across its stated scope.", known=None)
    if ("CAUSAL_DESIGN_INSUFFICIENT" in qualifier_reasons
            or ReasonCode.CAUSAL_EVIDENCE_TOO_INDIRECT in verdict.reason_codes
            or (pack.claim_snapshot.claim_type in {"causal", "prevention", "treatment"}
                and any(f.axis.finding_basis in {"association", "reverse_causation"}
                        for f in findings))):
        reverse = any(f.axis.finding_basis == "reverse_causation" for f in findings)
        return result(R.CAUSAL_DESIGN_INSUFFICIENT,
                      "The validated findings cannot distinguish the claimed causal effect "
                      "from reverse causation." if reverse else
                      "The validated findings do not establish causation; the study designs "
                      "cannot resolve the claimed causal effect.", known=None)
    if (verdict.conflicting_decisive_labels or "CONFLICTING_FINDINGS" in qualifier_reasons
            or any(f.axis.finding_basis == "conflicting_results" for f in findings)):
        return result(R.CONFLICTING_MATERIAL_EVIDENCE,
                      "Validated assessments disagreed: evidence pointed in both directions, "
                      "and neither direction justified a decisive conclusion at the claimed scope.",
                      known=None)
    if findings and all(f.axis.role in {"contextual", "background", "mechanistic"}
                        for f in findings):
        return result(R.ONLY_CONTEXTUAL_EVIDENCE,
                      "The validated findings provide background or mechanism only, rather "
                      "than direct evidence resolving the claim.", known=None)
    if scope or any(f.axis.role == "mechanistic" for f in findings):
        return result(R.ONLY_INDIRECT_EVIDENCE,
                      "The validated findings are indirect and do not resolve the claim "
                      "at its stated scope.", known=None)
    return result(R.INSUFFICIENT_DIRECT_EVIDENCE,
                  "The available validated findings do not provide enough direct evidence "
                  "to establish or rule out the claim at its stated scope.", known=None)
