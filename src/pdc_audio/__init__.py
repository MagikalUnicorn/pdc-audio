"""PDC-Audio package metadata and bundled decoder resources."""

from pathlib import Path

__version__ = "3.3.0"
DEFAULT_TABLES = Path(__file__).with_name("arib_std27_tables.npz")

__all__ = ["DEFAULT_TABLES", "__version__"]
