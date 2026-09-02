"""Stage 2: download 2024–31 March 2026 Sensor.Community files."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.downloader import download_archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    counts = download_archive(config)
    for status, count in counts.items():
        print(f"{status}: {count}")
    print(f"Saved under: {config['paths']['archive']}")


if __name__ == "__main__":
    main()
