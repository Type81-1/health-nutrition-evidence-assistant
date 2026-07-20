param(
    [string]$PythonPath = "",
    [int]$Port = 8000
)

$projectRoot = Split-Path -Parent $PSScriptRoot

if (-not $PythonPath) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw "Python was not found. Activate an environment or pass -PythonPath."
    }
    $PythonPath = $pythonCommand.Source
}

if (-not (Test-Path $PythonPath)) {
    throw "Python executable was not found: $PythonPath"
}

Set-Location $projectRoot
& $PythonPath -m uvicorn app.main:app --host 127.0.0.1 --port $Port
