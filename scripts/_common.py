"""Shared path and executable discovery for repository helper scripts."""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
MEDIA_ROOT = REPOSITORY_ROOT.parent / "pdc-audio-media"
DEFAULT_TABLES = MEDIA_ROOT / "generated" / "arib_std27_tables.npz"


def venv_python(*, required: bool = False) -> Path:
    candidates = (
        REPOSITORY_ROOT / ".venv" / "Scripts" / "python.exe",
        REPOSITORY_ROOT / ".venv" / "bin" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    if required:
        raise FileNotFoundError("the local .venv is missing; run scripts/build.py first")
    return Path(sys.executable)


def python_environment(tables: Path | None = None) -> dict[str, str]:
    environment = os.environ.copy()
    source_root = str(REPOSITORY_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root + os.pathsep + existing if existing else source_root
    )
    if tables is not None:
        environment["PDC_AUDIO_TABLES"] = str(tables)
    return environment


def find_ffmpeg(override: str | None = None) -> str:
    if override:
        discovered = shutil.which(override)
        if discovered:
            return discovered
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        raise FileNotFoundError(f"FFmpeg was not found: {override}")

    discovered = shutil.which("ffmpeg")
    if discovered:
        return discovered

    for parent in (REPOSITORY_ROOT, *REPOSITORY_ROOT.parents):
        candidate = parent / "mingw64" / "bin" / "ffmpeg.exe"
        if candidate.is_file():
            return str(candidate)
    raise FileNotFoundError("FFmpeg was not found; install it or pass --ffmpeg")
