"""NAR Daily summary helpers for the dashboard foundation.

Prediction and summary generation are intentionally out of scope for this phase.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .summary_loader import load_summary, summary_counts, summary_date, summary_venues


NAR_DAILY_SUMMARY_PATH = Path("assets/analysis/nar_daily_summary.json")


def load_nar_daily_summary(path: str | Path = NAR_DAILY_SUMMARY_PATH) -> dict[str, Any] | None:
    return load_summary(path)


__all__ = [
    "NAR_DAILY_SUMMARY_PATH",
    "load_nar_daily_summary",
    "summary_counts",
    "summary_date",
    "summary_venues",
]
