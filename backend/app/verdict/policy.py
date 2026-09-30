"""Versioned conservative decision table; never infer truth from model majority."""

from dataclasses import dataclass

from app.judging.models import JudgeLabel
from app.validation.models import ValidationStatus
from app.verdict.models import LensVerdict, ReasonCode


@dataclass(frozen=True)
class VerdictPolicyV1:
    version: str = "verdict-policy-1.1"
    pack_version: str = "1.3"
    validation_version: str = "judge-validation-1.0"
    minimum_standard_judges: int = 2
    minimum_high_risk_judges: int = 3
    decisive_validation_status: ValidationStatus = ValidationStatus.VALIDATED
    # No live entailment provider is approved in Phase 6B. Approval requires a
    # reviewed policy revision, not a local runtime flag or a fixture label.
    approved_entailment_providers: frozenset[str] = frozenset()

    def minimum_judges(self, risk_class: str) -> int:
        return (self.minimum_high_risk_judges if risk_class == "high"
                else self.minimum_standard_judges)

    def decide(
        self, risk_class: str, counts: dict[JudgeLabel, int],
    ) -> tuple[LensVerdict, ReasonCode]:
        supported = counts[JudgeLabel.SUPPORTED]
        contradicted = counts[JudgeLabel.CONTRADICTED]
        inconclusive = counts[JudgeLabel.NOT_ENOUGH_EVIDENCE]
        if supported and contradicted:
            return (LensVerdict.NOT_ENOUGH_EVIDENCE,
                    ReasonCode.VALIDATED_JUDGE_DISAGREEMENT)
        if risk_class == "high":
            # Every qualified/validated high-risk judge must be decisive and
            # unanimous. Three agreeing votes are necessary, not sufficient;
            # all provenance and semantic validation gates ran before this.
            if supported >= self.minimum_high_risk_judges and not inconclusive:
                return LensVerdict.SUPPORTED, ReasonCode.UNANIMOUS_HIGH_RISK_SUPPORT
            if contradicted >= self.minimum_high_risk_judges and not inconclusive:
                return (LensVerdict.CONTRADICTED,
                        ReasonCode.UNANIMOUS_HIGH_RISK_CONTRADICTION)
        else:
            if supported >= self.minimum_standard_judges and not contradicted:
                return (LensVerdict.SUPPORTED,
                        ReasonCode.SUPPORTED_BY_MULTIPLE_VALIDATED_JUDGES)
            if contradicted >= self.minimum_standard_judges and not supported:
                return (LensVerdict.CONTRADICTED,
                        ReasonCode.CONTRADICTED_BY_MULTIPLE_VALIDATED_JUDGES)
        if inconclusive and not supported and not contradicted:
            return (LensVerdict.NOT_ENOUGH_EVIDENCE,
                    ReasonCode.ALL_JUDGES_NOT_ENOUGH_EVIDENCE)
        return (LensVerdict.NOT_ENOUGH_EVIDENCE,
                ReasonCode.INSUFFICIENT_DECISIVE_EVIDENCE)


POLICY_V1 = VerdictPolicyV1()
POLICY_V2 = VerdictPolicyV1(
    version="verdict-policy-1.2", validation_version="judge-validation-2.0",
)
POLICY_V3 = VerdictPolicyV1(
    version="verdict-policy-1.3", validation_version="judge-validation-2.0",
)
