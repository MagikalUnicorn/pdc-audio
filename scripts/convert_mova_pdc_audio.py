"""Decode one supported MOVA ASF without modifying the source recording."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import subprocess

from _common import REPOSITORY_ROOT, find_ffmpeg, python_environment, venv_python


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="source MOVA ASF")
    parser.add_argument("--asf", type=Path, help="verified decoded ASF output")
    parser.add_argument("--wav", type=Path, help="decoded PCM WAV output")
    parser.add_argument("--json", type=Path, help="decoded parameter output")
    parser.add_argument("--float-npy", type=Path, help="float64 synthesis output")
    parser.add_argument("--mp4", type=Path, help="H.264/AAC listening output")
    parser.add_argument("--ffmpeg", help="FFmpeg executable name or path")
    parser.add_argument("--no-normalize", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    input_asf = args.input.expanduser().resolve()
    if not input_asf.is_file():
        parser.error("the input ASF does not exist")

    outputs = {
        "--asf": args.asf,
        "--wav": args.wav,
        "--json": args.json,
        "--float-npy": args.float_npy,
        "--mp4": args.mp4,
    }
    if not any(outputs.values()):
        output_directory = REPOSITORY_ROOT.parent / "pdc-audio-media" / "outputs"
        output_directory.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S%f")[:-3]
        outputs["--asf"] = output_directory / f"decoded-{timestamp}.asf"

    needs_ffmpeg = outputs["--asf"] is not None or outputs["--mp4"] is not None
    command = [str(venv_python()), "-m", "pdc_audio", str(input_asf)]
    if needs_ffmpeg:
        command.extend(["--ffmpeg", find_ffmpeg(args.ffmpeg)])
    for option, path in outputs.items():
        if path is not None:
            command.extend([option, str(path.expanduser().resolve())])
    if args.no_normalize:
        command.append("--no-normalize")
    if args.no_verify:
        command.append("--no-verify")
    if args.force:
        command.append("--force")

    subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=python_environment(),
        check=True,
    )


if __name__ == "__main__":
    main()
