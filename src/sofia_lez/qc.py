"""Extract archive observations, reconstruct hours, and apply explicit QC."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ensure_parent

ARCHIVE_PATTERN = re.compile(r"(?P<date>\d{4}-\d{2}-\d{2})_sensor_(?P<sensor>\d+)\.csv(?:\.gz)?$")


def _read_archive_file(
    path: Path, valid_pairs: set[tuple[int, int]], timezone: str
) -> pd.DataFrame:
    """Filter one daily source file to exact historical location-sensor pairs."""
    try:
        frame = pd.read_csv(
            path,
            sep=";",
            compression="infer",
            usecols=lambda column: column in {"sensor_id", "location", "timestamp", "P2"},
            low_memory=False,
        )
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()
    required = {"sensor_id", "location", "timestamp", "P2"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()

    frame["sensor_id"] = pd.to_numeric(frame["sensor_id"], errors="coerce")
    frame["location_id"] = pd.to_numeric(frame["location"], errors="coerce")
    frame["pm25"] = pd.to_numeric(frame["P2"], errors="coerce")
    frame = frame.dropna(subset=["sensor_id", "location_id", "timestamp", "pm25"])
    frame[["sensor_id", "location_id"]] = frame[["sensor_id", "location_id"]].astype(int)
    keep = [
        (sensor, location) in valid_pairs
        for sensor, location in zip(frame["sensor_id"], frame["location_id"], strict=True)
    ]
    frame = frame.loc[keep].copy()
    if frame.empty:
        return frame

    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["timestamp_utc"])
    frame["hour_utc"] = frame["timestamp_utc"].dt.floor("h")
    frame["twenty_minute_bin"] = frame["timestamp_utc"].dt.minute // 20
    hourly = (
        frame.groupby(["location_id", "sensor_id", "hour_utc"], as_index=False)
        .agg(
            raw_pm2_5=("pm25", "mean"),
            n_observations=("pm25", "size"),
            spread=("twenty_minute_bin", "nunique"),
        )
        .sort_values(["location_id", "sensor_id", "hour_utc"])
    )
    hourly["hour_local"] = hourly["hour_utc"].dt.tz_convert(timezone)
    return hourly


def _temporal_qc(group: pd.DataFrame, settings: dict) -> pd.DataFrame:
    group = group.sort_values("hour_utc").copy()
    values = group["pm2_5"]
    window = int(settings["temporal_window_hours"])
    minimum = int(settings["temporal_min_periods"])
    rolling_median = values.rolling(window, center=True, min_periods=minimum).median()
    residual = (values - rolling_median).abs()
    rolling_mad = residual.rolling(window, center=True, min_periods=minimum).median()
    threshold = np.maximum(
        float(settings["temporal_absolute_floor"]),
        float(settings["temporal_mad_multiplier"]) * 1.4826 * rolling_mad,
    )
    group["qc_temporal"] = rolling_median.isna() | residual.le(threshold)
    return group


def build_archive_hourly(config: dict) -> pd.DataFrame:
    """Reconstruct and quality-control the 2024+ Sensor.Community archive."""
    manifest = pd.read_csv(config["paths"]["manifest"])
    continuing = manifest["plausible_continuing"].astype(str).str.lower().eq("true")
    candidates = manifest.loc[continuing].copy()
    valid_pairs = set(
        zip(candidates["sensor_id"].astype(int), candidates["location_id"].astype(int), strict=True)
    )
    archive_files = sorted(config["paths"]["archive"].glob("**/*.csv")) + sorted(
        config["paths"]["archive"].glob("**/*.csv.gz")
    )
    frames = []
    for path in archive_files:
        if not ARCHIVE_PATTERN.search(path.name):
            continue
        extracted = _read_archive_file(path, valid_pairs, config["project"]["timezone"])
        if not extracted.empty:
            frames.append(extracted)
    if not frames:
        raise ValueError("No matching Sensor.Community observations found in the archive directory")
    hourly = pd.concat(frames, ignore_index=True).drop_duplicates(
        ["location_id", "sensor_id", "hour_utc"], keep="last"
    )

    archive_start = pd.Timestamp(config["project"]["archive_start_date"], tz="UTC")
    project_end = pd.Timestamp(config["project"]["end_date"]).date()
    hourly = hourly.loc[
        hourly["hour_utc"].ge(archive_start)
        & hourly["hour_local"].dt.date.le(project_end)
    ].copy()
    if hourly.empty:
        raise ValueError("Archive files were found, but none fall inside the configured dates")

    settings = config["qc"]
    hourly = hourly.rename(columns={"raw_pm2_5": "pm2_5"})
    hourly["qc_range"] = hourly["pm2_5"].between(
        float(settings["pm25_min"]), float(settings["pm25_max"]), inclusive="both"
    )
    hourly["qc_spread"] = hourly["spread"].ge(int(settings["minimum_twenty_minute_bins"]))
    hourly = pd.concat(
        [
            _temporal_qc(group, settings)
            for _, group in hourly.groupby(["location_id", "sensor_id"], sort=False)
        ],
        ignore_index=True,
    )
    hourly["qc_pass"] = hourly[["qc_range", "qc_spread", "qc_temporal"]].all(axis=1)
    hourly["location"] = "SC" + hourly["location_id"].astype(int).astype(str)
    hourly["date_local"] = hourly["hour_local"].dt.date.astype(str)
    hourly["data_source"] = "sensor_community"
    hourly["source_qc_code"] = pd.Series(pd.NA, index=hourly.index, dtype="string")
    hourly["qc_source_code"] = pd.Series(pd.NA, index=hourly.index, dtype="boolean")
    hourly["qc_method"] = "range + three 20-minute bins + rolling MAD"

    coordinates = candidates.drop_duplicates(["location_id", "sensor_id"])[
        ["location_id", "sensor_id", "lat", "lon"]
    ]
    hourly = hourly.merge(coordinates, on=["location_id", "sensor_id"], how="left")
    columns = [
        "hour_utc",
        "hour_local",
        "sensor_id",
        "location",
        "location_id",
        "lat",
        "lon",
        "pm2_5",
        "n_observations",
        "spread",
        "date_local",
        "data_source",
        "source_qc_code",
        "qc_method",
        "qc_source_code",
        "qc_range",
        "qc_spread",
        "qc_temporal",
        "qc_pass",
    ]
    hourly = hourly[columns].sort_values(["location_id", "sensor_id", "hour_utc"])
    ensure_parent(config["paths"]["archive_hourly"])
    hourly.to_csv(config["paths"]["archive_hourly"], index=False)
    return hourly


def build_hourly_qc(config: dict) -> pd.DataFrame:
    """Backward-compatible name for the archive-only processing stage."""
    return build_archive_hourly(config)
