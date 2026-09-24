from datetime import UTC, datetime, timedelta
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.dependencies import get_analysis_ingestion_service
from app.models.claim import Claim
from app.models.enums import InputType
from app.models.screenshot_upload import ScreenshotUpload
from app.models.submission import Submission
from app.schemas.analysis import CreateAnalysisRequest
from app.services.analysis_ingestion import OcrPreview, OcrPreviewLine
from app.services.image_ingestion import SanitizedImage


class FakeAnalysisIngestionService:
    """Route test double; extraction behavior is tested independently."""

    upload_max_bytes = 10 * 1024 * 1024
    upload_max_pixels = 25_000_000

    def __init__(self) -> None:
        self.analysis_id = uuid4()
        self.upload_id = uuid4()
        self.submission = Submission(
            id=self.analysis_id,
            client="web",
            language="auto",
            input_type=InputType.TEXT,
            content_sha256="a" * 64,
            privacy_notice_version="2026-09-01",
            consent_accepted=True,
            status="claims_extracted",
            purge_after=datetime.now(UTC) + timedelta(hours=24),
            updated_at=datetime.now(UTC),
        )
        self.submission.claims = [
            Claim(
                id=uuid4(),
                ordinal=1,
                span_start=0,
                span_end=21,
                raw_text="A public health claim.",
                normalized_text="A public health claim.",
                claim_type="association",
                population="adults",
                intervention_or_exposure="sunscreen use",
                outcome="melanoma incidence",
                risk_class="standard",
                verifiability=0.8,
                coreference_uncertain=False,
            )
        ]

    async def create_analysis(
        self, *, session: object, request: CreateAnalysisRequest
    ) -> Submission:
        del session, request
        return self.submission

    async def create_screenshot_upload(
        self, *, session: object, image: SanitizedImage
    ) -> ScreenshotUpload:
        del session
        return ScreenshotUpload(
            id=self.upload_id,
            object_key="test.png",
            content_sha256=image.content_sha256,
            media_type=image.media_type,
            byte_count=image.byte_count,
            width=image.width,
            height=image.height,
            status="uploaded",
            purge_after=datetime.now(UTC) + timedelta(hours=24),
        )

    def get_submission(self, *, session: object, analysis_id: UUID) -> Submission:
        del session
        assert analysis_id == self.analysis_id
        return self.submission

    async def preview_screenshot_ocr(self, *, session: object, upload_id: UUID) -> OcrPreview:
        del session
        assert upload_id == self.upload_id
        return OcrPreview(
            upload_id=upload_id,
            provider="tesseract",
            language_used="eng",
            confidence=0.9,
            redacted_text="Vitamin C prevents colds.",
            pii_redaction_count=0,
            lines=(
                OcrPreviewLine(
                    text="Vitamin C prevents colds.",
                    confidence=0.9,
                    left=0,
                    top=0,
                    width=100,
                    height=20,
                ),
            ),
        )


def _submission_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "client": "web",
        "lang": "auto",
        "input": {"type": "text", "text": "A public health claim."},
        "consent": {"privacy_notice_version": "2026-09-01", "accepted": True},
    }


@pytest.fixture
def phase_two_client(client: TestClient) -> TestClient:
    service = FakeAnalysisIngestionService()
    client.app.dependency_overrides[get_analysis_ingestion_service] = lambda: service
    yield client
    client.app.dependency_overrides.clear()


def test_create_analysis_returns_real_phase_two_state(phase_two_client: TestClient) -> None:
    response = phase_two_client.post("/v1/analyses", json=_submission_payload())

    assert response.status_code == 201
    body = response.json()
    assert UUID(body["analysis_id"])
    assert body["status"] == "claims_extracted"
    assert body["claim_count"] == 1


def test_get_analysis_returns_redacted_claim_contract(phase_two_client: TestClient) -> None:
    analysis_id = phase_two_client.app.dependency_overrides[
        get_analysis_ingestion_service
    ]().analysis_id
    response = phase_two_client.get(f"/v1/analyses/{analysis_id}")

    assert response.status_code == 200
    assert response.json()["analysis_id"] == str(analysis_id)
    assert response.json()["claims"][0]["span_start"] == 0
    assert response.json()["claims"][0]["population"] == "adults"
    assert response.json()["claims"][0]["outcome"] == "melanoma incidence"
    assert "is_mock" not in response.json()


def test_analysis_events_use_real_completed_stages(phase_two_client: TestClient) -> None:
    analysis_id = phase_two_client.app.dependency_overrides[
        get_analysis_ingestion_service
    ]().analysis_id
    response = phase_two_client.get(f"/v1/analyses/{analysis_id}/events")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "claims_extracted" in response.text
    assert '"mock": true' not in response.text


def test_screenshot_upload_uses_decoded_image_not_client_content_type(
    phase_two_client: TestClient,
) -> None:
    output = BytesIO()
    Image.new("RGB", (4, 3), "white").save(output, format="JPEG")

    response = phase_two_client.post(
        "/v1/analyses/uploads/screenshots",
        files={"screenshot": ("screenshot.txt", output.getvalue(), "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["media_type"] == "image/png"
    assert (body["width"], body["height"]) == (4, 3)


def test_ocr_preview_returns_redacted_development_diagnostics(phase_two_client: TestClient) -> None:
    upload_id = phase_two_client.app.dependency_overrides[
        get_analysis_ingestion_service
    ]().upload_id

    response = phase_two_client.post(f"/v1/analyses/uploads/screenshots/{upload_id}/ocr-preview")

    assert response.status_code == 200
    assert response.json()["provider"] == "tesseract"
    assert response.json()["lines"][0]["text"] == "Vitamin C prevents colds."


def test_rejects_submission_without_accepted_consent(phase_two_client: TestClient) -> None:
    payload = _submission_payload()
    payload["consent"] = {"privacy_notice_version": "2026-09-01", "accepted": False}

    response = phase_two_client.post("/v1/analyses", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_failed"
