# Building, running, and testing PDC-Audio

The repository helpers are ordinary Python scripts. They use repository-relative
and sibling-media paths and work from Windows, MSYS2, or another Python 3.11+
environment.

## Local data and privacy

Keep standards, source recordings, and generated output in the sibling
`pdc-audio-media` directory. Never commit recordings, extracted pictures,
handset metadata, absolute home paths, media-derived logs, or generated output.
The helpers read external samples without copying them into the repository.

## Build

From the repository root:

```console
python scripts/build.py
```

The helper creates `.venv` when needed, installs PDC-Audio in editable mode,
and writes a wheel under `dist`. Both directories are ignored by Git.

On a new MSYS2 MinGW64 installation, install the prerequisites first:

```console
pacman -S --needed mingw-w64-x86_64-python-numpy \
    mingw-w64-x86_64-python-pip mingw-w64-x86_64-python-setuptools \
    mingw-w64-x86_64-python-build mingw-w64-x86_64-ffmpeg
```

## Test

Run media-independent tests and every ASF under the sibling sample directory:

```console
python scripts/test.py
```

Run only media-independent tests:

```console
python scripts/test.py --unit-only
```

An alternative external directory or FFmpeg executable can be supplied without
storing either path in the repository:

```console
python scripts/test.py --sample-dir /private/samples \
    --ffmpeg /tools/ffmpeg
```

Each integration runs in a temporary directory. It checks the frame CRCs,
duration, copied MJPEG packets, decoded PCM packets, and exact preservation of
the `SEMC PDC-AUDIO` object. It never alters the source recording.

## Run

Decode one recording and create a verified ASF:

```console
python scripts/convert_sony_so505i_pdc_audio.py \
    ../pdc-audio-media/samples/sample.asf
```

With no explicit output, the helper writes a generically named ASF under
`pdc-audio-media/outputs`. Outputs can instead be selected explicitly:

```console
python scripts/convert_sony_so505i_pdc_audio.py \
    ../pdc-audio-media/samples/sample.asf \
    --asf ../pdc-audio-media/outputs/decoded.asf \
    --wav ../pdc-audio-media/outputs/decoded.wav
```

The input is never overwritten. Use `--help` with any helper to see all options.
The compatibility entry point `scripts/decode_sony_pdc_audio.py` accepts the
same interface.
