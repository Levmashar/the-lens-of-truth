> Scope changed during execution: only claim numbers divisible by 3 were requested. See the [completed selected results](CLAIM_CHECK_DIVISIBLE_BY_3_RESULTS_20261006.md). This file is an earlier partial snapshot.

# Forty full frontend-path claim checks ? 2026-10-06

Each claim was submitted once through the same HTTP endpoints/body as the frontend (`client=web`, `lang=auto`), followed through extraction, normalization, retrieval, selection, judging, source/semantic checks, qualification, aggregation and report serving whenever those stages could complete. Existing retries/deadlines were retained. Failed or incomplete stages are recorded; no forced verdict or fabricated report is supplied. Sanity expectations are engineering expectations supplied by the user, not a clinical benchmark.

Frozen V2.5 architecture, V2.4 quantity references, query-plan 1.4 and position 1.4; no code, prompt or model changes. All Paratera: DeepSeek-V4.1-Flash extraction/J1, Qwen3.5-Plus J2, GLM-4.7 J3, Qwen3.8-Flash validator (thinking disabled).

Completed cases: 3/40. Reported match count: 2/3. A match is only a label comparison.

| # | Claim | Actual final result | Qualified | Expectation match | Individual report |
|---|---|---|---|---|---|
| 1 | Cigarette smoking causes lung cancer. | Supported | 2/3 | Yes | [01](CLAIM_CHECK_40_20261006/reports/01.md) |
| 2 | High blood pressure increases the risk of stroke. | Supported | 3/3 | Yes | [02](CLAIM_CHECK_40_20261006/reports/02.md) |
| 3 | Persistent high-risk HPV infection can cause cervical cancer. | Not Enough Evidence | 3/3 | No | [03](CLAIM_CHECK_40_20261006/reports/03.md) |
