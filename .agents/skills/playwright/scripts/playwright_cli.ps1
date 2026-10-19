# Repository-local Windows adaptation of the upstream Bash wrapper.
# Does not install packages, access npm, or change global configuration.
$ErrorActionPreference = 'Stop'
$lensRepoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..\..'))
$cliCandidates = @(
    (Join-Path $lensRepoRoot 'frontend\node_modules\.bin\playwright-cli.cmd'),
    (Join-Path $lensRepoRoot 'runtime\browser-tools\node_modules\.bin\playwright-cli.cmd'),
    (Join-Path $lensRepoRoot 'node_modules\.bin\playwright-cli.cmd')
)

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    [Console]::Error.WriteLine('Missing prerequisite: Node.js is not on PATH. No installation was attempted.')
    exit 1
}
$cliPath = $cliCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
if (-not $cliPath) {
    [Console]::Error.WriteLine('Missing prerequisite: repository-local @playwright/cli. Prefer a connected browser tool. See .agents/skills/playwright/references/local-setup.md. No download or installation was attempted.')
    exit 1
}

$cliArguments = @($args)
$hasSession = @($cliArguments | Where-Object { $_ -eq '--session' -or $_ -like '--session=*' }).Count -gt 0
if (-not $hasSession -and $env:PLAYWRIGHT_CLI_SESSION) {
    $cliArguments = @('--session', $env:PLAYWRIGHT_CLI_SESSION) + $cliArguments
}

& $cliPath @cliArguments
exit $LASTEXITCODE
