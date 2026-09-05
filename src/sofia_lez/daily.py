"""Daily PM2.5 aggregation after hourly QC."""

from __future__ import annotations

import pandas as pd

from .config import ensure_parent


def aggregate_daily(config: dict) -> pd.DataFrame:
    """Aggregate passing local hours and apply transparent daily QC."""
    hourly = pd.read_csv(config["paths"]["hourly"], low_memory=False)
    timezone = config["project"]["timezone"]
    hourly["hour_local"] = pd.to_datetime(hourly["hour_local"], utc=True).dt.tz_convert(timezone)
    hourly["qc_pass"] = hourly["qc_pass"].astype(str).str.lower().eq("true")
    hourly["date"] = hourly["hour_local"].dt.date.astype(str)
    hourly["pm2_5_valid"] = hourly["pm2_5"].where(hourly["qc_pass"])
    index = ["date", "location", "location_id", "sensor_id", "lat", "lon"]
    daily = (
        hourly.groupby(index, as_index=False)
        .agg(
            pm2_5=("pm2_5_valid", "mean"),
            observed_hours=("pm2_5", "count"),
            valid_hours=("pm2_5_valid", "count"),
            data_source=("data_source", lambda values: "+".join(sorted(set(values)))),
        )
        .sort_values(["location_id", "sensor_id", "date"])
    )
    minimum = int(config["aggregation"]["minimum_valid_hours_per_day"])
    maximum = float(config["aggregation"]["maximum_daily_pm25_exclusive"])
    daily["pm2_5_before_daily_qc"] = daily["pm2_5"]
    daily["qc_daily_hours"] = daily["valid_hours"].ge(minimum)
    daily["qc_daily_range"] = daily["pm2_5_before_daily_qc"].lt(maximum)
    daily["daily_qc_pass"] = daily[["qc_daily_hours", "qc_daily_range"]].all(axis=1)
    daily.loc[~daily["daily_qc_pass"], "pm2_5"] = pd.NA
    ensure_parent(config["paths"]["daily"])
    daily.to_csv(config["paths"]["daily"], index=False)
    return daily
