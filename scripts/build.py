"""Create the local environment, install PDC-Audio, and build its wheel."""

from __future__ import annotations

from pathlib import Path
import argparse
import subprocess
import sys

from _common import REPOSITORY_ROOT, venv_python


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)


def ensure_environment() -> Path:
    try:
        return venv_python(required=True)
    except FileNotFoundError:
        print("Creating the local Python environment...", flush=True)
        run(
            [
                sys.executable,
                "-m",
                "venv",
                "--system-site-packages",
                str(REPOSITORY_ROOT / ".venv"),
            ]
        )
        return venv_python(required=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    if sys.version_info < (3, 11):
        raise SystemExit("PDC-Audio requires Python 3.11 or later")

    python = ensure_environment()
    dependency_check = subprocess.run(
        [str(python), "-c", "import numpy, setuptools"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
    )
    if dependency_check.returncode:
        raise SystemExit(
            "NumPy and setuptools are unavailable. In MSYS2 MinGW64, install "
            "mingw-w64-x86_64-python-numpy, python-pip, python-setuptools, "
            "and python-build with pacman."
        )

    print("Installing PDC-Audio in editable mode...", flush=True)
    run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-build-isolation",
            "--no-deps",
            "-e",
            str(REPOSITORY_ROOT),
        ]
    )

    print("Building the wheel...", flush=True)
    build_available = subprocess.run(
        [str(python), "-c", "import build"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
    ).returncode == 0
    if build_available:
        run(
            [
                str(python),
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                str(REPOSITORY_ROOT),
            ]
        )
    else:
        run(
            [
                str(python),
                "-m",
                "pip",
                "wheel",
                "--no-build-isolation",
                "--no-deps",
                "--wheel-dir",
                str(REPOSITORY_ROOT / "dist"),
                str(REPOSITORY_ROOT),
            ]
        )

    wheels = sorted(
        (REPOSITORY_ROOT / "dist").glob("pdc_audio-*.whl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not wheels:
        raise SystemExit("the build completed without producing a wheel")
    print(f"Build passed: dist/{wheels[0].name}", flush=True)


if __name__ == "__main__":
    main()
