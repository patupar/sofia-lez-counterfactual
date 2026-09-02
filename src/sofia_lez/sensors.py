"""Prepare one continuous FILTER and Sensor.Community PM2.5 record."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pandas as pd

from .config import ensure_parent
from .qc import build_archive_hourly

HOURLY_COLUMNS = [
    "hour_utc",
    "hour_local",
    "date_local",
    "sensor_id",
    "location",
    "location_id",
    "lat",
    "lon",
    "pm2_5",
    "n_observations",
    "spread",
    "data_source",
    "source_qc_code",
    "qc_method",
    "qc_source_code",
    "qc_range",
    "qc_spread",
    "qc_temporal",
    "qc_pass",
]


def _selected_pairs(manifest: pd.DataFrame) -> pd.DataFrame:
    """Return the historical pairs used for archive follow-up and modelling."""
    continuing = manifest["plausible_continuing"].astype(str).str.lower().eq("true")
    return manifest.loc[continuing].copy()


def _read_filter_pair(path: Path, pair: pd.Series, config: dict) -> pd.DataFrame:
    """Read and standardise one historical FILTER location-sensor file."""
    required = ["hour_timestamp", "raw_pm2_5", "spread", "raw_qc"]
    frame = pd.read_csv(path, usecols=required, dtype={"raw_qc": "string"})
    frame["hour_utc"] = pd.to_datetime(
        pd.to_numeric(frame["hour_timestamp"], errors="coerce"), unit="s", utc=True
    )
    frame["pm2_5"] = pd.to_numeric(frame["raw_pm2_5"], errors="coerce")
    frame["spread"] = pd.to_numeric(frame["spread"], errors="coerce")
    frame["source_qc_code"] = (
        frame["raw_qc"].astype("string").str.replace(r"\.0$", "", regex=True)
    )
    frame = frame.dropna(subset=["hour_utc", "pm2_5"])

    study_start = pd.Timestamp(config["project"]["study_start_date"])
    start = pd.Timestamp(study_start - timedelta(days=1), tz="UTC")
    end = pd.Timestamp(config["project"]["filter_end_date"], tz="UTC") + timedelta(days=1)
    frame = frame.loc[frame["hour_utc"].ge(start) & frame["hour_utc"].lt(end)].copy()
    if frame.empty:
        return frame

    timezone = config["project"]["timezone"]
    frame["hour_local"] = frame["hour_utc"].dt.tz_convert(timezone)
    frame["date_local"] = frame["hour_local"].dt.date.astype(str)
    frame = frame.loc[pd.to_datetime(frame["date_local"]).ge(study_start)].copy()
    frame["sensor_id"] = int(pair["sensor_id"])
    frame["location"] = str(pair["location"])
    frame["location_id"] = int(pair["location_id"])
    frame["lat"] = float(pair["lat"])
    frame["lon"] = float(pair["lon"])
    frame["n_observations"] = pd.Series(pd.NA, index=frame.index, dtype="Int64")
    frame["data_source"] = "filter"

    qc = config["qc"]
    manifest_settings = config["manifest"]
    frame["qc_source_code"] = frame["source_qc_code"].str.startswith(
        str(manifest_settings["historical_qc_prefix"]), na=False
    )
    frame["qc_range"] = frame["pm2_5"].between(
        float(qc["pm25_min"]), float(qc["pm25_max"]), inclusive="both"
    )
    frame["qc_spread"] = frame["spread"].eq(int(manifest_settings["require_spread"]))
    frame["qc_temporal"] = pd.Series(pd.NA, index=frame.index, dtype="boolean")
    frame["qc_pass"] = frame[["qc_source_code", "qc_range", "qc_spread"]].all(axis=1)
    frame["qc_method"] = (
        f"FILTER raw_qc prefix {manifest_settings['historical_qc_prefix']} + "
        f"spread={manifest_settings['require_spread']} + range"
    )
    return frame.reindex(columns=HOURLY_COLUMNS)


def extract_filter_hourly(config: dict) -> pd.DataFrame:
    """Extract historical raw PM2.5 for all plausible continuing Sofia pairs."""
    manifest = pd.read_csv(config["paths"]["manifest"])
    pairs = _selected_pairs(manifest)
    frames = []
    missing_files = []
    for _, pair in pairs.iterrows():
        path = config["paths"]["bgr_directory"] / str(pair["historical_file"])
        if not path.exists():
            missing_files.append(path.name)
            continue
        frame = _read_filter_pair(path, pair, config)
        if not frame.empty:
            frames.append(frame)

    if missing_files:
        examples = ", ".join(missing_files[:5])
        raise FileNotFoundError(f"Missing {len(missing_files)} BGR files, including: {examples}")
    if not frames:
        raise ValueError("No FILTER observations fall inside the configured historical period")

    hourly = pd.concat(frames, ignore_index=True).sort_values(
        ["location_id", "sensor_id", "hour_utc"]
    )
    ensure_parent(config["paths"]["filter_hourly"])
    hourly.to_csv(config["paths"]["filter_hourly"], index=False)
    return hourly


def build_unified_hourly(config: dict) -> pd.DataFrame:
    """Combine non-overlapping FILTER and archive records in one documented schema."""
    filter_end = pd.Timestamp(config["project"]["filter_end_date"])
    archive_start = pd.Timestamp(config["project"]["archive_start_date"])
    if filter_end >= archive_start:
        raise ValueError("filter_end_date must be earlier than archive_start_date")

    historical = extract_filter_hourly(config)
    archive = build_archive_hourly(config).reindex(columns=HOURLY_COLUMNS)
    for frame in (historical, archive):
        frame["n_observations"] = pd.to_numeric(
            frame["n_observations"], errors="coerce"
        ).astype("Int64")
        frame["source_qc_code"] = frame["source_qc_code"].astype("string")
        for column in (
            "qc_source_code",
            "qc_range",
            "qc_spread",
            "qc_temporal",
            "qc_pass",
        ):
            frame[column] = frame[column].astype("boolean")
    hourly = pd.concat([historical, archive], ignore_index=True)

    duplicate = hourly.duplicated(["location_id", "sensor_id", "hour_utc"], keep=False)
    if duplicate.any():
        examples = hourly.loc[duplicate, ["location", "sensor_id", "hour_utc"]].head()
        raise ValueError(f"Overlapping FILTER/archive observations found:\n{examples}")

    hourly = hourly.sort_values(["location_id", "sensor_id", "hour_utc"]).reset_index(drop=True)
    ensure_parent(config["paths"]["hourly"])
    hourly.to_csv(config["paths"]["hourly"], index=False)
    return hourly
