# Repository instructions

Read the applicable instructions and current `docs/PROJECT_CONTEXT.md`,
`docs/ARCHITECTURE.md`, `docs/TODO.md`, and `docs/DECISIONS.md` before project work.
The web frontend uses vanilla TypeScript and Vite; keep that stack.

Presentation changes must preserve evidence, canonical public labels, qualifications,
structured quantity references, audit provenance, and production gates. Changes to
medical logic or provider/model configuration require a task that authorizes them.
Use approved, traceable findings for factual summaries; distinguish reporting
fidelity from medical conclusions and scientific uncertainty from operational failure.
Preserve existing local work. Never disclose `.env` contents or credentials.

## Repository-local skills

Skills live only in `.agents/skills/`. Read the selected `SKILL.md` when using it:

- `$frontend-design`: intentional visual design and UI implementation.
- `$web-design-guidelines`: accessibility and web interface review; pass files/patterns.
- `$playwright`: real browser interaction, screenshots, and keyboard checks. Prefer
  available connected browser tooling; otherwise use its repository-local wrapper.
- `$lens-reader-review`: review Lens results and user-facing explanations.

Keep detailed workflows in the skills. Source commits, file hashes, notices, and
local adaptations are recorded in `.agents/skills/upstream-lock.json`.
Use Windows PowerShell by default. Use WSL only after verifying a usable development
distribution; Docker Desktop's internal distribution is not a development shell.
Do not install skills into home directories, change global Codex configuration, or
install global npm/Python tools. Report missing prerequisites. Browser testing is
complete only when the intended pages, screenshots, and interactions were inspected;
jsdom/unit tests alone do not establish visual or keyboard correctness.
