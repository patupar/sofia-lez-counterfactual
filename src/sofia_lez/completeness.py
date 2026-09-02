"""Sensor-year and heating-period completeness metrics."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta

import pandas as pd

from .config import ensure_parent


def _expected_hours(start: pd.Timestamp, end: pd.Timestamp, timezone: str) -> int:
    """Count local clock hours, correctly respecting daylight-saving changes."""
    start_local = pd.Timestamp(start.date(), tz=timezone)
    end_exclusive = pd.Timestamp(end.date() + timedelta(days=1), tz=timezone)
    return len(pd.date_range(start_local, end_exclusive, freq="h", inclusive="left"))


def _clip_period(
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    project_start: pd.Timestamp,
    project_end: pd.Timestamp,
) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    clipped_start = max(pd.Timestamp(start), project_start)
    clipped_end = min(pd.Timestamp(end), project_end)
    return None if clipped_start > clipped_end else (clipped_start, clipped_end)


def _period_metrics(
    hourly: pd.DataFrame,
    periods: Iterable[tuple[str, pd.Timestamp, pd.Timestamp]],
    timezone: str,
    minimum_daily_hours: int,
    name_column: str,
) -> pd.DataFrame:
    pair_columns = ["location", "location_id", "sensor_id", "lat", "lon"]
    pairs = hourly[pair_columns].drop_duplicates()
    rows: list[dict] = []
    for name, start, end in periods:
        start_local = pd.Timestamp(start.date(), tz=timezone)
        end_exclusive = pd.Timestamp(end.date() + timedelta(days=1), tz=timezone)
        subset = hourly.loc[
            hourly["hour_local"].ge(start_local) & hourly["hour_local"].lt(end_exclusive)
        ].copy()
        expected = _expected_hours(start, end, timezone)
        expected_days = (end.date() - start.date()).days + 1
        for pair in pairs.itertuples(index=False):
            selected = subset.loc[
                subset["location_id"].eq(pair.location_id) & subset["sensor_id"].eq(pair.sensor_id)
            ]
            valid = selected.loc[selected["qc_pass"]]
            daily_counts = valid.groupby(valid["hour_local"].dt.date).size()
            valid_hours = int(len(valid))
            rows.append(
                {
                    **pair._asdict(),
                    name_column: name,
                    "period_start": start.date().isoformat(),
                    "period_end": end.date().isoformat(),
                    "expected_hours": expected,
                    "observed_hours": int(len(selected)),
                    "valid_hours": valid_hours,
                    "hour_completeness": valid_hours / expected if expected else 0.0,
                    "expected_days": expected_days,
                    "valid_days": int(daily_counts.ge(minimum_daily_hours).sum()),
                    "day_completeness": int(daily_counts.ge(minimum_daily_hours).sum())
                    / expected_days,
                }
            )
    return pd.DataFrame(rows)


def _heating_seasons(project_start: pd.Timestamp, project_end: pd.Timestamp):
    for year in range(project_start.year - 1, project_end.year + 1):
        start = pd.Timestamp(year=year, month=10, day=1)
        end = pd.Timestamp(year=year + 1, month=3, day=31)
        clipped = _clip_period(start, end, project_start, project_end)
        if clipped:
            yield f"{year}-{year + 1}", *clipped


def calculate_completeness(config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write sensor-year plus standard and intervention-aligned season metrics."""
    hourly = pd.read_csv(config["paths"]["hourly"], low_memory=False)
    hourly["hour_local"] = pd.to_datetime(hourly["hour_local"], utc=True).dt.tz_convert(
        config["project"]["timezone"]
    )
    hourly["qc_pass"] = hourly["qc_pass"].astype(str).str.lower().eq("true")
    project_start = pd.Timestamp(config["project"]["study_start_date"])
    project_end = pd.Timestamp(config["project"]["end_date"])
    timezone = config["project"]["timezone"]
    minimum = int(config["completeness"]["minimum_valid_hours_per_day"])

    years = []
    for year in range(project_start.year, project_end.year + 1):
        clipped = _clip_period(
            pd.Timestamp(year=year, month=1, day=1),
            pd.Timestamp(year=year, month=12, day=31),
            project_start,
            project_end,
        )
        if clipped:
            years.append((str(year), *clipped))
    year_table = _period_metrics(hourly, years, timezone, minimum, "year")

    seasons = list(_heating_seasons(project_start, project_end))
    panel_periods = [
        (name, *_clip_period(start, end, project_start, project_end))
        for name, (start, end) in config["completeness"]["panel_periods"].items()
        if _clip_period(start, end, project_start, project_end)
    ]
    season_table = pd.concat(
        [
            _period_metrics(hourly, seasons, timezone, minimum, "season"),
            _period_metrics(hourly, panel_periods, timezone, minimum, "season"),
        ],
        ignore_index=True,
    )
    season_table["season_type"] = season_table["season"].apply(
        lambda value: "heating_season" if value[:4].isdigit() and "-" in value else "panel_period"
    )

    ensure_parent(config["paths"]["completeness_year"])
    year_table.to_csv(config["paths"]["completeness_year"], index=False)
    ensure_parent(config["paths"]["completeness_season"])
    season_table.to_csv(config["paths"]["completeness_season"], index=False)
    return year_table, season_table


def select_stable_panel(config: dict) -> pd.DataFrame:
    """Require the configured completeness threshold in every pre/post panel period."""
    seasons = pd.read_csv(config["paths"]["completeness_season"])
    required = list(config["completeness"]["panel_periods"])
    threshold = float(config["completeness"]["panel_minimum_hour_fraction"])
    panel_periods = seasons.loc[seasons["season"].isin(required)].copy()
    panel_periods["passes"] = panel_periods["hour_completeness"].ge(threshold)
    index = ["location", "location_id", "sensor_id", "lat", "lon"]
    wide = panel_periods.pivot_table(
        index=index, columns="season", values="hour_completeness", aggfunc="first"
    ).reset_index()
    pass_counts = panel_periods.groupby(index)["passes"].agg(["sum", "count"]).reset_index()
    panel = wide.merge(pass_counts, on=index, how="left")
    panel["required_periods"] = len(required)
    panel["stable_panel"] = panel["sum"].eq(len(required)) & panel["count"].eq(len(required))
    panel = panel.rename(columns={"sum": "periods_passing", "count": "periods_observed"})
    ensure_parent(config["paths"]["panel"])
    panel.to_csv(config["paths"]["panel"], index=False)
    return panel
