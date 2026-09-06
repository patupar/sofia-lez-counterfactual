"""Sensor completeness metrics and stable-panel selection."""

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
    daily: pd.DataFrame,
    periods: Iterable[tuple[str, pd.Timestamp, pd.Timestamp]],
    timezone: str,
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
        daily_subset = daily.loc[daily["date"].between(start, end)].copy()
        expected = _expected_hours(start, end, timezone)
        expected_days = (end.date() - start.date()).days + 1
        for pair in pairs.itertuples(index=False):
            selected = subset.loc[
                subset["location_id"].eq(pair.location_id) & subset["sensor_id"].eq(pair.sensor_id)
            ]
            valid = selected.loc[selected["qc_pass"]]
            selected_days = daily_subset.loc[
                daily_subset["location_id"].eq(pair.location_id)
                & daily_subset["sensor_id"].eq(pair.sensor_id)
            ]
            valid_hours = int(len(valid))
            valid_days = int(selected_days["daily_qc_pass"].sum())
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
                    "valid_days": valid_days,
                    "day_completeness": valid_days / expected_days,
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
    daily = pd.read_csv(config["paths"]["daily"], low_memory=False)
    daily["date"] = pd.to_datetime(daily["date"])
    daily["daily_qc_pass"] = daily["daily_qc_pass"].astype(str).str.lower().eq("true")
    project_start = pd.Timestamp(config["project"]["study_start_date"])
    project_end = pd.Timestamp(config["project"]["end_date"])
    timezone = config["project"]["timezone"]

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
    year_table = _period_metrics(hourly, daily, years, timezone, "year")

    seasons = list(_heating_seasons(project_start, project_end))
    selection_periods = [
        (name, *_clip_period(start, end, project_start, project_end))
        for name, (start, end) in config["panel_selection"]["post_periods"].items()
        if _clip_period(start, end, project_start, project_end)
    ]
    season_table = pd.concat(
        [
            _period_metrics(hourly, daily, seasons, timezone, "season"),
            _period_metrics(hourly, daily, selection_periods, timezone, "season"),
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
    """Select pairs complete across the aggregate pre period and each post period."""
    years = pd.read_csv(config["paths"]["completeness_year"])
    seasons = pd.read_csv(config["paths"]["completeness_season"])
    index = ["location", "location_id", "sensor_id", "lat", "lon"]
    settings = config["panel_selection"]
    threshold = float(settings["minimum_day_fraction"])
    pre_start_year = int(settings["pre_start_year"])
    pre_end_year = int(settings["pre_end_year"])
    post_periods = list(settings["post_periods"])

    pre = years.loc[years["year"].between(pre_start_year, pre_end_year)].copy()
    expected_pre_years = set(range(pre_start_year, pre_end_year + 1))
    observed_pre_years = set(pre["year"].unique())
    if observed_pre_years != expected_pre_years:
        missing = sorted(expected_pre_years - observed_pre_years)
        raise ValueError(f"Completeness table is missing configured pre-LEZ years: {missing}")

    pre_summary = (
        pre.groupby(index, as_index=False)
        .agg(
            pre_expected_days=("expected_days", "sum"),
            pre_valid_days=("valid_days", "sum"),
        )
    )
    pre_summary["pre_day_completeness"] = (
        pre_summary["pre_valid_days"] / pre_summary["pre_expected_days"]
    )
    pre_summary["passes_pre"] = pre_summary["pre_day_completeness"].ge(threshold)

    post = seasons.loc[seasons["season"].isin(post_periods)].copy()
    observed_post_periods = set(post["season"].unique())
    missing_post_periods = sorted(set(post_periods) - observed_post_periods)
    if missing_post_periods:
        raise ValueError(
            "Completeness table is missing configured post-LEZ periods: "
            f"{missing_post_periods}"
        )
    if post.duplicated(index + ["season"]).any():
        raise ValueError("Completeness table contains duplicate sensor-period rows")

    panel = pre_summary
    for period in post_periods:
        columns = index + ["expected_days", "valid_days", "day_completeness"]
        period_table = post.loc[post["season"].eq(period), columns].rename(
            columns={
                "expected_days": f"{period}_expected_days",
                "valid_days": f"{period}_valid_days",
                "day_completeness": f"{period}_day_completeness",
            }
        )
        period_table[f"passes_{period}"] = period_table[
            f"{period}_day_completeness"
        ].ge(threshold)
        panel = panel.merge(period_table, on=index, how="left", validate="one_to_one")

    pass_columns = ["passes_pre", *(f"passes_{period}" for period in post_periods)]
    panel["criteria_passing"] = panel[pass_columns].fillna(False).sum(axis=1)
    panel["required_criteria"] = len(pass_columns)
    panel["stable_panel"] = panel[pass_columns].fillna(False).all(axis=1)
    ensure_parent(config["paths"]["panel"])
    panel.to_csv(config["paths"]["panel"], index=False)
    return panel
