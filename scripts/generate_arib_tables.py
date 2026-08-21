"""Generate local decoder tables from the supported official ARIB PDF."""

from __future__ import annotations

from pathlib import Path
import argparse
import hashlib
import re
import shutil
import subprocess
import sys

import numpy as np

from _common import REPOSITORY_ROOT


SUPPORTED_PDF_SHA256 = (
    "d45bf76f02e3fbb927150e104a608c8fcee5015efd140323d820dd6505a703fb"
)
EXPECTED_TABLE_DIGEST = (
    "bb92c04f5756092124d4cfea770d304bbef0249a65e3164a61f6f1f32ba244c0"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT.parent
    / "pdc-audio-media"
    / "generated"
    / "arib_std27_tables.npz"
)
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
CSCB_HEADER = re.compile(
    r"CSCB([01])\(\s*(\d+)\s*,\s*(\d+)\s*,\s*k\s*\)"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _find_pdftotext(override: str | None) -> str:
    if override:
        discovered = shutil.which(override)
        if discovered:
            return discovered
        candidate = Path(override).expanduser()
        if candidate.is_file():
            return str(candidate.resolve())
        raise FileNotFoundError(f"pdftotext was not found: {override}")

    discovered = shutil.which("pdftotext")
    if discovered:
        return discovered

    candidates = [Path(sys.executable).with_name("pdftotext.exe")]
    for parent in (REPOSITORY_ROOT, *REPOSITORY_ROOT.parents):
        candidates.append(parent / "mingw64" / "bin" / "pdftotext.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    raise FileNotFoundError(
        "pdftotext is unavailable; install mingw-w64-x86_64-poppler or pass "
        "--pdftotext"
    )


def _extract_text(pdftotext: str, pdf: Path, first: int, last: int) -> str:
    result = subprocess.run(
        [
            pdftotext,
            "-f",
            str(first),
            "-l",
            str(last),
            "-layout",
            str(pdf),
            "-",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def _numeric_rows(text: str, width: int) -> tuple[list[int], np.ndarray]:
    indices: list[int] = []
    rows: list[list[float]] = []
    for line in text.splitlines():
        fields = line.split()
        # A single value in the supported PDF has an internal text-object gap
        # (for example ``0.15 29584``). Join decimal fragments without making
        # any assumption about the value itself.
        while len(fields) > width + 1:
            fragment = next(
                (
                    position
                    for position in range(1, len(fields) - 1)
                    if re.fullmatch(r"[+-]?\d+\.\d+", fields[position])
                    and fields[position + 1].isdigit()
                ),
                None,
            )
            if fragment is None:
                break
            fields[fragment] += fields.pop(fragment + 1)
        if len(fields) != width + 1 or not fields[0].isdigit():
            continue
        try:
            values = [float(value) for value in fields[1:]]
        except ValueError:
            continue
        indices.append(int(fields[0]))
        rows.append(values)
    return indices, np.asarray(rows, dtype=np.float64)


def _indexed_table(
    pdftotext: str,
    pdf: Path,
    pages: tuple[int, int],
    row_count: int,
    column_groups: int = 1,
    width: int = 4,
) -> np.ndarray:
    indices, values = _numeric_rows(
        _extract_text(pdftotext, pdf, *pages),
        width=width,
    )
    expected_indices = list(range(row_count)) * column_groups
    if indices != expected_indices:
        raise ValueError(
            f"unexpected rows on PDF pages {pages[0]}-{pages[1]}: "
            f"found {len(indices)}, expected {len(expected_indices)}"
        )
    groups = np.split(values, column_groups)
    return np.concatenate(groups, axis=1)


def _stochastic_codebooks(pdftotext: str, pdf: Path) -> tuple[np.ndarray, np.ndarray]:
    text = _extract_text(pdftotext, pdf, 591, 630)
    pages = [page for page in text.split("\f") if page.strip()]
    if len(pages) != 40:
        raise ValueError(f"expected 40 CSCB table pages, found {len(pages)}")

    books = {
        0: np.zeros((16, 4, 80), dtype=np.float64),
        1: np.zeros((16, 4, 80), dtype=np.float64),
    }
    populated = {
        0: np.zeros((16, 4, 80), dtype=np.bool_),
        1: np.zeros((16, 4, 80), dtype=np.bool_),
    }
    assignments: set[tuple[int, int, int]] = set()
    previous_headers: list[tuple[int, int, int]] | None = None
    for page_number, page in enumerate(pages, 591):
        headers = [tuple(map(int, match)) for match in CSCB_HEADER.findall(page)]
        if not headers and previous_headers is not None:
            headers = previous_headers
        elif len(headers) == 4:
            previous_headers = headers
        else:
            raise ValueError(
                f"expected four CSCB headers on PDF page {page_number}, "
                f"found {len(headers)}"
            )
        bank = headers[0][0]
        subframe = headers[0][2]
        codewords = [header[1] for header in headers]
        if any(header[0] != bank or header[2] != subframe for header in headers):
            raise ValueError(f"inconsistent CSCB headers on PDF page {page_number}")
        if codewords != list(range(codewords[0], codewords[0] + 4)):
            raise ValueError(f"non-consecutive CSCB headers on PDF page {page_number}")

        indices, values = _numeric_rows(page, width=4)
        if not indices or indices != list(range(indices[0], indices[-1] + 1)):
            raise ValueError(
                f"unexpected CSCB rows on PDF page {page_number}: found {len(indices)}"
            )
        # The standard prints six decimal places for values defined on a 1/128 grid.
        values = np.rint(values * 128.0) / 128.0
        for column, codeword in enumerate(codewords):
            assignment = (bank, codeword, subframe)
            assignments.add(assignment)
            if populated[bank][codeword, subframe, indices].any():
                raise ValueError(f"overlapping CSCB assignment {assignment}")
            books[bank][codeword, subframe, indices] = values[:, column]
            populated[bank][codeword, subframe, indices] = True

    if len(assignments) != 128:
        raise ValueError(f"expected 128 CSCB assignments, found {len(assignments)}")
    expected_lengths = (41, 80, 40, 39)
    for bank in (0, 1):
        actual_lengths = populated[bank].sum(axis=2)
        expected = np.tile(expected_lengths, (16, 1))
        if not np.array_equal(actual_lengths, expected):
            raise ValueError(f"incomplete CSCB{bank} table coverage")
    return books[0], books[1]


def _canonical_digest(tables: dict[str, np.ndarray]) -> str:
    digest = hashlib.sha256()
    for name in TABLE_ORDER:
        digest.update(name.encode("ascii") + b"\0")
        digest.update(np.asarray(tables[name], dtype="<f8").tobytes())
    return digest.hexdigest()


def extract_tables(pdftotext: str, pdf: Path) -> dict[str, np.ndarray]:
    """Extract and validate the decoder arrays from the supported PDF edition."""
    cfcb_rows = _indexed_table(pdftotext, pdf, (589, 590), 80)
    cscb0, cscb1 = _stochastic_codebooks(pdftotext, pdf)
    tables = {
        "clspl": _indexed_table(pdftotext, pdf, (549, 551), 128),
        "clsph": _indexed_table(pdftotext, pdf, (552, 563), 256, 2),
        "clspm1": _indexed_table(pdftotext, pdf, (564, 575), 256, 2),
        "clspm2": _indexed_table(pdftotext, pdf, (576, 576), 8, 2),
        "cpow": _indexed_table(pdftotext, pdf, (577, 579), 128),
        # CFCB is printed by sample index and on a 1/32768 grid.
        "cfcb": (np.rint(cfcb_rows * 32768.0) / 32768.0).T,
        "cscb0": cscb0,
        "cscb1": cscb1,
        "cgain": _indexed_table(pdftotext, pdf, (631, 633), 128, width=2),
    }
    digest = _canonical_digest(tables)
    if digest != EXPECTED_TABLE_DIGEST:
        raise ValueError(
            "the extracted tables failed their numerical integrity check: "
            f"{digest}"
        )
    return tables


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="official RCR STD-27 L-E Fascicle 2 PDF")
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"generated NPZ path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument("--pdftotext", help="pdftotext executable name or path")
    args = parser.parse_args()

    pdf = args.pdf.expanduser().resolve()
    if not pdf.is_file():
        parser.error(f"the standards PDF does not exist: {pdf}")
    pdf_digest = _sha256(pdf)
    if pdf_digest != SUPPORTED_PDF_SHA256:
        parser.error(
            "this extractor supports the official RCR STD-27 L-E Fascicle 2 "
            f"PDF with SHA-256 {SUPPORTED_PDF_SHA256}; received {pdf_digest}"
        )

    try:
        pdftotext = _find_pdftotext(args.pdftotext)
        tables = extract_tables(pdftotext, pdf)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError) as error:
        parser.error(str(error))

    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp.npz")
    np.savez(temporary, **tables)
    temporary.replace(output)
    print(f"Generated decoder tables: {output}")
    print(f"Canonical table SHA-256: {EXPECTED_TABLE_DIGEST}")


if __name__ == "__main__":
    main()
