[CmdletBinding()]
param(
    [Parameter(Mandatory, Position = 0)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string] $InputAsf,

    [string] $OutputAsf,
    [string] $OutputWav,
    [string] $ParameterJson,
    [string] $FloatNpy,
    [string] $OutputMp4,
    [switch] $NoNormalize,
    [switch] $SkipVerification,
    [switch] $Force,
    [string] $Python,
    [string] $Ffmpeg
)

$ErrorActionPreference = 'Stop'
$converter = Join-Path $PSScriptRoot 'Convert-SonySo505iPdcAudio.ps1'
$forward = @{
    InputAsf = $InputAsf
}
foreach ($name in @(
    'OutputAsf', 'OutputWav', 'ParameterJson', 'FloatNpy', 'OutputMp4',
    'Python', 'Ffmpeg'
)) {
    $value = Get-Variable -Name $name -ValueOnly
    if ($value) {
        $forward[$name] = $value
    }
}
if ($NoNormalize) { $forward['NoNormalize'] = $true }
if ($SkipVerification) { $forward['SkipVerification'] = $true }
if ($Force) { $forward['Force'] = $true }

& $converter @forward
