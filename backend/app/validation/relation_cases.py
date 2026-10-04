"""Engineer-authored synthetic relation controls; independent human review pending.

Statements are stipulated source-validated premises, not real clinical findings.
No real paper identifier, licensed abstract or clinical truth label is fabricated.
"""

from dataclasses import dataclass

from app.pipeline.claim_types import ClaimType
from app.validation.relations import ClaimRelation, ClaimScope, Materiality

VERSION = "relation-controls-1.0"
HUMAN_REVIEWED = False


@dataclass(frozen=True)
class RelationCase:
    id: str
    category: str
    claim: str
    statement: str
    expected: ClaimRelation
    scope: ClaimScope
    materiality: Materiality
    rationale: str
    claim_type: ClaimType = ClaimType.CAUSAL
    study_design: str = "randomized_controlled_trial"
    population: str | None = None
    exposure: str = "X"
    comparator: str | None = None
    outcome: str = "Y"

    def payload(self) -> dict[str, object]:
        return {
            "original_claim": self.claim,
            "claim_type": self.claim_type,
            "pico": {
                "original_claim": self.claim,
                "claim_type": self.claim_type,
                "population": self.population,
                "intervention_or_exposure": self.exposure,
                "comparator": self.comparator,
                "outcome": self.outcome,
                "timeframe": None,
            },
            "validated_statements": [
                {
                    "statement_id": "S1",
                    "text": self.statement,
                    "kind": "study_finding",
                    "frozen_metadata": [
                        {
                            "study_design": self.study_design,
                            "study_design_source": "synthetic_stipulation",
                            "integrity": "valid",
                        }
                    ],
                }
            ],
        }


S, C, LIMIT, B, U = (
    ClaimRelation.SUPPORTS,
    ClaimRelation.CONTRADICTS,
    ClaimRelation.INSUFFICIENT,
    ClaimRelation.CONTEXT_ONLY,
    ClaimRelation.UNCERTAIN,
)
A, N, D, M, Q = (
    ClaimScope.ALIGNED,
    ClaimScope.NARROWER,
    ClaimScope.INDIRECT,
    ClaimScope.MISMATCH,
    ClaimScope.UNCERTAIN,
)
DEC, SUP, CTX, UNC = (
    Materiality.DECISIVE,
    Materiality.SUPPORTING,
    Materiality.CONTEXTUAL,
    Materiality.UNCERTAIN,
)

CASES = (
    RelationCase(
        "support-trial",
        "A",
        "X increases Y.",
        "Randomized X versus placebo increased incidence of Y with a precise estimate.",
        S,
        A,
        DEC,
        "Direct randomized evidence for the asserted direction.",
    ),
    RelationCase(
        "support-association",
        "A",
        "X is associated with higher Y risk.",
        "A cohort found higher Y risk with X exposure, adjusting for measured confounders.",
        S,
        A,
        DEC,
        "An association claim does not demand randomized causality.",
        claim_type=ClaimType.ASSOCIATION,
        study_design="cohort",
    ),
    RelationCase(
        "support-prevention",
        "A",
        "X prevents Y.",
        "Randomized X versus placebo substantially reduced incident Y with a narrow CI.",
        S,
        A,
        DEC,
        "Compatible direct prevention finding.",
        claim_type=ClaimType.PREVENTION,
    ),
    RelationCase(
        "opposite-trial",
        "F",
        "X increases Y.",
        "Randomized X versus placebo decreased Y incidence; the interval excluded an increase.",
        C,
        A,
        DEC,
        "Opposite randomized direction, not absence of evidence.",
    ),
    RelationCase(
        "association-causal",
        "C",
        "X causes Y.",
        "An observational cohort found X associated with Y but could not establish causality.",
        LIMIT,
        A,
        SUP,
        "Association cannot establish this causal claim.",
        study_design="cohort",
    ),
    RelationCase(
        "wide-null",
        "D",
        "X increases Y risk.",
        "The randomized estimate for Y was RR 1.10 (95% CI 0.40-3.00), nonsignificant.",
        LIMIT,
        A,
        SUP,
        "Wide interval includes substantial increase and decrease.",
    ),
    RelationCase(
        "precise-magnitude-null",
        "E",
        "X doubles Y risk.",
        "Randomized X versus placebo yielded RR 1.00 (95% CI 0.98-1.02) for incident Y.",
        C,
        A,
        DEC,
        "Precise interval excludes doubling, not merely a nonsignificant P.",
    ),
    RelationCase(
        "equivalence",
        "E",
        "X changes Y by at least 20%.",
        "A prespecified equivalence trial found the X effect on Y within -2% to +2%.",
        C,
        A,
        DEC,
        "Tested equivalence bounds exclude the stated magnitude.",
    ),
    RelationCase(
        "animal-human",
        "G",
        "X prevents Y in humans.",
        "Randomized X reduced Y in mice; no human participants were studied.",
        LIMIT,
        M,
        SUP,
        "Animal result cannot decide the human endpoint.",
        claim_type=ClaimType.PREVENTION,
        study_design="animal_study",
        population="humans",
    ),
    RelationCase(
        "adult-child",
        "H",
        "X prevents Y in children.",
        "Randomized X reduced Y in adults; children were excluded.",
        LIMIT,
        M,
        SUP,
        "Adult-to-child extrapolation is explicit mismatch.",
        claim_type=ClaimType.PREVENTION,
        population="children",
    ),
    RelationCase(
        "narrow-dose",
        "I",
        "X increases Y.",
        "A randomized high-dose X trial increased incident Y; lower doses were not tested.",
        S,
        N,
        SUP,
        "Direction is relevant but only the narrower dose was studied.",
    ),
    RelationCase(
        "wrong-outcome",
        "J",
        "X reduces Y incidence.",
        "Randomized X lowered a surrogate blood marker Z; Y incidence was not measured.",
        LIMIT,
        M,
        SUP,
        "Surrogate marker is not the claimed clinical endpoint.",
    ),
    RelationCase(
        "mechanistic",
        "K",
        "X prevents clinical Y.",
        "Cell experiments show X binding receptor Z; clinical Y was not measured.",
        B,
        D,
        CTX,
        "Mechanism-only background cannot decide the clinical claim.",
        claim_type=ClaimType.PREVENTION,
        study_design="in_vitro",
    ),
    RelationCase(
        "synthesis-trials",
        "L",
        "X prevents Y.",
        "A systematic review of randomized placebo-controlled trials found X reduces incident Y.",
        S,
        A,
        DEC,
        "Explicit randomized synthesis, not design label alone.",
        claim_type=ClaimType.PREVENTION,
        study_design="systematic_review",
    ),
    RelationCase(
        "synthesis-observational",
        "L",
        "X causes Y.",
        "A meta-analysis of observational studies found X associated "
        "with Y and no causal inference.",
        LIMIT,
        A,
        SUP,
        "Meta-analysis does not upgrade observational causality.",
        study_design="meta_analysis",
    ),
    RelationCase(
        "numeric-overclaim",
        "M",
        "X reduces Y risk by 85%.",
        "The randomized estimate for incident Y was RR 0.85 (95% CI 0.82-0.88).",
        C,
        A,
        DEC,
        "RR 0.85 means 15% reduction; interval excludes 85% reduction.",
    ),
    RelationCase(
        "numeric-compatible",
        "N",
        "X reduces Y risk by about 15%.",
        "The randomized estimate for incident Y was RR 0.85 (95% CI 0.82-0.88).",
        S,
        A,
        DEC,
        "Correct numerical transformation at the same endpoint.",
    ),
    RelationCase(
        "numeric-opposite",
        "N",
        "X increases Y risk by 50%.",
        "Randomized X decreased Y risk: RR 0.70 (95% CI 0.65-0.75).",
        C,
        A,
        DEC,
        "Accurate counterestimate directly opposes the claimed increase.",
    ),
    RelationCase(
        "conflict-positive",
        "O",
        "X increases Y.",
        "One randomized X-placebo trial increased Y; another trial reported opposite findings.",
        U,
        A,
        UNC,
        "A combined conflicting premise has no safely unique direction.",
    ),
    RelationCase(
        "reverse-carrot",
        "P",
        "Eating carrots improves eyesight.",
        "A cross-sectional survey linked poor night vision to carrot intake, "
        "but direction and causality could not be inferred.",
        LIMIT,
        A,
        SUP,
        "Reverse causation cannot establish a carrot intervention effect.",
        study_design="cross_sectional",
        exposure="Eating carrots",
        outcome="eyesight",
    ),
    RelationCase(
        "causality-explicitly-unknown",
        "Q",
        "X causes Y.",
        "The investigators explicitly said causal inference from the "
        "X-Y correlation was impossible.",
        LIMIT,
        A,
        SUP,
        "Explicit inability to infer causality limits the question.",
        study_design="observational",
    ),
    RelationCase(
        "sample-size",
        "materiality",
        "X causes Y.",
        "The X-Y trial included 40,000 participants.",
        B,
        A,
        CTX,
        "Sample count alone says nothing about direction.",
    ),
    RelationCase(
        "smoking-stigma",
        "smoking",
        "Smoking causes lung cancer.",
        "People diagnosed with lung cancer reported stigma affecting emotional "
        "functioning; incidence from smoking was not studied.",
        B,
        D,
        CTX,
        "Post-diagnosis emotional outcome is background for incidence.",
        study_design="observational",
        exposure="Smoking",
        outcome="lung cancer",
    ),
    RelationCase(
        "smoking-covariate",
        "smoking",
        "Smoking causes lung cancer.",
        "A methylation-clock analysis used smoking as an adjustment covariate, "
        "without estimating smoking's lung cancer effect.",
        B,
        D,
        CTX,
        "Mentioned covariate is not tested exposure-effect evidence.",
        study_design="observational",
        exposure="Smoking",
        outcome="lung cancer",
    ),
    RelationCase(
        "smoking-risk-association",
        "smoking",
        "Smoking is associated with lung cancer risk.",
        "A cohort reported substantially greater lung cancer risk with greater cigarette exposure.",
        S,
        A,
        DEC,
        "Measured dose-related risk bears directly on the association.",
        claim_type=ClaimType.ASSOCIATION,
        study_design="cohort",
        exposure="Smoking",
        outcome="lung cancer",
    ),
    RelationCase(
        "smoking-causal-limited",
        "smoking",
        "Smoking causes lung cancer.",
        "A cohort reported substantially greater lung cancer risk with greater "
        "cigarette exposure, but did not establish a causal effect.",
        LIMIT,
        A,
        SUP,
        "Exposure-response evidence alone cannot prove causal strength.",
        study_design="cohort",
        exposure="Smoking",
        outcome="lung cancer",
    ),
    RelationCase(
        "sunscreen-null",
        "sunscreen",
        "Frequent sunscreen use causes invasive melanoma.",
        "An observational meta-analysis found no statistically significant association "
        "between sunscreen use and melanoma; estimates were imprecise and heterogeneous.",
        LIMIT,
        D,
        SUP,
        "Broad nonsignificant estimates do not rule out causal harm.",
        study_design="meta_analysis",
        exposure="Frequent sunscreen use",
        outcome="invasive melanoma",
    ),
    RelationCase(
        "sunscreen-randomized",
        "sunscreen",
        "Frequent sunscreen use causes invasive melanoma.",
        "Randomized daily versus discretionary sunscreen use in adults resulted in "
        "fewer invasive melanomas in the daily group: HR 0.27 (95% CI 0.08-0.97).",
        C,
        N,
        DEC,
        "Opposite randomized finding at narrower frequency/population scope.",
        exposure="Frequent sunscreen use",
        outcome="invasive melanoma",
    ),
    RelationCase(
        "soy-active-comparator",
        "soy",
        "Regular soy use reduces muscle gain.",
        "A trial comparing soy protein with whey found different muscle gains; "
        "no nonuse or placebo group was studied.",
        LIMIT,
        D,
        SUP,
        "An unstated active comparator does not decide absolute soy usage.",
        exposure="Regular soy use",
        outcome="muscle gain",
    ),
    RelationCase(
        "soy-wrong-endpoint",
        "soy",
        "Regular soy use reduces muscle gain.",
        "A randomized soy trial measured muscle soreness but did not measure muscle gain.",
        LIMIT,
        M,
        SUP,
        "Soreness is not muscle gain; extraction/retrieval remain untouched.",
        exposure="Regular soy use",
        outcome="muscle gain",
    ),
    RelationCase(
        "null-association-wide",
        "D",
        "X is associated with higher Y risk.",
        "The cohort estimate was RR 1.10 (95% CI 0.40-3.00), nonsignificant.",
        LIMIT,
        A,
        SUP,
        "Wide nonsignificant interval cannot decide direction.",
        claim_type=ClaimType.ASSOCIATION,
        study_design="cohort",
    ),
    RelationCase(
        "precision-limitation",
        "materiality",
        "X increases Y.",
        "The randomized X-Y estimate had a very wide CI including clinically "
        "important increase and decrease.",
        LIMIT,
        A,
        SUP,
        "Precision is a material limitation, not decorative context.",
    ),
)
