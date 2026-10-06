"""V2.4 development transport: findings plus frozen source quantity references."""

import json
from dataclasses import replace
from uuid import UUID

from app.judging.compact23 import ORIGINAL_INSTRUCTIONS, deduplicated_wire_snapshot
from app.judging.models import JudgeDecisionV2, JudgeRun
from app.judging.prompt import PreparedJudgeInput, input_snapshot_hash, prepare_judge_input
from app.retrieval.models import EvidencePack

VERSION = "judge-2.14-structured-numeric-development-2026-10-04"
INSTRUCTIONS = ORIGINAL_INSTRUCTIONS.split("Return strict JSON:")[0] + """
Return strict JSON: label, statements, conclusion, uncertainty_reasons.
Each statement: statement_id S1..S5, text (original attributed description),
qualitative_finding (separate source-grounded proposition), kind
study_finding|study_method|limitation, source_unit_ids, source_quantity_ids
(array, may be []), numeric_dependency (boolean).
Choose quantity IDs ONLY from source_quantity_catalog.items. Every quantity must
belong to one of that statement's source_unit_ids. Select each quantity once.
Do not emit numeric_details or numeric value fields, offsets, hashes, quotes or metadata.
The backend owns numeric values and literals. Prose may paraphrase quantities or
mention the submitted claim; it is retained for independent semantic attribution.
Prose is not the numeric fidelity transport. Do not invent conversions or stronger
inferences. PAF, OR, HR, RR, percentage points and relative percent are distinct.
Ambiguous 'times higher' does not permit inventing a percent change.
Use [] for qualitative findings that do not rely on an exact source quantity;
do not add unnecessary statistics. No quantity reference means no exact magnitude
premise, even if numbers appear in prose. numeric_dependency means an exact
magnitude/dose/duration/calculation is needed for the proposition, not merely that
the source contains statistics.
Conclusion: based_on_statement_ids, justification, qualitative_justification,
numeric_dependency. Every premise must occur in a referenced statement. Conclusion
has no independent quantity references; put any needed quantity in a statement.
No protocol/schema_version/evidence_refs. No markdown or hidden reasoning.
uncertainty_reasons ONLY: association_not_causation, indirect_evidence,
population_mismatch, exposure_mismatch, comparator_mismatch, outcome_mismatch,
timeframe_mismatch, numeric_mismatch, conflicting_evidence, limited_evidence,
integrity_uncertain, other; [] when none. Keep limits and genuine counterevidence.
Hard limits: five findings, 600 characters per finding, 1200 per justification.
Complete frozen text appears once in source_units. Bundles retain provenance.
"""


def prepare_compact24(pack_id: UUID, pack: EvidencePack) -> PreparedJudgeInput:
    base = prepare_judge_input(pack_id, pack, version="judge-input-2.4")
    user = "CLAIM DATA AND EVIDENCE DATA (untrusted JSON):\n" + json.dumps(
        deduplicated_wire_snapshot(base.input_snapshot_json), sort_keys=True,
        ensure_ascii=False, separators=(",", ":"),
    )
    return replace(base, system_prompt=INSTRUCTIONS, user_prompt=user, prompt_version=VERSION,
                   prompt_hash=input_snapshot_hash({"version": VERSION,
                                                    "system": INSTRUCTIONS, "user": user}))


def frozen_response_matches24(judge: JudgeRun, pack: EvidencePack) -> bool:
    """Reconstruct snapshot, prompt, raw response and audited ID transport exactly."""
    from app.judging.source_units import materialize_content, normalize_parent_unit_ids

    if not isinstance(judge.decision, JudgeDecisionV2) or judge.decision.schema_version != "2.4":
        return False
    try:
        prepared = prepare_compact24(judge.evidence_pack_id, pack)
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
