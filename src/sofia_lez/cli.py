"""Command-line interface for the six-stage data workflow."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable

from .completeness import calculate_completeness, select_stable_panel
from .config import load_config
from .daily import aggregate_daily
from .downloader import download_archive
from .manifest import build_manifest
from .qc import build_hourly_qc


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
    table = build_hourly_qc(config)
    return {
        "hourly_rows": len(table),
        "qc_pass_rows": int(table["qc_pass"].sum()),
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


COMMANDS: dict[str, Callable[[dict], dict]] = {
    "manifest": _manifest,
    "download": _download,
    "qc-hourly": _qc,
    "completeness": _completeness,
    "select-panel": _panel,
    "aggregate-daily": _daily,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sofia-lez",
        description="Prepare a stable, quality-controlled Sofia Sensor.Community PM2.5 panel.",
    )
    parser.add_argument("--config", default="configs/pipeline.yaml", help="YAML configuration path")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in COMMANDS:
        subparsers.add_parser(command, help={
            "manifest": "spatially filter Sofia pairs and summarize historical coverage",
            "download": "download 2024–2026 archive files for plausible continuing sensors",
            "qc-hourly": "reconstruct hours and apply consistent archive QC",
            "completeness": "calculate sensor-year and sensor-season completeness",
            "select-panel": "choose pairs complete in every configured pre/post period",
            "aggregate-daily": "aggregate QC-passing hours to local sensor-days",
        }[command])
    run = subparsers.add_parser("run", help="run the complete sequence")
    run.add_argument(
        "--skip-download",
        action="store_true",
        help="use already cached archive files (especially useful during development)",
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
    summary = {}
    for step in steps:
        print(f"[{step}]", flush=True)
        summary[step] = COMMANDS[step](config)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
