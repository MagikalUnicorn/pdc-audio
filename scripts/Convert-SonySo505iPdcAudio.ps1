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

    function Resolve-Python {
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

            $resolved = $null
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                $resolved = (Resolve-Path -LiteralPath $candidate).Path
            }
            else {
                $command = Get-Command -Name $candidate -ErrorAction SilentlyContinue
                if ($null -ne $command) {
                    $resolved = if ($command.Source) { $command.Source } else { $command.Definition }
                }
            }

            if ($resolved) {
                try {
                    & $resolved -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' *> $null
                    if ($LASTEXITCODE -eq 0) {
                        return $resolved
                    }
                }
                catch {
                    continue
                }
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
    $repositoryRoot = Split-Path -Parent $scriptDirectory
    $sourceRoot = Join-Path $repositoryRoot 'src'
    $msysRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $repositoryRoot))
    $decoderPackage = Join-Path $sourceRoot 'pdc_audio\__main__.py'
    if (-not (Test-Path -LiteralPath $decoderPackage -PathType Leaf)) {
        throw "Decoder package not found: $decoderPackage"
    }

    $pythonCommand = if ($Python) {
        Resolve-Python -Candidates @($Python) -Purpose 'Python 3.11 or later'
    }
    else {
        Resolve-Python -Candidates @(
            (Join-Path $repositoryRoot '.venv\Scripts\python.exe'),
            (Join-Path $repositoryRoot '.venv\bin\python.exe'),
            'py',
            'python',
            'python3',
            (Join-Path $msysRoot 'mingw64\bin\python.exe')
        ) -Purpose 'Python 3.11 or later'
    }

    # Python resolves FFmpeg only when an ASF or MP4 output is requested. This keeps
    # WAV-only decoding usable on systems where FFmpeg is not installed.
    $ffmpegCommand = if ($Ffmpeg) {
        $Ffmpeg
    }
    else {
        $msysFfmpeg = Join-Path $msysRoot 'mingw64\bin\ffmpeg.exe'
        if (Get-Command -Name 'ffmpeg' -ErrorAction SilentlyContinue) {
            'ffmpeg'
        }
        elseif (Test-Path -LiteralPath $msysFfmpeg -PathType Leaf) {
            $msysFfmpeg
        }
        else {
            'ffmpeg'
        }
    }
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

    $arguments = @('-m', 'pdc_audio', $resolvedInput, '--ffmpeg', $ffmpegCommand)

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

    $previousPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
    $sourcePath = (Resolve-Path -LiteralPath $sourceRoot).Path
    $env:PYTHONPATH = if ($previousPythonPath) {
        $sourcePath + [System.IO.Path]::PathSeparator + $previousPythonPath
    }
    else {
        $sourcePath
    }
    try {
        & $pythonCommand @arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Sony SO505i PDC-AUDIO conversion failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        [Environment]::SetEnvironmentVariable('PYTHONPATH', $previousPythonPath, 'Process')
    }

    if ($OutputAsf) {
        Get-Item -LiteralPath $resolvedOutputAsf
    }
}
