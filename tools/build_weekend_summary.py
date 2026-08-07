from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.html_classifier import classify_html, decode_uploaded_html, required_kinds
from core.models import PredictionResult
from core.weekend_summary import (
    build_weekend_summary,
    normalize_summary_date,
    write_prediction_result,
    write_weekend_summary,
)


RACE_ID_RE = re.compile(r"(?<!\d)(\d{12})(?!\d)")


def discover_race_html(input_directory: str | Path) -> dict[str, list[Path]]:
    root = Path(input_directory)
    if not root.is_dir():
        raise FileNotFoundError(f"Input directory was not found: {root}")
    grouped: dict[str, list[Path]] = {}
    for path in sorted(root.rglob("*.html")):
        race_id = _race_id_for_path(path, root)
        if race_id:
            grouped.setdefault(race_id, []).append(path)
    return grouped


def prepare_race_input(paths: list[Path]) -> tuple[dict[str, str], dict[str, str]]:
    classified: dict[str, list[tuple[Path, str]]] = {}
    for path in sorted(paths):
        html_text = decode_uploaded_html(path.read_bytes())
        item = classify_html(path.name, html_text, "jra")
        classified.setdefault(item.kind, []).append((path, html_text))

    missing = [kind for kind in required_kinds("jra") if not classified.get(kind)]
    if missing:
        raise ValueError("Required JRA HTML is missing: " + ", ".join(missing))

    html_files: dict[str, str] = {}
    file_names: dict[str, str] = {}
    for kind in ("speed", "newspaper", "style", "oikiri"):
        candidates = classified.get(kind, [])
        if not candidates:
            continue
        path, html_text = candidates[0]
        html_files[kind] = html_text
        file_names[kind] = path.name
    return html_files, file_names


def build_from_directory(
    input_directory: str | Path,
    output_path: str | Path,
    *,
    summary_date: str = "",
    fetch_past_detail: bool = True,
    predictor: Callable[[dict[str, str], dict[str, str]], PredictionResult] | None = None,
) -> tuple[Path, int, list[dict[str, str]]]:
    input_path = Path(input_directory)
    output = Path(output_path)
    grouped = discover_race_html(input_path)
    results: list[tuple[str, PredictionResult]] = []
    detail_paths: dict[str, str] = {}
    errors: list[dict[str, str]] = []

    if predictor is None:
        from core.jra_notebook_logic import predict_jra_from_html

        predictor = lambda html_files, file_names: predict_jra_from_html(
            html_files,
            file_names,
            fetch_past_detail=fetch_past_detail,
        )

    for race_id, paths in sorted(grouped.items()):
        try:
            html_files, file_names = prepare_race_input(paths)
            result = predictor(html_files, file_names)
            if result.status != "ok":
                raise RuntimeError(result.message or "PredictionResult is not ready.")
            detail_relative = f"results/{race_id}.json"
            write_prediction_result(result, output.parent / detail_relative)
            detail_paths[race_id] = detail_relative
            results.append((race_id, result))
            print(f"[{len(results)}/{len(grouped)}] {race_id}: analyzed")
        except Exception as exc:
            errors.append({"race_id": race_id, "message": str(exc)})
            print(f"{race_id}: failed: {exc}", file=sys.stderr)

    resolved_date = normalize_summary_date(summary_date) or _infer_date(input_path, results)
    summary = build_weekend_summary(
        results,
        summary_date=resolved_date,
        detail_paths=detail_paths,
        errors=errors,
    )
    write_weekend_summary(summary, output)
    return output, len(results), errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze every collected JRA race and build Keiba AI Weekend JSON.",
    )
    parser.add_argument("--input", required=True, help="Directory containing collected JRA HTML files.")
    parser.add_argument("--output", default="assets/analysis/weekend_summary.json", help="Output JSON path.")
    parser.add_argument("--date", default="", help="Race date, for example 2026-08-08. Inferred from the input path when omitted.")
    parser.add_argument(
        "--no-fetch-past-detail",
        action="store_true",
        help="Skip network completion of past-race details. Existing prediction behavior is used by default.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        output, success_count, errors = build_from_directory(
            args.input,
            args.output,
            summary_date=args.date,
            fetch_past_detail=not args.no_fetch_past_detail,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"weekend summary: {output}")
    print(f"analyzed: {success_count} / errors: {len(errors)}")
    return 0 if success_count else 1


def _race_id_for_path(path: Path, root: Path) -> str:
    relative = str(path.relative_to(root))
    match = RACE_ID_RE.search(relative)
    if match:
        return match.group(1)
    text = decode_uploaded_html(path.read_bytes()[:160_000])
    match = RACE_ID_RE.search(text)
    return match.group(1) if match else ""


def _infer_date(input_path: Path, results: list[tuple[str, PredictionResult]]) -> str:
    inferred = normalize_summary_date(str(input_path))
    if inferred:
        return inferred
    for _race_id, result in results:
        info = result.race_info or {}
        for key in ("race_date", "date", "開催日"):
            inferred = normalize_summary_date(info.get(key))
            if inferred:
                return inferred
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
