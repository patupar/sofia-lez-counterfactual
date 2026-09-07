# Workflow scripts

The numbered scripts make the seminar workflow explicit. Stages 1–7 are implemented. The
remaining stages are reserved until the daily predictor table has been inspected.

| Stage | Script | Status |
|---|---|---|
| 1 | `01_build_sensor_manifest.py` | implemented |
| 2 | `02_download_archive.py` | implemented |
| 3 | `03_prepare_sensor_observations.py` | implemented |
| 4 | `04_check_sensor_completeness.py` | implemented |
| 5 | `05_select_stable_panel.py` | implemented |
| 6 | `06_download_era5.py` | implemented |
| 7 | `07_prepare_predictors.py` | implemented |
| 8 | `08_build_model_table.py` | planned |
| 9 | `09_validate_random_forest.py` | planned |
| 10 | `10_train_random_forest.py` | planned |
| 11 | `11_predict_counterfactual.py` | planned |
| 12 | `12_summarise_results.py` | planned |

Run a script from the repository root after installing the package:

```bash
python scripts/01_build_sensor_manifest.py --config configs/pipeline.yaml
```

The future filenames document the intended order; empty placeholder Python files are not used.

`06_download_era5.py` requires external CDS credentials. The script accepts both a direct NetCDF
response and the split instantaneous/accumulated ZIP response currently returned for the selected
variables. Requests and cache files are monthly to remain below the CDS request-cost limit.
Retained responses and completed monthly files are reused; the December 2017 cache created by the
earlier annual naming scheme is migrated automatically. Tests and the synthetic sample workflow
do not contact CDS.
