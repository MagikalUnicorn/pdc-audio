from __future__ import annotations

from pathlib import Path
import argparse
import json
import shutil
import subprocess
import wave
import numpy as np

from extract_semc_pdc_audio import extract_semc_pdc_audio
from pdc_decoder import PDCDecoder, write_wav
from sony_unpack import frame_to_dict, unpack_record


def write_wav_with_duration(path: Path, samples: np.ndarray, duration_seconds: float) -> None:
    target_samples = max(len(samples), round(duration_seconds * 8000))
    padded = np.zeros(target_samples, dtype=np.float64)
    padded[:len(samples)] = samples
    write_wav(path, padded, sample_rate=8000, normalize=True)


def decode_asf(
    input_asf: Path,
    output_wav: Path,
    tables: Path,
    parameter_json: Path | None = None,
) -> tuple[int, int, float]:
    obj = extract_semc_pdc_audio(input_asf)
    if obj.frame_size != 24:
        raise ValueError(f"unsupported Sony record size {obj.frame_size}; expected 24")

    records = [
        obj.frame_data[offset:offset + obj.frame_size]
        for offset in range(0, len(obj.frame_data), obj.frame_size)
    ]

    # Active SO505i speech records use one of three fixed 32-bit trailer words.
    # The sample then ends with a marker record and an all-zero record; those
    # records can coincidentally satisfy a zero CRC but are not codec frames.
    active_trailers = {
        # Trailer family observed in Phone Pictures 130.
        bytes.fromhex("1d84537d"),
        bytes.fromhex("2b3853ef"),
        # Trailer family observed in Phone Pictures 131-134.
        bytes.fromhex("9d84537d"),
        bytes.fromhex("2b3053ef"),
        # Shared trailer value.
        bytes.fromhex("c81653ff"),
    }
    active_count = len(records)
    while active_count and records[active_count - 1][20:24] not in active_trailers:
        active_count -= 1
    if active_count == 0:
        raise ValueError("no Sony PDC-AUDIO speech records with recognized trailers were found")
    for index in range(active_count):
        if records[index][20:24] not in active_trailers:
            raise ValueError(f"unexpected non-speech marker inside the active record sequence at {index}")

    frames = []
    report = []
    for index, record in enumerate(records[:active_count]):
        frame, crc_ok = unpack_record(record, check_crc=False)
        if not crc_ok:
            raise ValueError(f"CRC mismatch in active speech record {index}")
        frames.append(frame)
        report.append(frame_to_dict(frame, index, crc_ok))

    decoder = PDCDecoder(tables)
    samples = decoder.decode(frames)
    nominal_duration = len(records) * 0.040
    write_wav_with_duration(output_wav, samples, nominal_duration)

    if parameter_json:
        parameter_json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return len(frames), len(records), nominal_duration


def mux_video(input_asf: Path, input_wav: Path, output_mp4: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg was not found on PATH")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-y",
        "-i", str(input_asf),
        "-i", str(input_wav),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        "-c:a", "aac",
        "-b:a", "96k",
        "-shortest",
        str(output_mp4),
    ]
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Decode Sony SO505i SEMC PDC-AUDIO from ASF")
    parser.add_argument("input", type=Path, help="Sony ASF movie")
    parser.add_argument("output_wav", type=Path, help="decoded 8 kHz mono WAV")
    parser.add_argument(
        "--tables",
        type=Path,
        default=Path(__file__).with_name("arib_std27_tables.npz"),
        help="parsed ARIB codebook table file",
    )
    parser.add_argument("--json", type=Path, help="optional decoded parameter dump")
    parser.add_argument("--mp4", type=Path, help="optional MP4 with decoded audio muxed to the video")
    args = parser.parse_args()

    active, nominal, duration = decode_asf(args.input, args.output_wav, args.tables, args.json)
    print(f"CRC-valid speech records: {active}/{nominal}")
    print(f"Output duration: {duration:.3f} s (trailing invalid records padded with silence)")
    print(f"Wrote: {args.output_wav}")

    if args.mp4:
        mux_video(args.input, args.output_wav, args.mp4)
        print(f"Wrote: {args.mp4}")


if __name__ == "__main__":
    main()
