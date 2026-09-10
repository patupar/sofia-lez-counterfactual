"""Model validation, selection, training and counterfactual prediction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
import yaml
from sklearn.base import clone
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score, root_mean_squared_error
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline

from .config import ensure_parent

PAIR_COLUMNS = ["location", "location_id", "sensor_id", "lat", "lon"]
JOIN_COLUMNS = ["location_id", "sensor_id", "date"]


def _model_settings(config: dict) -> dict[str, Any]:
    path = Path(config["paths"]["model_config"])
    with path.open(encoding="utf-8") as handle:
        settings = yaml.safe_load(handle) or {}
    settings["_path"] = path
    predictors = settings.get("predictors", [])
    if not predictors or len(predictors) != len(set(predictors)):
        raise ValueError("Model predictors must be a non-empty list without duplicates")
    training_end = pd.Timestamp(settings["training"]["end_date"])
    periods = settings["counterfactual_periods"]
    if any(pd.Timestamp(period["start_date"]) <= training_end for period in periods):
        raise ValueError("Counterfactual periods must begin after the training period")
    test_period = settings["validation"]["test_period"]
    if pd.Timestamp(test_period["test_end"]) > training_end:
        raise ValueError("The recent test period must remain within the training period")
    if settings["validation"].get("benchmark") != "sensor_mean":
        raise ValueError("The supported validation benchmark is 'sensor_mean'")
    rf_grid = settings.get("random_forest", {}).get("search", {}).get("parameter_grid")
    if not rf_grid or any(not values for values in rf_grid.values()):
        raise ValueError("random_forest must define a non-empty parameter grid")
    return settings


def _write_csv(table: pd.DataFrame, path: Path) -> None:
    output = ensure_parent(Path(path))
    part = output.with_suffix(output.suffix + ".part")
    table.to_csv(part, index=False)
    part.replace(output)


def _write_json(data: dict[str, Any], path: Path) -> None:
    output = ensure_parent(Path(path))
    part = output.with_suffix(output.suffix + ".part")
    with part.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    part.replace(output)


def _as_boolean(values: pd.Series) -> pd.Series:
    return values.fillna(False).astype(str).str.lower().eq("true")


def _period_labels(dates: pd.Series, settings: dict[str, Any]) -> pd.Series:
    labels = pd.Series(pd.NA, index=dates.index, dtype="string")
    for period in settings["counterfactual_periods"]:
        selected = dates.between(period["start_date"], period["end_date"])
        if labels.loc[selected].notna().any():
            raise ValueError("Configured counterfactual periods overlap")
        labels.loc[selected] = period["name"]
    return labels


def build_model_table(config: dict) -> pd.DataFrame:
    """Join the complete predictor panel to the available daily PM2.5 observations."""
    settings = _model_settings(config)
    predictors = pd.read_csv(config["paths"]["predictors"], low_memory=False)
    daily = pd.read_csv(config["paths"]["daily"], low_memory=False)
    target = settings["target"]
    features = list(settings["predictors"])

    required_predictors = [*JOIN_COLUMNS, *PAIR_COLUMNS, *features]
    missing_predictors = sorted(set(required_predictors) - set(predictors.columns))
    if missing_predictors:
        raise ValueError(f"Predictor table is missing columns: {missing_predictors}")
    required_daily = [*JOIN_COLUMNS, target, "daily_qc_pass"]
    missing_daily = sorted(set(required_daily) - set(daily.columns))
    if missing_daily:
        raise ValueError(f"Daily table is missing columns: {missing_daily}")

    for table in (predictors, daily):
        table["date"] = pd.to_datetime(table["date"])
    if predictors.duplicated(JOIN_COLUMNS).any():
        raise ValueError("Predictor table contains duplicate sensor-location dates")
    if daily.duplicated(JOIN_COLUMNS).any():
        raise ValueError("Daily PM2.5 table contains duplicate sensor-location dates")

    outcome_columns = [
        *JOIN_COLUMNS,
        target,
        "observed_hours",
        "valid_hours",
        "data_source",
        "daily_qc_pass",
    ]
    available_outcome_columns = [column for column in outcome_columns if column in daily.columns]
    table = predictors.merge(
        daily[available_outcome_columns],
        on=JOIN_COLUMNS,
        how="left",
        validate="one_to_one",
        indicator="sensor_observation_available",
    )
    table["sensor_observation_available"] = table["sensor_observation_available"].eq("both")
    table["daily_qc_pass"] = _as_boolean(table["daily_qc_pass"])
    table.loc[~table["daily_qc_pass"], target] = np.nan

    table["is_heating_month"] = table["date"].dt.month.isin(settings["training"]["include_months"])
    table["analysis_period"] = "outside_analysis_period"
    training = settings["training"]
    pre_lez = table["date"].between(training["start_date"], training["end_date"])
    table.loc[pre_lez, "analysis_period"] = "pre_lez"
    post_labels = _period_labels(table["date"], settings)
    table.loc[post_labels.notna(), "analysis_period"] = post_labels.dropna()
    table["eligible_for_training"] = (
        pre_lez & table["is_heating_month"] & table["daily_qc_pass"] & table[target].notna()
    )

    missing_feature_values = table[features].isna().sum()
    if missing_feature_values.any():
        details = missing_feature_values[missing_feature_values.gt(0)].to_dict()
        raise ValueError(f"Model predictors contain missing values: {details}")
    non_numeric = [
        column for column in features if not pd.api.types.is_numeric_dtype(table[column])
    ]
    if non_numeric:
        raise ValueError(f"Random Forest predictors must be numeric: {non_numeric}")

    table = table.sort_values(["date", "location_id", "sensor_id"]).reset_index(drop=True)
    table["date"] = table["date"].dt.date.astype(str)
    _write_csv(table, config["paths"]["model_table"])
    return table


def _read_model_table(config: dict, settings: dict[str, Any]) -> pd.DataFrame:
    table = pd.read_csv(config["paths"]["model_table"], low_memory=False)
    table["date"] = pd.to_datetime(table["date"])
    table["daily_qc_pass"] = _as_boolean(table["daily_qc_pass"])
    features = list(settings["predictors"])
    missing = sorted(set([settings["target"], *features]) - set(table.columns))
    if missing:
        raise ValueError(f"Model table is missing columns: {missing}")
    return table


def _training_observations(table: pd.DataFrame, settings: dict[str, Any]) -> pd.DataFrame:
    training = settings["training"]
    target = settings["target"]
    selected = table.loc[
        table["date"].between(training["start_date"], training["end_date"])
        & table["date"].dt.month.isin(training["include_months"])
        & table["daily_qc_pass"]
        & table[target].notna()
    ].copy()
    if selected.empty:
        raise ValueError("No eligible pre-LEZ training observations were found")
    missing = selected[settings["predictors"]].isna().sum()
    if missing.any():
        details = missing[missing.gt(0)].to_dict()
        raise ValueError(f"Training predictors contain missing values: {details}")
    return selected.reset_index(drop=True)


def _random_forest_pipeline(settings: dict[str, Any], n_jobs: int) -> Pipeline:
    forest = RandomForestRegressor(
        random_state=int(settings["random_forest"]["random_state"]),
        n_jobs=n_jobs,
    )
    return Pipeline([("model", forest)])


def _gradient_boosting_pipeline(settings: dict[str, Any]) -> Pipeline:
    model = HistGradientBoostingRegressor(
        random_state=int(settings["gradient_boosting"]["random_state"]),
        early_stopping=False,
    )
    return Pipeline([("model", model)])


def _blocked_splits(
    observations: pd.DataFrame,
    settings: dict[str, Any],
) -> tuple[list[tuple[np.ndarray, np.ndarray]], list[dict[str, Any]]]:
    splits = []
    details = []
    training_start = pd.Timestamp(settings["training"]["start_date"])
    for fold in settings["validation"]["folds"]:
        train_end = pd.Timestamp(fold["train_end"])
        validation_start = pd.Timestamp(fold["validation_start"])
        validation_end = pd.Timestamp(fold["validation_end"])
        if train_end >= validation_start:
            raise ValueError(f"Training and validation overlap in fold {fold['name']}")
        train_index = observations.index[
            observations["date"].between(training_start, train_end)
        ].to_numpy()
        validation_index = observations.index[
            observations["date"].between(validation_start, validation_end)
        ].to_numpy()
        if not len(train_index) or not len(validation_index):
            raise ValueError(f"Fold {fold['name']} has an empty training or validation block")
        splits.append((train_index, validation_index))
        details.append(
            {
                "name": fold["name"],
                "train_start": observations.loc[train_index, "date"].min().date().isoformat(),
                "train_end": observations.loc[train_index, "date"].max().date().isoformat(),
                "validation_start": observations.loc[validation_index, "date"]
                .min()
                .date()
                .isoformat(),
                "validation_end": observations.loc[validation_index, "date"]
                .max()
                .date()
                .isoformat(),
                "training_rows": int(len(train_index)),
                "validation_rows": int(len(validation_index)),
            }
        )
    return splits, details


def _test_split(
    observations: pd.DataFrame,
    settings: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    test_period = settings["validation"]["test_period"]
    training_start = pd.Timestamp(settings["training"]["start_date"])
    train_end = pd.Timestamp(test_period["train_end"])
    test_start = pd.Timestamp(test_period["test_start"])
    test_end = pd.Timestamp(test_period["test_end"])
    if train_end >= test_start:
        raise ValueError("Training and the recent test period overlap")
    train_index = observations.index[
        observations["date"].between(training_start, train_end)
    ].to_numpy()
    test_index = observations.index[
        observations["date"].between(test_start, test_end)
    ].to_numpy()
    if not len(train_index) or not len(test_index):
        raise ValueError("The recent test period has an empty training or test block")
    details = {
        "name": test_period["name"],
        "train_start": observations.loc[train_index, "date"].min().date().isoformat(),
        "train_end": observations.loc[train_index, "date"].max().date().isoformat(),
        "test_start": observations.loc[test_index, "date"].min().date().isoformat(),
        "test_end": observations.loc[test_index, "date"].max().date().isoformat(),
        "training_rows": int(len(train_index)),
        "test_rows": int(len(test_index)),
    }
    return train_index, test_index, details


def _regression_metrics(observed: pd.Series, predicted: np.ndarray) -> dict[str, float]:
    observed_array = observed.to_numpy(dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    return {
        "mae": float(mean_absolute_error(observed_array, predicted_array)),
        "rmse": float(root_mean_squared_error(observed_array, predicted_array)),
        "r2": float(r2_score(observed_array, predicted_array)),
        "mean_error": float(np.mean(predicted_array - observed_array)),
    }


def _sensor_mean_prediction(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    target: str,
) -> np.ndarray:
    sensor_means = train.groupby(["location_id", "sensor_id"])[target].mean()
    overall_mean = float(train[target].mean())
    keys = pd.MultiIndex.from_frame(validation[["location_id", "sensor_id"]])
    return sensor_means.reindex(keys).fillna(overall_mean).to_numpy(dtype=float)


def _metrics_by_sensor(
    predictions: pd.DataFrame,
    period_column: str,
    row_count_column: str,
    pooled_name: str | None = None,
) -> pd.DataFrame:
    rows = []
    model_columns = (
        ("random_forest", "rf_predicted_pm2_5"),
        ("sensor_mean_benchmark", "sensor_mean_predicted_pm2_5"),
    )
    pair_columns = ["location_id", "sensor_id"]
    for period, period_table in predictions.groupby(period_column, sort=False):
        for _, group in period_table.groupby(pair_columns, sort=True):
            for model_name, prediction_column in model_columns:
                rows.append(
                    {
                        period_column: period,
                        "model": model_name,
                        **group[PAIR_COLUMNS].iloc[0].to_dict(),
                        row_count_column: len(group),
                        **_regression_metrics(
                            group["observed_pm2_5"], group[prediction_column]
                        ),
                    }
                )
    if pooled_name is not None:
        for _, group in predictions.groupby(pair_columns, sort=True):
            for model_name, prediction_column in model_columns:
                rows.append(
                    {
                        period_column: pooled_name,
                        "model": model_name,
                        **group[PAIR_COLUMNS].iloc[0].to_dict(),
                        row_count_column: len(group),
                        **_regression_metrics(
                            group["observed_pm2_5"], group[prediction_column]
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _season_part_metrics(predictions: pd.DataFrame) -> pd.DataFrame:
    table = predictions.copy()
    table["season_part"] = np.where(table["date"].dt.month.ge(10), "oct_dec", "jan_mar")
    rows = []
    for season_part, group in table.groupby("season_part", sort=False):
        for model_name, prediction_column in (
            ("random_forest", "rf_predicted_pm2_5"),
            ("sensor_mean_benchmark", "sensor_mean_predicted_pm2_5"),
        ):
            rows.append(
                {
                    "season_part": season_part,
                    "model": model_name,
                    "validation_rows": len(group),
                    **_regression_metrics(group["observed_pm2_5"], group[prediction_column]),
                }
            )
    return pd.DataFrame(rows)


def _metrics_by_month(
    predictions: pd.DataFrame,
    period_column: str,
    row_count_column: str,
) -> pd.DataFrame:
    """Summarise observed values, predictions and residuals by calendar month."""
    table = predictions.copy()
    table["year_month"] = table["date"].dt.to_period("M").astype(str)
    rows = []
    for (period, year_month), group in table.groupby(
        [period_column, "year_month"], sort=False
    ):
        for model_name, prediction_column in (
            ("random_forest", "rf_predicted_pm2_5"),
            ("sensor_mean_benchmark", "sensor_mean_predicted_pm2_5"),
        ):
            rows.append(
                {
                    period_column: period,
                    "year_month": year_month,
                    "model": model_name,
                    row_count_column: len(group),
                    "observed_mean": float(group["observed_pm2_5"].mean()),
                    "predicted_mean": float(group[prediction_column].mean()),
                    **_regression_metrics(group["observed_pm2_5"], group[prediction_column]),
                }
            )
    return pd.DataFrame(rows)


def _predictor_shift(
    training: pd.DataFrame,
    evaluation: pd.DataFrame,
    period_type: str,
    period_name: str,
    predictors: list[str],
) -> list[dict[str, Any]]:
    """Compare predictor distributions in training and later evaluation data."""
    rows = []
    for predictor in predictors:
        training_mean = float(training[predictor].mean())
        training_std = float(training[predictor].std())
        evaluation_mean = float(evaluation[predictor].mean())
        rows.append(
            {
                "period_type": period_type,
                "period": period_name,
                "predictor": predictor,
                "training_rows": len(training),
                "evaluation_rows": len(evaluation),
                "training_mean": training_mean,
                "training_std": training_std,
                "evaluation_mean": evaluation_mean,
                "evaluation_std": float(evaluation[predictor].std()),
                "mean_difference": evaluation_mean - training_mean,
                "standardised_mean_difference": (
                    (evaluation_mean - training_mean) / training_std
                    if training_std > 0
                    else np.nan
                ),
            }
        )
    return rows


def _candidate_table(search: GridSearchCV, fold_details: list[dict[str, Any]]) -> pd.DataFrame:
    """Create an inspectable table of training and validation error for every candidate."""
    raw = pd.DataFrame(search.cv_results_)
    table = pd.DataFrame(
        {
            "validation_rank": raw["rank_test_mae"].astype(int),
            "mean_validation_mae": -raw["mean_test_mae"],
            "std_validation_mae": raw["std_test_mae"],
            "se_validation_mae": raw["std_test_mae"] / np.sqrt(len(fold_details)),
            "mean_validation_rmse": -raw["mean_test_rmse"],
            "mean_validation_r2": raw["mean_test_r2"],
            "mean_training_mae": -raw["mean_train_mae"],
            "training_validation_gap": -raw["mean_test_mae"] + raw["mean_train_mae"],
            "mean_fit_time_seconds": raw["mean_fit_time"],
            "parameters_json": [json.dumps(params, sort_keys=True) for params in raw["params"]],
        }
    )
    for index, fold in enumerate(fold_details):
        name = fold["name"]
        table[f"validation_mae__{name}"] = -raw[f"split{index}_test_mae"]
        table[f"validation_rmse__{name}"] = -raw[f"split{index}_test_rmse"]
        table[f"validation_r2__{name}"] = raw[f"split{index}_test_r2"]
        table[f"training_mae__{name}"] = -raw[f"split{index}_train_mae"]
    parameter_columns = [column for column in raw if column.startswith("param_")]
    for column in parameter_columns:
        table[column] = raw[column]
    table = table.sort_values(
        ["mean_validation_mae", "training_validation_gap", "parameters_json"],
        kind="stable",
    ).reset_index(drop=True)
    table.insert(0, "candidate_rank", np.arange(1, len(table) + 1))
    best_standard_error = float(table.loc[0, "se_validation_mae"])
    threshold = float(table.loc[0, "mean_validation_mae"]) + best_standard_error
    table["within_one_standard_error"] = table["mean_validation_mae"].le(threshold)
    return table


def _run_grid_search(
    observations: pd.DataFrame,
    settings: dict[str, Any],
    model_family: str,
) -> tuple[pd.DataFrame, list[tuple[np.ndarray, np.ndarray]], list[dict[str, Any]]]:
    splits, fold_details = _blocked_splits(observations, settings)
    search_settings = settings[model_family]["search"]
    parameter_grid = search_settings.get("parameter_grid")
    if not parameter_grid or any(not values for values in parameter_grid.values()):
        raise ValueError(f"{model_family} must define a non-empty parameter grid")
    if model_family == "random_forest":
        estimator = _random_forest_pipeline(settings, n_jobs=1)
    elif model_family == "gradient_boosting":
        estimator = _gradient_boosting_pipeline(settings)
    else:
        raise ValueError(f"Unsupported model family: {model_family}")
    search = GridSearchCV(
        estimator=estimator,
        param_grid=parameter_grid,
        scoring={
            "mae": settings["validation"]["scoring"],
            "rmse": "neg_root_mean_squared_error",
            "r2": "r2",
        },
        cv=splits,
        refit=False,
        n_jobs=int(search_settings["n_jobs"]),
        verbose=int(search_settings["verbose"]),
        return_train_score=True,
        error_score="raise",
    )
    features = list(settings["predictors"])
    search.fit(observations[features], observations[settings["target"]])
    return _candidate_table(search, fold_details), splits, fold_details


def validate_random_forest(config: dict) -> dict[str, Any]:
    """Evaluate all configured Random Forest candidates without selecting one."""
    settings = _model_settings(config)
    observations = _training_observations(_read_model_table(config, settings), settings)
    tuning, _, fold_details = _run_grid_search(observations, settings, "random_forest")
    search_id = pd.Timestamp.now(tz="UTC").isoformat()
    tuning.insert(1, "search_id", search_id)
    tuning.insert(2, "model_family", "random_forest")
    _write_csv(tuning, config["paths"]["tuning_results"])
    best = tuning.iloc[0]
    return {
        "training_rows": len(observations),
        "validation_folds": len(fold_details),
        "parameter_sets_tested": len(tuning),
        "best_cv_mae": float(best["mean_validation_mae"]),
        "lowest_mae_candidate_rank": int(best["candidate_rank"]),
        "one_standard_error_candidates": int(tuning["within_one_standard_error"].sum()),
        "tuning_results": str(config["paths"]["tuning_results"]),
        "search_id": search_id,
        "selection_required": True,
    }


def validate_gradient_boosting(config: dict) -> dict[str, Any]:
    """Optionally compare Gradient Boosting candidates on the same blocked folds."""
    settings = _model_settings(config)
    if "gradient_boosting" not in settings:
        raise ValueError("No optional gradient_boosting model is configured")
    observations = _training_observations(_read_model_table(config, settings), settings)
    tuning, _, fold_details = _run_grid_search(observations, settings, "gradient_boosting")
    search_id = pd.Timestamp.now(tz="UTC").isoformat()
    tuning.insert(1, "search_id", search_id)
    tuning.insert(2, "model_family", "hist_gradient_boosting")
    _write_csv(tuning, config["paths"]["gradient_boosting_tuning_results"])
    best = tuning.iloc[0]
    return {
        "training_rows": len(observations),
        "validation_folds": len(fold_details),
        "parameter_sets_tested": len(tuning),
        "best_cv_mae": float(best["mean_validation_mae"]),
        "lowest_mae_candidate_rank": int(best["candidate_rank"]),
        "one_standard_error_candidates": int(tuning["within_one_standard_error"].sum()),
        "tuning_results": str(config["paths"]["gradient_boosting_tuning_results"]),
        "search_id": search_id,
    }


def select_random_forest(
    config: dict,
    candidate_rank: int,
    selection_reason: str,
) -> dict[str, Any]:
    """Record one RF candidate, then evaluate it on validation and recent holdout data."""
    selection_reason = selection_reason.strip()
    if not selection_reason:
        raise ValueError("A validation-based selection reason is required")
    settings = _model_settings(config)
    observations = _training_observations(_read_model_table(config, settings), settings)
    features = list(settings["predictors"])
    target = settings["target"]
    tuning_path = Path(config["paths"]["tuning_results"])
    if not tuning_path.exists():
        raise FileNotFoundError("Run Stage 9 RF candidate validation before selecting a model")
    tuning = pd.read_csv(tuning_path)
    required_tuning_columns = {"candidate_rank", "parameters_json", "search_id"}
    missing_tuning_columns = sorted(required_tuning_columns - set(tuning.columns))
    if missing_tuning_columns:
        raise ValueError(
            "The RF tuning table predates explicit candidate selection; rerun Stage 9"
        )
    search_ids = tuning["search_id"].dropna().unique()
    if len(search_ids) != 1:
        raise ValueError("The RF tuning table does not identify one reproducible search run")
    search_id = str(search_ids[0])
    candidate = tuning.loc[tuning["candidate_rank"].eq(candidate_rank)]
    if len(candidate) != 1:
        available = tuning["candidate_rank"].astype(int).tolist()
        raise ValueError(f"Candidate rank {candidate_rank} is unavailable; choose from {available}")
    candidate = candidate.iloc[0]
    parameters = json.loads(candidate["parameters_json"])
    splits, fold_details = _blocked_splits(observations, settings)
    prediction_tables = []
    metric_rows = []
    shift_rows = []
    for (train_index, validation_index), fold in zip(splits, fold_details, strict=True):
        train = observations.loc[train_index]
        validation = observations.loc[validation_index]
        model = clone(_random_forest_pipeline(settings, n_jobs=-1)).set_params(**parameters)
        model.fit(train[features], train[target])
        rf_prediction = model.predict(validation[features])
        benchmark_prediction = _sensor_mean_prediction(train, validation, target)
        shift_rows.extend(
            _predictor_shift(train, validation, "validation", fold["name"], features)
        )

        fold_predictions = validation[[*PAIR_COLUMNS, "date", target]].copy()
        fold_predictions.insert(0, "fold", fold["name"])
        fold_predictions = fold_predictions.rename(columns={target: "observed_pm2_5"})
        fold_predictions["rf_predicted_pm2_5"] = rf_prediction
        fold_predictions["sensor_mean_predicted_pm2_5"] = benchmark_prediction
        fold_predictions["rf_error"] = rf_prediction - fold_predictions["observed_pm2_5"]
        fold_predictions["sensor_mean_error"] = (
            benchmark_prediction - fold_predictions["observed_pm2_5"]
        )
        prediction_tables.append(fold_predictions)

        for model_name, prediction in (
            ("random_forest", rf_prediction),
            ("sensor_mean_benchmark", benchmark_prediction),
        ):
            metric_rows.append(
                {
                    "fold": fold["name"],
                    "model": model_name,
                    "training_rows": fold["training_rows"],
                    "validation_rows": fold["validation_rows"],
                    **_regression_metrics(validation[target], prediction),
                }
            )

    predictions = pd.concat(prediction_tables, ignore_index=True)
    for model_name, column in (
        ("random_forest", "rf_predicted_pm2_5"),
        ("sensor_mean_benchmark", "sensor_mean_predicted_pm2_5"),
    ):
        metric_rows.append(
            {
                "fold": "all_validation_blocks",
                "model": model_name,
                "training_rows": pd.NA,
                "validation_rows": len(predictions),
                **_regression_metrics(predictions["observed_pm2_5"], predictions[column]),
            }
        )
    metrics = pd.DataFrame(metric_rows)
    sensor_metrics = _metrics_by_sensor(
        predictions,
        period_column="fold",
        row_count_column="validation_rows",
        pooled_name="all_validation_blocks",
    )
    season_part_metrics = _season_part_metrics(predictions)
    validation_month_metrics = _metrics_by_month(
        predictions,
        period_column="fold",
        row_count_column="validation_rows",
    )

    test_train_index, test_index, test_details = _test_split(observations, settings)
    selected = {
        "selected_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "holdout_evaluated_utc": None,
        "search_id": search_id,
        "model_family": "random_forest",
        "candidate_rank": int(candidate_rank),
        "selection_reason": selection_reason,
        "scoring": settings["validation"]["scoring"],
        "selected_cv_mae": float(candidate["mean_validation_mae"]),
        "selected_cv_standard_deviation": float(candidate["std_validation_mae"]),
        "selected_cv_standard_error": float(candidate["se_validation_mae"]),
        "selected_cv_rmse": float(candidate["mean_validation_rmse"]),
        "selected_cv_r2": float(candidate["mean_validation_r2"]),
        "mean_training_mae": float(candidate["mean_training_mae"]),
        "training_validation_gap": float(candidate["training_validation_gap"]),
        "within_one_standard_error": str(candidate["within_one_standard_error"]).lower()
        == "true",
        "best_parameters": parameters,
        "predictors": features,
        "folds": fold_details,
        "test_period": test_details,
    }
    # Persist the audited validation-based choice before reading the holdout response.
    _write_json(selected, config["paths"]["selected_parameters"])

    test_train = observations.loc[test_train_index]
    test = observations.loc[test_index]
    test_model = clone(_random_forest_pipeline(settings, n_jobs=-1)).set_params(**parameters)
    test_model.fit(test_train[features], test_train[target])
    test_rf_prediction = test_model.predict(test[features])
    test_benchmark_prediction = _sensor_mean_prediction(test_train, test, target)
    test_predictions = test[[*PAIR_COLUMNS, "date", target]].copy()
    test_predictions.insert(0, "test_period", test_details["name"])
    test_predictions = test_predictions.rename(columns={target: "observed_pm2_5"})
    test_predictions["rf_predicted_pm2_5"] = test_rf_prediction
    test_predictions["sensor_mean_predicted_pm2_5"] = test_benchmark_prediction
    test_predictions["rf_error"] = (
        test_rf_prediction - test_predictions["observed_pm2_5"]
    )
    test_predictions["sensor_mean_error"] = (
        test_benchmark_prediction - test_predictions["observed_pm2_5"]
    )
    test_metric_rows = []
    for model_name, prediction in (
        ("random_forest", test_rf_prediction),
        ("sensor_mean_benchmark", test_benchmark_prediction),
    ):
        test_metric_rows.append(
            {
                "test_period": test_details["name"],
                "model": model_name,
                "training_rows": test_details["training_rows"],
                "test_rows": test_details["test_rows"],
                **_regression_metrics(test[target], prediction),
            }
        )
    test_metrics = pd.DataFrame(test_metric_rows)
    test_sensor_metrics = _metrics_by_sensor(
        test_predictions,
        period_column="test_period",
        row_count_column="test_rows",
    )
    test_month_metrics = _metrics_by_month(
        test_predictions,
        period_column="test_period",
        row_count_column="test_rows",
    )
    shift_rows.extend(
        _predictor_shift(test_train, test, "recent_holdout", test_details["name"], features)
    )
    _write_csv(metrics, config["paths"]["validation_metrics"])
    _write_csv(sensor_metrics, config["paths"]["validation_metrics_by_sensor"])
    _write_csv(season_part_metrics, config["paths"]["validation_metrics_by_season_part"])
    _write_csv(validation_month_metrics, config["paths"]["validation_metrics_by_month"])
    _write_csv(predictions, config["paths"]["validation_predictions"])
    _write_csv(test_metrics, config["paths"]["test_metrics"])
    _write_csv(test_sensor_metrics, config["paths"]["test_metrics_by_sensor"])
    _write_csv(test_month_metrics, config["paths"]["test_metrics_by_month"])
    _write_csv(test_predictions, config["paths"]["test_predictions"])
    _write_csv(pd.DataFrame(shift_rows), config["paths"]["predictor_shift"])
    selected["holdout_evaluated_utc"] = pd.Timestamp.now(tz="UTC").isoformat()
    _write_json(selected, config["paths"]["selected_parameters"])
    return {
        "training_rows": len(observations),
        "validation_folds": len(splits),
        "candidate_rank": int(candidate_rank),
        "selected_cv_mae": float(candidate["mean_validation_mae"]),
        "parameters": parameters,
        "metrics": str(config["paths"]["validation_metrics"]),
        "test_period": test_details["name"],
        "test_rows": test_details["test_rows"],
        "test_metrics": str(config["paths"]["test_metrics"]),
        "predictor_shift": str(config["paths"]["predictor_shift"]),
        "selected_parameters": str(config["paths"]["selected_parameters"]),
    }


def train_random_forest(config: dict) -> dict[str, Any]:
    """Fit the selected model on all accepted pre-LEZ heating-month observations."""
    settings = _model_settings(config)
    observations = _training_observations(_read_model_table(config, settings), settings)
    features = list(settings["predictors"])
    target = settings["target"]
    selected_path = Path(config["paths"]["selected_parameters"])
    if not selected_path.exists():
        raise FileNotFoundError(
            "No Random Forest candidate has been selected; run Stage 9b before training"
        )
    with selected_path.open(encoding="utf-8") as handle:
        selected = json.load(handle)
    if selected.get("model_family") != "random_forest" or "candidate_rank" not in selected:
        raise ValueError(
            "The selected-parameter file predates explicit candidate selection; "
            "rerun Stages 9 and 9b"
        )
    tuning_path = Path(config["paths"]["tuning_results"])
    if not tuning_path.exists():
        raise FileNotFoundError("The RF tuning table is missing; rerun Stages 9 and 9b")
    current_tuning = pd.read_csv(tuning_path)
    if "search_id" not in current_tuning:
        raise ValueError("The RF tuning table predates Stage 9 candidate selection")
    current_search_ids = current_tuning["search_id"].dropna().unique()
    if len(current_search_ids) != 1 or selected.get("search_id") != str(
        current_search_ids[0]
    ):
        raise ValueError(
            "The selected candidate does not belong to the current Stage 9 search; "
            "rerun Stage 9b"
        )
    if not selected.get("holdout_evaluated_utc"):
        raise ValueError("The selected candidate has not completed recent-holdout evaluation")
    parameters = selected["best_parameters"]

    model = _random_forest_pipeline(
        settings,
        n_jobs=int(settings["random_forest"]["final_n_jobs"]),
    ).set_params(**parameters)
    model.fit(observations[features], observations[target])
    bundle = {
        "model": model,
        "predictors": features,
        "target": target,
        "training_start": observations["date"].min().date().isoformat(),
        "training_end": observations["date"].max().date().isoformat(),
        "training_rows": len(observations),
        "sensor_location_pairs": int(
            observations[["location_id", "sensor_id"]].drop_duplicates().shape[0]
        ),
        "parameters": parameters,
        "selected_candidate_rank": int(selected["candidate_rank"]),
        "selection_reason": selected["selection_reason"],
        "random_state": int(settings["random_forest"]["random_state"]),
        "scikit_learn_version": sklearn.__version__,
    }
    output = ensure_parent(Path(config["paths"]["model_file"]))
    part = output.with_suffix(output.suffix + ".part")
    joblib.dump(bundle, part)
    part.replace(output)

    forest = model.named_steps["model"]
    importance = pd.DataFrame(
        {
            "predictor": features,
            "impurity_importance": forest.feature_importances_,
        }
    ).sort_values("impurity_importance", ascending=False)
    _write_csv(importance, config["paths"]["feature_importance"])
    metadata = {key: value for key, value in bundle.items() if key != "model"}
    _write_json(metadata, config["paths"]["model_metadata"])
    return {
        "training_rows": len(observations),
        "sensor_location_pairs": bundle["sensor_location_pairs"],
        "training_start": bundle["training_start"],
        "training_end": bundle["training_end"],
        "model": str(output),
        "feature_importance": str(config["paths"]["feature_importance"]),
    }


def predict_counterfactual(config: dict) -> pd.DataFrame:
    """Predict the no-LEZ PM2.5 baseline for the configured post-intervention periods."""
    settings = _model_settings(config)
    table = _read_model_table(config, settings)
    bundle = joblib.load(config["paths"]["model_file"])
    features = list(bundle["predictors"])
    if features != list(settings["predictors"]):
        raise ValueError("Saved model predictors do not match the current model configuration")

    table["counterfactual_period"] = _period_labels(table["date"], settings)
    post = table.loc[table["counterfactual_period"].notna()].copy()
    if post.empty:
        raise ValueError("No model-table rows fall within the counterfactual periods")
    if post[features].isna().any().any():
        raise ValueError("Counterfactual predictor rows contain missing values")
    post["predicted_pm2_5_no_lez"] = bundle["model"].predict(post[features])
    post = post.rename(columns={settings["target"]: "observed_pm2_5"})
    post["observed_minus_predicted_pm2_5"] = (
        post["observed_pm2_5"] - post["predicted_pm2_5_no_lez"]
    )
    post["relative_difference_pct"] = np.where(
        post["predicted_pm2_5_no_lez"].gt(0) & post["observed_pm2_5"].notna(),
        100.0
        * post["observed_minus_predicted_pm2_5"]
        / post["predicted_pm2_5_no_lez"],
        np.nan,
    )
    post["date"] = post["date"].dt.date.astype(str)
    post = post.sort_values(["date", "location_id", "sensor_id"]).reset_index(drop=True)
    _write_csv(post, config["paths"]["predictions"])
    return post


def _counterfactual_summary(group: pd.DataFrame) -> dict[str, Any]:
    compared = group.loc[group["observed_pm2_5"].notna()]
    compared_predicted = compared["predicted_pm2_5_no_lez"]
    observed = compared["observed_pm2_5"]
    observed_mean = float(observed.mean()) if len(compared) else np.nan
    predicted_mean = float(compared_predicted.mean()) if len(compared) else np.nan
    difference = observed_mean - predicted_mean if len(compared) else np.nan
    return {
        "prediction_rows": len(group),
        "observed_rows": len(compared),
        "observed_coverage": len(compared) / len(group) if len(group) else np.nan,
        "sensor_location_pairs": int(
            group[["location_id", "sensor_id"]].drop_duplicates().shape[0]
        ),
        "predicted_mean_all_rows": float(group["predicted_pm2_5_no_lez"].mean()),
        "observed_mean_compared_rows": observed_mean,
        "predicted_mean_compared_rows": predicted_mean,
        "mean_observed_minus_predicted": difference,
        "relative_difference_pct": (
            100.0 * difference / predicted_mean if len(compared) and predicted_mean > 0 else np.nan
        ),
        "median_observed_minus_predicted": (
            float(compared["observed_minus_predicted_pm2_5"].median())
            if len(compared)
            else np.nan
        ),
    }


def summarise_counterfactual(config: dict) -> dict[str, Any]:
    """Summarise observed and no-LEZ predictions by period, date and sensor location."""
    predictions = pd.read_csv(config["paths"]["predictions"], low_memory=False)
    predictions["date"] = pd.to_datetime(predictions["date"])

    period_rows = [
        {"counterfactual_period": name, **_counterfactual_summary(group)}
        for name, group in predictions.groupby("counterfactual_period", sort=False)
    ]
    period_rows.append(
        {"counterfactual_period": "all_post_periods", **_counterfactual_summary(predictions)}
    )
    period_summary = pd.DataFrame(period_rows)

    date_rows = [
        {
            "counterfactual_period": period,
            "date": date.date().isoformat(),
            **_counterfactual_summary(group),
        }
        for (period, date), group in predictions.groupby(
            ["counterfactual_period", "date"], sort=True
        )
    ]
    date_summary = pd.DataFrame(date_rows)

    sensor_rows = [
        {
            "counterfactual_period": period,
            "location": group["location"].iloc[0],
            "location_id": location_id,
            "sensor_id": sensor_id,
            "lat": group["lat"].iloc[0],
            "lon": group["lon"].iloc[0],
            **_counterfactual_summary(group),
        }
        for (period, location_id, sensor_id), group in predictions.groupby(
            ["counterfactual_period", "location_id", "sensor_id"], sort=True
        )
    ]
    sensor_summary = pd.DataFrame(sensor_rows)

    _write_csv(period_summary, config["paths"]["counterfactual_summary"])
    _write_csv(date_summary, config["paths"]["counterfactual_by_date"])
    _write_csv(sensor_summary, config["paths"]["counterfactual_by_sensor"])
    return {
        "periods": int(predictions["counterfactual_period"].nunique()),
        "prediction_rows": len(predictions),
        "observed_rows": int(predictions["observed_pm2_5"].notna().sum()),
        "period_summary": str(config["paths"]["counterfactual_summary"]),
        "date_summary": str(config["paths"]["counterfactual_by_date"]),
        "sensor_summary": str(config["paths"]["counterfactual_by_sensor"]),
    }
