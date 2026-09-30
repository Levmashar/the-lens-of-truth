"""The toy prompt example illustrates V2 structure without medical content."""

import json

from app.judging.models import JudgeDecisionV2
from app.judging.prompt import PROMPT_VERSION, SYSTEM_INSTRUCTIONS


def test_toy_example_has_structured_conclusion_and_is_not_medical_evidence() -> None:
    assert PROMPT_VERSION == "judge-2.3-2026-09-30"
    example = SYSTEM_INSTRUCTIONS.split("SHAPE EXAMPLE ONLY", maxsplit=1)[1]
    example = example[example.index("{"):example.index("\nIn your real answer")]
    payload = json.loads(example)
    decision = JudgeDecisionV2.model_validate_json(json.dumps(payload))
    assert decision.conclusion.based_on_statement_ids == ("S1",)
    assert isinstance(payload["conclusion"], dict)
    assert "toy" in payload["statements"][0]["text"].casefold()
    assert "Do not copy" in SYSTEM_INSTRUCTIONS
    assert "never a string" in SYSTEM_INSTRUCTIONS
