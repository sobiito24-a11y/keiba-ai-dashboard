from __future__ import annotations

import io
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path

from core.summary_loader import load_summary, summary_counts
from core.upload_pipeline import (
    UploadProcessingError,
    date_from_archive_name,
    detect_archive_mode,
    process_html_zip,
    safe_extract_zip,
)


def archive_bytes(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def successful_builder(expected_html: str, captured: dict[str, object]):
    def build(input_directory, output_path, *, summary_date="", fetch_past_detail=True):
        input_root = Path(input_directory)
        captured["input_root"] = input_root
        captured["summary_date"] = summary_date
        captured["fetch_past_detail"] = fetch_past_detail
        self_html = input_root / expected_html
        if not self_html.is_file():
            raise AssertionError(f"missing extracted HTML: {self_html}")
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        detail_name = "nar_results" if output.name.startswith("nar_") else "results"
        detail = output.parent / detail_name / "race.json"
        detail.parent.mkdir(parents=True, exist_ok=True)
        detail.write_text('{"status":"ok"}\n', encoding="utf-8")
        output.write_text(
            json.dumps(
                {
                    "date": summary_date,
                    "counts": {"buy": 1, "hold": 0, "skip": 2},
                    "buy": [{"race_id": "race"}],
                    "hold": [],
                    "skip": [{}, {}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return output, 3, []

    return build


class UploadPipelineTest(unittest.TestCase):
    def test_archive_name_selects_jra_or_nar_and_extracts_date(self) -> None:
        self.assertEqual(detect_archive_mode("collected_html_jra_20260808.zip"), "jra")
        self.assertEqual(detect_archive_mode("collected_html_nar_20260806.zip"), "nar")
        self.assertEqual(date_from_archive_name("collected_html_jra_20260808.zip"), "2026-08-08")
        with self.assertRaises(UploadProcessingError):
            detect_archive_mode("html.zip")

    def test_jra_upload_calls_weekend_builder_and_publishes_summary(self) -> None:
        captured: dict[str, object] = {}
        data = archive_bytes({"collected/jra/race.html": "<html>JRA</html>"})

        def unexpected_daily(*args, **kwargs):
            raise AssertionError("NAR builder must not be called")

        with tempfile.TemporaryDirectory() as tmp:
            analysis = Path(tmp) / "assets" / "analysis"
            result = process_html_zip(
                "collected_html_jra_20260808.zip",
                data,
                analysis,
                weekend_builder=successful_builder("collected/jra/race.html", captured),
                daily_builder=unexpected_daily,
                fetch_past_detail=False,
            )
            self.assertEqual(result.mode, "jra")
            self.assertEqual(result.analyzed_races, 3)
            self.assertEqual(result.summary_path, analysis / "weekend_summary.json")
            self.assertTrue((analysis / "results" / "race.json").is_file())
            self.assertEqual(summary_counts(load_summary(result.summary_path) or {}), (1, 0, 2))
            self.assertEqual(captured["summary_date"], "2026-08-08")
            self.assertFalse(captured["fetch_past_detail"])
            self.assertFalse(Path(captured["input_root"]).exists())

    def test_nar_upload_calls_daily_builder_and_publishes_separate_summary(self) -> None:
        captured: dict[str, object] = {}
        data = archive_bytes({"nar/meeting/race.html": "<html>NAR</html>"})

        def unexpected_weekend(*args, **kwargs):
            raise AssertionError("JRA builder must not be called")

        with tempfile.TemporaryDirectory() as tmp:
            analysis = Path(tmp) / "analysis"
            result = process_html_zip(
                "collected_html_nar_20260806.zip",
                data,
                analysis,
                weekend_builder=unexpected_weekend,
                daily_builder=successful_builder("nar/meeting/race.html", captured),
            )
            self.assertEqual(result.mode, "nar")
            self.assertEqual(result.summary_path, analysis / "nar_daily_summary.json")
            self.assertTrue((analysis / "nar_results" / "race.json").is_file())
            self.assertFalse((analysis / "weekend_summary.json").exists())

    def test_failed_analysis_does_not_replace_existing_summary(self) -> None:
        data = archive_bytes({"race.html": "<html></html>"})

        def failed_builder(input_directory, output_path, **kwargs):
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text('{"counts":{"buy":0}}', encoding="utf-8")
            return output, 0, [{"race_id": "x", "message": "missing inputs"}]

        with tempfile.TemporaryDirectory() as tmp:
            analysis = Path(tmp) / "analysis"
            analysis.mkdir()
            existing = analysis / "weekend_summary.json"
            existing.write_text('{"marker":"keep"}', encoding="utf-8")
            with self.assertRaises(UploadProcessingError):
                process_html_zip(
                    "collected_html_jra_20260808.zip",
                    data,
                    analysis,
                    weekend_builder=failed_builder,
                )
            self.assertEqual(json.loads(existing.read_text(encoding="utf-8")), {"marker": "keep"})

    def test_safe_extraction_rejects_path_traversal(self) -> None:
        data = archive_bytes({"../outside.html": "bad"})
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UploadProcessingError):
                safe_extract_zip(data, Path(tmp) / "output")
            self.assertFalse((Path(tmp) / "outside.html").exists())

    def test_safe_extraction_rejects_symbolic_links(self) -> None:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            item = zipfile.ZipInfo("linked.html")
            item.create_system = 3
            item.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(item, "target.html")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UploadProcessingError):
                safe_extract_zip(buffer.getvalue(), Path(tmp) / "output")


if __name__ == "__main__":
    unittest.main()
