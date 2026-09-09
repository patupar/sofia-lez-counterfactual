"""Stage 10: fit the selected Random Forest on all pre-LEZ heating months."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.modeling import train_random_forest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    summary = train_random_forest(config)
    print(f"Training rows: {summary['training_rows']}")
    print(f"Sensor-location pairs: {summary['sensor_location_pairs']}")
    print(f"Training period: {summary['training_start']} to {summary['training_end']}")
    print(f"Saved model: {summary['model']}")
    print(f"Feature importance: {summary['feature_importance']}")


if __name__ == "__main__":
    main()
