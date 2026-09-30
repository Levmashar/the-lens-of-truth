"""Opt-in, bounded semantic contract evaluation against a configured real model.

Synthetic examples have hand-reviewed expected *contract* outcomes. This is not
a clinical benchmark or a production-provider approval.
"""

import argparse
import asyncio
from dataclasses import dataclass
from uuid import uuid4

from app.adapters.entailment import OpenAICompatibleEntailmentValidator
from app.core.config import get_settings
from app.judging.config import configured_slots
from app.validation.models import (
    ConclusionJustificationStatus as Conclusion,
)
from app.validation.models import (
    StatementAttributionStatus as Attribution,
)
from app.validation.semantic import prepare_semantic_input


@dataclass(frozen=True)
class Case:
    name: str
    claim: str
    statement: str
    passages: tuple[str, ...]
    label: str
    attribution: Attribution
    conclusion: Conclusion | None
    claim_type: str = "causal"


CASES: tuple[Case, ...] = (
    Case("polarity-limitation", "X causes Y.",
         "The review says causality has not been established for X and Y.",
         ("The available evidence does not establish that X causes Y.",),
         "not_enough_evidence", Attribution.SUPPORTED_BY_SOURCES, Conclusion.JUSTIFIED),
    Case("polarity-overclaim", "X causes Y.",
         "The review establishes that X causes Y.",
         ("The available evidence does not establish that X causes Y.",),
         "supported", Attribution.CONTRADICTED_BY_SOURCES, None),
    Case("null-is-not-absence", "X increases Y.",
         "A study reported a nonsignificant OR of 0.98 with 95% CI 0.79-1.21.",
         ("The OR was 0.98 (95% CI 0.79-1.21), not statistically significant.",),
         "contradicted", Attribution.SUPPORTED_BY_SOURCES, Conclusion.NOT_JUSTIFIED),
    Case("null-inconclusive", "X increases Y.",
         "A study reported a nonsignificant OR of 0.98 with 95% CI 0.79-1.21.",
         ("The OR was 0.98 (95% CI 0.79-1.21), not statistically significant.",),
         "not_enough_evidence", Attribution.SUPPORTED_BY_SOURCES, Conclusion.JUSTIFIED),
    Case("observational-causality", "X causes Y.",
         "A cohort observed an association between X and Y.",
         ("The cohort observed an association between X and Y; causation was not tested.",),
         "supported", Attribution.SUPPORTED_BY_SOURCES, Conclusion.NOT_JUSTIFIED),
    Case("association-as-stated", "X is associated with Y.",
         "A cohort observed an association between X and Y.",
         ("The cohort observed an association between X and Y.",),
         "supported", Attribution.SUPPORTED_BY_SOURCES, Conclusion.JUSTIFIED,
         claim_type="association"),
    Case("wrong-estimate", "X changes Y.",
         "The study reports OR 0.80 for X and Y.",
         ("The study reports OR 0.15 for X and Y.",),
         "supported", Attribution.NOT_ESTABLISHED_BY_SOURCES, None),
    Case("claim-source-discrepancy", "X reduces Y by 80%.",
         "The trial observed a 15% reduction in Y with X.",
         ("The trial observed a 15% reduction in Y with X. Its narrow confidence "
          "interval excluded an 80% reduction.",),
         "contradicted", Attribution.SUPPORTED_BY_SOURCES, Conclusion.JUSTIFIED),
    Case("ratio-type", "X changes Y.",
         "The study reports OR 0.85 for X and Y.",
         ("The study reports RR 0.85 for X and Y, not an odds ratio.",),
         "supported", Attribution.NOT_ESTABLISHED_BY_SOURCES, None),
    Case("population-shift", "X prevents Y in men.",
         "A trial in women reported a lower Y rate with X.",
         ("Only women were enrolled; the X group had a lower Y rate.",),
         "supported", Attribution.SUPPORTED_BY_SOURCES, Conclusion.NOT_JUSTIFIED),
    Case("invasive-scope", "X prevents invasive Y.",
         "The review reports a lower overall Y rate with X.",
         ("The review measured overall Y, without separating invasive Y.",),
         "supported", Attribution.SUPPORTED_BY_SOURCES, Conclusion.NOT_JUSTIFIED),
    Case("joint-method-result", "Daily X reduces Y in adults.",
         "An adult randomized comparison observed fewer Y events with daily X.",
         ("Adults were randomized to daily X or control.",
          "Fewer Y events occurred in the daily X arm than in control."),
         "supported", Attribution.SUPPORTED_BY_SOURCES, Conclusion.JUSTIFIED),
    Case("timeframe-shift", "X reduces Y within one week.",
         "The trial found lower Y at one year in the X group.",
         ("At one year, Y was lower in the X group than control.",),
         "supported", Attribution.SUPPORTED_BY_SOURCES, Conclusion.NOT_JUSTIFIED),
    Case("explicit-no-meaningful-effect", "X increases Y by at least 50%.",
         "A powered trial excluded a 50% Y increase under the tested X regimen.",
         ("The powered trial's confidence interval excluded a 50% or greater "
          "increase in Y under the tested X regimen.",),
         "contradicted", Attribution.SUPPORTED_BY_SOURCES, Conclusion.JUSTIFIED),
)


async def run(slot_number: int, limit: int) -> int:
    settings = get_settings()
    if settings.app_env not in {"development", "test"}:
        raise SystemExit("Semantic evaluation is development/test only.")
    slot = next((item for item in configured_slots(settings) if item.slot == slot_number), None)
    if slot is None:
        raise SystemExit("Configured judge slot was not found.")
    validator = OpenAICompatibleEntailmentValidator(
        provider=slot.provider, model=slot.model, base_url=slot.base_url,
        api_key=slot.api_key, timeout_seconds=20.0,
    )
    matched = failures = unresolved = provider_errors = 0
    for case in CASES[:limit]:
        refs = tuple(f"E{index}" for index in range(1, len(case.passages) + 1))
        statement = {
            "statement_id": "S1", "text": case.statement, "kind": "study_finding",
            "evidence_refs": [
                {"evidence_id": evidence_id, "quote": passage}
                for evidence_id, passage in zip(refs, case.passages, strict=True)
            ],
        }
        prepared = prepare_semantic_input(
            "statement_attribution", {
                "original_claim": case.claim, "statement": statement,
                "frozen_passages": [
                    {"evidence_id": evidence_id, "section": "RESULTS",
                     "passage": passage, "title": "Synthetic evaluation fixture",
                     "pmid": "synthetic", "study_design": "unknown", "integrity": "valid"}
                    for evidence_id, passage in zip(refs, case.passages, strict=True)
                ],
            }, judge_run_id=str(uuid4()), validation_run_id=str(uuid4()),
            statement_ids=("S1",), evidence_ids=refs,
        )
        try:
            attributed = await validator.assess_statement(prepared)
            observed = attributed.status.value
            expected = case.attribution.value
            if attributed.status == Attribution.UNABLE_TO_ASSESS:
                unresolved += 1
            elif attributed.status == case.attribution:
                matched += 1
            else:
                failures += 1
            print(f"{case.name} attribution expected={expected} observed={observed}")
            if case.conclusion is None or attributed.status != Attribution.SUPPORTED_BY_SOURCES:
                continue
            conclusion_input = prepare_semantic_input(
                "conclusion_justification", {
                    "original_claim": case.claim, "claim_type": case.claim_type,
                    "pico": None, "proposed_label": case.label,
                    "judge_conclusion": {
                        "based_on_statement_ids": ["S1"],
                        "justification": "The finding is proposed to justify this label.",
                    },
                    "validated_findings": [{"statement": statement,
                                            "attribution": attributed.model_dump(mode="json")}],
                }, judge_run_id=prepared.judge_run_id,
                validation_run_id=prepared.validation_run_id,
                statement_ids=("S1",), evidence_ids=refs,
            )
            justified = await validator.assess_conclusion(conclusion_input)
            if justified.status == Conclusion.UNABLE_TO_ASSESS:
                unresolved += 1
            elif justified.status == case.conclusion:
                matched += 1
            else:
                failures += 1
            print(f"{case.name} conclusion expected={case.conclusion.value} "
                  f"observed={justified.status.value}")
        except Exception as exc:
            provider_errors += 1
            print(f"{case.name} provider_or_format_failure={type(exc).__name__}")
    print(f"SUMMARY cases={min(limit, len(CASES))} matched={matched} "
          f"semantic_mismatches={failures} unresolved={unresolved} "
          f"provider_or_format_failures={provider_errors}")
    print("Contract evaluation only; not clinical accuracy or production approval.")
    return 0 if failures == unresolved == provider_errors == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Opt-in synthetic semantic contract evaluation")
    parser.add_argument("--run", action="store_true", required=True)
    parser.add_argument("--slot", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--limit", type=int, choices=range(1, len(CASES) + 1),
                        default=len(CASES))
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(args.slot, args.limit)))


if __name__ == "__main__":
    main()
