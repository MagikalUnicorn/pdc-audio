from __future__ import annotations

from pathlib import Path
import tempfile
import wave

from decode_sony_asf import decode_asf
from extract_semc_pdc_audio import extract_semc_pdc_audio
from sony_unpack import unpack_record

ROOT = Path(__file__).resolve().parent
SAMPLE_ASF = Path("/mnt/data/Phone Pictures 130.asf")
SUPPLIED_RAW = Path("/mnt/data/SEMC_PDC_AUDIO_130_raw3856(1).bin")


def main() -> None:
    if not SAMPLE_ASF.exists() or not SUPPLIED_RAW.exists():
        raise SystemExit("The supplied sample files are not mounted at their development paths.")

    obj = extract_semc_pdc_audio(SAMPLE_ASF)
    assert obj.payload == SUPPLIED_RAW.read_bytes()
    assert obj.frame_size == 24
    assert obj.nominal_frame_count == 160
    assert obj.video_fps == 5
    assert obj.video_frame_count == 32

    records = [obj.frame_data[i:i + 24] for i in range(0, len(obj.frame_data), 24)]
    active_trailers = {
        bytes.fromhex("1d84537d"),
        bytes.fromhex("2b3853ef"),
        bytes.fromhex("c81653ff"),
    }
    active = [record for record in records if record[20:24] in active_trailers]
    assert len(active) == 158
    assert all(unpack_record(record, check_crc=False)[1] for record in active)

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "test.wav"
        valid, nominal, duration = decode_asf(
            SAMPLE_ASF,
            output,
            ROOT / "arib_std27_tables.npz",
        )
        assert valid == 158
        assert nominal == 160
        assert duration == 6.4
        with wave.open(str(output), "rb") as wav:
            assert wav.getframerate() == 8000
            assert wav.getnchannels() == 1
            assert wav.getsampwidth() == 2
            assert wav.getnframes() == 51200

    print("Self-test passed: extraction, 158 CRC-valid frames, and 6.400-second WAV.")


if __name__ == "__main__":
    main()
