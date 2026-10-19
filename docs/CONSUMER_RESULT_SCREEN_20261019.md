# Consumer claim result screen — 2026-10-19

Deployed locally at <http://localhost:5173/analysis/cc3007b2-3c9c-40d8-af50-ea0bdf92d941>.
This is a presentation change to vanilla TypeScript/Vite claim reports. No new
analysis, paid model call, backend medical change or report rewrite was made.
The separate document reader and historical source/report contracts are preserved.

## First-screen answer

**Not established by research**

Does using your phone while lying on your side worsen myopia?

> Related research exists, but it does not establish this specific claim. The
> studies did not separately test whether using a phone while lying on your side
> affects how quickly short-sightedness gets worse.

Not established doesn't mean disproven.

The visible qualification note reads: “Development preview. Not qualified for
medical use. Some assessments could not be verified; the result uses only those
that passed.” The full saved notice and assessment details remain expandable.

Trace: the unchanged report has `not_enough_evidence`, reason `scope_too_narrow`,
two qualified assessments and one excluded assessment. Related research is
reading-guide `retrieval.state=related_only`. The second sentence simplifies
approved `findings[0]`, referencing E2.U1 and E22.U1. The original finding and
complete source passages remain available. A guide is used only when its verdict
run ID and report semantic hash match. Editorial sentence references are retained
on the rendered summary in `data-report-references`.

## Presentation rules

| Internal verdict (unchanged) | Consumer label |
| --- | --- |
| supported | Supported by research |
| contradicted | Research contradicts this |
| not_enough_evidence | Not established by research |
| unable_to_verify_reliably | We couldn't complete the check |

The verdict leads, followed by the claim question and one explanation. Ordinary
single-claim results omit the repeated process title, claim count and Completed
badge. Native evidence/source disclosures start closed. Citations open their owning
source and focus it; the complete exact quotations and original links are retained.
Check details and backend-authorized diagnostics are separate disclosures, and
Copy all diagnostics still copies the complete API data available to the screen.

No explanation changes a verdict. Conflict retains its saved explanation instead
of being described as absent research. Search incompleteness has a visible warning;
Unable explicitly describes an unfinished check rather than a scientific conclusion.
Generic decisive summaries may display a complete approved, referenced finding;
numeric, provisional and comparison-qualified summaries retain their saved wording.
No raw model prose is promoted to a factual summary. Historical reports without a
reading guide retain their saved explanation. Question grammar preserves negation,
qualifiers and the complete checked wording, also available in About this check.

## Verification

- **136 frontend tests passed** across 10 files; TypeScript/Vite production build passed.
- Frontend container rebuilt and restarted; backend and model configuration untouched.
- Real retained phone/myopia and smoking Supported screens inspected in Chrome
  through the repository-local Playwright CLI. No connected browser was available;
  existing local CLI and Chrome were used without installing packages.
- Contradicted, Unable and long-claim screens tested through browser-only API
  fixtures, visibly labelled **Synthetic UI fixture — not a real check**. These
  screenshots do not represent new medical analyses.
- Desktop 1440×1000; mobile 390×844; additional phone test at 320×800 and 200% text
  scaling. No horizontal overflow. This was text scaling, not a claim of browser
  zoom or assistive-technology certification.
- Keyboard Enter/Tab tested on evidence, source citations and source disclosures;
  citation focus has a 3px outline. Empty headings/bullets: zero.
- Stable-state text contrast checked: light theme minimum 5.55:1; dark theme minimum
  8.73:1 among the main answer, question, qualification note and evidence control.
  Reduced motion disables the answer animation. Status is expressed in words.
- Clipboard write/read verified in the real browser (44,444 characters of available
  diagnostics), without printing raw replies. The freshly read API had no live
  debug events after the earlier backend restart; existing response-preservation
  tests still pass. This UI change does not manufacture unavailable trace data.
- Source navigation opened the correct PubMed URL in a new tab. PubMed returned
  HTTP 403 in this browser environment; external page availability is a remaining
  testing limitation, not a replacement of the stored source identity.
- No human comprehension study was conducted.

## Screenshots

| State | Desktop | Mobile |
| --- | --- | --- |
| Retained phone/myopia NEI | [Desktop](assets/consumer-results-20261019/phone-desktop.png) | [Mobile](assets/consumer-results-20261019/phone-mobile.png) |
| Retained smoking Supported | [Desktop](assets/consumer-results-20261019/supported-desktop.png) | [Mobile](assets/consumer-results-20261019/supported-mobile.png) |
| Synthetic Contradicted | [Desktop](assets/consumer-results-20261019/contradicted-desktop.png) | [Mobile](assets/consumer-results-20261019/contradicted-mobile.png) |
| Synthetic Unable | [Desktop](assets/consumer-results-20261019/unable-desktop.png) | [Mobile](assets/consumer-results-20261019/unable-mobile.png) |

Additional [long claim](assets/consumer-results-20261019/long-mobile.png) and
[dark theme at 320px](assets/consumer-results-20261019/phone-dark-mobile.png).
