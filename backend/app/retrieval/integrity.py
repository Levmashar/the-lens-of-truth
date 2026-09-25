"""Conservative, source-attributed publication-integrity signal merging."""

from datetime import UTC, datetime

from app.retrieval.models import (
    CheckStatus,
    CrossrefEnrichment,
    DocumentIntegrity,
    IntegrityCheck,
    IntegrityReference,
    IntegrityStatus,
    PubMedDocument,
)

_VERSION = "integrity-1"
_PRIORITY: tuple[IntegrityStatus, ...] = (
    "retracted", "expression_of_concern", "corrected", "updated",
)
_PUBMED_RELATIONS: dict[str, IntegrityStatus] = {
    "retractionin": "retracted",
    "retractedandrepublishedin": "retracted",
    "expressionofconcernin": "expression_of_concern",
    "erratumin": "corrected",
    "correctedandrepublishedin": "corrected",
    "updatein": "updated",
    "republishedin": "updated",
    "retractionof": "updated",  # A notice is not itself the retracted article.
    "erratumfor": "updated",
    "expressionofconcernfor": "updated",
    "updateof": "updated",
    "correctedandrepublishedfrom": "updated",
}
_PUBMED_TYPES: dict[str, IntegrityStatus] = {
    "retracted publication": "retracted",
    "expression of concern": "expression_of_concern",
    "corrected and republished article": "corrected",
    "retraction notice": "updated",
    "published erratum": "updated",
}


def pubmed_integrity(
    publication_types: tuple[str, ...], references: tuple[IntegrityReference, ...],
    *, metadata_present: bool, checked_at: datetime,
) -> DocumentIntegrity:
    """Only structured citation fields count; never classify from title text."""

    signals = [_PUBMED_TYPES[value.casefold()] for value in publication_types
               if value.casefold() in _PUBMED_TYPES]
    signals.extend(ref.signal for ref in references if ref.signal is not None)
    status: IntegrityStatus = next((item for item in _PRIORITY if item in signals), "unknown")
    check_status: CheckStatus = "checked" if metadata_present else "unavailable"
    check = IntegrityCheck(
        source="pubmed", status=check_status, checked_at=checked_at,
        version="pubmed-efetch-1",
    )
    warnings = () if metadata_present else ("pubmed_integrity_metadata_absent",)
    return DocumentIntegrity(
        status=status, sources=("pubmed",), checked_at=checked_at,
        check_version=_VERSION, warnings=warnings, references=references,
        checks=(check,),
    )


def pubmed_reference(relation: str, pmid: str) -> IntegrityReference | None:
    signal = _PUBMED_RELATIONS.get(relation.casefold())
    if signal is None or not pmid.isdigit():
        return None
    return IntegrityReference(
        source="pubmed", relation=relation, identifier=pmid,
        identifier_type="pmid", signal=signal,
    )


def merge_integrity(
    document: PubMedDocument, crossref: CrossrefEnrichment,
) -> DocumentIntegrity:
    """A positive warning wins; clean status requires all applicable checks."""

    pubmed = document.integrity
    references = (*pubmed.references, *crossref.references)
    checks = (*pubmed.checks, crossref.check)
    signals = [ref.signal for ref in references if ref.signal is not None]
    # A publication-type-only PubMed signal has no linked reference.
    if pubmed.status not in {"valid", "unknown"}:
        signals.append(pubmed.status)
    status: IntegrityStatus = next(
        (item for item in _PRIORITY if item in signals), "unknown"
    )
    complete = all(check.status in {"checked", "not_applicable"} for check in checks)
    if status == "unknown" and complete:
        status = "valid"
    warnings = list(pubmed.warnings)
    if crossref.check.status not in {"checked", "not_applicable"}:
        warnings.append(f"crossref_{crossref.check.status}")
    if status == "unknown":
        warnings.append("integrity_partially_checked")
    if pubmed.status not in {"valid", "unknown"} and any(
        ref.source == "crossref" and ref.signal not in {None, pubmed.status}
        for ref in crossref.references
    ):
        warnings.append("integrity_sources_disagree")
    checked_times = [check.checked_at for check in checks if check.checked_at is not None]
    return DocumentIntegrity(
        status=status, sources=tuple(check.source for check in checks),
        checked_at=max(checked_times) if checked_times else None,
        check_version=_VERSION, warnings=tuple(dict.fromkeys(warnings)),
        references=references, checks=checks,
    )


def unavailable_crossref(
    doi: str | None, *, checked_at: datetime | None = None,
) -> CrossrefEnrichment:
    status: CheckStatus = "unavailable" if doi else "not_applicable"
    return CrossrefEnrichment(
        check=IntegrityCheck(
            source="crossref", status=status, checked_at=checked_at, version="crossref-rest-1",
        ),
        doi=doi,
    )


def failed_crossref(doi: str, failure_type: str) -> CrossrefEnrichment:
    return CrossrefEnrichment(
        check=IntegrityCheck(
            source="crossref", status="failed", checked_at=datetime.now(UTC),
            version="crossref-rest-1", failure_type=failure_type,
        ),
        doi=doi,
    )
