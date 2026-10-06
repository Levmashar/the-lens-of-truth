# Bounded live validator acceptance — 2026-10-05

The earlier V2.5 tests exercised saved responses without inference charges. This
follow-up made **16 real chat-completion requests**, including a timed-out request,
through the backend's full joint-validator adapter. No short sample prompts,
extraction reruns, judge reruns, retrieval reruns, or new full Lens analyses were
used. Judge quality and validator quality remain separate: all three judges had
already returned usable V2.5 structured responses in the supplied live analysis.

## Latest failure

Analysis `58ea1ccd-1e48-4829-870e-10ea3852eed9` completed with three usable judges
and zero qualified assessments. ERNIE returned empty required evidence ID lists
for two DeepSeek statements and the invalid strength `contextual` for GLM. Its
remaining Qwen assessment was blocked by unresolved source integrity. It also
classified the invasive-melanoma RCT result as a narrower endpoint despite the
submitted endpoint matching.

The RCT DOI `10.1200/JCO.2010.28.7078` had a Crossref **global deadline failure**,
not unknown randomized design: PubMed integrity was checked; the Crossref check
was cancelled. A fresh check through the normal Crossref adapter checked all
24 available DOI records in 8.71 seconds and populated the existing success cache.
The RCT metadata was successfully verified. Original frozen packs and historical
analyses were not rewritten.

Local Crossref total timeout is now 60 seconds instead of 30, within the existing
configuration range. Per-request timeout/retry rules and concurrency three remain
unchanged. Crossref returned `x-concurrency-limit: 3`; increasing parallelism would
have exceeded that limit. The larger bounded budget reduces queue cancellations;
it does not guarantee availability during an upstream outage. Unknown integrity
continues to block qualification.

## Actual paid results

All calls used complete frozen evidence, statements, unit/quantity references and
the existing joint checker instructions, strict JSON Schema and local ID checks.
Historical V2.4 judge responses were explicitly adopted into in-memory V2.5 replay
inputs; stored historical records retain their original contracts. Positions below
are backend-derived, not provider labels.

| Validator / settings | Frozen response | Position / outcome | Seconds |
| --- | --- | --- | ---: |
| Qwen3.8-Flash / thinking off | DeepSeek sunscreen | Supported | 19.910 |
| Qwen3.8-Flash / thinking off | Qwen3.5-Plus vitamin C | Contradicted | 41.691 |
| Qwen3.8-Flash / thinking off | DeepSeek smoking +85% | NEI | 18.515 |
| Qwen3.8-Flash / thinking off | DeepSeek inverse smoking | Contradicted | 26.685 |
| GPT-6 Luna / provider default | DeepSeek sunscreen | Unavailable: rejects a misattributed review limitation | 43.480 |
| GPT-6 Luna / provider default | Qwen3.5-Plus vitamin C | Unavailable: checker deadline | 76.371 |
| GPT-6 Luna / provider default | DeepSeek smoking +85% | NEI | 43.377 |
| GPT-6 Luna / provider default | DeepSeek inverse smoking | Contradicted | 49.890 |
| GPT-6 Luna / low reasoning | GLM sunscreen | Supported | 6.279 |
| GPT-6 Luna / low reasoning | Qwen3.5-Plus vitamin C | NEI: general-population conclusions classified narrower | 10.293 |
| GPT-6 Luna / low reasoning | DeepSeek smoking +85% | NEI | 10.021 |
| GPT-6 Luna / low reasoning | DeepSeek inverse smoking | Contradicted | 17.003 |
| GPT-6 Luna / reasoning disabled | Qwen3.5-Plus vitamin C | Unavailable: missing-material-evidence flag | 10.083 |
| GPT-6 Luna / reasoning disabled | GLM sunscreen | Supported | 7.129 |
| GPT-6 Luna / reasoning disabled | DeepSeek smoking +85% | NEI | 9.644 |
| GPT-6 Luna / reasoning disabled | DeepSeek inverse smoking | Contradicted | 10.075 |

Qwen's four replies had valid schema and references and matched all four engineering
positions. Average checker latency was 26.70 seconds. This is a small live sample,
not proof of repeatability, medical validity or production readiness.

**Known attribution limitation:** the saved DeepSeek sunscreen statement S5 cites
E6 for one review's protective conclusion and E59 for a different review's
non-systematic methodology, then describes them as the same review. Luna correctly
rejected that attribution. Qwen accepted it, as did the saved ERNIE response used
by the earlier offline replay. Qwen's observational-null directions were also
imperfect; the existing deterministic guards excluded those from material
opposition. Passing the expected position is not evidence that every semantic
axis or attribution was correct. No sources or findings were edited to make a
candidate pass.

Luna's default profile failed the existing deadline; low reasoning failed the
vitamin-C position expectation; disabled reasoning flagged missing material
evidence on that saved response. None is adopted. No prompts, scope rules,
thresholds, integrity gates, quantity contracts or public labels were loosened.

## Configuration and verification

Replace ERNIE provisionally with **Paratera Qwen3.8-Flash,
`enable_thinking=false`**. This improves measured schema availability over the
latest ERNIE failures and reproduces the four requested engineering positions.
The known attribution limitation remains an explicit acceptance gap. The checker
is a separate non-voting model call; it shares the Qwen family with Judge 2.

The small provider-settings change adds `VALIDATOR_THINKING_ENABLED` and reuses
the existing verified judge generation-options helper. Unset preserves provider
defaults; unsupported overrides are rejected before calling. Strict schema and
source-ID enforcement are unchanged. No Luna-specific production transport
extension was retained after its trial.

The configured validator's **entire four HTTP JSON bodies** were subsequently
compared to the actual paid request bodies using a local mock transport: all were
identical. Each actual returned answer passed normal validation and V2.5 audit
reconstruction again. These confirmation replays incurred no additional charges.

Active lineup:

- Extraction: Paratera DeepSeek-V4.1-Flash
- Judge 1: Paratera DeepSeek-V4.1-Flash
- Judge 2: Paratera Qwen3.5-Plus, provisional
- Judge 3: Paratera GLM-4.7
- Semantic validator: Paratera Qwen3.8-Flash, thinking disabled, provisional

Paid reply usage reported 388,038 prompt tokens and 21,698 completion tokens.
The timed-out request returned no usage; actual provider billing is not available
from these replies and no dollar total is claimed. The 16-request ceiling was
reached and no further inference requests were made.

Private raw requests/replies/audits, without authorization headers or credentials:
`%TEMP%/lens_live_acceptance_20261005.json`. Crossref check results:
`%TEMP%/lens_crossref_live_checks_20261005.json`. The AIMLAPI key is retained only
in the ignored local `.env`; temporary credential copies were removed.

Relevant offline checks: 85 tests covering validator transport, V2.5 positions
and retrieval integrity; final provider-settings tests 11 passed; Ruff and mypy
passed. Backend rebuilt and restarted; `/healthz` returned HTTP 200. The running
container reports Qwen3.8-Flash with enable_thinking=false, the unchanged three
judges/extractor, and Crossref total timeout 60. All four exact-request/live-answer
audit replays also passed inside the rebuilt container after restart, with no
network inference calls. No paid end-to-end rerun was performed, so the originally
supplied historical analysis remains unchanged.

Provider references: [OpenAI GPT-6 Luna request capabilities](https://developers.openai.com/api/docs/models/gpt-6-luna),
[AIMLAPI Luna chat request specification](https://api.aimlapi.com/docs-json?model=openai%2Fgpt-6-luna&endpoint=openai%2Fchat-completions).
