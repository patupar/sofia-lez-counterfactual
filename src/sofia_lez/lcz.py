"""Prepare grouped Local Climate Zone fractions around stable sensor locations."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import rasterio
from rasterio.windows import Window, from_bounds

from .config import ensure_parent

PAIR_COLUMNS = ["location", "location_id", "sensor_id", "lat", "lon"]
VALID_LCZ_CLASSES = set(range(1, 18))
EARTH_RADIUS_M = 6_371_008.8


def _stable_sensor_pairs(config: dict) -> pd.DataFrame:
    panel = pd.read_csv(config["paths"]["panel"])
    required = {*PAIR_COLUMNS, "stable_panel"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"Stable-panel table is missing columns: {missing}")
    accepted = panel["stable_panel"].astype(str).str.lower().eq("true")
    pairs = panel.loc[accepted, PAIR_COLUMNS].copy()
    if pairs.empty:
        raise ValueError("Stage 5 did not select any stable sensor-location pairs")
    if pairs.duplicated(["location_id", "sensor_id"]).any():
        raise ValueError("Stable-panel table contains duplicate sensor-location pairs")
    return pairs.sort_values(["location_id", "sensor_id"]).reset_index(drop=True)


def _class_groups(config: dict) -> dict[str, list[int]]:
    groups = config.get("lcz", {}).get("class_groups")
    if not groups:
        raise ValueError("The LCZ configuration must define class_groups")
    normalised = {name: [int(value) for value in values] for name, values in groups.items()}
    assigned = [value for values in normalised.values() for value in values]
    if len(assigned) != len(set(assigned)):
        raise ValueError("Each LCZ class must belong to exactly one configured group")
    if set(assigned) != VALID_LCZ_CLASSES:
        raise ValueError("LCZ class groups must cover classes 1-17 exactly once")
    return normalised


def _haversine_distance_m(
    longitudes: np.ndarray,
    latitudes: np.ndarray,
    centre_lon: float,
    centre_lat: float,
) -> np.ndarray:
    centre_lat_rad = math.radians(centre_lat)
    latitudes_rad = np.radians(latitudes)
    latitude_difference = latitudes_rad - centre_lat_rad
    longitude_difference = np.radians(longitudes - centre_lon)
    haversine = (
        np.sin(latitude_difference / 2.0) ** 2
        + math.cos(centre_lat_rad)
        * np.cos(latitudes_rad)
        * np.sin(longitude_difference / 2.0) ** 2
    )
    return 2.0 * EARTH_RADIUS_M * np.arcsin(np.sqrt(haversine))


def _buffer_window(
    dataset: rasterio.io.DatasetReader,
    lon: float,
    lat: float,
    radius_m: float,
) -> Window:
    latitude_radius = math.degrees(radius_m / EARTH_RADIUS_M)
    longitude_radius = math.degrees(
        radius_m / (EARTH_RADIUS_M * math.cos(math.radians(lat)))
    )
    bounds = (
        lon - longitude_radius,
        lat - latitude_radius,
        lon + longitude_radius,
        lat + latitude_radius,
    )
    raster_bounds = dataset.bounds
    if (
        bounds[0] < raster_bounds.left
        or bounds[1] < raster_bounds.bottom
        or bounds[2] > raster_bounds.right
        or bounds[3] > raster_bounds.top
    ):
        raise ValueError(f"The {radius_m:g} m LCZ buffer around ({lat}, {lon}) leaves the raster")
    window = from_bounds(*bounds, transform=dataset.transform)
    column_start = math.floor(window.col_off)
    row_start = math.floor(window.row_off)
    column_stop = math.ceil(window.col_off + window.width)
    row_stop = math.ceil(window.row_off + window.height)
    return Window(
        column_start,
        row_start,
        column_stop - column_start,
        row_stop - row_start,
    )


def _buffer_classes(
    dataset: rasterio.io.DatasetReader,
    lon: float,
    lat: float,
    radius_m: float,
) -> np.ndarray:
    window = _buffer_window(dataset, lon, lat, radius_m)
    values = dataset.read(1, window=window, masked=True)
    rows, columns = np.indices(values.shape)
    longitudes, latitudes = rasterio.transform.xy(
        dataset.window_transform(window), rows, columns, offset="center"
    )
    longitudes = np.asarray(longitudes).reshape(values.shape)
    latitudes = np.asarray(latitudes).reshape(values.shape)
    inside = _haversine_distance_m(longitudes, latitudes, lon, lat) <= radius_m
    valid = inside & ~np.ma.getmaskarray(values)
    classes = np.asarray(values)[valid].astype(int)
    invalid = sorted(set(classes.tolist()) - VALID_LCZ_CLASSES)
    if invalid:
        raise ValueError(
            f"LCZ raster contains unsupported classes inside a sensor buffer: {invalid}"
        )
    if not len(classes):
        raise ValueError(f"No valid LCZ pixels occur within {radius_m:g} m of ({lat}, {lon})")
    return classes


def _sensor_features(
    pair: pd.Series,
    dataset: rasterio.io.DatasetReader,
    radius_m: float,
    groups: dict[str, list[int]],
) -> dict[str, Any]:
    classes = _buffer_classes(
        dataset,
        lon=float(pair["lon"]),
        lat=float(pair["lat"]),
        radius_m=radius_m,
    )
    counts = np.bincount(classes, minlength=18)
    total = int(len(classes))
    row: dict[str, Any] = {
        **pair[PAIR_COLUMNS].to_dict(),
        "lcz_buffer_radius_m": radius_m,
        "lcz_valid_pixels": total,
        "lcz_dominant_class": int(np.flatnonzero(counts == counts.max())[0]),
    }
    for class_number in range(1, 18):
        row[f"lcz_class_{class_number:02d}_fraction"] = counts[class_number] / total
    for name, members in groups.items():
        row[name] = counts[members].sum() / total
    return row


def prepare_lcz_features(config: dict) -> pd.DataFrame:
    """Calculate five grouped LCZ fractions inside a buffer around every stable pair."""
    pairs = _stable_sensor_pairs(config)
    groups = _class_groups(config)
    radius_m = float(config.get("lcz", {}).get("buffer_radius_m", 500))
    if radius_m <= 0:
        raise ValueError("LCZ buffer_radius_m must be positive")
    raster_path = Path(config["paths"]["lcz_raster"])
    if not raster_path.exists():
        raise FileNotFoundError(
            f"LCZ raster not found: {raster_path}. Place the clipped GeoTIFF at this path."
        )

    with rasterio.open(raster_path) as dataset:
        if dataset.count != 1:
            raise ValueError("The LCZ source must be a single-band raster")
        if dataset.crs is None or dataset.crs.to_epsg() != 4326:
            raise ValueError("The LCZ source must use EPSG:4326")
        rows = [
            _sensor_features(pair, dataset, radius_m, groups)
            for _, pair in pairs.iterrows()
        ]

    features = pd.DataFrame(rows)
    grouped_columns = list(groups)
    if not features[grouped_columns].apply(lambda column: column.between(0, 1).all()).all():
        raise ValueError("Grouped LCZ fractions must remain between zero and one")
    grouped_sum = features[grouped_columns].sum(axis=1)
    if not np.allclose(grouped_sum, 1.0, atol=1e-9):
        raise ValueError("Grouped LCZ fractions must sum to one for every sensor-location pair")
    if features.duplicated(["location_id", "sensor_id"]).any():
        raise ValueError("Prepared LCZ table contains duplicate sensor-location pairs")

    output = ensure_parent(Path(config["paths"]["lcz_features"]))
    part = output.with_suffix(output.suffix + ".part")
    features.to_csv(part, index=False)
    part.replace(output)
    return features
