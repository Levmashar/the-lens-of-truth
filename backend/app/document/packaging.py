"""Lossless quantity-table view and source-only metadata for grouped prompts."""

from typing import Any

from app.retrieval.models import EvidencePack

LEGACY_INPUT_VERSION = "document-group-input-1.0"
TABLE_INPUT_VERSION = "document-group-input-1.1"
INPUT_VERSION = "document-group-input-1.2"
QUANTITY_COLUMNS = (
    "quantity_id",
    "source_unit_id",
    "evidence_id",
    "start",
    "end",
    "literal",
    "measure",
    "values",
    "unit",
    "binding",
    "normalization_reason",
)


def source_view(
    pack: EvidencePack, snapshot: dict[str, Any], *, version: str = INPUT_VERSION
) -> dict[str, Any]:
    if version == LEGACY_INPUT_VERSION:
        return {
            "source_units": snapshot["source_units"],
            "source_quantity_catalog": snapshot["source_quantity_catalog"],
            "documents": [
                d.model_dump(mode="json", exclude={"abstract", "abstract_sections"})
                for d in pack.documents
            ],
        }
    if version not in {INPUT_VERSION, TABLE_INPUT_VERSION}:
        raise ValueError("Unknown document group input version")
    catalog = snapshot["source_quantity_catalog"]
    quantities = {
        "version": catalog["version"],
        "view_version": "source-quantity-table-1.0",
        "columns": list(QUANTITY_COLUMNS),
        "rows": [[item[column] for column in QUANTITY_COLUMNS] for item in catalog["items"]],
    }
    if version == INPUT_VERSION:
        # Lossless dictionary encoding of repeated parser explanations. Source
        # values, IDs, units, ranges and offsets remain literal and complete.
        column = QUANTITY_COLUMNS.index("normalization_reason")
        reasons = list(dict.fromkeys(row[column] for row in quantities["rows"]))
        quantities["view_version"] = "source-quantity-table-1.1"
        quantities["dictionary_columns"] = {"normalization_reason": reasons}
        for row in quantities["rows"]:
            row[column] = reasons.index(row[column])
    selected_documents = {unit["document_id"] for unit in snapshot["source_units"]}
    documents = []
    for document in pack.documents:
        if document.document_id not in selected_documents:
            continue
        metadata = document.model_dump(
            mode="json",
            include={
                "document_id",
                "title",
                "pmid",
                "doi",
                "canonical_url",
                "source_kind",
                "publication_types",
                "study_design",
                "integrity",
                "relationship_analysis",
            },
        )
        if metadata["relationship_analysis"] is not None:
            metadata["relationship_analysis"].pop("evidence_text", None)
        documents.append(metadata)
    return {
        "source_units": snapshot["source_units"],
        "source_quantity_catalog": quantities,
        "documents": documents,
    }


def expand_quantity_view(view: dict[str, Any]) -> dict[str, Any]:
    """Round-trip invariant: no quantity, numeric field or ownership is omitted."""
    if (
        view.get("view_version") not in {"source-quantity-table-1.0", "source-quantity-table-1.1"}
        or view.get("columns") != list(QUANTITY_COLUMNS)
        or not isinstance(view.get("rows"), list)
        or any(
            not isinstance(row, list) or len(row) != len(QUANTITY_COLUMNS) for row in view["rows"]
        )
    ):
        raise ValueError("Invalid source quantity table view")
    rows = [list(row) for row in view["rows"]]
    if view["view_version"] == "source-quantity-table-1.1":
        dictionary = view.get("dictionary_columns", {}).get("normalization_reason")
        if not isinstance(dictionary, list) or any(
            v is not None and not isinstance(v, str) for v in dictionary
        ):
            raise ValueError("Invalid quantity dictionary")
        column = QUANTITY_COLUMNS.index("normalization_reason")
        for row in rows:
            if type(row[column]) is not int or not 0 <= row[column] < len(dictionary):
                raise ValueError("Invalid quantity dictionary reference")
            row[column] = dictionary[row[column]]
    return {
        "version": view["version"],
        "items": [dict(zip(QUANTITY_COLUMNS, row, strict=True)) for row in rows],
    }
