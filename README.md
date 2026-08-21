# Sony SO505i PDC / PSI-CELP decoder — v3.3 final ASF workflow

This package decodes the Sony SO505i `SEMC PDC-AUDIO` byte array and can create a new playable ASF that contains:

- the original MJPEG video packets, copied without re-encoding;
- decoded mono 8 kHz 16-bit PCM audio;
- the original `SEMC PDC-AUDIO` ASF `BYTE_ARRAY` descriptor, copied byte-for-byte.

The original source ASF is never modified. The default PowerShell command writes a new file beside it.

## Requirements

- Windows 11 PowerShell
- Python 3.11 or later
- NumPy
- FFmpeg on `PATH`, or supplied with `-Ffmpeg`

Install NumPy:

```powershell
py -m pip install -r .\requirements.txt
```

## Simplest PowerShell use

From this package directory:

```powershell
.\Convert-SonySo505iPdcAudio.ps1 `
    -InputAsf "C:\Videos\Phone Pictures 130.asf"
```

With no explicit output options, this creates:

```text
C:\Videos\Phone Pictures 130 - decoded PDC.asf
```

That output contains the copied MJPEG stream, decoded PCM audio, and the original binary attachment.

## Choose an output path

```powershell
.\Convert-SonySo505iPdcAudio.ps1 `
    -InputAsf "C:\Videos\Phone Pictures 130.asf" `
    -OutputAsf "C:\Videos\Phone Pictures 130 restored.asf"
```

Use `-Force` to replace an existing output file. The script still refuses to overwrite the source ASF.

## Also keep the decoded WAV and parameter dump

```powershell
.\Convert-SonySo505iPdcAudio.ps1 `
    -InputAsf "C:\Videos\Phone Pictures 130.asf" `
    -OutputAsf "C:\Videos\Phone Pictures 130 restored.asf" `
    -OutputWav "C:\Videos\Phone Pictures 130 decoded.wav" `
    -ParameterJson "C:\Videos\Phone Pictures 130 parameters.json"
```

The historical wrapper name remains available:

```powershell
.\Decode-SonyPdcAudio.ps1 -InputAsf "C:\Videos\Phone Pictures 130.asf"
```

## Batch conversion

```powershell
Get-ChildItem "C:\Videos" -Filter "*.asf" | ForEach-Object {
    $output = Join-Path $_.DirectoryName ($_.BaseName + " - decoded PDC.asf")
    .\Convert-SonySo505iPdcAudio.ps1 `
        -InputAsf $_.FullName `
        -OutputAsf $output
}
```

## Verification performed by default

After creating the ASF, the tool verifies:

1. the source and output video packet SHA-256 hashes are identical;
2. the temporary decoded WAV and output PCM packet SHA-256 hashes are identical;
3. the complete `SEMC PDC-AUDIO` descriptor entry is byte-for-byte identical.

Use `-SkipVerification` only when speed matters more than the final integrity pass.

## Direct Python use

```powershell
py .\decode_sony_asf.py `
    "C:\Videos\Phone Pictures 130.asf" `
    --asf "C:\Videos\Phone Pictures 130 restored.asf"
```

Optional outputs:

```text
--wav PATH          decoded PCM WAV
--json PATH         decoded parameter dump
--float-npy PATH    lossless float64 synthesis array
--mp4 PATH          H.264/AAC listening copy
--no-normalize      native decoder amplitude with 16-bit saturation
--no-verify         skip ASF integrity verification
--force             replace existing outputs
--ffmpeg PATH       explicit ffmpeg.exe path
```

## End-to-end self-test

Run against one original Sony clip:

```powershell
py .\asf_integration_test.py `
    "C:\Videos\Phone Pictures 130.asf"
```

The test creates temporary files and checks decoding, MJPEG packet identity, PCM packet identity, and exact attachment preservation.

## Production files

- `Convert-SonySo505iPdcAudio.ps1` — primary Windows PowerShell entry point
- `Decode-SonyPdcAudio.ps1` — compatibility wrapper
- `decode_sony_asf.py` — decode and container workflow
- `preserve_semc_pdc_attachment.py` — exact ASF descriptor preservation
- `extract_semc_pdc_audio.py` — Sony ASF binary-object extraction
- `sony_unpack.py` — Sony 24-byte record unpacking and CRC validation
- `pdc_decoder.py` — v3 audited PDC half-rate / PSI-CELP synthesis core
- `arib_std27_tables.npz` — decoder tables
- `asf_integration_test.py` — portable end-to-end test

## Decoder status

The core is the frozen v3 decoder after the final equation-level audit. No waveform change was made for v3.3; this release adds the integrated ASF-preserving workflow and verification.

It is a strong error-free floating-point implementation, but not formally claimed to be sample-for-sample bit-exact with the historical fixed-point master codec. The remaining blockers are the unavailable official conformance vectors, exact fixed-point arithmetic details, and the first-frame reset state.

See `FINAL_CORE_AUDIT.md` and `FFMPEG_INTEGRATION.md` for the detailed technical assessment.
