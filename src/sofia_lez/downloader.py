"""Resumable Sensor.Community daily archive downloader."""

from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd


@dataclass(frozen=True)
class DownloadJob:
    day: date
    sensor_id: int
    target_stem: Path


def candidate_urls(base: str, day: date, sensor_type: str, sensor_id: int) -> list[str]:
    """Return known archive layouts, newest/plain first and legacy/gzip included."""
    stamp = day.isoformat()
    filename = f"{stamp}_{sensor_type}_sensor_{sensor_id}.csv"
    directories = [f"{base.rstrip('/')}/{stamp}", f"{base.rstrip('/')}/{day.year}/{stamp}"]
    return [
        f"{directory}/{filename}{suffix}"
        for directory in directories
        for suffix in ("", ".gz")
    ]


def _download_one(job: DownloadJob, config: dict) -> dict:
    settings = config["download"]
    base = config["sources"]["sensor_community_archive"]
    sensor_type = config["sources"]["sensor_type"]
    existing = list(job.target_stem.parent.glob(job.target_stem.name + ".csv*"))
    if any(path.stat().st_size for path in existing):
        return {"status": "cached", "sensor_id": job.sensor_id, "date": job.day.isoformat()}

    job.target_stem.parent.mkdir(parents=True, exist_ok=True)
    last_error = "not found"
    for url in candidate_urls(base, job.day, sensor_type, job.sensor_id):
        extension = ".csv.gz" if url.endswith(".gz") else ".csv"
        target = job.target_stem.with_suffix(extension)
        part = target.with_suffix(target.suffix + ".part")
        for attempt in range(int(settings["retries"]) + 1):
            try:
                request = Request(url, headers={"User-Agent": "sofia-lez-counterfactual/0.1"})
                with urlopen(request, timeout=float(settings["timeout_seconds"])) as response:
                    if response.status != 200:
                        continue
                    with part.open("wb") as output:
                        shutil.copyfileobj(response, output)
                part.replace(target)
                return {
                    "status": "downloaded",
                    "sensor_id": job.sensor_id,
                    "date": job.day.isoformat(),
                    "url": url,
                }
            except HTTPError as error:
                last_error = f"HTTP {error.code}"
                if error.code == 404:
                    break
            except (URLError, TimeoutError, OSError) as error:
                last_error = str(error)
            if attempt < int(settings["retries"]):
                time.sleep(2**attempt)
        part.unlink(missing_ok=True)
    return {
        "status": "missing",
        "sensor_id": job.sensor_id,
        "date": job.day.isoformat(),
        "error": last_error,
    }


def download_archive(config: dict) -> dict[str, int]:
    """Download each plausible sensor/day once, preserving raw source files."""
    manifest = pd.read_csv(config["paths"]["manifest"])
    sensors = sorted(
        manifest.loc[manifest["plausible_continuing"].astype(bool), "sensor_id"].unique()
    )
    days = pd.date_range(config["project"]["start_date"], config["project"]["end_date"], freq="D")
    root = config["paths"]["archive"]
    jobs = [
        DownloadJob(
            day=timestamp.date(),
            sensor_id=int(sensor_id),
            target_stem=root / str(timestamp.year) / f"{timestamp.date()}_sensor_{int(sensor_id)}",
        )
        for timestamp in days
        for sensor_id in sensors
    ]

    counts: dict[str, int] = {"downloaded": 0, "cached": 0, "missing": 0}
    ledger = root / "download_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as log, ThreadPoolExecutor(
        max_workers=int(config["download"]["workers"])
    ) as pool:
        futures = [pool.submit(_download_one, job, config) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            counts[result["status"]] += 1
            log.write(json.dumps(result, sort_keys=True) + "\n")
            log.flush()
    return counts
