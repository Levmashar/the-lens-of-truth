"""Document-owned assertions and exact, source-grounded context contracts."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.pipeline.pico import NormalizedPico

PLAN_VERSION = "document-plan-1.0"
MAX_DOCUMENT_CHARACTERS = 20_000
MAX_GROUP_ASSERTIONS = 8
MAX_GROUP_ITEMS = 64


class DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceSpan(DocumentModel):
    start: int = Field(ge=0, le=MAX_DOCUMENT_CHARACTERS)
    end: int = Field(gt=0, le=MAX_DOCUMENT_CHARACTERS)
    text: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARACTERS)

    @model_validator(mode="after")
    def valid_bounds(self) -> "SourceSpan":
        if self.end <= self.start:
            raise ValueError("Source span must have positive width")
        return self


AssertionKind = Literal[
    "reported_study_fact",
    "general_medical_assertion",
    "interpretation",
    "methodology",
    "sample_size",
    "commentary",
    "repetition",
    "unclassified",
]


class ContextLink(DocumentModel):
    link_id: str = Field(pattern=r"^L[1-9][0-9]*$")
    reference: SourceSpan
    target: SourceSpan | None = None
    relationship: Literal["study_reference", "shared_exposure", "reported_result", "same_topic"]
    resolved: bool

    @model_validator(mode="after")
    def valid_resolution(self) -> "ContextLink":
        if self.resolved != (self.target is not None):
            raise ValueError("Resolved context must name an exact source target")
        return self


class DocumentAssertion(DocumentModel):
    assertion_id: str = Field(pattern=r"^A[1-9][0-9]*$")
    ordinal: int = Field(ge=1)
    kind: AssertionKind
    spans: tuple[SourceSpan, ...] = Field(min_length=1)
    normalized_text: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARACTERS)
    pico: NormalizedPico
    study_id: str | None = None
    risk_class: Literal["standard", "high", "unknown"] = "unknown"
    context_link_ids: tuple[str, ...] = ()
    duplicate_of: str | None = None
    planning_status: Literal["ready", "unresolved", "not_checkable"] = "ready"
    uncertainty_reasons: tuple[str, ...] = ()

    @property
    def source_text(self) -> str:
        """The first exact occurrence; repeated occurrences remain in spans."""
        return self.spans[0].text

    @property
    def checkable(self) -> bool:
        return self.kind not in {"commentary", "repetition"}


class DocumentGroup(DocumentModel):
    group_id: str = Field(pattern=r"^G[1-9][0-9]*$")
    title: str = Field(min_length=1, max_length=300)
    assertion_ids: tuple[str, ...] = Field(min_length=1, max_length=MAX_GROUP_ITEMS)
    study_id: str | None = None
    study_clues: tuple[SourceSpan, ...] = ()
    context_spans: tuple[SourceSpan, ...] = ()


class DocumentPlan(DocumentModel):
    version: Literal["document-plan-1.0"] = "document-plan-1.0"
    original_text: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARACTERS)
    original_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    assertions: tuple[DocumentAssertion, ...]
    groups: tuple[DocumentGroup, ...]
    context_links: tuple[ContextLink, ...] = ()
    warnings: tuple[str, ...] = ()
    planning_audit: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def exact_shared_provenance(self) -> "DocumentPlan":
        if hashlib.sha256(self.original_text.encode()).hexdigest() != self.original_sha256:
            raise ValueError("Document source hash mismatch")
        ids = [assertion.assertion_id for assertion in self.assertions]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate assertion ID")
        group_ids = [group.group_id for group in self.groups]
        if len(set(group_ids)) != len(group_ids):
            raise ValueError("Duplicate group ID")
        grouped = [aid for group in self.groups for aid in group.assertion_ids]
        if len(set(grouped)) != len(grouped) or set(grouped) != set(ids):
            raise ValueError("Every assertion must belong to exactly one document group")
        links = {link.link_id: link for link in self.context_links}
        if len(links) != len(self.context_links):
            raise ValueError("Duplicate context link ID")
        spans = [span for assertion in self.assertions for span in assertion.spans]
        spans += [
            span for group in self.groups for span in (*group.study_clues, *group.context_spans)
        ]
        spans += [link.reference for link in self.context_links]
        spans += [link.target for link in self.context_links if link.target is not None]
        if any(self.original_text[span.start : span.end] != span.text for span in spans):
            raise ValueError("Document span does not match original source")
        for assertion in self.assertions:
            if assertion.normalized_text != assertion.source_text:
                raise ValueError("Document assertions cannot replace source text with a summary")
            if any(lid not in links for lid in assertion.context_link_ids):
                raise ValueError("Unknown assertion context link")
            for lid in assertion.context_link_ids:
                reference = links[lid].reference
                if not any(
                    span.start <= reference.start < reference.end <= span.end
                    for span in assertion.spans
                ):
                    raise ValueError("Context reference is outside its assertion")
            if assertion.duplicate_of is not None and assertion.duplicate_of not in ids:
                raise ValueError("Unknown duplicate assertion target")
        # Every non-whitespace source character stays represented, including
        # commentary and planner omissions explicitly retained as unresolved.
        covered = bytearray(len(self.original_text))
        for assertion in self.assertions:
            for span in assertion.spans:
                covered[span.start : span.end] = b"\x01" * (span.end - span.start)
        if any(
            not covered[index] and not character.isspace()
            for index, character in enumerate(self.original_text)
        ):
            raise ValueError("Document plan silently omits source content")
        return self

    def assertion(self, assertion_id: str) -> DocumentAssertion:
        return next(
            assertion for assertion in self.assertions if assertion.assertion_id == assertion_id
        )

    def group(self, group_id: str) -> DocumentGroup:
        return next(group for group in self.groups if group.group_id == group_id)


def canonical_document_hash(snapshot: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            snapshot,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
