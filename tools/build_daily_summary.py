"""Reserved entrypoint for the future NAR Daily summary builder."""

from __future__ import annotations

import argparse


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NAR Daily summary builder (not implemented in this phase).")
    parser.add_argument("--input", help="Future collected NAR HTML directory.")
    parser.add_argument("--output", default="assets/analysis/nar_daily_summary.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    print("NAR Daily Summary生成は次のPhaseで実装します。")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
