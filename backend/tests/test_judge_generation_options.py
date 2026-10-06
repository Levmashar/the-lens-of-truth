"""Generation controls must reach the gateway without changing the frozen contract."""

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from app.adapters.judge import OpenAICompatibleJudgeProvider, ProviderFailure
from app.core.config import Settings
from app.judging.config import configured_slots
from app.judging.models import JudgeSlot, ProviderResponse
from app.judging.prompt import PreparedJudgeInput
from app.judging.service import JudgeService
from tests.test_judging import decision_json, pack_for, unit_content


@pytest.mark.parametrize("model,enabled,expected", [
    ("DeepSeek-V4.1-Flash", False, {"thinking": {"type": "disabled"}}),
    ("GLM-4.6", False, {"thinking": {"type": "disabled"}}),
    ("Qwen3.5-27B", False, {"enable_thinking": False}),
    ("GLM-4.6", True, {"thinking": {"type": "enabled"}}),
    ("Qwen3.5-27B", True, {"enable_thinking": True}),
    ("Kimi-K3", None, {}),
])
def test_configured_generation_mode_reaches_http_request(
    model: str, enabled: bool | None, expected: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        _env_file=None, app_env="test", judge_1_provider="paratera",
        judge_1_model=model, judge_1_model_family="fixture",
        judge_1_base_url="https://example.invalid/v1", judge_1_api_key="fixture-key",
        judge_1_thinking_enabled=enabled,
    )
    slot = configured_slots(settings)[0]
    prepared = PreparedJudgeInput(
        pack_id=uuid4(), pack_hash="a" * 64, selected_ids=("E1",),
        system_prompt="Use only frozen evidence", user_prompt="Untrusted frozen evidence",
        prompt_hash="b" * 64, input_snapshot_version="judge-input-2.4",
        input_snapshot_hash="c" * 64, input_snapshot_json={},
    )
    bodies: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fixture-key"
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        "app.adapters.judge.httpx.AsyncClient",
        lambda **kwargs: client_type(transport=httpx.MockTransport(respond), **kwargs),
    )
    adapter = OpenAICompatibleJudgeProvider(1)
    asyncio.run(adapter.evaluate(slot, prepared))
    asyncio.run(adapter.evaluate(slot.model_copy(update={"thinking_enabled": None}), prepared))
    configured, default = bodies
    assert {k: v for k, v in configured.items() if k in expected} == expected
    assert {k: v for k, v in configured.items() if k not in expected} == default
    assert "thinking" not in default and "enable_thinking" not in default
    assert default["messages"] == [
        {"role": "system", "content": prepared.system_prompt},
        {"role": "user", "content": prepared.user_prompt},
    ]
    response_format = default["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert "tools" not in configured


@pytest.mark.parametrize("provider,model", [
    ("paratera", "Kimi-K3"),
    ("paratera", "unknown-model"),
    ("miri", "Qwen3.5-27B"),
    ("openai_compatible", "GLM-4.6"),
])
def test_unsupported_generation_override_is_rejected(provider: str, model: str) -> None:
    with pytest.raises(ValueError, match="thinking"):
        configured_slots(Settings(
            _env_file=None, app_env="test", judge_1_provider=provider,
            judge_1_model=model, judge_1_model_family="fixture",
            judge_1_base_url="https://example.invalid/v1", judge_1_thinking_enabled=False,
        ))


def test_settings_environment_preserves_false(monkeypatch: pytest.MonkeyPatch) -> None:
    for number in (1, 2, 3):
        monkeypatch.setenv(f"JUDGE_{number}_THINKING_ENABLED", "false")
    settings = Settings(_env_file=None)
    assert all(getattr(settings, f"judge_{number}_thinking_enabled") is False
               for number in (1, 2, 3))
    assert JudgeSlot(
        slot=1, provider="paratera", model="GLM-4.6", model_family="glm",
        base_url="https://example.invalid/v1",
    ).thinking_enabled is None


@pytest.mark.parametrize("succeed", [True, False])
def test_retry_and_audit_preserve_generation_mode(succeed: bool) -> None:
    seen: list[JudgeSlot] = []

    class Provider:
        async def evaluate(
            self, slot: JudgeSlot, prepared: PreparedJudgeInput,
        ) -> ProviderResponse:
            seen.append(slot)
            if len(seen) == 1:
                raise ProviderFailure("response_format_unsupported", retryable=True)
            if not succeed:
                raise ProviderFailure("provider_error", retryable=False)
            return ProviderResponse(content=unit_content(decision_json()))

    slot = JudgeSlot(
        slot=1, provider="paratera", model="GLM-4.6", model_family="glm",
        base_url="https://example.invalid/v1", thinking_enabled=False,
    )
    runs, _ = asyncio.run(JudgeService({"paratera": Provider()}).run(
        uuid4(), pack_for(), (slot,), app_env="test",
    ))
    assert [s.request_json_schema for s in seen] == [True, False]
    assert all(s.thinking_enabled is False for s in seen)
    assert runs[0].outcome_status == ("succeeded" if succeed else "failed")
    assert runs[0].response_json is not None
    assert runs[0].response_json["generation_options"] == {"thinking": {"type": "disabled"}}
