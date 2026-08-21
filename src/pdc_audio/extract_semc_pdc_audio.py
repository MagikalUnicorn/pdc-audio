from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse


@dataclass(slots=True)
class SemcPdcAudioObject:
    payload: bytes
    offset: int
    data_type: int
    frame_size: int
    nominal_frame_count: int
    frame_data_bytes: int
    video_interval_ms: int
    video_fps: int
    video_frame_count: int

    @property
    def header(self) -> bytes:
        return self.payload[:16]

    @property
    def frame_data(self) -> bytes:
        return self.payload[16:16 + self.frame_data_bytes]


def extract_semc_pdc_audio(asf_path: str | Path) -> SemcPdcAudioObject:
    """Extract the ASF extended-content BYTE_ARRAY named SEMC PDC-AUDIO."""
    data = Path(asf_path).read_bytes()
    descriptor_name = "SEMC PDC-AUDIO\0".encode("utf-16le")
    name_offset = data.find(descriptor_name)
    if name_offset < 2:
        raise ValueError("SEMC PDC-AUDIO descriptor was not found")

    stored_name_length = int.from_bytes(data[name_offset - 2:name_offset], "little")
    if stored_name_length != len(descriptor_name):
        raise ValueError(
            f"descriptor name length mismatch: {stored_name_length} != {len(descriptor_name)}"
        )

    metadata_offset = name_offset + len(descriptor_name)
    if metadata_offset + 4 > len(data):
        raise ValueError("truncated descriptor metadata")
    data_type = int.from_bytes(data[metadata_offset:metadata_offset + 2], "little")
    payload_length = int.from_bytes(data[metadata_offset + 2:metadata_offset + 4], "little")
    payload_offset = metadata_offset + 4
    payload = data[payload_offset:payload_offset + payload_length]
    if len(payload) != payload_length:
        raise ValueError("truncated SEMC PDC-AUDIO payload")
    if data_type != 1:
        raise ValueError(f"unexpected ASF descriptor data type {data_type}; expected BYTE_ARRAY (1)")
    if len(payload) < 16:
        raise ValueError("SEMC PDC-AUDIO payload is shorter than its 16-byte header")

    header = payload[:16]
    frame_size = int.from_bytes(header[2:4], "little")
    video_interval_ms = int.from_bytes(header[4:6], "little")
    video_fps = int.from_bytes(header[6:8], "little")
    frame_data_bytes = int.from_bytes(header[10:12], "little")
    video_frame_count = int.from_bytes(header[12:14], "little")

    if frame_size <= 0:
        raise ValueError("invalid zero frame size")
    if frame_data_bytes % frame_size:
        raise ValueError(
            f"frame-data length {frame_data_bytes} is not divisible by frame size {frame_size}"
        )
    if 16 + frame_data_bytes > len(payload):
        raise ValueError("header declares more frame data than the payload contains")

    return SemcPdcAudioObject(
        payload=payload,
        offset=payload_offset,
        data_type=data_type,
        frame_size=frame_size,
        nominal_frame_count=frame_data_bytes // frame_size,
        frame_data_bytes=frame_data_bytes,
        video_interval_ms=video_interval_ms,
        video_fps=video_fps,
        video_frame_count=video_frame_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract SEMC PDC-AUDIO from a MOVA ASF movie")
    parser.add_argument("input", type=Path, help="MOVA ASF movie")
    parser.add_argument("output", type=Path, help="output raw payload (.bin)")
    parser.add_argument("--frames", type=Path, help="optional output containing only 24-byte records")
    args = parser.parse_args()

    obj = extract_semc_pdc_audio(args.input)
    args.output.write_bytes(obj.payload)
    if args.frames:
        args.frames.write_bytes(obj.frame_data)

    print(f"Descriptor payload offset: {obj.offset}")
    print(f"Payload bytes: {len(obj.payload)}")
    print(f"Frame size: {obj.frame_size}")
    print(f"Nominal records: {obj.nominal_frame_count}")
    print(f"Video timing: {obj.video_fps} fps, {obj.video_frame_count} frames")


if __name__ == "__main__":
    main()
