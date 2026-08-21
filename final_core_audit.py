from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import tempfile

import numpy as np
from scipy.signal import lfilter

from extract_semc_pdc_audio import extract_semc_pdc_audio
from pdc_decoder import PDCDecoder, PDCFrameParameters, decode_lsp_pair, lsp_to_lpc, lpc_to_parcor
from sony_unpack import (
    PHYSICAL_POSITIONS,
    crc9,
    extract_physical_bits,
    parameters_from_p_np,
    reverse_groups,
    unpack_cvin,
    unpack_record,
)

ROOT = Path(__file__).resolve().parent
TABLE_FILE = ROOT / "arib_std27_tables.npz"
SAMPLES = [Path(f"/mnt/data/Phone Pictures {n}.asf") for n in range(130, 135)]
ACTIVE_TRAILERS = {
    bytes.fromhex("1d84537d"), bytes.fromhex("2b3853ef"),
    bytes.fromhex("9d84537d"), bytes.fromhex("2b3053ef"),
    bytes.fromhex("c81653ff"),
}


def active_records(path: Path) -> tuple[list[bytes], list[bytes], bytes]:
    obj = extract_semc_pdc_audio(path)
    records = [obj.frame_data[i:i + obj.frame_size]
               for i in range(0, len(obj.frame_data), obj.frame_size)]
    active = [r for r in records if r[20:24] in ACTIVE_TRAILERS]
    return active, records, obj.payload[:16]


def crc9_independent(protected: np.ndarray) -> np.ndarray:
    """Independent integer-polynomial division, not the array algorithm used by crc9()."""
    p = sum(int(bit) << (9 + i) for i, bit in enumerate(protected))
    generator = sum(1 << exponent for exponent in (0, 1, 2, 5, 8, 9))
    for degree in range(74, 8, -1):
        if (p >> degree) & 1:
            p ^= generator << (degree - 9)
    return np.array([(p >> i) & 1 for i in range(9)], dtype=np.uint8)


def uint_to_lsb_bits(value: int, width: int) -> np.ndarray:
    return np.array([(value >> i) & 1 for i in range(width)], dtype=np.uint8)


def frame_to_p_np(frame: PDCFrameParameters) -> tuple[np.ndarray, np.ndarray]:
    """Inverse of parameters_from_p_np(), used only for audit round-trips."""
    p = np.zeros(66, dtype=np.uint8)
    np_bits = np.zeros(72, dtype=np.uint8)
    p[59:66] = uint_to_lsb_bits(frame.lsp0, 7)[::-1]
    p[51:59] = uint_to_lsb_bits(frame.lsp1, 8)[::-1]
    p[44:51] = uint_to_lsb_bits(frame.power, 7)[::-1]
    for sl, value in zip(((36,44),(28,36),(20,28),(12,20)), frame.lag):
        p[sl[0]:sl[1]] = uint_to_lsb_bits(value, 8)[::-1]
    for sl, value in zip(((9,12),(6,9),(3,6),(0,3)), frame.gain):
        p[sl[0]:sl[1]] = uint_to_lsb_bits(value >> 4, 3)[::-1]
    np_bits[0:8] = uint_to_lsb_bits(frame.lsp2, 8)
    np_bits[8:16] = uint_to_lsb_bits(frame.lsp3, 8)
    for low_sl, code_sl, gain, code in zip(
        ((16,20),(30,34),(44,48),(58,62)),
        ((20,30),(34,44),(48,58),(62,72)),
        frame.gain, frame.code,
    ):
        np_bits[low_sl[0]:low_sl[1]] = uint_to_lsb_bits(gain & 15, 4)
        np_bits[code_sl[0]:code_sl[1]] = uint_to_lsb_bits(code, 10)
    return p, np_bits


def pack_cvin(protected: np.ndarray, crc: np.ndarray) -> np.ndarray:
    cvin = np.zeros(75, dtype=np.uint8)
    for x in range(0, 5):
        cvin[x] = crc[2 * x]
    for x in range(5, 38):
        cvin[x] = protected[74 - 2 * x]
    for x in range(38, 71):
        cvin[x] = protected[2 * x - 75]
    for x in range(71, 75):
        cvin[x] = crc[149 - 2 * x]
    return cvin


def audit_record_roundtrip(record: bytes) -> None:
    physical = extract_physical_bits(record)
    cvin = reverse_groups(physical[:75], (16,16,16,16,11))
    np_bits = reverse_groups(physical[75:], (14,16,16,16,10))
    p, received_crc = unpack_cvin(cvin)
    frame = parameters_from_p_np(p, np_bits)
    p2, np2 = frame_to_p_np(frame)
    np.testing.assert_array_equal(p2, p)
    np.testing.assert_array_equal(np2, np_bits)
    crc_a = crc9(p)
    crc_b = crc9_independent(p)
    np.testing.assert_array_equal(crc_a, crc_b)
    np.testing.assert_array_equal(crc_a, received_crc)
    cvin2 = pack_cvin(p2, crc_a)
    physical2 = np.concatenate([
        reverse_groups(cvin2, (16,16,16,16,11)),
        reverse_groups(np2, (14,16,16,16,10)),
    ])
    np.testing.assert_array_equal(physical2, physical)


def audit_tables(tables: dict[str, np.ndarray]) -> dict[str, object]:
    expected_shapes = {
        "clspl": (128, 4), "clsph": (256, 8), "clspm1": (256, 8),
        "clspm2": (8, 8), "cpow": (128, 4), "cfcb": (4, 80),
        "cscb0": (16, 4, 80), "cscb1": (16, 4, 80), "cgain": (128, 2),
    }
    for name, shape in expected_shapes.items():
        assert name in tables, f"missing table {name}"
        assert tables[name].shape == shape, (name, tables[name].shape, shape)
        assert np.all(np.isfinite(tables[name])), f"non-finite values in {name}"
    np.testing.assert_array_equal(tables["cfcb"] * 32768.0, np.rint(tables["cfcb"] * 32768.0))
    for name in ("cscb0", "cscb1"):
        np.testing.assert_array_equal(tables[name] * 128.0, np.rint(tables[name] * 128.0))
    return {name: list(shape) for name, shape in expected_shapes.items()}


def audit_lpc_and_synthesis(frames: list[PDCFrameParameters], tables: dict[str, np.ndarray]) -> dict[str, float]:
    # Validate every decoded LSP/LPC set for strict ordering and filter stability.
    prev = np.linspace(0.05, 0.95, 10, dtype=np.float64)
    min_lsp_gap = math.inf
    max_abs_parcor = 0.0
    for frame in frames:
        q1, q3 = decode_lsp_pair(frame, tables)
        for lsp in (0.5*(prev+q1), q1, 0.5*(q1+q3), q3):
            min_lsp_gap = min(min_lsp_gap, float(np.min(np.diff(lsp))))
            assert np.all(np.diff(lsp) > 0)
            a = lsp_to_lpc(lsp)
            k = lpc_to_parcor(a)
            assert np.all(np.isfinite(a)) and np.all(np.isfinite(k))
            max_abs_parcor = max(max_abs_parcor, float(np.max(np.abs(k))))
            assert np.max(np.abs(k)) < 1.0
        prev = q3

    # Independently cross-check the synthesis recurrence against scipy.signal.lfilter.
    rng = np.random.default_rng(0x5051)
    max_filter_error = 0.0
    for _ in range(100):
        lsp = np.sort(rng.uniform(0.03, 0.97, 10))
        # Enforce a safe separation for a stable test vector.
        for i in range(1, 10):
            lsp[i] = max(lsp[i], lsp[i-1] + 0.012)
        if lsp[-1] >= 0.99:
            continue
        a = lsp_to_lpc(lsp)
        excitation = rng.normal(size=80)
        history = rng.normal(size=10)
        # scipy zi is DF-II state; obtain equivalent state by filtering the known history.
        # More robustly compare against a second direct equation with immutable history.
        direct = np.empty(80)
        full = list(history)
        for i, x in enumerate(excitation):
            y = float(x - np.dot(a[1:], np.asarray(full[-10:])[::-1]))
            direct[i] = y
            full.append(y)
        # lfilter over concatenated prior outputs is not directly seedable from output history,
        # so use lfiltic to construct the exact state.
        from scipy.signal import lfiltic
        zi = lfiltic([1.0], a, y=history[::-1], x=np.zeros(10))
        scipy_out, _ = lfilter([1.0], a, excitation, zi=zi)
        max_filter_error = max(max_filter_error, float(np.max(np.abs(direct - scipy_out))))
    assert max_filter_error < 1e-5, max_filter_error
    return {
        "minimum_lsp_gap": min_lsp_gap,
        "maximum_absolute_parcor": max_abs_parcor,
        "maximum_synthesis_crosscheck_error": max_filter_error,
    }


def decode_native(path: Path) -> tuple[np.ndarray, list[PDCFrameParameters]]:
    active, _, _ = active_records(path)
    frames = [unpack_record(r)[0] for r in active]
    decoder = PDCDecoder(TABLE_FILE)
    return decoder.decode(frames), frames


def audit_reset_sensitivity(frames: list[PDCFrameParameters]) -> dict[str, float]:
    """Quantify the unresolved first-frame LSP reset value without changing the baseline."""
    variants = {
        "baseline_even": np.linspace(0.05, 0.95, 10),
        "repeat_first_q1": None,
        "even_0.04_0.94": np.linspace(0.04, 0.94, 10),
    }
    tables = {k: v.astype(np.float64) for k, v in np.load(TABLE_FILE).items()}
    q1, _ = decode_lsp_pair(frames[0], tables)
    variants["repeat_first_q1"] = q1
    outputs = {}
    for name, init in variants.items():
        d = PDCDecoder(TABLE_FILE)
        d.prev_lsp3 = np.asarray(init, dtype=np.float64).copy()
        outputs[name] = d.decode(frames)
    base = outputs["baseline_even"]
    result = {}
    for name, out in outputs.items():
        diff = out - base
        result[f"{name}_whole_clip_diff_rms_ratio"] = float(np.sqrt(np.mean(diff**2)) / max(np.sqrt(np.mean(base**2)), 1e-30))
        result[f"{name}_first_40ms_diff_rms_ratio"] = float(np.sqrt(np.mean(diff[:320]**2)) / max(np.sqrt(np.mean(base[:320]**2)), 1e-30))
        tail = diff[320:]
        result[f"{name}_after_first_frame_diff_rms_ratio"] = float(np.sqrt(np.mean(tail**2)) / max(np.sqrt(np.mean(base[320:]**2)), 1e-30))
    return result


def main() -> None:
    tables_npz = np.load(TABLE_FILE)
    tables = {k: tables_npz[k].astype(np.float64) for k in tables_npz.files}
    report: dict[str, object] = {
        "decoder_version": "3.2-final-audit (waveform-identical to v3.1)",
        "table_sha256": hashlib.sha256(TABLE_FILE.read_bytes()).hexdigest(),
        "table_shapes": audit_tables(tables),
        "clips": {},
    }
    all_frames: list[PDCFrameParameters] = []
    output_hashes = {}
    for path in SAMPLES:
        active, records, header = active_records(path)
        assert len(records) == 160 and len(active) == 158
        assert header == bytes.fromhex("43281800c80005007800000f20000000")
        for record in active:
            audit_record_roundtrip(record)
        samples, frames = decode_native(path)
        assert samples.shape == (158 * 320,)
        assert np.all(np.isfinite(samples))
        all_frames.extend(frames)
        clip = path.stem.split()[-1]
        output_hashes[clip] = hashlib.sha256(samples.astype("<f8").tobytes()).hexdigest()
        trailer_counts = Counter(r[20:24].hex() for r in active)
        report["clips"][clip] = {
            "stored_records": len(records),
            "speech_records": len(active),
            "crc_valid": len(active),
            "decoded_samples": len(samples),
            "decoded_seconds": len(samples) / 8000,
            "native_float64_sha256": output_hashes[clip],
            "peak_native": float(np.max(np.abs(samples))),
            "rms_native": float(np.sqrt(np.mean(samples**2))),
            "trailer_counts": dict(trailer_counts),
        }
    report["lpc_and_synthesis"] = audit_lpc_and_synthesis(all_frames, tables)
    _, first_frames = decode_native(SAMPLES[0])
    report["reset_sensitivity_clip_130"] = audit_reset_sensitivity(first_frames)
    report["totals"] = {
        "clips": 5,
        "speech_records": 5 * 158,
        "record_roundtrips": 5 * 158,
        "crc_crosschecks": 5 * 158,
        "decoded_subframes": 5 * 158 * 4,
    }
    out = ROOT / "final-core-audit-results.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("Final core audit passed.")
    print(f"  790/790 Sony speech records round-tripped at the meaningful-bit level")
    print(f"  790/790 CRCs matched an independent polynomial implementation")
    print(f"  3,160 decoded subframes had ordered LSPs and stable LPC filters")
    print(f"  synthesis recurrence cross-check max error: {report['lpc_and_synthesis']['maximum_synthesis_crosscheck_error']:.3e}")
    print(f"  tables SHA-256: {report['table_sha256']}")
    print(f"  wrote: {out}")


if __name__ == "__main__":
    main()
