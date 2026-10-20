"""Compatibility wrapper for the project’s automated data-quality pass.

The canonical implementation lives in data_quality_report.py so the project reuses
its existing reporting logic and keeps the quality checks in one place.
"""

from data_quality_report import (
    assess_futures_quality,
    assess_options_quality,
    repair_futures_quality,
    repair_options_quality,
    run_quality_pass,
)

__all__ = [
    "assess_futures_quality",
    "assess_options_quality",
    "repair_futures_quality",
    "repair_options_quality",
    "run_quality_pass",
]
