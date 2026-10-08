"""Screenshot-specific handoff tests: no provider, retrieval, or judge calls."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.adapters.claim_extractor import (
    ClaimExtractionPayload,
    ExtractedClaimCandidate,
    PicoCandidate,
)
from app.adapters.ocr import OcrResult
from app.core.errors import LensError
from app.models.screenshot_upload import ScreenshotUpload
from app.models.submission import Submission
from app.schemas.analysis import AnalysisInput, Consent, CreateAnalysisRequest
from app.services.analysis_ingestion import AnalysisIngestionService
from app.services.redaction import PiiRedactor


def workflow(
    text: str = "Smoking causes lung cancer.",
) -> tuple[AnalysisIngestionService, Mock, ScreenshotUpload]:
    upload = ScreenshotUpload(
        id=uuid4(),
        object_key="fixture.png",
        content_sha256="a" * 64,
        status="uploaded",
        purge_after=datetime.now(UTC) + timedelta(hours=1),
    )
    session = Mock()
    session.get.return_value = upload
    session.scalars.return_value = []
    storage = Mock(get=AsyncMock(return_value=b"sanitized-image"))
    ocr = Mock(
        service_name="tesseract",
        recognize=AsyncMock(
            return_value=OcrResult(
                text=text,
                confidence=0.95,
                language_used="eng",
                lines=(),
            )
        ),
    )
    extractor = Mock(extract=AsyncMock())
    service = AnalysisIngestionService(
        storage=storage,
        ocr=ocr,
        extractor=extractor,
        redactor=PiiRedactor(),
        retention_hours=24,
        maximum_claims=20,
        upload_max_bytes=10_485_760,
        upload_max_pixels=25_000_000,
    )
    return service, session, upload


def screenshot_request(
    upload: ScreenshotUpload, reviewed_text: str | None = None
) -> CreateAnalysisRequest:
    return CreateAnalysisRequest(
        input=AnalysisInput(type="screenshot", upload_id=upload.id, reviewed_text=reviewed_text),
        consent=Consent(privacy_notice_version="2026-09-01", accepted=True),
    )


def test_read_is_local_redacted_ephemeral_and_does_not_extend_retention() -> None:
    text = "Smoking causes lung cancer. Contact me at private@example.com"
    service, session, upload = workflow(text)
    deadline = upload.purge_after

    result = asyncio.run(
        service.read_screenshot_text(session=session, upload_id=upload.id, language="en")
    )

    assert "private@example.com" not in result.redacted_text
    assert len(result.redacted_text) == len(text)
    assert upload.ocr_provider == "tesseract"
    assert upload.ocr_confidence == 0.95
    assert upload.status == "read"
    assert upload.purge_after == deadline
    assert not hasattr(upload, "redacted_text")
    service._extractor.extract.assert_not_called()
    session.commit.assert_called_once()


@pytest.mark.parametrize(
    "text,code", [(" \n", "screenshot_text_not_found"), ("A" * 20_001, "screenshot_text_too_long")]
)
def test_read_rejects_empty_or_excessive_text_without_a_model_call(text: str, code: str) -> None:
    service, session, upload = workflow(text)

    with pytest.raises(LensError) as caught:
        asyncio.run(
            service.read_screenshot_text(session=session, upload_id=upload.id, language="auto")
        )

    assert caught.value.code == code
    service._extractor.extract.assert_not_called()
    session.commit.assert_not_called()


def test_expired_upload_is_rejected_before_ocr() -> None:
    service, session, upload = workflow()
    session.get.return_value = None

    with pytest.raises(LensError) as caught:
        asyncio.run(
            service.read_screenshot_text(session=session, upload_id=upload.id, language="auto")
        )

    assert caught.value.code == "screenshot_upload_not_found"
    service._ocr.recognize.assert_not_called()


@pytest.mark.parametrize("reviewed", [True, False])
def test_screenshot_handoff_uses_reviewed_text_or_legacy_ocr_and_redacts_again(
    monkeypatch: pytest.MonkeyPatch,
    reviewed: bool,
) -> None:
    service, session, upload = workflow()
    upload.ocr_provider = "tesseract"
    upload.ocr_confidence = 0.95
    edited = "Smoking causes lung cancer. private@example.com" if reviewed else None
    persist = Mock(return_value=Submission(id=uuid4()))
    monkeypatch.setattr(service, "_persist_submission", persist)

    asyncio.run(
        service.create_analysis(session=session, request=screenshot_request(upload, edited))
    )

    source = persist.call_args.kwargs["redacted_text"]
    assert "private@example.com" not in source
    assert source.startswith("Smoking causes lung cancer.")
    service._extractor.extract.assert_awaited_once_with(text=source, language="auto")
    assert service._ocr.recognize.await_count == (0 if reviewed else 1)
    assert upload.status == "processed"
    assert persist.call_args.kwargs["screenshot_upload"] is upload


def test_reviewed_text_cannot_bypass_the_ocr_step() -> None:
    service, session, upload = workflow()

    with pytest.raises(LensError) as caught:
        asyncio.run(
            service.create_analysis(
                session=session,
                request=screenshot_request(upload, "User-reviewed text."),
            )
        )

    assert caught.value.code == "screenshot_text_not_ready"
    service._extractor.extract.assert_not_called()


def test_reviewed_screenshot_preserves_real_submission_and_source_span_contracts() -> None:
    service, session, upload = workflow()
    upload.ocr_provider = "tesseract"
    upload.ocr_confidence = 0.95
    reviewed = "Cigarette smoking causes lung cancer."
    service._extractor.extract.return_value = ClaimExtractionPayload(
        claims=[
            ExtractedClaimCandidate(
                raw_span=reviewed,
                span_start=0,
                span_end=len(reviewed),
                claim_type="causal",
                pico=PicoCandidate(
                    intervention_or_exposure="Cigarette smoking",
                    outcome="lung cancer",
                ),
            ),
        ]
    )

    submission = asyncio.run(
        service.create_analysis(
            session=session,
            request=screenshot_request(upload, reviewed),
        )
    )

    assert submission.input_type.value == "screenshot"
    assert submission.content_sha256 == upload.content_sha256
    assert submission.screenshot_upload is upload
    assert len(submission.claims) == 1
    assert submission.claims[0].raw_text == reviewed
    assert submission.claims[0].span_start == 0
    assert submission.claims[0].span_end == len(reviewed)
    assert submission.claims[0].outcome == "lung cancer"
    service._ocr.recognize.assert_not_called()
    service._extractor.extract.assert_awaited_once_with(text=reviewed, language="auto")


def test_reviewed_text_cannot_reuse_an_already_submitted_upload() -> None:
    service, session, upload = workflow()
    upload.submission_id = uuid4()

    with pytest.raises(LensError) as caught:
        asyncio.run(
            service.create_analysis(
                session=session, request=screenshot_request(upload, "Edited text.")
            )
        )

    assert caught.value.code == "screenshot_upload_already_used"
    service._extractor.extract.assert_not_called()


@pytest.mark.parametrize(
    "values",
    [
        {"type": "text", "text": "Text", "reviewed_text": "Edited"},
        {"type": "screenshot", "upload_id": str(uuid4()), "reviewed_text": " \n"},
        {"type": "screenshot", "upload_id": str(uuid4()), "reviewed_text": "A" * 20_001},
    ],
)
def test_reviewed_text_contract_is_screenshot_only_nonempty_and_bounded(
    values: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        AnalysisInput.model_validate(values)
