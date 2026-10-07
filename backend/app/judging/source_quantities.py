"""Frozen backend-owned quantities. Change extraction only under a new catalog version."""

import hashlib
import re

from pydantic import BaseModel, ConfigDict, Field

from app.judging.citation_errors import CitationReferenceError
from app.judging.source_units import SourceUnit
from app.validation.numeric_effects import Measure, NumericQuantity, parse_quantities

VERSION = "source-quantity-catalog-1.0"


class QuantityReferenceError(CitationReferenceError):
    """Model-selected reference defect, distinct from ambiguous source evidence."""


class SourceQuantity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    quantity_id: str = Field(pattern=r"^E[1-9][0-9]*\.U[1-9][0-9]*\.Q[1-9][0-9]*$")
    source_unit_id: str
    evidence_id: str
    start: int
    end: int
    literal: str
    measure: Measure
    values: tuple[str, ...]
    unit: str | None
    binding: str | None
    normalization_reason: str | None

    def typed(self) -> NumericQuantity:
        return NumericQuantity(
            values=self.values, kind=self.measure, unit=self.unit, literal=self.literal,
            binding=self.binding, normalization_reason=self.normalization_reason,
            start=self.start, end=self.end,
        )


def derive_catalog(raw_units: object) -> dict[str, object]:
    """Offsets are half-open Unicode character offsets relative to the frozen unit.

    The existing typed source extractor is pinned to its 1.1 followup behavior.
    Never extract judge prose here. Unbound spans remain unknown, with no arithmetic.
    """
    if not isinstance(raw_units, list):
        raise ValueError("Frozen source units missing")
    units = [SourceUnit.model_validate(raw) for raw in raw_units]
    if len({u.unit_id for u in units}) != len(units):
        raise ValueError("Duplicate frozen source unit")
    items = []
    for source in units:
        if (hashlib.sha256(source.text.encode("utf-8")).hexdigest() != source.passage_sha256
                or source.start != 0 or source.end != len(source.text)):
            raise ValueError("Corrupt frozen source unit")
        quantities: list[NumericQuantity] = []
        candidates = sorted(parse_quantities(source.text, followup=True)[0],
                            key=lambda q: (q.start or 0, -(q.end or 0)))
        for q in candidates:
            if q.start is None or q.end is None:
                continue  # Unlocated/ambiguous legacy results cannot become typed estimates.
            if any(previous.start is not None and previous.end is not None
                   and previous.start < q.end and q.start < previous.end
                   for previous in quantities):
                continue  # A residual extractor cannot reinterpret part of a typed decimal.
            quantities.append(q)
        occupied = [(q.start, q.end) for q in quantities]
        for match in re.finditer(r"\d+(?:\.\d+)?", source.text):
            if not any(start <= match.start() and match.end() <= end
                       for start, end in occupied if start is not None and end is not None):
                quantities.append(NumericQuantity(
                    values=(match.group(),), kind=Measure.UNKNOWN, literal=match.group(),
                    start=match.start(), end=match.end(),
                    normalization_reason="unbound_source_numeral_no_conversion",
                ))
        unique = {(q.start, q.end, q.kind, q.values, q.unit, q.binding): q for q in quantities}
        ordered = sorted(unique.values(), key=lambda q: (
            q.start or 0, q.end or 0, q.kind, q.values, q.unit or "", q.binding or "",
        ))
        for index, q in enumerate(ordered, 1):
            assert q.start is not None and q.end is not None
            items.append(SourceQuantity(
                quantity_id=f"{source.unit_id}.Q{index}", source_unit_id=source.unit_id,
                evidence_id=source.evidence_id, start=q.start, end=q.end,
                literal=source.text[q.start:q.end], measure=q.kind, values=q.values,
                unit=q.unit, binding=q.binding, normalization_reason=q.normalization_reason,
            ).model_dump(mode="json"))
    return {"version": VERSION, "items": items}


def catalog_items(snapshot: dict[str, object]) -> dict[str, SourceQuantity]:
    """Reject changed catalog content even when someone also recomputes its hash."""
    expected = derive_catalog(snapshot.get("source_units"))
    if snapshot.get("source_quantity_catalog") != expected:
        raise ValueError("Frozen quantity catalog identity mismatch")
    raw_items = expected["items"]
    assert isinstance(raw_items, list)
    return {q.quantity_id: q for q in (SourceQuantity.model_validate(i) for i in raw_items)}


def check_quantity_refs(ids: tuple[str, ...], unit_ids: tuple[str, ...],
                        catalog: dict[str, SourceQuantity]) -> None:
    allowed = tuple(identifier for identifier, quantity in catalog.items()
                    if quantity.source_unit_id in unit_ids)
    if len(ids) != len(set(ids)):
        duplicate = next(identifier for index, identifier in enumerate(ids)
                         if identifier in ids[:index])
        raise QuantityReferenceError(
            "Duplicate source quantity reference", reference_field="source_quantity_ids",
            offending_id=duplicate, expected_allowed_ids=allowed,
            expected_unit_ids=unit_ids,
        )
    for identifier in ids:
        quantity = catalog.get(identifier)
        if quantity is None:
            raise QuantityReferenceError(
                "Unknown source quantity reference", reference_field="source_quantity_ids",
                offending_id=identifier, expected_allowed_ids=allowed,
                expected_unit_ids=unit_ids,
            )
        if quantity.source_unit_id not in unit_ids:
            raise QuantityReferenceError(
                "Source quantity belongs to an uncited unit",
                reference_field="source_quantity_ids", offending_id=identifier,
                expected_allowed_ids=allowed, source_unit_id=quantity.source_unit_id,
                evidence_id=quantity.evidence_id, expected_unit_ids=unit_ids,
            )
