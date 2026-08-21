from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import wave

import numpy as np

from . import DEFAULT_TABLES
from .extract_semc_pdc_audio import extract_semc_pdc_audio
from .pdc_decoder import PDCDecoder, write_wav
from .preserve_semc_pdc_attachment import (
    preserve_attachment,
    verify_preserved_attachment,
)
from .sony_unpack import frame_to_dict, unpack_record


ACTIVE_TRAILERS = {
    # Trailer family observed in Phone Pictures 130.
    bytes.fromhex("1d84537d"),
    bytes.fromhex("2b3853ef"),
    # Trailer family observed in Phone Pictures 131-134.
    bytes.fromhex("9d84537d"),
    bytes.fromhex("2b3053ef"),
    # Shared trailer value.
    bytes.fromhex("c81653ff"),
}


def pad_to_duration(samples: np.ndarray, duration_seconds: float) -> np.ndarray:
    target_samples = max(len(samples), round(duration_seconds * 8000))
    padded = np.zeros(target_samples, dtype=np.float64)
    padded[: len(samples)] = samples
    return padded


def write_wav_with_duration(
    path: Path,
    samples: np.ndarray,
    duration_seconds: float,
    *,
    normalize: bool,
) -> np.ndarray:
    path.parent.mkdir(parents=True, exist_ok=True)
    padded = pad_to_duration(samples, duration_seconds)
    write_wav(path, padded, sample_rate=8000, normalize=normalize)
    return padded


def _decode_frames(input_asf: Path, tables: Path) -> tuple[np.ndarray, list[dict], int, int, float]:
    obj = extract_semc_pdc_audio(input_asf)
    if obj.frame_size != 24:
        raise ValueError(f"unsupported Sony record size {obj.frame_size}; expected 24")

    records = [
        obj.frame_data[offset : offset + obj.frame_size]
        for offset in range(0, len(obj.frame_data), obj.frame_size)
    ]

    # The object ends with one Sony marker record and one all-zero padding record.
    # Find the contiguous prefix of recognized active records rather than treating a
    # coincidental CRC on marker/padding data as a speech frame.
    active_count = len(records)
    while active_count and records[active_count - 1][20:24] not in ACTIVE_TRAILERS:
        active_count -= 1
    if active_count == 0:
        raise ValueError("no Sony PDC-AUDIO speech records with recognized trailers were found")
    for index in range(active_count):
        if records[index][20:24] not in ACTIVE_TRAILERS:
            raise ValueError(
                f"unexpected non-speech marker inside the active record sequence at {index}"
            )

    frames = []
    report: list[dict] = []
    for index, record in enumerate(records[:active_count]):
        frame, crc_ok = unpack_record(record, check_crc=False)
        if not crc_ok:
            raise ValueError(f"CRC mismatch in active speech record {index}")
        frames.append(frame)
        report.append(frame_to_dict(frame, index, crc_ok))

    decoder = PDCDecoder(tables)
    samples = decoder.decode(frames)
    nominal_duration = len(records) * 0.040
    return samples, report, len(frames), len(records), nominal_duration


def decode_asf(
    input_asf: Path,
    output_wav: Path,
    tables: Path,
    parameter_json: Path | None = None,
    *,
    normalize: bool = True,
    float_npy: Path | None = None,
) -> tuple[int, int, float]:
    """Compatibility API retained for the v3 audit and external callers."""
    samples, report, active, nominal, duration = _decode_frames(input_asf, tables)
    padded = write_wav_with_duration(output_wav, samples, duration, normalize=normalize)

    if float_npy:
        float_npy.parent.mkdir(parents=True, exist_ok=True)
        np.save(float_npy, padded)
    if parameter_json:
        parameter_json.parent.mkdir(parents=True, exist_ok=True)
        parameter_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return active, nominal, duration


def _resolve_executable(command: str) -> str:
    found = shutil.which(command)
    if found:
        return found
    candidate = Path(command)
    if candidate.is_file():
        return str(candidate.resolve())
    raise RuntimeError(f"required executable was not found: {command}")


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _stream_sha256(ffmpeg: str, media: Path, stream_specifier: str) -> str:
    result = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(media),
            "-map",
            stream_specifier,
            "-c",
            "copy",
            "-f",
            "hash",
            "-hash",
            "sha256",
            "-",
        ]
    )
    output = result.stdout.strip()
    prefix = "SHA256="
    if not output.startswith(prefix):
        raise RuntimeError(f"unexpected FFmpeg hash output: {output!r}")
    return output[len(prefix) :].lower()


def _verify_wav(path: Path) -> None:
    with wave.open(str(path), "rb") as wav:
        properties = (
            wav.getframerate(),
            wav.getnchannels(),
            wav.getsampwidth(),
        )
        if properties != (8000, 1, 2):
            raise ValueError(
                "decoded WAV has unexpected properties: "
                f"rate={properties[0]}, channels={properties[1]}, width={properties[2]}"
            )


def mux_mp4(input_asf: Path, input_wav: Path, output_mp4: Path, ffmpeg_command: str) -> None:
    ffmpeg = _resolve_executable(ffmpeg_command)
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_asf),
        "-i",
        str(input_wav),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        str(output_mp4),
    ]
    _run(command)


def mux_asf_preserving_original(
    input_asf: Path,
    input_wav: Path,
    output_asf: Path,
    *,
    ffmpeg_command: str = "ffmpeg",
    verify: bool = True,
) -> dict[str, str]:
    """Add decoded PCM to a new ASF while preserving MJPEG and SEMC PDC-AUDIO.

    FFmpeg copies the original video packets and muxes the decoded PCM. FFmpeg does
    not preserve the proprietary BYTE_ARRAY metadata, so the original descriptor is
    then inserted byte-for-byte into the remuxed ASF header.
    """
    ffmpeg = _resolve_executable(ffmpeg_command)
    input_asf = input_asf.resolve()
    output_asf = output_asf.resolve()
    input_wav = input_wav.resolve()

    if input_asf == output_asf:
        raise ValueError("output ASF must not overwrite the original Sony ASF")

    output_asf.parent.mkdir(parents=True, exist_ok=True)
    _verify_wav(input_wav)

    with tempfile.TemporaryDirectory(prefix="sony-pdc-asf-", dir=output_asf.parent) as temp_dir:
        temp_dir_path = Path(temp_dir)
        remuxed = temp_dir_path / "remuxed-with-pcm.asf"
        patched = temp_dir_path / "remuxed-with-pcm-and-original-attachment.asf"

        command = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(input_asf),
            "-i",
            str(input_wav),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-map_metadata",
            "0",
            "-c:v",
            "copy",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "8000",
            "-ac",
            "1",
            "-f",
            "asf",
            str(remuxed),
        ]
        _run(command)
        preserve_attachment(input_asf, remuxed, patched)

        verification: dict[str, str] = {}
        if verify:
            verify_preserved_attachment(input_asf, patched)

            source_video_hash = _stream_sha256(ffmpeg, input_asf, "0:v:0")
            output_video_hash = _stream_sha256(ffmpeg, patched, "0:v:0")
            if source_video_hash != output_video_hash:
                raise ValueError(
                    "MJPEG verification failed: output video packet hash differs from source"
                )

            wav_audio_hash = _stream_sha256(ffmpeg, input_wav, "0:a:0")
            output_audio_hash = _stream_sha256(ffmpeg, patched, "0:a:0")
            if wav_audio_hash != output_audio_hash:
                raise ValueError(
                    "PCM verification failed: output audio packet hash differs from decoded WAV"
                )

            verification = {
                "mjpeg_sha256": source_video_hash,
                "pcm_sha256": wav_audio_hash,
                "semc_pdc_audio": "byte-for-byte identical",
            }

        # os.replace is atomic when the temporary directory is on the same volume.
        os.replace(patched, output_asf)
        return verification


def _check_output(path: Path | None, *, force: bool) -> None:
    if path is None:
        return
    if path.exists() and not force:
        raise FileExistsError(f"output already exists (use --force to replace it): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Decode Sony SO505i SEMC PDC-AUDIO and optionally add the decoded PCM "
            "to a new ASF while preserving the original MJPEG and binary descriptor."
        )
    )
    parser.add_argument("input", type=Path, help="original Sony ASF movie")
    parser.add_argument(
        "legacy_output_wav",
        nargs="?",
        type=Path,
        help="legacy positional WAV output; prefer --wav",
    )
    parser.add_argument("--wav", type=Path, help="optional decoded 8 kHz mono WAV")
    parser.add_argument(
        "--asf",
        type=Path,
        help=(
            "optional ASF with original MJPEG copied losslessly, decoded PCM audio, "
            "and original SEMC PDC-AUDIO BYTE_ARRAY preserved byte-for-byte"
        ),
    )
    parser.add_argument("--mp4", type=Path, help="optional H.264/AAC listening MP4")
    parser.add_argument(
        "--tables",
        type=Path,
        default=DEFAULT_TABLES,
        help="parsed ARIB codebook table file",
    )
    parser.add_argument("--json", type=Path, help="optional decoded parameter dump")
    parser.add_argument(
        "--no-normalize",
        action="store_true",
        help="use native amplitude with 16-bit saturation instead of peak normalization",
    )
    parser.add_argument(
        "--float-npy",
        type=Path,
        help="optional lossless float64 synthesis output padded to movie duration",
    )
    parser.add_argument(
        "--ffmpeg",
        default="ffmpeg",
        help="FFmpeg executable name or full path",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="skip byte-for-byte attachment, video-packet, and PCM-packet verification",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace existing output files (never replaces the input ASF)",
    )
    args = parser.parse_args()

    if args.legacy_output_wav and args.wav:
        parser.error("specify either the positional WAV output or --wav, not both")
    output_wav = args.wav or args.legacy_output_wav
    if not any((output_wav, args.asf, args.mp4, args.json, args.float_npy)):
        parser.error("no output requested; use --asf, --wav, --mp4, --json, or --float-npy")

    input_asf = args.input.resolve()
    if not input_asf.is_file():
        parser.error(f"input ASF does not exist: {input_asf}")

    for output in (output_wav, args.asf, args.mp4, args.json, args.float_npy):
        _check_output(output, force=args.force)
    if args.asf and args.asf.resolve() == input_asf:
        parser.error("--asf must not be the same path as the input ASF")

    # A temporary WAV is used when only a container output is requested.
    with tempfile.TemporaryDirectory(prefix="sony-pdc-decode-") as temp_dir:
        working_wav = output_wav or (Path(temp_dir) / "decoded-pdc.wav")
        active, nominal, duration = decode_asf(
            input_asf,
            working_wav,
            args.tables,
            args.json,
            normalize=not args.no_normalize,
            float_npy=args.float_npy,
        )

        print(f"CRC-valid speech records: {active}/{nominal}")
        print(f"Output duration: {duration:.3f} s (trailing marker/padding padded with silence)")
        if output_wav:
            print(f"Wrote WAV: {output_wav}")

        if args.asf:
            verification = mux_asf_preserving_original(
                input_asf,
                working_wav,
                args.asf,
                ffmpeg_command=args.ffmpeg,
                verify=not args.no_verify,
            )
            print(f"Wrote ASF: {args.asf}")
            if verification:
                print(f"Verified MJPEG SHA-256: {verification['mjpeg_sha256']}")
                print(f"Verified PCM SHA-256:   {verification['pcm_sha256']}")
                print("Verified SEMC PDC-AUDIO: byte-for-byte identical")

        if args.mp4:
            mux_mp4(input_asf, working_wav, args.mp4, args.ffmpeg)
            print(f"Wrote MP4: {args.mp4}")


if __name__ == "__main__":
    main()
