"""Stage 9b: record one RF candidate and evaluate the frozen choice."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.modeling import select_random_forest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    parser.add_argument("--candidate-rank", type=int, required=True)
    parser.add_argument(
        "--reason",
        required=True,
        help="Short audit note explaining why this candidate was selected",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    summary = select_random_forest(config, args.candidate_rank, args.reason)
    print(f"Selected candidate rank: {summary['candidate_rank']}")
    print(f"Selected cross-validation MAE: {summary['selected_cv_mae']:.3f} ug/m3")
    print(f"Parameters: {summary['parameters']}")
    print(f"Validation metrics: {summary['metrics']}")
    print(f"Recent holdout: {summary['test_period']} ({summary['test_rows']} rows)")
    print(f"Recent holdout metrics: {summary['test_metrics']}")
    print(f"Predictor-shift diagnostics: {summary['predictor_shift']}")
    print(f"Recorded selection: {summary['selected_parameters']}")


if __name__ == "__main__":
    main()
