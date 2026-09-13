param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$BookDownloadArgs
)

$env:PYTHONPATH = Join-Path $PSScriptRoot "src"
$env:PYTHONUTF8 = "1"
$env:UV_CACHE_DIR = Join-Path $PSScriptRoot ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = Join-Path $PSScriptRoot ".uv-python"

$projectPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $projectPython) {
    & $projectPython -m bookdownload @BookDownloadArgs
} else {
    & uv run --no-project --python 3.12 python -m bookdownload @BookDownloadArgs
}
exit $LASTEXITCODE
