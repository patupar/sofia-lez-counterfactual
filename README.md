# Am I breathing cleaner air? | Дишам ли по-чист въздух?

## Prelude

This repository holds the codebase for a seminar paper initially conceived for the Institute of Geography, Ruprecht-Karl-University Heidelberg. The goal of this work is to present a reproducible counterfactual study of the recently introduced residential-heating low-emission zone (LEZ) in Sofia, Bulgaria. Later versions will aim to bring this academic work to public use. Ultimately, residents of Sofia should be able to observe on a day-by-day basis whether air quality in their neighbourhood has actually improved as a result of the LEZ intervention.   

## General information: 'Counterfactual Assessment of Sofia's Residential Heating Low Emission Zone'
On the 1 January 2025, Sofia implemented Europe’s first low-emission zone (LEZ) targeting residential heating. The
intervention prohibits the use of solid-fuels in buildings across nine districts, given operational district-heating or gas distribution networks are available. The codebase for the above mentioned study presents an exploratory counterfactual assessment of changes in ambient PM2.5 concentrations following the intervention. To the author’s
knowledge, it is the first such assessment of Sofia’s residential-heating LEZ to use post-intervention
PM2.5 measurements.

Daily PM2.5 observations from BGAir’s community-operated sensor network are used, as at the point writing, Sofia's regulatory monitoring network exhibits spatial coverage to an unsatisfactory extend. A secondary objective that has arisen through this work is exploring whether community-operate sensor networks and volunteered geographic information as a whole, can be leveraged in the study of Sofia's urban environment and potentially inform public decision making.    

Random forest models trained on pre-intervention observations from 2018–2024 predict PM2.5 concentrations during the heating
periods between January 2025 and March 2026, accounting for meteorological and temporal variation.
Model predictions reflect expected PM2.5 concentrations in absence of the LEZ intervention.

## Getting started

The following setup is used on macOS. Python 3.11 or newer is required.

```bash
git clone https://github.com/patupar/sofia-lez-counterfactual.git
cd sofia-lez-counterfactual

python -m venv .venv
source .venv/bin/activate          
python -m pip install -e ".[dev]"
```

Stage 6 uses the Copernicus Climate Data Store (CDS) API. Create a CDS account, accept the
licence for the ERA5 single-level dataset, and place the personal access token outside the
repository in `~/.cdsapirc`:

```yaml
url: https://cds.climate.copernicus.eu/api
key: <PERSONAL-ACCESS-TOKEN>
```

The CDS client can alternatively read the standard `CDSAPI_URL` and `CDSAPI_KEY` environment
variables. `CDSAPI_RC` can point to a credential file in a non-default location. Credentials are
never read from `configs/pipeline.yaml` or written to the download ledger.

CDS may package accumulated precipitation and instantaneous variables in separate NetCDF files
inside one ZIP response. Stage 6 detects this response, combines the members into the configured
monthly NetCDF file and validates every requested hour. Requests are submitted one month at a
time to remain below the CDS request-cost limit. A complete `.part` response retained after
an interruption or validation error is checked and recovered before a new request is submitted.

Prepare the two historical FILTER inputs:

```text
data/raw/filter/Sensor_Location.csv
data/raw/filter/BGR/SC<location_id>_<sensor_id>.csv
```

The 1,958 BGR files represent location-sensor pairs, not necessarily 1,958 physically
distinct stations. One sensor may have operated at more than one location over time. `location_id`
and `sensor_id` are there retained throughout the workflow.
Review all dates, thresholds, and paths in [`configs/pipeline.yaml`](configs/pipeline.yaml) before the full run.

## How to run

Run the stages separately so every decision can be inspected:

```bash
python scripts/01_build_sensor_manifest.py --config configs/pipeline.yaml
python scripts/02_download_archive.py --config configs/pipeline.yaml
python scripts/03_prepare_sensor_observations.py --config configs/pipeline.yaml
python scripts/04_check_sensor_completeness.py --config configs/pipeline.yaml
python scripts/05_select_stable_panel.py --config configs/pipeline.yaml
python scripts/06_download_era5.py --config configs/pipeline.yaml
python scripts/07_prepare_predictors.py --config configs/pipeline.yaml
python scripts/08_build_model_table.py --config configs/pipeline.yaml
python scripts/09_validate_random_forest.py --config configs/pipeline.yaml
python scripts/09b_select_random_forest.py \
  --config configs/pipeline.yaml \
  --candidate-rank <rank> \
  --reason "<brief validation-based reason>"
python scripts/10_train_random_forest.py --config configs/pipeline.yaml
python scripts/11_predict_counterfactual.py --config configs/pipeline.yaml
python scripts/12_summarise_results.py --config configs/pipeline.yaml
```

Stage 9 evaluates the complete configured Random Forest grid but does not select a model. Inspect
`data/interim/model/rf_tuning_results.csv`, then pass the chosen `candidate_rank` to Stage 9b.
Selection must use the blocked validation diagnostics rather than the autumn 2024 result. Stage 9b
records the decision and then evaluates the frozen candidate on that recent holdout.

If time permits, compare Gradient Boosting on exactly the same folds before selecting the RF:

```bash
python scripts/09c_validate_gradient_boosting.py --config configs/pipeline.yaml
```

Or run the workflow through RF candidate validation:

```bash
sofia-lez --config configs/pipeline.yaml run --include-provisional-panel --include-modeling
```

Use `--skip-download` when the Sensor.Community archive is already cached and
`--skip-era5-download` when the ERA5 NetCDF chunks are already cached.
Because model selection requires an audited decision, `--include-modeling` stops after Stage 9.
Stages 9b–12 are then run explicitly.

## Workflow

| Stage | Main output | Purpose |
|---|---|---|
| Sensor manifest | `data/interim/sensors/sofia_sensor_manifest.csv` | Identify sensor-location pairs within Sofia and summarise historical coverage |
| Archive retrieval | `data/raw/sensor_community/` | Store daily Sensor.Community source files |
| Observation preparation | `data/interim/sensors/pm25_hourly_unified.csv` | Combine the two sensor sources and retain hourly QC results |
| Daily aggregation | `data/processed/daily_pm25.csv` | Calculate daily PM₂.₅ and apply daily coverage and upper-bound checks |
| Completeness assessment | `data/interim/diagnostics/completeness_sensor_year.csv` and `completeness_sensor_season.csv` | Measure sensor availability across the required periods |
| Stable-panel selection | `data/interim/diagnostics/stable_panel.csv` | Identify sensor-location pairs meeting the completeness requirement |
| ERA5 retrieval | `data/raw/meteorology/era5/` and its download ledger | Cache reproducible monthly hourly ERA5 NetCDF chunks for the stable-panel extent |
| Predictor preparation | `data/interim/predictors/daily_predictors.csv` | Match ERA5 grid cells to stable pairs and aggregate weather to Sofia local days |
| Model-table construction | `data/processed/model_table.csv` | Join the complete predictor panel to available QC-valid daily PM₂.₅ observations |
| RF candidate validation | `data/interim/model/rf_tuning_results.csv` | Compare all configured RF candidates on three complete blocked heating seasons |
| Optional Gradient Boosting comparison | `data/interim/model/gradient_boosting_tuning_results.csv` | Compare a second tree-ensemble method on the same folds without replacing the RF |
| RF selection and recent holdout | selected parameters, validation diagnostics and test metrics | Record an audited RF choice, recreate its fold predictions and then assess autumn 2024 |
| Final model | `models/random_forest.joblib` | Fit the selected Random Forest to all accepted 2018–2024 heating-month observations |
| Counterfactual prediction | `data/processed/counterfactual_predictions.csv` | Predict the two post-LEZ periods using observed weather and temporal conditions |
| Result summary | tables under `outputs/tables/` | Compare observed and predicted PM₂.₅ by period, date and sensor-location pair |

`configs/model.yaml` records the response, predictor list, blocked validation dates, recent
holdout, random seeds and hyperparameter grids. The selected RF candidate and reason are written
to a separate JSON record. The post-LEZ response is never used for model selection or fitting.

## Documentation
The repository contains two complementary records:

- [`docs/seminar_methodology.md`](docs/seminar_methodology.md) describes the technical
  methodology, data-processing rules and relationship between the methodological stages and the
  code;
- [`docs/research_log.md`](docs/research_log.md) records commands, outputs, data checks,
  methodological decisions and problems encountered during the development of the project.

The [`scripts/README.md`](scripts/README.md) lists the numbered workflow stages, while
[`data/README.md`](data/README.md) describes the data-directory structure.

## Sample data and tests

`sample_data/` contains a tiny synthetic polygon, location table, historical pair files, and
one Sensor.Community-style archive file. It is intentionally small and exists only to test the
software contract:

```bash
make sample
make test
make lint
```

Continuous integration repeats linting, unit tests, and the sample end-to-end workflow on every
push and pull request.

## Data sources

- [BGAir/FILTER dataset](https://figshare.com/articles/dataset/_i_Harmonized_Standardized_and_Corrected_Crowd-Sourced_Low-Cost_Sensor_i_PM_sub_2_5_sub_i_Data_f_i_i_rom_i_i_Sensor_community_and_PurpleAir_Networks_i_i_Across_Europe_i_/27195720/1) — historical sensor observations and sensor-location information
- [Sensor.Community archive](https://archive.sensor.community/) — daily SDS011 observations from
  2024 onwards
- [ERA5 hourly data on single levels](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels) — hourly meteorological predictors
- [SofiaPlan API](https://sofiaplan.bg/api/) — Sofia Municipality boundary
- [AirBG](https://airbg.info/en/build-a-station/) — information about Sofia’s community-operated
  sensor network

## License

Code is released under the [MIT License](LICENSE). Source-data licences and attribution remain
with their respective providers and must be checked before redistribution.
