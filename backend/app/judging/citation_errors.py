"""Structured citation defects without retaining provider prose or secret inputs."""


class _CitationDiagnostics(Exception):
    def __init__(
        self, message: str, *, statement_id: str | None = None,
        reference_field: str, offending_id: str,
        expected_allowed_ids: tuple[str, ...],
        source_unit_id: str | None = None, evidence_id: str | None = None,
        expected_unit_ids: tuple[str, ...] = (),
    ) -> None:
        self.statement_id = statement_id
        self.reference_field = reference_field
        self.offending_id = offending_id
        self.expected_allowed_ids = expected_allowed_ids
        self.source_unit_id = source_unit_id
        self.evidence_id = evidence_id
        self.expected_unit_ids = expected_unit_ids
        super().__init__(message)

    def bind_statement(self, statement_id: str) -> None:
        self.statement_id = statement_id


class CitationReferenceError(_CitationDiagnostics, ValueError):
    """A reference defect that retains the existing ValueError contract."""


class SourceUnitReferenceError(_CitationDiagnostics, KeyError):
    """An unknown unit retains the existing KeyError/categorization contract."""


def citation_error_details(exc: BaseException) -> dict[str, object] | None:
    """Return only reference metadata, never the statement or response content."""

    if not isinstance(exc, _CitationDiagnostics):
        return None
    result: dict[str, object] = {
        "statement_id": exc.statement_id,
        "reference_field": exc.reference_field,
        "offending_id": exc.offending_id,
        "expected_allowed_ids": list(exc.expected_allowed_ids),
        "exception_type": type(exc).__name__,
        "message": str(exc),
    }
    if exc.source_unit_id is not None:
        result["source_unit_id"] = exc.source_unit_id
    if exc.reference_field == "source_quantity_ids" or ".Q" in exc.offending_id:
        result["source_quantity_id"] = exc.offending_id
    if exc.evidence_id is not None:
        result["evidence_id"] = exc.evidence_id
    if exc.expected_unit_ids:
        result["expected_unit_ids"] = list(exc.expected_unit_ids)
    return result
