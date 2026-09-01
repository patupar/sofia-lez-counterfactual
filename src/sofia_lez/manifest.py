"""Build the Sofia historical location-sensor manifest."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from .config import ensure_parent
from .spatial import boundary_bounds, load_polygons, point_in_boundary

PAIR_PATTERN = re.compile(r"^(SC(?P<location>\d+))_(?P<sensor>\d+)\.csv$", re.IGNORECASE)


def download_boundary(url: str, destination: Path) -> Path:
    """Download the authoritative Sofia municipality GeoJSON if absent."""
    if destination.exists() and destination.stat().st_size:
        return destination
    ensure_parent(destination)
    request = Request(url, headers={"User-Agent": "sofia-lez-counterfactual/0.1"})
    with urlopen(request, timeout=60) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    return destination


def _iso_timestamp(value: float | int | None) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value, unit="s", utc=True).isoformat()


def summarize_pair(path: Path, qc_prefix: str, require_spread: int) -> dict:
    """Summarize one FILTER location-sensor pair without retaining observations."""
    frame = pd.read_csv(
        path,
        usecols=["hour_timestamp", "raw_pm2_5", "spread", "raw_qc"],
        dtype={"raw_qc": "string"},
    )
    timestamps = pd.to_numeric(frame["hour_timestamp"], errors="coerce")
    qc_codes = frame["raw_qc"].astype("string").str.replace(r"\.0$", "", regex=True)
    valid = (
        qc_codes.str.startswith(qc_prefix, na=False)
        & pd.to_numeric(frame["spread"], errors="coerce").eq(require_spread)
        & pd.to_numeric(frame["raw_pm2_5"], errors="coerce").notna()
    )
    valid_timestamps = timestamps[valid]
    return {
        "n_historical_hours": int(timestamps.notna().sum()),
        "first_observation_utc": _iso_timestamp(timestamps.min()),
        "last_observation_utc": _iso_timestamp(timestamps.max()),
        "n_historical_qc_hours": int(valid.sum()),
        "first_qc_observation_utc": _iso_timestamp(valid_timestamps.min()),
        "last_qc_observation_utc": _iso_timestamp(valid_timestamps.max()),
    }


def build_manifest(config: dict) -> pd.DataFrame:
    """Spatially filter FILTER locations and attach each pair's coverage."""
    paths = config["paths"]
    boundary = download_boundary(config["sources"]["sofia_boundary_url"], paths["boundary"])
    polygons = load_polygons(boundary)

    pair_files = []
    relevant_locations = set()
    for csv_path in sorted(paths["bgr_directory"].glob("*.csv")):
        match = PAIR_PATTERN.match(csv_path.name)
        if match:
            pair_files.append((csv_path, match))
            relevant_locations.add(f"SC{match.group('location')}")

    locations = pd.read_csv(paths["sensor_locations"])
    required = {"location", "lat", "lon"}
    if not required.issubset(locations.columns):
        raise ValueError(f"Sensor location table needs columns {sorted(required)}")
    locations = locations.drop_duplicates("location", keep="last").copy()
    locations = locations.loc[locations["location"].isin(relevant_locations)].copy()
    min_lon, min_lat, max_lon, max_lat = boundary_bounds(polygons)
    in_bbox = locations["lon"].between(min_lon, max_lon) & locations["lat"].between(
        min_lat, max_lat
    )
    locations["in_sofia_municipality"] = False
    locations.loc[in_bbox, "in_sofia_municipality"] = [
        point_in_boundary(float(lon), float(lat), polygons)
        for lat, lon in zip(
            locations.loc[in_bbox, "lat"], locations.loc[in_bbox, "lon"], strict=True
        )
    ]
    sofia = locations.loc[locations["in_sofia_municipality"]].set_index("location")

    settings = config["manifest"]
    rows: list[dict] = []
    for csv_path, match in pair_files:
        location = f"SC{match.group('location')}"
        if location not in sofia.index:
            continue
        summary = summarize_pair(
            csv_path,
            str(settings["historical_qc_prefix"]),
            int(settings["require_spread"]),
        )
        rows.append(
            {
                "location": location,
                "location_id": int(match.group("location")),
                "sensor_id": int(match.group("sensor")),
                "lat": float(sofia.at[location, "lat"]),
                "lon": float(sofia.at[location, "lon"]),
                "historical_file": csv_path.name,
                **summary,
            }
        )

    manifest = pd.DataFrame(rows)
    if manifest.empty:
        raise ValueError("No BGR filename pairs matched locations inside the Sofia municipality")
    cutoff = pd.Timestamp(settings["continuing_after"], tz="UTC")
    last_seen = pd.to_datetime(manifest["last_observation_utc"], utc=True)
    manifest["plausible_continuing"] = last_seen.ge(cutoff)
    manifest = manifest.sort_values(["location_id", "sensor_id"]).reset_index(drop=True)
    ensure_parent(paths["manifest"])
    manifest.to_csv(paths["manifest"], index=False)
    return manifest
