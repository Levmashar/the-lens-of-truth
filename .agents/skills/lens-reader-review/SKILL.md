---
name: lens-reader-review
description: Review Lens result screens and user-facing explanations for clarity, evidence fidelity, visible uncertainty, and usable evidence controls. Use for result-reading and explanation reviews.
---

# Lens reader review

Review the requested screen using the existing vanilla TypeScript/Vite stack,
not React. Read the repository instructions and relevant current report contracts.

- Lead with a meaningful answer, not counts of assertions or pipeline stages.
- Keep essential uncertainty and incomplete-check warnings visible before disclosure.
- Clearly distinguish what a study reported from a medical conclusion.
- Never improve readability by changing evidence, labels, or qualifications.
- Use only approved findings for factual summaries, with traceable references to
  the owning finding, assertion, source unit, or quantity where applicable.
- Put evidence details behind clear controls and diagnostics in the advanced view.
  Keep the essential answer, uncertainty, and operational limitations visible.
- Check completed, scientifically inconclusive, and operationally incomplete states.
  An inconclusive scientific assessment must remain distinct from an unavailable check.
- Inspect desktop/mobile screenshots and keyboard behavior before declaring done.
  Check focus visibility/order, disclosure controls, evidence links, clipping, and
  readable warnings. Prefer existing browser tooling; use the local Playwright skill
  only when needed. If tooling is unavailable, report the unverified checks explicitly.
- Do not claim user comprehension testing unless people actually participated.

Compare each displayed factual statement with its approved findings and exact
references. Identify missing context or ambiguous copy without inventing a medical
conclusion. Preserve the distinction between exact quotations and editorial summaries.

Report concrete issues with file/line or screen references, the observed state,
and a bounded correction. Separate implementation checks, actual browser checks,
and any human research. A review request does not itself authorize changing medical
logic, making paid analysis calls, or redesigning unrelated screens.
