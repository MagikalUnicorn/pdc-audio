from __future__ import annotations

from pathlib import Path
import argparse
import tempfile

from decode_sony_asf import decode_asf, mux_asf_preserving_original
from preserve_semc_pdc_attachment import verify_preserved_attachment


def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end test of decoded PCM insertion and ASF preservation"
    )
    parser.add_argument("input", type=Path, help="Sony SO505i ASF test clip")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="sony-pdc-integration-test-") as directory:
        temp = Path(directory)
        wav = temp / "decoded.wav"
        output = temp / "output.asf"
        active, stored, duration = decode_asf(
            args.input,
            wav,
            root / "arib_std27_tables.npz",
        )
        verification = mux_asf_preserving_original(
            args.input,
            wav,
            output,
            ffmpeg_command=args.ffmpeg,
            verify=True,
        )
        verify_preserved_attachment(args.input, output)

        if active <= 0 or stored < active or duration <= 0:
            raise AssertionError("invalid decoder summary")
        if not verification.get("mjpeg_sha256") or not verification.get("pcm_sha256"):
            raise AssertionError("missing stream verification hashes")

    print("ASF integration test passed.")
    print(f"  CRC-valid speech records: {active}/{stored}")
    print(f"  duration: {duration:.3f} seconds")
    print(f"  MJPEG SHA-256: {verification['mjpeg_sha256']}")
    print(f"  PCM SHA-256:   {verification['pcm_sha256']}")
    print("  SEMC PDC-AUDIO: byte-for-byte identical")


if __name__ == "__main__":
    main()
