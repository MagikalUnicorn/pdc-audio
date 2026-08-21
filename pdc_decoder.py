from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import math
import wave
import numpy as np

NSUB = 80
ORDER = 10
S_MAX = 32768.0

# Fractional-delay FIR taps, indexed as W[frac][tap + 4], tap=-4..2.
_W = np.zeros((4, 7), dtype=np.float64)
_W[0] = [-0.06002109, 0.08184694, -0.12861662, 0.30010544, 0.90031632, -0.18006326, 0.10003515]
_W[1] = [0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0]
_W[2] = [0.05295978, -0.06925510, 0.10003515, -0.18006326, 0.90031632, 0.30010544, -0.12861662]
_W[3] = [0.07073553, -0.09094568, 0.12732395, -0.21220659, 0.63661977, 0.63661977, -0.21220659]

# Inverse of Tables 5.2.2.1-1 and 5.2.2.1-2.
_INV_SCB0: dict[tuple[int, int], tuple[int, int]] = {}
_INV_SCB1: dict[tuple[int, int], tuple[int, int]] = {}

_SCB0_ROWS = [
    (0,0,1,1),(0,1,0,6),(0,2,1,14),(0,3,1,12),(0,4,0,4),(0,5,0,5),(0,6,0,9),(0,7,0,8),
    (0,8,0,1),(0,9,0,11),(0,10,0,10),(0,11,1,13),(0,12,1,5),(0,13,1,10),(0,14,1,8),(0,15,0,15),
    (1,0,0,13),(1,1,0,12),(1,2,0,14),(1,3,1,9),(1,4,1,11),(1,5,1,3),(1,6,1,6),(1,7,1,4),
    (1,8,1,7),(1,9,1,2),(1,10,1,0),(1,11,0,7),(1,12,0,3),(1,13,0,0),(1,14,0,2),(1,15,1,15),
]
_SCB1_ROWS = [
    (0,0,0,0),(0,1,0,1),(0,2,1,8),(0,3,1,9),(0,4,1,13),(0,5,1,7),(0,6,0,6),(0,7,1,3),
    (0,8,1,14),(0,9,1,0),(0,10,0,8),(0,11,0,11),(0,12,0,15),(0,13,0,7),(0,14,1,15),(0,15,0,12),
    (1,0,1,12),(1,1,1,4),(1,2,0,10),(1,3,0,14),(1,4,0,4),(1,5,0,5),(1,6,1,5),(1,7,0,13),
    (1,8,0,2),(1,9,0,3),(1,10,1,10),(1,11,1,11),(1,12,1,1),(1,13,1,6),(1,14,0,9),(1,15,1,2),
]
for ss, ii, st, it in _SCB0_ROWS:
    _INV_SCB0[(st, it)] = (ss, ii)
for ss, ii, st, it in _SCB1_ROWS:
    _INV_SCB1[(st, it)] = (ss, ii)

@dataclass(slots=True)
class PDCFrameParameters:
    lsp0: int
    lsp1: int
    lsp2: int
    lsp3: int
    power: int
    lag: tuple[int, int, int, int]
    code: tuple[int, int, int, int]
    gain: tuple[int, int, int, int]

    def validate(self) -> None:
        ranges = [
            ('lsp0', self.lsp0, 128), ('lsp1', self.lsp1, 256),
            ('lsp2', self.lsp2, 256), ('lsp3', self.lsp3, 256),
            ('power', self.power, 128),
        ]
        for name, value, limit in ranges:
            if not 0 <= value < limit:
                raise ValueError(f'{name}={value} out of range')
        for i, v in enumerate(self.lag):
            if not 0 <= v < 256: raise ValueError(f'lag[{i}]={v} out of range')
        for i, v in enumerate(self.code):
            if not 0 <= v < 1024: raise ValueError(f'code[{i}]={v} out of range')
        for i, v in enumerate(self.gain):
            if not 0 <= v < 128: raise ValueError(f'gain[{i}]={v} out of range')


def _stabilize_lsp(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64).copy()
    if v[2] - v[1] < 0.02:
        v[2] = v[1] + 0.02
    for i in (3, 4, 5):
        if v[i] - v[i-1] < 0.02:
            avg = 0.5 * (v[i] + v[i-1])
            v[i-1] = avg - 0.01
            v[i] = avg + 0.01
    if v[6] - v[5] < 0.02:
        v[5] = v[6] - 0.02
    if v[5] < v[4]:
        v[4], v[5] = v[5], v[4]
    return v


def decode_lsp_pair(p: PDCFrameParameters, tables: dict[str, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    low = tables['clspl'][p.lsp0]
    high = tables['clsph'][p.lsp3]
    middle = tables['clspm1'][p.lsp1].copy()
    theta = np.array([1.0 if (p.lsp2 >> j) & 1 else -1.0 for j in range(8)])
    middle += theta @ tables['clspm2']

    q1 = np.empty(10, dtype=np.float64)
    q3 = np.empty(10, dtype=np.float64)
    q1[0:2] = low[0:2]
    q3[0:2] = low[2:4]
    q1[2] = middle[0] + q1[1]
    q1[3:6] = middle[1:4]
    q3[2] = middle[4] + q3[1]
    q3[3:6] = middle[5:8]
    q1[6:10] = high[0:4]
    q3[6:10] = high[4:8]
    return _stabilize_lsp(q1), _stabilize_lsp(q3)


def lsp_to_lpc(lsp: np.ndarray) -> np.ndarray:
    """Convert 10 normalized LSP frequencies (0..1, where 1=pi) to A(z)."""
    w = np.pi * np.asarray(lsp, dtype=np.float64)
    p = np.array([1.0])
    q = np.array([1.0])
    for angle in w[0::2]:
        p = np.convolve(p, [1.0, -2.0 * math.cos(float(angle)), 1.0])
    for angle in w[1::2]:
        q = np.convolve(q, [1.0, -2.0 * math.cos(float(angle)), 1.0])
    pp = np.convolve(p, [1.0, 1.0])
    qq = np.convolve(q, [1.0, -1.0])
    a = 0.5 * (pp + qq)
    # The degree-11 term cancels analytically.
    return a[:11] / a[0]


def lpc_to_parcor(a: np.ndarray) -> np.ndarray:
    coeff = np.asarray(a, dtype=np.float64)[1:].copy()
    order = len(coeff)
    k = np.zeros(order, dtype=np.float64)
    for m in range(order, 0, -1):
        km = coeff[m-1]
        k[m-1] = km
        den = 1.0 - km * km
        if den <= 1e-10:
            return np.full(order, np.nan)
        if m > 1:
            old = coeff[:m-1].copy()
            coeff[:m-1] = (old - km * old[::-1]) / den
    return k


def decode_lag(code: int) -> tuple[str, int, int, int]:
    """Return (kind, lagi_or_ifcb, lagf_or_sign, raw)."""
    if code <= 119:
        t = code + 64
        return 'acb', t // 4, t % 4, code
    if code <= 159:
        t = code - 28
        return 'acb', t // 2, 1 + 2 * (t & 1), code
    if code <= 190:
        return 'acb', code - 94, 1, code
    if code <= 254:
        t = code - 191
        return 'fcb', t // 2, t & 1, code
    return 'zero', 0, 1, code


def decode_scb_code(code: int) -> tuple[int, int, int, int]:
    st0 = (code >> 9) & 1
    st1 = (code >> 8) & 1
    it0 = (code >> 4) & 15
    it1 = code & 15
    try:
        ss0, i0 = _INV_SCB0[(st0, it0)]
        ss1, i1 = _INV_SCB1[(st1, it1)]
    except KeyError as exc:
        raise ValueError(f'invalid SCB transmission code {code}') from exc
    return i0, ss0, i1, ss1


def _dq_get(dq: np.ndarray, idx: int) -> float:
    return float(dq[idx]) if 0 <= idx < len(dq) else 0.0


def _dq_interp(dq: np.ndarray, lagi: int, j: int, frac: int) -> float:
    if j <= lagi - 3:
        shift = 0
        wshift = 0
    elif j == lagi - 2:
        shift = -1
        wshift = -1
    else:
        shift = -2
        wshift = -2
    s = 0.0
    for kk in range(-2, 3):
        di = len(dq) - lagi + j + kk + shift
        wi = kk + wshift
        s += _dq_get(dq, di) * _W[frac, wi + 4]
    return s


def acb_vector(dq: np.ndarray, lagi: int, lagf: int) -> np.ndarray:
    """Decode one ACB vector exactly as RCR STD-27 Eq. 5.2.1.8.4.1.1-2/-3.

    When two ``(n, j)`` combinations address the same output sample, the
    standard mandates this priority: ``j=0``; ``j=lagi-1``; interior ``j``;
    then ``j=-1``.  This is significant at pitch-period boundaries.
    """
    if not 16 <= lagi <= 96:
        raise ValueError(f"ACB integer lag {lagi} is outside the coded range 16..96")
    allowed_lagf = (0, 1, 2, 3) if lagi <= 45 else ((1, 3) if lagi <= 65 else (1,))
    if lagf not in allowed_lagf:
        raise ValueError(f"fractional lag code {lagf} is invalid for integer lag {lagi}")

    def priority(j: int) -> int:
        if j == 0:
            return 0
        if j == lagi - 1:
            return 1
        if 1 <= j <= lagi - 2:
            return 2
        if j == -1:
            return 3
        raise AssertionError(f"unexpected ACB interpolation index j={j}")

    out = np.zeros(NSUB, dtype=np.float64)
    selected_priority = np.full(NSUB, 99, dtype=np.int8)

    for n in range(NSUB // lagi + 1):
        phase_term = lagf + n * (lagf - 1)
        frac = phase_term % 4
        offset = phase_term // 4
        for j in range(-1, lagi):
            pos = n * lagi + j - offset
            if not 0 <= pos < NSUB:
                continue
            candidate_priority = priority(j)
            if candidate_priority < selected_priority[pos]:
                out[pos] = _dq_interp(dq, lagi, j, frac)
                selected_priority[pos] = candidate_priority

    missing = np.flatnonzero(selected_priority == 99)
    if len(missing):
        raise RuntimeError(f"RCR STD-27 ACB equations did not assign output samples {missing.tolist()}")
    return out


def fcb_vector(cfcb: np.ndarray, index: int, sign_bit: int) -> np.ndarray:
    n = index // 8
    i = index % 8
    out = np.array([cfcb[n, (k + 10 * i) % 80] for k in range(80)], dtype=np.float64)
    # S_FCB=0 for positive selected vector, 1 for negative.
    return -out if sign_bit else out


def psi_vector(book: np.ndarray, index: int, lagi: int, lagf: int) -> np.ndarray:
    """Apply the PSI repetition in RCR STD-27 Eq. 5.2.1.8.5.1-1."""
    if not 0 <= index < book.shape[0]:
        raise ValueError(f"SCB index {index} is outside the codebook")
    if lagi == 0:
        # With PSI disabled, phase 1 is the unshifted stored stochastic vector.
        return np.array(book[index, 1, :], dtype=np.float64)
    if not 16 <= lagi <= 96:
        raise ValueError(f"PSI integer lag {lagi} is outside 16..96")

    out = np.zeros(NSUB, dtype=np.float64)
    selected_j = np.full(NSUB, 127, dtype=np.int16)
    for n in range(NSUB // lagi + 1):
        phase_term = 1 + n * (lagf - 1)
        frac = phase_term % 4
        offset = phase_term // 4
        for j in range(0, lagi + 1):
            pos = n * lagi + j - offset
            if not 0 <= pos < NSUB:
                continue
            if j >= book.shape[2]:
                raise RuntimeError(f"PSI requested unavailable stored-vector sample j={j}")
            # The standard gives the smaller j precedence for duplicate positions.
            if j < selected_j[pos]:
                value = float(book[index, frac, j])
                if not math.isfinite(value):
                    raise RuntimeError(
                        f"SCB table has no value for index={index}, phase={frac}, j={j}"
                    )
                out[pos] = value
                selected_j[pos] = j

    missing = np.flatnonzero(selected_j == 127)
    if len(missing):
        raise RuntimeError(f"RCR STD-27 PSI equation did not assign output samples {missing.tolist()}")
    return out


def scb_vector(cscb0: np.ndarray, cscb1: np.ndarray, code: int, lagi: int, lagf: int) -> np.ndarray:
    i0, s0, i1, s1 = decode_scb_code(code)
    v0 = psi_vector(cscb0, i0, lagi, lagf)
    v1 = psi_vector(cscb1, i1, lagi, lagf)
    # Sign bit 0 means positive, 1 means negative.
    return (-v0 if s0 else v0) + (-v1 if s1 else v1)


class PDCDecoder:
    def __init__(self, table_file: str | Path):
        z = np.load(table_file)
        self.tables = {k: z[k].astype(np.float64) for k in z.files}
        self.prev_lsp3 = np.linspace(0.05, 0.95, 10, dtype=np.float64)
        self.dq = np.zeros(98, dtype=np.float64)
        # Previous synthesis-filter outputs, oldest to newest.
        self.synth_history = np.zeros(ORDER, dtype=np.float64)

    def decode_frame(self, p: PDCFrameParameters) -> np.ndarray:
        p.validate()
        q1, q3 = decode_lsp_pair(p, self.tables)
        sub_lsp = [0.5 * (self.prev_lsp3 + q1), q1, 0.5 * (q1 + q3), q3]
        power_mu = self.tables['cpow'][p.power]
        rspow = (S_MAX * (np.power(101.0, power_mu) - 1.0) / 100.0) ** 2
        spow = rspow * 1.44
        pcm = []
        for sf in range(4):
            a = lsp_to_lpc(sub_lsp[sf])
            k = lpc_to_parcor(a)
            if not np.all(np.isfinite(k)) or np.any(np.abs(k) >= 1.0):
                raise ValueError(f'unstable LPC in subframe {sf}: {k}')
            kind, x, y, _ = decode_lag(p.lag[sf])
            if kind == 'acb':
                lagi, lagf = x, y
                c0 = acb_vector(self.dq, lagi, lagf)
            elif kind == 'fcb':
                index, sign = x, y
                lagi, lagf = 80, 1
                c0 = fcb_vector(self.tables['cfcb'], index, sign)
            else:
                lagi, lagf = 0, 1
                c0 = np.zeros(NSUB, dtype=np.float64)
            c1 = scb_vector(self.tables['cscb0'], self.tables['cscb1'], p.code[sf], lagi, lagf)
            rs = NSUB * spow[sf] * float(np.prod(1.0 - k * k))
            pow0 = float(np.dot(c0, c0))
            pow1 = float(np.dot(c1, c1))
            gidx = p.gain[sf]
            g0 = math.sqrt(max(rs, 0.0) / max(pow0, 1e-20)) * self.tables['cgain'][gidx, 0]
            g1 = math.sqrt(max(rs, 0.0) / max(pow1, 1e-20)) * self.tables['cgain'][gidx, 1]
            ex = g0 * c0 + g1 * c1
            # Apply the CELP LP synthesis filter 1/A(z). This is the same
            # recurrence used by FFmpeg's generic CELP synthesis primitive.
            sq = np.empty(NSUB, dtype=np.float64)
            history = self.synth_history
            for sample_index, excitation_sample in enumerate(ex):
                synthesized = float(excitation_sample - np.dot(a[1:], history[::-1]))
                sq[sample_index] = synthesized
                history[:-1] = history[1:]
                history[-1] = synthesized
            pcm.append(sq)
            self.dq[:18] = self.dq[80:98]
            self.dq[18:98] = ex
        self.prev_lsp3 = q3.copy()
        return np.concatenate(pcm)

    def decode(self, frames: Iterable[PDCFrameParameters]) -> np.ndarray:
        return np.concatenate([self.decode_frame(f) for f in frames])


def write_wav(path: str | Path, samples: np.ndarray, sample_rate: int = 8000, normalize: bool = False) -> None:
    x = np.asarray(samples, dtype=np.float64)
    if normalize:
        peak = float(np.max(np.abs(x))) if len(x) else 0.0
        if peak > 0:
            x = x * (30000.0 / peak)
    y = np.clip(np.rint(x), -32768, 32767).astype('<i2')
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(y.tobytes())
