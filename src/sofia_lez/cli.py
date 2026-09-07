"""Command-line interface for the sensor and ERA5 predictor workflow."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable

from .completeness import calculate_completeness, select_stable_panel
from .config import load_config
from .daily import aggregate_daily
from .downloader import download_archive
from .manifest import build_manifest
from .meteorology import download_era5, prepare_predictors
from .sensors import build_unified_hourly


def _manifest(config: dict) -> dict:
    table = build_manifest(config)
    return {
        "pairs_inside_sofia": len(table),
        "plausible_continuing_pairs": int(table["plausible_continuing"].sum()),
        "output": str(config["paths"]["manifest"]),
    }


def _download(config: dict) -> dict:
    return {**download_archive(config), "output": str(config["paths"]["archive"])}


def _qc(config: dict) -> dict:
    table = build_unified_hourly(config)
    source_counts = table.groupby("data_source").size().to_dict()
    return {
        "hourly_rows": len(table),
        "qc_pass_rows": int(table["qc_pass"].sum()),
        "rows_by_source": source_counts,
        "output": str(config["paths"]["hourly"]),
    }


def _completeness(config: dict) -> dict:
    years, seasons = calculate_completeness(config)
    return {
        "sensor_year_rows": len(years),
        "sensor_season_rows": len(seasons),
        "year_output": str(config["paths"]["completeness_year"]),
        "season_output": str(config["paths"]["completeness_season"]),
    }


def _panel(config: dict) -> dict:
    table = select_stable_panel(config)
    return {
        "candidate_pairs": len(table),
        "stable_pairs": int(table["stable_panel"].sum()),
        "output": str(config["paths"]["panel"]),
    }


def _daily(config: dict) -> dict:
    table = aggregate_daily(config)
    return {
        "sensor_days": len(table),
        "valid_sensor_days": int(table["daily_qc_pass"].sum()),
        "output": str(config["paths"]["daily"]),
    }


def _download_era5(config: dict) -> dict:
    return download_era5(config)


def _predictors(config: dict) -> dict:
    table = prepare_predictors(config)
    return {
        "predictor_rows": len(table),
        "stable_pairs": int(table[["location_id", "sensor_id"]].drop_duplicates().shape[0]),
        "output": str(config["paths"]["predictors"]),
    }


COMMANDS: dict[str, Callable[[dict], dict]] = {
    "manifest": _manifest,
    "download": _download,
    "qc-hourly": _qc,
    "aggregate-daily": _daily,
    "completeness": _completeness,
    "select-panel": _panel,
    "download-era5": _download_era5,
    "prepare-predictors": _predictors,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sofia-lez",
        description="Prepare the Sofia PM2.5 panel and its daily ERA5 predictors.",
    )
    parser.add_argument("--config", default="configs/pipeline.yaml", help="YAML configuration path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparsers.add_parser(
            command,
            help={
                "manifest": "spatially filter Sofia pairs and summarize historical coverage",
                "download": "download 2024–2026 archive files for plausible continuing sensors",
                "qc-hourly": "combine FILTER and archive hours with documented source-specific QC",
                "completeness": "calculate sensor-year and sensor-season completeness",
                "select-panel": "choose pairs complete across the configured pre/post periods",
                "aggregate-daily": "aggregate QC-passing hours to local sensor-days",
                "download-era5": "download hourly ERA5 data for the stable-panel area",
                "prepare-predictors": "prepare daily meteorological and temporal predictors",
            }[command],
        )
    run = subparsers.add_parser("run", help="run the implemented data-preparation sequence")
    run.add_argument(
        "--skip-download",
        action="store_true",
        help="use already cached archive files (especially useful during development)",
    )
    run.add_argument(
        "--include-provisional-panel",
        action="store_true",
        help="apply the panel threshold and run the dependent ERA5 predictor stages",
    )
    run.add_argument(
        "--skip-era5-download",
        action="store_true",
        help="use already cached ERA5 files when the predictor stages are included",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.command in COMMANDS:
        print(json.dumps(COMMANDS[args.command](config), indent=2))
        return 0

    steps = list(COMMANDS)
    if args.skip_download:
        steps.remove("download")
    if not args.include_provisional_panel:
        for step in ("select-panel", "download-era5", "prepare-predictors"):
            steps.remove(step)
    elif args.skip_era5_download:
        steps.remove("download-era5")
    summary = {}
    for step in steps:
        print(f"[{step}]", flush=True)
        summary[step] = COMMANDS[step](config)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
