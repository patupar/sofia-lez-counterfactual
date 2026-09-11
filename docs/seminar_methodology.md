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

Meteorological predictors are derived from the ERA5 hourly single-level reanalysis. The selected
variables are 2 m temperature, 2 m dew-point temperature, 10 m u- and v-wind, surface pressure,
total precipitation and boundary-layer height. Using the hourly source rather than a derived
daily product allows all variables to be aggregated to `Europe/Sofia` local dates, including
23- and 25-hour days at daylight-saving transitions.

#### 1.2.3 Local Climate Zones

Local urban form is represented by the supplied filtered Global Local Climate Zone (LCZ)
version 3 raster. The raster has a nominal spatial resolution of approximately 100 m, uses the
17-class LCZ scheme and represents the nominal year 2018 (Demuzere et al., 2022). It has already
been clipped around Sofia and is stored locally rather than downloaded by the workflow.


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
inclusion. The completeness assessment provides the inputs for the final panel selection performed
by `scripts/05_select_stable_panel.py`.

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

`scripts/06_download_era5.py` reads the Stage 5 stable-panel coordinates and constructs the ERA5
request area around their combined extent with a configured 0.25-degree buffer. The request
settings are stored in `configs/pipeline.yaml`; no CDS credential is stored in the project. The
CDS client reads the user's external `~/.cdsapirc` file or its standard environment variables.

Requests are split into monthly NetCDF chunks and include one additional date on either side of
the study window. Monthly requests follow ECMWF guidance for hourly ERA5 retrievals and remain
below the CDS request-cost limit encountered by the initial annual request. Downloads first use a
`.part` file and are renamed only after the file can be opened and all configured variables and
requested hours have been found. Existing valid chunks are reused. The download ledger stores the
request, status, elapsed time, file size and SHA-256 checksum without storing authentication
information.

The CDS NetCDF converter separates instantaneous fields and accumulated fields such as total
precipitation when their GRIB step types differ. It can therefore return a ZIP archive containing
separate NetCDF members even when an unarchived response was requested. The downloader detects
this case, combines the members by timestamp and grid coordinate, and writes one validated monthly
NetCDF file. Validation requires every configured variable and requested UTC hour. A retained
complete `.part` response is processed before any replacement request is sent.

`scripts/07_prepare_predictors.py` assigns each stable sensor-location pair to its nearest ERA5
grid point and records that grid point's latitude and longitude. It calculates hourly relative
humidity from temperature and dew point and hourly wind speed from the u- and v-components.
Instantaneous variables are averaged across each Sofia local calendar day. Surface pressure is
converted from Pa to hPa and temperature from K to degrees Celsius.

ERA5 total precipitation is an hourly accumulation ending at the recorded timestamp. Daily
precipitation therefore comprises intervals ending after local midnight through the following
local midnight and is converted from metres to millimetres. The procedure requires the exact
23, 24 or 25 hourly values expected for every local day and fails rather than imputing incomplete
meteorological records.

The resulting table also contains cyclical day-of-year variables, weekday and a heating-season
label. The heating-season label is retained for grouping and diagnostics; it is not part of the
initial numeric Random Forest predictor list.

#### Local Climate Zones

`scripts/07b_prepare_lcz.py` reads the supplied raster and calculates LCZ composition from pixel
centres inside a 500 m circular buffer around each stable sensor-location pair. This provides
neighbourhood context rather than assigning only the LCZ value underneath the sensor. The 17
original class fractions and dominant class are retained for checking, while the model uses five
pre-defined fractions: compact built (classes 1–3), open built (4–6), other built (7–10),
vegetation (11–14), and bare surfaces and water (15–17).

Each class belongs to exactly one group. The code requires the grouped fractions to lie between
zero and one and to sum to one for every sensor-location pair. LCZ values are static and are
therefore calculated once for each pair rather than separately for every day.

### 2.2 Sensor quality control

Quality control (QC) is applied at hourly resolution. The output retains each component flag and
the combined `qc_pass` flag. This keeps rejected observations available for inspection.

#### FILTER observations

An hourly FILTER observation passes QC when all of the following conditions are true:

- `raw_qc` starts with the configured prefix `1233`;
- `spread` equals `3`; and
- `raw_pm2_5` lies within the configured range of 0–1000 µg/m³.

The concentration range and spread criterion follow the FILTER methodology (Hassani et al.,
2025). The upper boundary represents the plausible operating range of the low-cost sensors and
is not derived from the highest PM₂.₅ concentration observed in Sofia.

FILTER defines `spread` by dividing each hour into three twenty-minute bins. A value of `3`
indicates that the observations used for the hourly mean cover all three parts of the hour. This
provides a more representative hourly value than observations concentrated within only one part
of the hour.

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

The temporal check uses a centred 360-clock-hour window for each sensor-location pair. The
rolling median and median absolute deviation (MAD) are calculated directly from the available
values within that window. FILTER selected this window length because the variability of rolling
MAD values stabilised at approximately 360 hours in European reference-station records (Hassani
et al., 2025).

The archive implementation adapts the FILTER procedure to the long and partly discontinuous
Sensor.Community record. It requires at least 72 valid hourly values within the window, rather
than the 90 used by FILTER. This relaxed requirement allows the temporal check to operate where
short gaps occur without excluding extended parts of otherwise usable sensor records. If fewer
than 72 values are available, the observation is not rejected solely because the temporal
context is insufficient.

A potential spike is evaluated against the larger of:

- eight scaled median absolute deviations, where the scale factor is 1.4826; and
- an absolute difference of 75 µg/m³ from the rolling median.

These are deliberately permissive project settings rather than thresholds adopted directly from
FILTER. They provide a simple safeguard against isolated extreme values while reducing the risk
of removing genuine winter pollution episodes. FILTER uses nearby measurements to distinguish
sensor errors from spatially coherent pollution events; the archive procedure does not reproduce
that neighbour-based test. The absolute threshold therefore prevents small local variability
from producing an excessively strict spike criterion.

The archive procedure cannot reproduce all FILTER processing steps. In particular, it does not
contain the FILTER constant-value, spatial-correlation, spatial-similarity or correction
procedures. The unified table therefore identifies the source and exact QC settings for every
hour instead of presenting the two QC procedures as identical.

### 2.3 Completeness and panel selection

`src/sofia_lez/completeness.py` calculates completeness for each sensor-location pair. Expected
hours are generated in `Europe/Sofia` time so that daylight-saving transitions are counted
correctly. Hour completeness is based on the hourly QC table. Day completeness is based on the
daily QC table and therefore includes both the 18-hour requirement and the daily PM2.5 upper-bound
check. The output reports observed hours, QC-valid hours, valid days and the corresponding
fractions for each sensor-year and heating period.

The stable-panel rule requires at least 60% of expected days in each of three criteria:

| Criterion | Period | Calculation |
|---|---|---|
| Pre-LEZ | 1 January 2018–31 December 2024 | valid days pooled across all seven years |
| Post-LEZ 1 | 1 January–31 March 2025 | valid days within the evaluation window |
| Post-LEZ 2 | 1 October 2025–31 March 2026 | valid days within the evaluation window |

The 60% threshold is a relaxed project-specific requirement rather than a regulatory
completeness standard. The combined record spans several years and originates from a voluntary
sensor network in which interruptions and changes in availability are expected. Requiring every
sensor-location pair to satisfy a stricter threshold in every period could substantially reduce
the spatial coverage of the stable panel. The selected threshold attempts a balance between 
temporal continuity against sensor retention.

`scripts/05_select_stable_panel.py` applies these criteria to the Stage 4 completeness tables.
The panel table retains all candidate pairs, the numerator, denominator, completeness and pass
flag for every criterion, and the combined decision in `stable_panel`. It does not delete pairs
that fail the threshold. This permits inspection of sensor attrition and tests with alternative
completeness thresholds.

### 2.4 Daily aggregation

`src/sofia_lez/daily.py` calculates the arithmetic mean of QC-valid hourly PM₂.₅ values for each
sensor-location pair and local date. A day requires at least 18 valid hours, corresponding to 75%
coverage of a 24-hour day. This completeness criterion has precedent in published PM₂.₅ analyses
using low-cost sensor observations (Dhammapala et al., 2022).

As a project-specific analytical safeguard, daily means equal to or above 250 µg/m³ are excluded
from the analysis. This deliberately simple threshold is applied after daily aggregation rather
than to individual hours. It therefore does not replace the hourly 0–1000 µg/m³ operating-range
check or remove short high-concentration episodes that produce a daily mean below 250 µg/m³.

The table retains the calculated mean in `pm2_5_before_daily_qc` for inspection. Its analytical
`pm2_5` value is missing and `daily_qc_pass` is false when the day contains fewer than 18 valid
hours or its mean is at least 250 µg/m³. Missing values are not replaced with zero.

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

Meteorological conditions are assigned from the nearest ERA5 grid point. The selected ERA5
latitude and longitude remain in the predictor table so the spatial assignment can be inspected.
ERA5 is not interpreted as neighbourhood-scale weather: its role is to control the broad daily
meteorological variation affecting the fixed sensor locations.

LCZ provides finer local spatial context around the same fixed locations. Stage 8 verifies that
the LCZ table and meteorological predictor table contain the same sensor-location pairs and
coordinates before the static LCZ fractions are repeated across the corresponding daily rows.

### 3.2 Temporal harmonisation

Source timestamps are parsed as UTC and converted to `Europe/Sofia`. Hourly QC uses UTC hours to
avoid ambiguous timestamps during daylight-saving transitions. Daily aggregation and reporting
use Sofia local dates.

The FILTER record ends on 31 December 2023, and the Sensor.Community record starts on 1 January
2024. Both boundaries are applied to Sofia local dates. This prevents hours from the two sources
being combined within the same local sensor-day around the source transition. The code also
rejects overlapping hourly records for the same sensor-location pair. The final study date is
evaluated in Sofia local time.

ERA5 timestamps are parsed as UTC and converted to the same `Europe/Sofia` calendar used for the
PM2.5 daily observations. Instantaneous variables and ending-time precipitation accumulations
use separate interval rules before they are joined by local date. Temporal aggregation uses only
information from the corresponding observation period.

## 4. Machine-learning workflow

### 4.1 Model table

`scripts/08_build_model_table.py` first joins the five static LCZ fractions to the daily
meteorological predictor panel using `location_id` and `sensor_id`. It then joins the daily sensor
observations using `location_id`, `sensor_id` and local date. Daily PM₂.₅ is the response
variable. The predictors listed in `configs/model.yaml` are the eight meteorological variables,
the sine and cosine of day of year, weekday, latitude, longitude and five grouped LCZ fractions.
Sensor and location identifiers are retained for grouping and checking but are not treated as
continuous model inputs.

The join begins from the predictor table. Consequently, the model table retains one row for every
stable sensor-location pair and date even where no valid PM₂.₅ observation is available. The
response remains missing when the sensor-day is unavailable or fails daily QC; it is never
imputed. `eligible_for_training` identifies the QC-valid pre-LEZ heating-month rows which can enter
model fitting.

Data-dependent preprocessing and model choices are based only on pre-LEZ training data. 
Observed post-LEZ PM₂.₅ values do not influence model development and are reserved for 
comparison with the counterfactual predictions. Dates and sensor-location identifiers 
are retained to support temporal validation (see 4.3). 


### 4.2 Pre-LEZ training

The model is a Random Forest regressor. Training uses observations from January–March and 
October–December between 1 January 2018 and 31 December 2024. This restricts model fitting 
to the heating-season months represented in the counterfactual periods. The model learns the 
relationship between PM₂.₅ and the predictor variables under pre-LEZ
conditions. Post-LEZ PM₂.₅ observations are excluded from training.

No feature scaling is applied because the Random Forest makes tree splits within each predictor
and does not depend on distances between differently scaled variables. The estimator remains in a
scikit-learn `Pipeline` so that tuning and final fitting use one reproducible model object. The
configuration records the predictor list, random seed, search space and fitted parameters. The
trained pipeline is saved to `models/random_forest.joblib`, accompanied by model metadata and a
table of impurity-based feature importance.

### 4.3 Model tuning and validation

Validation uses blocked time periods rather than a random split of individual sensor-days. This
prevents neighbouring dates from appearing in both training and validation data. Only 
observations from January–March and October–December are included. The training window expands
forward through time while each validation block remains later than its corresponding training
data:

| Fold | Expanding training period | Validation block |
|---|---|---|
| `heating_2021_2022` | Heating months from 1 January 2018–31 March 2021 | 1 October 2021–31 March 2022 |
| `heating_2022_2023` | Heating months from 1 January 2018–31 March 2022 | 1 October 2022–31 March 2023 |
| `heating_2023_2024` | Heating months from 1 January 2018–31 March 2023 | 1 October 2023–31 March 2024 |

The April–September gap prevents parts of the same heating season from being placed on both sides
of a split. The incomplete 2019–2020 season is not used as its own validation block. All dates and
fold boundaries are explicit in `configs/model.yaml`.

`scripts/09_validate_random_forest.py` uses `GridSearchCV` to evaluate every configured
combination of number of trees, maximum tree depth, number of candidate features and minimum leaf
size. The current grid contains 54 candidates, each fitted on three blocked folds, resulting in
162 fits. For every candidate the output records fold-specific and mean validation MAE, RMSE and
R², training MAE, the training-validation MAE gap and fit time. It also marks candidates whose
mean MAE falls within one standard error of the lowest-MAE candidate. Stage 9 does not select a
model and does not evaluate October-December 2024.

The candidate is fixed explicitly with `scripts/09b_select_random_forest.py`, using its rank in
the Stage 9 table and a short written reason. This allows validation error, fold variability and
the training-validation gap to be considered together instead of automatically accepting a
marginal numerical winner. A search identifier links the selection to the exact Stage 9 run and
prevents final training with a selection made from an older tuning table.

Stage 9b first recreates the chosen model's predictions over all validation folds and writes
pooled, fold-specific, monthly, seasonal-part and sensor-location diagnostics. It then records the
chosen parameters and reason before fitting the model through 31 March 2024 and assessing it on
1 October-31 December 2024. The recent pre-LEZ period therefore remains outside candidate
selection. Because results for this period were inspected during the earlier automatic-selection
workflow, it is described as a recent holdout robustness check rather than a completely untouched
final test. No further model changes should be made in response to this period's result. After the
check, `scripts/10_train_random_forest.py` fits the final model using all accepted pre-LEZ
heating-month observations, including October-December 2024.

The Random Forest is also compared with a simple benchmark which predicts each sensor-location
pair's mean PM₂.₅ from the corresponding training block. If a pair has no accepted training value
in an early fold, the overall training mean is used for that pair. This shows whether the fitted
model improves upon a fixed historical sensor level. The sensor means and fallback mean are
recalculated inside every fold from that fold's training rows only. Validation and test PM₂.₅
values therefore cannot influence their own benchmark predictions.

**Note:** Spatial hold-out validation is omitted from the methodology at this point. The model 
predicts later observations for the same stable sensor location pairs rather than at previously
unseen locations. 

Mean absolute error (MAE) is the primary validation measure. Root mean squared error (RMSE)
shows sensitivity to large errors, and the coefficient of determination (R²) describes the
explained variation. Mean error, calculated as prediction minus observation, reports systematic
over- or under-prediction. Metrics are written for every fold, for all out-of-block predictions
combined, and separately for October-December and January-March. A second table reports the same
measures for each sensor-location pair so that poor performance at individual locations is not
hidden by the overall result. Monthly metrics show whether errors are concentrated in particular
parts of a winter. A predictor-shift table compares the mean and standard deviation of each input
between every training block and its later evaluation block. The autumn 2024 holdout metrics and
predictions are stored separately from the validation outputs.

If time permits, `scripts/09c_validate_gradient_boosting.py` evaluates an optional histogram-based
Gradient Boosting regressor with the same response, predictors and blocked folds. Gradient
Boosting is a separate tree-ensemble method, not a type of Random Forest: trees are added
sequentially to correct earlier errors rather than being fitted independently and averaged. Its
internal random early-stopping split is disabled so that only the declared temporal folds govern
validation. This stage creates a comparison table only and does not automatically replace the
Random Forest selected for the main analysis.

No calendar-year trend is supplied to the Random Forest. The counterfactual therefore assumes
that the pre-LEZ relationship between PM₂.₅, weather, season and location remains sufficiently
stable during the post-intervention periods. Changes in error across the ordered validation folds
provide a diagnostic for possible temporal drift, but may also reflect differences between
winters or the observation sources.

### 4.4 No-LEZ baseline prediction

The fitted model receives the observed meteorological, temporal and spatial predictors for the
post-LEZ periods. It does not receive an LEZ indicator or post-LEZ PM₂.₅ as an input. Its output
is the PM₂.₅ concentration expected if the pre-LEZ predictor-response relationship had continued.

The counterfactual periods are:

- 1 January–31 March 2025; and
- 1 October 2025–31 March 2026.

The prediction table retains observed PM2.5, predicted no-LEZ PM₂.₅, date and sensor-location
identifiers. Predictions are produced for every stable-pair predictor row in the two periods,
including dates on which the observed PM₂.₅ response is missing. Observed-minus-predicted
differences are calculated only where a QC-valid observation exists. This supports comparisons by
date and sensor-location pair without replacing missing observations.

## 5. Anomaly assessment

`scripts/12_summarise_results.py` aggregates the post-LEZ prediction table by counterfactual
period, local date and sensor-location pair. Each output reports the total number of predicted
rows, the number and coverage of comparable observed rows, the observed and predicted means on
those same rows, and the observed-minus-predicted absolute and relative difference. A separate
predicted mean across all rows is retained so that incomplete observation coverage remains
visible. These differences describe departure from the fitted no-LEZ baseline; they are not by
themselves proof that the LEZ caused the departure.

## 6. Code and data reference
The table below links each methodological step to its relevant script, module and resulting 
output. 

| Method | Entry point | Core module | Main output |
|---|---|---|---|
| Build sensor manifest | `scripts/01_build_sensor_manifest.py` | `manifest.py` | `data/interim/sensors/sofia_sensor_manifest.csv` |
| Retrieve archive | `scripts/02_download_archive.py` | `downloader.py` | `data/raw/sensor_community/` and `download_ledger.jsonl` |
| Prepare hourly and daily observations | `scripts/03_prepare_sensor_observations.py` | `sensors.py`, `qc.py`, `daily.py` | Unified hourly and daily PM2.5 tables |
| Calculate completeness | `scripts/04_check_sensor_completeness.py` | `completeness.py` | Sensor-year and sensor-season tables |
| Select stable panel | `scripts/05_select_stable_panel.py` | `completeness.py` | `data/interim/diagnostics/stable_panel.csv` |
| Retrieve ERA5 | `scripts/06_download_era5.py` | `meteorology.py` | Monthly NetCDF chunks and `download_ledger.jsonl` |
| Prepare predictors | `scripts/07_prepare_predictors.py` | `meteorology.py` | `data/interim/predictors/daily_predictors.csv` |
| Prepare LCZ features | `scripts/07b_prepare_lcz.py` | `lcz.py` | `data/interim/predictors/lcz_sensor_features.csv` |
| Build model table | `scripts/08_build_model_table.py` | `modeling.py` | `data/processed/model_table.csv` |
| Compare Random Forest candidates | `scripts/09_validate_random_forest.py` | `modeling.py` | Complete RF candidate table from blocked folds |
| Select Random Forest and run diagnostics | `scripts/09b_select_random_forest.py` | `modeling.py` | Recorded selection, validation diagnostics and recent-holdout outputs |
| Compare Gradient Boosting (optional) | `scripts/09c_validate_gradient_boosting.py` | `modeling.py` | Gradient Boosting candidate table from the same folds |
| Train final Random Forest | `scripts/10_train_random_forest.py` | `modeling.py` | `models/random_forest.joblib` and model metadata |
| Predict no-LEZ baseline | `scripts/11_predict_counterfactual.py` | `modeling.py` | `data/processed/counterfactual_predictions.csv` |
| Summarise results | `scripts/12_summarise_results.py` | `modeling.py` | Period, date and sensor-location summary tables |

All entry points read `configs/pipeline.yaml`, which points to the model specification in
`configs/model.yaml`. `pyproject.toml` defines the Python dependencies.
`sample_data/` contains synthetic data for `tests/test_pipeline.py`, while
`tests/test_modeling.py` generates a small multi-season panel during the test. The offline tests
cover spatial filtering, archive URL patterns, manifest construction, source combination,
completeness, daily aggregation, LCZ grouping and the complete model workflow without contacting
external services.

## 7. References

Dhammapala, R., Huynh, T., & Singamsetti, V. (2022). Evaluation of twenty-three low-cost PM₂.₅
sensors in the field: Can they be used for continuous monitoring? *Aerosol and Air Quality
Research, 22*, 210266. https://doi.org/10.4209/aaqr.210266

Demuzere, M., Kittner, J., Martilli, A., Mills, G., Moede, C., Stewart, I. D., van Vliet, J., &
Bechtel, B. (2022). A global map of local climate zones to support earth system modelling and
urban-scale environmental science. *Earth System Science Data, 14*, 3835–3873.
https://doi.org/10.5194/essd-14-3835-2022

Hassani, A., Castell, N., Schneider, P., Taherian, M., & Hassani, A. (2025). Harmonized,
standardized and corrected crowd-sourced low-cost sensor PM₂.₅ data from Sensor.Community and
PurpleAir networks across Europe. *Journal of Environmental Management, 376*, 125100.
https://doi.org/10.1016/j.jenvman.2025.125100
