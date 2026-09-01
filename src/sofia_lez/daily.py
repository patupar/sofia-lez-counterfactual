"""Daily PM2.5 aggregation after hourly QC."""

from __future__ import annotations

import pandas as pd

from .config import ensure_parent


def aggregate_daily(config: dict) -> pd.DataFrame:
    """Aggregate passing local hours and suppress incomplete sensor-days."""
    hourly = pd.read_csv(config["paths"]["hourly"])
    timezone = config["project"]["timezone"]
    hourly["hour_local"] = pd.to_datetime(hourly["hour_local"], utc=True).dt.tz_convert(timezone)
    hourly["qc_pass"] = hourly["qc_pass"].astype(str).str.lower().eq("true")
    valid = hourly.loc[hourly["qc_pass"]].copy()
    valid["date"] = valid["hour_local"].dt.date.astype(str)
    index = ["date", "location", "location_id", "sensor_id", "lat", "lon"]
    daily = (
        valid.groupby(index, as_index=False)
        .agg(pm2_5=("raw_pm2_5", "mean"), valid_hours=("raw_pm2_5", "size"))
        .sort_values(["location_id", "sensor_id", "date"])
    )
    minimum = int(config["aggregation"]["minimum_valid_hours_per_day"])
    daily["daily_qc_pass"] = daily["valid_hours"].ge(minimum)
    daily.loc[~daily["daily_qc_pass"], "pm2_5"] = pd.NA
    ensure_parent(config["paths"]["daily"])
    daily.to_csv(config["paths"]["daily"], index=False)
    return daily
