# PDC-Audio

PDC-Audio recovers and decodes the `SEMC PDC-AUDIO` object embedded in supported
NTT DoCoMo MOVA video recordings. Decoded audio is mono, 8 kHz, signed 16-bit
PCM.

The utility can also create a new playable ASF containing the original MJPEG
video packets, decoded PCM audio, and the original proprietary descriptor. It
never modifies the source recording in place.

## Status

The decoder is the audited floating-point v3 core with the v3.3 ASF-preserving
workflow. It is a strong implementation of the error-free PDC half-rate /
PSI-CELP equations, but it is not claimed to be bit-exact with the unavailable
historical fixed-point reference implementation.

The command-line interface is model-neutral and does not require or assume an
SO505i filename. It accepts any MOVA ASF carrying the validated `SEMC PDC-AUDIO`
descriptor, 16-byte object header, and 24-byte record layout. Active records are
accepted by CRC rather than an SO505i-specific trailer whitelist. The supplied
test corpus is from Sony Ericsson SO505i recordings; other MOVA manufacturers
or containers may use different private storage and require an additional
parser.

## Repository layout

```text
src/pdc_audio/   importable decoder and ASF tooling
scripts/         portable Python build, test, and run helpers
tests/           media-independent core tests and ASF integration test
docs/            development instructions and historical technical audits
```

Standards, private recordings, and generated media are deliberately kept
outside Git in the sibling `pdc-audio-media` directory.

## Standards and references

The decoder and its conformance audits are based on these supplied references:

1. Association of Radio Industries and Businesses (ARIB), *Personal Digital
   Cellular Telecommunication System*, RCR STD-27 L, Fascicle 2, Revision L,
   30 November 2005, English translation. This is the normative source for the
   PDC half-rate speech-decoder equations, bit mappings, CRC, codebooks, and
   synthesis procedure used by the implementation.
2. Association of Radio Industries and Businesses (ARIB), *Personal Digital
   Cellular Telecommunication System: Quality Recommendation and Validation
   Test for Speech Codec—Standard Technical Characteristics and Validation
   Testing Methods Related to Speech Codec Connectivity and Speech Quality*,
   ARIB TR-T1 Rev. 1.1, 25 July 2000, English translation. This describes codec
   validation and the historical fixed-point master-codec/reference-file
   process underlying the remaining bit-exactness limitations.
3. Satoshi Miki, Kazunori Mano, Takehiro Moriya, Kumiko Oguchi, and Hitoshi
   Ohmuro, “A Pitch Synchronous Innovation CELP (PSI-CELP) Coder for 2–4
   kbit/s,” *Proceedings of ICASSP 1994*, vol. II, pp. II-113–II-116. This
   provides technical background on the pitch-synchronous innovation method
   used by the PDC half-rate codec.

Local copies are expected under `../pdc-audio-media/standards` with the supplied
filenames `ARIB PDC RCR STD-27 L.pdf`, `ARIB PDC RCR STD-27 TR-T01 v1.pdf`, and
`NTT PSI-CELP Paper.pdf`. They remain outside the repository because of their
copyright and redistribution terms. See [the core audit](docs/CORE_AUDIT.md)
and [the final audit](docs/FINAL_CORE_AUDIT.md) for equation-level use of these
references.

## Requirements and build

PDC-Audio requires Python 3.11 or later and NumPy. FFmpeg is needed only for ASF
or MP4 output; decoding to WAV does not require it.

In MSYS2 MinGW64, install the dependencies once:

```console
pacman -S --needed mingw-w64-x86_64-python-numpy \
    mingw-w64-x86_64-python-pip mingw-w64-x86_64-python-setuptools \
    mingw-w64-x86_64-python-build mingw-w64-x86_64-ffmpeg
```

Then build the project from the repository root:

```console
python scripts/build.py
```

The helper creates `.venv`, installs the project in editable mode, and builds a
wheel under `dist`.

## Run

Create a verified ASF in the external output directory:

```console
python scripts/convert_mova_pdc_audio.py \
    ../pdc-audio-media/samples/sample.asf
```

Choose outputs explicitly when required:

```console
python scripts/convert_mova_pdc_audio.py \
    ../pdc-audio-media/samples/sample.asf \
    --asf ../pdc-audio-media/outputs/decoded.asf \
    --wav ../pdc-audio-media/outputs/decoded.wav \
    --json ../pdc-audio-media/outputs/parameters.json
```

Useful options include `--float-npy`, `--mp4`, `--no-normalize`, `--force`,
and `--ffmpeg PATH`. ASF output verifies the copied video packets, decoded PCM,
and preserved binary descriptor by default; `--no-verify` disables that pass.

`scripts/decode_mova_pdc_audio.py` is retained as the Python compatibility
replacement for the older decode wrapper and accepts the same arguments.

The installed `pdc-audio` command provides the same decoder interface. Lower
level commands are also installed:

- `pdc-audio-extract` extracts the proprietary object from an ASF.
- `pdc-audio-decode-records` decodes an extracted sequence of 24-byte records.
- `pdc-audio-preserve` copies the descriptor into an already-remuxed ASF.

## Test

Run the core suite and every external ASF sample:

```console
python scripts/test.py
```

Run only media-independent tests with `python scripts/test.py --unit-only`.
See [the development instructions](docs/DEVELOPMENT.md) for all helper options
and the repository’s private-media rules.

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
