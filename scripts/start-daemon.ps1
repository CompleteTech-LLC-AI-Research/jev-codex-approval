$ErrorActionPreference = "Stop"
if (-not $env:JEV_APPROVAL_CONFIG) { throw "Set JEV_APPROVAL_CONFIG to an absolute TOML path." }
if (-not $env:JEV_APPROVAL_TOKEN) { throw "Set a random JEV_APPROVAL_TOKEN of at least 32 characters." }
$Root = Split-Path -Parent $PSScriptRoot
python -I (Join-Path $Root "scripts/launcher.py") serve --config $env:JEV_APPROVAL_CONFIG
exit $LASTEXITCODE
