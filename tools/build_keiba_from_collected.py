from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.dashboard_batch import (  # noqa: E402
    BatchPredictionReport,
    UploadedSource,
    normalize_requested_race_date,
    predict_html_sources,
)
from core.prediction_snapshot import keiba_bytes  # noqa: E402


HTML_SUFFIXES = {".html", ".htm"}


@dataclass(frozen=True)
class BuildKeibaReport:
    batch_report: BatchPredictionReport
    output_path: Path


def build_keiba_from_collected(
    input_dir: str | Path,
    *,
    race_date: str,
    output_path: str | Path,
    mode: str = "all",
    overwrite: bool = False,
) -> BuildKeibaReport:
    input_path = Path(input_dir).expanduser().resolve()
    if not input_path.exists() or not input_path.is_dir():
        raise SystemExit(f"input directory was not found: {input_path}")

    selected_mode = normalize_mode(mode)
    output = Path(output_path).expanduser().resolve()
    if output.exists() and not overwrite:
        raise SystemExit(f"output already exists: {output}. Use --overwrite to replace it.")

    sources = html_sources_from_directory(input_path)
    if not sources:
        raise SystemExit(f"HTML files were not found under: {input_path}")

    def progress(index: int, total: int, label: str) -> None:
        print(f"[{index}/{total}] {label}")

    report = predict_html_sources(
        sources,
        prediction_logic_version="market",
        progress=progress,
        race_date=race_date,
        race_mode="" if selected_mode == "all" else selected_mode,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(keiba_bytes(report.event_snapshot))
    return BuildKeibaReport(batch_report=report, output_path=output)


def html_sources_from_directory(input_dir: Path) -> list[UploadedSource]:
    sources: list[UploadedSource] = []
    for path in sorted(input_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in HTML_SUFFIXES:
            continue
        relative = path.relative_to(input_dir).as_posix()
        sources.append(
            UploadedSource(
                file_name=relative,
                data=path.read_bytes(),
            )
        )
    return sources


def normalize_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode not in {"all", "jra", "nar"}:
        raise SystemExit(f"unsupported mode: {value}")
    return mode


def compact_date(value: str) -> str:
    normalized = normalize_requested_race_date(value)
    return normalized.replace("-", "")


def today_compact() -> str:
    return datetime.now().strftime("%Y%m%d")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a .keiba snapshot from collected netkeiba HTML.")
    parser.add_argument("--input", required=True, help="Directory containing collected .html/.htm files.")
    parser.add_argument("--date", help="Race date. Example: 20260908 or 2026-09-08.")
    parser.add_argument("--today", action="store_true", help="Use today's date in the local environment.")
    parser.add_argument("--mode", choices=("all", "jra", "nar"), default="all")
    parser.add_argument("--output", help="Output .keiba path.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing .keiba file.")
    args = parser.parse_args(argv)
    if args.today and args.date:
        parser.error("--today and --date cannot be used together.")
    if not args.today and not args.date:
        parser.error("--date or --today is required.")
    race_date = today_compact() if args.today else compact_date(args.date)
    args.date = race_date
    if not args.output:
        input_path = Path(args.input).expanduser().resolve()
        args.output = str(input_path.parent / f"{race_date}_{args.mode}.keiba")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("Keiba AI build_keiba_from_collected")
    print(f"date: {args.date}")
    print(f"mode: {args.mode}")
    print(f"input: {Path(args.input).expanduser().resolve()}")
    print(f"output: {Path(args.output).expanduser().resolve()}")
    report = build_keiba_from_collected(
        args.input,
        race_date=args.date,
        output_path=args.output,
        mode=args.mode,
        overwrite=args.overwrite,
    ).batch_report
    print(f"HTML files: {report.html_file_count}")
    print(f"Recognized: {report.recognized_file_count}")
    print(f"Predicted: {report.predicted_race_count}")
    print(f"Skipped: {report.skipped_race_count}")
    print(f"Warnings: {len(report.warnings)}")
    for message in report.warnings[:20]:
        print(f"WARNING: {message}")
    print(f"Errors: {len(report.errors)}")
    for message in report.errors[:20]:
        print(f"ERROR: {message}")
    print(f"Output: {Path(args.output).expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
