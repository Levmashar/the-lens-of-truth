"""The development wire view avoids duplicate data without changing frozen evidence."""

import asyncio
import json
from uuid import uuid4

from app.judging.compact23 import (
    PREVIOUS_VERSION,
    VERSION,
    deduplicated_wire_snapshot,
    prepare_compact23,
)
from app.judging.models import JudgeSlot, ProviderResponse
from app.judging.prompt import input_snapshot_hash, prepare_judge_input
from app.judging.service import JudgeService
from tests.test_judging import decision_json, pack_for, unit_content


def test_wire_snapshot_keeps_all_source_units_and_frozen_audit_input() -> None:
    pack = pack_for()
    pack_id = uuid4()
    prepared = prepare_compact23(pack_id, pack)
    baseline = prepare_judge_input(pack_id, pack, version="judge-input-2.3")
    prefix = "CLAIM DATA AND EVIDENCE DATA (untrusted JSON):\n"
    wire, _ = json.JSONDecoder().raw_decode(prepared.user_prompt[len(prefix):])

    assert prepared.prompt_version == VERSION
    assert prepared.input_snapshot_json == baseline.input_snapshot_json
    assert prepared.input_snapshot_hash == input_snapshot_hash(baseline.input_snapshot_json)
    assert wire["source_units"] == baseline.input_snapshot_json["source_units"]
    assert tuple(wire["selected_evidence_ids"]) == baseline.input_snapshot_json[
        "selected_evidence_ids"
    ]
    assert all("text" not in passage for bundle in wire["document_bundles"]
               for passage in bundle["passages"])
    assert all("text" in passage for bundle in baseline.input_snapshot_json["document_bundles"]
               for passage in bundle["passages"])
    assert len(prepared.user_prompt) < len(baseline.user_prompt)
    assert prepare_compact23(pack_id, pack).prompt_hash == prepared.prompt_hash


def test_authoritative_reference_urls_are_audited_but_not_sent_twice() -> None:
    snapshot: dict[str, object] = {
        "document_bundles": [{
            "document": {"authoritative": {"reference_urls": ["https://example.org/a"],
                                           "document_purpose": "assessment"}},
            "passages": [{"evidence_id": "E1", "text": "Frozen complete source unit"}],
        }],
        "source_units": [{"unit_id": "E1.U1", "text": "Frozen complete source unit"}],
    }
    wire = deduplicated_wire_snapshot(snapshot)
    assert wire["source_units"] == snapshot["source_units"]
    assert wire["document_bundles"][0]["document"]["authoritative"] == {
        "document_purpose": "assessment", "reference_url_count": 1,
    }
    assert snapshot["document_bundles"][0]["document"]["authoritative"]["reference_urls"] == [
        "https://example.org/a",
    ]


def test_previous_prompt_version_replays_without_projection() -> None:
    pack = pack_for()
    pack_id = uuid4()
    old = prepare_compact23(pack_id, pack, version=PREVIOUS_VERSION)
    assert "\"text\":\"Sunscreen use was associated" in old.user_prompt
    assert old.prompt_version == PREVIOUS_VERSION


def test_same_gateway_judges_are_serial_but_other_gateway_remains_parallel() -> None:
    class TrackingProvider:
        def __init__(self) -> None:
            self.active: dict[str, int] = {}
            self.peak: dict[str, int] = {}
            self.total_peak = 0

        async def evaluate(self, slot: JudgeSlot, prepared: object) -> ProviderResponse:
            endpoint = slot.base_url
            self.active[endpoint] = self.active.get(endpoint, 0) + 1
            self.peak[endpoint] = max(self.peak.get(endpoint, 0), self.active[endpoint])
            self.total_peak = max(self.total_peak, sum(self.active.values()))
            await asyncio.sleep(0.02)
            self.active[endpoint] -= 1
            return ProviderResponse(content=unit_content(decision_json()))

    provider = TrackingProvider()
    slots = tuple(JudgeSlot(
        slot=i, provider="openai_compatible", model=f"model-{i}",
        model_family=f"family-{i}",
        base_url="https://gateway.example/v1" if i != 2 else "https://other.example/v1",
    ) for i in (1, 2, 3))
    runs, _ = asyncio.run(JudgeService({"openai_compatible": provider}).run(
        uuid4(), pack_for(), slots,
    ))
    assert all(run.outcome_status == "succeeded" for run in runs)
    assert provider.peak["https://gateway.example/v1"] == 1
    assert provider.total_peak == 2
