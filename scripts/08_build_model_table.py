"""Stage 8: join the stable-panel predictors and daily PM2.5 observations."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.modeling import build_model_table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    table = build_model_table(config)
    stable_pairs = table[["location_id", "sensor_id"]].drop_duplicates().shape[0]
    print(f"Model-table rows: {len(table)}")
    print(f"Stable sensor-location pairs: {stable_pairs}")
    print(f"Grouped LCZ predictors: {len(config['lcz']['class_groups'])}")
    print(f"QC-valid PM2.5 rows: {table['pm2_5'].notna().sum()}")
    print(f"Eligible pre-LEZ training rows: {table['eligible_for_training'].sum()}")
    print(f"Model table: {config['paths']['model_table']}")


if __name__ == "__main__":
    main()
