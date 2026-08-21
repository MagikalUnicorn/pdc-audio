from __future__ import annotations

from pathlib import Path
import argparse
import json
import numpy as np

from . import DEFAULT_TABLES
from .pdc_decoder import PDCFrameParameters, PDCDecoder, write_wav

# The Sony record stores 147 meaningful bits among the first 20 bytes.
# Ordering here is the physical bit order discovered from cross-frame rank analysis.
PHYSICAL_POSITIONS: list[tuple[int, int]] = []
for byte in range(0, 8):
    for bit in range(8):
        PHYSICAL_POSITIONS.append((byte, bit))
for bit in range(5, 8):
    PHYSICAL_POSITIONS.append((8, bit))
for bit in range(8):
    PHYSICAL_POSITIONS.append((9, bit))
for bit in range(8):
    PHYSICAL_POSITIONS.append((10, bit))
for bit in range(0, 6):
    PHYSICAL_POSITIONS.append((11, bit))
for byte in range(12, 18):
    for bit in range(8):
        PHYSICAL_POSITIONS.append((byte, bit))
for bit in range(6, 8):
    PHYSICAL_POSITIONS.append((18, bit))
for bit in range(8):
    PHYSICAL_POSITIONS.append((19, bit))
assert len(PHYSICAL_POSITIONS) == 147


def extract_physical_bits(record: bytes) -> np.ndarray:
    if len(record) != 24:
        raise ValueError(f"record must be 24 bytes, got {len(record)}")
    return np.array([(record[b] >> bit) & 1 for b, bit in PHYSICAL_POSITIONS], dtype=np.uint8)


def reverse_groups(bits: np.ndarray, group_lengths: tuple[int, ...]) -> np.ndarray:
    """Reverse the meaningful bits inside each Sony 16-bit storage word."""
    bits = np.asarray(bits, dtype=np.uint8)
    if sum(group_lengths) != len(bits):
        raise ValueError("group lengths do not cover the input")
    out = np.empty_like(bits)
    start = 0
    for length in group_lengths:
        end = start + length
        out[start:end] = bits[start:end][::-1]
        start = end
    return out


def crc9(protected: np.ndarray) -> np.ndarray:
    """ARIB RCR STD-27 half-rate CRC, coefficients in ascending powers of x."""
    protected = np.asarray(protected, dtype=np.uint8)
    if protected.shape != (66,):
        raise ValueError("protected must contain 66 bits")
    work = np.zeros(75, dtype=np.uint8)
    work[9:] = protected
    # G(x) = 1 + x + x^2 + x^5 + x^8 + x^9.
    for degree in range(74, 8, -1):
        if work[degree]:
            for exponent in (0, 1, 2, 5, 8, 9):
                work[degree - 9 + exponent] ^= 1
    return work[:9]


def unpack_cvin(cvin: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Recover P[0..65] and CRC[0..8] from CVin[0..74]."""
    cvin = np.asarray(cvin, dtype=np.uint8)
    if cvin.shape != (75,):
        raise ValueError("CVin must contain 75 bits")
    protected = np.zeros(66, dtype=np.uint8)
    received_crc = np.zeros(9, dtype=np.uint8)
    for x in range(0, 5):
        received_crc[2 * x] = cvin[x]
    for x in range(5, 38):
        protected[74 - 2 * x] = cvin[x]
    for x in range(38, 71):
        protected[2 * x - 75] = cvin[x]
    for x in range(71, 75):
        received_crc[149 - 2 * x] = cvin[x]
    return protected, received_crc


def bits_to_uint(bits: np.ndarray) -> int:
    """Bits are indexed LSB first, matching the ARIB parameter tables."""
    return sum(int(bit) << i for i, bit in enumerate(bits))


def parameters_from_p_np(p: np.ndarray, np_bits: np.ndarray) -> PDCFrameParameters:
    p = np.asarray(p, dtype=np.uint8)
    np_bits = np.asarray(np_bits, dtype=np.uint8)
    if p.shape != (66,) or np_bits.shape != (72,):
        raise ValueError("expected 66 protected and 72 unprotected bits")

    # ARIB Table 5.2.2.2-2 stores each protected parameter in descending
    # P-index order: for example P[65] is LSP0 bit 0 (LSB), while P[59]
    # is LSP0 bit 6. Reverse each protected slice before converting it.
    lsp0 = bits_to_uint(p[59:66][::-1])
    lsp1 = bits_to_uint(p[51:59][::-1])
    power = bits_to_uint(p[44:51][::-1])
    lag = (
        bits_to_uint(p[36:44][::-1]),
        bits_to_uint(p[28:36][::-1]),
        bits_to_uint(p[20:28][::-1]),
        bits_to_uint(p[12:20][::-1]),
    )
    gain_high = (
        bits_to_uint(p[9:12][::-1]),
        bits_to_uint(p[6:9][::-1]),
        bits_to_uint(p[3:6][::-1]),
        bits_to_uint(p[0:3][::-1]),
    )

    lsp2 = bits_to_uint(np_bits[0:8])
    lsp3 = bits_to_uint(np_bits[8:16])
    gain_low = (
        bits_to_uint(np_bits[16:20]),
        bits_to_uint(np_bits[30:34]),
        bits_to_uint(np_bits[44:48]),
        bits_to_uint(np_bits[58:62]),
    )
    code = (
        bits_to_uint(np_bits[20:30]),
        bits_to_uint(np_bits[34:44]),
        bits_to_uint(np_bits[48:58]),
        bits_to_uint(np_bits[62:72]),
    )
    gain = tuple(gain_low[i] | (gain_high[i] << 4) for i in range(4))

    result = PDCFrameParameters(
        lsp0=lsp0,
        lsp1=lsp1,
        lsp2=lsp2,
        lsp3=lsp3,
        power=power,
        lag=lag,
        code=code,
        gain=gain,
    )
    result.validate()
    return result


def unpack_record(record: bytes, check_crc: bool = True) -> tuple[PDCFrameParameters, bool]:
    physical = extract_physical_bits(record)
    cvin = reverse_groups(physical[:75], (16, 16, 16, 16, 11))
    np_bits = reverse_groups(physical[75:147], (14, 16, 16, 16, 10))
    protected, received_crc = unpack_cvin(cvin)
    crc_ok = np.array_equal(crc9(protected), received_crc)
    if check_crc and not crc_ok:
        raise ValueError("CRC mismatch")
    return parameters_from_p_np(protected, np_bits), crc_ok


def load_records(path: str | Path, active_only: bool = True) -> list[bytes]:
    data = Path(path).read_bytes()
    if len(data) % 24:
        raise ValueError(f"record file length {len(data)} is not divisible by 24")
    records = [data[i:i + 24] for i in range(0, len(data), 24)]
    if active_only:
        # Sony appends one special end marker and one zero record in this sample.
        while records and records[-1] == bytes(24):
            records.pop()
        if records and records[-1][:19] == bytes(19):
            records.pop()
    return records


def frame_to_dict(frame: PDCFrameParameters, index: int, crc_ok: bool) -> dict[str, object]:
    return {
        "index": index,
        "crc_ok": crc_ok,
        "lsp": [frame.lsp0, frame.lsp1, frame.lsp2, frame.lsp3],
        "power": frame.power,
        "lag": list(frame.lag),
        "code": list(frame.code),
        "gain": list(frame.gain),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Decode Sony SEMC PDC-AUDIO records to WAV")
    parser.add_argument("input", type=Path, help="160x24-byte frame payload")
    parser.add_argument("output", type=Path, help="output mono 8 kHz WAV")
    parser.add_argument(
        "--tables",
        type=Path,
        default=DEFAULT_TABLES,
        help="parsed ARIB codebook table file",
    )
    parser.add_argument("--json", type=Path, help="optional decoded parameter dump")
    parser.add_argument("--include-trailer", action="store_true", help="attempt to decode trailing marker records")
    parser.add_argument("--no-normalize", action="store_true", help="do not peak-normalize output")
    args = parser.parse_args()

    records = load_records(args.input, active_only=not args.include_trailer)
    frames: list[PDCFrameParameters] = []
    report: list[dict[str, object]] = []
    crc_failures: list[int] = []
    for index, record in enumerate(records):
        try:
            frame, crc_ok = unpack_record(record, check_crc=False)
        except Exception as exc:
            raise RuntimeError(f"failed to unpack record {index}: {exc}") from exc
        if not crc_ok:
            crc_failures.append(index)
        frames.append(frame)
        report.append(frame_to_dict(frame, index, crc_ok))

    if crc_failures:
        raise RuntimeError(f"CRC failed in records: {crc_failures}")

    decoder = PDCDecoder(args.tables)
    samples = decoder.decode(frames)
    write_wav(args.output, samples, sample_rate=8000, normalize=not args.no_normalize)

    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Decoded {len(frames)} frames ({len(samples) / 8000:.3f} s)")
    print(f"CRC: {len(frames)}/{len(frames)} valid")
    print(f"Wrote: {args.output}")


if __name__ == "__main__":
    main()
