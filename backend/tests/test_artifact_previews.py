"""Phase D (upstream port): office previews for artifacts."""

import io
import zipfile

from backend.apps.artifacts.preview import (
    extract_csv,
    extract_docx,
    extract_pptx,
    extract_preview,
    extract_xlsx,
)

NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS_M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buf.getvalue()


def _docx_bytes() -> bytes:
    return _zip({
        "word/document.xml": (
            f'<w:document xmlns:w="{NS_W}"><w:body>'
            "<w:p><w:r><w:t>Hello</w:t></w:r></w:p>"
            "<w:p><w:r><w:t>World</w:t></w:r></w:p>"
            "</w:body></w:document>"
        ),
    })


def _xlsx_bytes() -> bytes:
    return _zip({
        "xl/workbook.xml": (
            f'<workbook xmlns="{NS_M}"><sheets>'
            f'<sheet name="People" r:id="rId1" xmlns:r="{NS_R}"/>'
            "</sheets></workbook>"
        ),
        "xl/_rels/workbook.xml.rels": (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/>'
            "</Relationships>"
        ),
        "xl/sharedStrings.xml": f'<sst xmlns="{NS_M}"><si><t>Name</t></si></sst>',
        "xl/worksheets/sheet1.xml": (
            f'<worksheet xmlns="{NS_M}"><sheetData><row>'
            '<c r="A1" t="s"><v>0</v></c><c r="B1"><v>42</v></c>'
            "</row></sheetData></worksheet>"
        ),
    })


def _pptx_bytes() -> bytes:
    return _zip({
        "ppt/slides/slide1.xml": (
            f'<sld xmlns:a="{NS_A}"><a:t>Title</a:t><a:t>Body text</a:t></sld>'
        ),
        "ppt/slides/slide2.xml": f'<sld xmlns:a="{NS_A}"><a:t>Second</a:t></sld>',
    })


def test_docx_paragraphs():
    result = extract_docx(_docx_bytes())
    assert result["kind"] == "document"
    assert result["document"]["paragraphs"] == ["Hello", "World"]


def test_xlsx_shared_strings_and_values():
    result = extract_xlsx(_xlsx_bytes())
    assert result["kind"] == "workbook"
    sheet = result["workbook"]["sheets"][0]
    assert sheet["name"] == "People"
    assert sheet["rows"] == [["Name", "42"]]


def test_pptx_slides():
    result = extract_pptx(_pptx_bytes())
    assert result["kind"] == "slides"
    assert [s["index"] for s in result["slides"]] == [1, 2]
    assert result["slides"][0]["texts"] == ["Title", "Body text"]


def test_csv_table():
    result = extract_csv(b"name,age\nann,3\n")
    assert result["kind"] == "workbook"
    assert result["workbook"]["sheets"][0]["rows"] == [["name", "age"], ["ann", "3"]]


def test_garbage_is_unsupported_not_an_error():
    assert extract_preview(b"not a zip", "a.xlsx") == {"kind": "unsupported"}
    assert extract_preview(b"\x00\x01", "a.docx") == {"kind": "unsupported"}
    assert extract_preview(b"{}", "a.pdf") == {"kind": "unsupported"}
    assert extract_preview(_zip({"other.txt": "x"}), "a.docx") == {"kind": "unsupported"}


def test_preview_endpoint_serves_bounded_json(tmp_path, monkeypatch):
    import backend.apps.artifacts.artifacts as artifacts_mod
    from backend.apps.artifacts.artifacts import _store_artifact
    from backend.apps.artifacts.models import Artifact

    monkeypatch.setattr(artifacts_mod, "ARTIFACTS_DIR", str(tmp_path))
    artifact = Artifact(
        name="people.xlsx",
        filename="people.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=len(_xlsx_bytes()),
    )
    _store_artifact(artifact, content=_xlsx_bytes())

    import asyncio

    from backend.apps.artifacts.artifacts import preview_artifact

    result = asyncio.run(preview_artifact(artifact.id))
    assert result["kind"] == "workbook"
    assert result["workbook"]["sheets"][0]["rows"] == [["Name", "42"]]
