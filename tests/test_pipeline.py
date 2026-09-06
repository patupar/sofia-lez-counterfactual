from pathlib import Path

import pandas as pd
import pytest

from sofia_lez.completeness import calculate_completeness, select_stable_panel
from sofia_lez.config import load_config
from sofia_lez.daily import aggregate_daily
from sofia_lez.downloader import candidate_urls
from sofia_lez.manifest import build_manifest
from sofia_lez.qc import _archive_qc_method, _median_absolute_deviation, _temporal_qc
from sofia_lez.sensors import build_unified_hourly
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


def test_median_absolute_deviation_uses_the_current_window_median():
    values = pd.Series([1.0, 2.0, 100.0]).to_numpy()
    assert _median_absolute_deviation(values) == 1.0


def test_temporal_qc_uses_clock_hours_and_retains_configured_safeguards():
    settings = {
        "temporal_window_hours": 360,
        "temporal_min_periods": 72,
        "temporal_mad_multiplier": 8.0,
        "temporal_absolute_floor": 75.0,
    }
    close_hours = pd.date_range("2024-01-01", periods=72, freq="h", tz="UTC")
    separated_spike = pd.DatetimeIndex([pd.Timestamp("2024-02-01", tz="UTC")])
    group = pd.DataFrame(
        {
            "hour_utc": close_hours.append(separated_spike),
            "pm2_5": [10.0] * 72 + [200.0],
        }
    )

    checked = _temporal_qc(group, settings).set_index("hour_utc")

    assert bool(checked.loc[separated_spike[0], "qc_temporal"])

    method = _archive_qc_method(
        {
            **settings,
            "pm25_min": 0.0,
            "pm25_max": 1000.0,
            "minimum_twenty_minute_bins": 3,
        }
    )
    assert "centered 360h" in method
    assert "minimum 72 values" in method
    assert "75.0 ug/m3" in method
    assert "8.0 x 1.4826 x MAD" in method


def test_temporal_qc_applies_absolute_floor_within_a_complete_window():
    settings = {
        "temporal_window_hours": 6,
        "temporal_min_periods": 5,
        "temporal_mad_multiplier": 8.0,
        "temporal_absolute_floor": 75.0,
    }
    hours = pd.date_range("2024-01-01", periods=7, freq="h", tz="UTC")
    group = pd.DataFrame(
        {
            "hour_utc": hours,
            "pm2_5": [10.0, 10.0, 10.0, 80.0, 10.0, 10.0, 10.0],
        }
    )
    checked = _temporal_qc(group, settings).set_index("hour_utc")
    assert bool(checked.loc[hours[3], "qc_temporal"])

    group.loc[3, "pm2_5"] = 100.0
    checked = _temporal_qc(group, settings).set_index("hour_utc")
    assert not bool(checked.loc[hours[3], "qc_temporal"])


def test_sample_pipeline(tmp_path):
    config = load_config(ROOT / "configs/sample.yaml")
    for key in (
        "manifest",
        "filter_hourly",
        "archive_hourly",
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

    hourly = build_unified_hourly(config)
    assert len(hourly) == 3
    assert set(hourly["data_source"]) == {"filter", "sensor_community"}
    assert not hourly.groupby(
        ["location_id", "sensor_id", "date_local"]
    )["data_source"].nunique().gt(1).any()
    historical = hourly.loc[hourly["data_source"].eq("filter")].reset_index(drop=True)
    archive = hourly.loc[hourly["data_source"].eq("sensor_community")].reset_index(drop=True)
    assert list(historical["pm2_5"]) == [20.0, 22.0]
    assert list(historical["qc_pass"]) == [True, False]
    assert archive.loc[0, "pm2_5"] == 21.0
    assert int(archive.loc[0, "spread"]) == 3
    assert bool(archive.loc[0, "qc_pass"])

    daily = aggregate_daily(config)
    assert len(daily) == 2
    assert list(daily["pm2_5"]) == [20.0, 21.0]
    assert list(daily["observed_hours"]) == [2, 1]
    assert daily["qc_daily_hours"].all()
    assert daily["qc_daily_range"].all()
    assert daily["daily_qc_pass"].all()

    years, seasons = calculate_completeness(config)
    assert years["valid_hours"].sum() == 2
    assert "sample_period" in set(seasons["season"])

    panel = select_stable_panel(config)
    assert bool(panel.loc[0, "stable_panel"])


def test_daily_aggregation_applies_exclusive_upper_bound(tmp_path):
    hours = pd.date_range("2024-01-01", periods=18, freq="h", tz="UTC")
    rows = []
    for sensor_id, value in ((1, 249.9), (2, 250.0), (3, 999.9)):
        rows.extend(
            {
                "hour_local": hour,
                "location": f"SC{sensor_id}",
                "location_id": sensor_id,
                "sensor_id": sensor_id,
                "lat": 42.7,
                "lon": 23.3,
                "pm2_5": value,
                "qc_pass": True,
                "data_source": "sensor_community",
            }
            for hour in hours
        )
    hourly_path = tmp_path / "hourly.csv"
    daily_path = tmp_path / "daily.csv"
    year_path = tmp_path / "year.csv"
    season_path = tmp_path / "season.csv"
    pd.DataFrame(rows).to_csv(hourly_path, index=False)
    config = {
        "project": {
            "timezone": "Europe/Sofia",
            "study_start_date": "2024-01-01",
            "end_date": "2024-01-01",
        },
        "paths": {
            "hourly": hourly_path,
            "daily": daily_path,
            "completeness_year": year_path,
            "completeness_season": season_path,
        },
        "aggregation": {
            "minimum_valid_hours_per_day": 18,
            "maximum_daily_pm25_exclusive": 250.0,
        },
        "panel_selection": {
            "post_periods": {"sample_period": ["2024-01-01", "2024-01-01"]},
        },
    }

    daily = aggregate_daily(config).set_index("sensor_id")

    assert daily.loc[1, "pm2_5"] == pytest.approx(249.9)
    assert bool(daily.loc[1, "daily_qc_pass"])
    assert pd.isna(daily.loc[2, "pm2_5"])
    assert pd.isna(daily.loc[3, "pm2_5"])
    assert daily.loc[2, "pm2_5_before_daily_qc"] == 250.0
    assert daily.loc[3, "pm2_5_before_daily_qc"] == pytest.approx(999.9)
    assert not bool(daily.loc[2, "qc_daily_range"])
    assert not bool(daily.loc[3, "qc_daily_range"])

    years, _ = calculate_completeness(config)
    valid_days = years.set_index("sensor_id")["valid_days"]
    assert valid_days.to_dict() == {1: 1, 2: 0, 3: 0}


def test_select_stable_panel_uses_aggregate_pre_and_each_post_period(tmp_path):
    index_values = {
        "location": ["SC1", "SC2"],
        "location_id": [1, 2],
        "sensor_id": [11, 22],
        "lat": [42.70, 42.71],
        "lon": [23.30, 23.31],
    }
    year_rows = []
    for position in range(2):
        pair = {column: values[position] for column, values in index_values.items()}
        for year, valid_days in ((2023, (40, 80)[position]), (2024, (100, 80)[position])):
            year_rows.append(
                {
                    **pair,
                    "year": year,
                    "expected_days": 100,
                    "valid_days": valid_days,
                }
            )

    season_rows = []
    post_completeness = {
        11: {"post_one": 0.70, "post_two": 0.80},
        22: {"post_one": 0.80, "post_two": 0.59},
    }
    for position in range(2):
        pair = {column: values[position] for column, values in index_values.items()}
        for period, completeness in post_completeness[pair["sensor_id"]].items():
            season_rows.append(
                {
                    **pair,
                    "season": period,
                    "expected_days": 100,
                    "valid_days": int(completeness * 100),
                    "day_completeness": completeness,
                }
            )

    year_path = tmp_path / "year.csv"
    season_path = tmp_path / "season.csv"
    panel_path = tmp_path / "panel.csv"
    pd.DataFrame(year_rows).to_csv(year_path, index=False)
    pd.DataFrame(season_rows).to_csv(season_path, index=False)
    config = {
        "paths": {
            "completeness_year": year_path,
            "completeness_season": season_path,
            "panel": panel_path,
        },
        "panel_selection": {
            "minimum_day_fraction": 0.60,
            "pre_start_year": 2023,
            "pre_end_year": 2024,
            "post_periods": {
                "post_one": ["2025-01-01", "2025-03-31"],
                "post_two": ["2025-10-01", "2026-03-31"],
            },
        },
    }

    panel = select_stable_panel(config).set_index("sensor_id")

    assert panel.loc[11, "pre_day_completeness"] == pytest.approx(0.70)
    assert bool(panel.loc[11, "stable_panel"])
    assert not bool(panel.loc[22, "stable_panel"])
    assert panel_path.exists()
