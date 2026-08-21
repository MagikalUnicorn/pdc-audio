# Core decoder conformance audit — v3

This audit compares the error-free speech-decoder path against RCR STD-27 L-E Fascicle 2. It deliberately excludes the optional postfilter.

## Confirmed correction from frozen baseline v2

### ACB duplicate-position priority

Section 5.2.1.8.4.1.1 says that when more than one `(n, j)` pair produces the same adaptive-codebook output position, the decoder must prefer:

1. `j = 0`
2. `j = lagi - 1`
3. `1 <= j <= lagi - 2`
4. `j = -1`

Baseline v2 retained the first value encountered while enumerating `n` and then `j`. That is not equivalent to the specified priority. Across all legal coded pitch lags, 75 of the 191 legal `(lagi, lagf)` combinations can produce a different result under the old rule.

The v3 `acb_vector()` implementation now:

- uses the exact equation range `0 <= n <= floor(NSUB / lagi)`;
- applies the four-level priority explicitly;
- verifies that every one of the 80 output samples is assigned;
- rejects invalid integer/fractional lag combinations instead of silently continuing.

Across clips 130–134, 59–120 ACB subframes per clip use a lag combination for which the correction matters geometrically. Because the excitation and synthesis-filter states are recursive, the numerical difference continues beyond the directly changed boundary samples.

## Other core tightening

### PSI construction

`psi_vector()` now follows Section 5.2.1.8.5.1 literally:

- exact `n` range;
- smaller-`j` precedence for duplicate positions;
- no sample-index clamping;
- complete-output and table-coverage checks.

The old implementation happened to give the same selected PSI samples for the tested legal combinations, but the new form removes non-standard fallback behaviour.

### Exact excitation-table grids

The decimal CFCB values in Table 5.2.1.8-1 uniquely recover values on a Q15 grid: every printed value is within `0.0000005` of an integer divided by 32768. The CSCB values in Table 5.2.1.8-2 similarly recover exactly to a Q7 grid, integer divided by 128.

The v3 table file therefore stores:

- CFCB as exact multiples of `1 / 32768`;
- CSCB0 and CSCB1 as exact multiples of `1 / 128`.

This removes decimal-publication rounding from the excitation vectors. Its numerical effect is tiny compared with the ACB-priority correction, but it is appropriate for a conformance-oriented decoder.

## Automated checks

Run:

```powershell
py .\core_self_test.py
```

The test covers:

- all 256 transmitted ACB/FCB lag codes;
- all 1,024 two-channel SCB index/sign transmission combinations;
- every legal ACB integer/fractional-lag combination against an independent equation implementation;
- every legal PSI combination against an independent equation implementation;
- exact Q15/Q7 excitation table grids;
- extraction, CRC and complete decoding of Phone Pictures 130–134;
- 158 CRC-valid speech frames and a 6.400-second WAV for every clip.

Current table SHA-256:

```text
8a4e39db686f6de86375fc5f735001ea89b54c4736c65dabf9adfe624b5a442f
```

## Numerical change from baseline v2

The decoded floating-point waveforms remain highly correlated with v2 (`0.9990–0.9994`), but the difference RMS is approximately `3.36–4.46%` of each v2 waveform's RMS. This is consistent with a small correction at pitch boundaries propagating through the recursive excitation and synthesis states.

Full per-clip figures are in `core-audit-statistics.json` in the listening-output package.

## Native amplitude versus listening output

Peak normalisation is not part of the speech decoder. The command-line tool retains normalised WAV output by default for convenient listening, but now supports:

```powershell
py .\decode_sony_asf.py `
    "Phone Pictures 130.asf" `
    "Phone Pictures 130 native.wav" `
    --no-normalize `
    --float-npy "Phone Pictures 130 synthesis.npy"
```

- `--no-normalize` writes the decoder's native amplitude with ordinary signed-16-bit saturation.
- `--float-npy` preserves the pre-PCM, float64 synthesis output without rounding or saturation.

## What is not yet proven exact

The decoder should still not be described as bit-exact. The remaining material issues are:

1. **Reset state:** the English codec description does not state a unique initial value for the previous-frame LSP vector or all synthesis memories. The current initial LSP vector is a stable evenly spaced placeholder.
2. **Reference arithmetic:** the implementation uses float64. A manufacturer's fixed-point decoder may specify intermediate word lengths, rounding and saturation that are not present in the English equation text.
3. **Non-excitation table precision:** LSP, power and gain tables currently use the published decimal values. Unlike CFCB and CSCB, they do not reveal an unambiguous coarse binary grid from the printed precision alone.
4. **Official conformance vectors:** no PSI-CELP decoder input/output vector has yet been obtained for sample-by-sample comparison.
5. **Error concealment:** the Sony storage samples are error-free and all CRCs pass. Optional/recommended behaviour for bad frames has not been made bit-exact.

The next core task is therefore to obtain or reconstruct a reference reset state and fixed-point arithmetic model, not to add perceptual filtering.
