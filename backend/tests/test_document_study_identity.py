"""Publication-version evidence never substitutes for medical qualification."""

from datetime import date
from uuid import uuid4

from app.document.retrieval import _source_match, document_claim_snapshots
from app.retrieval.passages import extract_passages
from tests.test_document_retrieval import _document, _plan


def fixtures():
    plan = _plan()
    group = plan.groups[0].model_copy(
        update={
            "study_clues": (
                plan.assertions[0]
                .spans[0]
                .model_copy(
                    update={
                        "text": "Atlas Review: Exposure X and endpoint Y outcomes.",
                    }
                ),
            )
        }
    )
    claims = document_claim_snapshots(uuid4(), plan, group)
    claims["A1"] = claims["A1"].model_copy(
        update={"raw_text": "Duration of endpoint Y reduced by 7% in adults and 16% in children."}
    )
    documents = tuple(
        _document(
            str(i),
            "Exposure X and endpoint Y outcomes.",
            f"Duration of endpoint Y reduced by 7% in adults and {value}% in children.",
        ).model_copy(
            update={
                "journal": "Atlas Review",
                "publication_date": date(year, 1, 1),
            }
        )
        for i, value, year in ((1, 15.5, 2007), (2, 16, 2013))
    )
    return group, claims, documents


def match(group, claims, documents):
    passages = tuple(p for d in documents for p in extract_passages(d))
    return _source_match(
        group, claims, documents, passages, {p.passage_id: f"E{i}" for i, p in enumerate(passages)}
    )


def test_metadata_plus_distinct_bound_findings_disambiguates_versions_not_latest_date():
    group, claims, documents = fixtures()
    result = match(group, claims, documents)
    assert result.status == "identified"
    assert result.matched_document_ids == ("pubmed:2",)
    assert any("fingerprint" in e for e in result.candidates[0].matching_evidence)
    # A newer paper is not preferred just because it is newer.
    changed = documents[0].model_copy(update={"publication_date": date(2024, 1, 1)})
    assert match(group, claims, (changed, documents[1])).matched_document_ids == ("pubmed:2",)


def test_topic_or_title_alone_and_rounded_values_cannot_identify_the_version():
    group, claims, documents = fixtures()
    assert match(group, claims, (documents[0],)).status == "uncertain"
    without_metadata = tuple(d.model_copy(update={"journal": "Other Journal"}) for d in documents)
    assert match(group, claims, without_metadata).status == "uncertain"


def test_same_fingerprint_versions_remain_ambiguous_and_year_conflicts_exclude():
    group, claims, documents = fixtures()
    clone = documents[1].model_copy(update={"document_id": "pubmed:3", "pmid": "3"})
    assert match(group, claims, (documents[1], clone)).status == "uncertain"
    span = group.study_clues[0].model_copy(
        update={"text": group.study_clues[0].text + " Published in 2007."}
    )
    assert (
        match(group.model_copy(update={"study_clues": (span,)}), claims, documents).status
        == "uncertain"
    )


def test_population_bindings_and_interval_bounds_cannot_be_swapped():
    from app.document.study_identity import _percent_signatures

    assert _percent_signatures(
        "In adults duration was reduced by 7% (2% to 10%) and in children by 16% (9% to 21%)."
    ) == {("7", "adults"), ("16", "children")}
    assert _percent_signatures("Duration reduced by 7% for adults and 16% for children.") == {
        ("7", "adults"),
        ("16", "children"),
    }


def test_large_unrelated_abstract_cannot_crowd_out_study_reporting():
    from app.document.retrieval import _reported_selection

    group, claims, documents = fixtures()
    unrelated = _document("99", "Unrelated methods review", "participants study outcome " * 2000)
    passages = tuple(p for d in (*documents, unrelated) for p in extract_passages(d))
    selected = _reported_selection(_plan().assertions[0], passages, {"pubmed:2"})
    assert selected
    assert all(p.document_id == "pubmed:2" for p in passages if p.passage_id in selected)
