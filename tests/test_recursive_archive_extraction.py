import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from openpyxl import Workbook

from scripts.extract_construction_evidence import (
    docx_chunks,
    find_country,
    is_source_document,
    numeric_tokens,
    pptx_chunks,
    unpack_archives,
    xlsx_chunks,
)


def zip_bytes(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return buffer.getvalue()


class RecursiveArchiveExtractionTests(unittest.TestCase):
    def test_extracts_two_nested_zip_levels_and_reuses_them(self) -> None:
        grandchild = zip_bytes({"evidence.txt": "deep KOICA evidence"})
        child = zip_bytes(
            {
                "inside.txt": "nested KOICA evidence",
                "deep.zip": grandchild,
            }
        )
        root_zip = zip_bytes({"docs/child.zip": child, "root.txt": "root"})

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            raw = base / "raw"
            unpacked = base / "unpacked"
            (raw / "L2023-00009-1").mkdir(parents=True)
            source = raw / "L2023-00009-1" / "package.zip"
            source.write_bytes(root_zip)

            first = unpack_archives(raw, unpacked)
            target = unpacked / "L2023-00009-1" / "package"
            self.assertEqual(first["unpacked"], 3)
            self.assertEqual(first["nested_unpacked"], 2)
            self.assertEqual(
                (target / "docs" / "child" / "inside.txt").read_text(),
                "nested KOICA evidence",
            )
            self.assertEqual(
                (target / "docs" / "child" / "deep" / "evidence.txt").read_text(),
                "deep KOICA evidence",
            )

            second = unpack_archives(raw, unpacked)
            self.assertEqual(second["reused"], 3)
            self.assertEqual(second["nested_reused"], 2)

    def test_path_traversal_member_is_not_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            raw = base / "raw"
            unpacked = base / "unpacked"
            raw.mkdir()
            with zipfile.ZipFile(raw / "unsafe.zip", "w") as archive:
                archive.writestr("../escape.txt", "must not escape")
                archive.writestr("safe.txt", "safe")

            stats = unpack_archives(raw, unpacked)
            self.assertEqual(stats["unpacked"], 1)
            self.assertFalse((base / "escape.txt").exists())
            self.assertEqual(
                (unpacked / "unsafe" / "safe.txt").read_text(),
                "safe",
            )

    def test_legacy_root_marker_is_upgraded_and_nested_zip_is_scanned(self) -> None:
        nested = zip_bytes({"boq.txt": "quantity data"})
        root_zip = zip_bytes({"nested.zip": nested})

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            raw = base / "raw"
            unpacked = base / "unpacked"
            raw.mkdir()
            unpacked.mkdir()
            source = raw / "package.zip"
            source.write_bytes(root_zip)
            target = unpacked / "package"
            target.mkdir()
            (target / "nested.zip").write_bytes(nested)
            (target / ".complete").touch()

            stats = unpack_archives(raw, unpacked)
            self.assertEqual(stats["legacy_markers_upgraded"], 1)
            self.assertEqual(stats["nested_unpacked"], 1)
            self.assertEqual(
                (target / "nested" / "boq.txt").read_text(),
                "quantity data",
            )
            marker = json.loads((target / ".complete").read_text())
            self.assertEqual(marker["version"], 1)

    def test_changed_archive_invalidates_versioned_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            raw = base / "raw"
            unpacked = base / "unpacked"
            raw.mkdir()
            source = raw / "package.zip"
            source.write_bytes(zip_bytes({"value.txt": "first"}))
            unpack_archives(raw, unpacked)

            source.write_bytes(zip_bytes({"value.txt": "second and longer"}))
            stats = unpack_archives(raw, unpacked)
            self.assertEqual(stats["unpacked"], 1)
            self.assertNotIn("reused", stats)
            self.assertEqual(
                (unpacked / "package" / "value.txt").read_text(),
                "second and longer",
            )


class SpreadsheetChunkTests(unittest.TestCase):
    def test_xlsx_row_is_indexed_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet["A1"] = "BOQ"
            sheet["B1"] = 12
            workbook.save(path)

            chunks = xlsx_chunks(path)
            self.assertEqual(chunks, [("Sheet!1", "A1=BOQ | B1=12")])


class OfficeXmlChunkTests(unittest.TestCase):
    def test_docx_text_and_table_are_read_without_python_docx(self) -> None:
        document_xml = """\
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>Gross floor area 827.4 m2</w:t></w:r></w:p>
    <w:tbl><w:tr>
      <w:tc><w:p><w:r><w:t>Item</w:t></w:r></w:p></w:tc>
      <w:tc><w:p><w:r><w:t>Quantity 12</w:t></w:r></w:p></w:tc>
    </w:tr></w:tbl>
  </w:body>
</w:document>"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("word/document.xml", document_xml)
            self.assertEqual(
                docx_chunks(path),
                [
                    ("문단 1", "Gross floor area 827.4 m2"),
                    ("표 1 행 1", "Item | Quantity 12"),
                ],
            )

    def test_pptx_slides_are_sorted_numerically(self) -> None:
        slide = """\
<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
 <p:cSld><a:t>{}</a:t></p:cSld>
</p:sld>"""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.pptx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("ppt/slides/slide10.xml", slide.format("ten"))
                archive.writestr("ppt/slides/slide2.xml", slide.format("two"))
            self.assertEqual(
                pptx_chunks(path),
                [("슬라이드 1", "two"), ("슬라이드 2", "ten")],
            )


class SourceFilteringTests(unittest.TestCase):
    def test_meaningful_dot_directory_is_not_discarded(self) -> None:
        self.assertTrue(
            is_source_document(
                Path(".CM_review_files") / "mechanical_comments.xlsx"
            )
        )

    def test_generated_metadata_is_discarded(self) -> None:
        for path in (
            Path(".complete"),
            Path("__MACOSX") / "._document.pdf",
            Path("documents") / "~$draft.docx",
            Path("documents") / ".DS_Store",
        ):
            self.assertFalse(is_source_document(path))


class NumericTokenTests(unittest.TestCase):
    def test_excel_absolute_references_are_not_dollar_amounts(self) -> None:
        tokens = numeric_tokens("G42==SUM($F$30:$F$35)")
        self.assertEqual(tokens["currencies"], [])

    def test_actual_dollar_amounts_are_preserved(self) -> None:
        self.assertEqual(
            numeric_tokens("Ceiling amount US$ 272,603")["currencies"],
            ["US$ 272,603"],
        )
        self.assertEqual(
            numeric_tokens("Allowance $30.00")["currencies"],
            ["$ 30.00"],
        )


class CountryDetectionTests(unittest.TestCase):
    def test_specific_country_wins_over_country_substring_in_place_name(self) -> None:
        text = (
            "우즈벡 페르가나 직업훈련원 건립사업 "
            "우즈베키스탄 페르가나 직업훈련원 신축공사 "
            "Fergana City, Uzbekistan"
        )
        self.assertEqual(find_country(text), ("우즈베키스탄", "Uzbekistan"))

    def test_uzbek_alias_is_not_misread_as_ghana_inside_fergana(self) -> None:
        self.assertEqual(
            find_country("우즈벡 페르가나 직업훈련원 건립사업"),
            ("우즈베키스탄", "Uzbekistan"),
        )

    def test_ghana_is_still_detected(self) -> None:
        self.assertEqual(find_country("가나 관개지구 개선사업"), ("가나", "Ghana"))


if __name__ == "__main__":
    unittest.main()
