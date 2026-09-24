import app.models  # noqa: F401
from app.db.base import Base
from app.models.enums import InputType
from app.models.submission import Submission


def test_initial_metadata_contains_required_phase_one_models() -> None:
    assert {
        "submission",
        "claim",
        "evidence_document",
        "evidence_passage",
        "model_evaluation",
        "final_verdict",
        "screenshot_upload",
    }.issubset(Base.metadata.tables)


def test_claim_to_submission_relationship_is_backed_by_a_foreign_key() -> None:
    claim_table = Base.metadata.tables["claim"]
    foreign_keys = claim_table.c.submission_id.foreign_keys

    assert len(foreign_keys) == 1
    assert next(iter(foreign_keys)).target_fullname == "submission.id"


def test_evidence_passage_reserves_a_pgvector_embedding_slot() -> None:
    embedding_type = str(Base.metadata.tables["evidence_passage"].c.embedding.type)

    assert "VECTOR(1024)" in embedding_type.upper()


def test_claim_has_phase_three_a_normalization_columns() -> None:
    claim_table = Base.metadata.tables["claim"]

    assert {"linked_entities", "pico_json", "normalization_status"}.issubset(claim_table.c.keys())
    assert str(claim_table.c.linked_entities.type).upper() == "JSONB"


def test_submission_input_type_uses_existing_lowercase_database_enum() -> None:
    column_type = Submission.__table__.c.input_type.type

    assert column_type.enums == [member.value for member in InputType]
