"""Source-owned ellipsis keeps its agent/endpoint without inheriting dosage."""

from hashlib import sha256
from uuid import uuid4

import pytest

from app.document.models import (
    ContextLink,
    DocumentAssertion,
    DocumentGroup,
    DocumentPlan,
    SourceSpan,
)
from app.document.retrieval import document_claim_snapshots
from app.medical.linker import MedicalEntityLinker
from app.medical.mesh import LocalMeshProvider
from app.medical.umls import UnconfiguredUmlsProvider
from app.pipeline.pico import NormalizedPico


@pytest.mark.parametrize("relationship", ["shared_exposure", "same_topic"])
def test_only_an_explicit_medical_dependency_resolves_vague_dose_framing(relationship):
    parent = "Authors argue that 100 mg of Agent X prevents infection Z."
    child = "They suggest that higher doses provide stronger protection."
    text = parent + " " + child
    assertions = tuple(
        DocumentAssertion(
            assertion_id=f"A{i}",
            ordinal=i,
            kind="general_medical_assertion",
            spans=(SourceSpan(start=start, end=start + len(raw), text=raw),),
            normalized_text=raw,
            pico=NormalizedPico(
                original_claim=raw,
                intervention_or_exposure=exposure,
                outcome=outcome,
                claim_type="prevention",
            ),
            context_link_ids=("L1",) if i == 2 else (),
        )
        for i, raw, start, exposure, outcome in (
            (1, parent, 0, "100 mg of Agent X", "infection Z"),
            (2, child, len(parent) + 1, "higher doses", "protection"),
        )
    )
    group = DocumentGroup(group_id="G1", title="Attributed claims", assertion_ids=("A1", "A2"))
    begin = text.index("higher doses")
    target = text.index("100 mg of Agent X")
    plan = DocumentPlan(
        original_text=text,
        original_sha256=sha256(text.encode()).hexdigest(),
        assertions=assertions,
        groups=(group,),
        context_links=(
            ContextLink(
                link_id="L1",
                reference=SourceSpan(
                    start=begin, end=begin + len("higher doses"), text="higher doses"
                ),
                target=SourceSpan(
                    start=target, end=target + len("100 mg of Agent X"), text="100 mg of Agent X"
                ),
                resolved=True,
                relationship=relationship,
            ),
        ),
    )
    linker = MedicalEntityLinker(
        UnconfiguredUmlsProvider(),
        LocalMeshProvider(
            {"Agent X": ("D000001", "Agent X", 1.0), "infection Z": ("D000002", "infection Z", 1.0)}
        ),
    )
    result = document_claim_snapshots(uuid4(), plan, group, linker)["A2"]
    if relationship == "shared_exposure":
        assert result.pico.intervention_or_exposure == "Agent X"
        assert result.pico.outcome == "infection Z"
        assert "100" not in result.pico.intervention_or_exposure
    else:
        assert result.pico.intervention_or_exposure == "higher doses"
        assert result.pico.outcome == "protection"
    assert result.raw_text == child and "higher doses" in result.pico.original_claim
