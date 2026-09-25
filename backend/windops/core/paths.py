"""Stable filesystem locations, independent of the process working directory.

WINDOPS_STORAGE_DIR can select an external data disk. Relative overrides are
resolved against the repository root. Importing this module creates no files.
"""
from __future__ import annotations

import os
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def resolve_storage_dir(value: str | None = None) -> Path:
    configured = value if value is not None else os.environ.get("WINDOPS_STORAGE_DIR")
    location = Path(configured).expanduser() if configured else Path("storage")
    if not location.is_absolute():
        location = REPOSITORY_ROOT / location
    return location.resolve()


STORAGE_DIR = resolve_storage_dir()
RAW_DATA_DIR = STORAGE_DIR / "data" / "raw"
PROCESSED_DIR = STORAGE_DIR / "data" / "processed"
MODEL_DIR = STORAGE_DIR / "models"
WEATHER_DIR = STORAGE_DIR / "weather"
FORECAST_DIR = STORAGE_DIR / "forecasts"
REPORT_DIR = STORAGE_DIR / "reports"
