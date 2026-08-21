# Experimental Sony SO505i PDC / PSI-CELP audio decoder

This is a first working floating-point decoder for the `SEMC PDC-AUDIO` byte array stored in Sony SO505i ASF movies.

## Result for the supplied movie

- ASF duration: 6.400 seconds
- Stored records: 160 × 24 bytes
- Codec records: 158
- Trailing non-codec records: 2 (marker/padding)
- Codec frame duration: 40 ms
- Decoded speech duration: 6.320 seconds
- Output WAV duration: 6.400 seconds after adding 80 ms of trailing silence
- CRC-valid codec records: 158 / 158
- Output format: mono, 8 kHz, signed 16-bit PCM

The implementation is intentionally described as experimental: it omits the optional speech postfilter and is not yet checked against an official bit-exact PDC half-rate conformance vector. The decoded waveform is finite, unclipped after normalization, and has a speech-like spectrogram.


## Correction made after testing clips 131–134

Testing the wider sample set exposed a protected-parameter bit-order error in the first prototype. ARIB Table 5.2.2.2-2 states that, for example, `P[65]` is LSP0 bit 0 (the LSB) and `P[59]` is LSP0 bit 6. The first prototype reconstructed protected parameters in the opposite direction. Version 2 reverses each protected parameter slice before converting it to an integer. Unprotected `NP[x]` parameter slices were already in the correct order.

The v2 decoder successfully processes Phone Pictures 130–134. Each file contains 160 stored records, of which 158 are speech records and the last two are marker/padding records; all 158 speech records pass the 9-bit CRC.

## What was reverse-engineered

The audio is not an ordinary ASF audio stream. It is an ASF extended-content BYTE_ARRAY descriptor named `SEMC PDC-AUDIO`.

The 3,856-byte payload is:

- 16-byte Sony header
- 3,840 bytes of records (`160 × 24`)

Each active 24-byte record contains the standard PDC half-rate information bits rather than the radio-channel convolutionally encoded/interleaved frame:

- 66 protected speech bits
- 9-bit CRC
- 72 unprotected speech bits
- total: 147 meaningful bits

The first 75 bits are the ARIB `CVin[0..74]` sequence (protected bits plus CRC in the standard convolutional-input order). The remaining 72 are `NP[0..71]`.

Sony stores meaningful bits MSB-first inside little-endian 16-bit storage words, with padding around the two logical blocks:

| Storage bytes | Meaningful word bits | Decoded source bits |
|---|---:|---|
| 0–1 | 0–15 | `CVin[0..15]` |
| 2–3 | 0–15 | `CVin[16..31]` |
| 4–5 | 0–15 | `CVin[32..47]` |
| 6–7 | 0–15 | `CVin[48..63]` |
| 8–9 | 5–15 | `CVin[64..74]` |
| 10–11 | 0–13 | `NP[0..13]` |
| 12–13 | 0–15 | `NP[14..29]` |
| 14–15 | 0–15 | `NP[30..45]` |
| 16–17 | 0–15 | `NP[46..61]` |
| 18–19 | 6–15 | `NP[62..71]` |
| 20–23 | — | Sony record trailer, not codec data |

The active record trailers observed across the tested SO505i clips are:

```text
1D 84 53 7D
2B 38 53 EF
9D 84 53 7D
2B 30 53 EF
C8 16 53 FF
```

The first two occur in Phone Pictures 130; the next two occur in Phone Pictures 131–134; `C8 16 53 FF` is shared. The exact purpose of the trailer bits remains unknown.

The 9-bit CRC uses:

```text
G(x) = 1 + x + x² + x⁵ + x⁸ + x⁹
```

All 158 active records pass this CRC after unpacking.

## Requirements

- Python 3.11 or later
- NumPy
- FFmpeg only when creating an MP4 with the recovered audio

Install NumPy in PowerShell:

```powershell
py -m pip install numpy
```

## Decode an ASF directly

From this directory:

```powershell
py .\decode_sony_asf.py `
    "C:\Path\Phone Pictures 130.asf" `
    "C:\Path\Phone Pictures 130 decoded.wav"
```

Create a Windows-friendly MP4 as well (requires `ffmpeg.exe` on `PATH`):

```powershell
py .\decode_sony_asf.py `
    "C:\Path\Phone Pictures 130.asf" `
    "C:\Path\Phone Pictures 130 decoded.wav" `
    --mp4 "C:\Path\Phone Pictures 130 decoded.mp4"
```

PowerShell wrapper:

```powershell
.\Decode-SonyPdcAudio.ps1 `
    -InputAsf "C:\Path\Phone Pictures 130.asf" `
    -OutputWav "C:\Path\Phone Pictures 130 decoded.wav" `
    -OutputMp4 "C:\Path\Phone Pictures 130 decoded.mp4"
```

## Decode the already-extracted 24-byte records

```powershell
py .\sony_unpack.py `
    "C:\Path\SEMC_PDC_AUDIO_130_frames160x24.bin" `
    "C:\Path\decoded.wav" `
    --json "C:\Path\decoded_parameters.json"
```

This lower-level command removes the sample's two known trailing marker records and writes the 6.320-second codec output. `decode_sony_asf.py` is preferred because it pads the WAV to the movie's nominal 6.400-second duration.

## Files

- `decode_sony_asf.py` — end-to-end extraction, decoding, optional MP4 muxing
- `extract_semc_pdc_audio.py` — extracts the ASF BYTE_ARRAY descriptor
- `sony_unpack.py` — Sony record unpacking, CRC validation and parameter reconstruction
- `pdc_decoder.py` — floating-point PDC half-rate / PSI-CELP synthesis decoder
- `arib_std27_tables.npz` — numerical LSP, power, excitation and gain tables
- `Decode-SonyPdcAudio.ps1` — PowerShell wrapper
- `self_test.py` — checks extraction, record count, CRC and output duration against the supplied sample

## Current limitations

1. The optional PDC postfilter has not been implemented.
2. Arithmetic is floating-point rather than the standard's fixed-point reference arithmetic.
3. The code has been validated against five Sony clips, not a wider SO505i corpus.
4. The five currently observed Sony trailer values are recognized empirically. Their exact purpose is still unknown.
5. The decoder needs comparison against official PDC half-rate test vectors before it can be called bit-exact.

FFmpeg's existing CELP-family decoders were useful as implementation references for LSP/LPC conversion, fractional interpolation and the `1/A(z)` synthesis-filter structure, but FFmpeg does not currently contain a PDC half-rate / PSI-CELP decoder or Sony `SEMC PDC-AUDIO` demuxer.
