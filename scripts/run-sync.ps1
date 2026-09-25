param(
    [ValidateSet('validate','sync')][string]$Command='sync',
    [string]$Csv='data/products.csv',
    [switch]$Apply,
    [string]$Log
)
$ErrorActionPreference='Stop'
$labRoot=Split-Path -Parent $PSScriptRoot
Push-Location $labRoot
$labOldPythonPath=$env:PYTHONPATH
$labOldUtf8=$env:PYTHONUTF8
try {
    $labPython=Join-Path $labRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $labPython)) {
        $labPythonCommand=Get-Command python -ErrorAction SilentlyContinue
        if ($labPythonCommand) { $labPython=$labPythonCommand.Source }
        else { throw 'Install Python 3.10+ and create .venv; see docs/WINDOWS.md.' }
    }
    if (-not (Test-Path -LiteralPath $labPython)) { throw 'Zainstaluj Python 3.10+ i utwórz .venv; patrz docs/WINDOWS.md.' }
    $env:PYTHONPATH=Join-Path $labRoot 'src'
    $env:PYTHONUTF8='1'
    $labArguments=@('-m','woo_sync',$Command,$Csv)
    if ($Apply) { $labArguments+='--apply' }
    if ($Log) { $labArguments+=@('--log',$Log) }
    & $labPython @labArguments
    $labExit=$LASTEXITCODE
} finally {
    $env:PYTHONPATH=$labOldPythonPath
    $env:PYTHONUTF8=$labOldUtf8
    Pop-Location
}
exit $labExit
