"""PDC-Audio package metadata and local decoder resource discovery."""

from pathlib import Path
import os

__version__ = "3.3.0"
DEFAULT_TABLES = Path(
    os.environ.get(
        "PDC_AUDIO_TABLES",
        Path.home()
        / "pdc-audio-media"
        / "generated"
        / "arib_std27_tables.npz",
    )
).expanduser()

__all__ = ["DEFAULT_TABLES", "__version__"]
