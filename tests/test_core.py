from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import hashlib
import unittest

import numpy as np

from pdc_audio import DEFAULT_TABLES
from pdc_audio.decode_mova_asf import _decode_frames
from pdc_audio.pdc_decoder import (
    NSUB,
    PDCDecoder,
    PDCFrameParameters,
    _SCB0_ROWS,
    _SCB1_ROWS,
    _dq_interp,
    acb_vector,
    decode_lag,
    decode_scb_code,
    psi_vector,
)
from pdc_audio.semc_pdc_records import strip_terminal_records


TABLE_ORDER = (
    "clspl",
    "clsph",
    "clspm1",
    "clspm2",
    "cpow",
    "cfcb",
    "cscb0",
    "cscb1",
    "cgain",
)
EXPECTED_TABLE_DIGEST = (
    "bb92c04f5756092124d4cfea770d304bbef0249a65e3164a61f6f1f32ba244c0"
)


def table_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with np.load(path) as tables:
        if tuple(tables.files) != TABLE_ORDER:
            raise AssertionError(f"unexpected decoder table keys: {tables.files}")
        for name in TABLE_ORDER:
            digest.update(name.encode("ascii") + b"\0")
            digest.update(np.asarray(tables[name], dtype="<f8").tobytes())
    return digest.hexdigest()


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


def check_lag_code_conversion() -> None:
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


def check_scb_code_conversion() -> None:
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


def check_acb_equations_and_priority() -> None:
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


def check_psi_equation_and_table_coverage() -> None:
    tables = np.load(DEFAULT_TABLES)
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


class CoreDecoderTests(unittest.TestCase):
    def test_lag_codes(self) -> None:
        check_lag_code_conversion()

    def test_scb_codes(self) -> None:
        check_scb_code_conversion()

    def test_acb_equations(self) -> None:
        check_acb_equations_and_priority()

    def test_psi_equations(self) -> None:
        check_psi_equation_and_table_coverage()

    def test_generated_tables_and_complete_frame(self) -> None:
        self.assertEqual(table_digest(DEFAULT_TABLES), EXPECTED_TABLE_DIGEST)

        frame = PDCFrameParameters(
            lsp0=0,
            lsp1=0,
            lsp2=0,
            lsp3=0,
            power=0,
            lag=(255, 255, 255, 255),
            code=(0, 0, 0, 0),
            gain=(0, 0, 0, 0),
        )
        decoded = PDCDecoder(DEFAULT_TABLES).decode([frame])
        self.assertEqual(decoded.shape, (320,))
        self.assertTrue(np.all(np.isfinite(decoded)))

    def test_terminal_records_do_not_require_an_active_trailer_whitelist(self) -> None:
        speech = bytes.fromhex("01" + "00" * 19 + "11223344")
        marker = bytes.fromhex("00" * 19 + "30" + "00005300")
        padding = bytes(24)
        self.assertEqual(strip_terminal_records([speech, marker, padding]), [speech])

        # Trailer bytes are outside the 147 meaningful codec bits. A valid frame with
        # a previously unseen trailer must therefore pass the complete decode path.
        crc_valid_speech = bytes(20) + bytes.fromhex("11223344")
        obj = SimpleNamespace(
            frame_size=24,
            frame_data=crc_valid_speech + marker + padding,
        )
        with patch("pdc_audio.decode_mova_asf.extract_semc_pdc_audio", return_value=obj):
            samples, report, active, stored, duration = _decode_frames(
                Path("unused.asf"), DEFAULT_TABLES
            )
        self.assertEqual((active, stored, duration), (1, 3, 0.12))
        self.assertEqual(samples.shape, (320,))
        self.assertEqual(len(report), 1)


def main() -> None:
    result = unittest.main(exit=False)
    if not result.result.wasSuccessful():
        raise SystemExit(1)
    print(f"Canonical decoder table SHA-256: {table_digest(DEFAULT_TABLES)}")


if __name__ == "__main__":
    main()
