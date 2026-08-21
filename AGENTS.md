# PDC-Audio development environment

These instructions apply to the PDC-Audio repository. PDC-Audio is a small
Python utility for recovering and decoding the `SEMC PDC-AUDIO` objects stored
in Japanese MOVA handset video recordings.

## Repository layout

- Keep importable Python code in `src/pdc_audio`.
- Keep automated tests in `tests` and command wrappers in `scripts`.
- Keep project documentation in `docs`.
- Keep standards, source recordings, extracted payloads, decoded audio, and
  other large or redistribution-sensitive media outside this repository in the
  sibling `pdc-audio-media` directory.
- Do not modify original recordings in place. Write converted or diagnostic
  outputs to a separate working directory.

## Before editing

- Preserve dirty files and unrelated user changes.
- Read `README.md` and the relevant audit or validation document before
  changing decoder behaviour.
- Follow the style already established in the affected source file.
- Keep text files LF-only. The repository uses `.gitattributes` to make this
  explicit.

## Python and builds

- Support Python 3.11 or later.
- Use a repository-local virtual environment (`.venv`) for development
  dependencies; do not commit it.
- Install the project in editable mode before testing: `python -m pip install -e .`.
- Treat a successful package build, import check, and automated test run as the
  normal build verification for this Python utility.
- FFmpeg and FFprobe are optional runtime tools used only for container
  conversion and integration checks.

## Tests and media

- Keep unit tests finite and independent of private recordings where possible.
- Tests that require handset recordings must accept paths from the command
  line or environment and skip cleanly when media is unavailable.
- Preserve the existing audited decoder waveform unless a normative equation,
  official reference vector, or reproducible recording evidence justifies a
  change.
- Do not claim bit-exact conformance without an official PSI-CELP reference
  vector and a matching fixed-point arithmetic model.
- Keep generated WAV, ASF, MP4, NumPy, JSON, and log files out of source
  directories unless they are deliberately small test fixtures.

## Git

- Make focused commits whose messages describe the development step or
  behaviour change.
- Preserve imported historical snapshots as distinct commits; do not rewrite
  them merely to match the current layout.
- Do not push, force-push, create remote branches or tags, or otherwise change
  remote state unless the user explicitly requests it.
