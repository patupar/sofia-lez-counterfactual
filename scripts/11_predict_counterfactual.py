"""Stage 11: predict the post-LEZ PM2.5 baseline under no intervention."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.modeling import predict_counterfactual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    predictions = predict_counterfactual(config)
    print(f"Counterfactual prediction rows: {len(predictions)}")
    print(f"Observed comparison rows: {predictions['observed_pm2_5'].notna().sum()}")
    print(f"Periods: {', '.join(predictions['counterfactual_period'].unique())}")
    print(f"Predictions: {config['paths']['predictions']}")


if __name__ == "__main__":
    main()
