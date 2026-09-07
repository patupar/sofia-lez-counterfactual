"""Offline tests for the ERA5 request and predictor workflow."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from sofia_lez.meteorology import (
    _expected_local_hours,
    build_era5_requests,
    download_era5,
    prepare_predictors,
)

VARIABLES = [
    "2m_temperature",
    "2m_dewpoint_temperature",
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "surface_pressure",
    "total_precipitation",
    "boundary_layer_height",
]


class _FakeResult:
    def __init__(self, dataset: xr.Dataset) -> None:
        self.dataset = dataset

    def download(self, path: str) -> None:
        self.dataset.to_netcdf(path, engine="netcdf4")


class _FakeCdsClient:
    def __init__(self, dataset: xr.Dataset) -> None:
        self.dataset = dataset
        self.calls: list[tuple[str, dict]] = []

    def retrieve(self, dataset_name: str, request: dict) -> _FakeResult:
        self.calls.append((dataset_name, request))
        return _FakeResult(self.dataset)


def _test_config(tmp_path: Path) -> dict:
    panel_path = tmp_path / "stable_panel.csv"
    pd.DataFrame(
        {
            "location": ["SC100", "SC200"],
            "location_id": [100, 200],
            "sensor_id": [10, 20],
            "lat": [42.70, 42.51],
            "lon": [23.30, 23.49],
            "stable_panel": [True, False],
        }
    ).to_csv(panel_path, index=False)
    return {
        "project": {
            "study_start_date": "2024-03-30",
            "end_date": "2024-04-01",
            "timezone": "Europe/Sofia",
        },
        "sources": {"era5_dataset": "reanalysis-era5-single-levels"},
        "paths": {
            "panel": panel_path,
            "meteorology": tmp_path / "era5",
            "meteorology_ledger": tmp_path / "era5" / "download_ledger.jsonl",
            "predictors": tmp_path / "daily_predictors.csv",
        },
        "meteorology": {
            "raw_file_pattern": "era5_single_levels_{year}.nc",
            "date_padding_days": 0,
            "bbox_padding_degrees": 0.25,
            "status_interval_seconds": 60,
            "grid_assignment": "nearest",
            "variables": VARIABLES,
        },
    }


def _synthetic_era5(config: dict) -> xr.Dataset:
    start = pd.Timestamp(config["project"]["study_start_date"], tz="Europe/Sofia").tz_convert("UTC")
    end = pd.Timestamp("2024-04-02", tz="Europe/Sofia").tz_convert("UTC")
    times = pd.date_range(start, end, freq="h").tz_localize(None)
    latitudes = [42.75, 42.50]
    longitudes = [23.25, 23.50]
    shape = (len(times), len(latitudes), len(longitudes))

    def values(value: float) -> np.ndarray:
        return np.full(shape, value, dtype=float)

    return xr.Dataset(
        {
            "t2m": (("valid_time", "latitude", "longitude"), values(283.15)),
            "d2m": (("valid_time", "latitude", "longitude"), values(278.15)),
            "u10": (("valid_time", "latitude", "longitude"), values(3.0)),
            "v10": (("valid_time", "latitude", "longitude"), values(4.0)),
            "sp": (("valid_time", "latitude", "longitude"), values(100_000.0)),
            "tp": (("valid_time", "latitude", "longitude"), values(0.001)),
            "blh": (("valid_time", "latitude", "longitude"), values(500.0)),
        },
        coords={
            "valid_time": times,
            "latitude": latitudes,
            "longitude": longitudes,
        },
    )


def test_request_uses_only_stable_panel_extent(tmp_path: Path):
    config = _test_config(tmp_path)
    requests = build_era5_requests(config)

    assert len(requests) == 1
    year, path, request = requests[0]
    assert year == 2024
    assert path.name == "era5_single_levels_2024.nc"
    assert request["area"] == [42.95, 23.05, 42.45, 23.55]
    assert request["variable"] == VARIABLES
    assert "2024" in request["year"]


def test_expected_local_hours_include_both_dst_transitions():
    spring = _expected_local_hours("2024-03-30", "2024-04-01", "Europe/Sofia")
    autumn = _expected_local_hours("2024-10-26", "2024-10-28", "Europe/Sofia")

    assert spring["expected_hours"].tolist() == [24, 23, 24]
    assert autumn["expected_hours"].tolist() == [24, 25, 24]


def test_download_and_prepare_predictors_without_network(tmp_path: Path):
    config = _test_config(tmp_path)
    client = _FakeCdsClient(_synthetic_era5(config))

    summary = download_era5(config, client=client)
    predictors = prepare_predictors(config)

    assert summary["downloaded_chunks"] == 1
    assert summary["cached_chunks"] == 0
    assert len(client.calls) == 1
    assert len(predictors) == 3
    assert predictors["meteorology_hours"].tolist() == [24, 23, 24]
    assert predictors["precipitation_sum_mm"].tolist() == pytest.approx([24.0, 23.0, 24.0])
    assert predictors["temperature_mean_c"].tolist() == pytest.approx([10.0, 10.0, 10.0])
    assert predictors["wind_speed_mean_ms"].tolist() == pytest.approx([5.0, 5.0, 5.0])
    assert predictors["surface_pressure_mean_hpa"].tolist() == pytest.approx(
        [1000.0, 1000.0, 1000.0]
    )
    assert predictors["boundary_layer_height_mean_m"].tolist() == [500.0, 500.0, 500.0]
    assert predictors["era5_latitude"].unique().tolist() == [42.75]
    assert predictors["era5_longitude"].unique().tolist() == [23.25]
    assert Path(config["paths"]["predictors"]).exists()

    records = [
        json.loads(line)
        for line in Path(config["paths"]["meteorology_ledger"]).read_text().splitlines()
    ]
    assert records[0]["status"] == "downloaded"
    assert "sha256" in records[0]
    assert "key" not in json.dumps(records[0]).lower()

    second_summary = download_era5(config, client=client)
    assert second_summary["cached_chunks"] == 1
    assert len(client.calls) == 1
