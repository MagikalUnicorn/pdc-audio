# PDC-Audio

PDC-Audio recovers and decodes the `SEMC PDC-AUDIO` object embedded in video
recordings made by Sony Japanese MOVA handsets, including the SO505i. The
decoded output is mono, 8 kHz, signed 16-bit PCM.

The utility can also create a new playable ASF containing the original MJPEG
video packets, decoded PCM audio, and the original proprietary audio descriptor.
The source recording is never modified in place.

## Status

The decoder is the audited floating-point v3 core with the v3.3 ASF-preserving
workflow. It is a strong implementation of the error-free PDC half-rate /
PSI-CELP equations, but it is not claimed to be bit-exact with the unavailable
historical fixed-point reference implementation.

## Repository layout

```text
src/pdc_audio/   importable decoder and ASF tooling
scripts/         PowerShell conversion entry points
tests/           media-independent core tests and optional ASF integration test
docs/            historical audits, validation, and integration notes
```

The three supplied standards/reference PDFs are deliberately not kept in Git.
They live in the sibling `pdc-audio-media/standards` directory, alongside any
private source recordings or generated media used for local validation.

## Installation

PDC-Audio requires Python 3.11 or later and NumPy. FFmpeg is needed only for ASF
or MP4 output; decoding to WAV does not require it.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

On MSYS2, activate `.venv/bin/activate` instead. An editable install provides
the `pdc-audio` command and keeps the bundled audited codebook tables available.

For the MinGW64 environment used by this repository, the equivalent setup is:

```bash
pacman -S --needed mingw-w64-x86_64-python-numpy \
    mingw-w64-x86_64-python-pip mingw-w64-x86_64-python-setuptools \
    mingw-w64-x86_64-python-build mingw-w64-x86_64-ffmpeg
python -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --no-build-isolation --no-deps -e .
```

## Use

The simplest Windows workflow creates a decoded ASF beside the source file:

```powershell
.\scripts\Convert-SonySo505iPdcAudio.ps1 `
    -InputAsf "C:\Videos\Phone Pictures 130.asf"
```

Choose outputs explicitly when required:

```powershell
pdc-audio "C:\Videos\Phone Pictures 130.asf" `
    --asf "C:\Videos\Phone Pictures 130 restored.asf" `
    --wav "C:\Videos\Phone Pictures 130 decoded.wav" `
    --json "C:\Videos\Phone Pictures 130 parameters.json"
```

The module form works without relying on the console-script name:

```powershell
python -m pdc_audio "C:\Videos\Phone Pictures 130.asf" `
    --wav "C:\Videos\Phone Pictures 130 decoded.wav"
```

Useful options include `--float-npy`, `--mp4`, `--no-normalize`, `--force`,
and `--ffmpeg PATH`. ASF output verifies the copied video packets, decoded PCM,
and preserved binary descriptor by default; `--no-verify` disables that pass.

Lower-level installed commands are also available:

- `pdc-audio-extract` extracts the proprietary object from an ASF.
- `pdc-audio-decode-records` decodes an extracted sequence of 24-byte records.
- `pdc-audio-preserve` copies the descriptor into an already-remuxed ASF.

## Test and build

The core suite does not require private handset recordings:

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -m pip wheel . --no-deps --wheel-dir dist
```

Run the end-to-end ASF test when an original SO505i recording and FFmpeg are
available:

```powershell
python .\tests\asf_integration.py `
    "C:\Videos\Phone Pictures 130.asf"
```

## Imported development history

The four supplied archives were imported as distinct, byte-for-byte snapshots
before the repository was reorganised. They can be inspected with these tags:

- `snapshot-v2`
- `snapshot-v3-core-audit`
- `snapshot-v3.2-final-audit`
- `snapshot-v3.3-final-asf`

See [the core audit](docs/CORE_AUDIT.md),
[the final audit](docs/FINAL_CORE_AUDIT.md),
[v3.3 validation](docs/VALIDATION.md), and
[the FFmpeg integration assessment](docs/FFMPEG_INTEGRATION.md) for technical
detail and known limitations.
