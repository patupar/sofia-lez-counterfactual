"""Tests for Local Climate Zone predictor preparation."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sofia_lez.lcz import prepare_lcz_features

ROOT = Path(__file__).parents[1]
GROUPS = {
    "lcz_compact_built_fraction": [1, 2, 3],
    "lcz_open_built_fraction": [4, 5, 6],
    "lcz_other_built_fraction": [7, 8, 9, 10],
    "lcz_vegetation_fraction": [11, 12, 13, 14],
    "lcz_bare_water_fraction": [15, 16, 17],
}


def _config(tmp_path: Path) -> dict:
    panel = tmp_path / "stable_panel.csv"
    pd.DataFrame(
        {
            "location": ["SC100", "SC200"],
            "location_id": [100, 200],
            "sensor_id": [10, 20],
            "lat": [42.70, 42.51],
            "lon": [23.32, 23.49],
            "stable_panel": [True, False],
        }
    ).to_csv(panel, index=False)
    return {
        "paths": {
            "panel": panel,
            "lcz_raster": ROOT / "sample_data/lcz/lcz_sofia_sample.tif",
            "lcz_features": tmp_path / "lcz_sensor_features.csv",
        },
        "lcz": {"buffer_radius_m": 500, "class_groups": GROUPS},
    }


def test_prepare_lcz_features_from_supplied_raster_crop(tmp_path: Path):
    config = _config(tmp_path)

    features = prepare_lcz_features(config)

    assert len(features) == 1
    assert features.loc[0, "location_id"] == 100
    assert features.loc[0, "lcz_valid_pixels"] == 107
    assert features.loc[0, "lcz_dominant_class"] == 2
    assert features.loc[0, "lcz_compact_built_fraction"] == pytest.approx(99 / 107)
    assert features.loc[0, "lcz_open_built_fraction"] == pytest.approx(6 / 107)
    assert features.loc[0, "lcz_other_built_fraction"] == pytest.approx(2 / 107)
    assert features.loc[0, "lcz_vegetation_fraction"] == 0
    assert features.loc[0, "lcz_bare_water_fraction"] == 0
    assert np.isclose(features[list(GROUPS)].sum(axis=1), 1).all()
    assert Path(config["paths"]["lcz_features"]).exists()


def test_lcz_groups_must_cover_all_classes_once(tmp_path: Path):
    config = _config(tmp_path)
    config["lcz"]["class_groups"]["lcz_bare_water_fraction"] = [15, 16]

    with pytest.raises(ValueError, match="cover classes 1-17 exactly once"):
        prepare_lcz_features(config)
