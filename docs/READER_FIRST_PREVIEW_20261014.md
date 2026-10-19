# Reader-first result preview — approval checkpoint

The preview is implemented and visually inspected. **The live result screen and
general report-generation pipeline have not been replaced.** This checkpoint
requires user approval before integration, as explicitly requested.

## Open the preview

Running locally: http://127.0.0.1:5174/reader-preview.html?fixture=incomplete

Use the **Preview state** selector to switch between Completed, Unresolved and
Incomplete. Direct links use `?fixture=completed`, `?fixture=inconclusive`, and
`?fixture=incomplete`. The theme switch also works.

To restart the preview from `frontend/`:

```powershell
npm run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

This is a separate Vite HTML entrypoint. It is not imported by `src/main.ts`, does
not replace `/analysis/`, and is excluded from the default production build.
Its entrypoint also refuses non-development execution. No React or application
dependency was added. No backend services were rebuilt/restarted for this task.

## Fixtures and provenance

| Preview state | Origin and scope |
|---|---|
| Completed | Explicitly synthetic scoped scenario using the saved, completed A1/A2 study-description checks from a897813c. It does not imply the full paragraph completed. |
| Scientifically unresolved | Explicitly synthetic scoped scenario using completed A1/A2/A4/A6 checks in the historical 42f64be8 report capture. A4/A6 remain NEI. This is not a new execution. |
| Operationally incomplete | Actual retained a897813c report, captured through the normal read API on 2026-10-14. All statuses are unchanged. |

The historical report's current API returns 404; the preview uses the existing
2026-10-08 local report capture as a labeled historical scenario, without restoring
an expired analysis, renewing retention, or claiming a fresh run.

The full original report remains available in the advanced view for each scenario,
including records outside its selected reading scope. No synthetic successful
outcomes were inserted into it. The incomplete original has 11 records: four
completed, three unavailable and four background, with no pending items.
A3/A4/A5 remain `unable_to_verify_reliably`; A6 remains saved Supported with an
explicit correctness-review flag. A10's broad supported association restatement
is not used to imply completion of the more specific failed checks.

Read-only API re-fetch at the end compared **exactly equal** to the initial
incomplete report capture. Saved report snapshot hash:
`924d3d93aac3bb02502b90c1a43103e135b226b049497414aaefc5b833c5d30b`.
Fixture file SHA-256:
`47f70cfbfa7c8b82c25b478740cd449b59d8620ad2df00c868cc059e118a7395`.
All fixture capture sources/hashes are in
`frontend/src/preview/fixtures/provenance.json`.

## Exact first-screen wording

All three screens begin with **Checking what the paper reported**, offer
**See the evidence** and **Read the study**, and display
**Development preview · Not approved for public release.**
No overall verdict/percentage is assigned. Counts, IDs, model names and methods
stay out of the ordinary first-screen text.

### Completed scoped scenario — synthetic

**The paper matches the study description.**

The study we found used UK Biobank data and included 472,672 people. That confirms
the paragraph’s description of a study involving more than 470,000 participants
and examining sunscreen use and skin cancer.

This preview focuses on the study’s identity, size and subject; it does not cover
the paragraph’s claims about higher cancer rates or the “292% increase.” Matching
a paper’s description is different from showing that sunscreen causes cancer.
Read the original study below, or open the evidence to see the exact passages
behind these checks.

Fixture notice: “Synthetic fixture. Uses the saved, completed study-description
checks only. This is not a completed execution of the full paragraph.”

### Scientifically unresolved scoped scenario — synthetic

**The paper was found. Its headline risk claim remains unresolved.**

The study’s size and subject match the paragraph, but the completed check did not
establish the claimed “292% increase” as an increase in someone’s chance of
developing invasive melanoma.

The numeric result’s meaning remains unresolved, and the saved checks also
disagree about the claim that other risk factors were accounted for. Those are
unresolved findings, rather than an interrupted check, for the details shown in
this scenario. This checks how accurately the paragraph describes the paper.
It does not establish that sunscreen causes cancer, and the large participant
count cannot resolve the disputed interpretation. Open the evidence to see
where the explanation becomes uncertain.

Fixture notice: “Synthetic fixture. Assembled from completed checks in the saved
8 October report. The full original report remains unchanged in the advanced
view; this is not a new execution.”

### Operationally incomplete — actual saved report

**We found the study, but couldn’t finish checking its main claims.**

The paragraph refers to a UK Biobank paper involving more than 470,000 people.
We confirmed its size and subject, but this run did not finish verifying the
claims about higher skin-cancer rates, including the “292% increase.”

The claim about other risk factors also needs review. This is an incomplete
check, not a conclusion that those claims are true or false. It should not be
read as confirmation that sunscreen causes cancer. You can read the study and
see the evidence already available, alongside the checks that remain unfinished.

Fixture notice: “Saved report from 13 October 2026. No new analysis was run.
All original outcomes are preserved.”

## Reading and audit layers

The second layer uses reader questions: study identity, higher rates, the 292%
figure and other risk factors, as applicable to each scenario. Each has a short
answer, a saved-state-derived status, a specific explanation and an exact owned
source excerpt. Relevant passages from unfinished checks are labeled source
context, not completed verification. Full passages are pooled by unit and open
through a working local disclosure; endpoints and their underlying assertion
records remain separate and traceable.

The A6 row says **Saved result: Matches the paper · Review flagged** even while
collapsed. Opening it explains the joint-adjustment concern and shows the exact
methods sentence. The saved outcome is not manually overridden.

The third layer retains the existing report renderer and development diagnostics.
All IDs, original wording, counts, full frozen passages and raw replies remain
accessible. Reader wording has its own reference ledger. **Copy all diagnostics**
uses the existing control for the retained report; the historical capture has a
copy control for all its saved diagnostics. Raw replies are not rendered in the
ordinary view. The complete saved reports are not modified.

`frontend/src/preview/model.ts` defines typed sentences, reference fields,
assertion/unit ownership, questions, quote purpose, scope and fixture origin.
The preview guard rejects untraced text, invented excerpts, foreign source units,
and promotion of unavailable items into approved facts/completed assessments.
`fixtures.ts` contains manually reviewed fixture copy; it is not a generic
classifier, an AI summarizer, or wording hardcoded into future live sunscreen runs.

## Screenshots inspected

Native Windows Chrome, desktop 1440×1000 and mobile-width 390×1000. Full-page
screenshots are provided; they are not physical-device or human research results.

| State | Desktop | Mobile |
|---|---|---|
| Completed | [Screenshot](assets/reader-preview-20261014/completed-desktop.png) | [Screenshot](assets/reader-preview-20261014/completed-mobile.png) |
| Scientifically unresolved | [Screenshot](assets/reader-preview-20261014/inconclusive-desktop.png) | [Screenshot](assets/reader-preview-20261014/inconclusive-mobile.png) |
| Operationally incomplete | [Screenshot](assets/reader-preview-20261014/incomplete-desktop.png) | [Screenshot](assets/reader-preview-20261014/incomplete-mobile.png) |
| Incomplete, dark mode | [Screenshot](assets/reader-preview-20261014/incomplete-dark-desktop.png) | [Screenshot](assets/reader-preview-20261014/incomplete-dark-mobile.png) |
| Evidence questions open | [Screenshot](assets/reader-preview-20261014/evidence-desktop.png) | [Screenshot](assets/reader-preview-20261014/evidence-mobile.png) |

## Verification and limitations

- Full frontend suite: **117 tests passed**, including 15 preview checks.
- TypeScript and production Vite build pass. Normal live bundle names remain
  `index-DMdErCu0.js` / `index-CK7HzMHC.css`; no fixture/raw-response preview content
  entered that bundle.
- All three states passed desktop/mobile layout, real Tab/Enter/Space disclosure
  navigation and focus checks. Focused question summaries have a visible 3px ring.
- All three passed 200% **text-size** zoom with a 320px viewport, without horizontal
  overflow. This tests text enlargement/reflow, not a physical mobile device or
  Chrome's browser-chrome zoom menu. The initial header overflow was fixed in
  preview-only CSS. Screenshots/metrics remain in ignored `runtime/playwright/reader-preview/`.
- Checked reader text contrast: minimum **5.55:1** in light mode; incomplete dark
  mode minimum **7.90:1**. Status is also written in words, not color alone.
- No visible empty headings/bullets in checked states. Native disclosures reveal
  their content; full-source controls open the correct passage and move focus.
- The selector was exercised in Chrome and updates the fixture URL. Light/dark
  themes were inspected. The original report and diagnostics remain on demand.
- Reduced-motion emulation verified root scrolling becomes `auto` and the theme
  control's transition duration becomes `0s`.
- Actual Chrome clipboard copy/read verified **363,640 characters**, all 11
  assertions and complete raw replies. Denied clipboard behavior is unit-tested.
- The source action opened the expected canonical PubMed URL in a new tab, but
  this browser environment received **HTTP 403** from that external site. Online
  PMC inspection also later encountered a browser challenge. External article
  rendering is therefore **not claimed successful**; the local frozen excerpts
  and full-passage controls work. No challenge/security warning was bypassed.
- No connected browser tooling was exposed, so the reviewed official Playwright
  CLI `0.1.22` was installed only in ignored `runtime/browser-tools`, with npm
  cache there and lifecycle scripts disabled. Existing native Chrome was used;
  no browser download, global npm/Python install or global configuration change.
- No backend application code changed, so no new backend unit-test run is claimed.
  The normal read API performed its existing frozen audit and exact-report check.
- **Zero paid model calls. No people participated in comprehension testing.**

The 20-second understanding goal is a design target, not a measured human outcome.
The visible answer states what was established, what remains unresolved or
unfinished, and that this concerns reporting of a paper rather than a general
medical conclusion.

## Separate backend findings and proposed next step

See [the two correctness findings and bounded proposed fixes](READER_PREVIEW_BACKEND_FINDINGS_20261014.md).
Missing reporting attributions explain the incomplete high-risk items. A6's
accepted joint-adjustment inference lacks direct support in the frozen material.
These findings remain visible rather than being repaired through editorial copy.

After approval, design a generic versioned reader-view projection from approved
report fields and explicit statuses, retain historical reconstruction and the
existing advanced renderer, then connect the approved layout to the live route.
Do not reuse the fixture strings as a classifier or add a summary model.
Address validator coverage and adjustment evidence in separate evaluated changes;
do not rewrite the saved report or lower quorum to make the preview look successful.
