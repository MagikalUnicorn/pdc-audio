[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$InputAsf,

    [Parameter(Mandatory)]
    [string]$OutputWav,

    [string]$OutputMp4,

    [string]$ParameterJson,

    [string]$FloatNpy,

    [switch]$NoNormalize,

    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$decoder = Join-Path $scriptDirectory "decode_sony_asf.py"

$arguments = @(
    $decoder,
    $InputAsf,
    $OutputWav
)

if ($OutputMp4) {
    $arguments += @("--mp4", $OutputMp4)
}

if ($ParameterJson) {
    $arguments += @("--json", $ParameterJson)
}

if ($FloatNpy) {
    $arguments += @("--float-npy", $FloatNpy)
}

if ($NoNormalize) {
    $arguments += "--no-normalize"
}

& $Python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "The Sony PDC-AUDIO decoder exited with code $LASTEXITCODE."
}
