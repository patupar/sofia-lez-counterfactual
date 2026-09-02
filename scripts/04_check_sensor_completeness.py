"""Stage 4: calculate sensor-year and heating-season completeness."""

import argparse

from sofia_lez.completeness import calculate_completeness
from sofia_lez.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    years, seasons = calculate_completeness(config)
    print(f"Sensor-year rows: {len(years)}")
    print(f"Sensor-season rows: {len(seasons)}")
    print(f"Year output: {config['paths']['completeness_year']}")
    print(f"Season output: {config['paths']['completeness_season']}")


if __name__ == "__main__":
    main()
