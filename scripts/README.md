# Workflow scripts

The numbered scripts make the seminar workflow explicit. Stages 1–4 are implemented. The
remaining stages are reserved until the sensor panel and predictor choices have been inspected.

| Stage | Script | Status |
|---|---|---|
| 1 | `01_build_sensor_manifest.py` | implemented |
| 2 | `02_download_archive.py` | implemented |
| 3 | `03_prepare_sensor_observations.py` | implemented |
| 4 | `04_check_sensor_completeness.py` | implemented |
| 5 | `05_prepare_predictors.py` | planned |
| 6 | `06_build_model_table.py` | planned |
| 7 | `07_validate_random_forest.py` | planned |
| 8 | `08_train_random_forest.py` | planned |
| 9 | `09_predict_counterfactual.py` | planned |
| 10 | `10_summarise_results.py` | planned |

Run a script from the repository root after installing the package:

```bash
python scripts/01_build_sensor_manifest.py --config configs/pipeline.yaml
```

The future filenames document the intended order; empty placeholder Python files are not used.
