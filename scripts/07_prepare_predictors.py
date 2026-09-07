"""Stage 7: prepare daily ERA5, temporal, and spatial predictors."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.meteorology import prepare_predictors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    predictors = prepare_predictors(config)
    stable_pairs = predictors[["location_id", "sensor_id"]].drop_duplicates().shape[0]
    print(f"Stable sensor-location pairs: {stable_pairs}")
    print(f"Daily predictor rows: {len(predictors)}")
    print(f"Date range: {predictors['date'].min()} to {predictors['date'].max()}")
    print(f"Predictor output: {config['paths']['predictors']}")


if __name__ == "__main__":
    main()
