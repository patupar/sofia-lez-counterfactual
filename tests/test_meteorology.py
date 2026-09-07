"""Offline tests for the ERA5 request and predictor workflow."""

from __future__ import annotations

import json
import tempfile
import zipfile
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
    def __init__(self, dataset: xr.Dataset, response_format: str) -> None:
        self.dataset = dataset
        self.response_format = response_format

    def download(self, path: str) -> None:
        if self.response_format == "netcdf":
            self.dataset.to_netcdf(path, engine="netcdf4")
            return
        if self.response_format == "invalid":
            Path(path).write_text("not a NetCDF or ZIP", encoding="utf-8")
            return
        if self.response_format != "zip":
            raise ValueError(f"Unsupported fake response format: {self.response_format}")

        target = Path(path)
        with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
            temporary_directory = Path(temporary)
            instantaneous = temporary_directory / "data_stream-oper_stepType-instant.nc"
            accumulated = temporary_directory / "data_stream-oper_stepType-accum.nc"
            self.dataset.drop_vars("tp").to_netcdf(instantaneous, engine="netcdf4")
            self.dataset[["tp"]].to_netcdf(accumulated, engine="netcdf4")
            with zipfile.ZipFile(target, "w") as archive:
                archive.write(instantaneous, instantaneous.name)
                archive.write(accumulated, accumulated.name)


class _FakeCdsClient:
    def __init__(self, dataset: xr.Dataset, response_format: str = "netcdf") -> None:
        self.dataset = dataset
        self.response_format = response_format
        self.calls: list[tuple[str, dict]] = []

    def retrieve(self, dataset_name: str, request: dict) -> _FakeResult:
        self.calls.append((dataset_name, request))
        return _FakeResult(self.dataset, self.response_format)


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
    # The real request asks for complete calendar months surrounding the study
    # dates, so the synthetic response follows the same contract.
    times = pd.date_range(
        "2024-03-01",
        "2024-05-01",
        freq="h",
        inclusive="left",
    )
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
            "number": 0,
            "expver": ("valid_time", np.full(len(times), "0001")),
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
    client = _FakeCdsClient(_synthetic_era5(config), response_format="zip")

    summary = download_era5(config, client=client)
    predictors = prepare_predictors(config)

    assert summary["downloaded_chunks"] == 1
    assert summary["cached_chunks"] == 0
    assert summary["recovered_chunks"] == 0
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
    assert records[0]["response_format"] == "zip"
    assert records[0]["archive_members"] == [
        "data_stream-oper_stepType-instant.nc",
        "data_stream-oper_stepType-accum.nc",
    ]
    assert "sha256" in records[0]
    assert "key" not in json.dumps(records[0]).lower()

    second_summary = download_era5(config, client=client)
    assert second_summary["cached_chunks"] == 1
    assert len(client.calls) == 1


def test_direct_netcdf_response_remains_supported(tmp_path: Path):
    config = _test_config(tmp_path)
    client = _FakeCdsClient(_synthetic_era5(config), response_format="netcdf")

    summary = download_era5(config, client=client)

    assert summary["downloaded_chunks"] == 1
    record = json.loads(Path(config["paths"]["meteorology_ledger"]).read_text().splitlines()[0])
    assert record["response_format"] == "netcdf"


def test_retained_zip_response_is_recovered_without_new_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    config = _test_config(tmp_path)
    dataset = _synthetic_era5(config)
    part = Path(config["paths"]["meteorology"]) / "era5_single_levels_2024.nc.part"
    part.parent.mkdir(parents=True)
    _FakeResult(dataset, "zip").download(str(part))
    monkeypatch.setattr(
        "sofia_lez.meteorology._default_cds_client",
        lambda: pytest.fail("CDS client should not be created while recovering a valid response"),
    )

    summary = download_era5(config)
    predictors = prepare_predictors(config)

    assert summary["recovered_chunks"] == 1
    assert summary["downloaded_chunks"] == 0
    assert len(predictors) == 3
    assert not zipfile.is_zipfile(
        Path(config["paths"]["meteorology"]) / "era5_single_levels_2024.nc"
    )


def test_invalid_response_reports_the_validation_reason(tmp_path: Path):
    config = _test_config(tmp_path)
    client = _FakeCdsClient(_synthetic_era5(config), response_format="invalid")

    with pytest.raises(RuntimeError, match="neither a readable NetCDF nor a supported ZIP"):
        download_era5(config, client=client)

    part = Path(config["paths"]["meteorology"]) / "era5_single_levels_2024.nc.part"
    assert part.exists()


def test_unusable_retained_response_is_replaced(tmp_path: Path):
    config = _test_config(tmp_path)
    part = Path(config["paths"]["meteorology"]) / "era5_single_levels_2024.nc.part"
    part.parent.mkdir(parents=True)
    part.write_text("interrupted response", encoding="utf-8")
    client = _FakeCdsClient(_synthetic_era5(config), response_format="zip")

    summary = download_era5(config, client=client)

    assert summary["recovered_chunks"] == 0
    assert summary["downloaded_chunks"] == 1
    assert len(client.calls) == 1


def test_missing_requested_hour_is_rejected(tmp_path: Path):
    config = _test_config(tmp_path)
    incomplete = _synthetic_era5(config).isel(valid_time=slice(1, None))
    client = _FakeCdsClient(incomplete, response_format="zip")

    with pytest.raises(RuntimeError, match="missing 1 requested UTC hours"):
        download_era5(config, client=client)


def test_zip_missing_a_configured_variable_is_rejected(tmp_path: Path):
    config = _test_config(tmp_path)
    missing_boundary_layer_height = _synthetic_era5(config).drop_vars("blh")
    client = _FakeCdsClient(missing_boundary_layer_height, response_format="zip")

    with pytest.raises(RuntimeError, match="boundary_layer_height"):
        download_era5(config, client=client)
