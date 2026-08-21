from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import hashlib
import math
import tempfile
import wave

import numpy as np

from decode_sony_asf import decode_asf
from extract_semc_pdc_audio import extract_semc_pdc_audio
from pdc_decoder import (
    NSUB,
    _SCB0_ROWS,
    _SCB1_ROWS,
    _dq_interp,
    acb_vector,
    decode_lag,
    decode_scb_code,
    psi_vector,
)
from sony_unpack import unpack_record

ROOT = Path(__file__).resolve().parent
SAMPLES = [Path(f"/mnt/data/Phone Pictures {number}.asf") for number in range(130, 135)]
ACTIVE_TRAILERS = {
    bytes.fromhex("1d84537d"),
    bytes.fromhex("2b3853ef"),
    bytes.fromhex("9d84537d"),
    bytes.fromhex("2b3053ef"),
    bytes.fromhex("c81653ff"),
}


def legal_lagf(lagi: int) -> tuple[int, ...]:
    if 16 <= lagi <= 45:
        return (0, 1, 2, 3)
    if 46 <= lagi <= 65:
        return (1, 3)
    if 66 <= lagi <= 96:
        return (1,)
    raise ValueError(lagi)


def acb_reference(dq: np.ndarray, lagi: int, lagf: int) -> np.ndarray:
    candidates: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for n in range(NSUB // lagi + 1):
        phase_term = lagf + n * (lagf - 1)
        frac = phase_term % 4
        offset = phase_term // 4
        for j in range(-1, lagi):
            pos = n * lagi + j - offset
            if 0 <= pos < NSUB:
                candidates[pos].append((n, j, frac))

    def priority(item: tuple[int, int, int]) -> int:
        _, j, _ = item
        if j == 0:
            return 0
        if j == lagi - 1:
            return 1
        if 1 <= j <= lagi - 2:
            return 2
        if j == -1:
            return 3
        raise AssertionError(j)

    assert set(candidates) == set(range(NSUB))
    result = np.empty(NSUB, dtype=np.float64)
    for pos in range(NSUB):
        n, j, frac = min(candidates[pos], key=priority)
        del n
        result[pos] = _dq_interp(dq, lagi, j, frac)
    return result


def psi_reference(book: np.ndarray, index: int, lagi: int, lagf: int) -> np.ndarray:
    if lagi == 0:
        return np.array(book[index, 1, :], dtype=np.float64)
    candidates: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for n in range(NSUB // lagi + 1):
        phase_term = 1 + n * (lagf - 1)
        frac = phase_term % 4
        offset = phase_term // 4
        for j in range(lagi + 1):
            pos = n * lagi + j - offset
            if 0 <= pos < NSUB:
                candidates[pos].append((j, frac, n))
    assert set(candidates) == set(range(NSUB))
    result = np.empty(NSUB, dtype=np.float64)
    for pos in range(NSUB):
        j, frac, _ = min(candidates[pos], key=lambda item: item[0])
        result[pos] = book[index, frac, j]
    return result


def test_lag_code_conversion() -> None:
    for code in range(256):
        kind, first, second, raw = decode_lag(code)
        assert raw == code
        if code <= 119:
            t = code + 64
            assert (kind, first, second) == ("acb", t // 4, t % 4)
        elif code <= 159:
            t = code - 28
            assert (kind, first, second) == ("acb", t // 2, 1 + 2 * (t & 1))
        elif code <= 190:
            assert (kind, first, second) == ("acb", code - 94, 1)
        elif code <= 254:
            t = code - 191
            assert (kind, first, second) == ("fcb", t // 2, t & 1)
        else:
            assert (kind, first, second) == ("zero", 0, 1)


def test_scb_code_conversion() -> None:
    tx0 = {(source_sign, source_index): (tx_sign, tx_index)
           for source_sign, source_index, tx_sign, tx_index in _SCB0_ROWS}
    tx1 = {(source_sign, source_index): (tx_sign, tx_index)
           for source_sign, source_index, tx_sign, tx_index in _SCB1_ROWS}
    assert len(tx0) == len(tx1) == 32
    for source0, transmitted0 in tx0.items():
        for source1, transmitted1 in tx1.items():
            st0, it0 = transmitted0
            st1, it1 = transmitted1
            code = (st0 << 9) | (st1 << 8) | (it0 << 4) | it1
            i0, s0, i1, s1 = decode_scb_code(code)
            assert (s0, i0) == source0
            assert (s1, i1) == source1


def test_acb_equations_and_priority() -> None:
    rng = np.random.default_rng(0x5051)
    dq = rng.normal(size=98)
    duplicate_cases = 0
    for lagi in range(16, 97):
        for lagf in legal_lagf(lagi):
            expected = acb_reference(dq, lagi, lagf)
            actual = acb_vector(dq, lagi, lagf)
            np.testing.assert_array_equal(actual, expected)

            positions: dict[int, int] = defaultdict(int)
            for n in range(NSUB // lagi + 1):
                phase_term = lagf + n * (lagf - 1)
                offset = phase_term // 4
                for j in range(-1, lagi):
                    pos = n * lagi + j - offset
                    if 0 <= pos < NSUB:
                        positions[pos] += 1
            duplicate_cases += sum(count > 1 for count in positions.values())
    assert duplicate_cases > 0


def test_psi_equation_and_table_coverage() -> None:
    tables = np.load(ROOT / "arib_std27_tables.npz")
    np.testing.assert_array_equal(tables["cfcb"] * 32768.0, np.rint(tables["cfcb"] * 32768.0))
    for scb_name in ("cscb0", "cscb1"):
        np.testing.assert_array_equal(tables[scb_name] * 128.0, np.rint(tables[scb_name] * 128.0))
    for name in ("cscb0", "cscb1"):
        book = tables[name].astype(np.float64)
        for lagi in range(16, 97):
            for lagf in legal_lagf(lagi):
                expected = psi_reference(book, 0, lagi, lagf)
                actual = psi_vector(book, 0, lagi, lagf)
                assert np.all(np.isfinite(expected))
                np.testing.assert_array_equal(actual, expected)
        expected = psi_reference(book, 0, NSUB, 1)
        actual = psi_vector(book, 0, NSUB, 1)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(psi_vector(book, 0, 0, 1), book[0, 1, :])


def active_records(path: Path) -> tuple[list[bytes], int]:
    obj = extract_semc_pdc_audio(path)
    records = [obj.frame_data[i:i + obj.frame_size]
               for i in range(0, len(obj.frame_data), obj.frame_size)]
    active = [record for record in records if record[20:24] in ACTIVE_TRAILERS]
    return active, len(records)


def test_real_clips() -> None:
    for sample in SAMPLES:
        if not sample.exists():
            raise AssertionError(f"missing test clip: {sample}")
        active, nominal = active_records(sample)
        assert nominal == 160
        assert len(active) == 158
        assert all(unpack_record(record, check_crc=False)[1] for record in active)
        with tempfile.TemporaryDirectory() as directory:
            wav_path = Path(directory) / "decoded.wav"
            valid, stored, duration = decode_asf(
                sample,
                wav_path,
                ROOT / "arib_std27_tables.npz",
            )
            assert (valid, stored, duration) == (158, 160, 6.4)
            with wave.open(str(wav_path), "rb") as wav:
                assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (8000, 1, 2)
                assert wav.getnframes() == 51200


def main() -> None:
    test_lag_code_conversion()
    test_scb_code_conversion()
    test_acb_equations_and_priority()
    test_psi_equation_and_table_coverage()
    test_real_clips()

    table_hash = hashlib.sha256((ROOT / "arib_std27_tables.npz").read_bytes()).hexdigest()
    print("Core self-test passed.")
    print("  256/256 lag codes checked")
    print("  1024/1024 two-channel SCB transmission combinations round-tripped")
    print("  all legal ACB lag/fraction combinations matched the normative equation and priority")
    print("  all legal PSI combinations matched the normative equation and table coverage")
    print("  clips 130-134: 158/158 CRC-valid speech records and 6.400-second WAVs")
    print(f"  table SHA-256: {table_hash}")


if __name__ == "__main__":
    main()
