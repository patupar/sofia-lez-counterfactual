"""Stage 9: tune and validate the Random Forest on blocked pre-LEZ periods."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.modeling import validate_random_forest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    summary = validate_random_forest(config)
    print(f"Pre-LEZ training rows available: {summary['training_rows']}")
    print(f"Blocked validation folds: {summary['validation_folds']}")
    print(f"Parameter sets tested: {summary['parameter_sets_tested']}")
    print(f"Best cross-validation MAE: {summary['best_cv_mae']:.3f} ug/m3")
    print(f"Best parameters: {summary['best_parameters']}")
    print(f"Validation metrics: {summary['metrics']}")
    print(f"Recent test period: {summary['test_period']} ({summary['test_rows']} rows)")
    print(f"Recent test metrics: {summary['test_metrics']}")


if __name__ == "__main__":
    main()
