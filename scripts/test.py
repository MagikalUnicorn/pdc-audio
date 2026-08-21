"""Run media-independent tests and optional external ASF integrations."""

from __future__ import annotations

from pathlib import Path
import argparse
import subprocess

from _common import REPOSITORY_ROOT, find_ffmpeg, python_environment, venv_python


def run(command: list[str]) -> None:
    subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=python_environment(),
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unit-only", action="store_true")
    parser.add_argument("--sample-dir", type=Path)
    parser.add_argument("--ffmpeg", help="FFmpeg executable name or path")
    args = parser.parse_args()

    python = venv_python()
    print("Running media-independent decoder tests...", flush=True)
    run(
        [
            str(python),
            "-m",
            "unittest",
            "discover",
            "-s",
            str(REPOSITORY_ROOT / "tests"),
            "-p",
            "test_*.py",
            "-v",
        ]
    )
    if args.unit_only:
        print("Unit tests passed.", flush=True)
        return

    sample_directory = args.sample_dir or (
        REPOSITORY_ROOT.parent / "pdc-audio-media" / "samples"
    )
    if not sample_directory.is_dir():
        print("No sample directory is available; integration tests skipped.", flush=True)
        return

    samples = sorted(
        sample_directory.rglob("*.asf"),
        key=lambda path: (path.stat().st_size, path.name),
    )
    if not samples:
        print("No ASF samples are available; integration tests skipped.", flush=True)
        return

    ffmpeg = find_ffmpeg(args.ffmpeg)
    integration_test = REPOSITORY_ROOT / "tests" / "asf_integration.py"
    for index, sample in enumerate(samples, 1):
        print(f"Running ASF integration sample {index}/{len(samples)}...", flush=True)
        run([str(python), str(integration_test), str(sample), "--ffmpeg", ffmpeg])

    print(
        f"All tests passed, including {len(samples)} ASF integration samples.",
        flush=True,
    )


if __name__ == "__main__":
    main()
