"""Development preview exposes frozen PubMed evidence without a verdict."""

from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from app.adapters.pubmed import PubMedAdapter
from app.core.config import Settings
from app.db.session import get_db_session
from app.dependencies import get_analysis_ingestion_service, get_pubmed_adapter
from app.main import create_app
from app.models.claim import Claim
from app.pipeline.pico import NormalizedPico

XML = (Path(__file__).parent / "fixtures" / "pubmed_sample.xml").read_bytes()


def test_evidence_preview_returns_pack_without_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    analysis_id, claim_id = uuid4(), uuid4()
    original = "Frequent sunscreen use causes invasive melanoma."
    claim = Claim(
        id=claim_id, submission_id=analysis_id, ordinal=1,
        raw_text=original, claim_type="causal", risk_class="standard",
        coreference_uncertain=False, normalization_status="normalized",
        pico_json=NormalizedPico(
            original_claim=original, intervention_or_exposure="Frequent sunscreen use",
            outcome="invasive melanoma", claim_type="causal",
        ).model_dump(mode="json"),
        linked_entities=[],
    )

    class FakeSession:
        def get(self, _model: object, _identifier: object) -> Claim:
            return claim

    class FakeService:
        def get_submission(self, *, session: object, analysis_id: object) -> object:
            return object()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("esearch.fcgi"):
            return httpx.Response(200, json={"esearchresult": {"idlist": ["12345678"]}})
        return httpx.Response(200, content=XML)

    adapter = PubMedAdapter(
        tool="lens_test", email="test@example.org", max_retries=0,
        minimum_interval_seconds=0, client=httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://eutils.ncbi.nlm.nih.gov/entrez/eutils/",
        ),
    )
    persisted: list[str] = []
    monkeypatch.setattr("app.api.routes.analyses.persist_retrieval",
                        lambda _session, result: persisted.append(result.pack.snapshot_hash))
    app = create_app(Settings(app_env="test"))
    app.dependency_overrides[get_db_session] = FakeSession
    app.dependency_overrides[get_analysis_ingestion_service] = FakeService
    app.dependency_overrides[get_pubmed_adapter] = lambda: adapter
    with TestClient(app) as client:
        response = client.post("/v1/analyses/evidence-preview", json={
            "analysis_id": str(analysis_id), "claim_id": str(claim_id),
        })
    assert response.status_code == 200
    body = response.json()
    assert body["evidence_pack"]["claim_snapshot"]["claim_type"] == "causal"
    assert body["evidence_pack"]["passages"][0]["evidence_id"] == "E1"
    assert body["diagnostics"]["status"] == "ok"
    assert persisted == [body["evidence_pack"]["snapshot_hash"]]
    assert "verdict" not in response.text.casefold()


def test_evidence_preview_is_not_available_in_production() -> None:
    app = create_app(Settings(app_env="production"))
    app.dependency_overrides[get_pubmed_adapter] = lambda: object()
    app.dependency_overrides[get_analysis_ingestion_service] = lambda: object()
    app.dependency_overrides[get_db_session] = lambda: object()
    with TestClient(app) as client:
        response = client.post("/v1/analyses/evidence-preview", json={
            "analysis_id": str(uuid4()), "claim_id": str(uuid4()),
        })
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "evidence_preview_not_available"
