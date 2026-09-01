from pathlib import Path

import pandas as pd

from sofia_lez.completeness import calculate_completeness, select_stable_panel
from sofia_lez.config import load_config
from sofia_lez.daily import aggregate_daily
from sofia_lez.downloader import candidate_urls
from sofia_lez.manifest import build_manifest
from sofia_lez.qc import build_hourly_qc
from sofia_lez.spatial import load_polygons, point_in_boundary

ROOT = Path(__file__).parents[1]


def test_point_in_boundary():
    polygons = load_polygons(ROOT / "sample_data/sofia_boundary.geojson")
    assert point_in_boundary(23.32, 42.70, polygons)
    assert not point_in_boundary(23.32, 43.10, polygons)


def test_archive_url_candidates_cover_both_layouts():
    urls = candidate_urls(
        "https://archive.sensor.community",
        pd.Timestamp("2024-01-01").date(),
        "sds011",
        10,
    )
    assert "https://archive.sensor.community/2024-01-01/2024-01-01_sds011_sensor_10.csv" in urls
    legacy_gzip = (
        "https://archive.sensor.community/2024/2024-01-01/"
        "2024-01-01_sds011_sensor_10.csv.gz"
    )
    assert legacy_gzip in urls


def test_sample_pipeline(tmp_path):
    config = load_config(ROOT / "configs/sample.yaml")
    for key in (
        "manifest",
        "hourly",
        "completeness_year",
        "completeness_season",
        "panel",
        "daily",
    ):
        config["paths"][key] = tmp_path / f"{key}.csv"

    manifest = build_manifest(config)
    assert list(manifest["location"]) == ["SC100"]
    assert bool(manifest.loc[0, "plausible_continuing"])

    hourly = build_hourly_qc(config)
    assert len(hourly) == 1
    assert hourly.loc[0, "raw_pm2_5"] == 21.0
    assert int(hourly.loc[0, "spread"]) == 3
    assert bool(hourly.loc[0, "qc_pass"])

    years, seasons = calculate_completeness(config)
    assert years.loc[0, "valid_hours"] == 1
    assert "sample_period" in set(seasons["season"])

    panel = select_stable_panel(config)
    assert bool(panel.loc[0, "stable_panel"])

    daily = aggregate_daily(config)
    assert daily.loc[0, "pm2_5"] == 21.0
    assert bool(daily.loc[0, "daily_qc_pass"])
