"""Download and prepare hourly ERA5 data as daily sensor-level predictors."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
import threading
import time
import zipfile
from collections.abc import Iterable
from contextlib import ExitStack
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import xarray as xr

from .config import ensure_parent

ERA5_SHORT_NAMES = {
    "2m_temperature": "t2m",
    "2m_dewpoint_temperature": "d2m",
    "10m_u_component_of_wind": "u10",
    "10m_v_component_of_wind": "v10",
    "surface_pressure": "sp",
    "total_precipitation": "tp",
    "boundary_layer_height": "blh",
}


def _stable_panel(config: dict) -> pd.DataFrame:
    """Read the Stage 5 output and retain only accepted sensor-location pairs."""
    panel = pd.read_csv(config["paths"]["panel"])
    required = {"location", "location_id", "sensor_id", "lat", "lon", "stable_panel"}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError(f"Stable-panel table is missing columns: {missing}")
    accepted = panel["stable_panel"].astype(str).str.lower().eq("true")
    panel = panel.loc[accepted, sorted(required - {"stable_panel"})].copy()
    if panel.empty:
        raise ValueError("Stage 5 did not select any stable sensor-location pairs")
    if panel.duplicated(["location_id", "sensor_id"]).any():
        raise ValueError("Stable-panel table contains duplicate sensor-location pairs")
    return panel.sort_values(["location_id", "sensor_id"]).reset_index(drop=True)


def _study_bounds_utc(config: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return inclusive start and exclusive end instants for Sofia local dates."""
    project = config["project"]
    timezone = project["timezone"]
    start = pd.Timestamp(project["study_start_date"], tz=timezone)
    end_date = pd.Timestamp(project["end_date"]).date() + timedelta(days=1)
    end_exclusive = pd.Timestamp(end_date, tz=timezone)
    return start.tz_convert("UTC"), end_exclusive.tz_convert("UTC")


def _request_months(config: dict) -> dict[int, list[str]]:
    """Return the year/month chunks needed around the local-date study window."""
    start, end_exclusive = _study_bounds_utc(config)
    padding = pd.to_timedelta(int(config["meteorology"].get("date_padding_days", 1)), unit="D")
    first = (start - padding).date().replace(day=1)
    last = (end_exclusive + padding).date().replace(day=1)
    months = pd.date_range(first, last, freq="MS")
    chunks: dict[int, list[str]] = {}
    for month in months:
        chunks.setdefault(month.year, []).append(f"{month.month:02d}")
    return chunks


def era5_area(config: dict, panel: pd.DataFrame | None = None) -> list[float]:
    """Return CDS area order [north, west, south, east] around the stable panel."""
    panel = _stable_panel(config) if panel is None else panel
    padding = float(config["meteorology"]["bbox_padding_degrees"])
    return [
        round(float(panel["lat"].max()) + padding, 6),
        round(float(panel["lon"].min()) - padding, 6),
        round(float(panel["lat"].min()) - padding, 6),
        round(float(panel["lon"].max()) + padding, 6),
    ]


def build_era5_requests(config: dict) -> list[tuple[int, Path, dict[str, Any]]]:
    """Build auditable monthly CDS requests without contacting the service."""
    panel = _stable_panel(config)
    settings = config["meteorology"]
    variables = list(settings["variables"])
    missing = sorted(set(ERA5_SHORT_NAMES) - set(variables))
    unsupported = sorted(set(variables) - set(ERA5_SHORT_NAMES))
    if missing:
        raise ValueError(f"Required ERA5 variables are missing from configuration: {missing}")
    if unsupported:
        raise ValueError(f"Unsupported ERA5 variables in configuration: {unsupported}")
    raw_directory = Path(config["paths"]["meteorology"])
    pattern = settings.get("raw_file_pattern", "era5_single_levels_{year}_{month}.nc")
    if "{year}" not in pattern or "{month}" not in pattern:
        raise ValueError(
            "meteorology.raw_file_pattern must include both {year} and {month} "
            "so every monthly ERA5 request has a unique cache file"
        )
    days = [f"{day:02d}" for day in range(1, 32)]
    hours = [f"{hour:02d}:00" for hour in range(24)]
    requests = []
    for year, months in _request_months(config).items():
        for month in months:
            request = {
                "product_type": ["reanalysis"],
                "variable": variables,
                "year": [str(year)],
                "month": [month],
                "day": days,
                "time": hours,
                "data_format": "netcdf",
                "download_format": "unarchived",
                "area": era5_area(config, panel),
            }
            target = raw_directory / pattern.format(year=year, month=month)
            requests.append((year, target, request))
    paths = [path for _, path, _ in requests]
    if len(paths) != len(set(paths)):
        raise ValueError(
            "meteorology.raw_file_pattern must include both {year} and {month} "
            "so every monthly ERA5 request has a unique cache file"
        )
    return requests


def _find_time_name(dataset: xr.Dataset) -> str:
    for name in ("valid_time", "time"):
        if name in dataset.coords or name in dataset.variables:
            return name
    raise ValueError("ERA5 file has neither a 'valid_time' nor a 'time' coordinate")


def _find_variable(dataset: xr.Dataset, cds_name: str) -> str:
    short_name = ERA5_SHORT_NAMES[cds_name]
    if short_name in dataset.data_vars:
        return short_name
    if cds_name in dataset.data_vars:
        return cds_name
    expected = cds_name.replace("_", " ").lower()
    for name, variable in dataset.data_vars.items():
        descriptions = {
            str(variable.attrs.get("long_name", "")).lower(),
            str(variable.attrs.get("standard_name", "")).replace("_", " ").lower(),
        }
        if expected in descriptions:
            return name
    raise ValueError(f"ERA5 file is missing configured variable '{cds_name}'")


def _collapse_expver(array: xr.DataArray) -> xr.DataArray:
    """Combine ERA5/ERA5T expver slices when both occur in one file."""
    if "expver" not in array.dims:
        return array
    combined = array.isel(expver=0, drop=True)
    for index in range(1, array.sizes["expver"]):
        combined = combined.combine_first(array.isel(expver=index, drop=True))
    return combined


def _normalise_dataset(
    dataset: xr.Dataset,
    configured_variables: Iterable[str],
    *,
    require_all: bool = True,
) -> xr.Dataset:
    """Return the configured variables under stable ERA5 short names."""
    arrays = {}
    missing = []
    for cds_name in configured_variables:
        try:
            source_name = _find_variable(dataset, cds_name)
        except ValueError:
            missing.append(cds_name)
            continue
        arrays[ERA5_SHORT_NAMES[cds_name]] = _collapse_expver(dataset[source_name])
    if missing and require_all:
        raise ValueError(f"ERA5 file is missing configured variables: {missing}")
    if not arrays:
        raise ValueError("ERA5 file contains none of the configured variables")
    normalised = xr.Dataset(arrays)
    time_name = _find_time_name(normalised)
    if time_name != "time":
        if "time" in normalised.coords and "time" not in normalised.dims:
            normalised = normalised.drop_vars("time")
        normalised = normalised.rename({time_name: "time"})
    for coordinate in ("latitude", "longitude"):
        if coordinate not in normalised.coords:
            raise ValueError(f"ERA5 file is missing coordinate '{coordinate}'")
    nuisance_coordinates = [
        name
        for name in normalised.coords
        if name not in {"time", "latitude", "longitude"} and name not in normalised.dims
    ]
    if nuisance_coordinates:
        normalised = normalised.drop_vars(nuisance_coordinates)
    return normalised


def _expected_request_times(request: dict[str, Any]) -> pd.DatetimeIndex:
    """Return all valid UTC hours represented by one CDS request."""
    ranges = []
    year = int(request["year"][0])
    requested_days = {int(value) for value in request["day"]}
    requested_hours = {int(value.split(":")[0]) for value in request["time"]}
    for month_text in request["month"]:
        month = int(month_text)
        start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
        end = start + pd.offsets.MonthBegin(1)
        hours = pd.date_range(start, end, freq="h", inclusive="left")
        ranges.append(hours[hours.day.isin(requested_days) & hours.hour.isin(requested_hours)])
    if not ranges:
        return pd.DatetimeIndex([], tz="UTC")
    return ranges[0].append(ranges[1:])


def _validate_era5_file(
    path: Path,
    configured_variables: Iterable[str],
    request: dict[str, Any] | None = None,
) -> None:
    """Raise a useful error when a cached or downloaded ERA5 file is unsuitable."""
    if not path.exists():
        raise ValueError(f"file does not exist: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"file is empty: {path}")
    if zipfile.is_zipfile(path):
        raise ValueError("CDS returned a ZIP archive that has not yet been normalised")
    try:
        with xr.open_dataset(path, engine="netcdf4") as dataset:
            normalised = _normalise_dataset(dataset, configured_variables)
            if normalised.sizes.get("time", 0) == 0:
                raise ValueError("ERA5 file has an empty time coordinate")
            for coordinate in ("latitude", "longitude"):
                if normalised.sizes.get(coordinate, 0) == 0:
                    raise ValueError(f"ERA5 file has an empty {coordinate} coordinate")
            times = pd.DatetimeIndex(pd.to_datetime(normalised["time"].values, utc=True))
            if times.has_duplicates:
                raise ValueError("ERA5 file contains duplicate timestamps")
            if not times.is_monotonic_increasing:
                raise ValueError("ERA5 timestamps are not in increasing order")
            if request is not None:
                expected = _expected_request_times(request)
                missing = expected.difference(times)
                if len(missing):
                    preview = [str(value) for value in missing[:5]]
                    raise ValueError(
                        f"ERA5 file is missing {len(missing)} requested UTC hours; "
                        f"first missing: {preview}"
                    )
    except OSError as exc:
        raise ValueError(f"file is neither a readable NetCDF nor a supported ZIP: {exc}") from exc


def _valid_era5_file(
    path: Path,
    configured_variables: Iterable[str],
    request: dict[str, Any] | None = None,
) -> bool:
    try:
        _validate_era5_file(path, configured_variables, request)
    except ValueError:
        return False
    return True


def _normalise_cds_download(
    path: Path,
    configured_variables: list[str],
) -> dict[str, Any]:
    """Convert a split CDS ZIP response into the single NetCDF used by later stages."""
    if not zipfile.is_zipfile(path):
        _validate_era5_file(path, configured_variables)
        return {"response_format": "netcdf", "archive_members": []}

    with zipfile.ZipFile(path) as archive:
        members = [
            member
            for member in archive.infolist()
            if not member.is_dir() and Path(member.filename).suffix.lower() in {".nc", ".nc4"}
        ]
        if not members:
            raise ValueError("CDS ZIP response contains no NetCDF files")
        encrypted = [member.filename for member in members if member.flag_bits & 0x1]
        if encrypted:
            raise ValueError(f"CDS ZIP response contains encrypted members: {encrypted}")

        with tempfile.TemporaryDirectory(prefix="era5_", dir=path.parent) as temporary:
            temporary_directory = Path(temporary)
            extracted_paths = []
            for index, member in enumerate(members):
                extracted = temporary_directory / f"member_{index}.nc"
                with archive.open(member) as source, extracted.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                extracted_paths.append(extracted)

            normalised_path = temporary_directory / "combined.nc"
            with ExitStack() as stack:
                pieces = []
                for extracted in extracted_paths:
                    dataset = stack.enter_context(xr.open_dataset(extracted, engine="netcdf4"))
                    try:
                        piece = _normalise_dataset(
                            dataset,
                            configured_variables,
                            require_all=False,
                        )
                    except ValueError as exc:
                        if "none of the configured variables" in str(exc):
                            continue
                        raise
                    pieces.append(piece)
                if not pieces:
                    raise ValueError(
                        "CDS ZIP NetCDF files contain none of the configured variables"
                    )
                combined = xr.merge(pieces, join="outer", compat="no_conflicts")
                combined = _normalise_dataset(combined, configured_variables)
                combined.to_netcdf(normalised_path, engine="netcdf4")
            normalised_path.replace(path)

    _validate_era5_file(path, configured_variables)
    return {
        "response_format": "zip",
        "archive_members": [member.filename for member in members],
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _append_ledger(path: Path, record: dict[str, Any]) -> None:
    ensure_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _format_duration(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds):
        return "calculating"
    seconds = max(0, round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class _StatusTicker:
    """Print periodic chunk status while the blocking CDS request is running."""

    def __init__(
        self,
        *,
        chunk_label: str,
        completed: int,
        total: int,
        estimated_remaining: float | None,
        interval_seconds: int,
    ) -> None:
        self.chunk_label = chunk_label
        self.completed = completed
        self.total = total
        self.estimated_remaining = estimated_remaining
        self.interval_seconds = max(1, interval_seconds)
        self.started = time.monotonic()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _message(self) -> str:
        elapsed = time.monotonic() - self.started
        progress = self.completed / self.total if self.total else 0.0
        return (
            f"[ERA5 {self.chunk_label}] request active | overall "
            f"{self.completed}/{self.total} "
            f"({progress:.0%}) "
            f"| chunk elapsed {_format_duration(elapsed)} "
            f"| estimated remaining {_format_duration(self.estimated_remaining)}"
        )

    def _run(self) -> None:
        while not self.stopped.wait(self.interval_seconds):
            print(self._message(), flush=True)

    def __enter__(self) -> _StatusTicker:
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stopped.set()
        self.thread.join(timeout=1)


def _default_cds_client():
    """Create a CDS client using its standard external credential lookup."""
    try:
        import cdsapi
    except ImportError as exc:  # pragma: no cover - installation error
        raise RuntimeError("cdsapi is not installed; run 'python -m pip install -e .'") from exc
    try:
        return cdsapi.Client(quiet=False, progress=True)
    except Exception as exc:
        raise RuntimeError(
            "CDS credentials were not found. Configure ~/.cdsapirc or the standard "
            "CDSAPI_URL and CDSAPI_KEY environment variables."
        ) from exc


def _migrate_legacy_single_month_cache(
    config: dict,
    requests: list[tuple[int, Path, dict[str, Any]]],
    variables: list[str],
) -> None:
    """Rename a valid legacy annual cache when that year needs only one month."""
    by_year: dict[int, list[tuple[Path, dict[str, Any]]]] = {}
    for year, target, request in requests:
        by_year.setdefault(year, []).append((target, request))

    raw_directory = Path(config["paths"]["meteorology"])
    for year, chunks in by_year.items():
        if len(chunks) != 1:
            continue
        target, request = chunks[0]
        legacy = raw_directory / f"era5_single_levels_{year}.nc"
        if legacy == target or target.exists():
            continue
        if _valid_era5_file(legacy, variables, request):
            ensure_parent(target)
            legacy.replace(target)
            print(
                f"[ERA5 {year}-{request['month'][0]}] migrated legacy annual cache",
                flush=True,
            )
            continue
        legacy_part = legacy.with_suffix(legacy.suffix + ".part")
        target_part = target.with_suffix(target.suffix + ".part")
        if legacy_part.exists() and not target_part.exists():
            ensure_parent(target_part)
            legacy_part.replace(target_part)


def download_era5(config: dict, client: object | None = None) -> dict[str, Any]:
    """Download resumable monthly ERA5 NetCDF chunks and record their provenance."""
    requests = build_era5_requests(config)
    variables = list(config["meteorology"]["variables"])
    ledger = Path(config["paths"]["meteorology_ledger"])
    dataset_name = config["sources"]["era5_dataset"]
    interval = int(config["meteorology"].get("status_interval_seconds", 30))
    resolved_client = client
    downloaded = 0
    cached = 0
    recovered = 0
    completed = 0
    chunk_durations: list[float] = []

    _migrate_legacy_single_month_cache(config, requests, variables)

    for position, (year, target, request) in enumerate(requests):
        chunk_label = f"{year}-{request['month'][0]}"
        ensure_parent(target)
        if _valid_era5_file(target, variables, request):
            cached += 1
            completed += 1
            progress = completed / len(requests)
            print(
                f"[ERA5 {chunk_label}] cached | overall "
                f"{completed}/{len(requests)} ({progress:.0%})",
                flush=True,
            )
            _append_ledger(
                ledger,
                {
                    "dataset": dataset_name,
                    "year": year,
                    "month": request["month"][0],
                    "status": "cached",
                    "path": str(target),
                    "sha256": _sha256(target),
                    "request": request,
                },
            )
            continue

        part = target.with_suffix(target.suffix + ".part")
        if part.exists():
            try:
                response = _normalise_cds_download(part, variables)
                _validate_era5_file(part, variables, request)
                part.replace(target)
            except ValueError as exc:
                print(
                    f"[ERA5 {chunk_label}] discarded unusable partial response: {exc}",
                    flush=True,
                )
                part.unlink(missing_ok=True)
            else:
                recovered += 1
                completed += 1
                checksum = _sha256(target)
                _append_ledger(
                    ledger,
                    {
                        "dataset": dataset_name,
                        "year": year,
                        "month": request["month"][0],
                        "status": "recovered",
                        "path": str(target),
                        "size_bytes": target.stat().st_size,
                        "sha256": checksum,
                        "request": request,
                        **response,
                    },
                )
                print(
                    f"[ERA5 {chunk_label}] recovered retained response | overall "
                    f"{completed}/{len(requests)} ({completed / len(requests):.0%})",
                    flush=True,
                )
                continue
        average = sum(chunk_durations) / len(chunk_durations) if chunk_durations else None
        remaining_chunks = len(requests) - position
        estimated_remaining = average * remaining_chunks if average is not None else None
        print(
            f"[ERA5 {chunk_label}] starting request {completed + 1}/{len(requests)} "
            f"| ETA {_format_duration(estimated_remaining)}",
            flush=True,
        )
        started = time.monotonic()
        response: dict[str, Any] = {}
        try:
            if resolved_client is None:
                resolved_client = _default_cds_client()
            with _StatusTicker(
                chunk_label=chunk_label,
                completed=completed,
                total=len(requests),
                estimated_remaining=estimated_remaining,
                interval_seconds=interval,
            ):
                result = resolved_client.retrieve(dataset_name, request)
                result.download(str(part))
            response = _normalise_cds_download(part, variables)
            _validate_era5_file(part, variables, request)
            part.replace(target)
        except Exception as exc:
            _append_ledger(
                ledger,
                {
                    "dataset": dataset_name,
                    "year": year,
                    "month": request["month"][0],
                    "status": "failed",
                    "path": str(target),
                    "error_type": type(exc).__name__,
                    "failure_stage": "retrieve_or_validate",
                    "request": request,
                },
            )
            raise RuntimeError(
                f"ERA5 request for {chunk_label} failed during retrieval or validation: {exc}. "
                "The .part response is retained when available and will be checked on the next run."
            ) from exc

        duration = time.monotonic() - started
        chunk_durations.append(duration)
        downloaded += 1
        completed += 1
        average = sum(chunk_durations) / len(chunk_durations)
        remaining_chunks = len(requests) - completed
        estimated_remaining = average * remaining_chunks
        checksum = _sha256(target)
        _append_ledger(
            ledger,
            {
                "dataset": dataset_name,
                "year": year,
                "month": request["month"][0],
                "status": "downloaded",
                "path": str(target),
                "size_bytes": target.stat().st_size,
                "sha256": checksum,
                "elapsed_seconds": round(duration, 3),
                "request": request,
                **response,
            },
        )
        print(
            f"[ERA5 {chunk_label}] complete in {_format_duration(duration)} | overall "
            f"{completed}/{len(requests)} ({completed / len(requests):.0%}) "
            f"| ETA {_format_duration(estimated_remaining)}",
            flush=True,
        )

    return {
        "requested_chunks": len(requests),
        "downloaded_chunks": downloaded,
        "cached_chunks": cached,
        "recovered_chunks": recovered,
        "raw_directory": str(config["paths"]["meteorology"]),
        "ledger": str(ledger),
    }


def _nearest_grid_mapping(dataset: xr.Dataset, panel: pd.DataFrame) -> pd.DataFrame:
    latitudes = np.asarray(dataset["latitude"].values, dtype=float)
    longitudes = np.asarray(dataset["longitude"].values, dtype=float)
    pair_latitudes = panel["lat"].to_numpy(dtype=float)
    pair_longitudes = panel["lon"].to_numpy(dtype=float)
    if longitudes.min() >= 0 and np.any(pair_longitudes < 0):
        pair_longitudes = pair_longitudes % 360
    nearest_latitudes = latitudes[np.abs(latitudes[:, None] - pair_latitudes).argmin(axis=0)]
    nearest_longitudes = longitudes[np.abs(longitudes[:, None] - pair_longitudes).argmin(axis=0)]
    mapping = panel.copy()
    mapping["era5_latitude"] = nearest_latitudes
    mapping["era5_longitude"] = nearest_longitudes
    cells = pd.Series(
        [
            f"{latitude:.10f},{longitude:.10f}"
            for latitude, longitude in zip(nearest_latitudes, nearest_longitudes, strict=True)
        ],
        dtype="string",
    )
    mapping["era5_grid_id"] = pd.factorize(cells, sort=True)[0]
    return mapping


def _hourly_grid_frame(
    path: Path,
    configured_variables: list[str],
    grid_cells: pd.DataFrame,
) -> pd.DataFrame:
    with xr.open_dataset(path, engine="netcdf4") as source:
        dataset = _normalise_dataset(source, configured_variables)
        selected = dataset.sel(
            latitude=xr.DataArray(grid_cells["era5_latitude"], dims="era5_grid_id"),
            longitude=xr.DataArray(grid_cells["era5_longitude"], dims="era5_grid_id"),
            method="nearest",
        ).load()
    selected = selected.assign_coords(
        era5_grid_id=("era5_grid_id", grid_cells["era5_grid_id"].to_numpy())
    )
    frame = selected.to_dataframe().reset_index()
    frame["time_utc"] = pd.to_datetime(frame["time"], utc=True)
    short_names = [ERA5_SHORT_NAMES[name] for name in configured_variables]
    return frame[["era5_grid_id", "time_utc", *short_names]]


def _relative_humidity(temperature_c: pd.Series, dewpoint_c: pd.Series) -> pd.Series:
    """Calculate relative humidity with the Magnus saturation-vapour relation."""
    numerator = np.exp((17.625 * dewpoint_c) / (243.04 + dewpoint_c))
    denominator = np.exp((17.625 * temperature_c) / (243.04 + temperature_c))
    return (100.0 * numerator / denominator).clip(lower=0.0, upper=100.0)


def _expected_local_hours(start: str, end: str, timezone: str) -> pd.DataFrame:
    dates = pd.date_range(start, end, freq="D")
    rows = []
    for date in dates:
        day_start = pd.Timestamp(date.date(), tz=timezone)
        day_end = pd.Timestamp(date.date() + timedelta(days=1), tz=timezone)
        rows.append(
            {
                "date": date.date(),
                "expected_hours": int(
                    (day_end.tz_convert("UTC") - day_start.tz_convert("UTC")).total_seconds() / 3600
                ),
            }
        )
    return pd.DataFrame(rows)


def _heating_season(date: object) -> str | None:
    timestamp = pd.Timestamp(date)
    if timestamp.month <= 3:
        return f"{timestamp.year - 1}-{timestamp.year}"
    if timestamp.month >= 10:
        return f"{timestamp.year}-{timestamp.year + 1}"
    return None


def prepare_predictors(config: dict) -> pd.DataFrame:
    """Convert cached ERA5 hours into one predictor row per stable pair and local date."""
    assignment = config["meteorology"].get("grid_assignment", "nearest")
    if assignment != "nearest":
        raise ValueError(f"Unsupported ERA5 grid assignment: {assignment!r}")
    panel = _stable_panel(config)
    requests = build_era5_requests(config)
    paths = [path for _, path, _ in requests]
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(f"ERA5 raw chunks are missing: {missing}")
    variables = list(config["meteorology"]["variables"])

    with xr.open_dataset(paths[0], engine="netcdf4") as source:
        first_dataset = _normalise_dataset(source, variables)
        mapping = _nearest_grid_mapping(first_dataset, panel)
    grid_cells = mapping[["era5_grid_id", "era5_latitude", "era5_longitude"]].drop_duplicates(
        "era5_grid_id"
    )

    hourly = pd.concat(
        [_hourly_grid_frame(path, variables, grid_cells) for path in paths],
        ignore_index=True,
    )
    if hourly.duplicated(["era5_grid_id", "time_utc"]).any():
        raise ValueError("ERA5 chunks contain overlapping grid-cell timestamps")
    hourly = hourly.sort_values(["era5_grid_id", "time_utc"]).reset_index(drop=True)
    required_short_names = [ERA5_SHORT_NAMES[name] for name in variables]
    missing_values = hourly[required_short_names].isna().sum()
    if missing_values.any():
        details = missing_values[missing_values.gt(0)].to_dict()
        raise ValueError(f"ERA5 source contains missing configured values: {details}")

    hourly["temperature_c"] = hourly["t2m"] - 273.15
    hourly["dewpoint_c"] = hourly["d2m"] - 273.15
    hourly["relative_humidity_pct"] = _relative_humidity(
        hourly["temperature_c"], hourly["dewpoint_c"]
    )
    hourly["wind_speed_ms"] = np.hypot(hourly["u10"], hourly["v10"])
    hourly["surface_pressure_hpa"] = hourly["sp"] / 100.0
    hourly["precipitation_mm"] = hourly["tp"] * 1000.0
    if hourly["precipitation_mm"].lt(-1e-6).any():
        raise ValueError("ERA5 total precipitation contains materially negative values")
    hourly["precipitation_mm"] = hourly["precipitation_mm"].clip(lower=0.0)

    start_utc, end_exclusive_utc = _study_bounds_utc(config)
    timezone = config["project"]["timezone"]
    instant = hourly.loc[
        hourly["time_utc"].ge(start_utc) & hourly["time_utc"].lt(end_exclusive_utc)
    ].copy()
    instant["date"] = instant["time_utc"].dt.tz_convert(timezone).dt.date
    daily = instant.groupby(["era5_grid_id", "date"], as_index=False).agg(
        temperature_mean_c=("temperature_c", "mean"),
        relative_humidity_mean_pct=("relative_humidity_pct", "mean"),
        wind_speed_mean_ms=("wind_speed_ms", "mean"),
        u_wind_mean_ms=("u10", "mean"),
        v_wind_mean_ms=("v10", "mean"),
        surface_pressure_mean_hpa=("surface_pressure_hpa", "mean"),
        boundary_layer_height_mean_m=("blh", "mean"),
        meteorology_hours=("time_utc", "count"),
    )

    precipitation = hourly.loc[
        hourly["time_utc"].gt(start_utc) & hourly["time_utc"].le(end_exclusive_utc)
    ].copy()
    precipitation["date"] = (
        (precipitation["time_utc"] - pd.to_timedelta(1, unit="ns")).dt.tz_convert(timezone).dt.date
    )
    precipitation_daily = precipitation.groupby(["era5_grid_id", "date"], as_index=False).agg(
        precipitation_sum_mm=("precipitation_mm", "sum"),
        precipitation_hours=("time_utc", "count"),
    )
    daily = daily.merge(
        precipitation_daily,
        on=["era5_grid_id", "date"],
        how="outer",
        validate="one_to_one",
    )

    expected = _expected_local_hours(
        config["project"]["study_start_date"],
        config["project"]["end_date"],
        timezone,
    )
    daily = daily.merge(expected, on="date", how="left", validate="many_to_one")
    incomplete = daily.loc[
        daily["meteorology_hours"].ne(daily["expected_hours"])
        | daily["precipitation_hours"].ne(daily["expected_hours"])
    ]
    if not incomplete.empty:
        sample = incomplete[
            ["era5_grid_id", "date", "meteorology_hours", "precipitation_hours", "expected_hours"]
        ].head(10)
        raise ValueError(
            "ERA5 does not provide the expected 23/24/25 hours for every Sofia local day. "
            f"First incomplete rows: {sample.to_dict(orient='records')}"
        )

    predictors = mapping.merge(daily, on="era5_grid_id", how="left", validate="many_to_many")
    predictors["date"] = pd.to_datetime(predictors["date"])
    predictors["day_of_year_sin"] = np.sin(2 * np.pi * predictors["date"].dt.dayofyear / 365.25)
    predictors["day_of_year_cos"] = np.cos(2 * np.pi * predictors["date"].dt.dayofyear / 365.25)
    predictors["weekday"] = predictors["date"].dt.weekday
    predictors["heating_season"] = predictors["date"].map(_heating_season)
    predictors["date"] = predictors["date"].dt.date.astype(str)
    predictors = predictors.drop(columns=["era5_grid_id", "precipitation_hours", "expected_hours"])
    column_order = [
        "location",
        "location_id",
        "sensor_id",
        "date",
        "lat",
        "lon",
        "era5_latitude",
        "era5_longitude",
        "temperature_mean_c",
        "relative_humidity_mean_pct",
        "wind_speed_mean_ms",
        "u_wind_mean_ms",
        "v_wind_mean_ms",
        "surface_pressure_mean_hpa",
        "precipitation_sum_mm",
        "boundary_layer_height_mean_m",
        "meteorology_hours",
        "day_of_year_sin",
        "day_of_year_cos",
        "weekday",
        "heating_season",
    ]
    predictors = (
        predictors[column_order]
        .sort_values(["date", "location_id", "sensor_id"])
        .reset_index(drop=True)
    )
    if predictors.duplicated(["location_id", "sensor_id", "date"]).any():
        raise ValueError("Prepared predictor table contains duplicate sensor-location dates")
    expected_rows = len(panel) * len(expected)
    if len(predictors) != expected_rows:
        raise ValueError(f"Expected {expected_rows} predictor rows, found {len(predictors)}")

    output = ensure_parent(Path(config["paths"]["predictors"]))
    part = output.with_suffix(output.suffix + ".part")
    predictors.to_csv(part, index=False)
    part.replace(output)
    return predictors
