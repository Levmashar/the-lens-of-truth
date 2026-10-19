---
name: "playwright"
description: "Use when the task requires automating a real browser from the terminal (navigation, form filling, snapshots, screenshots, data extraction, UI-flow debugging) via `playwright-cli` or the bundled wrapper script."
---


# Playwright CLI Skill

Prefer existing connected browser tooling when it can complete the task. Otherwise
drive a real browser from the terminal using the repository-local wrapper and
an already installed repository-local `playwright-cli`.
Treat this skill as CLI-first automation. Do not pivot to `@playwright/test` unless the user explicitly asks for test files.

## Prerequisite check (required)

Inventory connected browsers first. For terminal fallback, verify Node.js and
the repository-local CLI. On Windows, use PowerShell:

```powershell
Get-Command node,npm,npx -ErrorAction SilentlyContinue
& .\.agents\skills\playwright\scripts\playwright_cli.ps1 --help
```

The wrappers do not use `npx` to auto-download packages. Missing Node.js, CLI,
browser executable, or usable browser connection must be reported. Do not install
global npm/Python packages or change execution policy. Read
`references/local-setup.md` before setting up a missing local prerequisite.
Successful `--help` alone does not establish browser functionality.

## Skill path (set once)

From the repository root in PowerShell:

```powershell
$lensPwcli = (Resolve-Path -LiteralPath '.agents/skills/playwright/scripts/playwright_cli.ps1').Path
& $lensPwcli --help
```

Use `& $lensPwcli` for the commands below on Windows. With a verified development
WSL distribution or Git Bash, from the repository root:

```bash
export PWCLI="$(pwd -P)/.agents/skills/playwright/scripts/playwright_cli.sh"
pwcli() { bash "$PWCLI" "$@"; }
```

Use `pwcli` for the Bash examples below. Keep the path absolute before changing
working directories; the wrappers locate dependencies relative to themselves.

## Quick start

Use the wrapper script:

```bash
pwcli open https://playwright.dev --headed
pwcli snapshot
pwcli click e15
pwcli type "Playwright"
pwcli press Enter
pwcli screenshot
```

Do not use a global installation for this repository.

## Core workflow

1. Open the page.
2. Snapshot to get stable element refs.
3. Interact using refs from the latest snapshot.
4. Re-snapshot after navigation or significant DOM changes.
5. Capture artifacts (screenshot, pdf, traces) when useful.

Minimal loop:

```bash
pwcli open https://example.com
pwcli snapshot
pwcli click e3
pwcli snapshot
```

## When to snapshot again

Snapshot again after:

- navigation
- clicking elements that change the UI substantially
- opening/closing modals or menus
- tab switches

Refs can go stale. When a command fails due to a missing ref, snapshot again.

## Recommended patterns

### Form fill and submit

```bash
pwcli open https://example.com/form
pwcli snapshot
pwcli fill e1 "user@example.com"
pwcli fill e2 "password123"
pwcli click e3
pwcli snapshot
```

### Debug a UI flow with traces

```bash
pwcli open https://example.com --headed
pwcli tracing-start
# ...interactions...
pwcli tracing-stop
```

### Multi-tab work

```bash
pwcli tab-new https://example.com
pwcli tab-list
pwcli tab-select 0
pwcli snapshot
```

## Wrapper script

The wrappers resolve an existing CLI in `frontend/node_modules/.bin`,
`runtime/browser-tools/node_modules/.bin`, or root `node_modules/.bin` in that
order. They preserve arguments, session overrides, and the CLI exit code:

```bash
pwcli --help
```

They do not install anything or fall back to home-directory skill paths.

## References

Open only what you need:

- CLI command reference: `references/cli.md`
- Practical workflows and troubleshooting: `references/workflows.md`
- Windows/WSL prerequisites and local tooling: `references/local-setup.md`

## Guardrails

- Always snapshot before referencing element ids like `e12`.
- Re-snapshot when refs seem stale.
- Prefer explicit commands over `eval` and `run-code` unless needed.
- When you do not have a fresh snapshot, use placeholder refs like `eX` and say why; do not bypass refs with `run-code`.
- Use `--headed` when a visual check will help.
- Capture artifacts in ignored `runtime/playwright/<task>/`, preserving source
  files and credentials. Set the absolute wrapper path before changing directory.
- Inspect desktop/mobile screenshots and actual keyboard behavior for UI review;
  report unavailable checks without claiming browser testing succeeded.
- Default to CLI commands and workflows, not Playwright test specs.
