"""V2.5 development transport: findings plus frozen source quantity references."""

import json
from dataclasses import replace
from uuid import UUID

from app.judging.compact23 import deduplicated_wire_snapshot
from app.judging.compact24 import INSTRUCTIONS as INSTRUCTIONS24
from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.prompt import PreparedJudgeInput, input_snapshot_hash, prepare_judge_input
from app.retrieval.models import EvidencePack

VERSION = "judge-2.15-validated-evidence-position-2026-10-05"
INSTRUCTIONS = INSTRUCTIONS24.replace(
    "Propose supported, contradicted, or not_enough_evidence. The backend independently\n"
    "checks source attribution and evidence direction/scope/strength/role, then qualifies\n"
    "your proposal. Do not force a binary answer.",
    "The backend independently checks source attribution and evidence axes, then derives\n"
    "the evidence position. A final label is not required. Any label is advisory only.",
).replace(
    "Return strict JSON: label, statements, conclusion, uncertainty_reasons.",
    "Return strict JSON: statements, conclusion, uncertainty_reasons. Omit label;\n"
    "if present it is optional advisory text, never a backend evidence position.",
)


def prepare_compact25(pack_id: UUID, pack: EvidencePack) -> PreparedJudgeInput:
    base = prepare_judge_input(pack_id, pack, version="judge-input-2.5")
    user = "CLAIM DATA AND EVIDENCE DATA (untrusted JSON):\n" + json.dumps(
        deduplicated_wire_snapshot(base.input_snapshot_json), sort_keys=True,
        ensure_ascii=False, separators=(",", ":"),
    )
    return replace(base, system_prompt=INSTRUCTIONS, user_prompt=user, prompt_version=VERSION,
                   prompt_hash=input_snapshot_hash({"version": VERSION,
                                                    "system": INSTRUCTIONS, "user": user}))


def frozen_response_matches25(judge: JudgeRun, pack: EvidencePack) -> bool:
    """Reconstruct snapshot, prompt, raw response and audited ID transport exactly."""
    from app.judging.source_units import materialize_content, normalize_parent_unit_ids

    if not isinstance(judge.decision, JudgeDecisionV2) or judge.decision.schema_version != "2.5":
        return False
    try:
        prepared = prepare_compact25(judge.evidence_pack_id, pack)
        if (judge.claim_id != pack.claim_id or judge.evidence_pack_hash != pack.snapshot_hash
                or judge.input_snapshot_version != prepared.input_snapshot_version
                or judge.input_snapshot_hash != prepared.input_snapshot_hash
                or judge.input_snapshot_json is None
                or input_snapshot_hash(judge.input_snapshot_json) != prepared.input_snapshot_hash
                or judge.prompt_version != VERSION or judge.prompt_hash != prepared.prompt_hash):
            return False
        raw = (judge.response_json or {}).get("raw_model_content")
        if not isinstance(raw, str):
            return False
        normalized, changes = normalize_parent_unit_ids(raw, prepared.input_snapshot_json)
        recorded = (judge.response_json or {}).get("source_unit_id_normalizations", [])
        if input_snapshot_hash({"changes": recorded}) != input_snapshot_hash({"changes": changes}):
            return False
        decision = materialize_content(normalized, prepared.input_snapshot_json)
        if decision != judge.decision:
            return False
        if any((judge.response_json or {}).get(k) != v
               for k, v in decision.model_dump(mode="json").items()):
            return False
        passages = {p.evidence_id: p for p in pack.passages}
        documents = {d.document_id: d for d in pack.documents}
        for statement in decision.statements:
            for ref in statement.evidence_refs:
                document = documents[passages[ref.evidence_id].passage.document_id]
                if (not document.canonical_url or not (document.pmid or document.authoritative)
                        or document.integrity.status == "retracted"):
                    return False
        return True
    except (ValueError, TypeError, KeyError):
        return False
