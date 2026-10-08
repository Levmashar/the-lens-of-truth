# Screenshot upload and OCR fixes — 2026-10-07

Scope: screenshot selection, sanitization, local OCR, text review, and ingestion
handoff. No changes to extraction models/prompts, medical normalization,
retrieval, judging, validation, aggregation, production gates, or `.env`.

## Recorded failure

Analysis `f5da4f6e-2369-4460-b83a-77d764218a80`, upload
`94ea13f6-9309-4837-8953-cb987404432e`: upload HTTP 201, analysis acknowledgement
HTTP 202. Local OCR completed. The subsequent extraction provider timed out on
both 55-second attempts, ending with `claim_extractor_timeout` at extracting.
This was not an OCR dependency/storage failure.

The previous single-block OCR mode treated the image/footer as text. Original
OCR confidence was 0.912859; automatic page layout now returns the article alone,
1,019 characters, confidence 0.963666. This confidence concerns text recognition,
not whether the article's medical claims are true.

## Changes

- Automatically detect screenshot layout with Tesseract page-segmentation mode 3.
  Preserve literal quotation marks in TSV; terminate and reap OCR subprocesses
  on deadline/cancellation; map launch/permission failures to safe OCR errors.
- Flatten transparency against white, preserve dark screenshots, report EXIF
  rotated dimensions accurately, and emit clean metadata-free PNG bytes.
- Add public, consent-required `POST /v1/analyses/uploads/screenshots/{id}/read`.
  It performs local OCR and existing conservative identifier redaction only.
  Return transient review text; persist provider/confidence/redaction count, not
  the full recognized text. Existing retention deadlines remain unchanged.
- Screenshot UX: select → consent → Read screenshot → review/edit the recognized
  text → Check this claim. The user can keep the proposition they want checked
  and correct recognition mistakes before making an extraction request.
- Optional screenshot-only `reviewed_text` preserves the screenshot reference
  and original image hash. Re-redact it, then pass it to the unchanged extractor;
  validate/store exact claim spans against that user-reviewed source. Legacy
  screenshot requests still use direct OCR. Reviewed text requires completed
  OCR, a live upload, and the existing unused-upload guard.
- Lock screenshot/mode controls in flight. Reuse an upload after OCR/network
  failures, clear expired/missing references, clear resolved error messages, and
  retain final submission keys on retry while replacing them after text edits.
- Accept supported extensions when browsers omit MIME; reject empty/undecodable
  previews, allow reselection, and provide screenshot-specific safe errors.
  Server decoding still decides the actual format.
- Recognize OCR failure codes even when the failure precedes persisted input
  metadata. Do not mislabel an extraction-provider timeout as an OCR failure.

## Verification

- Full offline backend suite in Python 3.13 Docker: **1,181 passed, 15 skipped**.
  Database-mutating tests were disabled; real Tesseract tests ran. Final targeted
  upload/OCR tests: **43 passed**, including an additional real submission/source-span
  handoff regression with a local extractor test double.
- Frontend: **71 passed**, production build passed. Ruff and mypy (178 source
  files) passed. Added regression coverage for layout, quotes, transparency,
  rotation/metadata, process cleanup, consent, redaction, reviewed-text bounds,
  ownership/retention, direct OCR compatibility, retries, controls, and errors.
- Live HTTP upload/read: PNG, JPEG, WebP, transparent PNG and dark PNG each
  HTTP 201 → HTTP 200; exact generated quoted text and `85%` preserved.
- Original saved screenshot: public read HTTP 200, 96.37% OCR confidence,
  no photo/footer junk. Blank screenshot: 422 `screenshot_text_not_found`;
  invalid and empty image uploads: 415 with precise safe error codes.
- Reading did not create any analysis runs. **Zero paid model calls**. Local
  live results are in [the JSON record](OCR_UPLOAD_RESULTS_20261007.json).
- Browser UI automation was unavailable (no enabled browser). Frontend behavior
  was verified through DOM tests; no visual browser inspection is claimed.

Rebuilt/restarted the idle local services. Backend image config digest:
`sha256:cb2e7e0325b3475a5011d13256bc73142b3292ee26b7600cb203297a7d56e730`.
Final frontend digest:
`sha256:dbf428234778495db757e87727c66d1a8e6d06b1eb49d181b2ac696bab6cde32`.
Health is `ok`; frontend HTTP 200 serves the final `index-D1ZmvkMn.js` bundle.

## Remaining verification boundary

Automatic approval review rejected a live extraction replay because it would
transmit the saved screenshot's text to the external extraction provider and
incur model usage under a request explicitly limited to upload/OCR. No such
request was sent. Extraction transport/model behavior was not changed; the
original downstream deadline failure is not asserted resolved. The local OCR
workflow and unchanged extractor handoff were verified with test doubles.
