# Developing PDC-Audio

See the [README](../README.md#requirements-and-build) for installation, build,
PowerShell, and conversion instructions. This guide covers the additional
checks and privacy rules used while changing the project.

## Local data and privacy

Keep standards, source recordings, and generated output in the sibling
`pdc-audio-media` directory. Never commit recordings, extracted pictures,
handset metadata, absolute home paths, media-derived logs, or generated output.
The helpers read external samples without copying them into the repository.

## Routine verification

From the repository root, build the package and run all available tests:

```console
python scripts/build.py
python scripts/test.py
```

The build helper creates `.venv` when needed, installs the package in editable
mode, and writes a wheel under `dist`. The test helper runs media-independent
tests followed by every ASF in the sibling sample directory. Both generated
directories are ignored by Git.

To run only media-independent tests:

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

## Conversion diagnostics

Use the canonical `scripts/convert_mova_pdc_audio.py` helper documented in the
[README](../README.md#run). Run it with `--help` to inspect all diagnostic
outputs and options. The input is never overwritten, and generated output must
remain under the external media directory.
