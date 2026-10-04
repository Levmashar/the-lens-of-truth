"""Read the configured gateway catalog without returning credentials or endpoints."""

import re

import httpx

from app.judging.models import JudgeSlot


async def discover_models(slot: JudgeSlot) -> list[dict[str, object]]:
    headers = {"Authorization": f"Bearer {slot.api_key}"} if slot.api_key else {}
    async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
        response = await client.get(f"{slot.base_url.rstrip('/')}/models", headers=headers)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Invalid model catalog")
    entries = payload.get("data", [])
    if not isinstance(entries, list):
        raise ValueError("Invalid model catalog")
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        identifier = entry.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[\w./:-]{1,128}", identifier, re.ASCII,
        ):
            continue
        kind = str(entry.get("type", "unknown"))
        searchable = bool(re.search(r"search|research|browser|browse", identifier, re.I))
        chat = kind == "openai/chat-completions"
        result.append({
            "provider": slot.provider, "model": identifier,
            "claimed_family": identifier.split("/")[0], "endpoint_type": kind,
            "search_mode": searchable, "structured_output": "unverified",
            "eligible": chat and not searchable,
            "exclusion": "search_mode" if searchable else None if chat else "not_chat_endpoint",
        })
    return result
