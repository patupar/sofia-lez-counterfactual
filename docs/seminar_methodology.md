# Codebase Documentation: A counterfactual assessment of Sofia's Residential Heating Low Emission Zone 

## 1. Prelude

This document provides the technical documentation for the codebase of the related GeoML seminar 
project. It describes the employed methodology and relevant scripts. 

### 1.1 Spatial and temporal framework
The employed methodology is intended for the study area Sofia, Bulgaria as defined by its
municipal boundaries. The intended study period runs from 1 January 2018 through 31 March 2026. 
Modelling uses observations before 1 January 2025 for training and validation. It then predicts PM₂.₅ concentrations expected after that date if the pre-LEZ relationship between PM₂.₅, weather, time 
and location had continued.

### 1.2 Data sources

#### 1.2.1 PM2.5
PM₂.₅ observations are obtained from community-operated sensors within the study area. 

The sensor record combines two sources:

| Source | Period | PM2.5 field |
|---|---|---|
| BGAir/FILTER | 1 January 2018–31 December 2023 | `raw_pm2_5` |
| Sensor.Community archive | 1 January 2024–31 March 2026 | SDS011 `P2` |

Both sources provide raw PM₂.₅ observations. Empty FILTER correction fields are not used, and
raw values are not described as corrected concentrations. `configs/pipeline.yaml` records the
dates, paths and thresholds that control the data workflow.

#### 1.2.2 Meteorological Data
[Draft: Derived from ERA5 ...]


## 2. Preprocessing

### 2.1 Data ingest

#### Sensor identity and study area

A FILTER filename has the form `SC<location_id>_<sensor_id>.csv`. The code treats this as a
sensor-location pair. It does not treat `sensor_id` as a fixed monitoring station because one
sensor can occur at different locations.

`src/sofia_lez/manifest.py` performs the following operations:

1. Read the sensor coordinates from `Sensor_Location.csv`.
2. Match the coordinates to the location identifiers in the FILTER filenames.
3. Test each coordinate against the Sofia Municipality polygon in WGS84.
4. Record the first observation, last observation and number of historical hours for each pair.
5. Record the equivalent statistics for historically QC-eligible hours.

The manifest marks a pair as `plausible_continuing` when its last raw observation occurs on or
after 1 October 2023. This flag limits archive requests. It is not the final rule for analytical
inclusion. The completeness assessment `scripts/04_check_sensor_completeness.py` defines the final sensor panel.

**Note:** _BGAir/FILTER records are retrieved from this [link](https://figshare.com/articles/dataset/_i_Harmonized_Standardized_and_Corrected_Crowd-Sourced_Low-Cost_Sensor_i_PM_sub_2_5_sub_i_Data_f_i_i_rom_i_i_Sensor_community_and_PurpleAir_Networks_i_i_Across_Europe_i_/27195720/1) under BGR.zip. Sensor_Location.csv is provided in this repository but can be retrieved from the same page._

#### Sensor.Community archive

`src/sofia_lez/downloader.py` requests one source file for each unique candidate sensor and date.
It checks two archive directory layouts and both `.csv` and `.csv.gz` formats. A daily archive
file can contain more than one location for the same sensor. The ingest step therefore stores
the unchanged source file first. The QC step later retains only rows that match an accepted
`(location_id, sensor_id)` pair.

The downloader writes data to a temporary `.part` file and renames the file after a successful
transfer. It skips existing non-empty files. `download_ledger.jsonl` records each downloaded,
cached or missing sensor-date request. A missing archive file remains missing; the code does not
replace it with a zero concentration.

**Note:** _Running the corresponding `scripts/02_download_archive.py` to completion takes considerable time.
It is advised to run this script on a stable and fast internet connection. However, if the program is 
interrupted, running `02_download_archive` will resume from the last saved file. Check research_log
on instructions to setup a status ticker. _

#### Meteorological data

Meteorological inputs must cover the complete study period and the Sofia study area. [...]

The preprocessing workflow harmonises these inputs to the sensor-day observations before it
constructs the model table.

### 2.2 Sensor quality control

Quality control (QC) is applied at hourly resolution. The output retains each component flag and
the combined `qc_pass` flag. This keeps rejected observations available for inspection.

#### FILTER observations

An hourly FILTER observation passes QC when all of the following conditions are true:

- `raw_qc` starts with the configured prefix `1233`;
- `spread` equals `3`; and
- `raw_pm2_5` lies within the configured range of 0–1000 µg/m³.

The original FILTER code remains in `source_qc_code`. The code does not infer a corrected PM2.5
value when the correction columns are empty.

#### Sensor.Community observations

The archive workflow reads SDS011 `P2` as raw PM₂.₅ It does not use `P1`. Timestamps are first
parsed as UTC. Observations within each UTC hour are assigned to
three twenty-minute bins: minutes 0–19, 20–39 and 40–59. The  mean of `P2` forms the
hourly value.

An archive hour passes QC when all of the following conditions are true:

1. The hourly PM₂.₅ mean lies within 0–1000 µg/m³.
2. All three twenty-minute bins contain at least one observation.
3. The value passes a temporal spike check.

The temporal check uses a centred rolling median and a rolling median absolute deviation (MAD)
for each sensor-location pair. The default window is 360 hours and requires at least 72 values.
The rejection threshold is the larger of 75 µg/m³ and eight scaled MAD values. The scale factor
is 1.4826. An endpoint with too few observations for the rolling calculation is not rejected for
that reason alone.

The archive procedure cannot reproduce all FILTER processing steps. In particular, it does not
contain the FILTER spatial checks or correction model. The unified table therefore identifies
the source and QC method for every hour instead of presenting the two QC procedures as identical.

### 2.3 Completeness and panel selection

`src/sofia_lez/completeness.py` calculates completeness for each sensor-location pair. Expected
hours are generated in `Europe/Sofia` time so that daylight-saving transitions are counted
correctly. The output reports observed hours, QC-valid hours, valid days and the corresponding
fractions for each sensor-year and heating period.

The stable-panel rule requires at least 60% of expected hours in every configured period:

| Role | Period |
|---|---|
| Pre-LEZ | 1 January–31 March 2024 |
| Pre-LEZ | 1 October–31 December 2024 |
| Post-LEZ | 1 January–31 March 2025 |
| Post-LEZ | 1 October–31 December 2025 |
| Post-LEZ | 1 January–31 March 2026 |

The panel table retains all candidate pairs and records the decision in `stable_panel`. It does
not delete pairs that fail the threshold. This permits inspection of sensor attrition and tests
with alternative completeness thresholds.

### 2.4 Daily aggregation

`src/sofia_lez/daily.py` calculates the arithmetic mean of QC-valid hourly PM₂.₅ values for each
sensor-location pair and local date. A day requires at least 18 valid hours. The table retains a
day with fewer valid hours, but its `pm2_5` value is missing and `daily_qc_pass` is false. Missing
values are not replaced with zero.

## 3. Spatial and temporal harmonisation

### 3.1 Spatial harmonisation

Sensor coordinates use WGS84 (`EPSG:4326`). The manifest attaches longitude and latitude to each
sensor-location pair. Later tables retain both identifiers and the coordinates.

Each sensor location is assigned to a Sofia administrative district. This identifies sensors 
located within the nine districts covered by LEZ. 

**Note:** _District membership is used for spatial context. Membership does not imply that sensor 
surroundings are directly affected by the LEZ. Within the nine covered districts, the restriction
applies only to buildings on streets with an operational district-heating or gas-distribution
network._

Meteorological [... filled in later]

### 3.2 Temporal harmonisation

Source timestamps are parsed as UTC and converted to `Europe/Sofia`. Hourly QC uses UTC hours to
avoid ambiguous timestamps during daylight-saving transitions. Daily aggregation and reporting
use Sofia local dates.

The FILTER record ends on 31 December 2023, and the Sensor.Community record starts on 1 January
2024. The code rejects overlapping hourly records for the same sensor-location pair. The final
study date is evaluated in Sofia local time.

Meteorological timestamps use the same hourly or daily index before they are joined to sensor
observations. Temporal aggregation uses only information from the corresponding observation
period.

## 4. Machine-learning workflow

### 4.1 Model table

The model table contains [t.b.d.]. 
Daily PM₂.₅ is the response variable. Predictor columns contain meteorological conditions, 
temporal variables and sensor coordinates. Only daily observations from the stable panel 
with `daily_qc_pass == True` enter the model.

Data-dependent preprocessing and model choices are based only on pre-LEZ training data. 
Observed post-LEZ PM₂.₅ values do not influence model development and are reserved for 
comparison with the counterfactual predictions. Dates and sensor-location identifiers 
are retained to support temporal validation (see 4.3). 


### 4.2 Pre-LEZ training

The model is a Random Forest regressor. Training records cover 1 January 2018 through 31 December
2024. The model learns the relationship between PM₂.₅ and the predictor variables under pre-LEZ
conditions. Post-LEZ PM₂.₅ observations are excluded from training.

The model configuration records the predictor list, random seed and fitted parameters. The
trained model is saved to `models/random_forest.joblib`.

### 4.3 Model tuning and validation

Validation uses blocked time periods rather than a random split of individual sensor-days. This
prevents neighbouring dates from appearing in both training and validation data. 
Tuning compares candidate values for the number of trees, maximum tree depth, number of 
candidate features and minimum leaf size.

**Note:** Spatial hold-out validation has been omitted for the methodology at this point. The model predicts later observations at the same stable sensor locations rather 
than at previously unseen locations. 

Mean absolute error (MAE) is the primary validation measure. Root mean squared error (RMSE)
shows sensitivity to large errors, and the coefficient of determination (R²) describes the
explained variation. The selected parameter set is fitted again with all accepted pre-LEZ
training records.

### 4.4 No-LEZ baseline prediction

The fitted model receives the observed meteorological, temporal and spatial predictors for the
post-LEZ periods. It does not receive an LEZ indicator or post-LEZ PM₂.₅ as an input. Its output
is the PM₂.₅ concentration expected if the pre-LEZ predictor-response relationship had continued.

The counterfactual periods are:

- 1 January–31 March 2025; and
- 1 October 2025–31 March 2026.

The prediction table retains observed PM2.5, predicted no-LEZ PM₂.₅, date and sensor-location
identifiers. This supports comparisons by date, sensor and administrative district.

## 5. Anomaly assessment

## 6. Code and data reference
The table below links each methodological step to its relevant script, module and resulting 
output. 

| Method | Entry point | Core module | Main output |
|---|---|---|---|
| Build sensor manifest | `scripts/01_build_sensor_manifest.py` | `manifest.py` | `data/interim/sensors/sofia_sensor_manifest.csv` |
| Retrieve archive | `scripts/02_download_archive.py` | `downloader.py` | `data/raw/sensor_community/` and `download_ledger.jsonl` |
| Prepare hourly and daily observations | `scripts/03_prepare_sensor_observations.py` | `sensors.py`, `qc.py`, `daily.py` | Unified hourly and daily PM2.5 tables |
| Calculate completeness | `scripts/04_check_sensor_completeness.py` | `completeness.py` | Sensor-year and sensor-season tables |
| Select stable panel | `sofia-lez select-panel` | `completeness.py` | `data/interim/diagnostics/stable_panel.csv` |

All entry points read `configs/pipeline.yaml`. `pyproject.toml` defines the Python dependencies.
`sample_data/` contains synthetic data for `tests/test_pipeline.py` where  spatial filter, archive
URL patterns, manifest construction, source combination, completeness rules and daily
aggregation were tested. 
