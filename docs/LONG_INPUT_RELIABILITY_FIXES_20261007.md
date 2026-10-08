# Long-input reliability repair — 2026-10-07

Investigated `9d105a9e-23c6-41e5-9de9-6ad2ed301c4e` using the supplied
1,019-character UK Biobank/sunscreen article. The input is below the existing
20,000-character limit. Earlier runs and Evidence Packs remain unchanged.

## What failed

- The original analysis failed during extraction: two 55-second attempts,
  `claim_extractor_timeout`, no HTTP response, no extracted claims. Retrieval,
  judges and semantic validation were never reached. This was not an OCR failure
  or an input-size rejection. The old logs cannot establish the provider's
  internal reason for not answering within the deadline.
- Unlike the active judge adapter, extraction left DeepSeek thinking implicit
  and had no explicit output-token ceiling. The repaired profile disables
  thinking and caps output at 8,192 tokens; attempt/total deadlines stay 55/115
  seconds. The first real adapter probe answered in 27,790 ms, HTTP 200,
  910 input/773 output tokens, zero reported reasoning tokens.
- Saved article replies paraphrased PICO exposures, used source offsets based
  on flattened line wrapping, emitted an elliptical coordinated endpoint, and
  treated an unresolved contextual reference as a complete medical claim.
- Source grounding accepted `use` inside `users` and `smokers` inside
  `non-smokers`. Normalization discarded the prefix `up to a 292%` entirely.
- MeSH scanning covered only the first 256 characters/20 tokens. Ordinary
  `risks`/relationship `association` created false missing-medical-concept
  failures, and the relative pronoun `who` matched WHO.
- A built frontend hid development diagnostics even when backend debug was
  enabled.

## Changes

- Version extraction instructions as
  `phase7-literal-article-claims-2026-10-07`: literal PICO words, adequate source
  clauses, preserved numeric bounds and association wording, and medical
  propositions rather than article commentary. One bounded repair also checks
  grounded core slots and standalone completeness. Judge/validator prompts are
  unchanged.
- Send recursively strict JSON Schema; reject a `length` stop even if the
  truncated answer happens to contain valid JSON. Record safe input/output
  sizes, stop reason and usage counters without reasoning, keys or provider
  error bodies.
- Reconcile only unique literal/whitespace-equivalent spans to original Unicode
  offsets and exact source text. Reject changed words/numbers/negation and
  ambiguous matches. Discard stale provider antecedent offsets after rebinding;
  deterministic reconstruction must establish an inherited source span again.
- Require word/hyphen boundaries. Recover only a literal core already named
  by the model when the source explicitly states its usage verb or user noun;
  proposed frequency must also be stated. No invented `users` → `use` phrase.
- Reconstruct an adjacent affirmative reported risk/rate clause's explicit
  single human group for coordinated `plus/and higher/lower rates`. Preserve
  raw spans and inherited offsets. Reject speculative, negated, ambiguous,
  missing-group and non-adjacent forms, including unsafe decimal fallbacks.
- Preserve `up to 292%` as `upper_value="292"`, `value=null`, increase, percent
  change. Existing one-sided-bound comparison remains unresolved: this is not
  silently evaluated as an exact 292% effect.
- Scan accepted source text through 20,000 characters/all tokens with bounded
  SQLite batches, retaining exact MeSH provenance and ambiguity handling.
  Exempt ordinary relationship grammar without exempting omitted diseases.
  Preserve explicit `WHO` and the full organization name.
- Set `DEBUG_MODE=true`; built frontend follows the backend debug flag while
  preserving the explicit frontend opt-out and production backend privacy gate.
  Rebuild/restart both services.

No model, retrieval query-plan, evidence-selection, citation/quantity-validation,
medical threshold, qualifier policy or production-release gate was changed.

## Verification and limitations

Exact no-paid replay of the first full run's extraction reply now normalizes
claims 1, 2, 3 and 5 and makes them ready for evidence. Claim 3 inherits only
the literal `sunscreen users` at source offsets 292–307. All five source spans
validate. The method sentence starting `These links...` remains unresolved:
it is not an independently grounded medical proposition. It safely receives
Unable rather than a fabricated relationship or medical NEI.

The initial full HTTP run `9ba0121b-6ce1-436b-8e42-eebf80a22aff` completed two
reports (HTTP 200) in 367,316 ms: first association NEI; final vague association
Contradicted. The numeric/coordination/context candidates were normalization
unavailable. All six judges and six semantic calls responded; 14 total requests
including two extraction attempts. The final source fixes were developed from
these actual failures; this initial run is preserved separately.

Complete database-enabled backend suite: **1,297 passed**, zero failures/skips.
The final article/coordination/extraction regression group: **85 passed**,
including the last two fail-closed decimal/reporting tests added after full
suite collection. Frontend: **76 passed**, TypeScript and production build
passed. Full backend Ruff and mypy (180 source files) passed; diff check passed.
Final live acceptance is recorded below. This bounded test is not a claim of
universal provider reliability.

Deployed backend image:
`sha256:1a31bd97697e2dcd8fa0c78e023f9e1bcac8af0eff84c3179b066e909f9b933b`.
Frontend image:
`sha256:3c753720b8b29f7e6c599b7c326abd3a434da1d56dfa3cc0cd78ed3b78c49ddc`.

Artifacts:

- [First live extractor probe](LONG_INPUT_EXTRACTION_PROBE_20261007.json)
- [Initial full run](LONG_INPUT_LIVE_INITIAL_RESULTS_20261007.json)
- [Final frozen normalization replay](LONG_INPUT_FROZEN_NORMALIZATION_20261007.json)
- [Final full run](LONG_INPUT_LIVE_RESULTS_20261007.json)

Active lineup remains Paratera DeepSeek-V4.1-Flash extraction/J1,
Qwen3.5-Plus J2, GLM-4.7 J3 and Qwen3.8-Flash validator.
Architecture V2.5, structured quantities V2.4, query-plan 1.6, validated position
1.8, question-evidence policy 2.1, semantic prompt 2.7, judge prompt 2.15 and
verdict policy 1.4 remain unchanged.

## Final fresh frontend-path run

Analysis `0e581f5d-8d5d-4f2b-b49e-1529ffe45967` submits the exact article
through `POST /v1/analyses`, polls durable progress/claim summaries and loads
each report through its ordinary HTTP route. Extraction responded in 9,628 ms
then 5,346 ms on the single bounded repair (14,974 ms combined attempt time),
zero reported reasoning tokens, with no extraction timeout.

| Extracted proposition | Original failure / initial full run | Final build |
|---|---|---|
| Frequent sunscreen users had higher skin-cancer risk | Original analysis never extracted; initial run NEI | Contradicted, completed, 2/3 qualified |
| Up to 292% increased invasive-melanoma risk for users | Initial normalization unavailable (exposure lost) | NEI, completed, 3/3 qualified; bound preserved |
| Higher basal-cell and squamous-cell carcinoma rates | Initial normalization unavailable (subject ellipsis) | Contradicted, completed, 3/3 qualified |
| `These links held...` adjustment sentence | Unresolved context reference | Unable to Verify Reliably; not standalone, no model judging |
| Study highlights a sunscreen/skin-cancer association | Initial report Contradicted | NEI, completed, 3/3 qualified |

Results are recorded application outputs, not independent clinical acceptance
labels. The initial and final fresh reports differ for the first and final associations;
these were new retrieval/model calls, not a deterministic verdict replay.
One GLM finding in final claim 1 remained unavailable under existing source
validation; two other qualified assessments produced its report. No source
validation rule was weakened to qualify that finding.

Final status is `partially_completed`: **4/5 extracted candidates completed**,
with four actual reports **HTTP 200** and no top-level failure code. Only the
unresolved context/method sentence is `normalization_incomplete`; its public
label is Unable to Verify Reliably. It does not stop the remaining medical
checks or manufacture medical NEI. All twelve judges and twelve semantic
checks returned usable transport responses. One final DeepSeek judge attempt
hit its 60-second deadline and succeeded on its single existing retry in
39,317 ms. No timeout budgets were raised.

Total final HTTP workflow time: **756,743 ms (12m 37s)**. The existing serial
multi-claim workflow still takes several minutes; the transport/grounding
repairs do not make four complete evidence reviews instantaneous.
Final run initiated **27 provider requests** (two extraction, thirteen judge
attempts, twelve semantic calls). This task initiated **42 total requests**:
one extractor probe + fourteen initial full-run requests + twenty-seven final
requests. No model bakeoff or extra control analyses were run.

All four frontend reading-guide endpoints also return HTTP 200. Backend
`/healthz` and frontend `/` return HTTP 200 after completion. Debug is enabled,
models are unchanged, and all earlier snapshots remain historical.
