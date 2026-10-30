"""Extract text from the ReportLab letters. Standard library only.

These PDFs are compressed text (ASCII85 + Flate), not scans. A scanned page
would come back empty; this module does not OCR.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path
from typing import Any


def _ascii85_decode(data: bytes) -> bytes:
    data = re.sub(rb"\s+", b"", data)
    if data.endswith(b"~>"):
        data = data[:-2]
    out = bytearray()
    i = 0
    while i < len(data):
        if data[i : i + 1] == b"z":
            out.extend(b"\x00" * 4)
            i += 1
            continue
        chunk = data[i : i + 5]
        i += len(chunk)
        pad = 5 - len(chunk)
        if pad:
            chunk += b"u" * pad
        value = 0
        for char in chunk:
            value = value * 85 + (char - 33)
        raw = value.to_bytes(4, "big")
        out.extend(raw[: 4 - pad] if pad else raw)
    return bytes(out)


def _unescape_pdf_string(raw: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(raw):
        if raw[i] == "\\" and i + 1 < len(raw):
            nxt = raw[i + 1]
            if nxt in "01234567":
                octal = nxt
                j = i + 2
                while j < len(raw) and j < i + 4 and raw[j] in "01234567":
                    octal += raw[j]
                    j += 1
                out.append(chr(int(octal, 8)))
                i = j
                continue
            out.append(
                {
                    "n": "\n",
                    "r": "\r",
                    "t": "\t",
                    "b": "\b",
                    "f": "\f",
                    "(": "(",
                    ")": ")",
                    "\\": "\\",
                }.get(nxt, nxt)
            )
            i += 2
            continue
        out.append(raw[i])
        i += 1
    return "".join(out)


def _inflate_streams(pdf_bytes: bytes) -> str:
    parts: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.S):
        header = pdf_bytes[max(0, match.start() - 240) : match.start()]
        if b"FlateDecode" not in header:
            continue
        payload = match.group(1).strip()
        try:
            if b"ASCII85Decode" in header:
                inflated = zlib.decompress(_ascii85_decode(payload))
            else:
                inflated = zlib.decompress(payload)
        except (zlib.error, ValueError):
            continue
        parts.append(inflated.decode("latin-1", errors="replace"))
    return "\n".join(parts)


def extract_pdf_text(path: Path) -> str:
    """Return the letter as lines of Unicode text, in reading order."""
    content = _inflate_streams(path.read_bytes())
    token_re = re.compile(r"\((?:\\.|[^\\)])*\)|T\*|ET")
    lines: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            line = "".join(current).strip()
            current.clear()
            if line:
                lines.append(line)

    for match in token_re.finditer(content):
        token = match.group(0)
        if token in ("T*", "ET"):
            flush()
        else:
            current.append(_unescape_pdf_string(token[1:-1]))
    flush()
    return "\n".join(lines)


def load_pdf_documents(folder: Path, specs: list[tuple[str, str, str, str, str]]) -> dict[str, dict[str, Any]]:
    """specs items are (doc_id, filename, short, title, date)."""
    if not folder.is_dir():
        raise FileNotFoundError(f"PDF folder not found: {folder}")
    docs: dict[str, dict[str, Any]] = {}
    for doc_id, filename, short, title, date in specs:
        path = folder / filename
        if not path.is_file():
            raise FileNotFoundError(f"Missing letter: {path}")
        text = extract_pdf_text(path)
        if not text.strip():
            raise RuntimeError(f"No text extracted from {path.name}")
        docs[doc_id] = {
            "id": doc_id,
            "title": title,
            "date": date,
            "short": short,
            "filename": filename,
            "text": text,
            "lines": [line.strip() for line in text.split("\n") if line.strip()],
        }
    return docs
