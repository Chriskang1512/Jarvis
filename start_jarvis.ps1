param(
    [switch]$Once,
    [switch]$CheckEncoding
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $projectRoot

$utf8 = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8
[Console]::OutputEncoding = $utf8
$global:OutputEncoding = $utf8

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if ($CheckEncoding) {
    python -c "import sys; print(f'stdin={sys.stdin.encoding} stdout={sys.stdout.encoding}'); print('\ucd5c\uadfc \uba54\uc77c \uc54c\ub824\uc918'); print('\uc624\ub298 \uc77c\uc815 \uc54c\ub824\uc918')"
    exit $LASTEXITCODE
}

if ($Once) {
    $env:JARVIS_VOICE_ONCE = "true"
} else {
    Remove-Item Env:JARVIS_VOICE_ONCE -ErrorAction SilentlyContinue
}

python voice_main.py
exit $LASTEXITCODE
