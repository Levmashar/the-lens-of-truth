# Architecture Decisions

## ADR-060 - Context-aware document evidence and reporting fidelity

**Decision (2026-10-08):** Use an exact-spanned document plan and frozen shared
evidence for related study assertions instead of disconnected atomic analyses.
Preserve full original context, qualifiers, explicit literal references and every
unresolved detail. Keep different studies/endpoints separate. Deduplicate only
verifiable literal repeats; never cache semantic verdicts.

Run three independent grouped judge chains within the provider-account concurrency
limit and start each one's grouped validator when ready. Preserve item isolation,
task-local database sessions, bounded deadlines/retries, source/quantity ownership,
integrity, existing clinical safeguards/quorum and production gates.

Reporting fidelity is a distinct validation target: verify attributed findings and
the source's reported details without requiring clinical causation. New validator
1.2 transports source/quantity IDs; backend-owned literal source materialization
removes generated quotation spelling from the machine-critical contract. Clinical
targets retain full semantic axes and deterministic qualification. Reporting support
does not become support for a general medical conclusion.

Persist append-only hash-bound plan/evidence/judge/report artifacts and verify them
offline at read time. Version-dispatch earlier contracts without rewriting their
results. Deliver one expandable vanilla TypeScript document report, partial progress,
exact citations and explicit scientific interpretation limits; no average score.

The exact 326b6a1c failure showed that commentary attribution must not trigger
factual group ownership checks. Factual mismatches still fail closed. Unique literal
reference ownership/punctuation repair preserves source text without inventing
antecedents. Follow-up live testing corrected grouped shape, source packaging,
retrieval bounds and validator target/quote transport. Models are unchanged.
Production certification and the under-90-second target remain unmet. See
[implementation, full evidence and measurements](DOCUMENT_MODE_RESULTS_20261008.md).

## ADR-059 - Disambiguate source vocabulary without aliasing citations

**Decision (2026-10-06):** Repair the V2.5 prose preflight namespace collision
using each finding's own exact materialized frozen quotations. Bare scientific
E-number vocabulary present in those quotations is not itself an evidence
citation. Explicit citation grammar/brackets and unit/quantity IDs remain exact
local references. Conclusions inherit only declared statement dependencies.
Historical contracts through V2.4 retain their original acceptance rules.

Keep unit/quantity ownership, catalog/hash reconstruction, duplicate and ambiguous
parent checks. No claim-specific vocabulary, ID aliases, model/prompt change or
medical-policy relaxation. Version citation preflight independently as 1.1;
record sanitized offending statement/field/ID, expected IDs and exact exception
on each rejected attempt without rewriting old failed analyses.

All six original soy-run replies replay citation-valid; one fresh full run reaches
three validators and three qualified NEI positions. Final-source saved audits
reconstruct exactly. Separate exposure grounding and misleading report-reason
priority remain open; this operational repair is not production certification.
See [trace, regression evidence and live result](CITATION_PREFLIGHT_RELIABILITY_FIX_20261006.md).

## ADR-058 - Claim-type causal evidence and reviewed route assessments

**Decision (2026-10-06):** Separate etiologic exposure/disease-transmission
questions from manipulation/treatment/prevention using question semantics and
linked ontology categories, without disease-specific policy branches.

Permit explicit source-validated, current reviewed causal/transmission assessments
or suitably converging empirical evidence for natural exposures and transmission.
Require finding-bound exposure/endpoint/relation, integrity and semantic scope;
retain causal disclaimers, quantitative, null and endpoint safeguards. Authority
alone, omission, opinion, mechanism alone and belief surveys are insufficient.
Independent cohort/case-control convergence needs temporality; an eligible
explicit causal assessment may auditably override incidental association wording.

Keep established intervention/treatment/prevention eligibility unchanged in
question-evidence-2.1. Preserve historical intermediate question-evidence-2.0
behavior, whose tighter synthesis requirement was rejected by regression tests.
Write position 1.8 with exact 1.0-1.7 reconstruction. Semantic prompt 2.7 explains
these distinctions; judge prompt/models/thresholds/public labels/gates unchanged.
Query-plan 1.6 extends only the bounded design query; reviewed manifest 1.1 adds
actual NCI and CDC documents. Source selection quotas and weights are unchanged.

Live HPV/HIV positions resolve to Supported/Contradicted (3 matching assessments
each), BP/sunscreen remain Supported, and antibiotics final-build repeat is
Supported following an initial scope/comparator NEI. This is not a guarantee of
future model consistency. Full backend 1,066/frontend 52/build and Ruff/mypy pass.
See [auditable evidence and run history](CLAIM_TYPE_CAUSAL_EVIDENCE_RESULTS_20261006.md).

## ADR-057 - Setting-aware scope and source-grounded literal polarity

**Decision (2026-10-06):** Keep V2.5, source selection, structured quantities,
thresholds/public labels/production gates and models. Normalize exact disease
objects from relation annotations; do not require setting-only words as core
medical entities. Explicit cell-experiment questions may use actual attributed
laboratory interventions, without inventing controls or clinical eligibility.
Primary assignment facts cannot come from reviews/plans/speculation or be borrowed
for an unrelated measured exposure in a trial.

For existential treatment capability, an unspecified population permits validated
compatible narrower population evidence; explicit/universal qualifiers remain
guarded. A literal polarity correction requires unambiguous matching exposure,
endpoint and direction in the claim, finding and source. Preserve raw model axes
and audit the override. Ambiguous/null/mixed effects and lowering-the-exposure
statements cannot supply this deterministic correction.

Write position 1.6, retaining exact 1.0-1.5 reconstruction. Query-plan 1.5 adds
one design-focused variant only when bounded query capacity permits. Semantic
prompt 2.6 clarifies polarity/capability/cellular scope; judge prompt unchanged.
Report actual causal/conflict reasons before incidental scope warnings.

Full backend suite passes 1,032 with no skips; frontend passes 52/build. Seven
requested full live cases plus a laboratory repeat establish antibiotics/lab
Supported and inverse BP Contradicted, with both controls Supported. HPV and HIV
still return NEI for evidence/design limitations; no policy exception is used to
force their expected labels. See [exact results](SELECTED_SCOPE_POLARITY_FIXES_20261006.md).

## ADR-056 - Freeze the final 1.4 development reliability baseline

**Decision (2026-10-06):** After test-isolation/full-response expectation cleanup,
freeze V2.5 validated evidence position with V2.4 structured references, query-plan
1.4 and position 1.4 as the current development baseline. The deployed full suite
passes 990/990 including PostgreSQL; frontend passes 52/52. Fresh blue-light and
carrots analyses retain NEI with 3/3 and 2/3 qualifications respectively.

**Limit:** Qwen3.5-Plus's carrots replies twice omitted required S3/S4
numeric_dependency fields and remain excluded, without schema repair. Reduced
qualification is recorded even though the medical result remains unchanged.
No medical logic, models, prompts or production gates changed. Model repeatability
and production qualification are not inferred from this freeze. Actual Miri
provider identifiers remain; the shared parser flag now describes its behavior.
See [exact baseline hashes and versions](RELIABILITY_BASELINE_20261006.md).

## ADR-055 - Source-owned comparability guards and completed trial synthesis

**Decision (2026-10-05):** Fix the generic failures in manual tests 11-15 within
backend validated evidence position, without a model/prompt change or bakeoff.
A review's explicit completed randomized result is a frozen source fact, not a
new label for the document. An attributed aligned direct/synthesis finding can
use that fact for eligibility/materiality; aggregation reconstructs the same
facts. Trial-name mentions, future/nonrandomized trials and prestige alone do
not qualify. Direction and clinical scope still require validation.

Project invalid opposition (alternative causes, omitted causes, unrelated
population/time trends) to context. Distinguish existing-disease treatment,
cell killing, progression and diagnostic processes from disease onset. Preserve
raw axes, source terms, statement text and reason-coded overrides in the audit.
Do not mistake an incident-diagnosis outcome or mortality wording alone for
these invalid contexts. Write position 1.4 and retain exact 1.3 behavior plus
1.0/1.1/1.2 reconstruction. New facts remain confined to V2.5; V2.4 stays strict.

Normalize literal disease objects when extraction adds a relation annotation.
When a genuine incomplete normalization stops processing, expose operational
Unable without synthesizing medical artifacts. Preserve linked phrase meaning
and additional exposure entities in all bounded query families. Keep canonical
MeSH recall separate from literal lexical recall. Retrieval source selection
rules, quantitative references, thresholds and production gates remain intact.

Seven requested live cases completed with 57 real requests including retries and
a BP repeat. Final guard replay preserves every successful live position; the
sunscreen DeepSeek deadline exclusion remains visible. No production qualification
is asserted. See [results and code scope](MANUAL_TESTS_11_15_FIXES_20261005.md).

## ADR-054 - Scope integrity to participating findings and retain review trial facts

**Decision (2026-10-05):** Fix the latest ten-case failures generically within
validated-position qualification. Keep unknown material integrity, retraction,
concern, semantic direction/scope, numeric references and causal safeguards.
Unknown currency of excluded context cannot veto separate verified material
research. Record raw facts and ignored statement IDs rather than calling an
undated context page current or valid.

Freeze affirmative randomized-trial methods as an optional synthesis fact for
new checker inputs. A source-validated aligned direct/synthesis finding can be
direct even when retrieval classified the whole review as context. Preserve the
review design and synthesized exposure assignment. Final causal aggregation uses
these same reconstructed finding facts; objective trial methods can establish
materiality with strength=supporting. No direction comes from design alone.

Write position 1.2 and preserve recorded 1.0/1.1 reconstruction. Preserve absent
numeric bounds in old serialization; capture and evaluate new explicit fold/RR
ranges without altering source-quantity catalogs or ambiguous-source conventions.
Select the correct structured checker contract before reference enforcement.
Persist exact rejected replies/exceptions and keep failed checks unavailable.
The original lost smoking exception cannot be asserted from a successful replay.

All six requested full live analyses and the additional final-build exercise
case qualified 3/3 assessments, within 52 paid requests. No models, retrieval,
source selection, prompt instructions, verdict thresholds, public labels or
production gates changed. See [live results](MANUAL_RELIABILITY_FIXES_20261005.md).

## ADR-053 — Provisional live checker replacement and bounded integrity timeout

**Decision (2026-10-05):** Following 16 authorized full-input paid checker calls,
use Paratera Qwen3.8-Flash with enable_thinking=false as the local development
validator. Reuse verified provider generation options, reject unsupported
overrides and retain strict local schema/ID enforcement. Default settings remain
unchanged when the new optional setting is unset. All judge/extraction models,
V2.5 contracts, prompts, quantity references and policy/gates are preserved.

Qwen matched all four expected engineering positions with valid schema/IDs, but
missed a cross-review attribution defect that Luna correctly rejected. Adoption
is provisional; positions alone do not establish semantic accuracy. Tested Luna
profiles failed a deadline or vitamin-C checks and are not activated.

The latest sunscreen RCT's unknown integrity came from Crossref's global deadline,
not randomized-design metadata. All available DOI checks genuinely succeeded on
normal live recheck and populated the existing success cache. Local total timeout
increases from 30 to 60 seconds without exceeding Crossref concurrency three or
relaxing integrity guards. Historical snapshots/results remain unchanged. See
[actual calls, limitations and verification](LIVE_VALIDATOR_ACCEPTANCE_20261005.md).

## ADR-052 - Derive a backend-owned validated evidence position

**Decision (2026-10-05):** New development/test contract V2.5 requests
source-attributed findings with unchanged V2.4 unit/quantity references, rationale,
conclusion dependencies and uncertainty reasons. The provider schema does not
request a final label. The local new-contract parser tolerates optional advisory
label text, records it exactly and never converts it into a vote. Historical
contracts continue to require their original valid enum; invalid old labels are
never silently normalized.

After source attribution and the unchanged independent semantic axes checker,
`validated-evidence-position-1.0` derives a position from all validated findings,
including findings omitted from the judge's conclusion dependencies. Reuse
qualifier source/integrity/design/risk and numeric guards while testing positions
independently. All checks are deterministic, versioned and auditable. Source,
transport/schema, missing-material-evidence or integrity failures are unavailable
assessments, not NEI. Both eligible material directions mean conflict/NEI; only
contextual/weak/imprecise findings mean NEI. No imprecise null manufactures opposition.

Aligned direct randomized intervention results and applicable direct review/causal
assessments may establish materiality when axes say supporting, provided objective
relationship facts and existing scope/numeric/integrity gates pass. Design cannot
establish semantic direction. Parent RCT labels do not randomize observed exposures.
CAUSAL_DESIGN_INSUFFICIENT denotes actual ineligible design, not merely low strength.

Aggregation and causal sufficiency checks use audited positions/material findings;
reports use guarded finding relations. Save raw axes, mapped relations, promotions,
inputs/output and position in append-only JSONB; reconstruct at aggregation. No
migration, backfill or historical V2.4 replay change. Retrieval, selection, numeric
catalog/fidelity, models, production gates, public labels and vote thresholds remain.

**Acceptance:** Only saved responses/checkers from the four requested engineering
claims, plus adversarial controls on those same frozen cases. No provider calls or
new full analyses. See [results](VALIDATED_EVIDENCE_POSITION_RESULTS.md).

## ADR-051 — Transport source quantities by frozen references in development V2.4

**Decision:** create `judge-input-2.4` / decision 2.4 /
`judge-validation-2.4`. Derive `source-quantity-catalog-1.0` from exact frozen
source units; hash it with the input snapshot without changing the Evidence Pack.
Each item retains source identity, literal, half-open offsets, exact decimal
values, typed measure/unit/binding and normalization reason. Extraction changes
require a new catalog version and recorded-version reconstruction.

**Transport:** retain source-attributed descriptions, separate qualitative
findings and conclusion statement dependencies. Replace provider-facing
`numeric_details` with `source_quantity_ids`, allowing []. References must exist
and belong to the statement's cited units. No provider-owned numeric values,
conversions or conclusion quantity fields. Historical 2.3 stays unchanged.

**Numeric path:** source fidelity is reference membership/ownership plus frozen
unit, catalog, Pack, snapshot, prompt and raw/canonical response integrity.
Never parse generated text/finding/conclusion numbers for V2.4 numeric fidelity
or claim magnitude alignment. One statement/reference produces one diagnostic,
regardless of repeated prose. New numeric contracts are
`numeric-reference-fidelity-2.4` / `numeric-reference-comparability-2.4`.
Preserve numeric-materiality 1.0–1.3 and numeric-fidelity-comparability 1.0–1.1.

**Qualification:** keep one configured joint non-voting checker and its current
attribution, direction, scope, strength, role, finding/scope basis and omitted
material evidence schema. Supply selected backend quantities. Only after scope
assessment compare those quantities with backend submitted `numeric_effect`.
Reuse qualifier 1.4 and `magnitude_eligible`: no refs/unknown/ambiguous arithmetic,
PAF/OR/HR versus RR, percentage points versus relative percent and incompatible
or ineligible narrower scope cannot power exact magnitude. Such evidence facts
are not preflight operational failures, forced NEI or flipped judge labels.

**Why retain V2:** V3 bake-off controls showed false null-direction and narrow-dose
materiality classifications despite schema compliance. Unit-only classification
is not adopted. Production gates, models, retrieval, source selection, semantic
axes and vote thresholds remain unchanged. Persist new audits append-only and
reconstruct full requests/results at aggregation; no historical backfill.

**Acceptance:** offline plumbing/safety only; no paid calls. See
[results](STRUCTURED_NUMERIC_REFERENCES_RESULTS.md) for software checks and the
user's pending normal smoking-85 live test. Semantic correctness is unmeasured.

V2.4 removes generated prose from machine-critical numeric source fidelity.
It does not establish medical correctness or semantic qualification.

## ADR-050 — Version occurrence-local numeric roles and skipped checks

**Decision:** Retain fidelity/comparability separation with numeric-materiality-1.3
and diagnostic contract 1.1. Classify original numeric occurrences as source
assertion, claim reference, derived assertion, identifier or ambiguous before
matching. Save original text/spans, value/measure/direction reference status and
statement links in append-only JSONB. Explicit S1 results use S1's actual
frozen citations. Older numeric versions retain original semantics/hashes.

**Binding:** Recognize risk-attached x/× scalars/ranges through existing numeric
normalization, without arithmetic or scope promotion. Keep times-higher ambiguity.
Use explicit local measures/sentence boundaries; claim references cannot inherit
PAF. Alleged source support remains checked despite quoting, negation, “claimed”
or dependency=false. Keep wrong references and uncertain roles explicit. PAF
summaries need both bound fractions in one actual frozen quote; no RR conversion.

**Diagnostics:** A configured checker blocked by numeric preflight records an
explicit skipped state and blocking issue references, with zero attempts.
Genuine missing configuration stays distinct. Historical diagnostics are
immutable. No model, prompt, retrieval, revision loop, policy or threshold change.

**Acceptance:** Exact failures reproduced before edits. Retained actual
Grok/Luna/Claude passed real deterministic preflight within TTL. A labeled
offline double confirms boundary entry only; no new semantic qualification or
verdict. 63 controls, 787 backend tests, six PostgreSQL checks,
Ruff/mypy/Alembic/diff passed; zero paid calls. Numeric results section 10 records
the occurrence before/after and remaining semantic uncertainty.

## ADR-049 — Separate numeric source fidelity from claim comparability

**Decision:** Version the development numeric preflight as
`numeric-materiality-1.2`. Store frozen, typed
`numeric-fidelity-comparability-1.0` results for each raw finding, explicit
qualitative finding and numeric detail. First verify values, measure bindings
and permitted conversions against the cited frozen source. Only then compare
the verified quantity with the submitted claim and existing semantic axes.

**Reason:** Source-grounded lifelong risk ranges and attributable fractions
were being rejected as numeric uncertainty merely because they did not express
the claim's +85% relative increase. Source fidelity and magnitude eligibility
answer separate questions. Wrong or missing material numbers remain failures.

**Boundaries:** A verified different measure is retained but cannot power a
magnitude vote. Ambiguous “times higher” retains its literal meaning and no
invented percent increase. PAF/OR/HR are not automatically RR. Complete ordered
absolute-risk pairs and explicit RR/relative-change conversions record their
inputs/formulas; an interval alone is not a baseline pair. Mixed measures
inside a qualitative finding with empty numeric details remain an output
discipline defect; the backend never invents a cleaned finding.

**Compatibility:** Add diagnostics to existing append-only validation JSONB,
not tables or old rows. Replay numeric 1.0/1.1 under their original contract.
Raw judge responses and semantic axes remain unchanged. The existing qualifier
receives numeric alignment and magnitude eligibility; thresholds, proposed
labels, retrieval, models, prompts and production policy are unchanged.
Verdict Explanation 1.0 consumes only qualified new diagnostics descriptively.

**Presentation:** Development API exposes an allowlisted compact numeric
summary. Raw response disclosure remains collapsed by default and renders
wrapping text without an internal scroll box. Existing safety/excerpt limits
remain. Results and acceptance limits are recorded in
`NUMERIC_FIDELITY_COMPARABILITY_RESULTS.md`.

**Acceptance status:** Offline checks passed. One normal run used five of the
maximum eight calls; all models responded but only Luna qualified. New Grok
ASCII-x and Claude negated claim-reference wording failed conclusion numeric
preflight. Normal acceptance remains incomplete. The user's stop-after-failure
boundary was observed; no other layer was patched or further paid run made.

## ADR-048 — Deterministic, non-voting verdict explanations

**Decision:** Generate VerdictExplanation `1.0` only after deterministic
aggregation, with controlled templates over qualified audited inputs. Save it
inside new LensReport `1.3` JSONB snapshots with builder `report-builder-1.5`;
include it in the report semantic hash. It contains `summary`, `reason_category`,
nullable `established`/`unresolved`, and frozen qualified `evidence_ids`.

The verdict explanation is descriptive and non-voting. It cannot alter or
override the deterministic Lens verdict. No new judge, model call, retrieval,
outside medical knowledge, vote, threshold or qualification policy is added.
Rejected assessments cannot establish scientific facts or explanation citations.

**Priority:** For NEI, audited material magnitude gaps precede specific scope
gaps, causal design, material conflict, indirect/contextual evidence and direct
evidence gaps. Different estimates with noncomparable scope cannot become
contradiction. A quantitative Contradicted explanation identifies magnitude
only when qualified findings establish the qualitative direction plus decisive,
aligned numeric opposition. Unable remains a process/qualification explanation.
Fallback templates stay bounded when historical inputs lack structured axes.

**Compatibility:** New summaries and structured explanations are identical,
stored once and readable without recomputation. Historical report payloads and
hashes retain their old shape: no explanation backfill and no in-place update.
Existing JSONB persistence and append-only triggers require no migration.
Frontend adds the saved explanation beneath the label and exposes its fields
only in development technical details; existing diagnostic sections remain.

**Verification:** Twenty-one offline explanation controls; 692 backend tests plus
five PostgreSQL report/orchestration tests; 48 frontend tests; frontend build,
Ruff, mypy, Alembic check. No paid acceptance is needed for this layer.

## ADR-047 — Explicit judge and validator migration after provider failures

**Decision:** Keep development V2 decision 2.3, the current versioned judge prompt, the
joint evidence checker, current retrieval, validation axes, verdict gates and
append-only audits. Use the existing OpenAI-shaped chat transport for a named
`paratera` provider. After the user authorized other callable models, configure
judge 1 as AIMLAPI `x-ai/grok-4-3`, judge 2 as the
unchanged AIMLAPI `openai/gpt-6-luna`, judge 3 as AIMLAPI
`anthropic/claude-sonnet-5.5`, and the development joint validator independently
as AIMLAPI `anthropic/claude-haiku-4-5-20251001`.
The explicit validator configuration is development/test only; absent settings
retain the earlier slot-based behavior. No automatic runtime substitution occurs.

**Why fallbacks were needed:** The authenticated Paratera catalog listed
`DeepSeek-V3.2-Exp`, `GLM-4.6`, and `Baichuan-M2`, but actual structured chat
requests returned HTTP 404 for DeepSeek and HTTP 429 for Baichuan. The user's
specified first fallbacks, `DeepSeek-V4-Flash` and `GLM-5.2`, each returned HTTP
200 to a small JSON-schema probe, but the full normal path then exposed
DeepSeek timeouts and GLM-5.2 timeouts/invalid arrays. The expanded, bounded
research used actual retained frozen judge/validator requests. MiniMax-M3
passed one validator schema/ID probe but repeated schema failures in normal
smoke, so pinned Haiku replaced it. Non-thinking DeepSeek parsed some requests
but timed out on carrots and Vitamin C. Grok parsed two smoking requests in
9.6/10.6 seconds; six-case stability remains unverified. Sonnet returned parsed
judge proposals. Numeric and semantic
qualification still apply independently. Catalog listing and a small probe do
not establish full judge/validator compatibility. See
`PARATERA_MODEL_MIGRATION_RESULTS.md` for the bounded six-case live assessment.

**Boundary:** Do not weaken the structured schema, exact source IDs, material
numeric preflight, medical semantic policy, judge-count thresholds or production
qualification for a model. Provider/schema/timeout failures remain explicit.
Historical model runs are unchanged.

**Acceptance blocker:** AIMLAPI returned HTTP 403 with
`API key quota exceeded (ALL_TIME_LIMIT_EXCEEDED)`. Account balance remains
positive; the key quota needs an external change. Paid work stopped before
the planned Grok six-case check. Do not mark final normal acceptance complete.

**Diagnostics:** record a terminal unavailable event when a semantic request
is cancelled by its deadline. Read validator identity and timeout state from
the retained validation audit when live events are absent or still say calling.
This fixes the completed-analysis status display without altering an audit row.

## ADR-046 — Version numeric preflight and audit exact visible-source citations

**Decision:** For new development/test decision 2.3 runs, recognize bounded
range syntax and explicit references to the user's asserted magnitude without
turning them into source estimates. Distinguish material quantitative premises
from optional study details. Save numeric-materiality version 1.1 in validation
audits and reconstruct historical 1.0 exactly. Never suppress a mismatched
asserted effect or unresolved required magnitude.

The current 2.13 development judge input contains complete, frozen sections of
selected documents, including visible sibling passages. Permit citations to
that exact judge-visible set with backend-owned quotes and existing passage
hash/provenance/integrity checks. A model's parent evidence ID may be expanded
to its sole frozen `.U1` child only in development/test; retain the raw response
and a deterministic per-statement conversion record, and verify both in the
append-only audit. Unknown/ambiguous IDs and production shorthand still fail.
Production qualification and judge-count thresholds do not change. Keep a
bounded 75-second development joint-check deadline and 420-second claim budget.

**Reason and limit:** retained smoking run `0e8beb6c-196c-4a54-9f96-249de6988309`
failed numeric preflight for all three parsed judges despite syntactic range and
user-claim mentions. A later saved Luna response cited `E34` and `E2`; `E34`
was a judge-visible section of a selected document but not its representative
passage. Read-only replay of that exact completion now parses with two audited
ID conversions and has no deterministic numeric/provenance issue. Neither that
replay nor a transport smoke establishes that its medical conclusion is right.
The bounded normal repeat `38efcbb4-2f0e-4a01-bd05-c380bfdbe993` produced
one qualified Luna development assessment; Qwen timed out and ERNIE had a
materially unresolved, peripheral mLOY hazard-ratio assertion. The required
judge count still blocked the verdict. Do not treat numeric parser coverage as
permission to ignore such model statements or force a medical label.

## ADR-045 — Replace two repeatedly unavailable development judge slots

**Decision:** keep AIMLAPI GPT Luna as judge 2 and Ling claim extraction
unchanged. Configure Paratera Qwen3.5-35B-A3B as judge 1 and
DeepSeek-V4-Flash as judge 3. The existing development semantic checker
continues to use slot 3, so it changes to DeepSeek-V4-Flash automatically.
Keep verdict thresholds, source isolation, validation rules, model-family
distinctness checks and append-only audits unchanged. This is an operational
development configuration, not a production model qualification.

**Evidence and limit:** the latest normal analysis
`8fd27898-0858-4f58-8d30-aff36f8d750b` recorded GLM-4.6 timeout after
two attempts/80 seconds and DeepSeek-V3.2-Exp provider error; the validator
also used the unavailable DeepSeek model. On the corrected Paratera endpoint,
both replacement IDs returned HTTP 200 and parseable JSON in small probes.
This does not prove they can complete the full frozen Evidence Pack or the
validator's 25-second limit. Test that before treating the trio as reliable.

## ADR-044 — Correct Paratera transport without substituting model identity

**Decision:** use `https://llmapi.paratera.com/v1` for the two local Paratera
judge slots. Keep GPT Luna on AIMLAPI and retain the user-selected
DeepSeek-V3.2-Exp ID pending explicit replacement approval. The single
development semantic checker inherits judge 3's endpoint and remains failed
while that ID returns 404; no fallback or artificial validation is allowed.

**Evidence:** a short GLM-4.6 call and a full frozen-Pack judge call completed
on the corrected endpoint (the latter in one attempt, about 27 seconds).
DeepSeek-V3.2-Exp remained 404, Baichuan-M2 returned 429, and
DeepSeek-V4-Flash answered a short probe. The retained normal analysis
`06a25f0c-2eea-45ea-adb1-9542f36d69b8` recorded two GLM timeouts over
80 seconds on the old endpoint and a DeepSeek validator failure. These are
transport checks, not medical accuracy or production qualification evidence.

## ADR-043 — Separate gateway names from judge identity during local provider switch

**Decision:** use the existing generic `JUDGE_N_PROVIDER/MODEL/MODEL_FAMILY/
BASE_URL/API_KEY` configuration. Remove unused `MIRI_JUDGE_N_MODEL` entries
from local `.env`, retain the actual Miri credentials, and keep GPT Luna on
AIMLAPI. Locally, judge 1 switches to Paratera GLM-4.6 after a successful
frozen-Pack transport/schema probe. The user explicitly selected
Paratera DeepSeek-V3.2-Exp for judge 3 despite its current 404 response;
failures remain visible and do not become fabricated judge decisions. The
development-only model-status API distinguishes actual model identities in
retained runs from currently configured but uncalled slots. No verdict,
independence or production-qualification policy changes are implied.

**Evidence:** authenticated Paratera catalog lists GLM-4.6 and
DeepSeek-V3.2-Exp, but the latter's chat endpoint returned 404 twice.
Requested Qwen3-30B-A3B-Thinking-2507 and Qwen3-32B were absent from the
catalog and returned 403. Baichuan-M2 returned 429 twice. GLM-4.6 completed
one real frozen-Pack judge request in one attempt; catalog-listed
Qwen3.5-35B-A3B passed short transport/JSON probes but was not on the user's
requested permanent-judge list. These checks establish reachability and
format handling, not medical judgment quality or underlying family identity.

## ADR-042 — Stabilize pre-pilot framing and development audit without changing policy

**Decision:** Recover only literal numeric-claim subjects/endpoints from simple
explicit relations when model PICO slots fail source grounding. Store the source
numeric notation separately; keep malformed quantities uncertain. Use a
versioned frozen-child-ID conversion, new null/gradient reason audit and a
strict literal-source independence fallback. Expose a development-only failure
waterfall and retained-analysis export. Keep all three judges, Pack selection,
production thresholds, labels and `.env` unchanged.

**Reason:** the retained `85%` smoking run stopped at normalization because
the model's PICO outcome was a nonliteral paraphrase; no retrieval was attempted.
The 4.1 checks also showed exact-ID failures, null precision overreach and a
false optional-number independence rejection. Distinct raw and effective
diagnostics make these visible without rewriting judge conclusions. Legacy
serialized PICO omits the new null field to preserve historical pack hashes.

**Boundary:** a source-text precision signal is a necessary guard, not clinical
proof. Exact child-parent ID normalization is audited. A source-literal
qualitative premise can survive an optional numeric warning, but user-asserted
magnitudes and unresolved required quantities remain material. Manual pilot
results are needed before semantic acceptance or production claims.

## ADR-041 — V2 axes, explicit numeric materiality and unspecified comparator (Slice 4.1)

**Decision:** keep V2, Pack 1.5/current selection and the existing Ling/Luna/Gemini
Lite judge slots. New development/test decisions use 2.3, preserving original
text and explicit qualitative/numeric fields. One bounded label-blind Gemini Lite
request checks source attribution and independent direction/scope/strength/role;
Python qualifies the proposed label. No semantic revisions/replacement/threshold
or production-policy change. No `.env` edit or database migration.

**Reason:** the retained manual sunscreen run lost Ling and Gemini before
semantic checking solely for optional numeric content, while the relation checker
conflated contrary direction with comparator mismatch. Unspecified comparator
does not imply no exposure. A tested same-exposure frequency gradient can be
compatible-but-narrower; an active alternative or untested dose/population cannot
gain the same exception. Optional numeric defects are auditable warnings only
when an independently source-grounded qualitative premise survives. Quantities
asserted by the user, required by the proposition or an explicit dependency,
including transformations, remain strict. No raw text deletion or repaired vote.

**Additional observed defects:** joint attribution sometimes checked the user
claim instead of the judge's source description; canonical tuple/list differences
caused PostgreSQL audit false rejection; a model sometimes called imprecise null
evidence precise. Versioned prompt clarifications and a source-grounded necessary
precision check address these without assuming a final medical label. Original
classifier axes stay retained even when Python makes them nondecisive.

**Versions:** latest judge 2.12.1, joint axes 2.2, axes object 1.0, qualifier 1.3,
numeric materiality 1.0. Earlier judge 2.12, joint 2.0/2.1 and qualifier 1.2 are
reconstructed by their recorded versions. Historical 2.2/Slice 4 rows and results
are not rewritten. JSONB suffices; append-only triggers remain enforced.

**Evidence and limit:** 622 backend/PostgreSQL tests pass; live results improved,
but final null-direction/basis and numeric upstream grounding defects remain.
146/150 new reservations (including failures/retries) were used; the old exhausted
120-call ledger is untouched. The ≤100 preference was exceeded to diagnose two
failed normal batches and confirm the database repair, not for a new bake-off.
Stop architecture work; full semantic acceptance/public qualification is NOT
claimed. See `RELIABILITY_SLICE4_1_RESULTS.md` for the reviewed-pilot gate.

## ADR-001 — Keep the MVP pipeline-first

**Decision:** analysis is a staged evidence-verification pipeline, not a chat
completion or popularity-based fact checker.

**Reason:** claim decomposition, shared evidence, provenance, and abstention
are essential to medical safety and the competition differentiator.

## ADR-002 — PostgreSQL + pgvector for the initial corpus

**Decision:** use PostgreSQL with pgvector before introducing a separate search
or vector cluster.

**Reason:** the expected MVP workload is small enough that operational
simplicity is more valuable than premature distributed search infrastructure.

## ADR-003 — Preserve a four-label outcome

**Decision:** distinguish `NOT_ENOUGH_EVIDENCE` from `UNABLE_TO_VERIFY`.

**Reason:** a claim with inconclusive evidence is materially different from a
claim that cannot be reliably formulated or retrieved. Conflating them would
hide technical degradation as medical uncertainty.

## ADR-004 — Adapter boundary for external services

**Decision:** all OCR, evidence, model, storage, and other outbound services
are accessed through an adapter owned by the backend.

**Reason:** it prevents provider details from leaking into pipeline logic and
supports testing, fallbacks, auditing, and vendor changes.

## ADR-005 — No fake AI

**Decision:** routes must never generate simulated claims, evidence, or verdict
data that resembles a real analysis.

**Reason:** fabricated medical reasoning would undermine safety and make
integration behavior indistinguishable from a real verification result.

## ADR-006 — Phase 2 extraction fails closed

**Decision:** use a configured, OpenAI-compatible structured-output adapter
for semantic atomic-claim extraction and return an availability error when it
is not configured or returns invalid offsets.

**Reason:** sentence splitting or a simulated response cannot reliably produce
atomic medical propositions. A provider response is treated as untrusted too:
the backend verifies every returned span against the redacted source before it
can become a stored claim.

## ADR-007 — Re-encode then retain raw screenshots for at most 24 hours

**Decision:** accept only decoded static PNG/JPEG/WebP images, re-encode them
to metadata-free PNG, keep their bytes outside PostgreSQL, and purge uploads
and their short-lived analyses after 24 hours.

**Reason:** client-declared MIME types and image metadata are not trustworthy.
Short retention and position-preserving PII masking minimize exposure while
preserving source offsets required for claim auditing.

## ADR-008 — Use miri-api for ChatGPT Auto claim framing

**Decision:** default to `miri` while requiring a configured gateway address,
send only redacted content to the gateway's OpenAI-shaped chat completion,
request `chatgpt-auto`,
and validate its JSON and source offsets in the backend. Capture nullable PICO
fields from the same extraction response. The gateway address and optional
Bearer token remain in the local environment.

**Reason:** the supplied gateway documentation identifies `chatgpt-auto` as
the ChatGPT Auto picker mode. Its browser-backed responses do not guarantee
schema-constrained JSON or an exact underlying model version. Fail closed on
invalid responses, and do not assign UMLS/MeSH IDs without a verified
vocabulary source.

## ADR-009 — Ground PICO and leave terminology unresolved by default

**Decision:** consume the structured PICO proposal already returned by the
approved claim-extraction adapter, then retain only slot text present in that
same redacted atomic claim. Do not make an additional model call for each
claim. UMLS and MeSH remain separate provider interfaces; local providers
accept only caller-supplied fixture mappings. Runtime providers return no
identifiers until an authorized terminology source is connected. A candidate
below the configured confidence threshold is unresolved.

**Reason:** this prevents cross-claim leakage and invented clinical details,
avoids repeated gateway latency for the competition MVP, and distinguishes
query framing from verified vocabulary concepts or medical evidence.

## ADR-010 — Use a local, versioned official NLM MeSH descriptor index

**Decision:** import NLM's annual MeSH descriptor XML into an atomic SQLite
index outside source control. Use preferred labels and official entry terms for
deterministic exact/synonym matching; keep fuzzy results as suggestions below
the assignment threshold. Record MeSH production year and source-file SHA-256.
When no index is installed, leave IDs unresolved. Keep the UMLS provider
optional and independent. Re-normalize only untouched pending claims using
stored PICO, with dry-run as the default.

**Reason:** a local official source avoids sending sensitive claims to a
terminology API, makes matching reproducible, requires no UMLS license, and
does not fabricate identifiers. The claim's existing JSONB entity field can
carry provenance without another migration. NLM attribution and release
currency remain deployment responsibilities under its data terms.

## ADR-011 — Canonical assertion type and source-grounded completeness

**Decision:** use one controlled claim-type enum rather than a second relation
field. Explicit English causal/association wording deterministically takes
precedence over a conflicting model label; other wording uses the validated
model category. A bounded set of historic labels maps to canonical values,
while unknown new labels are rejected. The exact raw span remains separate.

**Decision:** `normalized` requires source-grounded required-slot and lexical
MeSH completeness checks, plus resolved identified mentions. Preserve
`pending`, `unresolved`, `pico_only`, and `partially_linked`; add `partial` for
missing slots/source concepts or an incomplete source scan. A nullable JSONB
quality audit stores coverage and warnings. On migration, legacy `normalized`
rows become `partial` with `legacy_not_audited`; existing mappings remain
untouched. The pending-only re-normalizer does not rewrite them.

**Reason:** linked extracted mentions are not proof that all explicitly stated
concepts were extracted. The Vitamin C/common-cold omission demonstrated this
failure mode. MeSH exact/entry-term checks are reproducible but lexical, not
medical evidence; generic terms and fuzzy suggestions cannot force a finding.

## ADR-012 — One bounded extraction retry, then fail closed

**Decision:** both existing OpenAI-shaped adapters make at most two requests.
Malformed JSON/schema/empty/unsupported responses receive one strict-JSON
repair prompt with the same redacted source, never the invalid answer.
Timeouts, transport failures, HTTP 429, and HTTP 5xx retry once; other HTTP
errors fail immediately. Exhaustion keeps the existing public 502/503 error
codes. Diagnostics log only non-sensitive provider/model, failure class,
attempt count, latency, and a validated upstream request ID.

**Reason:** browser-backed responses can violate JSON structure despite an
HTTP 200. A small retry improves resilience without weakening validation,
adding an unapproved provider, or fabricating claims.

## ADR-013 — Bound claim-extraction wall time

**Decision:** each extractor attempt has a configurable 55-second default
timeout (maximum 60 seconds), and the entire operation has a configurable
115-second default deadline (maximum 120 seconds). An asynchronous deadline
wraps the actual HTTP request, even if an HTTP client ignores its own timeout.
At most one retry remains available. Empty responses still qualify for that
retry. Exhausted attempt timeouts return `claim_extractor_timeout`; an overall
deadline returns `claim_extractor_deadline_exceeded`, both with HTTP 504.

**Reason:** a browser gateway can return slowly or produce an empty first
reply. Two former 180-second attempts allowed the API to outlast common client
timeouts. Distinct failure codes and logs make timeout behavior observable
without disclosing prompts, credentials, or provider responses to users.

## ADR-014 — PubMed-only, content-addressed Evidence Pack foundation

**Decision:** Phase 4A plans small deterministic PubMed query variants from
source-grounded PICO and confident MeSH concepts. It uses NCBI ESearch/EFetch,
never HTML scraping. Search PMID lists may be cached briefly in Redis; Redis
is never the evidence system of record. Documents are keyed by PMID and
content hash so metadata revisions do not overwrite earlier source versions.
Each retrieval run stores query provenance and creates a new, append-only JSONB
Evidence Pack with backend E IDs and canonical SHA-256. Retrieval timestamps
do not affect the content hash. Ranking is lexical topical relevance only.

**Reason:** later judges must see identical, auditable source bytes and cannot
invent identifiers. A bounded official adapter and simple relevance ranking
meet the MVP latency/complexity target without implying medical truth or study
quality. Subsequent source and retraction checks remain separate work.

## ADR-015 — Separate auditable passages from judge-facing evidence selection

**Decision:** Phase 4A.1 Evidence Packs use version 1.1. All extracted PubMed
title and abstract passages remain ranked and frozen with E IDs. An ordered
`selected_evidence_ids` subset identifies future judge input, with a default
maximum of one passage per document. Selection favors directly relevant
abstracts, while title-only evidence is retained and may be selected when its
core-concept coverage is unique or no usable abstract exists. Lexical/MeSH
concept coverage and conservative outcome-only background penalties are
recorded as relevance factors. The selected IDs and flags enter the pack hash;
older version 1.0 packs remain readable but are not automatically judge-ready.

**Reason:** multiple passages from one PMID can otherwise dominate a small
top-k, and a broad outcome review can rank like a paper directly discussing
both claim concepts. Selection must improve topical diversity without hiding
source text or implying a truth, causal, or study-quality judgment.

## ADR-016 — Treat publication integrity as checked, versioned metadata

**Decision:** Phase 4B parses PubMed publication types and linked
`CommentsCorrections` records, then optionally checks DOI-bearing records
through Crossref's REST API using `CROSSREF_MAILTO`. Crossref is enrichment,
not a medical search source. Its per-DOI timeout, one retry, bounded 429
backoff, three-way concurrency cap, 30-second overall enrichment budget, and
versioned one-hour Redis cache are fail-open for PubMed retrieval. DOI-less
records mark Crossref `not_applicable`; configured failures/not-found and
unconfigured DOI checks never imply `valid`. Positive signals from either
provider win, with severity order retracted, expression of concern, corrected,
updated. A retraction notice's `update-to` target is recorded but must not
label the notice itself retracted; `updated-by` can label the original.

**Decision:** Evidence Pack 1.2 freezes per-provider check status/version,
integrity status/sources/references/warnings, Crossref fields, field provenance,
study design, methodology `quality_prior` and factors, applicability warnings,
and selection. PubMed bibliographic values are not overwritten by Crossref.
Semantic changes alter the hash, while check/retrieval wall-clock timestamps
do not. The append-only pack JSONB is authoritative; the pre-existing
`evidence_document.retraction_status` column is legacy bibliographic storage,
not a current integrity decision, so no schema migration is required.

**Decision:** Study design is classified without an LLM from PubMed publication
types, then structured MeSH, then conservative title wording; uncertainty is
`unknown`. `quality_prior` is a transparent methodology heuristic, not truth,
claim support, or verdict confidence. It is not added to the topical
`retrieval_score`. Retractions remain auditable but are excluded from selected
evidence; unknown integrity stays eligible with warnings. `partial_metadata`
denotes incomplete/missing EFetch records or unsupported PubMed book records,
while reason counts expose optional field absences and enrichment failures
separately.

**Reason:** medical claims can be harmed by treating a retracted source, a
metadata outage, or a prestigious but irrelevant review as decisive evidence.
Separate typed signals and immutable provenance let later judges evaluate the
same snapshot without hiding uncertainty or conflating retrieval relevance
with study quality.

## ADR-017 — Separate relationship directness from relevance and evidence truth

**Decision:** Phase 4B.1 adds deterministic, claim-specific document and
passage `relationship_directness` with an exposed `[0,1]` score, direction
(`aligned`, `reverse`, `incidental`, `unknown`), factors, reasons, and warnings.
Only PICO wording and confident exact/synonym MeSH labels expand concepts.
Same/adjacent sentence and section occurrence, RESULTS/CONCLUSIONS weighting,
relation cues, post-outcome framing, background/covariate-only mentions, and
explicit exposure/population exclusions affect directness. Ambiguous direction
remains unknown. The signal is a heuristic for addressing the same question,
not entailment or support/contradiction; a paper finding no effect can be
highly direct.

**Decision:** Keep `retrieval_score`, `quality_prior`, integrity, and directness
separate. Version 1.3 records an explained selection priority (30% topical,
45% passage directness, 20% document directness, 5% study-quality prior, minus
an applicability penalty). It chooses the strongest direct representative per
document, preserves the one-PMID default and hard retraction exclusion, and
retains every nonselected record in the append-only pack. Version 1.3 hashes
the new metadata and selection. Existing pack JSONB needs no schema migration;
older packs are not rewritten.

**Reason:** topical overlap selected a zinc review for a Vitamin C prevention
claim, post-stroke BP management for a hypertension-to-stroke-risk claim, and
screening/cessation or never-smoker contexts for a smoking-to-lung-cancer-risk
claim. The bounded lexical rules address these reproducibly without a new
model, fabricated medical inference, or PMID-specific hardcoding. Their
precision/recall and multilingual coverage still require Phase 7 evaluation.

## ADR-018 — Freeze one pack before independent judging

**Decision:** Phase 5A accepts only hash-verified Evidence Pack 1.3 snapshots.
All active judge slots receive the same canonical versioned prompt containing
the same exact claim and ordered selected E passages; no new retrieval or model
tools are available during judging. Slots explicitly state provider, requested
model, and actual model family. Duplicate families are rejected except under a
development/test-only override. Miri and other OpenAI-shaped gateways use one
adapter interface; no model IDs are hardcoded.

**Decision:** individual judges have only `supported`, `contradicted`, and
`not_enough_evidence`. Strict Pydantic validation rejects unsupported labels,
missing fields, and citations outside the selected E IDs. A 45-second attempt
limit, 80-second total per-slot deadline, one retry, bounded concurrent calls,
and process-local circuit breaker isolate failures. An append-only `judge_run`
record links every success or failure to pack ID/hash, prompt version/hash,
provider/model/family, attempt/timing diagnostics, and validated canonical
response when available. Claim/pack retention cascades apply. Descriptive
agreement statistics are not a vote, confidence score, or final verdict.

**Reason:** independent model opinions are only comparable when they assess
identical evidence. Existing `model_evaluation` includes an orchestrator-only
label and lacks failed-run/pack provenance, so a dedicated audit table avoids
misrepresenting technical degradation as a medical decision. Miri browser
aliases do not prove model pinning or that native browsing is disabled; these
controls must be verified before production use.

## ADR-019 — Permit search-enabled Miri modes only for marked development smoke

**Decision:** keep the conservative search-mode name guard on by default and
unconditionally reject matching modes in staging/production. In development
or test only, an explicit `JUDGE_ALLOW_SEARCH_ENABLED_DEVELOPMENT=true` permits
a plumbing smoke. The service independently rechecks the environment and flag.
All runs in a bypassed ensemble, including failures, store
`search_override_active=true` and `search_isolation_verified=false`; matching
slots store `search_guard_bypassed=true`. The CLI warns before calling models.
The canonical prompt version advances to `judge-1.1-2026-09-26` and explicitly
forbids search and outside sources. No search/browsing tool is passed.

**Reason:** the available Miri modes can trigger the name guard, preventing a
live integration smoke. The override tests transport, parsing, persistence,
and failure isolation without misrepresenting a browser-backed model's native
search behavior as controlled. It cannot qualify a model or a medical judgment
for production.

## ADR-020 — Advance to evidence validation without qualifying the live ensemble

**Decision:** the 2026-09-28 development Miri smoke is sufficient to proceed
with Phase 6 citation and evidence validation against frozen Evidence Pack 1.3
and strictly validated judge-response fixtures. It is not a release gate for
live verdicts: two of three configured family labels returned valid responses,
while Gemini returned malformed JSON twice. The smoke used a development-only
search guard bypass, so evidence isolation and underlying model-family identity
remain unverified. Do not interpret descriptive agreement among two successful
slots as a three-judge consensus or aggregate it into a medical verdict.

**Reason:** the smoke exercises the transport, schema, shared-pack, and audit
paths enough to develop the next deterministic validation layer. A public
judgment still requires reliable structured output, verified distinct/pinned
families, provider-side search controls, and the later citation/entailment and
risk-aware verdict gates.

## ADR-021 — Validate judge evidence use separately, with fail-closed semantics

**Decision:** Phase 6A validates each successful `JudgeDecision` against its
exact frozen Evidence Pack 1.3. Recheck selected E IDs, canonical pack and
passage hashes, document provenance, and frozen integrity before bounded
numeric, PICO/scope, and relation-strength checks. Fatal deterministic issues
short-circuit optional per-passage entailment. Association-only evidence
cannot justify a decisive causal judgment but can explain a legitimate
`not_enough_evidence` decision. Cited and opposing roles are validated
independently. Structured entailment stays behind a provider-independent
interface; no live provider is approved in this phase. An absent or failed
provider produces `unable_to_validate`, never manufactured validation.

**Decision:** every validation execution creates a new append-only
`judge_validation_run` with versioned deterministic rules, prompt/provider
provenance when used, result JSON, timing, and failure type. A PostgreSQL
update trigger mirrors the existing judge-run protection; normal claim
retention cascades remain. No public endpoint, final verdict, confidence,
aggregation, or user-facing report is introduced.

**Reason:** model citations can be real but misused through numeric distortion,
population shift, or association-to-causation overclaim. Separate typed audit
records expose those defects without confusing validation of a judge's
reasoning with medical truth or treating development Miri labels as ground
truth. Conservative `uncertain` states prevent lexical heuristics from posing
as clinical entailment.

## ADR-022 — Aggregate only qualified, validated evidence under a versioned policy

**Decision:** Phase 6B uses immutable, explicit-ID `AggregationInput` and a
pure `verdict-policy-1.0` decision table. The only labels are `supported`,
`contradicted`, `not_enough_evidence`, and `unable_to_verify_reliably`. First
rehash the frozen Pack 1.3 and check normalization, retrieval, selection,
and audit identity. Successful no-results retrieval is evidence insufficiency;
technical retrieval failure is system inability. Only `validated` judge
decisions without fatal issues enter decisive counts. Partial, invalid, failed,
or unavailable judgments are retained as exclusions, never flipped to an
opposite label. Standard risk requires two same-direction validated judges
and zero validated opposition; high risk requires three unanimous validated
judges. Validated conflict or inconclusive evidence abstains as
`not_enough_evidence`; too few qualified judges abstains as
`unable_to_verify_reliably`. No raw-label majority, brand weights, numeric
truth confidence, or LLM final choice is permitted.

**Decision:** production eligibility additionally requires audited underlying
model snapshot/identity, family verification, verified search isolation with
no development bypass, and a policy-approved entailment provider. New judge
audit flags default false; current Miri service cannot self-certify them.
Policy 1.0 approves no live entailment provider. Offline fixture/evaluation
mode can demonstrate logic but is always explicitly non-production. Every
aggregation inserts a new `verdict_run` with input IDs, controlled reasons,
policy/engine versions, semantic hash, and a PostgreSQL update-blocking
trigger. The legacy `final_verdict` table remains unused and no public route
or explanation is introduced.

**Reason:** two matching model labels do not repair a broken pack, an invalid
citation, uncertain entailment, or an unverified browser-backed provider.
Explicit provenance makes policy results reproducible and prevents silent
promotion of the 2/3 development Miri smoke into medical truth. Approval of
live semantic validation or model identity requires reviewed policy and
provider changes, not a casual development switch.

## ADR-023 — Build reports only from frozen, validated audit records

**Decision:** Phase 6C uses a versioned, pure report builder over one named
VerdictRun, its frozen Pack 1.3, and only the judge/validation IDs recorded by
that run. It never changes or redecides the verdict. Four display labels and
every verdict reason code have controlled prose. No LLM-generated medical
explanation, numeric truth confidence, outside-source lookup, or latest-row
selection is permitted. Source cards show exact bounded frozen passages only
when selected and cited by qualified, fully validated assessments; metadata
and citation roles retain their audit provenance. Operational inability does
not show evidence cards. Material numeric, causal-strength, scope, and
integrity issues become explicitly separate limitations.

**Decision:** `production_qualified=false` forces an in-contract visible
development/evaluation notice, so current Miri-like records cannot appear as
ordinary trusted reports. Every report also carries a separate, concise
health-information safety notice. The semantic hash excludes only generation
time; each execution inserts a new append-only `report_run` with an UPDATE
trigger and claim-retention cascade. The CLI remains development/test-only;
there is no public HTTP or frontend report contract in this phase.

**Reason:** source excerpts and deterministic qualification metadata can be
presented reproducibly without granting another model freedom to invent or
overstate medical conclusions. Immutable report snapshots preserve the exact
presentation that was emitted even if controlled wording changes later.

## ADR-024 — Persist orchestration checkpoints and gate frozen report reads

**Decision:** Phase 7A reserves an `analysis_run` before slow work, returns
HTTP 202, and executes the existing services in a single-process FastAPI
background task. Each atomic claim has its own `claim_analysis_run` with
explicit Pack ID/hash and JudgeRun, JudgeValidationRun, VerdictRun, and
ReportRun IDs. These two records hold mutable progress/timestamps and safe
failure categories; the referenced evidence and audit records stay immutable.
The analysis UUID becomes the Submission UUID when ingestion commits. Client
`Idempotency-Key` is hashed and unique with a canonical request digest;
identical retries return the same run, mismatched requests fail 409. Without
a key, a new request creates new immutable work intentionally. An expired
key fails 410 rather than returning an analysis that polling cannot read.

**Decision:** there is no automatic stage replay or startup replay of external
model calls. In the single-worker MVP, startup marks abandoned queued/running
runs failed. A checkpoint gap can leave an orphaned immutable artifact; the
system never guesses a latest row to repair that gap. The run has bounded
retrieval, claim, and total time budgets. Claims fail independently, and
adapter initialization failure becomes a failed run rather than a stuck queue.
Technical failure does not become Not Enough Evidence. Polling is the current
progress contract; the events route is a one-shot SSE snapshot rather than a
live event bus.

**Decision:** the report route reads only the checkpointed ReportRun and
verifies its hash, recomputes the frozen Pack content hash, and checks full
claim/Pack/verdict/audit linkage. A failed claim has no result label until a
VerdictRun exists. Staging/production suppress unqualified result labels and
deny a non-production-qualified report server-side. Development/test return
the unchanged LensReport with its compulsory evaluation notice. URL fetching
and frontend redesign are outside this phase. Analysis responses are
non-cacheable with no-referrer headers. The anonymous UUID convention is not
user authentication; public deployment requires an access-control and
distributed-worker review.

**Reason:** one request can now traverse the implemented evidence pipeline
without duplicating medical logic, combining independent claims, or
accidentally promoting Miri/unapproved entailment outputs. In-process tasks
and explicit no-replay semantics meet the competition MVP's complexity
constraint while honestly recording their crash-recovery limitations.

## ADR-025 — Use framework-free TypeScript for the competition web client

**Decision:** replace the early Phase 2 React/Tailwind shell with vanilla
HTML, CSS, TypeScript, and Vite. Keep small typed API, page, component, and
utility modules instead of a custom reactive framework. Poll the Phase 7A
status and claim checkpoints; the SSE endpoint is a one-shot snapshot, not a
live stream. Use History API routes `/` and `/analysis/{uuid}` and the existing
Vite/Nginx SPA fallback. Submit an opaque idempotency key per deliberate
attempt, retaining it for uncertain retries. A same-tab session record may
store only a content digest, key, and upload UUID, never raw medical text or
image bytes.

**Decision:** render backend LensReports without browser-side medical
reasoning. Preserve four controlled verdict labels, exact frozen excerpts,
the separate safety notice, and a visually prominent backend development
notice whenever `production_qualified=false`. A 403 report gate is displayed
as release ineligibility, not as a medical verdict. Untrusted claim/source
text enters the DOM only as text; source links require backend-provided
HTTP(S) URLs. Avoid demo fixtures in the running product and do not bypass
the backend qualification gate.

**Reason:** the original framework was only a placeholder. A small modular
client keeps the competition MVP understandable while making the complete
claim-scoped pipeline usable and preserving medical and security boundaries.

## ADR-026 — Ground coordinated subjects and retain lexical retrieval for partial terminology

**Decision:** exact extraction span validation happens within the existing
one-retry, 115-second total deadline. If the first structurally valid response
omits an exposure or outcome in an explicit relation, that same single retry
may request repair; a still-missing slot remains `partial`. For subject ellipsis
in an adjacent coordinated `and` clause (with optional comma), normalization
may carry only the exact preceding
subject when the extractor's antecedent offsets, both source slices, and a
small explicit English verb pattern all agree. The later soy regression also
permits the second clause's *explicit* verb object to fill a model-omitted
outcome when the shared-subject syntax is independently verified. It does not
fill an outcome for a standalone claim, change the original span, or assign an
unverified MeSH ID.

**Decision:** `partially_linked` means source PICO is complete but some
terminology mentions lack a safe ID. Only an audited row with complete
source-grounded PICO, explicit completeness fields, and no missing concepts or
unsafe source-scan warnings may use lexical PubMed queries and continue to the
existing verdict policy. The standalone verdict loader rechecks this eligibility;
legacy unaudited rows fail closed. `partial` (missing required slots or source
concepts), `pico_only`, and `unresolved` remain blocked. No judge,
citation, search-isolation, or production-release guard changes. Nondiagnostic
exposure words such as `regular` and `usage` are omitted from lexical query
terms, while the exact qualified exposure stays in frozen PICO and audits.

**Reason:** a colloquial but explicit exposure such as "regular usage of soy"
must not silently become a fabricated vocabulary match or be rejected solely
because MeSH lacks an exact synonym. The original two-clause sentence exposed
both an omitted model outcome and discarded shared subject. The bounded repair
and source-checked coordination preserve that meaning without treating an
unresolved terminology code as missing medical evidence.

## ADR-027 — Treat extractor rate limits as operational failures

**Decision:** keep the configured ChatGPT extraction model and the existing
one-retry/total-deadline boundary. A provider HTTP 429 is logged with only its
status code, optionally waits for a numeric or date `Retry-After` within the
remaining deadline, and becomes `claim_extractor_rate_limited` if retry is
exhausted or cannot fit the deadline. The web client presents extraction
outages and rate limits as operational failures, never medical verdicts. No
silent fallback to another model or fabrication of claims is permitted.

**Reason:** the live Miri catalog listed `chatgpt-auto`, but a chat probe
returned 429 and the user's analysis stopped before extracting any claim.
Immediate retries and a generic verification-failure screen obscured the
actual operational condition.

## ADR-028 — Keep generic aliases and unrelated studies out of selected evidence

**Decision:** an isolated generic MeSH entry term such as `consumption` must
not resolve a multiword exposure to `Economics`. Query planning falls back to
the source-grounded PICO slot when an entity is only a generic alias or a
population modifier. The linker likewise leaves an exposure unresolved rather
than recording `Male` as its intervention when it occurs only in an explicit
demographic suffix. Query planning retains an outcome qualifier in a bounded
lexical variant. Explicit nonhuman study subjects in a title take precedence
over ambiguous mixed species metadata. Nonhuman studies for claims without an
explicit animal subject, and documents without a sufficiently direct two-core-
concept focus, remain in the immutable, auditable Evidence Pack but are not
selected for judge prompts. If no paper qualifies, selection may be empty;
retrieval never manufactures a substitute. These are relevance and
applicability heuristics, not medical support or contradiction judgments.

**Reason:** the live soy run linked `consumption` to `Economics`, queried only
that MeSH concept for the estrogen claim, and omitted soy from the muscle
query. A later retrieval included papers explicitly about ducks, crabs, pigs,
and broilers despite the human-health context; one pig paper even had both
`Humans` and `Animals` MeSH tags. The source-grounded queries and conservative
selection keep such hits auditable without presenting them as direct medical
evidence. Judge qualification and verdict gates are unchanged.

## ADR-029 — Bound development model diagnostics and distrust provider JSON mode

**Decision:** In development/test only, a single-process, expiring trace records
actual extraction/judge call states, typed failures, and at most 3000 characters
of visible completion content per event. It never records requests, provider
reasoning fields, or credentials; production/staging ignore `DEBUG_MODE`.
This diagnostic trace is not a durable audit or a provider-wide heartbeat.
OpenAI-compatible extraction repeats a JSON-only instruction in the system
message because a live provider ignored `response_format`. Exact unique
source spans may have arithmetic offsets corrected locally; non-unique or
invented spans still fail validation. An empty claim array for source text
containing an explicit health-relation cue gets the existing single retry and
then a typed failure, not a fabricated claim.

**Reason:** live Ling output was sometimes YAML-like or contained correct
source text with incorrect offsets, producing no claims. Other long requests
still timed out at the configured deadline. Developers need to distinguish
calling, responding, invalid content, and provider unavailability without
loosening medical evidence or public-release gates.

## ADR-030 — Cross-check inconclusive evidence use in development only

**Decision:** development/test orchestration uses `fixture_or_evaluation`
aggregation and may send each cited frozen passage to a different configured,
non-search judge-family model through a no-tools entailment adapter. Strict
E-ID JSON results, provider/model, and prompt hashes remain in append-only
validation audits. The adapter is not approved for production. A partially
scoped source may qualify an *inconclusive* evaluation assessment only when
every cited use is semantically validated and no other material warning is
present; decisive and production gates remain unchanged. Such citations may
appear as `relevant_but_insufficient` cards with the evaluation notice. Old
reports are never rewritten.

**Reason:** the hypertension/cancer run had relevant observational passages
and two inconclusive judges but no live citation validator. A first live
validator confused "supports the explanation of insufficiency" with "proves
the causal claim"; the versioned prompt now distinguishes them. Ling HTTP 500
outages remain separate operational failures with no silent model fallback.
The changed abstention qualification is versioned as `verdict-policy-1.1`
and `verdict-engine-1.1`; report rendering is `report-builder-1.1`.

## ADR-031 — Bound judge citation selection and audit protocol-only repair

**Decision:** judge prompt `judge-1.6-2026-09-29` requires the smallest set
of passages that directly supports each cited use. It warns against adding
generic background, indirect estimates, or title-only topical matches to a
decisive judgment. The independent citation validator and verdict thresholds
are unchanged. If a provider omits only the constant `schema_version`, local
parsing can insert `1.0` and revalidate the entire decision. The append-only
judge row marks `schema_version_inferred`; production qualification rejects
that row. No medical content, citation, or label is silently repaired, and an
old judge or verdict run is never rewritten.

**Reason:** a live smoking/lung-cancer run had direct frozen passages, but two
decisive judgments also cited weaker passages and failed citation validation.
The third provider returned otherwise structured JSON without the mandatory
protocol version. Topical over-citation should be reduced at generation;
protocol-only omission should be visible in the audit rather than disguised
as a fully native schema-valid answer.
Invalid citation IDs or unlisted E mentions may use the existing single
retry, but the first response remains rejected and citations are never
silently removed from a model decision.

## ADR-032 — Require standalone atomic claims and measure endpoint fit separately

**Decision:** the exact redacted `raw_text`/offsets remain immutable source
provenance. For new claims, a deterministic validator constructs independently
readable `normalized_text` only from the clause itself or an adjacent,
unambiguous English shared subject. The persisted `standalone_status` and
verified antecedent offsets distinguish reconstructed text from a literal
source span. Uncertain/incomplete fragments are `partial` and stop before
normal retrieval. A source-grounded population can be carried to PICO; no
unstated qualifier or causal strength is inferred.

**Decision:** preserve broad PubMed recall and add bounded endpoint-focused
precision queries for explicit measured outcomes. Score title/abstract
outcome-as-endpoint signals separately from topical `retrieval_score`,
relationship directness, study quality, integrity, and applicability. Favor
measured outcomes in selection; mechanistic/background/unrelated endpoint
hits remain auditable. Contrary findings can be highly endpoint-direct.
Normalize selection priority by the maximum title-bonus weight so ties at
1.0 do not erase ordering; demote reverse/incidental relationships and
post-disease endpoints for disease-risk claims without treating those
signals as a medical verdict. If an extractor inflects only the leading
relation verb in a proposed outcome, retain the exact remainder only when
it occurs verbatim in the atomic source span.
When three strong quantitative-endpoint documents are present, do not fill
selection with documents scoring below 0.35 on endpoint directness; preserve
all such documents in the auditable pack. Keep broader directly measured
studies eligible even when their titles use less specific hormone wording.
Evidence Pack 1.4 freezes endpoint factors and the changed selection order;
historic Pack 1.3 retains its exact canonical hash path. A nullable claim
status column requires migration `20260929_0016`; old rows remain nullable
rather than being falsely certified as reconstructed.

**Reason:** coordinated soy claims lost the shared subject even though PICO
could recover it, while estrogen-related meningioma/bone-health papers could
rank as topical matches without measuring the asserted hormone endpoint.
These are extraction and retrieval-selection defects, not grounds to change
judge labels, citation validation, verdict thresholds, or report templates.

## ADR-033 — Validate attributed findings before proposed conclusions

**Decision:** new judge requests use strict decision schema 2.0: one
source-attributed statement per finding/method/limitation, exact quote and E
ID for each reference, and a separate proposed-label justification naming
its statement IDs. A statement may cite multiple frozen passages jointly.
Judge input `judge-input-2.0` groups exact frozen sections by selected
document, records omitted E IDs and a content hash, and is identical for all
judges. Passage IDs remain from the immutable Pack; historical Pack 1.3/1.4
hashes and old judge rows are not rewritten. The old **whole free-text
explanation against each individual citation** approach in ADR-021 is
superseded for new runs. Historical v1 decisions remain readable, but no
statement mappings are inferred for them under policy 1.2.
Snapshot equivalence is checked by canonical JSON content hash after JSONB
round-trip, not Python tuple/list object equality; the latter caused a live
false provenance failure and is covered by a regression test.

**Decision:** `judge-validation-2.0` first checks pack/input/quote/number
provenance per statement, then asks a no-tools semantic validator whether the
*statement* is attributed, and separately whether validated findings justify
the proposed label for the *original claim*. Typed target-specific issues
identify judge statement versus user claim versus source metadata. A correctly
quoted estimate from one study is not compared with every other citation or
with a user claim number. OR/RR/HR and other typed measures are not silently
substituted. Missing context stays uncertain. The source can contradict the
user claim while supporting an accurate judge statement; a null result alone
does not establish absence of effect. Valid findings remain recorded even
when a conclusion fails. Mock semantic providers test orchestration only;
the bounded, opt-in real-model semantic command is not clinical validation.

**Decision:** after a target-specific invalid validation, at most one
same-provider, same-model semantic revision may be requested. It sees only
the original claim, the *same* frozen input, its own response, and its own
issues. The new append-only judge row links to its parent and gets one model
attempt, without another schema retry. An explicit claim checkpoint names
only the active run per slot for aggregation; parent and failed revision rows
remain audit records, never second votes. Database uniqueness prevents a
second child revision. `verdict-policy-1.2` retains existing 2/3 minimum
judge counts and production identity/family/search/validator gates; it accepts
only v2 validation. Policy 1.1 remains for historical fixtures and audit
reading, not reinterpretation of old free text.

**Decision:** report contract 1.1 and builder 1.2 attribute numeric issues to
the actual target. An Unable result in development may show a separate
neutral set of exact frozen, hash-verified retrieved excerpts, explicitly not
validated support or opposition. Staging/production still deny unqualified
reports. Debug events bind analysis/claim/judge/validation/call, operation,
statement/E IDs, and revision; `calling` means awaiting a response. Stage
execution is displayed separately from accepted assessment counts.

**Reason:** retained sunscreen analysis
`9338114b-f9fe-4642-b1e3-29830073400f` proved the old contract could
cross-compare two studies' numbers, label E8 as contradicting judge use while
its explanation said it opposed the *user claim*, and blame a nonexistent
numeric magnitude in the claim. It also showed PMID 21135266's METHODS and
RESULTS frozen but hidden behind its selected CONCLUSION. None of these
observations establishes a particular sunscreen verdict; the old 1-of-3
qualified Unable result remains an immutable historical outcome.

## ADR-034 — Permit a clearly provisional single-assessment result in development

**Decision:** new live V2 runs use `verdict-policy-1.3`. Only in
`fixture_or_evaluation` mode, for a standard-risk claim, one fully validated
decisive judge assessment may yield a provisional `supported` or
`contradicted` result. The report labels this “Provisional … (Development
Only),” keeps `production_qualified=false`, displays its exact validated
citations, and records `EVALUATION_SINGLE_VALIDATED_ASSESSMENT` alongside all
excluded-assessment reasons. Zero qualified judges, an inconclusive qualified
judge, partial/invalid validation, no selected evidence, and high-risk claims
cannot use this branch. Production still requires two independently qualified
judges for standard risk and three for high risk, plus all existing identity,
search-isolation, provenance, and approved-validator gates. Policies 1.1 and
1.2 and historical append-only records are unchanged. This is a prototype
demonstration output, not a public medical report or a substitute for the
Phase 8 clinical evaluation benchmark.

For causal/prevention/treatment wording under policy 1.3, a decisive label
also needs at least one *conclusion-cited* trial or evidence synthesis in the
frozen Pack. An observational/unknown-design citation alone yields
`not_enough_evidence` with `CAUSAL_EVIDENCE_TOO_INDIRECT`, even when a semantic
model mistakenly calls a reverse-direction association decisive. Study-design
metadata is a conservative sufficiency gate, not a truth vote; a trial or
synthesis still needs normal attribution and conclusion validation.

**Reason:** live runs on a direct smoking/lung-cancer association found and
validated strong cited evidence but frequently lost the second vote to
provider response-shape or semantic-validator availability. Reporting only
`Unable to Verify Reliably` hid that one assessment had actually passed every
available evidence-use check. A versioned, visibly provisional evaluation
result preserves useful prototype behavior without silently releasing a
single-model medical verdict.

## ADR-035 — Increase retrieval recall and repair validation contract edges

**Decision:** the PubMed query planner retains MeSH/source-grounded queries
and adds bounded automatic-term/lay-word fallbacks when a literal phrase is
overly restrictive. Selection ranks direct exposure-outcome endpoint studies
above generic topical articles and keeps exclusions in the auditable Pack.
The judge accepts at most eight attributed statements and 1,200 conclusion
characters, while its prompt still requests one or two concise decisive
findings. Exact source IDs and quotes, numeric alignment, semantic validation,
and the frozen input hash remain mandatory. The numeric parser recognizes
`confidence interval (CI)` as well as `CI`, avoiding comparison against the
wrong interval in a multi-estimate passage. The semantic validator receives
and must echo exact required statement/evidence identifiers. Statement
attribution deliberately omits the original claim so the model cannot
confuse a source-to-statement check with the final claim check. No retrieval
rank is treated as a medical support vote.

**Reason:** the carrot/eyesight smoke had no selected papers because the
literal query missed ordinary vision wording; smoking/lung-cancer runs had
direct studies yet lost judges to bounded JSON-shape issues and one false
numeric mismatch. These repairs improve reachability and audit fidelity, not
the medical truth threshold for a production verdict.

## ADR-036 — Preserve the assessed soy claim and exclude unasserted comparisons

**Decision:** show a source-verified `normalized_text` as the claim title when
an atomic source span omits an adjacent shared subject. Keep the exact raw span
and inherited offsets in the API and audit record. The judge prompt now states
that `exact_atomic_claim` is authoritative; `raw_source_span` and
`pico.original_claim` are provenance and may be fragments. A coordinated
`and` does not assert that one outcome causes the other, so no estrogen
mediation is added to the muscle-gain claim without explicit source wording.

**Decision:** retain exposure/outcome qualifiers in bounded PubMed queries even
when both concepts have linked terms. Remove a leading effect-direction verb
from outcome *search wording* (for example, search `muscle gain` rather than
requiring `lowers muscle gain`); the stored proposition and PICO direction are
unchanged. When the claim names no comparator, exclude a title-level
active-exposure comparison (such as soy versus whey or
animal protein) from judge selection if it addresses only that relative
question. Preserve every such paper, passage, and
`unstated_active_comparator_excluded` reason in Evidence Pack 1.4. Explicit
no-exposure/placebo and within-exposure comparisons, or an actually asserted
comparator, remain eligible. This is a conservative relevance check, not a
medical verdict. For a muscle-gain/growth claim, a generic mention of
`muscle` plus an unrelated biomarker or soreness measurement is not the
claimed endpoint; such records keep a
`specific_outcome_endpoint_absent_excluded` audit reason and cannot fill an
otherwise empty judge subset. A numbered sub-study that explicitly assigns
the exposure arm to women only is not evidence for a men-specific claim merely
because the parent trial includes men elsewhere. The inverse sex mismatch is
handled symmetrically. Such an arm receives an
`exposure_arm_population_mismatch_excluded` reason, while the full paper stays
auditable; unassigned or matching arms are not excluded. New judge and
semantic-validation prompt versions require the actual study contrast to be
named and bar a decisive conclusion based only on an unasserted active
comparator or unmeasured mechanism. Frozen old packs and append-only
judge/verdict rows are never rewritten.

**Reason:** analysis `89c4b08a-c482-41ff-b298-12a90e965684` stored the second
claim as the standalone proposition “Regular soy usage in male body lowers
muscle gain.” but the web card displayed only the raw “lowers muscle gain”
fragment. Its selected soy-versus-whey/animal studies led a judge to argue
against a comparison the user had not asserted. The fix aligns visible claim,
retrieval question, and judge/validator scope without relaxing evidence-use
or production-release gates.

## ADR-037 — Backend-owned source units and assertion-specific numeric checks

**Decision:** retain the existing attributed-statement/conclusion split. New
`judge-input-2.1` adds exact whole-section units to the frozen coherent document
bundles. Models return source-unit IDs and semantic content, not redundant
quotes or protocol metadata. The backend materializes canonical decision 2.1
and validates it against the reconstructed, hash-bound input. Historical
1.0/2.0 artifacts retain their original contracts and hashes; old copied quotes
are never retroactively certified. Existing JSONB columns need no migration.

**Reason:** inspection of the retained smoking/sunscreen runs found rejected
model quotes differing in Unicode whitespace or containing ellipses. Exact
source fidelity is mandatory, but asking a model to retype backend-held text
adds avoidable failure. Correct unit selection still does not prove an
assertion: attribution and conclusion checks remain mandatory.

**Decision:** validation 2.1 uses assertion-local typed quantities, interval-to-
estimate binding and verified RR arithmetic. Backend quotes alone do not add
assertions. Exact user magnitudes remain claim targets; a correct contrast with
the user's number is not a source-attribution error. Definite false statistics
stay fatal; ambiguous assignments are recorded with tokens, candidates,
references and actual conclusion dependency. An unresolved required premise
cannot qualify. Optional unsupported prose requires a new decision and full
revalidation through the existing single revision budget, never silent deletion
or `NUMERIC_UNCERTAIN -> ignore`.

**Reason:** original sunscreen judge 2 correctly restated invasive-melanoma
HR 0.27 and CI 0.08–0.97. The old parser missed `HR,` and `CI,` in its exact
source, classified the confidence level as an unrelated percentage, and
returned uncertainty. This was reproduced before repair. Missing publication
years remain explicit unknown classifications, not alleged medical effects.

**Decision:** keep a two/three-finding default and eight-finding hard maximum;
expanded context/conflict must be explained in the retained justification.
Capture bounded sanitized failed judge content and safe schema field paths in
existing append-only audit JSON. Developer-only replay and live measurement
remain opt-in, time/call bounded, and outside normal-user responses. Preserve
retention and never resurrect missing artifacts. The smoking failed revision's
raw response/error fields were not retained, so its exact schema cause remains
unknown; do not claim it was a missing version or medical reasoning error.

No judge-count, risk, retrieval, production-qualification or environment change
is authorized by this ADR. Final synthetic controls passed, but fresh probes
of both original Packs still lacked eligible conclusions for semantic/provider
reasons. Measurements and remaining Slice 2/3 work are reported separately in
[RELIABILITY_SLICE1_RESULTS.md](RELIABILITY_SLICE1_RESULTS.md).

Additional exact replay found `20 cigarettes daily` equivalent to the source's
`20 cigarettes per day`; this narrowly typed exposure-rate spelling is now
recognized. Explicit confidence levels and integer-valued estimate/CI pairs
are checked separately, including negative tests. A new smoking semantic
response had correct IDs/status and a 685-character reason but failed the
600-character local reason limit. Semantic response/audit reasons now have a
1200-character hard maximum, with a shorter preferred prompt target and
unchanged status/reference/provenance validation. Prompt version is 2.5.
This is an inspected shape repair, not an inference about the unretained
historical failed judge revision. No long response is silently truncated.

## ADR-038 — Statement-to-claim relations and deterministic conclusion qualification

**Decision:** supersede ADR-033/037's holistic semantic conclusion-justification
call for **new** `judge-input/decision/validation-2.2` runs. Retain source-to-
statement attribution, exact backend source units and assertion-local numeric
checks. One bounded label-blind relation batch classifies every eligible finding
against the original claim; `conclusion-qualifier-1.0` qualifies, never flips,
the proposed judge label. Existing aggregation/count/risk/release gates remain.
Historical rows/contracts are neither rewritten nor reinterpreted.

**Reason:** exact retained Slice 1 active requests had six source-supported
findings but two negative holistic statuses whose rationales described evidence
insufficiency compatible with the proposed NEI labels. Scope and evidence strength
were conflated with qualification. Earlier different judge responses are not
controlled identical-input stability evidence. Separating relation classification
from the backend rule removes that status/rationale decision from the LLM.

**Decision:** use strict relation, scope and materiality enums with exact IDs;
preserve conflict and uncertainty; do not treat nonsignificance as contradiction,
association as causation, or a parent trial label as proof of exposure randomization.
Only material compatible direction plus existing design gates can qualify a
decisive proposal. Accurate counterestimates need not match user magnitudes;
backend RR arithmetic blocks false support of an incompatible asserted effect.
Unestablished publication integrity and provider failures are operational
limitations, not scientifically established NEI. Every outcome remains auditable.

**Decision:** persist full typed audits in existing append-only validation JSONB.
Aggregation rechecks hashes, frozen metadata, risk/type and deterministic outputs.
No schema migration, added critic/debate, new retrieval source or environment
edit is needed. New prompt shape explicitly distinguishes S IDs from E unit IDs
and requires an object conclusion; malformed responses are not coerced to votes.

**Decision:** measure configured aliases on paired engineering controls and three
identical-prompt trials, with explicit call/time budgets and no automatic model
selection. Engineer annotations must not be called human-reviewed or clinically
qualified until independent review occurs. Preserve earlier measurements and
failed live runs rather than silently replacing them with favorable repeats.
See [RELIABILITY_SLICE2_RESULTS.md](RELIABILITY_SLICE2_RESULTS.md).

## ADR-039 — Curated coverage and question-appropriate evidence design

**Decision:** retrieve a small reviewed canonical NCI/CDC/WHO/IARC/NIH-NCCIH
manifest through one bounded HTML adapter, not search, a crawler, arbitrary
user URL fetches or judge browsing. Preserve purpose (assessment/synthesis/
guideline/guidance/fact sheet/research/press release/other), publisher, dates,
content version, exact sections and attribution. Unknown update dates remain
unknown; review/document age policies are configurable engineering windows.

**Reason:** the retained smoking run had three parsed judgments and two qualified
assessments, but only one qualified decisive direction. It selected indirect
individual research rather than a published body-of-evidence assessment. An ATBC
parent trial tag also incorrectly conferred smoking-randomization strength on
a secondary observed exposure analysis. Coverage and design are separate from
model protocol survival and must be measured, not repaired by forcing a label.

**Decision:** combined immutable Pack `1.5` includes approved-source provenance,
actual exposure design and direct/contextual/incompatible role hints. At most
two approved direct sources coexist with PubMed; at most two contextual documents
enter free slots, never independently decisive. Summaries are not individual
cohorts: a cited never-smoker study does not restrict the whole summary population.
No source unit is model-copied and all judges receive the same frozen input.
Reports group cited exact sections into one source card. Known summary references
and shared lineage cannot be represented as independent replications.

**Decision:** qualifier `1.1` and policy `1.4` use actual exposure assignment,
purpose and the question category. Harmful-exposure causality can use a direct
current causal assessment or systematic evidence summary without an unethical
randomized harmful exposure trial. Treatment/prevention require relevant actual
randomization/synthesis; diagnostic accuracy needs a reference-standard design;
essential quantitative alignment stays mandatory. Unreviewed convergent observational
causal sufficiency is not enabled. Unknown design stays unknown; MeSH "As Topic"
does not establish the document's own synthesis design.

**Critical constraint:** authority, purpose and study design never assign truth.
The existing source-attribution → statement/claim relation → pure qualification
flow stays. Model-family/count/risk/release/production gates and pre-existing
development provisional rules are unchanged. No environment/model edit or V3
rewrite occurs. New source-body versions and audit runs append, never overwrite.
The exact-heading Text migration preserves prior data; downgrade refuses truncation.

**Measurement:** preserve pilot failures separately from repaired measurements.
Paired controls reuse identical retained PubMed content, disclose manual source-
grounded PICO, expired originals, provider failures, token usage and absent billing
rates. Engineer controls are not a human-reviewed clinical benchmark. Higher label
coverage is not itself accuracy. See [RELIABILITY_SLICE3_RESULTS.md](RELIABILITY_SLICE3_RESULTS.md).

## ADR-040 — Measured development probes, no unsafe adoption

**Decision:** implement opt-in frozen-input V2/minimal-V2/V3 model evaluation,
lean/manual reviewed source selection and non-voting decisive cross-checks outside
the normal pipeline. V3 classifications have no model-written findings, copied
quotes, statistics or verdicts; local provenance/numeric/design checks and existing
pure qualification derive positions. Explicitly synthetic controls are not papers;
engineer labels and policy-derived expected positions are not clinical gold.

**Decision:** retain the existing V2 contract, current evidence selection, judge
models and normal validator strategy. V3 produced false decisive null/scope results;
minimal-V2 retained narrow-dose false support; lean lost reviewed BP-source recall.
Quota interruption and incomplete clean held-out/repeat/validator comparisons
cannot establish a superior model or justify a configuration change. The normal
36–41 model-call traces remain a measured blocker, not a solved performance claim.

**Constraint:** no `.env`, billing/account/key/URL, production minimum, high-risk,
identity/isolation/validator-approval or append-only persistence changes. The
pre-existing single-decisive development rule remains provisional, not production
approval. Historical artifacts are not rewritten or TTL-extended. Private runtime
exports are exclusive/sanitized; new checkpoints preserve received paid responses
even if an experiment aborts. Quota failure stops additional queued paid requests.

**Status:** software verified, bounded engineering measurements documented in
[Slice 4 results](RELIABILITY_SLICE4_RESULTS.md) and
[bake-off results](JUDGE_BAKEOFF_RESULTS.md). Adoption and final full normal-flow/
all-three-judge stability acceptance remain open; do not mark the task complete.

## 2026-10-02: bounded Slice 4 continuation decision

**Choose V2, not V3, for normal development.** Keep current Slice 3 selection
and Ling/Luna/Gemini Lite judge slots. No candidate established superiority on
both development and held-out controls; model aliases are identity-unverified.
Keep `.env`, all keys/URLs and production qualification/count thresholds unchanged.

Batch the two existing semantic targets into one label-blind Gemini Lite request
per judge using configured slot 3. Keep deterministic source/quantity/provenance
checks and the same Python sufficiency qualifier. Exact requests/responses and
hashes are audited and rechecked; a reviewer is not another independent vote.
Production cannot use the development single-request qualification exception.
Disable development semantic judge revisions: only 3/12 saved normal revisions
became usable, while they duplicated 13 attribution checks in a smoking run.
Keep one bounded schema/format retry; no retry-until-agreement loop.

New qualitative prose is constrained and locally checked to omit optional
statistics; essential quantities in genuine numeric claims remain material.
Models violating this format fail closed. This reduces numeric-validation noise,
but is NOT proof that providers always obey the format (some did not).

V3 generic guards prevent reason/relation inconsistency, decisive limited scope,
contextual basis and conflict promotion. They do not repair a wrongly emitted
aligned/decisive classification; a decisive-only checker blocked that fresh
high-dose error. V3 nevertheless qualified 0/3 real smoking judges versus V2's
1/3 on the same frozen Pack, so adoption was rejected and further V3 sweeps
early-stopped. Lean source selection remains rejected for measured recall loss.

The additional hard ceiling was 120 initiated requests, enforced persistently
before transport, including retries and interrupted analyses. All 120 received
HTTP 200; this is transport reliability, NOT semantic accuracy. Paid work stopped.
Normal flow reached 6-7 post-retrieval calls, but final repeatability acceptance
is incomplete: health-test app lifecycles reconciled the live repeated-smoking
run as interrupted. The test is isolated now; the historical run is not repaired
or relabeled. See the continuation results for this self-caused measurement
limitation, all failure denominators and the unchanged release blockers.

## 2026-10-03: full-Pack judge transport and shared-gateway scheduling

Small JSON probes are insufficient for judge readiness. On the original
smoking Pack, Qwen's full response took 46.4 seconds and was cancelled by the
old 45-second attempt limit; DeepSeek-V4-Flash and GLM-4.5-Flash exceeded 60
seconds even after input compaction. A versioned development wire projection
removes duplicate passage text and reference-URL lists from the transmitted
JSON, but retains every complete source unit and the original full snapshot
for audit/validation. Historical prompt versions remain reconstructible.

Use bounded 60-second attempts and 110-second slot totals. Serialize judges
sharing one OpenAI-compatible gateway within a batch; keep separate endpoints
parallel. This is a latency/availability choice, not a relaxation of medical
validation or independence requirements. Configure Paratera Qwen3.5-35B-A3B
and ERNIE-4.5-Turbo-128K around unchanged AIMLAPI GPT Luna. A fresh normal
analysis returned 3/3 structured judge responses, but none passed the strict
material numeric preflight for a submitted 85% effect. Neither provider
identity nor medical verdict quality is established by this smoke test.
