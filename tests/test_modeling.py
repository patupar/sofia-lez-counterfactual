import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from sofia_lez.modeling import (
    _sensor_mean_prediction,
    build_model_table,
    predict_counterfactual,
    summarise_counterfactual,
    train_random_forest,
    validate_random_forest,
)


def test_sensor_mean_benchmark_uses_training_targets_only():
    train = pd.DataFrame(
        {
            "location_id": [1, 1, 2],
            "sensor_id": [11, 11, 22],
            "pm2_5": [10.0, 20.0, 30.0],
        }
    )
    validation = pd.DataFrame(
        {
            "location_id": [1, 3],
            "sensor_id": [11, 33],
            # These future values must not affect either benchmark prediction.
            "pm2_5": [999.0, 999.0],
        }
    )

    predictions = _sensor_mean_prediction(train, validation, "pm2_5")

    # Pair 1 receives its training mean; unseen pair 3 receives the overall
    # training mean. Neither value can have been calculated from validation y.
    np.testing.assert_allclose(predictions, [15.0, 20.0])


def _model_config(path: Path) -> None:
    settings = {
        "target": "pm2_5",
        "training": {
            "start_date": "2018-01-01",
            "end_date": "2021-12-31",
            "include_months": [1, 2, 3, 10, 11, 12],
        },
        "counterfactual_periods": [
            {"name": "post_one", "start_date": "2022-01-01", "end_date": "2022-01-02"},
            {"name": "post_two", "start_date": "2022-10-01", "end_date": "2022-10-02"},
        ],
        "random_forest": {
            "random_state": 42,
            "final_n_jobs": 1,
            "search": {
                "n_iter": 1,
                "n_jobs": 1,
                "verbose": 0,
                "parameter_distributions": {
                    "model__n_estimators": [5],
                    "model__max_depth": [5],
                    "model__max_features": [1.0],
                    "model__min_samples_leaf": [1],
                },
            },
        },
        "validation": {
            "scoring": "neg_mean_absolute_error",
            "benchmark": "sensor_mean",
            "folds": [
                {
                    "name": "2019-2020",
                    "train_end": "2019-03-31",
                    "validation_start": "2019-10-01",
                    "validation_end": "2020-03-31",
                },
                {
                    "name": "2020-2021",
                    "train_end": "2020-03-31",
                    "validation_start": "2020-10-01",
                    "validation_end": "2021-03-31",
                },
            ],
            "test_period": {
                "name": "autumn_2021",
                "train_end": "2021-03-31",
                "test_start": "2021-10-01",
                "test_end": "2021-12-31",
            },
        },
        "predictors": [
            "temperature_mean_c",
            "relative_humidity_mean_pct",
            "wind_speed_mean_ms",
            "u_wind_mean_ms",
            "v_wind_mean_ms",
            "surface_pressure_mean_hpa",
            "precipitation_sum_mm",
            "boundary_layer_height_mean_m",
            "day_of_year_sin",
            "day_of_year_cos",
            "weekday",
            "lat",
            "lon",
        ],
    }
    path.write_text(yaml.safe_dump(settings, sort_keys=False), encoding="utf-8")


def _synthetic_tables(tmp_path: Path) -> tuple[Path, Path]:
    dates = pd.date_range("2018-01-01", "2022-10-02", freq="D")
    dates = dates[dates.month.isin([1, 2, 3, 10, 11, 12])]
    pairs = [
        ("SC1", 1, 11, 42.68, 23.30),
        ("SC2", 2, 22, 42.70, 23.32),
        ("SC3", 3, 33, 42.72, 23.34),
    ]
    predictor_rows = []
    daily_rows = []
    for location, location_id, sensor_id, lat, lon in pairs:
        for date in dates:
            angle = 2 * np.pi * date.dayofyear / 365.25
            temperature = 8 + 10 * np.sin(angle)
            pm2_5 = 18 - 0.4 * temperature + location_id + 2 * np.cos(angle)
            predictor_rows.append(
                {
                    "location": location,
                    "location_id": location_id,
                    "sensor_id": sensor_id,
                    "date": date.date().isoformat(),
                    "lat": lat,
                    "lon": lon,
                    "era5_latitude": 42.75,
                    "era5_longitude": 23.25,
                    "temperature_mean_c": temperature,
                    "relative_humidity_mean_pct": 70 - temperature / 4,
                    "wind_speed_mean_ms": 2 + location_id / 10,
                    "u_wind_mean_ms": 1.0,
                    "v_wind_mean_ms": -1.0,
                    "surface_pressure_mean_hpa": 920 + np.cos(angle),
                    "precipitation_sum_mm": max(0.0, np.sin(angle)),
                    "boundary_layer_height_mean_m": 400 + 10 * temperature,
                    "meteorology_hours": 24,
                    "day_of_year_sin": np.sin(angle),
                    "day_of_year_cos": np.cos(angle),
                    "weekday": date.weekday(),
                    "heating_season": "test",
                }
            )
            daily_rows.append(
                {
                    "location_id": location_id,
                    "sensor_id": sensor_id,
                    "date": date.date().isoformat(),
                    "pm2_5": pm2_5,
                    "observed_hours": 24,
                    "valid_hours": 24,
                    "data_source": "synthetic",
                    "daily_qc_pass": True,
                }
            )
    daily_rows[0]["daily_qc_pass"] = False
    daily_rows[0]["pm2_5"] = np.nan
    predictors_path = tmp_path / "predictors.csv"
    daily_path = tmp_path / "daily.csv"
    pd.DataFrame(predictor_rows).to_csv(predictors_path, index=False)
    pd.DataFrame(daily_rows).to_csv(daily_path, index=False)
    return predictors_path, daily_path


def _pipeline_config(tmp_path: Path) -> dict:
    predictors, daily = _synthetic_tables(tmp_path)
    model_config = tmp_path / "model.yaml"
    _model_config(model_config)
    return {
        "paths": {
            "predictors": predictors,
            "daily": daily,
            "model_config": model_config,
            "model_table": tmp_path / "model_table.csv",
            "validation_predictions": tmp_path / "validation_predictions.csv",
            "test_predictions": tmp_path / "test_predictions.csv",
            "tuning_results": tmp_path / "tuning_results.csv",
            "selected_parameters": tmp_path / "selected_parameters.json",
            "validation_metrics": tmp_path / "validation_metrics.csv",
            "validation_metrics_by_sensor": tmp_path / "validation_metrics_by_sensor.csv",
            "validation_metrics_by_season_part": tmp_path / "validation_by_season_part.csv",
            "test_metrics": tmp_path / "test_metrics.csv",
            "test_metrics_by_sensor": tmp_path / "test_metrics_by_sensor.csv",
            "model_file": tmp_path / "random_forest.joblib",
            "model_metadata": tmp_path / "random_forest_metadata.json",
            "feature_importance": tmp_path / "feature_importance.csv",
            "predictions": tmp_path / "counterfactual_predictions.csv",
            "counterfactual_summary": tmp_path / "counterfactual_summary.csv",
            "counterfactual_by_date": tmp_path / "counterfactual_by_date.csv",
            "counterfactual_by_sensor": tmp_path / "counterfactual_by_sensor.csv",
        }
    }


def test_random_forest_workflow_uses_blocked_pre_lez_data(tmp_path, monkeypatch):
    config = _pipeline_config(tmp_path)
    benchmark_windows = []

    def tracked_sensor_mean(train, validation, target):
        benchmark_windows.append((train["date"].max(), validation["date"].min()))
        return _sensor_mean_prediction(train, validation, target)

    monkeypatch.setattr(
        "sofia_lez.modeling._sensor_mean_prediction",
        tracked_sensor_mean,
    )

    model_table = build_model_table(config)
    assert not model_table.duplicated(["location_id", "sensor_id", "date"]).any()
    assert model_table["pm2_5"].isna().sum() == 1
    assert not bool(model_table.loc[0, "eligible_for_training"])

    validation = validate_random_forest(config)
    assert validation["validation_folds"] == 2
    assert validation["parameter_sets_tested"] == 1
    assert validation["test_period"] == "autumn_2021"
    assert benchmark_windows == [
        (pd.Timestamp("2019-03-31"), pd.Timestamp("2019-10-01")),
        (pd.Timestamp("2020-03-31"), pd.Timestamp("2020-10-01")),
        (pd.Timestamp("2021-03-31"), pd.Timestamp("2021-10-01")),
    ]
    metrics = pd.read_csv(config["paths"]["validation_metrics"])
    assert set(metrics["model"]) == {"random_forest", "sensor_mean_benchmark"}
    assert set(metrics["fold"]) == {"2019-2020", "2020-2021", "all_validation_blocks"}
    sensor_metrics = pd.read_csv(config["paths"]["validation_metrics_by_sensor"])
    assert sensor_metrics[["location_id", "sensor_id"]].drop_duplicates().shape[0] == 3
    season_part_metrics = pd.read_csv(
        config["paths"]["validation_metrics_by_season_part"]
    )
    assert set(season_part_metrics["season_part"]) == {"oct_dec", "jan_mar"}
    test_metrics = pd.read_csv(config["paths"]["test_metrics"])
    assert set(test_metrics["model"]) == {"random_forest", "sensor_mean_benchmark"}
    with config["paths"]["selected_parameters"].open(encoding="utf-8") as handle:
        selected = json.load(handle)
    assert selected["test_period"]["name"] == "autumn_2021"
    assert all(fold["name"] != "autumn_2021" for fold in selected["folds"])

    trained = train_random_forest(config)
    assert trained["training_end"] == "2021-12-31"
    assert config["paths"]["model_file"].exists()

    predictions = predict_counterfactual(config)
    assert len(predictions) == 12
    assert set(predictions["counterfactual_period"]) == {"post_one", "post_two"}
    assert predictions["predicted_pm2_5_no_lez"].notna().all()

    summary = summarise_counterfactual(config)
    assert summary["periods"] == 2
    period_summary = pd.read_csv(config["paths"]["counterfactual_summary"])
    assert set(period_summary["counterfactual_period"]) == {
        "post_one",
        "post_two",
        "all_post_periods",
    }
