"""Numeric preflight distinguishes source estimates from mentions of the claim."""

import asyncio
import json
from dataclasses import replace

import pytest

from app.evaluation.slice41_cases import CASES, probe_judge
from app.validation.assertion_numeric import compare_assertion_numbers
from app.validation.joint23 import (
    PRE_COMPACT_VERSION,
    prepare_joint23,
    validate_joint23,
)
from app.validation.models import NumericAlignment
from app.validation.numeric23 import LEGACY_VERSION, numeric_issues23

CLAIM = "Smoking increases lung cancer risk by 85%."


@pytest.mark.parametrize(("assertion", "source", "expected"), [
    ("20-40 times higher", "20–40 times higher", NumericAlignment.ALIGNED),
    ("20-40 times higher", "10-20 times higher", NumericAlignment.MISMATCH),
    ("30% to 50% lower", "30% to 50% lower", NumericAlignment.ALIGNED),
    ("Risk reduces by 30% to 50% over 10 years.",
     "Risk is 30% to 50% lower after 10 years.", NumericAlignment.ALIGNED),
    ("30 to 40% of deaths", "30 to 40% of deaths", NumericAlignment.ALIGNED),
    ("A review does not establish an 85% increase.", "A review reported no estimate.",
     NumericAlignment.NOT_APPLICABLE),
    ("The claim states an 85% increase.", "A review reported no estimate.",
     NumericAlignment.NOT_APPLICABLE),
    ("The claim states a 95% increase.", "A review reported no estimate.",
     NumericAlignment.MISMATCH),
    ("No source confirms an 85% increase.", "A review reports 20-40 times higher risk.",
     NumericAlignment.NOT_APPLICABLE),
    ("The evidence fails to support the specific 85% value asserted in the claim.",
     "A review reports 20-40 times higher risk.", NumericAlignment.NOT_APPLICABLE),
    ("The study reports an 85% increase.", "The study reports a 40% increase.",
     NumericAlignment.MISMATCH),
])
def test_typed_ranges_and_claim_mentions(assertion, source, expected):
    assert compare_assertion_numbers(
        assertion, (source,), user_claim=CLAIM, repaired=True,
    ).status == expected


def test_numeric_claim_can_reach_semantic_validation_when_its_source_range_aligns():
    case = replace(next(c for c in CASES if c.id == "smoking-positive"),
                   claim=CLAIM, exposure="Smoking", outcome="lung cancer risk",
                   source="A review reports 20-40 times higher lung cancer risk in smokers.",
                   raw="A review reports 20–40 times higher lung cancer risk, not an 85% "
                       "increase as claimed.",
                   finding="A review reports 20–40 times higher lung cancer risk.")
    judge, pack = probe_judge(case)
    assert not numeric_issues23(judge.decision, pack)
    assert numeric_issues23(judge.decision, pack, version=LEGACY_VERSION)

    class SentinelValidator:
        provider = "fixture"
        model = "fixture"
        called = False

        async def assess_joint23(self, _prepared):
            self.called = True
            raise TimeoutError

    validator = SentinelValidator()
    result = asyncio.run(validate_joint23(judge, pack, validator))
    assert validator.called
    assert result.error_category == "joint_axes_timeout"


def test_incorrect_material_effect_still_blocks_semantic_validation():
    case = replace(next(c for c in CASES if c.id == "smoking-positive"),
                   claim=CLAIM, exposure="Smoking", outcome="lung cancer risk",
                   source="The source reports a 40% increase in lung cancer risk.",
                   raw="The source reports an 85% increase in lung cancer risk.",
                   finding="The source reports an 85% increase in lung cancer risk.")
    judge, pack = probe_judge(case)
    assert any(issue.issue_code.value == "STATEMENT_NUMERIC_MISMATCH"
               and issue.severity == "fatal" for issue in numeric_issues23(judge.decision, pack))


def test_unrelated_trend_numbers_are_optional_not_the_claimed_effect():
    case = replace(next(c for c in CASES if c.id == "smoking-positive"),
                   claim=CLAIM, exposure="Smoking", outcome="lung cancer risk",
                   source="Smoking-attributable DALY burden increased from 100 to 120.",
                   raw="Smoking-attributable DALY burden increased from 100 to 120.",
                   finding="Smoking-attributable DALY burden increased over time.")
    judge, pack = probe_judge(case)
    issues = numeric_issues23(judge.decision, pack)
    assert issues
    assert all(issue.issue_code.value.startswith("OPTIONAL_") for issue in issues)


def test_verbatim_numeric_detail_is_checked_once_in_its_attributed_sentence():
    case = replace(next(c for c in CASES if c.id == "smoking-positive"),
                   claim=CLAIM, exposure="Smoking", outcome="lung cancer risk",
                   source="After 10 years, lung cancer risk is 30% to 50% lower after cessation.",
                   raw="After 10 years, lung cancer risk is 30% to 50% lower after cessation.",
                   finding="After cessation, lung cancer risk is 30% to 50% lower.",
                   details=("30% to 50%",))
    judge, pack = probe_judge(case)
    assert not numeric_issues23(judge.decision, pack)
    assert numeric_issues23(judge.decision, pack, version=LEGACY_VERSION)


def test_validator_wire_view_keeps_full_units_and_old_prompt_reconstructible():
    case = next(c for c in CASES if c.id == "smoking-positive")
    judge, pack = probe_judge(case)
    old = prepare_joint23(judge, pack, "fixture", version=PRE_COMPACT_VERSION,
                          numeric_version=LEGACY_VERSION)
    new = prepare_joint23(judge, pack, "fixture")
    old_payload = json.loads(old.user_prompt.split("\n", 1)[1])
    new_payload = json.loads(new.user_prompt.split("\n", 1)[1])
    assert old_payload["frozen_snapshot"]["source_units"] == new_payload[
        "frozen_snapshot"
    ]["source_units"]
    assert old_payload["frozen_snapshot"]["evidence_pack_hash"] == new_payload[
        "frozen_snapshot"
    ]["evidence_pack_hash"]
    assert all("text" in passage for bundle in old_payload["frozen_snapshot"][
        "document_bundles"
    ] for passage in bundle["passages"])
    assert all("text" not in passage for bundle in new_payload["frozen_snapshot"][
        "document_bundles"
    ] for passage in bundle["passages"])
    assert len(new.user_prompt) < len(old.user_prompt)
    assert new.prompt_hash != old.prompt_hash
