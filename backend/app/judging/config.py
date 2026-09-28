"""Resolve explicit judge slots without guessing model family from an alias."""

import re

from app.core.config import Settings
from app.judging.models import JudgeSlot


def is_search_enabled_model(model: str) -> bool:
    """Conservative name guard for gateway modes that may search or browse."""

    return bool(re.search(r"(?:search|research|browse)", model, re.I))


def configured_slots(settings: Settings) -> tuple[JudgeSlot, ...]:
    slots: list[JudgeSlot] = []
    search_override_allowed = (
        settings.app_env in {"development", "test"}
        and settings.judge_allow_search_enabled_development
    )
    for number in (1, 2, 3):
        prefix = f"judge_{number}_"
        provider = getattr(settings, prefix + "provider")
        model = getattr(settings, prefix + "model")
        family = getattr(settings, prefix + "model_family")
        base_url = getattr(settings, prefix + "base_url")
        secret = getattr(settings, prefix + "api_key")
        if not any((provider, model, family, base_url, secret)):
            continue
        if not provider or not model or not family:
            raise ValueError(f"Judge slot {number} requires provider, model, and model_family")
        if is_search_enabled_model(model) and not search_override_allowed:
            raise ValueError(f"Judge slot {number} uses a search-enabled model mode")
        if provider == "miri":
            base_url = base_url or settings.claim_extractor_base_url
            secret = secret or settings.claim_extractor_api_key
        if not base_url:
            raise ValueError(f"Judge slot {number} requires a base URL")
        slots.append(JudgeSlot(
            slot=number, provider=provider, model=model, model_family=family,
            base_url=base_url,
            api_key=secret.get_secret_value() if secret else None,
        ))
    if search_override_allowed and any(is_search_enabled_model(slot.model) for slot in slots):
        slots = [slot.model_copy(update={
            "search_override_active": True,
            "search_guard_bypassed": is_search_enabled_model(slot.model),
        }) for slot in slots]
    families = [slot.model_family.casefold() for slot in slots]
    allow_override = (settings.app_env in {"development", "test"}
                      and settings.judge_allow_same_family_development)
    if not allow_override and len(families) != len(set(families)):
        raise ValueError("Configured judge slots must have distinct model families")
    return tuple(slots)
