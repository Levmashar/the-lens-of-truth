# Reliability Slice 2 — results and reproduction

Date: 2026-10-01. Implementation scope: relation classification and deterministic
judge-conclusion qualification only. No source expansion, frontend change,
environment edit, threshold reduction, production qualification or forced label.

## Outcome

The new flow is implemented and software-tested. The holistic conclusion LLM
call is absent from new 2.2 runs. Source attribution remains separate. Relations
and pure qualification are append-only and auditable. This is **not** a claim
that every medical claim now receives a decisive or reliable report: all four
fresh development cases still ended Unable to Verify Reliably under the unchanged
policy, for the recorded reasons below. Independent human benchmark review and
clinical/production qualification remain open.

## 1. Exact blocker replay and confirmed causes

Original smoking analysis `75b56567-dd52-4e92-806d-ea2471bf6dc7` and sunscreen
analysis `1e58f2e8-f1cc-4e05-94af-1e008c22307d` were still retained. No original
was reconstructed. Before behavior changes, replay exported their active Slice 1
revision decisions, six exact statement texts, attribution results, exact saved
conclusion requests and returned statuses/rationales to ignored
`runtime/debug/slice2-blocker-20261001T144143428650.json`. Each active request was
matched to its exact findings, not merely the same Pack.

Both proposed NEI; all six active findings were source-supported. Both old
holistic statuses were `not_justified`. Smoking's rationale described limited
within-smoker comparisons, temporal patterns and genetic-variant analyses, none
establishing the broad causal claim. Sunscreen's rationale described broad null
meta-analyses and a contrary randomized daily/discretionary result, then demanded
a never-user comparator not present in the submitted frequent-use claim.

Confirmed category **B: status/rationale contradiction**, with **C: scope
ambiguity** and **D: evidence-strength ambiguity**. Different interpretations
remain semantic disagreements (A), not automatically bugs or medical truth.
The active saved checks had no schema/transport failure (F). Earlier outcomes
used different generated findings despite the same Pack: they do **not** prove
controlled identical-input instability (E). That is measured separately below.

Later frozen replay also exposed a specific ambiguity: metadata tagged the
parent ATBC paper as randomized, while the validated finding was a smoking-change
association among its participants. Some relation responses invented randomized
smoking comparisons. Final prompt 1.2 explicitly forbids that inference; retrieval
and the historical study classifier were not changed in this slice.

## 2. Implemented flow and rules

Historical input/decision/validation 2.0/2.1 retain holistic conclusion checking.
New 2.2 runs use:

```text
Frozen units → unchanged source→statement attribution
             → one label-blind statement→claim relation batch
             → pure qualification of the unchanged judge proposal
             → existing deterministic Lens policy → frozen report
```

Strict assessments contain statement ID, relation
(`supports_claim|contradicts_claim|insufficient|context_only|uncertain`), scope
(`aligned|compatible_but_narrower|broader_or_indirect|mismatch|uncertain`),
materiality (`decisive|supporting|contextual|uncertain`) and bounded reason.
Exactly the supplied ordered IDs must appear. Only source-validated eligible
findings, exact original claim/type/PICO and frozen metadata enter the batch;
no proposed label, desired outcome, majority, other judges, browsing/tools or
external knowledge. One 18-second semantic operation sits inside the existing
validation deadline; an existing unsupported-native-schema fallback can make
two physical HTTP requests, counted by evaluation budgets.

Pure `conclusion-qualifier-1.0`:

- Support/contradiction require relied-on decisive, compatible material direction,
  no material opposing direction, no required uncertainty/fatal defect and the
  existing claim-type design gate. Context cannot vote or supply a design gate
  for an unrelated observational finding.
- NEI may qualify insufficiency, semantic uncertainty, conflict or blocked
  scope/design strength. It does not require a paper to prove insufficiency;
  it cannot qualify clear one-sided decisive findings.
- Essential numeric mismatch/unresolved magnitude blocks **support**, without
  inventing contradiction. RR 0.85 is a 15% reduction, not 85%; HR/OR cannot be
  substituted. An accurate contrary estimate need not equal the user's number.
- Unknown/concern/retracted integrity cannot yield a qualified scientific NEI.
  Attribution's existing provenance/retraction/numeric/scope checks remain.
- Transport/schema/deadline errors produce unavailable/excluded validation,
  never fabricated claims or scientific NEI. Failed judge proposals are never
  flipped; the aggregator still counts only qualified proposals.

Audits retain provider/model, prompt version/hash, exact input/hash, every
relation/scope/materiality/reason and qualifier version/full input/output.
Aggregation rechecks frozen metadata, claim/risk, hashes and pure output.
Historical relation prompts 1.0/1.1/1.2 are reconstructible by recorded version.
Existing validation JSONB and append-only triggers suffice: **no migration**.
Canonical decision/input/validation: 2.2; judge prompt 2.7; relation contract
1.0/prompt 1.2. Public medical labels/routes/UI and production gates are unchanged.

## 3. Software verification — separate from semantic evaluation

- Python 3.13 Docker: **505 passed**, including all nine enabled PostgreSQL tests
  and new relation/qualifier JSONB round-trip and update-block checks.
- Ruff `check .`: passed. `mypy app`: passed, 127 modules.
- Alembic `check`: no upgrade operations detected; schema remains at existing head.
- `git diff --check`: passed; repository LF/CRLF notices are not failures.
- Frontend tests/build not rerun: no public frontend contract or UI was changed
  by Slice 2. Pre-existing frontend and other worktree edits were preserved.

Tests include all label/relation/scope/materiality combinations (300 single-
finding combinations), direct/conflicting/contextual cases, association vs causal
designs, contextual-trial laundering, essential quantity failure, integrity,
unknown/duplicate/missing IDs, one batch/no tools, no holistic call, typed provider
errors, old-flow compatibility, same prompt across repeat IDs, unchanged count/
risk/release gates, audit tampering and physical HTTP budgets.

The initial Compose test run inherited live model settings and caused two offline
fixture failures. Tests now isolate model environment variables while preserving
explicit PostgreSQL configuration. Test clients also ran startup recovery during
the first live batch; that batch is retained but is not used as clean acceptance.
Subsequent software tests and live analyses were run serially, not concurrently.
This did not modify the two original completed analyses. Before/after captures
compared their complete analysis/claim/evidence/judge/validation/verdict/report
records: unchanged for both. No `.env` edit was performed.

## 4. Engineering semantic benchmark

32 synthetic conditional cases: 7 expected support, 6 contradiction, 14
insufficient, 4 contextual, 1 uncertain. Categories A–Q include trials,
association-for-causation, wide nulls, equivalence/precise nulls, opposite direction,
population mismatch, narrower exposure, wrong endpoints, mechanism, synthesis,
numeric overclaim, conflicting studies, reverse causation and inability to infer
causality. Smoking, sunscreen and soy regressions are explicit. Statements are
stipulated accurate premises, **not fabricated real papers or clinical findings**.
Frozen real-source findings were evaluated separately with their actual provenance
and expiry, without publishing complete private excerpts in tracked documentation.

**Independent human review is pending.** Engineer-authored labels/rationales are
available in `app/validation/relation_cases.py`. These numbers measure agreement
with those annotations, not clinical accuracy. Some context/insufficiency and
narrow-dose materiality boundaries require reviewer adjudication. Expected labels
are never sent to models. Configured aliases are not verified backing identities.

Final prompt-1.2 paired run:
`runtime/debug/slice2-relations-20261001T153539447384.json`.
32 baseline cases per model plus two extra calls on four cases, giving three
identical-prompt trials; 120 physical HTTP calls, 121.021 seconds, reported
135,341 input / 25,044 output tokens. Hard ceiling: 240 calls / 360 seconds.
Accuracy denominators include failures; false-direction denominators are cases
whose expected relation is not that direction. Latency includes failed calls.

| Configured model alias | Relation accuracy | Scope / materiality | False support | False contradiction | Over-abstention | Schema / provider-timeout | Mean latency |
|---|---:|---:|---:|---:|---:|---:|---:|
| inclusionai/ling-3.0-flash | 29/32 (90.6%) | 68.8% / 78.1% | 0/25 | 1/26 | 0/13 | 1/32 / 1/32 | 3268 ms |
| openai/gpt-6-luna | 29/32 (90.6%) | 65.6% / 90.6% | 1/25 | 0/26 | 2/13 | 0 / 0 | 3997 ms |
| google/gemini-2.5-flash-lite | 31/32 (96.9%) | 71.9% / 78.1% | 1/25 | 0/26 | 0/13 | 0 / 0 | 1244 ms |

Per-class precision/recall (support, contradiction, insufficient, context, uncertain):

| Alias | Support | Contradiction | Insufficient | Context | Uncertain |
|---|---|---|---|---|---|
| Ling | 1.000/1.000 | .857/1.000 | 1.000/.786 | 1.000/1.000 | 1.000/1.000 |
| GPT | .857/.857 | 1.000/.667 | .875/1.000 | 1.000/1.000 | 1.000/1.000 |
| Gemini | .875/1.000 | 1.000/.833 | 1.000/1.000 | 1.000/1.000 | 1.000/1.000 |

Stability is case-level: any differing relation across three successful,
identical-prompt answers counts as a flip. Ling: **0/3**, with wide-null trials
incomplete (0/3 usable) and therefore not counted stable. GPT: **2/4** flips,
wide-null and sunscreen randomized. Gemini: **0/4**. Scope/materiality-inclusive
flip rates were the same. Small subsets do not establish general stability.

Earlier paired runs are preserved, not hidden: prompt 1.0 had 29/32 relation
agreement for all three, and prompt 1.1 had Ling 26/32, GPT 31/32, Gemini 30/32.
Those prompt versions are not identical trials of the final prompt. In particular,
the preliminary GPT advantage did not persist: do not select a validator by brand
or one favorable measurement.

### Qualification replay of measured answers

Offline artifact `runtime/debug/slice2-qualification-20261001T154003130924.json`
applies all three possible proposals to each baseline relation (96 per model).
Its oracle is the engineer's relation/scope/materiality annotation plus the same
pure gate, **not independent medical ground truth**. No additional model calls.

| Alias | False qualifications / expected negatives | False decisive qualifications | False rejections / expected positives |
|---|---:|---:|---:|
| Ling | 2/64 | 1/52 | 4/32 |
| GPT | 4/64 | 2/52 | 4/32 |
| Gemini | 2/64 | 1/52 | 2/32 |

Gemini's erroneous RR-0.85 → 85%-reduction support is blocked by backend
arithmetic: it is not a qualified support vote. The backend does not fabricate
a contradiction instead; wrong semantic relations can still cause over-abstention
or inappropriate NEI. All models over-promoted the narrower-dose materiality
relative to the annotation in this run. GPT also mislabeled the randomized
sunscreen direction. These are remaining semantic errors, not successful repairs.

## 5. Frozen regressions

Final label-preserving counterfactual over original retained findings:
`runtime/debug/slice2-frozen-20261001T154034968090.json` (four requests, configured
GPT/Gemini validators). This is a fresh relation/qualification probe, **not** a
new judge decision, historical rewrite or final medical verdict.

- Smoking: GPT classified S1 association as insufficient/narrower/supporting,
  S2 insufficient, S3 context/mismatch; the saved NEI qualifies. Gemini classified
  directions as supporting, not decisive; the saved NEI qualifies under unchanged
  strength gates. Earlier frozen probes disagreed on S1 materiality; prompt 1.2
  addresses the parent-design/randomized-exposure confusion, not every ambiguity.
- Sunscreen: both classified S1/S2 broad null meta-analyses insufficient and S3
  fewer invasive melanomas under randomized daily use contrary/decisive. The saved
  NEI does **not** qualify against that one-sided decisive finding. No automatic
  relabeling to contradiction occurs; a fresh judge must make that proposal.
- Carrot controls: cross-sectional/reverse-causation findings cannot become
  decisive causal votes. Final paired baselines classified the reverse-carrot
  control insufficient. Fresh source scope and numeric checks remain mandatory.
- Soy controls: active-comparator and wrong-outcome evidence cannot satisfy an
  absolute-use claim merely by topic overlap. No standalone/comparator/endpoint
  extraction or retrieval logic was reopened. No new optional soy live run.

## 6. Fresh live development acceptance

Clean four-case batch used normal Compose `.env`, existing MeSH/retrieval/Crossref
and configured judges. No temporary provider overrides. New-run contract 2.2,
judge prompt 2.7, relation prompt 1.1; the final parent-design clarification 1.2
was subsequently checked in the frozen probes above and one fresh smoking run.
Each analysis ceiling was tightened to 240 seconds / claim 180 seconds for this
evaluation only, inside a 400-HTTP-call / 1100-second budget. Artifact:
`runtime/debug/slice2-live-20261001T153339144487.json`, 191 calls / 341.713 seconds;
provider-reported 421,683 input / 50,939 output tokens. Only active checkpointed
children/originals count; parents are retained but do not vote twice.

| Claim / analysis UUID | Evidence | Active qualification | Final policy outcome |
|---|---|---|---|
| Smoking / `856cb119-2de7-40f5-a37c-31afbb8cc373` | 28 documents; 7 selected | GPT NEI validated; Ling required duration unresolved; Gemini unsupported source statement | Unable; 1 qualified, 2 excluded |
| Sunscreen / `62762bb8-41b2-4787-b66f-87bbfd440b62` | 26 documents; 3 selected | GPT NEI validated with supporting/nondecisive trial interpretation; Ling/Gemini required numbers unresolved | Unable; 1 qualified, 2 excluded |
| Hypertension/cancer / `04cfca40-c47d-4659-a029-8e7a4663b6e9` | 30 documents; 8 selected | Ling invalid unit citation; GPT/Gemini source-attribution defects | Unable; 0 qualified, 3 excluded |
| Carrots / `75b6ae56-1d8f-4c98-bc72-40c6d790a553` | 12 documents; 1 selected | GPT NEI validated; Ling/Gemini unsupported source assertions | Unable; 1 qualified, 2 excluded |

Selected evidence and findings, not inferred truth:

- Smoking E11: PMID 38268471, smoking changes in ATBC participants; E23: PMID
  41402808, methylation clocks; E31: PMID 42021368, epigenetic age/smoking dose.
  Active GPT S1 describes a county-level modeled-elimination scenario, S2 a
  within-smoker association. Relations context/supporting; NEI qualifies because
  no decisive causal finding survives. Ling's asserted 13-year duration had no
  bound source quantity in its own selected references and remains unresolved.
- Sunscreen E4: PMID 40876975 meta-analysis; E2: PMID 29620003 meta-analysis;
  E8: PMID 21135266 randomized follow-up. Active GPT S1 reports a broad null,
  S2 fewer invasive melanomas under daily/discretionary assignment, S3 the
  exposure-comparison limitation. The live validator assigned supporting rather
  than decisive direction; NEI qualified. This differs from the frozen exact
  statement test, exposing materiality variability rather than proving stability.
- Hypertension/cancer E21: PMID 41602789 cardiovascular comorbidity/cancer drug
  selection; E17: PMID 41313611 social determinants/cancer; E13: PMID 41289656
  genetic-result presentation formats. Active GPT S1 concerns a hypertension
  subgroup without estimating hypertension's effect; S2 obesity findings;
  S3 treatment-induced hypertension (reverse question). Passed findings received
  insufficient/context classifications; failed attribution still excludes the
  assessment. Topical background is not direct causal evidence.
- Carrots E2: PMID 10484191, *Carrots, carotene and seeing in the dark*. Active
  GPT S1 describes survey methods, S2 an observational association among women,
  S3 a reverse-causation explanation. Relations context, supporting opposite
  association, insufficient; unchanged causal gates permit NEI, not a decisive
  carrot-effect conclusion. Other judges failed source attribution.

Final-prompt fresh smoking analysis `d7780d62-42d5-4043-a17d-693ce2f524a8`:
artifact `runtime/debug/slice2-live-20261001T153653650623.json`. GPT NEI validated;
Ling essential numeric uncertainty excluded; Gemini relation timeout excluded.
Final Unable with 1 qualified. All of these runs were development-only and not
production-qualified. The first, startup-contaminated batch remains in
`slice2-live-20261001T152327413810.json` and is not substituted for clean results.

## 7. Files and remaining blockers

Created: `app/validation/{relations,relation_flow,qualification,relation_cases,
relation_eval,relation_qualification_eval,evaluation_budget,slice2_replay,
slice2_frozen_eval,slice2_live}.py`, `tests/test_reliability_slice2.py`, this report.
Modified Slice 2 integration: judging prompt/models/service/source-unit
materialization, judge/semantic adapters, validation models/protocol/service/v2,
worker risk propagation, verdict audit verification; contract/DB tests and test
environment isolation; PROJECT_CONTEXT, TODO, ARCHITECTURE, API_SPEC, DECISIONS.
No migrations. Existing Slice 1/source-unit files and unrelated dirty changes
were extended or preserved, not deleted; frontend/retrieval/.env not edited here.

Remaining: independent review; scope/materiality errors and demonstrated GPT
repeat instability; Ling schema/timeouts; model identity/family/isolation/provider
approval; exposure-specific design classification; source recall/background
selection and live integrity coverage; genuine unsupported or unbound judge
assertions. These are not fixed by counting an invalid judge or forcing a label.

Recommendation: final paired measurement favors **Gemini for development-only
relation trials with backend numeric guards**, not production certification.
It was fastest and most accurate in the final run, but still had a false support
relation and imperfect scope/materiality. Earlier GPT results were better than
its final repeat. Keep configuration unchanged; independently review labels and
expand held-out controls before any approved validator selection. The next
evidence-source slice should add approved WHO/CDC coverage and evaluate recall/
exposure-specific causal relevance, preserving frozen packs and gates. It was
**not** started here.

## 8. Exact PowerShell reproduction

From the repository, no `.env` edits are required. Run tests and live evaluations
**serially**: TestClient startup recovery must not overlap a live worker.

```powershell
cd "C:\Users\levma\Desktop\startup\The Lens of Truth\the-lens-of-truth"
docker compose up -d postgres redis
docker compose build backend
docker compose run --rm --no-deps --entrypoint alembic backend check
docker compose run --rm --no-deps --entrypoint python -v "./backend/tests:/app/tests:ro" -e RUN_DB_TESTS=1 backend -m pytest -q
docker compose run --rm --no-deps --entrypoint python -v "./backend/tests:/app/tests:ro" backend -m ruff check .
docker compose run --rm --no-deps --entrypoint python backend -m mypy app
git diff --check

# Paid, opt-in, normal configured development pipeline; never concurrent with tests.
docker compose run --rm --no-deps --entrypoint python -v "./runtime:/app/runtime" backend -m app.validation.slice2_live --run --limit 4 --max-calls 400 --deadline 1100

# Local tooling uses the existing backend venv and ../.env; no config modification.
cd backend
.\.venv\Scripts\python.exe -m app.validation.slice2_replay
.\.venv\Scripts\python.exe -m app.validation.replay --database-url postgresql+psycopg://lens:lens@localhost:5432/lens
.\.venv\Scripts\python.exe -m app.validation.slice2_frozen_eval --run --slot 2 --slot 3 --max-calls 8 --deadline 120
.\.venv\Scripts\python.exe -m app.validation.relation_eval --run --limit 32 --stability 4 --max-calls 240 --deadline 360
.\.venv\Scripts\python.exe -m app.validation.relation_qualification_eval ../runtime/debug/slice2-relations-20261001T153539447384.json
```

Use the newly printed benchmark path for an independent rerun's offline
qualification replay. Frozen-original commands refuse expired traces/captures;
do not resurrect expired data or pass reconstructions off as originals. Exact
private requests/excerpts and all per-judge relations/issues remain in their
ignored, sanitized, retention-limited artifacts. This report preserves aggregate
engineering measurements, not raw credentials or provider reasoning.
