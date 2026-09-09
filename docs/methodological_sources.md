# Methodological decisions and supporting literature

## Purpose

This document links the main workflow decisions to published literature or official technical
guidance. It is intended as a working list for the seminar report rather than as a finished
bibliography. The distinction between an adopted method, an adaptation and a project-specific
choice is important: not every threshold used in this project is a generally accepted standard.

## 1. Study design and interpretation

### 1.1 Meteorology-adjusted counterfactual

- **Decision:** Train a model on pre-LEZ PM₂.₅, meteorology, calendar variables and location,
  then supply observed post-LEZ weather to estimate a no-LEZ PM₂.₅ baseline.
- **Basis:** Random Forest meteorological-normalisation studies show that weather adjustment can
  help separate meteorological variability from changes associated with emissions and can be
  used to investigate air-quality interventions.
- **Use in the report:** The observed-minus-predicted difference is an exploratory estimate of
  departure from the pre-LEZ relationship under the weather that actually occurred.
- **Important limit:** This design alone does not identify the LEZ as the only cause. Unmeasured
  changes in emissions, sensor behaviour or the city can also produce a difference. The report
  should therefore use careful counterfactual language and avoid claiming definitive causality.
- **Sources:** [Grange et al. (2018)](https://doi.org/10.5194/acp-18-6223-2018),
  [Grange and Carslaw (2019)](https://doi.org/10.1016/j.scitotenv.2018.10.344).

### 1.2 Separation at the intervention date

- **Decision:** Exclude PM₂.₅ observations from 1 January 2025 onward from tuning and fitting.
- **Basis:** A no-intervention model must be estimated from the non-intervention regime. Allowing
  post-intervention outcomes into fitting would partly teach the model the change it is meant to
  assess.
- **Status:** Literature-informed design requirement.
- **Sources:** [Grange and Carslaw (2019)](https://doi.org/10.1016/j.scitotenv.2018.10.344),
  [Kaufman et al. (2012)](https://doi.org/10.1145/2382577.2382579).

### 1.3 Heating-month restriction

- **Decision:** Fit and evaluate the model only in January–March and October–December because these
  are the months covered by the intervention evaluation.
- **Basis:** Validation should represent the conditions in which the model will be used. Restricting
  the sample also avoids allowing abundant summer observations to dominate a winter application.
- **Status:** Study-specific target-population choice, supported indirectly by the principle of
  matching evaluation to the prediction task. It is not a universal six-month definition of a
  heating season.
- **Source:** [Roberts et al. (2017)](https://doi.org/10.1111/ecog.02881).

## 2. Validation, testing and leakage control

### 2.1 Temporally blocked expanding-window validation

- **Decision:** Use successively later complete heating seasons as validation blocks, while every
  corresponding training block contains only earlier dates and expands from 2018 onward.
- **Basis:** Random splitting is inappropriate where observations close in time are dependent.
  Blocked validation and rolling-origin evaluation preserve temporal ordering and better represent
  prediction at a later time.
- **Status:** Directly literature-informed.
- **Sources:** [Tashman (2000)](https://doi.org/10.1016/S0169-2070%2800%2900065-0),
  [Roberts et al. (2017)](https://doi.org/10.1111/ecog.02881).

### 2.2 April–September gap

- **Decision:** A validation fold trained through March resumes validation in October.
- **Basis:** The gap follows from keeping whole October–March heating seasons together and prevents
  the two halves of one winter from being split across training and validation.
- **Status:** Defensible project design, not a literature-prescribed six-month embargo. The gap does
  not by itself remove long-term dependence or concept drift.
- **Sources:** [Tashman (2000)](https://doi.org/10.1016/S0169-2070%2800%2900065-0),
  [Roberts et al. (2017)](https://doi.org/10.1111/ecog.02881).

### 2.3 Incomplete 2019–2020 season

- **Decision:** Retain its available observations inside later expanding training windows, but do
  not use the incomplete season as a standalone validation block.
- **Basis:** A validation block should provide a credible sample of the stated deployment period.
  The available October–November data remain legitimate earlier training observations, while the
  missing December–March period would make a full-season validation result misleading.
- **Status:** Data-driven project decision. It should be reported transparently rather than
  presented as a general best practice.

### 2.4 Separate autumn 2024 test

- **Decision:** Select hyperparameters with the three complete validation seasons, then evaluate
  the chosen model once on October–December 2024. The test period does not select parameters.
- **Basis:** Reusing the same observations for model selection and final evaluation causes
  optimistic selection bias. A held-out test gives a separate estimate after tuning.
- **Status:** Directly literature-informed.
- **Source:** [Cawley and Talbot (2010)](https://www.jmlr.org/papers/v11/cawley10a.html).

### 2.5 Final refit after evaluation

- **Decision:** After hyperparameters are fixed and the autumn 2024 test is recorded, refit the
  final model using all QC-valid pre-LEZ heating observations through 31 December 2024.
- **Basis:** The held-out period is needed for honest evaluation, but it contains useful
  pre-intervention information for the deployed model once all model choices are fixed.
- **Status:** Standard model-development practice. Test results must not be repeatedly consulted to
  revise the model before this refit.
- **Source:** [Cawley and Talbot (2010)](https://www.jmlr.org/papers/v11/cawley10a.html).

### 2.6 Historical-mean benchmark fitted within each split

- **Decision:** For every validation fold, calculate each sensor-location mean from that fold's
  training rows only. For the autumn 2024 test, calculate it only from the corresponding test
  training rows. Use the overall mean of the same training rows only when a pair has no training
  observation.
- **Why it matters:** A mean calculated with validation/test PM₂.₅, or with later pre-LEZ years,
  contains future target information. This is leakage and can make the simple benchmark appear
  unfairly strong.
- **Current implementation:** `_sensor_mean_prediction(train, validation, target)` reads target
  values only from `train`. `tests/test_modeling.py` contains a dedicated test with extreme future
  values to ensure that neither the sensor mean nor the fallback mean can use them.
- **Status:** Correctness requirement, now explicitly tested.
- **Sources:** [Kaufman et al. (2012)](https://doi.org/10.1145/2382577.2382579),
  [scikit-learn model-evaluation guidance](https://scikit-learn.org/stable/modules/model_evaluation.html#dummy-estimators).

### 2.7 Same-location rather than new-location validation

- **Decision:** Retain the same stable sensor-location pairs across training and later validation.
- **Basis:** This matches the intended task: predicting later dates at the monitored locations.
- **Interpretation:** The resulting errors measure temporal generalisation at known locations. They
  are not evidence that the model predicts accurately at an unmonitored street or district.
- **Status:** Deployment-aligned project decision; the limitation must accompany the results.
- **Source:** [Roberts et al. (2017)](https://doi.org/10.1111/ecog.02881).

### 2.8 Pooled and fold-specific reporting

- **Decision:** Report each fold separately and also calculate metrics from all out-of-fold rows
  pooled together. Report autumn 2024 separately as the test.
- **Basis:** Fold results show temporal instability, while pooled metrics weight observations rather
  than giving a short block the same influence as a long block.
- **Status:** Transparent reporting choice. Fold-to-fold spread remains important because only
  three tuning folds are available.

## 3. Model specification and assessment

### 3.1 Random Forest regression

- **Decision:** Use a Random Forest regressor for daily PM₂.₅.
- **Basis:** Random Forests combine many decision trees and can represent non-linear responses and
  interactions. Published air-quality work has used them for meteorological normalisation and
  intervention analysis.
- **Status:** Directly literature-informed.
- **Sources:** [Breiman (2001)](https://doi.org/10.1023/A:1010933404324),
  [Grange et al. (2018)](https://doi.org/10.5194/acp-18-6223-2018),
  [Grange and Carslaw (2019)](https://doi.org/10.1016/j.scitotenv.2018.10.344).

### 3.2 Predictor groups

- **Decision:** Use temperature, relative humidity, wind, surface pressure, precipitation,
  boundary-layer height, cyclical day of year, weekday and coordinates.
- **Basis:** Meteorological-normalisation studies combine surface meteorology, boundary-layer and
  time variables because weather and atmospheric mixing strongly influence pollutant
  concentrations.
- **Status:** Literature-informed predictor groups, adapted to the ERA5 variables available for
  Sofia. Inclusion does not prove that every individual feature is important.
- **Sources:** [Grange et al. (2018)](https://doi.org/10.5194/acp-18-6223-2018),
  [Grange and Carslaw (2019)](https://doi.org/10.1016/j.scitotenv.2018.10.344).

### 3.3 No calendar-year trend

- **Decision:** Do not include year or a linear long-term trend as a predictor.
- **Reason:** This keeps the counterfactual anchored to the observed weather–season–location
  relationship rather than forcing a short pre-period trend to extrapolate into 2025–2026.
- **Status:** Deliberate project assumption, not a rule taken from the cited meteorological-
  normalisation studies. It assumes sufficient temporal stability. Ordered fold and autumn 2024
  errors should be inspected for drift, and the longer 2025–2026 horizon should be stated as more
  uncertain.

### 3.4 Randomised hyperparameter search

- **Decision:** Search a bounded set of tree count, depth, feature fraction and minimum leaf size
  combinations with a fixed random seed.
- **Basis:** Random search is an established, computationally efficient alternative to exhaustive
  grid search when only some hyperparameters strongly affect performance.
- **Status:** The search method is literature-informed. The exact ranges and 16 iterations are
  project-specific runtime choices and should not be described as universally optimal.
- **Source:** [Bergstra and Bengio (2012)](https://www.jmlr.org/papers/v13/bergstra12a.html).

### 3.5 Pipeline and split-local fitting

- **Decision:** Keep the estimator in a scikit-learn `Pipeline` and fit it separately inside every
  temporal split.
- **Basis:** Split-local fitting preserves the separation between training and evaluation data and
  allows later preprocessing to be added without fitting it on held-out observations.
- **Status:** Official implementation best practice.
- **Source:** [scikit-learn common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage).

### 3.6 No feature scaling

- **Decision:** Do not standardise predictors for the Random Forest.
- **Basis:** Tree splits compare values within one feature, so predictors do not need a common unit
  scale in the way distance- or gradient-based models often do.
- **Status:** Algorithm-specific implementation choice. Keeping a `Pipeline` remains useful even
  when it currently contains only the estimator.
- **Source:** [Breiman (2001)](https://doi.org/10.1023/A:1010933404324).

### 3.7 Error measures

- **Decision:** Select hyperparameters by MAE and additionally report RMSE, R² and mean error.
- **Basis:** MAE gives an error in the original concentration unit with equal absolute weighting.
  RMSE gives larger errors more influence. R² describes explained variation, while signed mean
  error reveals systematic over- or under-prediction. No single metric answers all four questions.
- **Status:** Literature-informed multi-metric reporting; MAE as the selection measure is a project
  choice aligned with a readily interpretable absolute error.
- **Source:** [Chai and Draxler (2014)](https://doi.org/10.5194/gmd-7-1247-2014).

### 3.8 Feature importance

- **Decision:** Export impurity-based Random Forest feature importance as a diagnostic.
- **Caution:** Impurity importance is not a causal effect and can be biased, particularly when
  predictors differ in scale/cardinality or are correlated. It should not be used alone to claim
  that one process causes PM₂.₅ changes.
- **Status:** Useful descriptive output with a literature-backed warning. Permutation importance on
  held-out data would be a stronger additional diagnostic if interpretation becomes central.
- **Sources:** [Strobl et al. (2007)](https://doi.org/10.1186/1471-2105-8-25),
  [Strobl et al. (2008)](https://doi.org/10.1186/1471-2105-9-307).

## 4. Meteorological data

### 4.1 ERA5 hourly single-level data

- **Decision:** Use ERA5 hourly data across the complete study period and aggregate the required
  meteorological variables to Sofia local dates.
- **Basis:** ERA5 provides a temporally consistent global reanalysis with hourly output and about
  31 km native horizontal resolution. Hourly data permit correct local-day aggregation, including
  daylight-saving transitions.
- **Status:** Source choice is literature-informed. ERA5 is broad-scale meteorology and does not
  resolve neighbourhood weather within Sofia.
- **Sources:** [Hersbach et al. (2020)](https://doi.org/10.1002/qj.3803),
  [ERA5 dataset page](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels).

### 4.2 Monthly requests and validated cache

- **Decision:** Request hourly ERA5 one month at a time, validate variables and hours, retain a
  checksum ledger, and safely resume interrupted downloads.
- **Basis:** ECMWF advises smaller requests and illustrates whole-year hourly retrieval as one
  request per month. The validation, ledger and atomic `.part`-file handling are reproducibility
  safeguards added by this project.
- **Status:** Request size follows official guidance; the cache design is an engineering decision.
- **Source:** [ECMWF, How the CDS works](https://confluence.ecmwf.int/display/CKB/How+the+CDS+works).

### 4.3 Local-day aggregation and precipitation timing

- **Decision:** Convert UTC timestamps to `Europe/Sofia`; require the expected 23, 24 or 25 hours
  per local day; and assign each hourly precipitation accumulation to the hour-ending interval.
- **Basis:** ECMWF documents ERA5 accumulated variables as representing the interval ending at the
  validity time. The one-day padding and interval boundary prevent the 00:00 accumulation from
  being attributed to the wrong local date.
- **Status:** Officially informed temporal handling implemented for the Sofia calendar.
- **Source:** [ECMWF ERA5 parameter timing](https://confluence.ecmwf.int/display/CKB/ERA5%3A+data+documentation).

### 4.4 Relative humidity and wind speed derivation

- **Decision:** Derive relative humidity from 2 m temperature and dew point with the Magnus
  saturation-vapour relation, and derive wind speed as the magnitude of the 10 m u/v components.
- **Basis:** These are standard physical transformations. The Magnus constants in the code are the
  Alduchov–Eskridge coefficients described by Lawrence.
- **Status:** Literature-informed calculation.
- **Source:** [Lawrence (2005)](https://doi.org/10.1175/BAMS-86-2-225).

### 4.5 Nearest ERA5 grid point

- **Decision:** Assign every fixed sensor-location pair to the nearest ERA5 grid point and retain
  the selected grid coordinates in the predictor table.
- **Reason:** This is transparent, deterministic and adequate for using ERA5 as a broad daily
  weather control.
- **Status:** Pragmatic project choice, not a claim of neighbourhood-scale interpolation. ERA5's
  coarse resolution means that several sensors share the same meteorological series. Sensitivity
  to bilinear interpolation could be checked later, but would not create genuinely local weather.
- **Source:** [Hersbach et al. (2020)](https://doi.org/10.1002/qj.3803).

## 5. Sensor processing and panel construction

### 5.1 Sensor-location pair as the observational unit

- **Decision:** Identify an observation site by `(location_id, sensor_id)` rather than assuming a
  sensor ID always represents one fixed station.
- **Basis:** The source archive can contain the same physical sensor identifier at different
  locations. Retaining both identifiers avoids joining measurements to the wrong coordinates.
- **Status:** Source-structure and data-integrity requirement.

### 5.2 FILTER-informed hourly quality control

- **Decision:** Retain the FILTER QC code and spread criterion for historical observations, and
  reconstruct comparable three-bin hourly coverage for Sensor.Community observations. Use raw P2
  rather than claiming absent correction fields are corrected data.
- **Basis:** FILTER provides a published framework for harmonising and quality-controlling
  crowd-sourced European PM₂.₅ data and underlies the historical dataset used here.
- **Status:** Adapted from the source methodology. The archive processing does not reproduce all
  FILTER spatial and correction stages, so the two sources must not be described as identically
  corrected.
- **Source:** [Hassani et al. (2025)](https://doi.org/10.1016/j.jenvman.2025.125100).

### 5.3 Rolling median/MAD screen

- **Decision:** Use a centred 360-hour rolling median/MAD context, but allow 72 observations and
  apply the permissive threshold `max(75 µg/m³, 8 × 1.4826 × MAD)`.
- **Basis:** The broad rolling-window approach and 360-hour context are FILTER-informed.
- **Status:** The 72-observation minimum, absolute 75 µg/m³ floor and exact combined threshold are
  project adaptations intended to avoid removing real winter peaks. They require transparent
  reporting and, if feasible, sensitivity checks.
- **Source:** [Hassani et al. (2025)](https://doi.org/10.1016/j.jenvman.2025.125100).

### 5.4 Daily aggregation with at least 18 valid hours

- **Decision:** Calculate a daily mean only when at least 18 of 24 nominal hours are valid.
- **Basis:** This 75% daily-coverage rule has precedent in published low-cost PM₂.₅ processing.
- **Status:** Literature-informed analytical threshold rather than a claim of regulatory
  equivalence.
- **Source:** [Dhammapala et al. (2022)](https://doi.org/10.4209/aaqr.210266).

### 5.5 Daily PM₂.₅ upper screen

- **Decision:** Exclude daily means greater than or equal to 250 µg/m³ after retaining the
  pre-screen value and QC flag.
- **Reason:** Inspection found repeated saturation-like values, including 999.9 µg/m³, that did
  not resemble plausible Sofia episodes.
- **Status:** Project-specific safeguard, not a published health, legal or instrument threshold.
  Results near this choice should be checked in a sensitivity analysis (for example, no daily
  screen and alternative upper bounds).

### 5.6 Stable-panel completeness threshold

- **Decision:** Require at least 60% valid days across the pooled pre-LEZ period and separately in
  each post-LEZ evaluation period.
- **Reason:** This balances temporal continuity against loss of spatial coverage in a voluntary
  network.
- **Status:** Project-specific selection rule, deliberately less strict than regulatory-monitoring
  completeness objectives. It should be accompanied by retained/excluded sensor counts and, if
  possible, sensitivity results at alternative thresholds.
- **Context source:** [European Environment Agency monitoring-station criteria](https://www.eea.europa.eu/en/topics/in-depth/air-pollution/monitoring-station-classifications-and-criteria/).

### 5.7 Missing observations

- **Decision:** Keep missing or QC-failed PM₂.₅ as missing rather than replacing it with zero.
  Build the model table from the complete predictor panel so prediction dates remain available
  even where observed PM₂.₅ is absent.
- **Basis:** Zero is a concentration value, not a missing-data code. Separating predictor coverage
  from response availability also makes the observed comparison coverage explicit.
- **Status:** Data-integrity and transparent-reporting requirement.

## 6. Highest-priority report limitations and checks

1. Describe the result as an exploratory weather-adjusted counterfactual, not definitive causal
   attribution to the LEZ.
2. Show Random Forest and historical-mean performance for every validation fold and the separate
   autumn 2024 test.
3. Plot fold errors in chronological order to assess temporal drift. State that the second
   post-LEZ period has a longer extrapolation horizon than the validation blocks.
4. State that validation concerns later dates at the same locations, not unmonitored locations.
5. Report valid-observation coverage for every post-LEZ comparison and do not impute missing PM₂.₅
   as zero.
6. Treat the 250 µg/m³ daily screen, 60% panel threshold and adapted temporal-QC thresholds as
   project choices. Prefer sensitivity checks over claims that these are standard values.
7. Treat impurity feature importance as descriptive only; do not interpret it as a causal ranking.

## 7. Reference list

- Bergstra, J. and Bengio, Y. (2012). Random search for hyper-parameter optimization.
  *Journal of Machine Learning Research*, 13, 281–305.
  <https://www.jmlr.org/papers/v13/bergstra12a.html>
- Breiman, L. (2001). Random forests. *Machine Learning*, 45, 5–32.
  <https://doi.org/10.1023/A:1010933404324>
- Cawley, G. C. and Talbot, N. L. C. (2010). On over-fitting in model selection and subsequent
  selection bias in performance evaluation. *Journal of Machine Learning Research*, 11,
  2079–2107. <https://www.jmlr.org/papers/v11/cawley10a.html>
- Chai, T. and Draxler, R. R. (2014). Root mean square error (RMSE) or mean absolute error
  (MAE)? *Geoscientific Model Development*, 7, 1247–1250.
  <https://doi.org/10.5194/gmd-7-1247-2014>
- Dhammapala, R., Basnayake, A., Premasiri, S. and others (2022). PM₂.₅ in Sri Lanka:
  trend analysis, low-cost sensor correlations and spatial distribution. *Aerosol and Air
  Quality Research*, 22, 210266. <https://doi.org/10.4209/aaqr.210266>
- Grange, S. K., Carslaw, D. C., Lewis, A. C., Boleti, E. and Hueglin, C. (2018). Random forest
  meteorological normalisation models for Swiss PM₁₀ trend analysis. *Atmospheric Chemistry and
  Physics*, 18, 6223–6239. <https://doi.org/10.5194/acp-18-6223-2018>
- Grange, S. K. and Carslaw, D. C. (2019). Using meteorological normalisation to detect
  interventions in air quality time series. *Science of the Total Environment*, 653, 578–588.
  <https://doi.org/10.1016/j.scitotenv.2018.10.344>
- Hassani, A., Salamalikis, V., Schneider, P., Stebel, K. and Castell, N. (2025). A scalable
  framework for harmonizing, standardization, and correcting crowd-sourced low-cost sensor PM₂.₅
  data across Europe. *Journal of Environmental Management*, 380, 125100.
  <https://doi.org/10.1016/j.jenvman.2025.125100>
- Hersbach, H. and others (2020). The ERA5 global reanalysis. *Quarterly Journal of the Royal
  Meteorological Society*, 146, 1999–2049. <https://doi.org/10.1002/qj.3803>
- Kaufman, S., Rosset, S., Perlich, C. and Stitelman, O. (2012). Leakage in data mining:
  formulation, detection, and avoidance. *ACM Transactions on Knowledge Discovery from Data*,
  6(4), 15. <https://doi.org/10.1145/2382577.2382579>
- Lawrence, M. G. (2005). The relationship between relative humidity and the dewpoint
  temperature in moist air: a simple conversion and applications. *Bulletin of the American
  Meteorological Society*, 86, 225–233. <https://doi.org/10.1175/BAMS-86-2-225>
- Roberts, D. R. and others (2017). Cross-validation strategies for data with temporal, spatial,
  hierarchical, or phylogenetic structure. *Ecography*, 40, 913–929.
  <https://doi.org/10.1111/ecog.02881>
- Strobl, C., Boulesteix, A.-L., Zeileis, A. and Hothorn, T. (2007). Bias in random forest
  variable importance measures: illustrations, sources and a solution. *BMC Bioinformatics*, 8,
  25. <https://doi.org/10.1186/1471-2105-8-25>
- Strobl, C., Boulesteix, A.-L., Kneib, T., Augustin, T. and Zeileis, A. (2008). Conditional
  variable importance for random forests. *BMC Bioinformatics*, 9, 307.
  <https://doi.org/10.1186/1471-2105-9-307>
- Tashman, L. J. (2000). Out-of-sample tests of forecasting accuracy: an analysis and review.
  *International Journal of Forecasting*, 16, 437–450.
  <https://doi.org/10.1016/S0169-2070(00)00065-0>
