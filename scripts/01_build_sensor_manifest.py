"""Stage 1: build the Sofia location-sensor manifest."""

import argparse

from sofia_lez.config import load_config
from sofia_lez.manifest import build_manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/pipeline.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    manifest = build_manifest(config)
    print(f"Sofia location-sensor pairs: {len(manifest)}")
    print(f"Plausible continuing pairs: {int(manifest['plausible_continuing'].sum())}")
    print(f"Saved: {config['paths']['manifest']}")


if __name__ == "__main__":
    main()
