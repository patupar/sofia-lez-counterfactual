"""Small, dependency-light GeoJSON point-in-polygon helpers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path


def _point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    """Return True when a point is inside or on a linear ring."""
    inside = False
    j = len(ring) - 1
    for i, (xi, yi, *_) in enumerate(ring):
        xj, yj, *_ = ring[j]
        cross = (yi > y) != (yj > y)
        if cross:
            x_intersection = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x <= x_intersection:
                inside = not inside
        j = i
    return inside


def _point_in_polygon(x: float, y: float, polygon: list[list[list[float]]]) -> bool:
    return bool(polygon and _point_in_ring(x, y, polygon[0])) and not any(
        _point_in_ring(x, y, hole) for hole in polygon[1:]
    )


def iter_polygons(geojson: dict) -> Iterable[list[list[list[float]]]]:
    """Yield Polygon coordinate arrays from a GeoJSON object."""
    if geojson.get("type") == "FeatureCollection":
        for feature in geojson.get("features", []):
            yield from iter_polygons(feature)
    elif geojson.get("type") == "Feature":
        yield from iter_polygons(geojson.get("geometry") or {})
    elif geojson.get("type") == "Polygon":
        yield geojson["coordinates"]
    elif geojson.get("type") == "MultiPolygon":
        yield from geojson["coordinates"]


def load_polygons(path: Path) -> list[list[list[list[float]]]]:
    with path.open(encoding="utf-8") as handle:
        return list(iter_polygons(json.load(handle)))


def point_in_boundary(lon: float, lat: float, polygons: list) -> bool:
    return any(_point_in_polygon(lon, lat, polygon) for polygon in polygons)


def boundary_bounds(polygons: list) -> tuple[float, float, float, float]:
    """Return the combined (minimum longitude, latitude, maximum longitude, latitude)."""
    exterior_points = [point for polygon in polygons for point in polygon[0]]
    longitudes = [point[0] for point in exterior_points]
    latitudes = [point[1] for point in exterior_points]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)
