#!/usr/bin/env bash
# Repository-local adaptation: never download or install packages automatically.
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd -P)"
if ! command -v node >/dev/null 2>&1; then
  echo "Missing prerequisite: Node.js in this shell. No installation was attempted." >&2
  exit 1
fi

cli=""
for candidate in \
  "$repo_root/frontend/node_modules/.bin/playwright-cli" \
  "$repo_root/runtime/browser-tools/node_modules/.bin/playwright-cli" \
  "$repo_root/node_modules/.bin/playwright-cli"; do
  if [[ -f "$candidate" ]]; then
    cli="$candidate"
    break
  fi
done
if [[ -z "$cli" ]]; then
  echo "Missing prerequisite: repository-local @playwright/cli. Prefer connected browser tooling. See .agents/skills/playwright/references/local-setup.md. No installation was attempted." >&2
  exit 1
fi

has_session_flag="false"
for arg in "$@"; do
  case "$arg" in
    --session|--session=*)
      has_session_flag="true"
      break
      ;;
  esac
done

cmd=("$cli")
if [[ "${has_session_flag}" != "true" && -n "${PLAYWRIGHT_CLI_SESSION:-}" ]]; then
  cmd+=(--session "${PLAYWRIGHT_CLI_SESSION}")
fi
cmd+=("$@")

exec "${cmd[@]}"
