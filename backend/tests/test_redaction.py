from app.services.redaction import PiiRedactor


def test_redaction_masks_structured_pii_without_changing_offsets() -> None:
    source = "Email jane@example.org or call +1 202-555-0188 about vitamin C."

    result = PiiRedactor().redact(source)

    assert len(result.text) == len(source)
    assert "jane@example.org" not in result.text
    assert "+1 202-555-0188" not in result.text
    assert result.text.endswith("about vitamin C.")
    assert {match.category for match in result.matches} == {"email", "phone"}
