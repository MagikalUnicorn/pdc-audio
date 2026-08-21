# Final core-decoder correctness pass — v3.2

> Historical audit imported from `snapshot-v3.2-final-audit`. The complete
> original audit scripts and captured results remain available at that tag.

## Result

No further algorithmic correction was found after the v3 adaptive-codebook priority fix. Version 3.2 deliberately leaves the decoder waveform unchanged from v3/v3.1 and adds a broader independent audit rather than another speculative change.

The error-free core path is internally consistent with the reviewed RCR STD-27 equations for:

- Sony 24-byte record unpacking into `CVin`, protected bits, CRC and unprotected bits;
- protected/unprotected parameter reconstruction;
- LSP reconstruction, stabilization and four-subframe interpolation;
- ACB/FCB and PSI/SCB excitation reconstruction;
- gain and power recovery;
- `1/A(z)` LP synthesis and ACB-state updates.

The optional postfilter remains excluded.

## Additional checks added in v3.2

`final_core_audit.py` performs checks independent of the existing `core_self_test.py`:

1. Every meaningful bit from all 790 speech records is unpacked and repacked, with an exact round trip.
2. Every one of the 790 received CRCs is verified with a second integer-polynomial implementation.
3. All 3,160 decoded subframes are checked for ordered LSPs and stable PARCOR coefficients.
4. The synthesis recurrence is compared against SciPy's independent `lfilter` implementation with equivalent initial conditions.
5. Table dimensions, finite values and exact Q15/Q7 excitation grids are checked.
6. Native float64 output hashes are recorded for clips 130–134.
7. The unresolved previous-frame-LSP reset value is isolated and quantified.

Run both suites:

```console
python core_self_test.py
python final_core_audit.py
```

## Passed results

- Sony record meaningful-bit round trips: **790 / 790**
- CRC checks using the original routine: **790 / 790**
- CRC checks using an independent polynomial routine: **790 / 790**
- Decoded subframes with ordered LSPs and stable LPC filters: **3,160 / 3,160**
- Minimum decoded LSP separation: **0.0199954**
- Maximum absolute PARCOR coefficient: **0.9441621**
- Maximum synthesis-filter cross-check error: **1.65 × 10⁻⁶** in float64 arithmetic
- Original core self-test: all lag mappings, SCB mappings, legal ACB/PSI combinations and five complete clips pass

Exact figures and native waveform hashes are in `final-core-audit-results.json`.

## Remaining limits on an exactness claim

The decoder is now a strong equation-level implementation of the error-free core, but it is still not proven bit-exact against the original PDC reference decoder.

### 1. Initial previous-frame LSP value

RCR STD-27 defines the first subframe by interpolating the previous frame's final LSP vector with the current frame's first LSP vector, but the reviewed English text does not define the reset value of that previous vector. The current decoder uses a stable evenly spaced vector.

Changing only that reset value affects almost entirely the first 40 ms. For clip 130, replacing it with the first decoded LSP vector changes the first-frame RMS by about 28.1%, but the difference after the first frame falls below one part per million of the remaining clip RMS. The uncertainty therefore does not affect the body of the recording, but it prevents a sample-exact claim from sample zero.

### 2. Fixed-point arithmetic

ARIB TR-T1 describes the half-rate master codec as a fixed-point executable. The current implementation is float64 and therefore does not reproduce unknown reference word lengths, rounding and saturation. Native synthesis peaks also exceed signed-16-bit range in some clips, so an official fixed-point implementation's saturation points would matter for exact PCM comparison.

### 3. Published table precision

The fixed and stochastic excitation tables recover cleanly to Q15 and Q7 respectively. The printed LSP, power and gain tables do not expose an equally unambiguous fixed-point grid, so the decoder currently uses their published decimal values.

### 4. No official reference vector

TR-T1 confirms that separate half-rate encoded and decoded reference files and a master codec program existed, but they are not included in the report itself. Until one such pair is obtained, exact output cannot be proven.

### 5. Error concealment

All supplied Sony records pass CRC. Bad-frame masking and parameter replacement are therefore outside the tested path and are not implemented as a conformance feature.

## Baseline decision

Use **v3/v3.1/v3.2 core output as the current baseline**. Version 3.2 does not alter the audio. Further core changes should require one of:

- an official encoded/decoded reference vector;
- the fixed-point master codec or source;
- clear evidence from additional independent Sony recordings;
- a demonstrable discrepancy with a normative equation.
