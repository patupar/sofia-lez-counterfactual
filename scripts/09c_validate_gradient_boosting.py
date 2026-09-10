"""Optional Stage 9c: compare Gradient Boosting on the same temporal folds."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.modeling import validate_gradient_boosting


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    summary = validate_gradient_boosting(config)
    print(f"Pre-LEZ training rows available: {summary['training_rows']}")
    print(f"Blocked validation folds: {summary['validation_folds']}")
    print(f"Parameter sets tested: {summary['parameter_sets_tested']}")
    print(f"Lowest cross-validation MAE: {summary['best_cv_mae']:.3f} ug/m3")
    print(
        "Candidates within one standard error: "
        f"{summary['one_standard_error_candidates']}"
    )
    print(f"Candidate diagnostics: {summary['tuning_results']}")
    print("This comparison does not select or replace the Random Forest.")


if __name__ == "__main__":
    main()
