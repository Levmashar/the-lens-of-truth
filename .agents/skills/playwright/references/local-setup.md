# Repository-local browser tooling

Read the repository `AGENTS.md` and inventory existing connected browser tools first.
Use an available tool capable of the intended screenshot and keyboard checks before
adding dependencies. Do not use a home-directory skill or change global Codex config.

## Windows PowerShell

From the repository root:

```powershell
Get-Command node,npm,npx -ErrorAction SilentlyContinue
$lensPwcli = (Resolve-Path -LiteralPath '.agents/skills/playwright/scripts/playwright_cli.ps1').Path
& $lensPwcli --help
```

The wrapper resolves `playwright-cli.cmd` in these repository-relative directories:

1. `frontend/node_modules/.bin/`
2. `runtime/browser-tools/node_modules/.bin/`
3. `node_modules/.bin/`

It never invokes `npx`, downloads dependencies, or changes execution policy. It
fails clearly when Node.js or a local CLI is absent. Use the normal `&` invocation;
if execution policy blocks scripts, report the error instead of bypassing policy.

If no existing browser tool works and a later browser task needs the CLI, inspect
the selected published `@playwright/cli` version, its entry point, scripts, dependencies,
and license first. Install only that reviewed version under `runtime/browser-tools`
using npm's local `--prefix` option with `--no-save --package-lock=false --ignore-scripts`.
Keep npm's cache under `runtime/browser-tools/npm-cache` using `--cache`. Record the
actual package version; do not use `npm install -g` or unreviewed `npx --yes` downloads.
No package installation is required merely to load this skill.

Check the reviewed CLI's `--help` for supported browser/channel/config flags; use an
existing Chrome or Edge executable if supported. Do not assume that finding a browser
file or cached Chromium proves it launches. If a separate browser download is needed,
report it and keep any authorized download under `runtime/browser-tools/browsers`
via `PLAYWRIGHT_BROWSERS_PATH`, without modifying global settings.

## WSL or Git Bash

`wsl --list --verbose` must show a usable development distribution. Docker Desktop's
internal distribution is not one. Windows Node/npm presence does not prove a WSL
Node/npm toolchain works. Verify the tools inside the selected shell; do not install
system/global packages as part of this skill.

From the repository root in a verified shell:

```bash
command -v node
export PWCLI="$(pwd -P)/.agents/skills/playwright/scripts/playwright_cli.sh"
pwcli() { bash "$PWCLI" "$@"; }
pwcli --help
```

The Bash wrapper uses the corresponding repository-local `.bin/playwright-cli`.
Do not mix Windows-installed dependencies with WSL Linux dependencies blindly.
If those prerequisites are unavailable, use native PowerShell or report the limitation.

## Artifacts and verification

Define the absolute wrapper path before changing directory. Put screenshots, traces,
and snapshots under ignored `runtime/playwright/<task>/`. Prefer explicit snapshot,
navigation, resize, and keyboard commands from `cli.md`. Review desktop and mobile
screenshots, actual focus behavior, and requested states before reporting completion.
Never enter secrets into a test page or submit paid analyses just to test styling
without task authorization. `--help` is only a CLI check, not a browser test.

## Setup inspection: 2026-10-14

- Windows Node.js `v24.16.0` and npm `11.13.0` are available; `npx` is on PATH.
- Connected browser inventory was empty.
- No repository-local `@playwright/cli` or PATH `playwright-cli` was found.
- Chrome and Edge executable files and a Chromium 1228 cache were found. Launch
  compatibility was not tested; no browser automation or screenshots were performed.
- WSL listed only `docker-desktop`; no development distribution was verified.

These observations describe setup time, not permanent prerequisites. Recheck before use.
