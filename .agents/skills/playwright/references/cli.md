# Playwright CLI Reference

Prefer connected browser tooling. For CLI fallback, use the repository-local
wrapper. From the repository root on Windows:

```powershell
$lensPwcli = (Resolve-Path -LiteralPath '.agents/skills/playwright/scripts/playwright_cli.ps1').Path
function pwcli { & $lensPwcli @args }
pwcli --help
```

With a verified development WSL distribution or Git Bash:

```bash
export PWCLI="$(pwd -P)/.agents/skills/playwright/scripts/playwright_cli.sh"
pwcli() { bash "$PWCLI" "$@"; }
pwcli --help
```

Read `local-setup.md` if a prerequisite is missing. No global installation or
home-directory skill path is required. Keep the absolute wrapper path when changing
to `runtime/playwright/<task>/` for generated artifacts. The `pwcli` examples below
work with the shell function defined above.

## Core

```bash
pwcli open https://example.com
pwcli close
pwcli snapshot
pwcli click e3
pwcli dblclick e7
pwcli type "search terms"
pwcli press Enter
pwcli fill e5 "user@example.com"
pwcli drag e2 e8
pwcli hover e4
pwcli select e9 "option-value"
pwcli upload ./document.pdf
pwcli check e12
pwcli uncheck e12
pwcli eval "document.title"
pwcli eval "el => el.textContent" e5
pwcli dialog-accept
pwcli dialog-accept "confirmation text"
pwcli dialog-dismiss
pwcli resize 1920 1080
```

## Navigation

```bash
pwcli go-back
pwcli go-forward
pwcli reload
```

## Keyboard

```bash
pwcli press Enter
pwcli press ArrowDown
pwcli keydown Shift
pwcli keyup Shift
```

## Mouse

```bash
pwcli mousemove 150 300
pwcli mousedown
pwcli mousedown right
pwcli mouseup
pwcli mouseup right
pwcli mousewheel 0 100
```

## Save as

```bash
pwcli screenshot
pwcli screenshot e5
pwcli pdf
```

## Tabs

```bash
pwcli tab-list
pwcli tab-new
pwcli tab-new https://example.com/page
pwcli tab-close
pwcli tab-close 2
pwcli tab-select 0
```

## DevTools

```bash
pwcli console
pwcli console warning
pwcli network
pwcli run-code "await page.waitForTimeout(1000)"
pwcli tracing-start
pwcli tracing-stop
```

## Sessions

Use a named session to isolate work:

```bash
pwcli --session todo open https://demo.playwright.dev/todomvc
pwcli --session todo snapshot
```

Or set an environment variable once:

```bash
export PLAYWRIGHT_CLI_SESSION=todo
pwcli open https://demo.playwright.dev/todomvc
```
