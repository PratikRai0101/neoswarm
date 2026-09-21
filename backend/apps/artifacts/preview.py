"""Structured previews for office documents (stdlib only).

Extracts docx paragraphs, pptx slide texts, and xlsx/csv sheets into small
JSON payloads the Artifacts viewer renders. Everything is bounded so one
huge spreadsheet cannot flood the response; truncation is reported honestly.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

MAX_SHEETS = 10
MAX_ROWS = 500
MAX_COLS = 50
MAX_CELL_CHARS = 500
MAX_PARAGRAPHS = 500
MAX_SLIDES = 100


def _clip(text: str, limit: int = MAX_CELL_CHARS) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _sheet_payload(name: str, rows: list[list[str]], truncated: bool) -> dict[str, Any]:
    clipped = [[_clip(cell) for cell in row[:MAX_COLS]] for row in rows[:MAX_ROWS]]
    return {
        "name": name or "Sheet",
        "rows": clipped,
        "total_rows": len(rows),
        "truncated": truncated or len(rows) > MAX_ROWS,
    }


def extract_csv(content: bytes) -> dict[str, Any]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    sample = text[:8192]
    first_line = sample.splitlines()[0] if sample.splitlines() else ""
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except Exception:
        dialect = csv.excel_tab if "\t" in first_line else csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [[cell for cell in row] for _, row in zip(range(MAX_ROWS + 1), reader)]
    return {
        "kind": "workbook",
        "workbook": {
            "sheets": [_sheet_payload("Sheet 1", rows, len(rows) > MAX_ROWS)],
        },
    }


def _zip_names(archive: zipfile.ZipFile) -> set[str]:
    try:
        return set(archive.namelist())
    except Exception:
        return set()


def extract_docx(content: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if "word/document.xml" not in _zip_names(archive):
                return {"kind": "unsupported"}
            root = ET.fromstring(archive.read("word/document.xml"))
    except Exception as exc:
        logger.warning("docx preview failed: %s", exc)
        return {"kind": "unsupported"}
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for para in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in para.findall(".//w:t", namespace)).strip()
        if text:
            paragraphs.append(text)
        if len(paragraphs) >= MAX_PARAGRAPHS:
            break
    return {
        "kind": "document",
        "document": {
            "paragraphs": [_clip(p, 2000) for p in paragraphs],
            "truncated": len(paragraphs) >= MAX_PARAGRAPHS,
        },
    }


def extract_pptx(content: bytes) -> dict[str, Any]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        names = sorted(
            name for name in _zip_names(archive)
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        )
        if not names:
            return {"kind": "unsupported"}
        namespace = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        slides: list[dict[str, Any]] = []
        for index, name in enumerate(names[:MAX_SLIDES], start=1):
            try:
                root = ET.fromstring(archive.read(name))
            except Exception:
                continue
            texts = [
                _clip(node.text or "", 500)
                for node in root.findall(".//a:t", namespace)
                if (node.text or "").strip()
            ]
            slides.append({"index": index, "texts": texts})
        archive.close()
    except Exception as exc:
        logger.warning("pptx preview failed: %s", exc)
        return {"kind": "unsupported"}
    return {
        "kind": "slides",
        "slides": slides,
        "truncated": len(names) > MAX_SLIDES,
    }


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    try:
        root = ET.fromstring(raw)
    except Exception:
        return []
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    strings: list[str] = []
    for item in root.findall("m:si", namespace):
        strings.append("".join(node.text or "" for node in item.findall(".//m:t", namespace)))
    return strings


def _xlsx_sheet_names(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Return (name, rel_id) pairs in workbook order."""
    try:
        root = ET.fromstring(archive.read("xl/workbook.xml"))
    except Exception:
        return []
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rels = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    return [
        (node.get("name", "Sheet"), node.get(f"{{{rels}}}id", ""))
        for node in root.findall(f".//{{{main}}}sheet")
    ]


def _xlsx_sheet_path(archive: zipfile.ZipFile, rel_id: str, fallback_index: int) -> str:
    try:
        root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        namespace = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
        for rel in root.findall("r:Relationship", namespace):
            if rel.get("Id") == rel_id:
                target = rel.get("Target", "")
                return "xl/" + target.replace("../", "") if not target.startswith("xl/") else target
    except Exception:
        pass
    return f"xl/worksheets/sheet{fallback_index}.xml"


def _xlsx_sheet_rows(archive: zipfile.ZipFile, path: str, shared: list[str]) -> list[list[str]]:
    try:
        root = ET.fromstring(archive.read(path))
    except Exception:
        return []
    main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    rows: list[list[str]] = []
    for row in root.findall(f".//{{{main}}}row"):
        cells: list[tuple[int, str]] = []
        for cell in row.findall(f"{{{main}}}c"):
            ref = cell.get("r", "A1")
            col = 0
            for char in ref:
                if char.isalpha():
                    col = col * 26 + (ord(char.upper()) - ord("A") + 1)
                else:
                    break
            kind = cell.get("t", "")
            value_node = cell.find(f"{{{main}}}v")
            inline = cell.find(f"{{{main}}}is")
            if kind == "s" and value_node is not None and value_node.text:
                try:
                    value = shared[int(value_node.text)]
                except (ValueError, IndexError):
                    value = ""
            elif inline is not None:
                value = "".join(
                    node.text or "" for node in inline.findall(f".//{{{main}}}t")
                )
            elif value_node is not None:
                value = value_node.text or ""
            else:
                value = ""
            cells.append((col, value))
        cells.sort(key=lambda item: item[0])
        # Fill gaps so columns line up.
        expanded: list[str] = []
        for col, value in cells:
            while len(expanded) < col - 1:
                expanded.append("")
            expanded.append(value)
        rows.append(expanded[:MAX_COLS])
        if len(rows) > MAX_ROWS:
            break
    width = max((len(row) for row in rows), default=0)
    return [row + [""] * (width - len(row)) for row in rows]


def extract_xlsx(content: bytes) -> dict[str, Any]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        shared = _xlsx_shared_strings(archive)
        sheets: list[dict[str, Any]] = []
        names = _xlsx_sheet_names(archive)
        truncated = len(names) > MAX_SHEETS
        for position, (name, rel_id) in enumerate(names[:MAX_SHEETS], start=1):
            path = _xlsx_sheet_path(archive, rel_id, position)
            rows = _xlsx_sheet_rows(archive, path, shared)
            sheets.append(_sheet_payload(name, rows, False))
        archive.close()
    except Exception as exc:
        logger.warning("xlsx preview failed: %s", exc)
        return {"kind": "unsupported"}
    if not sheets:
        return {"kind": "unsupported"}
    return {"kind": "workbook", "workbook": {"sheets": sheets}}


def extract_preview(content: bytes, filename: str) -> dict[str, Any]:
    """Extract a bounded structured preview for a stored artifact file."""
    suffix = Path(filename).suffix.lower()
    if suffix == ".xlsx":
        return extract_xlsx(content)
    if suffix == ".docx":
        return extract_docx(content)
    if suffix == ".pptx":
        return extract_pptx(content)
    if suffix in (".csv", ".tsv"):
        return extract_csv(content)
    return {"kind": "unsupported"}
