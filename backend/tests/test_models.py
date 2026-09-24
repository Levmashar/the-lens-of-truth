import app.models  # noqa: F401
from app.db.base import Base


def test_initial_metadata_contains_required_phase_one_models() -> None:
    assert {
        "submission",
        "claim",
        "evidence_document",
        "evidence_passage",
        "model_evaluation",
        "final_verdict",
    }.issubset(Base.metadata.tables)


def test_claim_to_submission_relationship_is_backed_by_a_foreign_key() -> None:
    claim_table = Base.metadata.tables["claim"]
    foreign_keys = claim_table.c.submission_id.foreign_keys

    assert len(foreign_keys) == 1
    assert next(iter(foreign_keys)).target_fullname == "submission.id"


def test_evidence_passage_reserves_a_pgvector_embedding_slot() -> None:
    embedding_type = str(Base.metadata.tables["evidence_passage"].c.embedding.type)

    assert "VECTOR(1024)" in embedding_type.upper()
