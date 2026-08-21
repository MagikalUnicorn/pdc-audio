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

begin {
    $ErrorActionPreference = 'Stop'

    function Resolve-Executable {
        [CmdletBinding()]
        param(
            [Parameter(Mandatory)]
            [string[]] $Candidates,

            [Parameter(Mandatory)]
            [string] $Purpose
        )

        foreach ($candidate in $Candidates) {
            if ([string]::IsNullOrWhiteSpace($candidate)) {
                continue
            }

            $command = Get-Command -Name $candidate -ErrorAction SilentlyContinue
            if ($null -ne $command) {
                if ($command.Source) { return $command.Source }
                return $command.Definition
            }

            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return (Resolve-Path -LiteralPath $candidate).Path
            }
        }

        throw "Unable to find $Purpose. Supply its full path explicitly."
    }

    function Get-FullOutputPath {
        [CmdletBinding()]
        param(
            [Parameter(Mandatory)]
            [string] $Path
        )

        return [System.IO.Path]::GetFullPath($Path)
    }

    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $decoder = Join-Path $scriptDirectory 'decode_sony_asf.py'
    if (-not (Test-Path -LiteralPath $decoder -PathType Leaf)) {
        throw "Decoder script not found: $decoder"
    }

    $pythonCommand = if ($Python) {
        Resolve-Executable -Candidates @($Python) -Purpose 'Python 3'
    }
    else {
        Resolve-Executable -Candidates @('py', 'python', 'python3') -Purpose 'Python 3'
    }

    # Python resolves FFmpeg only when an ASF or MP4 output is requested. This keeps
    # WAV-only decoding usable on systems where FFmpeg is not installed.
    $ffmpegCommand = if ($Ffmpeg) { $Ffmpeg } else { 'ffmpeg' }
}

process {
    $resolvedInput = (Resolve-Path -LiteralPath $InputAsf).Path

    # With no explicit output, perform the main archival operation requested by this
    # package: create a new ASF beside the source, leaving the source untouched.
    if (-not $OutputAsf -and -not $OutputWav -and -not $ParameterJson -and
        -not $FloatNpy -and -not $OutputMp4) {
        $directory = Split-Path -Parent $resolvedInput
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedInput)
        $OutputAsf = Join-Path $directory "$baseName - decoded PDC.asf"
    }

    $arguments = @($decoder, $resolvedInput, '--ffmpeg', $ffmpegCommand)

    if ($OutputAsf) {
        $resolvedOutputAsf = Get-FullOutputPath -Path $OutputAsf
        if ($resolvedOutputAsf -eq $resolvedInput) {
            throw 'OutputAsf must not overwrite the original Sony ASF.'
        }
        $arguments += @('--asf', $resolvedOutputAsf)
    }

    if ($OutputWav) {
        $arguments += @('--wav', (Get-FullOutputPath -Path $OutputWav))
    }

    if ($ParameterJson) {
        $arguments += @('--json', (Get-FullOutputPath -Path $ParameterJson))
    }

    if ($FloatNpy) {
        $arguments += @('--float-npy', (Get-FullOutputPath -Path $FloatNpy))
    }

    if ($OutputMp4) {
        $arguments += @('--mp4', (Get-FullOutputPath -Path $OutputMp4))
    }

    if ($NoNormalize) {
        $arguments += '--no-normalize'
    }

    if ($SkipVerification) {
        $arguments += '--no-verify'
    }

    if ($Force) {
        $arguments += '--force'
    }

    & $pythonCommand @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Sony SO505i PDC-AUDIO conversion failed with exit code $LASTEXITCODE."
    }

    if ($OutputAsf) {
        Get-Item -LiteralPath $resolvedOutputAsf
    }
}
