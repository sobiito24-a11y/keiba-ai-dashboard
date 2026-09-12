from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.build_keiba_from_collected import build_keiba_from_collected, compact_date  # noqa: E402


COLLECTOR_NO_RACES_EXIT_CODE = 3


@dataclass(frozen=True)
class PipelinePaths:
    data_root: Path
    date_root: Path
    html_root: Path
    logs_root: Path
    output_path: Path


@dataclass(frozen=True)
class CollectorRunResult:
    mode: str
    no_races: bool = False


def default_data_root() -> Path:
    return Path.home() / "Documents" / "Codex" / "Keiba_AI_Data" / "morning"


def default_mobile_root() -> Path:
    return ROOT.parent / "keiba_ai_mobile"


def selected_modes(mode: str) -> list[str]:
    normalized = str(mode or "").strip().lower()
    if normalized == "all":
        return ["jra", "nar"]
    if normalized in {"jra", "nar"}:
        return [normalized]
    raise SystemExit(f"unsupported mode: {mode}")


def pipeline_paths(data_root: Path, race_date: str, mode: str) -> PipelinePaths:
    date_root = data_root / race_date
    html_root = date_root / "html"
    logs_root = date_root / "logs"
    output_path = date_root / f"{race_date}_{mode}.keiba"
    return PipelinePaths(
        data_root=data_root,
        date_root=date_root,
        html_root=html_root,
        logs_root=logs_root,
        output_path=output_path,
    )


def run_collector(
    *,
    mobile_root: Path,
    mode: str,
    race_date: str,
    paths: PipelinePaths,
    overwrite: bool,
    headless: bool,
    no_pause_on_login: bool,
) -> CollectorRunResult:
    collector = mobile_root / "tools" / "netkeiba_html_collector.py"
    if not collector.exists():
        raise SystemExit(f"Mobile collector was not found: {collector}")
    command = [
        sys.executable,
        str(collector),
        "--mode",
        mode,
        "--date",
        race_date,
        "--out",
        str(paths.html_root),
        "--profile-dir",
        str(paths.data_root / "_collector_profile"),
    ]
    if overwrite:
        command.append("--overwrite")
    if headless:
        command.append("--headless")
    if no_pause_on_login:
        command.append("--no-pause-on-login")
    print(f"STEP collect {mode.upper()}")
    completed = subprocess.run(command, cwd=str(mobile_root), check=False)
    if completed.returncode == COLLECTOR_NO_RACES_EXIT_CODE:
        print(f"{mode.upper()}: 0 races -> skip")
        return CollectorRunResult(mode=mode, no_races=True)
    if completed.returncode != 0:
        raise SystemExit(f"{mode.upper()} HTML collection failed with exit code {completed.returncode}")
    return CollectorRunResult(mode=mode, no_races=False)


def run_pipeline(
    *,
    race_date: str,
    mode: str,
    data_root: Path,
    mobile_root: Path,
    overwrite: bool,
    headless: bool,
    no_pause_on_login: bool,
) -> Path | None:
    normalized_mode = str(mode or "").strip().lower()
    modes = selected_modes(normalized_mode)
    paths = pipeline_paths(data_root.expanduser().resolve(), race_date, normalized_mode)
    paths.html_root.mkdir(parents=True, exist_ok=True)
    paths.logs_root.mkdir(parents=True, exist_ok=True)

    print("====================================")
    print("Keiba AI Morning Pipeline")
    print(race_date)
    print("====================================")
    print(f"data root: {paths.data_root}")
    print(f"html root: {paths.html_root}")
    collector_results: list[CollectorRunResult] = []
    for item in modes:
        collector_results.append(
            run_collector(
                mobile_root=mobile_root.expanduser().resolve(),
                mode=item,
                race_date=race_date,
                paths=paths,
                overwrite=overwrite,
                headless=headless,
                no_pause_on_login=no_pause_on_login,
            )
        )

    if collector_results and all(result.no_races for result in collector_results):
        print("====================================")
        print("Prediction")
        print("No races were found for the requested date and mode.")
        print("Output: none")
        print("====================================")
        return None

    print("STEP build .keiba")
    build_report = build_keiba_from_collected(
        paths.html_root,
        race_date=race_date,
        output_path=paths.output_path,
        mode=normalized_mode,
        overwrite=overwrite,
        logs_dir=paths.logs_root,
    )
    report = build_report.batch_report
    scope = report.event_snapshot.get("scope") or {}
    print("====================================")
    print("Prediction")
    print(f"races attempted: {report.predicted_race_count + report.skipped_race_count}")
    print(f"predicted: {report.predicted_race_count}")
    print(f"skipped: {report.skipped_race_count}")
    print(f"race modes: {', '.join(scope.get('race_modes') or [])}")
    print(f"venues: {', '.join(scope.get('venues') or [])}")
    if getattr(build_report, "diagnostics_log_path", None):
        print(f"diagnostics log: {build_report.diagnostics_log_path}")
    print("Output:")
    print(paths.output_path)
    print("NEXT:")
    print("Dashboard -> 保存した予想を開く -> " + paths.output_path.name)
    print("====================================")
    return paths.output_path


def today_compact() -> str:
    return datetime.now().strftime("%Y%m%d")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect today's netkeiba HTML and build a .keiba file.")
    parser.add_argument("--today", action="store_true", help="Use today's date in the local environment.")
    parser.add_argument("--date", help="Race date. Example: 20260908 or 2026-09-08.")
    parser.add_argument("--mode", choices=("all", "jra", "nar"), default="all")
    parser.add_argument("--data-root", default=str(default_data_root()))
    parser.add_argument("--mobile-root", default=str(default_mobile_root()))
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-pause-on-login", action="store_true")
    args = parser.parse_args(argv)
    if args.today and args.date:
        parser.error("--today and --date cannot be used together.")
    if not args.today and not args.date:
        parser.error("--date or --today is required.")
    args.date = today_compact() if args.today else compact_date(args.date)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    run_pipeline(
        race_date=args.date,
        mode=args.mode,
        data_root=Path(args.data_root),
        mobile_root=Path(args.mobile_root),
        overwrite=args.overwrite,
        headless=args.headless,
        no_pause_on_login=args.no_pause_on_login,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
