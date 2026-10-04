# The Lens of Truth — Reliability Reset: Codex Implementation Brief

## Objective

Improve the rate of **correct, evidence-grounded answers**, without increasing unsupported conclusions. Do not optimize for making the sunscreen example say “Contradicted.” Do not remove safeguards, lower judge-count thresholds, or turn every failure into “Not Enough Evidence.”

This is a repair of the existing implementation, not a rewrite. Keep FastAPI, PostgreSQL, immutable provenance, the existing adapters and orchestration, and vanilla HTML/CSS/TypeScript/Vite.

The full roadmap below is context. **Implement only Slice 1 in the first run.** Report its measured results before implementing the source-coverage and policy changes in Slice 2. Do not spend another run only producing an architecture plan.

## Read the current state, not obsolete phase descriptions

Inspect applicable AGENTS.md files, git status, current implementation, and:

- docs/PROJECT_CONTEXT.md
- docs/DECISIONS.md — particularly ADR-033 through ADR-036
- docs/ARCHITECTURE.md
- docs/API_SPEC.md
- docs/TODO.md
- Relevant sections of the original implementation report, treating superseded recommendations as historical.

If the uploaded diagnostic files are available, read `Pasted text(1).txt` and `Pasted text (2).txt` too.

The following are ALREADY implemented. Do not propose rebuilding them:

- Schema-2.0 attributed judge statements and separate conclusion justification.
- Coherent, frozen judge-input-2.0 document sections, with E IDs and hashes.
- One semantic revision per judge, with append-only parent/child lineage.
- Policy 1.3's provisional, one-fully-validated-judge result for standard-risk development only.
- Neutral retrieved-source display for development Unable results.
- Source-grounded standalone claims and endpoint/directness ranking.

The current documented local route is AIMLAPI/OpenAI-compatible, not active Miri. Read effective configuration without revealing keys. Do not assume requested aliases establish underlying model identity. Do not change provider configuration or release qualification as part of this repair.

## Evidence motivating the repair

### Smoking run

Analysis ID: `75b56567-dd52-4e92-806d-ea2471bf6dc7`

Claim: `Smoking causes lung cancer`

Observed in the supplied diagnostic export:

- Zero accepted assessments.
- Judge 1: one statement supported; another `unable_to_assess`; `statement_validator_unavailable`.
- Judge 2: semantic revision failed `schema_violation`.
- Judge 3: six of eight statements supported, two not established; two `QUOTE_NOT_IN_FROZEN_PASSAGE` issues and `INVALID_CONCLUSION_PREMISE`.
- Displayed neutral sources include smoking-intensity research but also genetic mediation, methylation-clock, latency, and lung-cancer stigma material.

Neutral displayed sources are not proof of what was actually selected or sent to judges. Trace source membership explicitly before diagnosing selection.

### Sunscreen run

Analysis ID: `1e58f2e8-f1cc-4e05-94af-1e008c22307d`

Claim: `Frequent sunscreen use causes invasive melanoma.`

Observed:

- Zero accepted assessments.
- Judge 2 has two statements marked `supported_by_sources`, a `justified` conclusion, but overall `partially_validated` with `NUMERIC_UNCERTAIN` as its only listed issue.
- Judges 1 and 3 have exact-quotation failures; some other statements were correctly attributed.
- PMID 21135266 is present in the displayed retrieved evidence.

These exports establish the failing stage, NOT whether each particular quotation or numerical rejection was correct. Inspect actual frozen payloads and error details before modifying behavior.

### Existing semantic evaluation

The project records 14 cases with 13 expected checks matched and 8 mismatched, without provider/format failures. These are 21 checks within 14 cases, not 13/14 accuracy. Inspect the evaluation manifest and annotation quality. Do not describe these results as qualification of a medical validator.

## Principles for this repair

1. Machine-verifiable provenance is a hard boundary; an unbenchmarked semantic heuristic is not a truth oracle.
2. A parser limitation is different from an observed false statistic.
3. Unknown scope is different from mismatched scope.
4. A failed optional explanation detail is different from a failed premise required by a conclusion.
5. Retrieving documents and then excluding every one is different from finding no literature.
6. The number of models agreeing is not the number of independent studies supporting a claim.
7. Model-originated prose must remain grounded, but do not require a model to retype source text already held by the application.
8. Public-release qualification and the scientific assessment remain separate. Preserve both; never forge qualification.

---

# Slice 1 — Reproducible failures, backend-owned citations, material numeric validation

## 1. Capture and classify the failures

Create a development-only replay/export utility using existing persistence conventions.

For the two analysis IDs, capture exact referenced artifacts, if retained:

- normalized claim, risk class, scope, and original wording;
- query plan, candidate counts and selection/exclusion reasons;
- frozen Evidence Pack and exact judge-input snapshot;
- original and active revised judge decisions;
- every validation input/result;
- the exact number tokens, measures, source units, and comparison that led to NUMERIC_UNCERTAIN;
- actual model schema response and safe validation errors for the failed revision;
- aggregation exclusions and report metadata;
- effective prompt, policy, adapter, model-alias, and configuration versions.

Keep sanitized developer replay files in an ignored local directory. Never include secrets. Respect existing retention and do not recover deleted user data. If an artifact expired, report that and reconstruct a clearly labeled synthetic fixture, never pretend it is the original run.

Produce a compact rejection ledger:

`run -> judge -> required finding -> failure -> hard defect / parser uncertainty / semantic disagreement / provider failure -> affected conclusion`

For quote failures, display the proposed quote, exact referenced source text, and first divergence in the developer replay only. Determine whether the difference is substantive, punctuation, whitespace, a noncontiguous quotation, or a wrong reference. Do not automatically forgive any category.

## 2. Stop asking models to reproduce exact quotations

Add backend-created citation units to the frozen judge input. A unit is an exact, reasonably sized source span with:

- stable unit ID within the versioned input;
- original E passage ID;
- source/document content version and hash;
- start/end offsets in the stored passage;
- exact text;
- section and document context.

Keep coherent methods/results/conclusion context. Unit segmentation must not break decimals, confidence intervals, or necessary negations. Larger paragraph units are acceptable when safer. Multiple units can support one statement.

Conceptual input:

```json
{
  "source_units": [
    {
      "unit_id": "E8.U2",
      "evidence_id": "E8",
      "text": "Exact backend-owned source text.",
      "start": 0,
      "end": 32
    }
  ]
}
```

Conceptual model output:

```json
{
  "statement_id": "S1",
  "text": "A concise claim about what the source reported.",
  "source_unit_ids": ["E8.U2"]
}
```

The backend materializes quotations from these references; the model does not retype the quote or supply trusted offsets/hashes.

Unknown unit IDs, units outside the frozen judge input, and corrupted hashes still fail. Correct ID selection does NOT prove a paraphrase is supported: preserve semantic statement-attribution and conclusion checks.

Do not “solve” quotation errors with fuzzy string acceptance. The structural fix is to eliminate redundant quote copying.

Version the judge/input/validation contracts. Preserve historical v1/v2 records and pack hashes. Reuse existing persistence where possible; add migrations only when necessary. Old free-text quotations must not be retroactively certified under the new contract.

## 3. Make numeric validation assertion-specific and materiality-aware

Inspect the current sunscreen NUMERIC_UNCERTAIN failure before changing rules.

Separate these cases:

- A number appears only in a backend-materialized quotation: exact source fidelity is already checked.
- The judge asserts a numerical finding: verify it against that statement's sources.
- The judge computes a numerical transformation: verify the calculation and quantity type.
- The user asserts an exact magnitude: the answer must address that magnitude at matching scope.
- The submitted claim is qualitative: an optional numerical restatement is not automatically essential to its conclusion.

Never compare every number in an abstract with every number in an explanation.

Keep measure/endpoint/comparator/timepoint binding. OR, RR, and HR are not interchangeable. A confidence level, interval endpoint, sample count, publication year, p-value, and effect estimate are not the same quantity. Ambiguous assignments must remain explicit.

A definite false numerical assertion is invalid. An unsupported or unresolved *material* assertion prevents reliance on that premise. A parser's failure to classify a number is not automatically proof that the source contradicts the claim.

Do not implement `NUMERIC_UNCERTAIN -> ignore`. Instead:

1. Identify which statement and exact quantity the issue concerns.
2. Determine whether the proposed conclusion relies on that quantity, using the actual conclusion dependency set and source scope—not only a model's self-reported materiality flag.
3. Repair an objectively incorrect parser classification where reproducible.
4. Otherwise omit an optional unsupported numerical restatement from the publishable explanation and reassess the remaining conclusion against the unchanged complete evidence, using the existing single revision budget if semantics change.
5. If the quantity is essential, retain uncertainty or inability. Do not launder it through a vague paraphrase.

Retain all original findings, rejected details, counterevidence, and audit lineage. Never drop an inconvenient source to manufacture agreement.

Examples for regression tests:

- No number in user claim; no numerical assertion in judge prose; source contains several confidence intervals. Source numerals alone do not become an asserted judge statistic.
- Source reports RR 0.85; judge says 85% risk reduction. Reject the conversion.
- User claims 80%; source says 15%; judge accurately explains that difference. Attribution may pass; disagreement with user magnitude is not an attribution error.
- Judge attributes study A's value to study B. Reject.
- Claim requires a precise dose or effect magnitude; that number is unresolved. Do not emit a decisive precise answer.
- Optional quoted publication year absent from parser coverage must not masquerade as an unsupported medical effect.

## 4. Reduce contract-only failure surfaces

Read actual schema_violation details. Do not guess that every failure is a model reasoning error.

Backend metadata—schema version, pack hash, invocation ID, provider identity—should normally be attached by the caller, not generated by the model. Models must still identify the statement/source units necessary for semantic mapping.

Use native structured-output enforcement only where the configured endpoint actually supports it. Keep Pydantic validation, refusals, truncation handling, bounded retries, and clear failure categories. Do not assume a third-party endpoint honors an OpenAI-shaped response_format merely because it accepts the parameter.

Do not relabel substantive model output or fill missing medical premises heuristically.

## 5. Validate Slice 1 with frozen examples

Add deterministic tests for the above contracts. Then use opt-in, bounded real-model tests to measure whether valid source uses are accepted and fabricated/overstated uses are rejected.

Keep a modest default target of two or three material attributed findings per judge, with necessary counterevidence and limitations. This is not permission to omit material conflict. Keep a hard maximum and log why an expanded response was needed.

First test the exact two frozen cases and a balanced set of positive/negative attribution and numerical fixtures. Do not require a predetermined sunscreen verdict.

Report separately:

- transport/schema success;
- reference/provenance success;
- attribution correctness against reviewed expectations;
- false rejection of correct statements;
- false acceptance of incorrect statements;
- conclusion eligibility;
- total calls, latency, and estimated usage if available.

Do not reduce the existing production or high-risk judge thresholds. Do not add another development threshold exception. Policy 1.3 already has a development single-assessment path; zero eligible conclusions cannot be fixed by decreasing the threshold again.

**Stop after Slice 1, its tests, measured replay, and documentation.** The next slices are specified below so the direction is clear, not authorization to implement them simultaneously.

---

# Slice 2 — Evidence coverage and claim-appropriate sufficiency

## 6. Add authoritative evidence summaries alongside PubMed

The product answers public-health questions, not only questions about one paper. Add a small generic curated-source adapter using an explicit server-managed manifest of authoritative public-health/evidence-summary pages. Begin with a few relevant NCI/CDC/WHO/IARC pages and broaden by topic; do not create a condition-to-verdict lookup table.

For each source, preserve publisher, document purpose, publication/update date where supplied, retrieval time, URL, permitted text, hash, sections, and references. Respect source terms. This must not become arbitrary client-supplied URL fetching.

Institutional origin alone does not make a statement true. Distinguish evidence assessment, guideline recommendation, patient information, press release, and mechanistic commentary. Verify exact claim fit, currency, authority, and potentially conflicting evidence.

No DOI or clinical-trial publication type is expected for many such documents. Do not mark them incomplete merely because they are not journal articles.

Retrieve both authoritative summaries and relevant research. Deduplicate shared studies/assessments so several documents repeating one source do not masquerade as independent evidence. Freeze the combined selection before independent judging; no judge gets separate browsing.

## 7. Inspect retrieval recall rather than adding another topical penalty

Log actual ESearch parameters: query, sort, retmax, total count, returned IDs. Do not assume current defaults from source recency.

Use complementary broad and focused queries and a bounded candidate budget. PubMed ESearch documents `sort=relevance`; verify usage against the actual adapter. Search wording must not force the desired answer.

Track relevant reference sources through:

candidate retrieval -> normalized document -> exclusion or ranking -> selected document -> judge-visible sections

Do not infer selection from the report's neutral source list.

Use exact primary reference documents as evaluation sentinels, not hardcoded production boosts. A general smoking claim should be able to retrieve a genuine authoritative causal assessment rather than relying on papers about stigma or covariate-adjusted methylation clocks.

## 8. Replace scientifically inappropriate hard sufficiency rules

Review ADR-034's blanket requirement that a causal/prevention/treatment conclusion cite a trial or synthesis.

Causal evidence for harmful exposures can include authoritative causal assessments and coherent epidemiological/mechanistic evidence synthesis. Do not require a randomized harmful-exposure trial. Conversely, the word “review” or the presence of an RCT does not by itself establish the claim.

Implement a documented question-specific evidence policy rather than a publication-type whitelist pretending to determine truth. Maintain strict treatment/dose/personal-medical safeguards. Validate evidence sufficiency on reviewed examples before changing the default policy; version any change.

Distinguish unsupported generalizations from legitimate bounded conclusions. Missing exact frequency, dose, or comparator in an ordinary public claim is not automatically a universal quantifier.

Preserve the literal claim. Display the scope actually assessed. Ask for clarification or report bounded findings when different plausible interpretations lead to materially different answers. Never silently invent a comparator.

For unknown-comparator claims, related active-comparator trials may remain contextual evidence, clearly labeled with their actual contrast. They cannot automatically establish an absolute benefit or harm. Do not eliminate useful literature solely because the user did not state every PICO field.

Keep hard exclusion for compromised provenance, retraction as decisive evidence, and genuinely incompatible evidence use. Lexical relevance/directness heuristics should not get irreversible scientific vetoes without validation.

---

# Slice 3 — Qualify the semantic checker and reduce unnecessary model work

## 9. Move evaluation into the development loop now

Create approximately 30 source-anchored examples, with separate development and held-out sets. Include:

- established supported claims and their false inverses;
- properly insufficient claims;
- numerical misquotes;
- correct numerical contrasts;
- association-to-causation overclaims;
- evidence that genuinely opposes a claim;
- compatible versus mismatched population/comparator scope;
- correct and incorrect quotations/reference selections;
- provider failure cases, kept separate from scientific judgments.

Have expected medical conclusions reviewed before calling this an accuracy benchmark. Engineer-authored synthetic entailment tests remain useful but are not clinical validation.

Use the same frozen source inputs for model comparisons. Include an evidence oracle condition: reviewed claims plus reviewed source packs, bypassing retrieval only in evaluation. If this still fails, source retrieval is not the immediate problem.

Compare:

A. Current multi-judge + validator pipeline.
B. Same models/evidence with backend-owned citation references and materiality-aware numeric handling.
C. A simple, high-quality evidence-grounded assessment plus one bounded independent review, as an evaluation baseline—not a replacement automatically approved for production.

A reviewer that sees a proposed answer is not a second blind independent judge. Never count it that way or bypass the production judge threshold.

Choose the semantic checker based on measured attribution/inference performance, not because it belongs to a different brand or is cheapest. Expose validator inability and reviewer disagreement separately from evidence insufficiency.

Where performance supports it, batch attribution checks into one bounded call with statement-local results, followed by a separate conclusion check; allow a cached validated statement only for identical source/input/schema/model versions. Batch failure remains explicit. Never add recursive reviewers of reviewers.

Measure false rejection, false acceptance, decisive-answer accuracy/coverage, abstention causes, citation fidelity, and cost/latency. Do not optimize merely for fewer Unable labels. Repeat a small subset to measure stochastic instability.

---

# Slice 4 — Useful evidence reporting and one effective current contract

## 10. Make the report answer the actual question

Retain four verdict labels and visible release qualification. Add no numeric truth probability.

Report the assessed scope and the strongest validated findings, not only procedural text such as “two models agreed.” When a conclusion remains unavailable, preserve separately labeled source quotations only when provenance is intact; do not imply those quotations received semantic approval if they did not.

For sunscreen, a report should be capable of discussing the applicable daily-versus-discretionary trial result and the limits/heterogeneity of observational evidence. It must not turn a null statistical result into proof of universal safety, or equate a broad possible harm claim with “every product always harms every user.” The label must follow the reviewed policy and supplied evidence.

For a general smoking causal claim, a retrieved, applicable authoritative causal assessment should count as relevant evidence. The system should not need to rediscover established public-health conclusions from unrelated recent abstracts.

## 11. Consolidate current guidance

Keep historical ADRs, but create or refresh a concise effective contract showing what is currently implemented and which earlier rules are superseded. Do not leave present-tense, contradictory instructions across Phase 1.0, 1.1, 1.2, and 2.0 descriptions.

Update PROJECT_CONTEXT, TODO, API_SPEC, ARCHITECTURE, and DECISIONS only for actual changes. Do not equate another checked implementation box with proven medical quality.

## Verification for every slice

Run the repository's real backend/static checks, migrations/schema checks when changed, and frontend tests/build only when affected. Preserve append-only history, privacy/retention, secrets, and unrelated uncommitted changes. Live model tests are opt-in and bounded; use current configuration without silently changing paid models or credentials.

A successful delivery reports confirmed causes, changed contracts, software test results, separate semantic evaluation results, newly remaining failure reasons, and production qualification. No claim of correctness may rest only on green mocked tests.

## Primary references to inspect, not hardcode as answers

- NCI, Tobacco: `https://www.cancer.gov/about-cancer/causes-prevention/risk/tobacco`
- IARC Monographs general information: `https://monographs.iarc.who.int/home/iarc-monographs-general-information/`
- Sunscreen trial follow-up, PMID 21135266: `https://pubmed.ncbi.nlm.nih.gov/21135266/`
- Cochrane Handbook chapter 15, interpretation and applicability: `https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-15`
- NCBI E-utilities parameters: `https://www.ncbi.nlm.nih.gov/books/NBK25499/`
- OpenAI Structured Outputs, for supported official endpoints and documented limitations: `https://developers.openai.com/api/docs/guides/structured-outputs`
- ALCE citation evaluation: `https://aclanthology.org/2023.emnlp-main.398/`

These are source and engineering references, not evidence of clinical validation of The Lens of Truth.
