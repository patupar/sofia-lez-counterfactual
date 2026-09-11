"""Stage 7b: prepare grouped LCZ fractions for the stable sensor-location pairs."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.lcz import prepare_lcz_features


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    features = prepare_lcz_features(config)
    group_columns = list(config["lcz"]["class_groups"])
    print(f"Stable sensor-location pairs: {len(features)}")
    print(f"LCZ buffer radius: {config['lcz']['buffer_radius_m']} m")
    print(f"Grouped LCZ predictors: {len(group_columns)}")
    print(f"LCZ feature output: {config['paths']['lcz_features']}")


if __name__ == "__main__":
    main()
